"""KBC Moments API.

Security-principes (Aikido: auth, authorization, IDOR, business logic):
- De klant-ID komt ALTIJD uit de JWT, nooit uit de URL of body.
- Adviseurs zien enkel klanten die aan hen toegewezen zijn.
- Rollen worden server-side gecontroleerd per endpoint.
- Wachtwoorden gehasht (PBKDF2), secrets enkel via omgevingsvariabelen.
- Rate limiting op login, strikte input-validatie, security headers.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import engine

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

JWT_SECRET = os.getenv("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise RuntimeError("Zet JWT_SECRET (minstens 32 tekens) in .env")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")
if len(DEMO_PASSWORD) < 8:
    raise RuntimeError("Zet DEMO_PASSWORD (minstens 8 tekens) in .env")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TOKEN_TTL = timedelta(hours=2)
JWT_ISS = JWT_AUD = "kbc-moments"

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# ---------------------------------------------------------------- gebruikers
def _hash(pw: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)


def _user(role: str, customer_id: str | None = None, clients: tuple = ()):
    salt = secrets.token_bytes(16)
    return {"role": role, "customer_id": customer_id, "clients": set(clients),
            "salt": salt, "pw": _hash(DEMO_PASSWORD, salt)}


USERS = {
    "lotte": _user("customer", "c-lotte"),
    "karim": _user("customer", "c-karim"),
    "jan": _user("customer", "c-jan"),
    "adviseur": _user("advisor", clients=("c-lotte", "c-karim")),  # Jan is NIET toegewezen
}

CUSTOMERS = engine.demo_customers()
SIGNALS = {cid: engine.detect_signals(c) for cid, c in CUSTOMERS.items()}
CONSENT: dict[str, set[str]] = {cid: set(engine.SIGNALS) for cid in CUSTOMERS}
SUPPRESSED: dict[str, set[str]] = defaultdict(set)
MSG_CACHE: dict[tuple, dict] = {}
LLM_CALLS = {"count": 0}
REVOKED: dict[str, float] = {}  # jti -> verloop (epoch), na uitloggen ongeldig

app = FastAPI(title="KBC Moments", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; connect-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- auth
bearer = HTTPBearer(auto_error=False)
_attempts: dict[str, deque] = defaultdict(deque)
MAX_TRACKED = 10_000  # begrens geheugen: willekeurige gebruikersnamen vullen de tabel niet op
WINDOW = 60


def _recent(key: str) -> deque:
    now = time.monotonic()
    if len(_attempts) > MAX_TRACKED:
        for k in [k for k, q in _attempts.items() if not q or now - q[-1] > WINDOW]:
            del _attempts[k]
        if len(_attempts) > MAX_TRACKED:  # nog steeds vol: oudste weg
            for k in sorted(_attempts, key=lambda k: _attempts[k][-1])[: len(_attempts) // 2]:
                del _attempts[k]
    q = _attempts[key]
    while q and now - q[0] > WINDOW:
        q.popleft()
    return q


def _check(key: str, limit: int):
    if len(_recent(key)) >= limit:
        raise HTTPException(429, "Te veel pogingen, probeer over een minuut opnieuw")


def _hit(key: str):
    _recent(key).append(time.monotonic())


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(401, "Niet ingelogd")
    try:
        data = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"],
                          audience=JWT_AUD, issuer=JWT_ISS,
                          options={"require": ["sub", "exp", "role", "jti", "iss", "aud"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Ongeldige of verlopen sessie")
    if data["jti"] in REVOKED:
        raise HTTPException(401, "Sessie beëindigd")
    user = USERS.get(data["sub"])
    if user is None or user["role"] != data["role"]:
        raise HTTPException(401, "Ongeldige sessie")
    return {"username": data["sub"], "jti": data["jti"], "exp": data["exp"], **user}


def require(role: str):
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] != role:
            raise HTTPException(403, "Geen toegang")
        return user
    return dep


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else "?"
    name = body.username.lower()
    # Enkel MISLUKTE pogingen tellen, per gebruiker+IP. Zo kan een aanvaller van
    # elders een echte klant niet buitensluiten. De ruimere limiet per gebruiker
    # blijft een rem op brute force over veel IP's heen.
    keys = {f"ip:{ip}": 30, f"fail:{name}:{ip}": 5, f"fail:{name}": 30}
    for k, limit in keys.items():
        _check(k, limit)
    _hit(f"ip:{ip}")
    user = USERS.get(name)
    # altijd hashen, ook bij onbekende user (geen timing-lek)
    salt = user["salt"] if user else b"\x00" * 16
    ok = hmac.compare_digest(_hash(body.password, salt), user["pw"] if user else b"")
    if not user or not ok:
        _hit(f"fail:{name}:{ip}")
        _hit(f"fail:{name}")
        raise HTTPException(401, "Verkeerde gebruikersnaam of wachtwoord")
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": name, "role": user["role"], "iss": JWT_ISS, "aud": JWT_AUD,
                        "jti": secrets.token_urlsafe(16), "iat": now, "exp": now + TOKEN_TTL},
                       JWT_SECRET, algorithm="HS256")
    return {"token": token, "role": user["role"], "name": name.capitalize()}


@app.post("/api/logout")
def logout(user: dict = Depends(current_user)):
    now = time.time()
    for jti in [j for j, exp in REVOKED.items() if exp < now]:
        del REVOKED[jti]  # verlopen tokens hoeven niet onthouden te worden
    REVOKED[user["jti"]] = user["exp"]
    return {"ok": True}


# ---------------------------------------------------------------- personalisatie
def _fallback_message(c: engine.Customer, m: dict) -> str:
    return f"Hoi {c.name}, we zagen dat er iets verandert. We willen je helpen: {m['goal']}. Jij beslist of en wanneer."


def _personal_message(c: engine.Customer, key: str, used: list[str]) -> dict:
    """Taalmodel ENKEL bij een actief moment, met cache. Fallback zonder API-key."""
    cache_key = (c.id, key, tuple(sorted(used)))
    if cache_key in MSG_CACHE:
        return MSG_CACHE[cache_key]
    m = engine.MOMENTS[key]
    text, source = _fallback_message(c, m), "sjabloon"
    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "Je schrijft één korte boodschap (max 2 zinnen, Nederlands) van KBC aan een klant.\n"
                f"Voornaam: {c.name}. Toon: {m['tone']}. Doel: {m['goal']}.\n"
                f"Voorgestelde actie: {m['action']}.\n"
                "Regels: geen verkoopdruk, geen krediet voorstellen, geen bedragen verzinnen, "
                "benadruk dat de klant zelf beslist. Geef enkel de boodschap."
            )
            r = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            if r.text and len(r.text) < 600:
                text, source = r.text.strip(), "taalmodel"
                LLM_CALLS["count"] += 1
        except Exception:
            pass  # demo mag nooit crashen: val terug op sjabloon
    out = {"text": text, "source": source}
    MSG_CACHE[cache_key] = out
    return out


def _view(cid: str, with_message: bool = True) -> dict:
    c = CUSTOMERS[cid]
    sigs = SIGNALS[cid]
    best = engine.pick_moment(sigs, CONSENT[cid], SUPPRESSED[cid])
    res = {
        "customer": {"name": c.name, "age": c.age, "desc": c.desc},
        "signals": [{"key": k, "label": lbl, "present": k in sigs, "consent": k in CONSENT[cid],
                     "evidence": sigs.get(k) if k in CONSENT[cid] else None}
                    for k, lbl in engine.SIGNALS.items()],
        "score": best["score"], "active": best["active"], "suppressed": sorted(SUPPRESSED[cid]),
        "why": [{"label": engine.SIGNALS[s], "evidence": sigs[s]} for s in best["used"]],
    }
    if best["active"]:
        m = engine.MOMENTS[best["key"]]
        res["moment"] = {"key": best["key"], "title": m["title"], "action": m["action"],
                         "channel": m["channel"], "tone": m["tone"]}
        res["timing"] = engine.plan_contact(c, best["key"])
        if with_message:
            res["message"] = _personal_message(c, best["key"], best["used"])
    return res


# ---------------------------------------------------------------- klant-endpoints
@app.get("/api/me")
def me(user: dict = Depends(require("customer"))):
    return _view(user["customer_id"])  # ID uit de token, nooit uit de request


class ConsentIn(BaseModel):
    signal: Literal["income", "rent", "search", "lowbal", "mortgage", "notary", "pension"]
    enabled: bool


@app.put("/api/me/consent")
def set_consent(body: ConsentIn, user: dict = Depends(require("customer"))):
    cid = user["customer_id"]
    (CONSENT[cid].add if body.enabled else CONSENT[cid].discard)(body.signal)
    return _view(cid)


class FeedbackIn(BaseModel):
    moment: Literal["first", "home", "ret"]


@app.post("/api/me/feedback")
def feedback(body: FeedbackIn, user: dict = Depends(require("customer"))):
    """'Klopt niet': dit moment wordt niet meer voorgesteld aan deze klant."""
    cid = user["customer_id"]
    best = engine.pick_moment(SIGNALS[cid], CONSENT[cid], SUPPRESSED[cid])
    # enkel feedback op het moment dat de klant nu effectief te zien krijgt
    if not best["active"] or best["key"] != body.moment:
        raise HTTPException(409, "Dit moment wordt je momenteel niet voorgesteld")
    SUPPRESSED[cid].add(body.moment)
    return _view(user["customer_id"])


@app.post("/api/me/reset")
def reset(user: dict = Depends(require("customer"))):
    cid = user["customer_id"]
    CONSENT[cid] = set(engine.SIGNALS)
    SUPPRESSED[cid].clear()
    return _view(cid)


# ---------------------------------------------------------------- adviseur
@app.get("/api/advisor/clients")
def advisor_clients(user: dict = Depends(require("advisor"))):
    out = []
    for cid in sorted(user["clients"]):
        v = _view(cid, with_message=False)
        # adviseur ziet het moment en de uitleg, geen ruwe transacties
        out.append({"customer": v["customer"], "score": v["score"], "active": v["active"],
                    "moment": v.get("moment"), "timing": v.get("timing"), "why": v["why"]})
    return out


# ---------------------------------------------------------------- schaal
_STATS: dict = {}


@app.get("/api/stats")
def stats(user: dict = Depends(current_user)):
    if not _STATS:
        n = 10_000
        pop = engine.synthetic_population(n)
        t0 = time.perf_counter()
        counts = {k: 0 for k in engine.MOMENTS}
        none = 0
        for c in pop:
            best = engine.pick_moment(engine.detect_signals(c), set(engine.SIGNALS))
            if best["active"]:
                counts[best["key"]] += 1
            else:
                none += 1
        ms = (time.perf_counter() - t0) * 1000
        triggered = n - none
        _STATS.update({
            "customers": n, "ms": round(ms), "none": none, "triggered": triggered,
            "moments": [{"title": engine.MOMENTS[k]["title"], "count": v} for k, v in counts.items()],
            "trigger_rate": round(triggered / n * 100, 1),
            "projected_seconds_2_3m": round(ms / 1000 * 230, 1),  # 1 CPU-kern, lineair
        })
    return {**_STATS, "llm_calls_this_session": LLM_CALLS["count"]}


# ---------------------------------------------------------------- frontend
@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")


@app.get("/app.js")
def app_js():
    return FileResponse(FRONTEND_DIR / "app.js", media_type="text/javascript")
