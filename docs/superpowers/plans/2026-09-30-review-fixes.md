# Review-fixes en backend-verbeteringen Implementation Plan

> Werkwijze: Superpowers (requesting-code-review -> writing-plans -> test-driven-development -> verification-before-completion).

**Goal:** De bevindingen uit de onafhankelijke code-review oplossen, zodat login-bescherming, toestemming en "liever niets dan fout" ook onder aanval en randgevallen kloppen.

**Architecture:** Kleine, gerichte wijzigingen in `backend/engine.py` (momentlogica, timing) en `backend/main.py` (auth, state, taalmodel). Elke taak start met een falende test in `tests/`.

**Tech Stack:** Python 3.11+, FastAPI, PyJWT, pytest.

## Global Constraints
- Klant-ID altijd uit de JWT. Adviseur ziet nooit niet-toegestane signalen of ruwe transacties.
- Onder 50% zekerheid: niets sturen. Geen krediet-push.
- De demo mag nooit crashen.

## Tasks
- [x] **T1 Login-bescherming** (review 1-3): één lock rond tellen, poging tellen vóór het hashen, tuple-sleutels, gebruikersnaam `^[a-z0-9._-]+$`, client-IP bewust bepalen (`TRUST_PROXY=1` op Cloud Run: meest rechtse X-Forwarded-For). Tests: burst van parallelle pogingen geeft 429, gebruikersnaam met `:` geweigerd.
- [x] **T2 Toestemming overal bindend** (review 4): `plan_contact` gebruikt loondata enkel met toestemming voor `income`. Test: income uit -> geen loondag-timing.
- [x] **T3 Ankersignaal per moment** (review 5): "Eerste vaste job" vereist income, "Eerste woning" mortgage of notary, "Pensioen" pension. Test: rent+search+lowbal -> niet actief.
- [x] **T4 Timing-randgevallen** (minor): loondag 29-31 via `calendar.monthrange`, meest voorkomende loondag, uitgestelde boodschap naar de eerstvolgende loondag, notaris met recency-venster. Tests per geval.
- [x] **T5 Gedeelde state thread-safe** (minor): lock rond mutaties en iteraties van CONSENT, SUPPRESSED, REVOKED.
- [x] **T6 Taalmodel veilig** (minor): timeout van 5 s, uitvoer met krediet-/leningtermen of bedragen weigeren. Test op de guard.
- [x] **T7 Reset herstelt geen toestemming** (minor): reset maakt enkel "Klopt niet" ongedaan. Frontend vangt API-fouten op.
- [x] **T8 Tests en deploy** (minor + review 6): vervalste tokens met alle claims, adviseur krijgt nooit `signals`/`message`, `/api/stats`; deploy met `--max-instances=1 --min-instances=1`, gepinde versies, README.

## Review Focus
- Parallelle loginpogingen, gespoofde X-Forwarded-For.
- Toestemming intrekken terwijl een moment actief is.
- Klanten zonder loon, loon op 29-31, jaarwissel.

## Tweede review (na T1-T8)
- [x] Uitvoerfilter taalmodel te streng: bedragen uit de actie en "woonlening" als onderwerp nu toegelaten, krediet-push en verzonnen bedragen nog steeds geweigerd.
- [x] Ankerregel verborg een geldig moment: verankerde momenten gaan nu voor bij de keuze.
- [x] Lege tests vervangen door tests die het gedrag echt afdwingen; test voor geslaagde login na mislukte pogingen.
- [x] TRUST_PROXY uit de image, enkel bij deploy achter Cloud Run.
- [x] Cache en teller van het taalmodel onder de lock; gelijkspel loondag kiest de niet-verschoven dag.
