from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Literal, Dict, Any, Set
from zoneinfo import ZoneInfo
import os, json, datetime, threading, random, re

APP_NAME = "Savion"
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("DATA_DIR", "/data")
LEDGER_PATH = os.path.join(DATA_DIR, "ledger.jsonl")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
os.makedirs(DATA_DIR, exist_ok=True)

# --- Supported languages ---
SUPPORTED_LANGS = ("en", "es", "fr", "zh", "pt", "ja", "de", "it")
SYSTEM_TAG_VALUE = "__balance_adjust__"
SYSTEM_TAG_VALUE_LOWER = SYSTEM_TAG_VALUE.lower()
SYSTEM_TAG_COLOR = "#9C89FF"

# --- English translations (fallback) ---
EN_TRANSLATIONS: Dict[str, str] = {
    "nav_home": "Home",
    "nav_summary": "Summary",
    "nav_export": "Export",
    "nav_settings": "Settings",
    "nav_reset": "Reset",

    "nav_open_menu": "Open menu",
    "nav_close_menu": "Close menu",

    "balance_current": "Current Balance",
    "section_add_withdraw": "Add / Withdraw",
    "form_action": "Action",
    "system_tag_balance_adjust": "Balance adjust",
    "action_select_placeholder": "Select an action",
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

    # Recent movements display count control
    "recent_display_label": "Show",
    "recent_display_all": "All",

    "settings_title": "Settings",
    "settings_theme": "Theme",
    "settings_fade_start": "Fade start (balance where green begins to fade)",
    "settings_currency": "Display currency",
    "currency_eur": "€ Euro",
    "currency_usd": "$ US Dollar",
    "currency_gbp": "£ British Pound",
    "settings_timezone": "Timezone (IANA, e.g., Europe/London)",
    "settings_language": "Language",
    "language_en": "English (EN)",
    "language_es": "Español (ES)",
    "language_fr": "Français (FR)",
    "language_zh": "Chinese (ZH)",
    "language_pt": "Português (PT)",
    "language_ja": "日本語 (JA)",
    "language_de": "Deutsch (DE)",
    "language_it": "Italiano (IT)",
    "settings_save": "Save",
    "tz_preview_prefix": "Current time in",

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

    # Tags management (Settings)
    "settings_tags_group": "Tag types",
    "settings_tags_help": "Add/remove tags to use on movements. Pick a color for each.",
    "settings_tag_name": "Name",
    "settings_tag_color": "Color",
    "settings_add_tag": "Add tag type",
    "settings_remove": "Remove",

    # Editing UI
    "edit": "Edit",
    "save": "Save",
    "cancel": "Cancel",
    "edit_description": "Edit description",
    "edit_tags": "Edit tags",
    "delete": "Delete",
    "delete_confirm": "Confirm delete",

    # Extra UI copy
    "no_tags_defined": "No tags defined yet — add some in Settings.",
    "placeholder_example_tag": "e.g., Groceries",
    "error_invalid_timezone": "⚠️ Invalid timezone.",
    "error_action_required": "Please select whether this is an add or withdraw.",

    # Setup page
    "setup_title": "Setup",
    "setup_fresh_title": "Fresh setup",
    "setup_fresh_subtitle": "Start a new ledger with an initial balance.",
    "setup_initial_label": "Initial balance",
    "setup_create_btn": "Create",
    "setup_import_title": "Import existing ledger",
    "setup_import_subtitle": "Choose an exported file to continue where you left off.",
    "setup_ledger_file_label": "Ledger file",
    "setup_import_btn": "Import",

    # Reset page
    "reset_title": "Reset Savion",
    "reset_warning": "This will erase all data. We recommend exporting your ledger before continuing.",
    "reset_type_label": "Type RESET to confirm",
    "reset_math_label": "Solve",
    "reset_button": "Erase everything",
    
    # NEW granular error copy
    "reset_error_word": "Type “RESET” exactly.",
    "reset_error_math": "The math answer is incorrect.",
    "reset_error_math_empty": "Enter the result of the equation.",

    # Footer
    "footer_tagline": "Simple, local-first money tracker.",

    # Errors
    "error_file_required": "Please choose a ledger file to import.",
    "error_file_empty": "Uploaded file is empty.",
    "error_file_invalid": "File format invalid. Expecting JSON Lines exported by Savion.",
    "error_initial_balance_required": "Please enter an initial balance or choose Import.",
    "error_reset_verification": "Verification failed. Type RESET and solve the math correctly.",

    # Summary page
    "summary_title": "Monthly Summaries",
    "summary_month": "Month",
    "summary_total_change": "Net change",
    "summary_entries": "Entries",
    "summary_in_progress": "In progress",
    "summary_income": "Income",
    "summary_expenses": "Expenses",
}

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

