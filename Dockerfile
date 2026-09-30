# Container voor Google Cloud Run. Secrets (JWT_SECRET, DEMO_PASSWORD, GEMINI_API_KEY)
# komen als omgevingsvariabelen via Cloud Run, nooit in de image.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Cloud Run zet de echte client als meest rechtse X-Forwarded-For-hop
ENV TRUST_PROXY=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
RUN useradd --create-home app
USER app
WORKDIR /app/backend
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --no-proxy-headers"]
