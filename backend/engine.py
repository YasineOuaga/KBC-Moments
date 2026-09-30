"""KBC Moments engine: transacties -> signalen -> moment -> actie.

Alles is deterministisch en goedkoop (geen taalmodel). Het taalmodel wordt
alleen aangeroepen in main.py wanneer er een moment gedetecteerd wordt.
"""
from __future__ import annotations

import calendar
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

TODAY = date(2026, 9, 30)
BUFFER_EUR = 300  # persoonlijke buffer: saldo eronder = signaal
CONTACT_GAP_DAYS = 30  # contactbeleid: max 1 proactief bericht per 30 dagen
DAYS_NL = ["ma", "di", "wo", "do", "vr", "za", "zo"]

# ---------------------------------------------------------------- signalen
SIGNALS = {
    "income": "Eerste salaris ontvangen",
    "rent": "Nieuwe huur als vaste kost",
    "search": "Zocht naar sparen in de app",
    "lowbal": "Saldo onder persoonlijke buffer",
    "mortgage": "Woonlening-simulatie bekeken",
    "notary": "Notariskosten betaald",
    "pension": "Pensioensimulatie bekeken",
}

# ---------------------------------------------------------------- momenten
MOMENTS = {
    "first": {
        "title": "Eerste vaste job",
        "weights": {"income": .35, "rent": .25, "search": .2, "lowbal": .2},
        "anchor": {"income"},  # zonder eerste loon geen "eerste job"
        "action": "Start een spaarpotje van €50 per maand",
        "goal": "helpen een buffer op te bouwen zodat huur en vaste kosten altijd gedekt zijn",
        "channel": "App-melding",
        "tone": "Informeel, korte zinnen",
        "timing": "payday",
    },
    "home": {
        "title": "Eerste woning",
        "weights": {"mortgage": .4, "notary": .35, "rent": .25},
        "anchor": {"mortgage", "notary"},
        "action": "Bekijk je maandlast en regel je brandverzekering",
        "goal": "tonen wat de maandlast wordt en welke verzekering nu al nodig is",
        "channel": "Afspraak op kantoor voorgesteld, plus app",
        "tone": "Geruststellend, met cijfers",
        "timing": "workday",
    },
    "ret": {
        "title": "Op weg naar pensioen",
        "weights": {"pension": .55, "search": .25, "lowbal": .2},
        "anchor": {"pension"},
        "action": "Plan een gesprek over je pensioen",
        "goal": "samen het pensioenplan doorlopen en aanvullende opties tonen, zonder druk",
        "channel": "Persoonlijk gesprek, geen app-melding",
        "tone": "Rustig en uitgebreid",
        "timing": "workday",
    },
}
THRESHOLD = 0.5


@dataclass
class Customer:
    id: str
    name: str
    age: int
    desc: str
    start_balance: float
    tx: list = field(default_factory=list)       # (date, amount, counterparty, category)
    events: list = field(default_factory=list)   # (date, type)
    last_contact: date | None = None             # laatste proactieve boodschap van KBC


# ---------------------------------------------------------------- detectie
def eur(v: float) -> str:
    return ("-" if v < 0 else "") + f"€{abs(v):,.0f}".replace(",", ".")


def detect_signals(c: Customer) -> dict[str, str]:
    """Geeft {signaal: bewijs} terug. Bewijs is wat de klant te zien krijgt."""
    out: dict[str, str] = {}
    tx = sorted(c.tx, key=lambda t: t[0])
    recent = TODAY - timedelta(days=90)

    salaries = [t for t in tx if t[3] == "salary"]
    if salaries and salaries[0][0] >= recent:
        s = salaries[0]
        out["income"] = f"Eerste loon van {s[2]} ({eur(s[1])}) op {s[0]:%d/%m}"

    rents = [t for t in tx if t[3] == "rent"]
    if rents and rents[0][0] >= TODAY - timedelta(days=120):
        r = rents[0]
        out["rent"] = f"Nieuwe maandelijkse betaling aan {r[2]} ({eur(-r[1])}) sinds {r[0]:%d/%m}"

    notary = [t for t in tx if t[3] == "notary" and t[0] >= TODAY - timedelta(days=180)]
    if notary:
        n = notary[-1]
        out["notary"] = f"Betaling aan {n[2]} ({eur(-n[1])}) op {n[0]:%d/%m}"

    bal, low_day = c.start_balance, None
    for t in tx:
        bal += t[1]
        if t[0] >= TODAY - timedelta(days=30) and bal < BUFFER_EUR:
            low_day = (t[0], bal)
    if low_day:
        out["lowbal"] = f"Saldo zakte tot {eur(low_day[1])} op {low_day[0]:%d/%m} (buffer €{BUFFER_EUR})"

    ev_map = {"search_savings": "search", "sim_mortgage": "mortgage", "sim_pension": "pension"}
    for d, typ in c.events:
        if typ in ev_map and d >= recent:
            out[ev_map[typ]] = f"{SIGNALS[ev_map[typ]]} op {d:%d/%m}"
    return out


