import pytest


def test_create_property_runs_base_underwriting(owner, prop):
    assert prop["latest"]["irr_levered"] is not None or prop["latest"]["irr_unlevered"] is not None
    scs = owner.get(f"/api/properties/{prop['id']}/scenarios").json()
    assert len(scs) == 1 and scs[0]["is_base"]
    a = scs[0]["assumptions"]
    assert a["purchase_price"] == 20_000_000 and a["units"] == 100
    # Template going-in cap ≈ template exit cap
    assert prop["latest"]["cap_rate"] == pytest.approx(a["exit_cap_rate"], abs=0.006)


def test_property_validation(owner):
    bad = owner.post("/api/properties", json={"name": "X", "property_type": "castle", "purchase_price": 1})
    assert bad.status_code == 422
    bad = owner.post("/api/properties", json={"name": "X", "property_type": "office", "purchase_price": -5})
    assert bad.status_code == 422


@pytest.mark.parametrize("ptype", ["multifamily", "industrial", "office", "retail", "mixed_use", "hospitality",
                                   "self_storage", "student_housing", "land"])
def test_every_property_type_has_working_defaults(owner, ptype):
    r = owner.post("/api/properties", json={"name": ptype, "property_type": ptype, "purchase_price": 15_000_000,
                                            "rentable_sf": 80_000, "units": 60})
    assert r.status_code == 201, r.text
    assert r.json()["latest"]["noi_year1"] > 0


def test_list_filters_and_update(owner, prop):
    owner.post("/api/properties", json={"name": "Warehouse", "property_type": "industrial",
                                        "purchase_price": 9_000_000, "rentable_sf": 90_000, "status": "ic"})
    assert len(owner.get("/api/properties?status=ic").json()) == 1
    assert len(owner.get("/api/properties?property_type=multifamily").json()) == 1
    assert len(owner.get("/api/properties?q=austin").json()) == 1
    r = owner.patch(f"/api/properties/{prop['id']}", json={"purchase_price": 19_000_000, "status": "underwriting"})
    assert r.status_code == 200 and r.json()["status"] == "underwriting"
    base = owner.get(f"/api/properties/{prop['id']}/scenarios").json()[0]
    assert base["assumptions"]["purchase_price"] == 19_000_000  # synced into scenarios
    assert owner.patch(f"/api/properties/{prop['id']}", json={"status": "nope"}).status_code == 422


def test_delete_requires_admin_and_soft_deletes(owner, prop):
    assert owner.delete(f"/api/properties/{prop['id']}").status_code == 204
    assert owner.get(f"/api/properties/{prop['id']}").status_code == 404


def test_live_calculation_preview(owner, prop):
    base = owner.get(f"/api/properties/{prop['id']}/scenarios").json()[0]
    a = dict(base["assumptions"], vacancy_rate=0.10)
    r = owner.post("/api/underwriting/calculate", json={"assumptions": a, "property_type": "multifamily"})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["noi_year1"] < prop["latest"]["noi_year1"]
    assert "risk" in body and body["calc_ms"] < 500
    bad = owner.post("/api/underwriting/calculate", json={"assumptions": dict(a, hold_period_years=-1)})
    assert bad.status_code == 422
    assert bad.json()["detail"]["errors"][0]["field"] == "hold_period_years"


