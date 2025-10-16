# Recent, small base lowers CVEs
FROM python:3.14-alpine3.22

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

# Only what we truly need at runtime
RUN apk add --no-cache tzdata ca-certificates

# Non-root user + writable /data for persistence
RUN addgroup -S app && adduser -S app -G app && \
    mkdir -p /opt/savion /data && chown -R app:app /opt/savion /data

WORKDIR /opt/savion

# Install deps first (better cache) — no compiled extras
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Then copy the app (respects .dockerignore)
COPY . .

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${UVICORN_PORT}/healthz >/dev/null 2>&1 || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
