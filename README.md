# KBC Moments

**Begeleid klanten op het juiste moment, niet met de juiste reclame.**
Proof of concept voor de KBC Challenge, Tectonic Hackathon 2026.

## Het idee
KBC herkent levensmomenten (eerste job, eerste woning, op weg naar pensioen) uit transacties en app-gedrag, en reageert met **één** passende actie op het juiste kanaal. Drie principes:

1. **Uitlegbaar:** elke klant ziet *waarom*, met het concrete bewijs ("Eerste loon van Colruyt Group NV op 25/07").
2. **Klant beslist:** toestemming per signaal. Zet een signaal uit en het voorstel past zich meteen aan. "Klopt niet" wordt onthouden.
3. **Liever niets dan fout:** onder 50% zekerheid wordt er niets gestuurd. Geen krediet-push.

## Het juiste moment
Een moment herkennen is niet genoeg: de boodschap moet ook op het juiste tijdstip vertrekken.
- **Timing per moment:** "Eerste vaste job" vertrekt de ochtend dat het loon binnenkomt (valt de loondag in het weekend, dan de vrijdag ervoor). Andere momenten: de eerstvolgende werkdag, tijdens de kantooruren.
- **Contactbeleid:** maximaal 1 proactief bericht per 30 dagen per klant. Karim kreeg op 15/09 al een bericht, dus zijn voorstel schuift op naar 15/10.
- De klant ziet op een telefoonvoorbeeld hoe en wanneer het bericht binnenkomt, of waarom er geen melding komt.

## Waarom het schaalt naar 2,3 miljoen klanten
```
Transacties/events → Signalen → Moment (regels, batch) → Beleid (actie of niets) → Taalmodel (enkel bij trigger) → Kanaal
```
- Detectie is deterministisch en goedkoop: **10.000 klanten in ±0,1 s** op 1 CPU-kern (gemeten in de app).
- Slechts ±6% van de klanten heeft een moment, dus het taalmodel wordt alleen voor hen aangeroepen (met cache).

## Draaien
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # vul JWT_SECRET en DEMO_PASSWORD in
cd backend && uvicorn main:app --reload
```
Open http://localhost:8000. Demo-gebruikers: `lotte`, `karim`, `jan` (klanten) en `adviseur` (ziet enkel Lotte en Karim). Wachtwoord = `DEMO_PASSWORD` uit `.env`.

Tests draaien (vanuit de root):
```bash
pip install -r requirements-dev.txt
pytest -q
```

Deployen op Google Cloud Run (secrets als omgevingsvariabelen, nooit in de image):
```bash
gcloud run deploy kbc-moments --source . --region europe-west1 --allow-unauthenticated \
  --set-env-vars JWT_SECRET=...,DEMO_PASSWORD=...,GEMINI_API_KEY=...
```

## Security
- Klant-ID komt uit de JWT, nooit uit de URL of body (geen IDOR).
- Rollen server-side gecontroleerd. De adviseur ziet enkel toegewezen klanten en enkel signalen met toestemming, geen ruwe transacties.
- PBKDF2-gehashte wachtwoorden en strikte input-validatie.
- Login-bescherming zonder lockout-misbruik: enkel mislukte pogingen tellen, per gebruiker+IP. Een aanvaller kan een echte klant dus niet buitensluiten. De tabel met pogingen is begrensd (geen geheugenlek).
- JWT met `iss`, `aud` en `jti`. Uitloggen trekt de token server-side in.
- Business logic: "Klopt niet" kan enkel op het moment dat de klant effectief te zien krijgt.
- Security headers: strikte CSP zonder inline scripts, HSTS, Permissions-Policy. Output-escaping in de frontend.
- 18 automatische tests voor authenticatie, autorisatie/IDOR en business logic (`tests/`).
- Geen secrets in de repo, enkel synthetische data.

## Structuur
- `backend/engine.py`: signaaldetectie, momentscoring, synthetische data
- `backend/main.py`: API, auth, personalisatie via Gemini (met fallback)
- `frontend/index.html` + `frontend/app.js`: klant-, adviseur- en schaal-view in KBC-stijl
- `tests/test_api.py`: security- en logica-tests
- `Dockerfile`: container voor Cloud Run

## Onafgewerkt
- Data zit in geheugen (herstart = reset). In productie: event-streaming en een feature store.
- Momenten zijn regelgebaseerd. Volgende stap: gewichten leren uit feedback ("klopt niet").
- Kanalen worden getoond, maar niet echt verstuurd.