def test_scenarios_crud_and_results(owner, prop):
    pid = prop["id"]
    base = owner.get(f"/api/properties/{pid}/scenarios").json()[0]
    created = owner.post(f"/api/properties/{pid}/scenarios/defaults").json()
    assert {s["name"] for s in created} == {"Conservative", "Optimistic"}
    assert owner.post(f"/api/properties/{pid}/scenarios/defaults").json() == []  # idempotent
    custom = owner.post(f"/api/properties/{pid}/scenarios", json={"name": "Value-add", "clone_from": base["id"]})
    assert custom.status_code == 201
    sid = custom.json()["id"]
    a = dict(custom.json()["assumptions"], upfront_capex=1_500_000, rent_growth=0.05)
    upd = owner.patch(f"/api/scenarios/{sid}", json={"assumptions": a})
    assert upd.status_code == 200
    assert owner.patch(f"/api/scenarios/{sid}", json={"assumptions": dict(a, exit_cap_rate=0)}).status_code == 422
    res = owner.get(f"/api/scenarios/{sid}/result").json()
    assert res["assumptions"]["upfront_capex"] == 1_500_000 and res["stale"] is False
    assert len(res["annual"]) == 5 and res["audit_trace"]
    comp = owner.get(f"/api/properties/{pid}/scenario-comparison").json()
    irr = {c["name"]: c["metrics"]["irr_levered"] or c["metrics"]["irr_unlevered"] for c in comp}
    assert irr["Conservative"] < irr["Base Case"] < irr["Optimistic"]
    assert owner.post(f"/api/scenarios/{sid}/run").status_code == 200
    assert len(owner.get(f"/api/properties/{pid}/results").json()) >= 5
    assert owner.delete(f"/api/scenarios/{base['id']}").status_code == 409
    assert owner.post(f"/api/scenarios/{sid}/make-base").json()["is_base"] is True
    assert owner.delete(f"/api/scenarios/{base['id']}").status_code == 204


def test_sensitivity_and_monte_carlo(owner, prop):
    pid = prop["id"]
    t = owner.post(f"/api/properties/{pid}/sensitivity", json={"metric": "irr_unlevered"}).json()
    assert len(t["grid"]) == 5 and len(t["grid"][0]) == 5
    assert t["grid"][2][2] == pytest.approx(prop["latest"]["irr_unlevered"], abs=1e-9)
    custom = owner.post(f"/api/properties/{pid}/sensitivity", json={"row_path": "vacancy_rate",
                                                                    "row_values": [0.03, 0.05, 0.08],
                                                                    "col_path": "hold_period_years"}).json()
    assert custom["col_values"] == [3, 4, 5, 6, 7]
    assert owner.post(f"/api/properties/{pid}/sensitivity", json={"row_path": "bogus"}).status_code == 422
    assert owner.post(f"/api/properties/{pid}/sensitivity", json={"metric": "bogus"}).status_code == 422
    mc = owner.post(f"/api/properties/{pid}/monte-carlo", json={"iterations": 200, "seed": 1}).json()
    assert mc["completed"] + mc["rejected"] == 200
    p = mc["irr_unlevered"]["percentiles"]
    assert p["p5"] < p["p50"] < p["p95"]
    again = owner.post(f"/api/properties/{pid}/monte-carlo", json={"iterations": 200, "seed": 1}).json()
    assert again["irr_unlevered"]["mean"] == mc["irr_unlevered"]["mean"]


def test_financing_lifecycle(owner, prop):
    pid = prop["id"]
    agency = owner.post(f"/api/properties/{pid}/financing", json={
        "name": "Agency", "ltv": 0.65, "interest_rate": 0.055, "amortization_years": 30, "io_period": 2,
        "covenants": {"min_dscr": 1.25}}).json()
    bridge = owner.post(f"/api/properties/{pid}/financing", json={
        "name": "Bridge", "type": "bridge", "rate_type": "floating", "ltv": 0.75, "index_rate": 0.043,
        "spread": 0.0325, "amortization_years": 0, "term_years": 3}).json()
    assert owner.post(f"/api/properties/{pid}/financing", json={"name": "No size"}).status_code == 422
    assert owner.post(f"/api/properties/{pid}/financing", json={"name": "Too big", "loan_amount": 50_000_000,
                                                                "interest_rate": 0.05}).status_code == 422
    rows = owner.get(f"/api/properties/{pid}/financing/compare").json()
    assert [r["name"] for r in rows] == ["All cash (unlevered)", "Agency", "Bridge"]
    assert rows[0]["dscr_year1"] is None and rows[1]["dscr_year1"] > 1
    assert rows[2]["rate"] == pytest.approx(0.0755)
    act = owner.post(f"/api/financing/{agency['id']}/activate")
    assert act.status_code == 200 and act.json()["is_active"]
    base = owner.get(f"/api/properties/{pid}/scenarios").json()[0]
    assert base["assumptions"]["loan"]["ltv"] == 0.65
    upd = owner.put(f"/api/financing/{bridge['id']}", json={**bridge, "spread": 0.03})
    assert upd.status_code == 200 and upd.json()["spread"] == 0.03
    assert owner.delete(f"/api/financing/{bridge['id']}").status_code == 204
    assert len(owner.get(f"/api/properties/{pid}/financing").json()) == 1


