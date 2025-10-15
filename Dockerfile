FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app
RUN mkdir -p /app && mkdir -p ${DATA_DIR}

RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart

COPY app /app/app

EXPOSE 8000
HEALTHCHECK CMD curl --fail http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
