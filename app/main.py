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
os.makedirs(DATA_DIR, exist_ok=True)

app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

write_lock = threading.Lock()

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

def now_iso():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def is_initialized() -> bool:
    return os.path.exists(LEDGER_PATH) and os.path.getsize(LEDGER_PATH) > 0

def read_ledger() -> List[Movement]:
    rows: List[Movement] = []
    if not os.path.exists(LEDGER_PATH):
        return rows
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
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

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    guard = ensure_setup_page()
    if guard: return guard

    rows = read_ledger()
    balance = compute_balance(rows)

    # ---- Dynamic color: fade from green (>=1000) to red (0), red if negative ----
    if balance <= 0:
        hue = 0.0  # red
    else:
        ratio = min(balance, 1000.0) / 1000.0  # 0..1
        hue = 120.0 * ratio  # 120=green, 0=red
    balance_color = f"hsl({hue:.0f}, 70%, 60%)"

    movements = [r for r in rows if r.kind == "movement"]
    movements.sort(key=lambda r: r.timestamp, reverse=True)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "balance": f"{balance:.2f}",
        "balance_color": balance_color,
        "movements": movements[:200],
        "app_name": APP_NAME
    })

@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    if is_initialized():
        return RedirectResponse("/", 303)
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "app_name": APP_NAME
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
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "Please choose a ledger file to import.",
                "app_name": APP_NAME
            }, status_code=400)
        content = await ledger_file.read()
        text = content.decode("utf-8", errors="ignore")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "Uploaded file is empty.",
                "app_name": APP_NAME
            }, status_code=400)
        parsed = []
        for ln in lines:
            try:
                obj = json.loads(ln)
                Movement(**obj)
                parsed.append(obj)
            except Exception:
                return templates.TemplateResponse("setup.html", {
                    "request": request,
                    "error": "File format invalid. Expecting JSON Lines exported by Savion.",
                    "app_name": APP_NAME
                }, status_code=400)
        with write_lock:
            with open(LEDGER_PATH, "w", encoding="utf-8") as f:
                for obj in parsed:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        return RedirectResponse("/", 303)
    else:
        if initial_balance is None:
            return templates.TemplateResponse("setup.html", {
                "request": request,
                "error": "Please enter an initial balance or choose Import.",
                "app_name": APP_NAME
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

    rows = read_ledger()
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
    return templates.TemplateResponse("reset.html", {
        "request": request,
        "a": a, "b": b, "op": op,
        "app_name": APP_NAME
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
        return templates.TemplateResponse("reset.html", {
            "request": request,
            "error": "Verification failed. Type RESET and solve the math correctly.",
            "a": random.randint(20,60),
            "b": random.randint(5,15),
            "op": random.choice(["+","-"]),
            "app_name": APP_NAME
        }, status_code=400)

    if os.path.exists(LEDGER_PATH):
        try:
            rows = read_ledger()
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

    return RedirectResponse("/setup", 303)

@app.get("/healthz")
async def health():
    return {"status": "ok"}
