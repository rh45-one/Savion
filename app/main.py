from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict, Any
from zoneinfo import ZoneInfo
import os, json, datetime, threading, random, re

APP_NAME = "Savion"
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LEDGER_PATH = os.path.join(DATA_DIR, "ledger.jsonl")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Supported languages ---
SUPPORTED_LANGS = ("en", "es", "fr", "zh", "pt", "ja", "de", "it", "tlh")

# --- English translations (fallback) ---
EN_TRANSLATIONS: Dict[str, str] = {
    "nav_home": "Home",
    "nav_export": "Export",
    "nav_settings": "Settings",
    "nav_reset": "Reset",
    "balance_current": "Current Balance",
    "section_add_withdraw": "Add / Withdraw",
    "form_action": "Action",
    "action_add": "Add",
    "action_withdraw": "Withdraw",
    "form_amount": "Amount",
    "form_description_optional": "Description (optional)",
    "form_submit": "Submit",
    "form_tags": "Tags",
    "section_recent": "Recent Movements",
    "table_date": "Date",
    "table_action": "Action",
    "table_amount": "Amount",
    "table_balance": "Balance",
    "table_description": "Description",
    "table_tags": "Tags",
    "table_empty": "No movements yet.",
    "settings_title": "Settings",
    "settings_theme": "Theme",
    "settings_fade_start": "Fade start (balance where green begins to fade)",
    "settings_currency": "Display currency",
    "currency_eur": "€ Euro",
    "currency_usd": "$ US Dollar",
    "currency_gbp": "£ British Pound",
    "settings_timezone": "Timezone (IANA, e.g., Europe/Madrid)",
    "settings_language": "Language",
    "language_en": "English (EN)",
    "language_es": "Español (ES)",
    "language_fr": "Français (FR)",
    "language_zh": "Chinese (ZH)",
    "language_pt": "Português (PT)",
    "language_ja": "日本語 (JA)",
    "language_de": "Deutsch (DE)",
    "language_it": "Italiano (IT)",
    "language_tlh": "Klingon (TLH)",
    "settings_save": "Save",
    "tz_preview_prefix": "Current time in",
    # Errors
    "error_file_required": "Please choose a ledger file to import.",
    "error_file_empty": "Uploaded file is empty.",
    "error_file_invalid": "File format invalid. Expecting JSON Lines exported by Savion.",
    "error_initial_balance_required": "Please enter an initial balance or choose Import.",
    "error_reset_verification": "Verification failed. Type RESET and solve the math correctly.",
    # Filters
    "filters_title": "Filters",
    "filters_search": "Search",
    "filters_action": "Action",
    "filters_action_all": "All",
    "filters_action_add": "Add only",
    "filters_action_withdraw": "Withdraw only",
    "filters_date_from": "From date",
    "filters_date_to": "To date",
    "filters_amount_min": "Min amount",
    "filters_amount_max": "Max amount",
    "filters_apply": "Apply",
    "filters_clear": "Clear",
    "filters_tags": "Tags",
    # Tags management
    "settings_tags_group": "Tag types",
    "settings_tags_help": "Add/remove tags to use on movements. Pick a color for each.",
    "settings_tag_name": "Name",
    "settings_tag_color": "Color",
    "settings_add_tag": "Add tag type",
    "settings_remove": "Remove",
}

# External translations (non-English)
TRANSLATIONS_PATH = os.path.join(BASE_DIR, "translations.json")
_EXTERNAL_TRANSLATIONS: Dict[str, Dict[str, str]] = {}

