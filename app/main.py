from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Literal
from zoneinfo import ZoneInfo
import os, json, datetime, threading, random

APP_NAME = "Savion"
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LEDGER_PATH = os.path.join(DATA_DIR, "ledger.jsonl")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Default settings ---
DEFAULT_SETTINGS = {
    "theme": "dark",        # "dark" | "light" | "dracula"
    "fade_start": 1000.0,   # where green starts to fade to red
    "currency": "EUR",      # "EUR" | "USD" | "GBP"
    "timezone": "Europe/Madrid"  # IANA tz for display + new log timestamps
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
    currency: Optional[Literal["EUR","USD","GBP"]] = None
    timezone: Optional[str] = None  # IANA tz

# --- Helpers ---
def validate_timezone(tz: Optional[str]) -> str:
    name = (tz or "").strip() or DEFAULT_SETTINGS["timezone"]
    try:
        ZoneInfo(name)
        return name
    except Exception:
        return DEFAULT_SETTINGS["timezone"]

def now_iso_in_tz(tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = datetime.timezone.utc
    return datetime.datetime.now(tz=tz).isoformat()

def parse_ts(ts: str) -> datetime.datetime:
    """Parse ISO timestamp to aware datetime; fall back to epoch if invalid."""
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

def format_display_date(ts: str, tz_name: str) -> str:
    """Return European-format date: DD/MM/YYYY HH:MM in target tz."""
    dt = parse_ts(ts)
    try:
        tz = ZoneInfo(tz_name)
        dt = dt.astimezone(tz)
    except Exception:
        pass
    return dt.strftime("%d/%m/%Y %H:%M")

def is_initialized() -> bool:
    return os.path.exists(LEDGER_PATH) and os.path.getsize(LEDGER_PATH) > 0

def get_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # ensure defaults
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
        # sanitize
        if data.get("theme") not in ("dark","light","dracula"):
            data["theme"] = DEFAULT_SETTINGS["theme"]
        try:
            data["fade_start"] = float(data.get("fade_start", DEFAULT_SETTINGS["fade_start"]))
        except Exception:
            data["fade_start"] = DEFAULT_SETTINGS["fade_start"]
        if data["fade_start"] <= 0:
            data["fade_start"] = 1.0
        if data.get("currency") not in ("EUR","USD","GBP"):
            data["currency"] = DEFAULT_SETTINGS["currency"]
        data["timezone"] = validate_timezone(data.get("timezone"))
        return data
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(s: dict):
    with write_lock:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f)

def append_settings_to_ledger(s: dict):
    entry = SettingsEntry(
        kind="settings",
        timestamp=now_iso_in_tz(s.get("timezone", DEFAULT_SETTINGS["timezone"])),
        theme=s.get("theme", DEFAULT_SETTINGS["theme"]),
        fade_start=float(s.get("fade_start", DEFAULT_SETTINGS["fade_start"])),
        currency=s.get("currency", DEFAULT_SETTINGS["currency"]),
        timezone=s.get("timezone", DEFAULT_SETTINGS["timezone"])
    )
    with write_lock:
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.dict(), ensure_ascii=False) + "\n")

def read_ledger_entries() -> List[dict]:
    entries: List[dict] = []
    if not os.path.exists(LEDGER_PATH):
        return entries
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    return entries

def read_movements() -> List[Movement]:
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

# Currency formatting
def format_currency(value: float, currency: str) -> str:
    sign = "-" if value < 0 else ""
    amt = f"{abs(value):.2f}"
    if currency == "USD":
        return f"{sign}${amt}"
    if currency == "GBP":
        return f"{sign}£{amt}"
    return f"{sign}{amt} €"  # EUR

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    guard = ensure_setup_page()
    if guard: return guard

    settings = get_settings()
    rows = read_movements()
    balance = compute_balance(rows)

    # color fade using settings.fade_start
    fade_start = float(settings["fade_start"])
    if balance <= 0:
        hue = 0.0
    elif balance >= fade_start:
        hue = 120.0
    else:
        ratio = max(0.0, min(balance / fade_start, 1.0))
        hue = 120.0 * ratio
    balance_color = f"hsl({hue:.0f}, 70%, 60%)"

    # Currency + tz
    currency = settings["currency"]
    tz_name = settings["timezone"]
    balance_display = format_currency(balance, currency)

    movements_src = [r for r in rows if r.kind == "movement"]
    # sort by parsed datetime desc
    movements_src.sort(key=lambda r: parse_ts(r.timestamp), reverse=True)

    movements = []
    for r in movements_src[:200]:
        movements.append({
            "timestamp_display": format_display_date(r.timestamp, tz_name),
            "action": r.action,
            "amount_display": format_currency(float(r.amount or 0.0), currency),
            "balance_display": format_currency(float(r.resulting_balance or 0.0), currency),
            "description": r.description or ""
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "balance_display": balance_display,
        "balance_color": balance_color,
        "movements": movements,
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

        parsed_any = False
        imported_settings = None
        with write_lock:
            with open(LEDGER_PATH, "w", encoding="utf-8") as f:
                for ln in lines:
                    try:
                        obj = json.loads(ln)
                        k = obj.get("kind")
                        if k == "settings":
                            try:
                                se = SettingsEntry(**obj)
                                imported_settings = {
                                    "theme": se.theme,
                                    "fade_start": float(se.fade_start),
                                    "currency": (se.currency or DEFAULT_SETTINGS["currency"]),
                                    "timezone": validate_timezone(se.timezone)
                                }
                            except Exception:
                                pass
                        else:
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

        if imported_settings:
            s = get_settings()
            s.update(imported_settings)
            s["timezone"] = validate_timezone(s.get("timezone"))
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

        s = get_settings()
        entry = Movement(
            kind="setup",
            timestamp=now_iso_in_tz(s["timezone"]),
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

    s = get_settings()
    entry = Movement(
        kind="movement",
        timestamp=now_iso_in_tz(s["timezone"]),
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

    # Ensure latest settings snapshot (now includes timezone)
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
            s = get_settings()
            reset_entry = Movement(kind="reset", timestamp=now_iso_in_tz(s["timezone"]), note=f"Reset at balance {balance:.2f}")
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
    currency: Literal["EUR","USD","GBP"] = Form(...),
    timezone: str = Form(...),
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
    s["currency"] = currency
    s["timezone"] = validate_timezone(timezone)

    # persist & snapshot
    save_settings(s)
    if is_initialized():
        append_settings_to_ledger(s)

    return RedirectResponse("/settings", 303)

@app.get("/healthz")
async def health():
    return {"status": "ok"}
