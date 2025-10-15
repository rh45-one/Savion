# Savion

What
- Minimal personal ledger web app (FastAPI + Jinja2). Record movements, export/import JSONL ledger, reset safely.

Run (Docker)
```powershell
docker compose up --build -d
# or
docker build -t savion .
docker run -d --name savion -p 8000:8000 -e DATA_DIR=/data -v savion_data:/data savion
```

Run (local)
```powershell
pip install fastapi uvicorn jinja2 pydantic python-multipart
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Config
- `DATA_DIR` environment variable (default `/data`).
- Files in `DATA_DIR`: `ledger.jsonl`, `settings.json`.

Ledger format (`ledger.jsonl`)
- Newline-delimited JSON objects. Key `kind` values:
  - `setup`: sets `initial_balance`.
  - `movement`: fields `action` (`add`/`withdraw`), `amount`, `delta`, `resulting_balance`, `description`.
  - `reset`: record before ledger is deleted.
  - `settings`: snapshot of `settings.json` (appended on export and on settings change).

Export/Import
- Export: GET `/export` — app appends a `settings` snapshot before returning the file.
- Import: upload JSONL on `/setup` (import mode). Server validates lines; import fails if no valid entries.

Settings
- Stored in `settings.json`: `theme` (`dark`/`light`/`dracula`) and `fade_start` (number used for balance color).

Reset
- Requires typing `RESET` and answering a simple math question. Logs a `reset` entry, deletes `ledger.jsonl`, resets `settings.json` to defaults.

Troubleshooting
- If you see the setup page: ensure `ledger.jsonl` exists and contains at least one valid `setup`/`movement`/`reset` entry.
- Import errors: file must be valid JSONL (one JSON object per line). Malformed lines are skipped.
- Permission errors: mount a Docker volume or use a host directory with correct permissions for `DATA_DIR`.

Developer notes
- Main server: `app/main.py`. Templates: `app/templates/`. Static: `app/static/`.
- Add `requirements.txt` and tests if you plan ongoing development.

License
- No license file included. Add `LICENSE` if you want to publish or redistribute.