def _load_external_translations() -> Dict[str, Dict[str, str]]:
    try:
        with open(TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            out: Dict[str, Dict[str, str]] = {}
            for lang, bundle in data.items():
                if isinstance(bundle, dict):
                    out[lang] = {str(k): str(v) for k, v in bundle.items()}
            return out
    except Exception:
        pass
    return {}
_EXTERNAL_TRANSLATIONS = _load_external_translations()

def t_for(lang: str) -> Dict[str, str]:
    lang = (lang or "en").lower()
    if lang == "en": return EN_TRANSLATIONS
    bundle = _EXTERNAL_TRANSLATIONS.get(lang)
    if not bundle: return EN_TRANSLATIONS
    merged = EN_TRANSLATIONS.copy()
    merged.update(bundle)
    return merged

# --- Default settings (extended with tag types) ---
DEFAULT_SETTINGS = {
    "theme": "dark",            # "dark" | "light" | "dracula" | "winclassic" | "system1"
    "fade_start": 1000.0,
    "currency": "EUR",
    "timezone": "Europe/Madrid",
    "language": "en",
    "tag_types": []             # list of {"name": str, "color": "#RRGGBB"}
}

app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
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
    tags: Optional[List[str]] = None

class SettingsEntry(BaseModel):
    kind: Literal["settings"]
    timestamp: str
    theme: Literal["dark","light","dracula","winclassic","system1"]
    fade_start: float
    currency: Optional[Literal["EUR","USD","GBP"]] = None
    timezone: Optional[str] = None
    language: Optional[Literal["en","es","fr","zh","pt","ja","de","it","tlh"]] = None
    tag_types: Optional[List[Dict[str, Any]]] = None

# --- Helpers ---
def validate_timezone(tz: Optional[str]) -> str:
    name = (tz or "").strip() or DEFAULT_SETTINGS["timezone"]
    try:
        ZoneInfo(name)
        return name
    except Exception:
        return DEFAULT_SETTINGS["timezone"]

def validate_language(lang: Optional[str]) -> str:
    code = (lang or "").lower()
    return code if code in SUPPORTED_LANGS else "en"

def now_iso_in_tz(tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = datetime.timezone.utc
    return datetime.datetime.now(tz=tz).isoformat()

def parse_ts(ts: str) -> datetime.datetime:
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

def format_display_date(ts: str, tz_name: str) -> str:
    dt = parse_ts(ts)
    try:
        tz = ZoneInfo(tz_name)
        dt = dt.astimezone(tz)
    except Exception:
        pass
    return dt.strftime("%d/%m/%Y %H:%M")

def format_now_preview(tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = datetime.timezone.utc
    dt = datetime.datetime.now(tz=tz)
    return dt.strftime("%d/%m/%Y %H:%M")

HEX_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")

def clean_tag_types(tt: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(tt, list):
        return out
    seen = set()
    for item in tt:
        name = str(item.get("name", "")).strip()
        color = str(item.get("color", "")).strip()
        if not name:
            continue
        if not HEX_RE.match(color):
            color = "#777777"
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "color": color})
    return out

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
        if data.get("theme") not in ("dark","light","dracula","winclassic","system1"):
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
        data["language"] = validate_language(data.get("language"))
        data["tag_types"] = clean_tag_types(data.get("tag_types", []))
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
        timezone=s.get("timezone", DEFAULT_SETTINGS["timezone"]),
        language=s.get("language", DEFAULT_SETTINGS["language"]),
        tag_types=s.get("tag_types", []),
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

def format_currency(value: float, currency: str) -> str:
    sign = "-" if value < 0 else ""
    amt = f"{abs(value):.2f}"
    if currency == "USD":
        return f"{sign}${amt}"
    if currency == "GBP":
        return f"{sign}£{amt}"
    return f"{sign}{amt} €"

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    guard = ensure_setup_page()
    if guard: return guard

    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)

    rows = read_movements()
    balance = compute_balance(rows)

    fade_start = float(settings["fade_start"])
    if balance <= 0:
        hue = 0.0
    elif balance >= fade_start:
        hue = 120.0
    else:
        ratio = max(0.0, min(balance / fade_start, 1.0))
        hue = 120.0 * ratio
    balance_color = f"hsl({hue:.0f}, 70%, 60%)"

    currency = settings["currency"]
    tz_name = settings["timezone"]
    balance_display = format_currency(balance, currency)

    # Filters
    qp = request.query_params
    q = (qp.get("q") or "").strip()
    action_filter = (qp.get("action") or "all").lower()
    start_str = (qp.get("start") or "").strip()
    end_str = (qp.get("end") or "").strip()
    min_str = (qp.get("min") or "").strip()
    max_str = (qp.get("max") or "").strip()
    selected_tags = qp.getlist("tags")
    selected_tags = [s for s in (selected_tags or []) if s.strip()]
    filters_open = any([q, action_filter in ("add", "withdraw"), start_str, end_str, min_str, max_str, selected_tags])

    # Parse filters
    start_date = end_date = None
    try:
        if start_str: start_date = datetime.date.fromisoformat(start_str)
        if end_str:   end_date = datetime.date.fromisoformat(end_str)
    except Exception:
        pass

    min_amount = max_amount = None
    try:
        if min_str: min_amount = float(min_str)
    except Exception:
        pass
    try:
        if max_str: max_amount = float(max_str)
    except Exception:
        pass

    tag_types = settings.get("tag_types", [])
    tag_color_map = { (t["name"] or "").strip().lower(): t.get("color", "#777777") for t in tag_types }

    movements_src = [r for r in rows if r.kind == "movement"]

    def passes_filters(m: Movement) -> bool:
        if action_filter in ("add","withdraw") and (m.action or "") != action_filter:
            return False
        m_dt = parse_ts(m.timestamp)
        try:
            m_dt = m_dt.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
        m_d = m_dt.date()
        if start_date and m_d < start_date: return False
        if end_date and m_d > end_date: return False
        m_amt = float(m.amount or 0.0)
        if min_amount is not None and m_amt < min_amount: return False
        if max_amount is not None and m_amt > max_amount: return False
        if q:
            ql = q.lower()
            hay = f"{m.description or ''} {m.action or ''} {format_display_date(m.timestamp, tz_name)} {' '.join(m.tags or [])}".lower()
            if ql not in hay: return False
        if selected_tags:
            mtags = [s.lower() for s in (m.tags or [])]
            # ANY of selected tags:
            if not any(tag.lower() in mtags for tag in selected_tags):
                return False
        return True

    filtered = [m for m in movements_src if passes_filters(m)]
    filtered.sort(key=lambda r: parse_ts(r.timestamp), reverse=True)

    movements = []
    for r in filtered[:200]:
        action_label = t["action_add"] if r.action == "add" else t["action_withdraw"]
        tags_display = []
        for tag in (r.tags or []):
            key = (tag or "").strip().lower()
            color = tag_color_map.get(key, "#777777")
            tags_display.append({"name": tag, "color": color})
        movements.append({
            "timestamp_display": format_display_date(r.timestamp, tz_name),
            "action_display": action_label,
            "amount_display": format_currency(float(r.amount or 0.0), currency),
            "balance_display": format_currency(float(r.resulting_balance or 0.0), currency),
            "description": r.description or "",
            "tags": tags_display
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "balance_display": balance_display,
        "balance_color": balance_color,
        "movements": movements,
        "app_name": APP_NAME,
        "theme": settings["theme"],
        "t": t,
        "lang": lang,
        "q": q,
        "action_filter": action_filter,
        "start_str": start_str,
        "end_str": end_str,
        "min_str": min_str,
        "max_str": max_str,
        "filters_open": filters_open,
        "tag_types": tag_types,
        "selected_tags": selected_tags,
    })

@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if is_initialized():
        return RedirectResponse("/", 303)
    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "app_name": APP_NAME,
        "theme": settings["theme"],
        "t": t,
        "lang": lang
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

    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)

    def render_error(msg: str, status_code: int = 400):
        return templates.TemplateResponse("setup.html", {
            "request": request,
            "error": msg,
            "app_name": APP_NAME,
            "theme": settings["theme"],
            "t": t, "lang": lang
        }, status_code=status_code)

    if setup_mode == "import":
        if not ledger_file:
            return render_error(t["error_file_required"])
        content = await ledger_file.read()
        text = content.decode("utf-8", errors="ignore")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return render_error(t["error_file_empty"])

        parsed_any = False
        imported_settings: Optional[Dict[str, Any]] = None
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
                                    "timezone": validate_timezone(se.timezone),
                                    "language": validate_language(se.language),
                                    "tag_types": clean_tag_types(se.tag_types or [])
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
            return render_error(t["error_file_invalid"])

        if imported_settings:
            s = get_settings()
            s.update(imported_settings)
            s["timezone"] = validate_timezone(s.get("timezone"))
            s["language"] = validate_language(s.get("language"))
            s["tag_types"] = clean_tag_types(s.get("tag_types", []))
            save_settings(s)

        return RedirectResponse("/", 303)

    else:
        if initial_balance is None:
            return render_error(t["error_initial_balance_required"])

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
    description: Optional[str] = Form(default=""),
    tags: List[str] = Form(default=[])
):
    guard = ensure_setup_page()
    if guard: return guard

    rows = read_movements()
    balance = compute_balance(rows)

    delta = float(amount) if action == "add" else -float(amount)
    new_balance = round(balance + delta, 2)

    # Normalize tags (trim + dedupe)
    norm_tags: List[str] = []
    seen = set()
    for tname in tags or []:
        name = (tname or "").strip()
        if not name: continue
        key = name.lower()
        if key in seen: continue
        seen.add(key)
        norm_tags.append(name)

    s = get_settings()
    entry = Movement(
        kind="movement",
        timestamp=now_iso_in_tz(s["timezone"]),
        action=action,
        amount=float(amount),
        delta=delta,
        description=description or "",
        resulting_balance=new_balance,
        tags=norm_tags
    )
    append_entry(entry)
    return RedirectResponse("/", 303)

