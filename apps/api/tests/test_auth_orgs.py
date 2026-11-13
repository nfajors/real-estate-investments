import uuid

from conftest import MF_PROPERTY, PASSWORD, Session, register


def test_register_login_me(client):
    s = register(client)
    me = s.get("/api/auth/me").json()
    assert me["memberships"][0]["role"] == "owner"
    r = client.post("/api/auth/login", json={"email": s.email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"
    assert "axiom_refresh" in r.cookies or "axiom_refresh" in client.cookies


def test_bad_credentials_and_weak_password(client):
    s = register(client)
    assert client.post("/api/auth/login", json={"email": s.email, "password": "wrong-password1"}).status_code == 401
    r = client.post("/api/auth/register", json={"email": "weak@example.com", "password": "aaaaaaaaaaaa",
                                                "name": "x", "organization_name": "Weak Co"})
    assert r.status_code == 422
    dup = client.post("/api/auth/register", json={"email": s.email, "password": PASSWORD, "name": "x",
                                                  "organization_name": "Dup Co"})
    assert dup.status_code == 409


def test_unauthenticated_and_invalid_token(client):
    assert client.get("/api/properties").status_code == 401
    assert client.get("/api/properties", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client):
    s = register(client)
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"email": s.email, "password": PASSWORD})
    old = r.cookies.get("axiom_refresh")
    r2 = client.post("/api/auth/refresh", cookies={"axiom_refresh": old})
    assert r2.status_code == 200
    new = r2.cookies.get("axiom_refresh")
    assert new and new != old
    # Reusing the rotated token revokes the family – including the new token.
    assert client.post("/api/auth/refresh", cookies={"axiom_refresh": old}).status_code == 401
    assert client.post("/api/auth/refresh", cookies={"axiom_refresh": new}).status_code == 401
    client.cookies.clear()


def test_logout_revokes_refresh(client):
    s = register(client)
    client.cookies.clear()
    tok = client.post("/api/auth/login", json={"email": s.email, "password": PASSWORD}).cookies.get("axiom_refresh")
    assert client.post("/api/auth/logout", cookies={"axiom_refresh": tok}).status_code == 204
    assert client.post("/api/auth/refresh", cookies={"axiom_refresh": tok}).status_code == 401
    client.cookies.clear()


def test_invitation_flow_new_user_and_roles(client, owner):
    r = owner.post("/api/org/invitations", json={"email": f"new.analyst-{uuid.uuid4().hex[:8]}@example.com", "role": "analyst"})
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    preview = client.get(f"/api/invitations/{token}").json()
    assert preview["role"] == "analyst" and preview["has_account"] is False
    assert client.post("/api/invitations/accept", json={"token": token}).status_code == 422
    acc = client.post("/api/invitations/accept", json={"token": token, "name": "New Analyst", "password": PASSWORD})
    assert acc.status_code == 200
    analyst = Session(client, acc.json()["access_token"], owner.org_id)
    assert client.post("/api/invitations/accept", json={"token": token, "password": PASSWORD}).status_code == 404

    members = owner.get("/api/org/members").json()
    assert {m["role"] for m in members} == {"owner", "analyst"}
    analyst_id = next(m["user_id"] for m in members if m["role"] == "analyst")
    # Analyst can create deals but not manage members
    assert analyst.post("/api/properties", json=MF_PROPERTY).status_code == 201
    assert analyst.post("/api/org/invitations", json={"email": f"x-{uuid.uuid4().hex[:8]}@example.com"}).status_code == 403
    # Downgrade to viewer → read only
    assert owner.patch(f"/api/org/members/{analyst_id}", json={"role": "viewer"}).status_code == 200
    assert analyst.post("/api/properties", json=MF_PROPERTY).status_code == 403
    assert analyst.get("/api/properties").status_code == 200
    # Remove member
    assert owner.delete(f"/api/org/members/{analyst_id}").status_code == 204
    assert analyst.get("/api/properties").status_code == 403


def test_existing_user_invitation_requires_password(client, owner):
    other = register(client, org="Other Co")
    token = owner.post("/api/org/invitations", json={"email": other.email, "role": "viewer"}).json()["token"]
    assert client.get(f"/api/invitations/{token}").json()["has_account"] is True
    assert client.post("/api/invitations/accept", json={"token": token, "password": "wrong-pass-123"}).status_code == 401
    assert client.post("/api/invitations/accept", json={"token": token, "password": PASSWORD}).status_code == 200
    me = other.get("/api/auth/me").json()
    assert len(me["memberships"]) == 2
    # Duplicate invite for an existing member is rejected
    assert owner.post("/api/org/invitations", json={"email": other.email}).status_code == 409


def test_owner_protections(client, owner):
    assert owner.patch(f"/api/org/members/{owner.user_id}", json={"role": "admin"}).status_code == 409
    assert owner.delete(f"/api/org/members/{owner.user_id}").status_code == 409
    assert owner.post("/api/org/invitations", json={"email": f"o-{uuid.uuid4().hex[:8]}@example.com", "role": "owner"}).status_code == 422


def test_revoke_invitation(client, owner):
    inv = owner.post("/api/org/invitations", json={"email": f"revoke-{uuid.uuid4().hex[:8]}@example.com"}).json()
    assert owner.delete(f"/api/org/invitations/{inv['id']}").status_code == 204
    assert client.get(f"/api/invitations/{inv['token']}").status_code == 404


def test_tenant_isolation(client, owner, prop):
    intruder = register(client, org="Intruder LLC")
    assert intruder.get(f"/api/properties/{prop['id']}").status_code == 404
    assert intruder.get("/api/properties").json() == []
    # Spoofing the org header for an org you don't belong to is rejected
    intruder.org_id = owner.org_id
    assert intruder.get("/api/properties").status_code == 403


def test_features_billing_and_audit(owner):
    feats = owner.get("/api/features").json()
    assert feats["monte_carlo"]["enabled"] is True
    assert feats["portfolio_analytics"]["enabled"] is False
    assert owner.patch("/api/org", json={"feature_overrides": {"monte_carlo": False}}).status_code == 200
    assert owner.get("/api/features").json()["monte_carlo"]["enabled"] is False
    b = owner.get("/api/billing").json()
    assert b["plan"] == "professional" and b["billing_mode"] == "manual"
    assert owner.post("/api/billing/plan", json={"plan": "starter"}).json()["plan"] == "starter"
    assert owner.get("/api/features").json()["ai_analyst"]["enabled"] is False
    assert owner.post("/api/billing/plan", json={"plan": "bogus"}).status_code == 422
    audit = owner.get("/api/org/audit").json()
    assert any(a["action"] == "billing.plan_change" for a in audit)


def test_plan_deal_limit(owner):
    owner.post("/api/billing/plan", json={"plan": "starter"})
    for _ in range(5):
        assert owner.post("/api/properties", json=MF_PROPERTY).status_code == 201
    assert owner.post("/api/properties", json=MF_PROPERTY).status_code == 402


def test_create_second_org(client, owner):
    r = owner.post("/api/orgs", json={"name": "Second Fund"})
    assert r.status_code == 201
    me = owner.get("/api/auth/me").json()
    assert len(me["memberships"]) == 2