# --- Default settings ---
DEFAULT_SETTINGS = {
    "theme": "dark",            # "dark" | "light" | "dracula" | "winclassic" | "system1"
    "fade_start": 1000.0,
    "currency": "EUR",
    "timezone": "Europe/London",
    "language": "en",
    "tag_types": [],            # list of {"name": str, "color": "#RRGGBB"}
    "show_balance": True        # home-page toggle to show/hide total balance
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
    language: Optional[Literal["en","es","fr","zh","pt","ja","de","it"]] = None
    tag_types: Optional[List[Dict[str, Any]]] = None
    show_balance: Optional[bool] = None

class EditEntry(BaseModel):
    """Non-destructive edits for movements (description/tags only)."""
    kind: Literal["edit"]
    timestamp: str            # when the edit happened
    target_ts: str            # identifies the movement by its original timestamp
    new_description: Optional[str] = None
    new_tags: Optional[List[str]] = None

class DeleteEntry(BaseModel):
    """Soft-delete a movement by timestamp. The original movement remains in ledger for audit, but is ignored in UI and balance calc."""
    kind: Literal["delete"]
    timestamp: str            # when the delete happened
    target_ts: str            # movement timestamp being deleted

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

def year_month_from_ts(ts: str, tz_name: str) -> tuple[int, int]:
    dt = parse_ts(ts)
    try:
        tz = ZoneInfo(tz_name)
        dt = dt.astimezone(tz)
    except Exception:
        pass
    return dt.year, dt.month

def group_movements_by_month(movs: List[Movement], tz_name: str) -> List[Dict[str, Any]]:
    """Group movement entries by calendar month/year and sum their deltas.
    Returns a list of dicts: {year, month, total_change: float, count: int, is_in_progress: bool}
    Sorted descending by (year, month).
    """
    groups: Dict[tuple[int,int], Dict[str, Any]] = {}
    for m in movs:
        if m.kind != "movement":
            continue
        y, mo = year_month_from_ts(m.timestamp, tz_name)
        key = (y, mo)
        g = groups.get(key)
        if not g:
            g = {"year": y, "month": mo, "total_change": 0.0, "count": 0}
            groups[key] = g
        g["total_change"] += float(m.delta or 0.0)
        g["count"] += 1

    # Determine current month/year in tz
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = datetime.timezone.utc
    now_dt = datetime.datetime.now(tz=tz)
    cur_y, cur_m = now_dt.year, now_dt.month

    out = []
    for (y, mo), g in groups.items():
        gcopy = g.copy()
        gcopy["total_change"] = round(float(gcopy["total_change"]), 2)
        gcopy["is_in_progress"] = (y == cur_y and mo == cur_m)
        out.append(gcopy)
    out.sort(key=lambda d: (d["year"], d["month"]), reverse=True)
    return out

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

def merged_tag_types(settings_tags: List[Dict[str, str]], t: Dict[str, str]) -> List[Dict[str, str]]:
    cleaned = clean_tag_types(settings_tags)
    enriched: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for tag in cleaned:
        name = (tag.get("name") or "").strip()
        color = (tag.get("color") or "").strip() or "#777777"
        if not name:
            continue
        key = name.lower()
        if key == SYSTEM_TAG_VALUE_LOWER:
            # Avoid collisions with manually created tag with same internal name
            continue
        enriched.append({
            "name": name,
            "color": color,
            "label": name,
            "is_system": False,
        })
        seen.add(key)

    if SYSTEM_TAG_VALUE_LOWER not in seen:
        enriched.append({
            "name": SYSTEM_TAG_VALUE,
            "color": SYSTEM_TAG_COLOR,
            "label": t.get("system_tag_balance_adjust", "Balance adjust"),
            "is_system": True,
        })

    return enriched

def canonical_tag_value(tag: Optional[str]) -> str:
    return (tag or "").strip()

def is_system_balance_tag(tag: Optional[str]) -> bool:
    return canonical_tag_value(tag).lower() == SYSTEM_TAG_VALUE_LOWER

def has_system_balance_tag(tags: Optional[List[str]]) -> bool:
    return any(is_system_balance_tag(tag) for tag in (tags or []))

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
        # Coerce show_balance to bool
        data["show_balance"] = bool(data.get("show_balance", True))
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
        show_balance=bool(s.get("show_balance", True)),
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

def read_edits() -> List[EditEntry]:
    edits: List[EditEntry] = []
    for obj in read_ledger_entries():
        if obj.get("kind") == "edit":
            try:
                edits.append(EditEntry(**obj))
            except Exception:
                continue
    return edits

def read_deletes() -> List[DeleteEntry]:
    deleted: List[DeleteEntry] = []
    for obj in read_ledger_entries():
        if obj.get("kind") == "delete":
            try:
                deleted.append(DeleteEntry(**obj))
            except Exception:
                continue
    return deleted

def compute_balance(rows: List[Movement]) -> float:
    # Legacy helper kept for internal calls; current UI uses deletion-aware compute below.
    balance = 0.0
    for r in rows:
        if r.kind == "setup" and r.initial_balance is not None:
            balance = float(r.initial_balance)
        elif r.kind == "movement" and r.delta is not None:
            balance += float(r.delta)
    return round(balance, 2)

def compute_balance_and_map(rows: List[Movement], deleted_ts: set[str]) -> tuple[float, Dict[str, float]]:
    """Return final balance and a map of resulting_balance per movement timestamp, skipping deleted movements."""
    balance = 0.0
    per_move_balance: Dict[str, float] = {}
    for r in rows:
        if r.kind == "setup" and r.initial_balance is not None:
            balance = float(r.initial_balance)
        elif r.kind == "movement" and r.delta is not None:
            if r.timestamp in deleted_ts:
                continue
            balance += float(r.delta)
            per_move_balance[r.timestamp] = round(balance, 2)
    return round(balance, 2), per_move_balance

def append_entry(entry: BaseModel):
    with write_lock:
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.dict(), ensure_ascii=False) + "\n")

