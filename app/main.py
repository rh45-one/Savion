from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Literal
import os, json, datetime, threading, random

APP_NAME = "Savion"
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LEDGER_PATH = os.path.join(DATA_DIR, "ledger.jsonl")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Default settings ---
DEFAULT_SETTINGS = {
    "theme": "dark",       # "dark" | "light" | "dracula" (applied)
    "fade_start": 1000.0   # balance where green starts to fade toward red
}

app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

write_lock = threading.Lock()

# --- Data models ---
class Movement(BaseModel):
    kind: Literal["setup","movement","reset"]
    timestamp: str
    initial_balance: Optional[float] = None
    note: Optional[str] = None
    action: Optional[Literal["add","withdraw"]] = None
    amount: Optional[float] = None
    delta: Optional[float] = None
    description: Optional[str] = None
    resulting_balance: Optional[float] = None

class SettingsEntry(BaseModel):
    kind: Literal["settings"]
    timestamp: str
    theme: Literal["dark","light","dracula"]
    fade_start: float

# --- Helpers ---
def now_iso():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def is_initialized() -> bool:
    return os.path.exists(LEDGER_PATH) and os.path.getsize(LEDGER_PATH) > 0

def get_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
        # sanitize
        if data.get("theme") not in ("dark", "light", "dracula"):
            data["theme"] = DEFAULT_SETTINGS["theme"]
        try:
            data["fade_start"] = float(data.get("fade_start", DEFAULT_SETTINGS["fade_start"]))
        except Exception:
            data["fade_start"] = DEFAULT_SETTINGS["fade_start"]
        if data["fade_start"] <= 0:
            data["fade_start"] = 1.0
        return data
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(s: dict):
    # persist to settings.json
    with write_lock:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f)

def append_settings_to_ledger(s: dict):
    # record a settings snapshot in the ledger for portability on export/import
    entry = SettingsEntry(
        kind="settings",
        timestamp=now_iso(),
        theme=s.get("theme", DEFAULT_SETTINGS["theme"]),
        fade_start=float(s.get("fade_start", DEFAULT_SETTINGS["fade_start"]))
    )
    with write_lock:
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.dict(), ensure_ascii=False) + "\n")

def read_ledger_entries() -> List[dict]:
    """Read raw JSON objects (skip blank/malformed)."""
    entries: List[dict] = []
    if not os.path.exists(LEDGER_PATH):
        return entries
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entries.append(obj)
            except Exception:
                continue
    return entries

def read_movements() -> List[Movement]:
    """Only return movement/setup/reset entries (ignore settings lines)."""
    rows: List[Movement] = []
    for obj in read_ledger_entries():
        k = obj.get("kind")
        if k in ("setup","movement","reset"):
            try:
                rows.append(Movement(**obj))
            except Exception:
                continue
    return rows

def compute_balance(rows: List[Movement]) -> float:
    balance = 0.0
    for r in rows:
        if r.kind == "setup" and r.initial_balance is not None:
            balance = float(r.initial_balance)
        elif r.kind == "movement" and r.delta is not None:
            balance += float(r.delta)
    return round(balance, 2)

def append_entry(entry: Movement):
    with write_lock:
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.dict(), ensure_ascii=False) + "\n")

def ensure_setup_page():
    if not is_initialized():
        return RedirectResponse(url="/setup", status_code=303)
    return None

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    guard = ensure_setup_page()
    if guard: return guard

    settings = get_settings()
    rows = read_movements()
    balance = compute_balance(rows)

    # compute HSL color based on settings.fade_start
    fade_start = float(settings["fade_start"])
    if balance <= 0:
        hue = 0.0  # red
    elif balance >= fade_start:
        hue = 120.0  # green
    else:
        ratio = max(0.0, min(balance / fade_start, 1.0))
        hue = 120.0 * ratio
    balance_color = f"hsl({hue:.0f}, 70%, 60%)"

    movements = [r for r in rows if r.kind == "movement"]
    movements.sort(key=lambda r: r.timestamp, reverse=True)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "balance": f"{balance:.2f}",
        "balance_color": balance_color,
        "movements": movements[:200],
        "app_name": APP_NAME,
        "theme": settings["theme"]
    })

@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if is_initialized():
        return RedirectResponse("/", 303)
    settings = get_settings()
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "app_name": APP_NAME,
        "theme": settings["theme"]
    })

