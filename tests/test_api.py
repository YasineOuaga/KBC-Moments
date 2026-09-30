"""Security- en logica-tests. Draaien: pytest -q (vanuit de root van de repo)."""
import os
import sys
from pathlib import Path

os.environ["JWT_SECRET"] = "t" * 40
os.environ["DEMO_PASSWORD"] = "test-wachtwoord"
os.environ["GEMINI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import engine  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)
PW = os.environ["DEMO_PASSWORD"]


@pytest.fixture(autouse=True)
def clean_state():
    main._attempts.clear()
    main.REVOKED.clear()
    for cid in main.CUSTOMERS:
        main.CONSENT[cid] = set(engine.SIGNALS)
        main.SUPPRESSED[cid].clear()


def login(user, pw=PW):
    return client.post("/api/login", json={"username": user, "password": pw})


def auth(user):
    return {"Authorization": "Bearer " + login(user).json()["token"]}


# ---------------------------------------------------------------- authenticatie
def test_zonder_token_geen_toegang():
    assert client.get("/api/me").status_code == 401


def test_vervalste_token_geweigerd():
    fake = jwt.encode({"sub": "adviseur", "role": "advisor", "exp": 9999999999},
                      "verkeerd-geheim" * 3, algorithm="HS256")
    r = client.get("/api/advisor/clients", headers={"Authorization": "Bearer " + fake})
    assert r.status_code == 401


def test_token_met_alg_none_geweigerd():
    fake = jwt.encode({"sub": "adviseur", "role": "advisor", "exp": 9999999999}, None, algorithm="none")
    r = client.get("/api/advisor/clients", headers={"Authorization": "Bearer " + fake})
    assert r.status_code == 401


def test_uitloggen_trekt_token_in():
    h = auth("lotte")
    assert client.get("/api/me", headers=h).status_code == 200
    assert client.post("/api/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401


def test_aanvaller_kan_klant_niet_buitensluiten():
    # aanvaller probeerde 6x een fout wachtwoord vanaf een ander IP (TestClient heeft 1 vast IP)
    for _ in range(6):
        main._hit("fail:karim:6.6.6.6")
    assert login("karim").status_code == 200  # echte Karim kan nog steeds binnen


def test_brute_force_wordt_afgeremd():
    codes = [login("karim", "fout").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_geslaagde_logins_tellen_niet_mee():
    for _ in range(8):
        assert login("lotte").status_code == 200


# ---------------------------------------------------------------- autorisatie / IDOR
def test_adviseur_kan_klant_endpoint_niet_gebruiken():
    assert client.get("/api/me", headers=auth("adviseur")).status_code == 403


def test_klant_kan_adviseur_endpoint_niet_gebruiken():
    assert client.get("/api/advisor/clients", headers=auth("lotte")).status_code == 403


def test_adviseur_ziet_enkel_toegewezen_klanten():
    names = {c["customer"]["name"] for c in client.get("/api/advisor/clients", headers=auth("adviseur")).json()}
    assert names == {"Lotte", "Karim"}  # Jan is niet toegewezen


def test_klant_id_uit_body_wordt_genegeerd():
    r = client.put("/api/me/consent", headers=auth("lotte"),
                   json={"signal": "income", "enabled": False, "customer_id": "c-jan"})
    assert r.status_code == 200 and r.json()["customer"]["name"] == "Lotte"
    assert "income" in main.CONSENT["c-jan"]


def test_adviseur_ziet_geen_signalen_zonder_toestemming():
    client.put("/api/me/consent", headers=auth("lotte"), json={"signal": "income", "enabled": False})
    lotte = next(c for c in client.get("/api/advisor/clients", headers=auth("adviseur")).json()
                 if c["customer"]["name"] == "Lotte")
    assert all("loon" not in w["evidence"] for w in lotte["why"])


# ---------------------------------------------------------------- business logic
def test_feedback_enkel_op_getoond_moment():
    r = client.post("/api/me/feedback", headers=auth("jan"), json={"moment": "home"})
    assert r.status_code == 409
    assert not main.SUPPRESSED["c-jan"]


def test_feedback_op_getoond_moment_werkt():
    r = client.post("/api/me/feedback", headers=auth("jan"), json={"moment": "ret"})
    assert r.status_code == 200 and r.json()["active"] is False


def test_onbekend_signaal_geweigerd():
    r = client.put("/api/me/consent", headers=auth("lotte"), json={"signal": "salaris_admin", "enabled": False})
    assert r.status_code == 422


# ---------------------------------------------------------------- het juiste moment
def test_lotte_krijgt_bericht_op_loondag_weekend_naar_vrijdag():
    t = client.get("/api/me", headers=auth("lotte")).json()["timing"]
    assert t["date"] == "2026-10-23" and t["hour"] == 8  # 25/10 is een zondag
    assert t["held"] is None


def test_contactbeleid_stelt_karim_uit():
    t = client.get("/api/me", headers=auth("karim")).json()["timing"]
    assert t["date"] == "2026-10-15" and t["held"]


def test_security_headers():
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self';" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "Strict-Transport-Security" in r.headers
