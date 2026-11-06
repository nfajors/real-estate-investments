"""API test fixtures.

Runs against SQLite by default. Set AXIOM_TEST_DATABASE_URL to a migrated
Postgres database (connected as the non-superuser app role) to exercise RLS.
"""

import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp(prefix="axiom-test-")
os.environ["AXIOM_DATABASE_URL"] = os.environ.get("AXIOM_TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["AXIOM_STORAGE_PATH"] = f"{_tmp}/storage"
os.environ["AXIOM_LOG_LEVEL"] = "WARNING"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PASSWORD = "Sup3r-secret-pass"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class Session:
    def __init__(self, client: TestClient, token: str, org_id: str | None = None):
        self.c = client
        self.token = token
        self.org_id = org_id

    @property
    def headers(self):
        h = {"Authorization": f"Bearer {self.token}"}
        if self.org_id:
            h["X-Org-Id"] = self.org_id
        return h

    def get(self, url, **kw):
        return self.c.get(url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self.headers, **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self.headers, **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self.headers, **kw)


def register(client, seed=False, org="Test Capital") -> Session:
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "name": "Test User",
                                                "organization_name": org, "seed_demo_data": seed})
    assert r.status_code == 201, r.text
    s = Session(client, r.json()["access_token"])
    s.email = email
    me = s.get("/api/auth/me").json()
    s.org_id = me["memberships"][0]["org_id"]
    s.user_id = me["user"]["id"]
    return s


@pytest.fixture
def owner(client) -> Session:
    return register(client)


@pytest.fixture(scope="session")
def demo(client) -> Session:
    """One seeded demo workspace shared by read-mostly tests."""
    return register(client, seed=True, org="Demo Capital")


MF_PROPERTY = {"name": "Test Apartments", "property_type": "multifamily", "city": "Austin", "state": "TX",
               "purchase_price": 20_000_000, "hold_period_years": 5, "units": 100}


@pytest.fixture
def prop(owner):
    r = owner.post("/api/properties", json=MF_PROPERTY)
    assert r.status_code == 201, r.text
    return r.json()
