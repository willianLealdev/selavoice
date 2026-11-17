"""Fixtures de teste. Usa SQLite temporário e modo `test` (sem chaves externas)."""
import os
import pathlib
import uuid

# DEVE vir antes de importar o app.
_db = pathlib.Path(__file__).parent / "_test.db"
for suffix in ("", "-wal", "-shm"):
    p = pathlib.Path(str(_db) + suffix)
    if p.exists():
        p.unlink()
os.environ.update({"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{_db}", "STRIPE_MODE": "fake",
                   "AUTH_RATE_LIMIT_PER_MINUTE": "1000", "RATE_LIMIT_PER_MINUTE": "100000"})

import pytest
from fastapi.testclient import TestClient

from app.core.ratelimit import limiter
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Plan, PlanVersion, BillingType, User
from app.security import hash_password
from app.seed import run as seed_run

PW = "Senha-Forte-123"


@pytest.fixture(scope="session", autouse=True)
def _db_setup():
    Base.metadata.create_all(engine)
    os.environ["SUPER_ADMIN_PASSWORD"] = PW
    yield


@pytest.fixture()
def client():
    limiter.reset()
    with TestClient(app) as c:
        yield c


def register(client, name="Igreja X", email=None):
    email = email or f"{uuid.uuid4().hex[:8]}@t.com"
    r = client.post("/auth/register", json={"email": email, "password": PW, "name": "Admin", "org_name": name})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def make_event(client, h, title="Culto", **kw):
    body = {"title": title, "starts_at": "2030-01-01T18:00:00Z", **kw}
    r = client.post("/events", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def tenant_a(client):
    h, email = register(client, "Org A")
    return h


@pytest.fixture()
def tenant_b(client):
    h, email = register(client, "Org B")
    return h


def _super_headers(client):
    """Cria super admin com MFA e devolve cabeçalhos com sessão MFA verificada."""
    import pyotp
    from app.security import decrypt_secret
    email = f"su{uuid.uuid4().hex[:6]}@t.com"
    with SessionLocal() as db:
        db.add(User(email=email, name="SU", is_super_admin=True, password_hash=hash_password(PW)))
        db.commit()
    r = client.post("/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200 and r.json()["mfa_required_setup"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    s = client.post("/auth/mfa/setup", headers=h).json()["secret"]
    r = client.post("/auth/mfa/verify", json={"code": pyotp.TOTP(s).now()}, headers=h)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def superadmin(client):
    return _super_headers(client)


@pytest.fixture()
def paid_plan():
    """Plano avulso publicado com 1 evento; retorna plan_version_id."""
    with SessionLocal() as db:
        p = Plan(public_name="Avulso T", slug=f"av-{uuid.uuid4().hex[:6]}", status="published")
        db.add(p)
        db.flush()
        v = PlanVersion(plan_id=p.id, version=1, billing_type=BillingType.ONE_OFF, amount_cents=1000,
                        entitlements={"included_events": 1, "included_language_minutes": 100,
                                      "max_concurrent_events": 1})
        db.add(v)
        db.commit()
        return str(v.id)