@app.post("/setup", response_class=HTMLResponse)
async def setup_post(
    request: Request,
    initial_balance: Optional[float] = Form(default=None),
    setup_mode: str = Form(default="fresh"),
    ledger_file: Optional[UploadFile] = File(default=None),
):
    if is_initialized():
        return RedirectResponse("/", 303)

    if setup_mode == "import":
        if not ledger_file:
            s = get_settings()
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "Please choose a ledger file to import.",
                "app_name": APP_NAME,
                "theme": s["theme"]
            }, status_code=400)
        content = await ledger_file.read()
        text = content.decode("utf-8", errors="ignore")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            s = get_settings()
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "Uploaded file is empty.",
                "app_name": APP_NAME,
                "theme": s["theme"]
            }, status_code=400)

        # Write file verbatim; also apply any settings lines found
        parsed_any = False
        imported_settings = None
        with write_lock:
            with open(LEDGER_PATH, "w", encoding="utf-8") as f:
                for ln in lines:
                    try:
                        obj = json.loads(ln)
                        k = obj.get("kind")
                        if k == "settings":
                            # apply to settings.json as well
                            try:
                                se = SettingsEntry(**obj)
                                imported_settings = {"theme": se.theme, "fade_start": float(se.fade_start)}
                            except Exception:
                                pass
                        else:
                            # validate movement-like lines
                            Movement(**obj)
                        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                        parsed_any = True
                    except Exception:
                        pass
        if not parsed_any:
            s = get_settings()
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "File format invalid. Expecting JSON Lines exported by Savion.",
                "app_name": APP_NAME,
                "theme": s["theme"]
            }, status_code=400)

        # If import carried settings, persist them
        if imported_settings:
            s = get_settings()
            s.update(imported_settings)
            save_settings(s)

        return RedirectResponse("/", 303)

    else:
        if initial_balance is None:
            s = get_settings()
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "Please enter an initial balance or choose Import.",
                "app_name": APP_NAME,
                "theme": s["theme"]
            }, status_code=400)
        entry = Movement(
            kind="setup",
            timestamp=now_iso(),
            initial_balance=float(initial_balance),
            note="Fresh setup"
        )
        append_entry(entry)
        return RedirectResponse("/", 303)

@app.post("/movement")
async def add_movement(
    action: Literal["add","withdraw"] = Form(...),
    amount: float = Form(...),
    description: Optional[str] = Form(default="")
):
    guard = ensure_setup_page()
    if guard: return guard

    rows = read_movements()
    balance = compute_balance(rows)

    delta = float(amount) if action == "add" else -float(amount)
    new_balance = round(balance + delta, 2)

    entry = Movement(
        kind="movement",
        timestamp=now_iso(),
        action=action,
        amount=float(amount),
        delta=delta,
        description=description or "",
        resulting_balance=new_balance
    )
    append_entry(entry)

    return RedirectResponse("/", 303)

@app.get("/export")
async def export_ledger():
    guard = ensure_setup_page()
    if guard: return guard

    # Ensure latest settings snapshot is recorded in ledger before export
    s = get_settings()
    append_settings_to_ledger(s)

    if not os.path.exists(LEDGER_PATH):
        return PlainTextResponse("No ledger available.", status_code=404)
    filename = f"savion-ledger-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    return FileResponse(LEDGER_PATH, media_type="text/plain", filename=filename)

@app.get("/reset", response_class=HTMLResponse)
async def reset_get(request: Request):
    guard = ensure_setup_page()
    if guard: return guard

    a = random.randint(20, 60)
    b = random.randint(5, 15)
    op = random.choice(["+","-"])
    s = get_settings()
    return templates.TemplateResponse("reset.html", {
        "request": request,
        "a": a, "b": b, "op": op,
        "app_name": APP_NAME,
        "theme": s["theme"]
    })

@app.post("/reset", response_class=HTMLResponse)
async def reset_post(
    request: Request,
    confirm_text: str = Form(...),
    a: int = Form(...),
    b: int = Form(...),
    op: str = Form(...),
    math_answer: int = Form(...),
):
    guard = ensure_setup_page()
    if guard: return guard

    expected = a + b if op == "+" else a - b
    if confirm_text.strip().upper() != "RESET" or math_answer != expected:
        s = get_settings()
        return templates.TemplateResponse("reset.html", {
            "request": request,
            "error": "Verification failed. Type RESET and solve the math correctly.",
            "a": random.randint(20,60),
            "b": random.randint(5,15),
            "op": random.choice(["+","-"]),
            "app_name": APP_NAME,
            "theme": s["theme"]
        }, status_code=400)

    # Log reset and wipe ledger
    if os.path.exists(LEDGER_PATH):
        try:
            rows = read_movements()
            balance = compute_balance(rows)
            reset_entry = Movement(kind="reset", timestamp=now_iso(), note=f"Reset at balance {balance:.2f}")
            append_entry(reset_entry)
        except Exception:
            pass
        with write_lock:
            try:
                os.remove(LEDGER_PATH)
            except FileNotFoundError:
                pass

    # Reset settings to defaults
    save_settings(DEFAULT_SETTINGS.copy())

    return RedirectResponse("/setup", 303)

# --- Settings page ---
@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request):
    s = get_settings()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "app_name": APP_NAME,
        "theme": s["theme"],
        "settings": s
    })

@app.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    theme: Literal["dark","light","dracula"] = Form(...),
    fade_start: float = Form(...),
):
    # sanitize fade_start
    try:
        fs = float(fade_start)
    except Exception:
        fs = DEFAULT_SETTINGS["fade_start"]
    if fs <= 0:
        fs = 1.0

    s = get_settings()
    s["theme"] = theme
    s["fade_start"] = fs

    # persist to file AND record a snapshot in ledger for portability
    save_settings(s)
    if is_initialized():
        append_settings_to_ledger(s)

    return RedirectResponse("/settings", 303)

@app.get("/healthz")
async def health():
    return {"status": "ok"}