def ensure_setup_page():
    if not is_initialized():
        return RedirectResponse(url="/setup", status_code=303)
    return None

def format_currency(value: float, currency: str) -> str:
    sign = "-" if value < 0 else ""
    # Use thousands separators, e.g., 1000 -> 1,000.00
    amt = f"{abs(value):,.2f}"
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
    # Build deletion set
    deleted_ts_set = {d.target_ts for d in read_deletes()}
    balance, per_move_balance = compute_balance_and_map(rows, deleted_ts_set)

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
    # Obfuscated balance retains currency symbol only
    if currency == "USD":
        balance_obfuscated = "$\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    elif currency == "GBP":
        balance_obfuscated = "£\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    else:  # EUR default
        balance_obfuscated = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022 \u20AC"

    # Build overrides from edits (last write wins by file order)
    overrides: Dict[str, Dict[str, Any]] = {}
    for e in read_edits():
        overrides[e.target_ts] = {
            "description": (e.new_description if e.new_description is not None else None),
            "tags": (e.new_tags if e.new_tags is not None else None)
        }

    # Filters
    qp = request.query_params
    q = (qp.get("q") or "").strip()
    action_filter = (qp.get("action") or "all").lower()
    start_str = (qp.get("start") or "").strip()
    end_str = (qp.get("end") or "").strip()
    min_str = (qp.get("min") or "").strip()
    max_str = (qp.get("max") or "").strip()
    selected_tags_raw = qp.getlist("tags")
    selected_tags = [canonical_tag_value(s) for s in (selected_tags_raw or []) if canonical_tag_value(s)]
    filters_open = any([q, action_filter in ("add", "withdraw"), start_str, end_str, min_str, max_str, selected_tags])

    # Movements display limit
    limit_raw = (qp.get("limit") or "50").strip().lower()
    limit: Optional[int]
    if limit_raw in ("all", "*"):
        limit = None
    else:
        try:
            limit_val = int(limit_raw)
            if limit_val <= 0:
                limit = 50
            else:
                limit = limit_val
        except Exception:
            limit = 50

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

    tag_types = merged_tag_types(settings.get("tag_types", []), t)
    tag_meta_map: Dict[str, Dict[str, str]] = {}
    for tag in tag_types:
        key = canonical_tag_value(tag.get("name")).lower()
        if not key:
            continue
        tag_meta_map[key] = {
            "color": tag.get("color", "#777777"),
            "label": tag.get("label") or canonical_tag_value(tag.get("name")),
        }

    base_movs = [r for r in rows if r.kind == "movement" and r.timestamp not in deleted_ts_set]

    def apply_override(m: Movement) -> Movement:
        ov = overrides.get(m.timestamp)
        if not ov:
            return m
        # make a shallow copy with patched fields
        md = m.dict()
        if ov.get("description") is not None:
            md["description"] = ov["description"]
        if ov.get("tags") is not None:
            md["tags"] = ov["tags"]
        try:
            return Movement(**md)
        except Exception:
            return m

    # Apply overrides before filtering
    movs = [apply_override(m) for m in base_movs]

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
            tags_str = " ".join(m.tags or [])
            hay = f"{m.description or ''} {m.action or ''} {format_display_date(m.timestamp, tz_name)} {tags_str}".lower()
            if ql not in hay: return False
        if selected_tags:
            mtags = [s.lower() for s in (m.tags or [])]
            if not any(tag.lower() in mtags for tag in selected_tags):
                return False
        return True

    filtered = [m for m in movs if passes_filters(m)]
    filtered.sort(key=lambda r: parse_ts(r.timestamp), reverse=True)

    movements = []
    # Apply limit (default 50). Hard ceil safety: 10000 to avoid runaway rendering.
    slice_end = None if limit is None else min(limit, 10000)
    display_rows = filtered if slice_end is None else filtered[:slice_end]
    for r in display_rows:
        action_label = t["action_add"] if r.action == "add" else t["action_withdraw"]
        tags_display = []
        tags_names: List[str] = []
        for tag in (r.tags or []):
            raw = canonical_tag_value(tag)
            if not raw:
                continue
            tags_names.append(raw)
            meta = tag_meta_map.get(raw.lower())
            label = (meta.get("label") if meta else None) or raw
            color = (meta.get("color") if meta else None) or "#777777"
            tags_display.append({"name": label, "color": color})
        movements.append({
            "ts_raw": r.timestamp,  # identifier for edit target
            "timestamp_display": format_display_date(r.timestamp, tz_name),
            "action_display": action_label,
            "amount_display": format_currency(float(r.amount or 0.0), currency),
            "balance_display": format_currency(float(per_move_balance.get(r.timestamp, r.resulting_balance or 0.0)), currency),
            "description": r.description or "",
            "tags": tags_display,
            "tags_names": tags_names
        })

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "balance_display": balance_display,
            "balance_color": balance_color,
            "show_balance": settings.get("show_balance", True),
            "balance_obfuscated": balance_obfuscated,
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
            "limit_selected": ("all" if limit is None else str(limit)),
        },
    )

