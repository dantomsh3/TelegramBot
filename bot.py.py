# --- Telegram expense bot (Hebrew) ---
# Features:
# - Parse "דניאל - 120" / "אריאל- 55,5" and store per person with timestamp
# - Monthly window: from 1st of current month (00:00) to 1st of next month (exclusive)
# - Command "סה\"כ חודשי" -> total (and per person) since 1st of month
# - Command "סיכום חודש" -> split equally, show who owes whom and how much
# Data persists to expenses.json (same folder).

import json
import os
import re
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

import gspread
from google.oauth2.service_account import Credentials

# התחברות לחשבון השירות של גוגל
SERVICE_ACCOUNT_FILE = "utility-descent-443509-f9-c3eb77e6772e.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",  # קריאה/כתיבה ל-Sheets
    "https://www.googleapis.com/auth/drive.readonly" # קריאת רשימת קבצים (חיפוש לפי שם)
]


creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)

# פתח את הגיליון לפי השם שלו (כמו שאתה רואה ב-Google Sheets)
SPREADSHEET_NAME = "הוצאות חודשיות"
worksheet = gc.open(SPREADSHEET_NAME).sheet1


# ---- CONFIG ----
TOKEN = "8026269826:AAGVBj3i1qEPnSo4Yg2tstsdetNZI_TkqGg"  # <<< שים כאן את הטוקן מ-BotFather
DATA_FILE = "expenses.json"
PEOPLE = ("דניאל", "אריאל")  # שני השמות לזיהוי
CURRENCY = "₪"

# ---- STORAGE HELPERS ----
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"records": []}  # each: {"ts": ISO, "name": str, "amount": float}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_record(name: str, amount: float, ts: datetime):
    # המרת תאריך לפורמט קריא
    date_str = ts.strftime("%d/%m/%Y %H:%M")
    # הוספת שורה חדשה לגיליון
    worksheet.append_row([date_str, name, amount])


# ---- DATE WINDOW (1st to 1st) ----
def month_window(dt: datetime):
    """Return (start, end) for current month: [1st 00:00, 1st of next month 00:00)."""
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # move to next month
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end

def filter_monthly(records, now: datetime):
    start, end = month_window(now)
    out = [r for r in records if start <= datetime.fromisoformat(r["ts"]) < end]
    return out, start, end

# ---- PARSE TEXT "Name - amount" ----
NAME_PATTERN = "|".join(map(re.escape, PEOPLE))
AMOUNT_RE = re.compile(rf"^\s*({NAME_PATTERN})\s*[-–—:]\s*([0-9]+(?:[.,][0-9]+)?)\s*$")

def parse_expense_line(text: str):
    """
    Returns (name, amount) if matches "דניאל - 120.5" (comma or dot accepted), else None.
    """
    m = AMOUNT_RE.match(text.strip())
    if not m:
        return None
    name = m.group(1)
    raw = m.group(2).replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return None
    return name, amount

# ---- COMMANDS ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "היי! אני בוט הוצאות.\n"
        f"הזינו כך: {PEOPLE[0]} - 45  או  {PEOPLE[1]} - 72.5\n"
        "פקודות זמינות:\n"
        "• סה\"כ חודשי – סכום מצטבר מה־1 לחודש\n"
        "• סיכום חודש – חלוקה שווה וחישוב יתרה\n"
        "• פירוט חודשי – פירוט רשומות מהחודש\n"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # Commands in plain Hebrew (not slash-commands)
    if text in ('סה"כ חודשי', 'סה״כ חודשי', 'סהכ חודשי'):
        return await monthly_total(update, context)
    if text == 'סיכום חודש':
        return await monthly_split(update, context)
    if text == 'פירוט חודשי':
        return await monthly_list(update, context)

    parsed = parse_expense_line(text)
    if parsed:
        name, amount = parsed
        now = datetime.now()
        add_record(name, amount, now)
        await update.message.reply_text(f"הוספתי {amount:.2f}{CURRENCY} על שם {name} ✅")
    else:
        # soft hint
        await update.message.reply_text(
            f"לא זיהיתי פורמט. נסו למשל: {PEOPLE[0]} - 45  או  {PEOPLE[1]} - 72.5\n"
            "או כתבו: סה\"כ חודשי / סיכום חודש / פירוט חודשי"
        )

async def monthly_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    data = load_data()
    records, start, _ = filter_monthly(data["records"], now)

    totals = {p: 0.0 for p in PEOPLE}
    for r in records:
        if r["name"] in totals:
            totals[r["name"]] += r["amount"]

    grand = sum(totals.values())
    start_str = start.strftime("%d.%m.%Y")
    lines = [f"סה\"כ חודשי (מ־{start_str}): {grand:.2f}{CURRENCY}"]
    for p in PEOPLE:
        lines.append(f"• {p}: {totals[p]:.2f}{CURRENCY}")
    await update.message.reply_text("\n".join(lines))

async def monthly_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    data = load_data()
    records, start, _ = filter_monthly(data["records"], now)

    totals = {p: 0.0 for p in PEOPLE}
    for r in records:
        if r["name"] in totals:
            totals[r["name"]] += r["amount"]

    grand = sum(totals.values())
    per_person = grand / 2.0

    # balance: how much each should pay/add to reach split
    # if value is positive -> this person SHOULD PAY (i.e., spent less than half)
    # if negative -> this person SHOULD RECEIVE
    balances = {p: round(per_person - totals[p], 2) for p in PEOPLE}

    # Determine who owes whom
    p1, p2 = PEOPLE
    if balances[p1] > 0 and balances[p2] < 0:
        owes = p1
        gets = p2
        amount = min(balances[p1], -balances[p2])
    elif balances[p2] > 0 and balances[p1] < 0:
        owes = p2
        gets = p1
        amount = min(balances[p2], -balances[p1])
    else:
        owes = gets = None
        amount = 0.0

    start_str = start.strftime("%d.%m.%Y")
    lines = [
        f"סיכום חודש (מ־{start_str}):",
        f"סה\"כ: {grand:.2f}{CURRENCY}  |  לכל אחד: {per_person:.2f}{CURRENCY}",
        f"{p1}: {totals[p1]:.2f}{CURRENCY}",
        f"{p2}: {totals[p2]:.2f}{CURRENCY}",
    ]
    if amount > 0:
        lines.append(f"יתרה: {owes} מעביר/ה ל{gets} {amount:.2f}{CURRENCY} כדי להשתוות 💸")
    else:
        lines.append("אין יתרה – אתם מאוזנים ✔️")

    await update.message.reply_text("\n".join(lines))

async def monthly_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    data = load_data()
    records, start, _ = filter_monthly(data["records"], now)

    if not records:
        await update.message.reply_text("אין רשומות החודש 🧾")
        return

    rows = []
    for r in sorted(records, key=lambda x: x["ts"]):
        dt = datetime.fromisoformat(r["ts"]).strftime("%d.%m %H:%M")
        rows.append(f"{dt} | {r['name']} | {r['amount']:.2f}{CURRENCY}")
    await update.message.reply_text("פירוט חודשי:\n" + "\n".join(rows))

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("הבוט פועל... ✨  (עוצרים עם Ctrl+C)")
    app.run_polling()

if __name__ == "__main__":
    main()
