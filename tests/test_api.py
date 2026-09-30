"""Security- en logica-tests. Draaien: pytest -q (vanuit de root van de repo)."""
import os
import sys
import time
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


FULL_CLAIMS = {"sub": "adviseur", "role": "advisor", "exp": 9999999999,
               "iss": "kbc-moments", "aud": "kbc-moments", "jti": "x"}


def test_niet_bearer_schema_geweigerd():
    assert client.get("/api/me", headers={"Authorization": "Basic bG90dGU6eA=="}).status_code == 401


def test_vervalste_token_geweigerd():
    # alle claims aanwezig: enkel de handtekening is fout
    fake = jwt.encode(FULL_CLAIMS, "verkeerd-geheim" * 3, algorithm="HS256")
    r = client.get("/api/advisor/clients", headers={"Authorization": "Bearer " + fake})
    assert r.status_code == 401


def test_token_met_alg_none_geweigerd():
    fake = jwt.encode(FULL_CLAIMS, None, algorithm="none")
    r = client.get("/api/advisor/clients", headers={"Authorization": "Bearer " + fake})
    assert r.status_code == 401


def test_uitloggen_trekt_token_in():
    h = auth("lotte")
    assert client.get("/api/me", headers=h).status_code == 200
    assert client.post("/api/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401


def test_aanvaller_kan_klant_niet_buitensluiten():
    # aanvaller probeerde 6x een fout wachtwoord vanaf een ander IP (TestClient heeft 1 vast IP)
    with main._attempts_lock:
        main._attempts[("fail", "karim", "6.6.6.6")].extend([time.monotonic()] * 6)
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


# ---------------------------------------------------------------- review-fixes: login
def test_parallelle_brute_force_wordt_afgeremd():
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(lambda _: login("jan", "fout").status_code, range(20)))
    assert codes.count(401) <= 5 and codes.count(429) >= 15


def test_gebruikersnaam_met_scheidingsteken_geweigerd():
    assert login("karim:1.2.3.4", "fout").status_code == 422


def test_x_forwarded_for_wordt_niet_blind_vertrouwd():
    # zonder TRUST_PROXY telt het echte verbindings-IP, niet de header
    for i in range(5):
        client.post("/api/login", json={"username": "jan", "password": "fout"},
                    headers={"X-Forwarded-For": f"10.0.0.{i}"})
    r = client.post("/api/login", json={"username": "jan", "password": "fout"},
                    headers={"X-Forwarded-For": "10.0.0.99"})
    assert r.status_code == 429


def test_client_ip_achter_proxy_neemt_meest_rechtse_hop(monkeypatch):
    monkeypatch.setattr(main, "TRUST_PROXY", True)

    class Req:
        headers = {"x-forwarded-for": "6.6.6.6, 81.82.83.84"}
        client = type("C", (), {"host": "169.254.1.1"})()
    assert main.client_ip(Req()) == "81.82.83.84"


# ---------------------------------------------------------------- review-fixes: toestemming
def test_zonder_loontoestemming_geen_moment_en_geen_timing():
    # het loon is het anker van "Eerste vaste job": zonder toestemming geen moment,
    # en dus ook geen tijdstip dat uit het loon is afgeleid (zie ook test_engine)
    h = auth("lotte")
    client.put("/api/me/consent", headers=h, json={"signal": "income", "enabled": False})
    v = client.get("/api/me", headers=h).json()
    assert v["active"] is False and "timing" not in v


def test_adviseur_krijgt_nooit_signalenlijst_of_boodschap():
    for c in client.get("/api/advisor/clients", headers=auth("adviseur")).json():
        assert "signals" not in c and "message" not in c


def test_reset_herstelt_geen_ingetrokken_toestemming():
    h = auth("lotte")
    client.put("/api/me/consent", headers=h, json={"signal": "search", "enabled": False})
    client.post("/api/me/reset", headers=h)
    assert "search" not in main.CONSENT["c-lotte"]


def test_stats_werkt():
    s = client.get("/api/stats", headers=auth("lotte")).json()
    assert s["customers"] == 10_000 and 0 < s["trigger_rate"] < 20


# ---------------------------------------------------------------- review-fixes: taalmodel
def test_geslaagde_login_telt_niet_als_mislukte_poging():
    for _ in range(4):
        login("karim", "fout")
    assert login("karim").status_code == 200
    assert login("karim", "fout").status_code == 401   # 5e mislukte poging: nog toegestaan
    assert login("karim", "fout").status_code == 429


FIRST, HOME, RET = (engine.MOMENTS[k]["action"] for k in ("first", "home", "ret"))


def test_taalmodel_uitvoer_met_krediet_of_verzonnen_bedrag_geweigerd():
    assert main._safe_llm_text("Neem nu een lening van €5000!", FIRST) is None
    assert main._safe_llm_text("Denk aan een krediet voor je auto.", FIRST) is None
    assert main._safe_llm_text("Leen nu €2000 extra.", HOME) is None
    assert main._safe_llm_text("Spaar €200 per maand.", FIRST) is None  # bedrag niet uit de actie


def test_taalmodel_realistische_uitvoer_per_moment_toegelaten():
    ok = [
        ("Hoi Lotte! Zin in een spaarpotje van €50 per maand? Jij beslist.", FIRST),
        ("Hoi Lotte, start je een spaarpotje van 50 euro per maand? Jij kiest.", FIRST),
        ("Dag Karim, benieuwd wat je maandlast wordt met je woonlening? Jij beslist.", HOME),
        ("Dag Jan, zin in een rustig gesprek over je pensioen? Jij beslist.", RET),
    ]
    for text, action in ok:
        assert main._safe_llm_text(text, action) == text