@app.post("/toggle-balance")
async def toggle_balance():
    s = get_settings()
    cur = bool(s.get("show_balance", True))
    s["show_balance"] = not cur
    save_settings(s)
    # Append to ledger so it persists across exports too
    if is_initialized():
        append_settings_to_ledger(s)
    return RedirectResponse("/", 303)

@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if is_initialized():
        return RedirectResponse("/", 303)
    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={
            "app_name": APP_NAME,
            "theme": settings["theme"],
            "t": t,
            "lang": lang,
        },
    )

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
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            context={
                "error": msg,
                "app_name": APP_NAME,
                "theme": settings["theme"],
                "t": t,
                "lang": lang,
            },
            status_code=status_code,
        )

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
                                    "tag_types": clean_tag_types(se.tag_types or []),
                                    "show_balance": bool(se.show_balance) if (se.show_balance is not None) else True,
                                }
                            except Exception:
                                pass
                        else:
                            # Validate movements/edits/deletes structurally
                            if k == "edit":
                                EditEntry(**obj)
                            elif k == "delete":
                                DeleteEntry(**obj)
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
        name = canonical_tag_value(tname)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        if key == SYSTEM_TAG_VALUE_LOWER:
            name = SYSTEM_TAG_VALUE
            key = SYSTEM_TAG_VALUE_LOWER
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