def pick_moment(signals: dict[str, str], consent: set[str], suppressed: set[str] | None = None) -> dict:
    """Kiest het moment met de hoogste score, enkel met signalen waarvoor toestemming is.

    Een moment is pas actief als ook een ankersignaal meetelt: bijkomende signalen
    alleen (huur, zoeken, laag saldo) bewijzen nog geen levensmoment.
    """
    suppressed = suppressed or set()
    best = None
    for key, m in MOMENTS.items():
        if key in suppressed:
            continue
        used = [s for s in m["weights"] if s in signals and s in consent]
        score = round(sum(m["weights"][s] for s in used), 2)
        anchored = bool(m["anchor"] & set(used))
        if best is None or score > best["score"]:
            best = {"key": key, "score": score, "used": used, "anchored": anchored}
    if best is None:
        return {"key": None, "score": 0, "used": [], "active": False}
    best["active"] = best.pop("anchored") and best["score"] >= THRESHOLD
    return best


# ---------------------------------------------------------------- timing
def _next_workday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _payday(y: int, m: int, day: int) -> date:
    """Loondag in maand y/m: geklemd op de maandlengte, weekend -> vrijdag ervoor."""
    d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _next_payday(day: int, after: date) -> date:
    """Eerste loondag strikt na `after`."""
    y, m = after.year, after.month
    while (d := _payday(y, m, day)) <= after:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return d


def plan_contact(c: Customer, key: str, consent: set[str]) -> dict:
    """Bepaalt WANNEER de boodschap vertrekt: het juiste moment, binnen het contactbeleid.

    Loondata wordt enkel gebruikt met toestemming voor het signaal 'income'.
    """
    salaries = [t[0] for t in c.tx if t[3] == "salary"]
    payday = (MOMENTS[key]["timing"] == "payday" and salaries and "income" in consent)
    if payday:
        # meest voorkomende dag: een verschoven betaling (weekend) verandert de loondag niet
        day = Counter(d.day for d in salaries).most_common(1)[0][0]
        when = _next_payday(day, TODAY)
        hour, why = 8, "De ochtend dat het loon binnenkomt: dan is er ruimte om te sparen."
    else:
        when = _next_workday(TODAY + timedelta(days=1))
        hour, why = 10, "De eerstvolgende werkdag, tijdens de kantooruren."

    held = None
    if c.last_contact:
        earliest = _next_workday(c.last_contact + timedelta(days=CONTACT_GAP_DAYS))
        if earliest > when:
            when = _next_payday(day, earliest - timedelta(days=1)) if payday else earliest
            held = (f"Uitgesteld: laatste bericht was op {c.last_contact:%d/%m}. "
                    f"Maximaal 1 bericht per {CONTACT_GAP_DAYS} dagen.")
    return {"date": when.isoformat(), "hour": hour,
            "label": f"{DAYS_NL[when.weekday()]} {when:%d/%m} om {hour:02d}:00",
            "why": why, "held": held}


# ---------------------------------------------------------------- synthetische data
def _monthly(start: date, day: int, amount: float, cp: str, cat: str, until: date = TODAY):
    out, y, m = [], start.year, start.month
    while True:
        d = date(y, m, min(day, 28))
        if d > until:
            break
        if d >= start:
            out.append((d, amount, cp, cat))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _groceries(rng: random.Random, start: date, per_week: float):
    out, d = [], start
    while d <= TODAY:
        out.append((d, -round(per_week * rng.uniform(.7, 1.3), 2), rng.choice(["Colruyt", "Delhaize", "Aldi"]), "groceries"))
        d += timedelta(days=7)
    return out


