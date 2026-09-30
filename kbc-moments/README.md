# KBC Moments

**Begeleid klanten op het juiste moment, niet met de juiste reclame.**
Proof of concept voor de KBC Challenge, Tectonic Hackathon 2026.

## Het idee
KBC herkent levensmomenten (eerste job, eerste woning, op weg naar pensioen) uit transacties en app-gedrag, en reageert met **één** passende actie op het juiste kanaal. Drie principes:

1. **Uitlegbaar:** elke klant ziet *waarom*, met het concrete bewijs ("Eerste loon van Colruyt Group NV op 25/07").
2. **Klant beslist:** toestemming per signaal. Zet een signaal uit en het voorstel past zich meteen aan. "Klopt niet" wordt onthouden.
3. **Liever niets dan fout:** onder 50% zekerheid wordt er niets gestuurd. Geen krediet-push.

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

## Security
- Klant-ID komt uit de JWT, nooit uit de URL of body (geen IDOR).
- Rollen server-side gecontroleerd. De adviseur ziet enkel toegewezen klanten en enkel signalen met toestemming, geen ruwe transacties.
- PBKDF2-gehashte wachtwoorden, rate limiting op login, strikte input-validatie, security headers (CSP), output-escaping in de frontend.
- Geen secrets in de repo, enkel synthetische data.

## Structuur
- `backend/engine.py`: signaaldetectie, momentscoring, synthetische data
- `backend/main.py`: API, auth, personalisatie via Gemini (met fallback)
- `frontend/index.html`: klant-, adviseur- en schaal-view

## Onafgewerkt
- Data zit in geheugen (herstart = reset). In productie: event-streaming en een feature store.
- Momenten zijn regelgebaseerd. Volgende stap: gewichten leren uit feedback ("klopt niet").
- Kanalen worden getoond, maar niet echt verstuurd.
