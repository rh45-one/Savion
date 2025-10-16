# Base: switch to preferred, recent tag to reduce CVEs
FROM python:3.14-alpine3.22

# Security/size hardening
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

# System deps:
# - tzdata for ZoneInfo (your app uses IANA timezones)
# - ca-certificates for HTTPS if ever needed (export/downloads)
RUN apk add --no-cache tzdata ca-certificates

# Create a non-root user and writable data dir
RUN addgroup -S app && adduser -S app -G app && \
    mkdir -p /opt/savion /data && chown -R app:app /opt/savion /data

WORKDIR /opt/savion

# Copy only dependency files first (for better cache)
# If you keep requirements.txt, this optimizes rebuilds
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# Now copy the application
COPY app ./app
COPY app/themes.css ./app/themes.css
COPY app/translations.json ./app/translations.json

# Ensure runtime user
USER app

# Expose HTTP port
EXPOSE 8000

# Basic liveness check (uses busybox wget in Alpine)
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${UVICORN_PORT}/healthz >/dev/null 2>&1 || exit 1

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
