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

Pull prebuilt image from Docker Hub:

```powershell
docker pull rh45one/savion:latest
docker run -d --name savion -p 8000:8000 -e DATA_DIR=/data -v savion_data:/data rh45one/savion:latest
```

Docker Compose (pull from Docker Hub):

```yaml
version: '3.8'
services:
  savion:
    image: rh45one/savion:latest
    ports:
      - '8000:8000'
    environment:
      - DATA_DIR=/data
    volumes:
      - savion_data:/data

volumes:
  savion_data:
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
- Movements: add/withdraw with `delta`, `amount`, `description`, `resulting_balance`, `timestamp`, and `tags`.
- Tags: define tag types and colors in Settings; use tags on movements; filter by tags; color-coded chips.
- Non-destructive edits: edit description and tags inline; changes are stored as `edit` entries.
- Soft delete: delete a movement with inline confirm; adds a `delete` entry and removes its effect from balances and listings.
- Settings: theme, fade interpolation, currency (EUR/USD/GBP), timezone, language, and tag types. Balance visibility toggle is persisted.
- Themes: `dark`, `light`, `dracula`, `winclassic`, `system1` — with responsive and readable UI across variants.
- Summary: monthly summaries with net change and entry count. Each month is expandable to reveal that month’s total Income and total Expenses.
- Recent Movements: filter by text, action, date range, amount range, and tags. Choose display size (50/100/200/500/All).
- Responsive UI: mobile-first layout, accessible keyboard interactions, and compact grids for small screens.
- Export: returns `ledger.jsonl` with a `settings` snapshot appended; filename `savion-ledger-<UTC timestamp>.jsonl`.
- Import: validates JSONL lines; applies any `settings` entries to `settings.json`; import fails if no valid entries found.
- Reset: protected by typing `RESET` and solving a simple math challenge; logs a `reset` entry and deletes `ledger.jsonl`.
- Health check: `GET /healthz` returns basic status.
- Concurrency: file writes guarded by an internal thread lock to avoid concurrent corruption.

### Internationalization

- Built-in languages: `en`, `es`, `fr`, `zh`, `pt`, `ja`, `de`, `it`.
- Summary totals use translated labels for Income/Expenses.
- Add custom translations in `app/translations.json`.

### UI polish

- Balance visibility toggle on Home (eye/eye-off). Hidden mode preserves the currency symbol.
- Numbers use thousands separators consistently.
- Mobile navigation with hamburger menu; accessible focus states; ESC closes editors.

## API / Endpoints

- `GET /` — main UI (requires setup).
- `GET /summary` — monthly summary view (expand a month to see totals for income and expenses).
- `GET /setup`, `POST /setup` — initial setup or ledger import.
- `POST /movement` — submit a movement (`action`: `add`/`withdraw`, `amount`, optional `description`).
- `POST /movement/edit` — non-destructive edit of `description` and `tags` for a movement.
- `POST /movement/delete` — soft-delete a movement by timestamp.
- `GET /export` — download ledger (appends `settings` snapshot before exporting).
- `GET /reset`, `POST /reset` — reset workflow with verification.
- `GET /settings`, `POST /settings` — view and update UI settings.
- `POST /toggle-balance` — toggle the persisted “show balance” preference from the home page.
- `GET /healthz` — health check.

Notes:

- The home page supports optional query parameters for filtering and display size, e.g. `/?q=groceries&action=add&limit=100`. Use `limit=all` to show all filtered items.

## Ledger format

Each line in `ledger.jsonl` is a JSON object. Common `kind` values:

- `setup` — `{ "kind":"setup", "timestamp":..., "initial_balance": <number> }`
- `movement` — `{ "kind":"movement", "timestamp":..., "action":"add"|"withdraw", "amount":<number>, "delta":<signed>, "description":"...", "resulting_balance":<number> }`
- `edit` — `{ "kind":"edit", "timestamp":..., "target_ts":..., "new_description":"...", "new_tags":["..."] }`
- `delete` — `{ "kind":"delete", "timestamp":..., "target_ts":... }`
- `settings` — settings snapshot saved as a ledger entry.
- `reset` — record indicating a reset occurred.

Entries are validated when read; malformed lines are ignored.

## Changelog (recent)

- Summary: expandable monthly sections now reveal total Income and total Expenses per month.
- Summary and cards: improved mobile responsiveness; all card surfaces now honor theme `--card` for readability (incl. Windows Classic/System 1).
- Themes: added `winclassic` and `system1`; improved tinting for status pills across themes.
- Recent Movements: inline edit (description/tags) and soft delete with confirmation; keyboard and ESC support.
- Filters: added tag filter; preserved filters when changing display size.
- Internationalization: added translation keys for Summary Income/Expenses across all built-in languages.

## Notes & troubleshooting

- If the app shows the setup page: ensure `ledger.jsonl` exists and contains at least one valid `setup`/`movement`/`reset` entry.
- Import requires valid JSONL (one JSON object per line). Malformed lines are skipped; import fails if none are valid.
- Permissions: when running in Docker, mount a volume or host directory to `/data` and ensure the container user can read/write it.
- Movement list shows 50 items by default for performance. Use the selector at the bottom of the list to change to 100/200/500 or All.

## Developer notes

- Main server implementation: `app/main.py` (FastAPI). Templates: `app/templates/`. Static assets: `app/static/`.
- Data model classes: `Movement` and `SettingsEntry` (Pydantic models in `app/main.py`).
- The app is intentionally dependency-light; add a `requirements.txt` for reproducible installs.

## License

Creative Commons BY-NC-SA 4.0 — see `LICENSE` for full text.
