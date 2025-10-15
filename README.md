# Savion

Minimal personal ledger web app (FastAPI + Jinja2). Records add/withdraw movements in a newline-delimited JSON ledger, supports import/export, settings snapshots, and a protected reset.

Live demo (non-persistent): [https://savion.onrender.com](https://savion.onrender.com) — usually starts in ~20 seconds (may take up to 1 minute).

## Run

Docker (recommended):

```powershell
docker compose up --build -d
```

Or build/run manually:

```powershell
docker build -t savion .
docker run -d --name savion -p 8000:8000 -e DATA_DIR=/data -v savion_data:/data savion
```

Local (development):

```powershell
pip install fastapi uvicorn jinja2 pydantic python-multipart
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Config & data

- `DATA_DIR` environment variable (default `/data`).
- Files stored in `DATA_DIR`:
  - `ledger.jsonl` — newline-delimited JSON ledger.
  - `settings.json` — app settings snapshot.
 - Languages: `en`, `es`, `fr`, `zh`, `pt`, `ja`, `de`, `it` (selectable in Settings). Translations are in `app/translations.json`.

## Features

- Setup: fresh initial balance or import a JSONL ledger.
- Movements: add or withdraw; each movement stores `delta`, `amount`, `description`, `resulting_balance`, and `timestamp`.
- Settings: `theme` (`dark`/`light`/`dracula`) and `fade_start` (controls balance color interpolation).
- Export: returns `ledger.jsonl` with a `settings` snapshot appended; filename `savion-ledger-<UTC timestamp>.jsonl`.
- Import: validates JSONL lines; applies any `settings` entries to `settings.json`; import fails if no valid entries found.
- Reset: protected by typing `RESET` and solving a simple math challenge; logs a `reset` entry and deletes `ledger.jsonl`.
- Health check: `GET /healthz` returns basic status.
- Concurrency: file writes guarded by an internal thread lock to avoid concurrent corruption.

## API / Endpoints

- `GET /` — main UI (requires setup).
- `GET /setup`, `POST /setup` — initial setup or ledger import.
- `POST /movement` — submit a movement (`action`: `add`/`withdraw`, `amount`, optional `description`).
- `GET /export` — download ledger (appends `settings` snapshot before exporting).
- `GET /reset`, `POST /reset` — reset workflow with verification.
- `GET /settings`, `POST /settings` — view and update UI settings.
- `GET /healthz` — health check.

## Ledger format

Each line in `ledger.jsonl` is a JSON object. Common `kind` values:

- `setup` — `{ "kind":"setup", "timestamp":..., "initial_balance": <number> }`
- `movement` — `{ "kind":"movement", "timestamp":..., "action":"add"|"withdraw", "amount":<number>, "delta":<signed>, "description":"...", "resulting_balance":<number> }`
- `settings` — settings snapshot saved as a ledger entry.
- `reset` — record indicating a reset occurred.

Entries are validated when read; malformed lines are ignored.

## Notes & troubleshooting

- If the app shows the setup page: ensure `ledger.jsonl` exists and contains at least one valid `setup`/`movement`/`reset` entry.
- Import requires valid JSONL (one JSON object per line). Malformed lines are skipped; import fails if none are valid.
- Permissions: when running in Docker, mount a volume or host directory to `/data` and ensure the container user can read/write it.
- Movement list on the UI is limited to the most recent 200 movements for performance.

## Developer notes

- Main server implementation: `app/main.py` (FastAPI). Templates: `app/templates/`. Static assets: `app/static/`.
- Data model classes: `Movement` and `SettingsEntry` (Pydantic models in `app/main.py`).
- The app is intentionally dependency-light; add a `requirements.txt` for reproducible installs.

## License

MIT License — see `LICENSE` for full text.