def demo_customers() -> dict[str, Customer]:
    rng = random.Random(42)
    y0 = TODAY - timedelta(days=365)

    lotte = Customer("c-lotte", "Lotte", 23, "Net begonnen te werken", 0)
    lotte.tx += _monthly(date(2026, 7, 1), 25, 2150, "Colruyt Group NV", "salary")
    lotte.tx += _monthly(date(2026, 7, 1), 1, -720, "Immo Gent BV", "rent")
    lotte.tx += _monthly(y0, 5, 180, "Ouders", "transfer")
    lotte.tx += _groceries(rng, date(2026, 6, 1), 70)
    lotte.tx += [(date(2026, 9, 20), -5400, "Garage Peeters (tweedehands auto)", "shopping")]
    lotte.events += [(date(2026, 9, 12), "search_savings")]

    karim = Customer("c-karim", "Karim", 34, "Zoekt een huis", 24000)
    karim.tx += _monthly(y0, 25, 3400, "Proximus NV", "salary")
    karim.tx += _monthly(date(2026, 7, 1), 1, -950, "Vastgoed Leuven", "rent")
    karim.tx += [(date(2026, 9, 3), -9800, "Notaris De Smet", "notary")]
    karim.tx += _groceries(rng, y0, 110)
    karim.events += [(date(2026, 8, 18), "sim_mortgage"), (date(2026, 9, 1), "sim_mortgage")]
    karim.last_contact = date(2026, 9, 15)  # kreeg onlangs al een bericht: contactbeleid houdt tegen

    jan = Customer("c-jan", "Jan", 62, "Kijkt naar de toekomst", 41000)
    jan.tx += _monthly(y0, 25, 3900, "Vlaamse Overheid", "salary")
    jan.tx += _groceries(rng, y0, 95)
    jan.events += [(date(2026, 9, 8), "sim_pension"), (date(2026, 9, 15), "search_savings")]

    return {c.id: c for c in (lotte, karim, jan)}


def synthetic_population(n: int, seed: int = 7) -> list[Customer]:
    """n willekeurige klanten met een realistische mix van levensfasen en ruis."""
    rng = random.Random(seed)
    y0 = TODAY - timedelta(days=365)
    pop = []
    for i in range(n):
        age = rng.randint(18, 80)
        c = Customer(f"s-{i}", f"Klant {i}", age, "synthetisch", rng.uniform(-200, 20000))
        r = rng.random()
        if age < 30 and r < .08:          # nieuwe job
            start = TODAY - timedelta(days=rng.randint(20, 85))
            c.tx += _monthly(start, 25, rng.uniform(1800, 2600), "Werkgever", "salary")
            if rng.random() < .6:
                c.tx += _monthly(start, 1, -rng.uniform(550, 900), "Verhuurder", "rent")
            if rng.random() < .4:
                c.events.append((TODAY - timedelta(days=rng.randint(1, 60)), "search_savings"))
            c.start_balance = rng.uniform(0, 800)
        elif age < 60:
            c.tx += _monthly(y0, 25, rng.uniform(2200, 5000), "Werkgever", "salary")
            if r < .04:                   # huis kopen
                c.events.append((TODAY - timedelta(days=rng.randint(5, 80)), "sim_mortgage"))
                if rng.random() < .6:
                    c.tx.append((TODAY - timedelta(days=rng.randint(5, 60)), -rng.uniform(6000, 15000), "Notaris", "notary"))
                if rng.random() < .5:
                    c.tx += _monthly(TODAY - timedelta(days=rng.randint(20, 110)), 1, -rng.uniform(700, 1100), "Verhuurder", "rent")
        else:
            c.tx += _monthly(y0, 25, rng.uniform(1500, 4000), "Werkgever/Pensioen", "salary")
            if r < .10:
                c.events.append((TODAY - timedelta(days=rng.randint(1, 80)), "sim_pension"))
                if rng.random() < .5:
                    c.events.append((TODAY - timedelta(days=rng.randint(1, 80)), "search_savings"))
        # ruis: soms ook zonder levensmoment een sparen-zoekopdracht
        if rng.random() < .03:
            c.events.append((TODAY - timedelta(days=rng.randint(1, 80)), "search_savings"))
        pop.append(c)
    return pop