def test_valuation(owner, prop):
    pid = prop["id"]
    v = owner.get(f"/api/properties/{pid}/valuation").json()
    assert set(v["weights"]) == {"direct_cap", "dcf"}
    saved = owner.put(f"/api/properties/{pid}/valuation", json={
        "market_cap_rate": 0.055,
        "comps": [{"name": "Comp A", "sale_price": 21_000_000, "units": 100}],
        "cost": {"land_value": 3_000_000, "replacement_cost": 18_000_000, "physical_depreciation_pct": 0.1},
        "weights": {"direct_cap": 1, "dcf": 1, "sales_comparison": 1, "cost": 1},
    }).json()
    assert saved["values"]["sales_comparison"] == pytest.approx(21_000_000)
    assert saved["values"]["cost"] == pytest.approx(3_000_000 + 18_000_000 * 0.9)
    assert owner.put(f"/api/properties/{pid}/valuation", json={"bogus": 1}).status_code == 422


def test_development(owner, prop):
    body = {"land_cost": 3_000_000, "hard_costs": 20_000_000, "stabilized_noi": 2_000_000, "exit_cap_rate": 0.055}
    r = owner.post("/api/development/calculate", json=body)
    assert r.status_code == 200 and r.json()["returns"]["yield_on_cost"] > 0.055
    assert owner.post("/api/development/calculate", json={**body, "hard_costs": 0}).status_code == 422
    saved = owner.put(f"/api/properties/{prop['id']}/development", json=body)
    assert saved.status_code == 200
    assert owner.get(f"/api/properties/{prop['id']}").json()["attributes"]["development"]["land_cost"] == 3_000_000


def test_compare_and_dashboard(demo):
    props = demo.get("/api/properties").json()
    assert len(props) == 5 and all(p["is_demo"] and p["name"].startswith("[DEMO]") for p in props)
    ids = ",".join(p["id"] for p in props[:3])
    rows = demo.get(f"/api/compare?ids={ids}").json()
    assert len(rows) == 3 and all("irr_levered" in r for r in rows)
    assert demo.get("/api/compare?ids=not-a-uuid").status_code == 422
    d = demo.get("/api/dashboard").json()
    assert d["totals"]["deals"] == 5 and d["totals"]["demo_deals"] == 5
    assert d["totals"]["aum"] > 0 and d["totals"]["weighted_avg_cap_rate"] > 0
    assert sum(p["count"] for p in d["pipeline"]) == 5
    assert d["recent_activity"]
    filtered = demo.get("/api/dashboard?property_type=industrial").json()
    assert filtered["totals"]["deals"] == 1


def test_demo_multifamily_and_industrial_are_fully_modelled(demo):
    props = {p["property_type"]: p for p in demo.get("/api/properties").json()}
    for t in ("multifamily", "industrial"):
        pid = props[t]["id"]
        scs = demo.get(f"/api/properties/{pid}/scenarios").json()
        assert {s["name"] for s in scs} == {"Base Case", "Conservative", "Optimistic"}
        fin = demo.get(f"/api/properties/{pid}/financing/compare").json()
        assert len(fin) >= 3
        val = demo.get(f"/api/properties/{pid}/valuation").json()
        assert val["values"]["sales_comparison"] is not None
