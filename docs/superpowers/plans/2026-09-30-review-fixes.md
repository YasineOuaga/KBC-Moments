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
- [ ] **T1 Login-bescherming** (review 1-3): één lock rond tellen, poging tellen vóór het hashen, tuple-sleutels, gebruikersnaam `^[a-z0-9._-]+$`, client-IP bewust bepalen (`TRUST_PROXY=1` op Cloud Run: meest rechtse X-Forwarded-For). Tests: burst van parallelle pogingen geeft 429, gebruikersnaam met `:` geweigerd.
- [ ] **T2 Toestemming overal bindend** (review 4): `plan_contact` gebruikt loondata enkel met toestemming voor `income`. Test: income uit -> geen loondag-timing.
- [ ] **T3 Ankersignaal per moment** (review 5): "Eerste vaste job" vereist income, "Eerste woning" mortgage of notary, "Pensioen" pension. Test: rent+search+lowbal -> niet actief.
- [ ] **T4 Timing-randgevallen** (minor): loondag 29-31 via `calendar.monthrange`, meest voorkomende loondag, uitgestelde boodschap naar de eerstvolgende loondag, notaris met recency-venster. Tests per geval.
- [ ] **T5 Gedeelde state thread-safe** (minor): lock rond mutaties en iteraties van CONSENT, SUPPRESSED, REVOKED.
- [ ] **T6 Taalmodel veilig** (minor): timeout van 5 s, uitvoer met krediet-/leningtermen of bedragen weigeren. Test op de guard.
- [ ] **T7 Reset herstelt geen toestemming** (minor): reset maakt enkel "Klopt niet" ongedaan. Frontend vangt API-fouten op.
- [ ] **T8 Tests en deploy** (minor + review 6): vervalste tokens met alle claims, adviseur krijgt nooit `signals`/`message`, `/api/stats`; deploy met `--max-instances=1 --min-instances=1`, gepinde versies, README.

## Review Focus
- Parallelle loginpogingen, gespoofde X-Forwarded-For.
- Toestemming intrekken terwijl een moment actief is.
- Klanten zonder loon, loon op 29-31, jaarwissel.