@app.post("/movement/edit")
async def edit_movement(
    target_ts: str = Form(...),
    new_description: Optional[str] = Form(default=None),
    tags: List[str] = Form(default=[])
):
    """Append a non-destructive edit entry for an existing movement."""
    guard = ensure_setup_page()
    if guard: return guard

    s = get_settings()
    # Normalize tags
    norm_tags: List[str] = []
    seen = set()
    for tname in tags or []:
        nm = canonical_tag_value(tname)
        if not nm:
            continue
        key = nm.lower()
        if key in seen:
            continue
        if key == SYSTEM_TAG_VALUE_LOWER:
            nm = SYSTEM_TAG_VALUE
            key = SYSTEM_TAG_VALUE_LOWER
        seen.add(key)
        norm_tags.append(nm)

    entry = EditEntry(
        kind="edit",
        timestamp=now_iso_in_tz(s["timezone"]),
        target_ts=target_ts,
        new_description=(new_description or ""),
        new_tags=norm_tags
    )
    append_entry(entry)
    return RedirectResponse("/", 303)

@app.post("/movement/delete")
async def delete_movement(target_ts: str = Form(...)):
    """Append a delete entry for an existing movement to invert its effect from balances and listings."""
    guard = ensure_setup_page()
    if guard: return guard

    # Validate that target exists and is a movement
    rows = read_movements()
    target = next((m for m in rows if m.kind == "movement" and m.timestamp == target_ts), None)
    if not target:
        return RedirectResponse("/", 303)

    # Ensure not already deleted
    if any(d.target_ts == target_ts for d in read_deletes()):
        return RedirectResponse("/", 303)

    s = get_settings()
    entry = DeleteEntry(
        kind="delete",
        timestamp=now_iso_in_tz(s["timezone"]),
        target_ts=target_ts,
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
    return templates.TemplateResponse(
        request=request,
        name="reset.html",
        context={
            "a": a,
            "b": b,
            "op": op,
            "app_name": APP_NAME,
            "theme": settings["theme"],
            "t": t,
            "lang": lang,
        },
    )

@app.post("/reset", response_class=HTMLResponse)
async def reset_post(
    request: Request,
    confirm_text: str = Form(...),
    a: int = Form(...),
    b: int = Form(...),
    op: str = Form(...),
    math_answer: Optional[str] = Form(None),
):
    guard = ensure_setup_page()
    if guard: return guard

    settings = get_settings()
    lang = settings["language"]
    t = t_for(lang)

    # Compute expected answer
    expected = a + b if op == "+" else a - b

    # Normalize inputs
    word_ok = (confirm_text or "").strip().upper() == "RESET"
    math_str = (math_answer or "").strip()
    try:
        ans = int(math_str) if math_str != "" else None
    except Exception:
        ans = None
    math_ok = (ans is not None) and (ans == expected)

    # Collect errors (granular)
    errors: list[str] = []
    confirm_error = ""
    math_error = ""
    if not word_ok:
        msg = t.get("reset_error_word", "Type “RESET” exactly.")
        errors.append(msg)
        confirm_error = msg
    if not math_ok:
        if ans is None:
            msg = t.get("reset_error_math_empty", "Enter the result of the equation.")
        else:
            msg = t.get("reset_error_math", "The math answer is incorrect.")
        errors.append(msg)
        math_error = msg

    if errors:
        # Re-render SAME challenge to allow user to fix inputs; keep their values
        return templates.TemplateResponse(
            request=request,
            name="reset.html",
            context={
                "error": " ".join(errors),  # page-level alert via base.html
                "a": a,
                "b": b,
                "op": op,
                "confirm_text": confirm_text,
                "math_answer": math_str,
                "confirm_error": confirm_error,
                "math_error": math_error,
                "app_name": APP_NAME,
                "theme": settings["theme"],
                "t": t,
                "lang": lang,
            },
            status_code=400,
        )

    # Proceed with destructive reset
    if os.path.exists(LEDGER_PATH):
        try:
            rows = read_movements()
            balance = compute_balance(rows)
            reset_entry = Movement(
                kind="reset",
                timestamp=now_iso_in_tz(settings["timezone"]),
                note=f"Reset at balance {balance:.2f}",
            )
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
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "app_name": APP_NAME,
            "theme": s["theme"],
            "settings": s,
            "tz_preview": tz_preview,
            "t": t,
            "lang": lang,
        },
    )

@app.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    theme: Literal["dark","light","dracula","winclassic","system1"] = Form(...),
    fade_start: float = Form(...),
    currency: Literal["EUR","USD","GBP"] = Form(...),
    timezone: str = Form(...),
    language: Literal["en","es","fr","zh","pt","ja","de","it"] = Form(...),
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