@app.get("/export")
async def export_ledger():
    guard = ensure_setup_page()
    if guard: return guard
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
    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)
    return templates.TemplateResponse("reset.html", {
        "request": request, "a": a, "b": b, "op": op,
        "app_name": APP_NAME, "theme": settings["theme"], "t": t, "lang": lang
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

    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)

    expected = a + b if op == "+" else a - b
    if confirm_text.strip().upper() != "RESET" or math_answer != expected:
        return templates.TemplateResponse("reset.html", {
            "request": request,
            "error": t["error_reset_verification"],
            "a": random.randint(20,60),
            "b": random.randint(5,15),
            "op": random.choice(["+","-"]),
            "app_name": APP_NAME,
            "theme": settings["theme"],
            "t": t, "lang": lang
        }, status_code=400)

    if os.path.exists(LEDGER_PATH):
        try:
            rows = read_movements()
            balance = compute_balance(rows)
            reset_entry = Movement(kind="reset", timestamp=now_iso_in_tz(settings["timezone"]), note=f"Reset at balance {balance:.2f}")
            append_entry(reset_entry)
        except Exception:
            pass
        with write_lock:
            try:
                os.remove(LEDGER_PATH)
            except FileNotFoundError:
                pass

    save_settings(DEFAULT_SETTINGS.copy())
    return RedirectResponse("/setup", 303)

@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request):
    s = get_settings()
    lang = s["language"]
    t = t_for(lang)
    tz_preview = format_now_preview(s["timezone"])
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "app_name": APP_NAME,
        "theme": s["theme"],
        "settings": s,
        "tz_preview": tz_preview,
        "t": t,
        "lang": lang
    })

