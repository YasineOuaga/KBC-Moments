"""Tests voor momentlogica en timing (engine.py)."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import engine  # noqa: E402

ALL = set(engine.SIGNALS)


def cust(salary_days=(), last_contact=None, **kw):
    c = engine.Customer("x", "X", 30, "", 1000, last_contact=last_contact)
    c.tx = [(d, 2000, "Werkgever", "salary") for d in salary_days]
    return c


# ---------------------------------------------------------------- ankersignalen
def test_eerste_job_vereist_loon():
    best = engine.pick_moment({"rent": "", "search": "", "lowbal": ""}, ALL)
    assert best["active"] is False


def test_verankerd_moment_wint_van_hogere_score_zonder_anker():
    # zonder anker zou "first" (huur+zoeken+saldo = 0.65) winnen en alles verbergen
    best = engine.pick_moment({"mortgage": "", "rent": "", "search": "", "lowbal": ""}, ALL)
    assert best["key"] == "home" and best["active"]


def test_zonder_enig_anker_niet_actief_maar_score_zichtbaar():
    best = engine.pick_moment({"rent": "", "search": "", "lowbal": ""}, ALL)
    assert best["active"] is False and best["score"] == 0.65


def test_anker_zonder_toestemming_telt_niet():
    sigs = {"income": "", "rent": "", "search": "", "lowbal": ""}
    assert engine.pick_moment(sigs, ALL - {"income"})["active"] is False


def test_lotte_blijft_actief():
    c = engine.demo_customers()["c-lotte"]
    assert engine.pick_moment(engine.detect_signals(c), ALL)["key"] == "first"


# ---------------------------------------------------------------- timing
def test_loondag_30_wordt_niet_naar_28_geklemd():
    c = cust([date(2026, 7, 30), date(2026, 8, 30), date(2026, 9, 30)])
    t = engine.plan_contact(c, "first", ALL)
    assert t["date"] == "2026-10-30"  # vrijdag 30/10


def test_loondag_31_in_korte_maand():
    c = cust([date(2026, 8, 31)])
    # TODAY 30/09: volgende loondag is 30/09? nee, dat is vandaag -> 31/10 is zaterdag -> vr 30/10
    assert engine.plan_contact(c, "first", ALL)["date"] == "2026-10-30"


def test_meest_voorkomende_loondag_wint():
    # 25/07 en 25/08 normaal, 23/09 verschoven wegens weekend-verwerking
    c = cust([date(2026, 7, 25), date(2026, 8, 25), date(2026, 9, 23)])
    assert engine.plan_contact(c, "first", ALL)["date"] == "2026-10-23"  # 25/10 = zondag -> vr 23/10


def test_jaarwissel():
    old = engine.TODAY
    try:
        engine.TODAY = date(2026, 12, 28)
        c = cust([date(2026, 12, 25)])
        assert engine.plan_contact(c, "first", ALL)["date"] == "2027-01-25"
    finally:
        engine.TODAY = old


def test_zonder_loontoestemming_volgende_werkdag():
    c = cust([date(2026, 9, 25)])
    t = engine.plan_contact(c, "first", ALL - {"income"})
    assert t["date"] == "2026-10-01" and "loon" not in t["why"].lower()


def test_uitgestelde_loondag_boodschap_valt_op_een_loondag():
    c = cust([date(2026, 8, 25), date(2026, 9, 25)], last_contact=date(2026, 9, 28))
    t = engine.plan_contact(c, "first", ALL)
    # vroegst 28/10 volgens beleid -> eerstvolgende loondag is 25/11 (woensdag)
    assert t["date"] == "2026-11-25" and t["held"]


def test_oude_notarisbetaling_telt_niet():
    c = cust()
    c.tx = [(engine.TODAY - timedelta(days=400), -9000, "Notaris", "notary")]
    assert "notary" not in engine.detect_signals(c)


def test_gelijkspel_loondag_kiest_de_niet_verschoven_dag():
    # loondag 30: 30/08/2026 is een zondag, dus betaald op vr 28/08. 30/09 normaal.
    # Bij gelijkspel wint de latere dag (een weekendverschuiving is altijd vroeger).
    for days in ([date(2026, 8, 28), date(2026, 9, 30)], [date(2026, 9, 30), date(2026, 8, 28)]):
        assert engine.plan_contact(cust(days), "first", ALL)["date"] == "2026-10-30"