@app.get("/summary", response_class=HTMLResponse)
async def summary_get(request: Request):
    guard = ensure_setup_page()
    if guard: return guard

    s = get_settings()
    lang = s["language"]
    t = t_for(lang)
    currency = s["currency"]
    tz_name = s["timezone"]

    rows = read_movements()
    deleted_ts = {d.target_ts for d in read_deletes()}
    movs = [m for m in rows if m.kind == "movement" and m.timestamp not in deleted_ts]
    groups = group_movements_by_month(movs, tz_name)

    # Prepare tag color map
    tag_types = merged_tag_types(s.get("tag_types", []), t)
    tag_meta_map: Dict[str, Dict[str, str]] = {}
    for tag in tag_types:
        key = canonical_tag_value(tag.get("name")).lower()
        if not key:
            continue
        tag_meta_map[key] = {
            "color": tag.get("color", "#777777"),
            "label": tag.get("label") or canonical_tag_value(tag.get("name")),
        }

    # Helper for month label like "October 2025"
    def month_label(y: int, m: int) -> str:
        try:
            d = datetime.date(y, m, 1)
            return d.strftime("%B %Y")
        except Exception:
            return f"{y}-{m:02d}"

    # Build mapping from (y,m) to displayed movement rows
    grouped_movs: Dict[tuple[int,int], List[Dict[str, Any]]] = {}
    for m in movs:
        y, mo = year_month_from_ts(m.timestamp, tz_name)
        key = (y, mo)
        lst = grouped_movs.get(key)
        if lst is None:
            lst = []
            grouped_movs[key] = lst
        action_label = t["action_add"] if m.action == "add" else t["action_withdraw"]
        tags_display = []
        raw_tags: List[str] = []
        for tag in (m.tags or []):
            raw = canonical_tag_value(tag)
            if not raw:
                continue
            raw_tags.append(raw)
            meta = tag_meta_map.get(raw.lower())
            label = (meta.get("label") if meta else None) or raw
            color = (meta.get("color") if meta else None) or "#777777"
            tags_display.append({"name": label, "color": color})
        lst.append({
            "ts_raw": m.timestamp,
            "timestamp_display": format_display_date(m.timestamp, tz_name),
            "action_display": action_label,
            "action": (m.action or ""),
            "amount_display": format_currency(float(m.amount or 0.0), currency),
            "amount_value": float(m.amount or 0.0),
            "description": m.description or "",
            "tags": tags_display,
            "tags_raw": raw_tags,
        })

    display_groups = []
    for g in groups:
        key = (g["year"], g["month"])
        key_str = f"{g['year']}-{g['month']:02d}"
        month_movs = grouped_movs.get(key, [])
        summary_movs = [r for r in month_movs if not has_system_balance_tag(r.get("tags_raw"))]

        def net_amount(row: Dict[str, Any]) -> float:
            amt = float(row.get("amount_value", 0.0))
            return -amt if row.get("action") == "withdraw" else amt

        total_change_val = round(sum(net_amount(r) for r in summary_movs), 2)
        # Compute monthly income (adds) and expenses (withdrawals) as positive sums
        total_income_val = round(sum(
            r.get("amount_value", 0.0)
            for r in summary_movs
            if r.get("action") == "add"
        ), 2)
        total_expenses_val = round(sum(
            r.get("amount_value", 0.0)
            for r in summary_movs
            if r.get("action") == "withdraw"
        ), 2)
        display_groups.append({
            "year": g["year"],
            "month": g["month"],
            "key": key_str,
            "label": month_label(g["year"], g["month"]),
            "count": g["count"],
            "total_change": total_change_val,
            "total_change_display": format_currency(total_change_val, currency),
            "is_in_progress": g["is_in_progress"],
            "movements": month_movs,
            "total_income": total_income_val,
            "total_expenses": total_expenses_val,
            "total_income_display": format_currency(total_income_val, currency),
            "total_expenses_display": format_currency(total_expenses_val, currency),
        })

    return templates.TemplateResponse(
        request=request,
        name="summary.html",
        context={
            "app_name": APP_NAME,
            "theme": s["theme"],
            "t": t,
            "lang": lang,
            "groups": display_groups,
        },
    )

@app.get("/healthz")
async def health():
    return {"status": "ok"}