@app.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    theme: Literal["dark","light","dracula","winclassic","system1"] = Form(...),
    fade_start: float = Form(...),
    currency: Literal["EUR","USD","GBP"] = Form(...),
    timezone: str = Form(...),
    language: Literal["en","es","fr","zh","pt","ja","de","it","tlh"] = Form(...),
    tag_name: List[str] = Form(default=[]),
    tag_color: List[str] = Form(default=[]),
):
    try:
        fs = float(fade_start)
    except Exception:
        fs = DEFAULT_SETTINGS["fade_start"]
    if fs <= 0:
        fs = 1.0

    # Build tag_types from paired arrays
    tt: List[Dict[str, str]] = []
    for i in range(max(len(tag_name), len(tag_color))):
        name = (tag_name[i] if i < len(tag_name) else "").strip()
        color = (tag_color[i] if i < len(tag_color) else "").strip()
        if not name:
            continue
        if not HEX_RE.match(color):
            color = "#777777"
        tt.append({"name": name, "color": color})
    tt = clean_tag_types(tt)

    s = get_settings()
    s["theme"] = theme
    s["fade_start"] = fs
    s["currency"] = currency
    s["timezone"] = validate_timezone(timezone)
    s["language"] = validate_language(language)
    s["tag_types"] = tt

    save_settings(s)
    if is_initialized():
        append_settings_to_ledger(s)
    return RedirectResponse("/settings", 303)

@app.get("/healthz")
async def health():
    return {"status": "ok"}
