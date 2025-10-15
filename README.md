# Savion — v3
Updates:
- Removed light/dark toggle (dark only).
- Single responsive movements list (no duplicate render).
- Mobile: description wraps to new lines; no horizontal scrolling.

Run:
```bash
docker compose up --build -d
# or
docker build -t savion .
docker run -d --name savion -p 8000:8000 -e DATA_DIR=/data -v savion_data:/data savion
```
Open http://localhost:8000
