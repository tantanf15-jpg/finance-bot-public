import json
import re
import os
import threading
import time
import sqlite3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# ========== אבטחה ==========
ALLOWED_USERS = set()
RATE_LIMIT = 999999
rate_tracker = defaultdict(list)

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    rate_tracker[user_id] = [t for t in rate_tracker[user_id] if now - t < 60]
    if len(rate_tracker[user_id]) >= RATE_LIMIT:
        return True
    rate_tracker[user_id].append(now)
    return False

def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ========== SQLite ==========
DB_PATH = "finance_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY, user_id INTEGER, role TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS goals
                 (user_id INTEGER PRIMARY KEY, goal TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY, user_id INTEGER, date TEXT, amount TEXT, description TEXT, category TEXT, type TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS insights
                 (id INTEGER PRIMARY KEY, user_id INTEGER, type TEXT, description TEXT, suggestion TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

def db_save_history(user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO history (user_id, role, content, timestamp) VALUES (?,?,?,?)",
              (user_id, str(role), str(content), datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit()
    conn.close()

def db_load_history(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": str(r[1])} for r in reversed(rows)]

def db_save_goal(user_id: int, goal: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO goals (user_id, goal) VALUES (?,?)", (user_id, goal))
    conn.commit()
    conn.close()

def db_load_goal(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT goal FROM goals WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def db_save_transaction(user_id: int, transaction: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO transactions (user_id, date, amount, description, category, type) VALUES (?,?,?,?,?,?)",
              (user_id,
               transaction.get("date", datetime.now().strftime("%d/%m/%Y")),
               str(transaction.get("amount", "")),
               str(transaction.get("description", "")),
               str(transaction.get("category", "")),
               str(transaction.get("type", ""))))
    conn.commit()
    conn.close()

def db_save_insight(user_id: int, insight: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO insights (user_id, type, description, suggestion, timestamp) VALUES (?,?,?,?,?)",
              (user_id,
               str(insight.get("type", "")),
               str(insight.get("description", "")),
               str(insight.get("suggestion", "")),
               datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit()
    conn.close()

# ========== Google Sheets (גיבוי בלבד) ==========
try:
    credentials_path = f"/etc/secrets/{GOOGLE_CREDENTIALS_FILE}" if os.path.exists(f"/etc/secrets/{GOOGLE_CREDENTIALS_FILE}") else GOOGLE_CREDENTIALS_FILE
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    gc = gspread.authorize(creds)
    SHEETS_ENABLED = True
except:
    SHEETS_ENABLED = False
    print("Google Sheets not available - using SQLite only")

def backup_to_sheets(user_id: int, role: str, content: str):
    if not SHEETS_ENABLED or not SHEET_ID:
        return
    def _backup():
        try:
            sh = gc.open_by_key(SHEET_ID)
            try:
                ws = sh.worksheet(f"History_{user_id}")
            except:
                ws = sh.add_worksheet(title=f"History_{user_id}", rows=10000, cols=3)
                ws.append_row(["Date", "Role", "Content"])
            ws.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), str(role), str(content)])
        except Exception as e:
            print(f"Sheets backup error: {e}")
    threading.Thread(target=_backup, daemon=True).start()

def backup_transaction_to_sheets(user_id: int, transaction: dict):
    if not SHEETS_ENABLED or not SHEET_ID:
        return
    def _backup():
        try:
            sh = gc.open_by_key(SHEET_ID)
            try:
                ws = sh.worksheet(f"User_{user_id}")
            except:
                ws = sh.add_worksheet(title=f"User_{user_id}", rows=1000, cols=6)
                ws.append_row(["Date", "Amount", "Description", "Category", "Type"])
            ws.append_row([
                transaction.get("date", datetime.now().strftime("%d/%m/%Y")),
                str(transaction.get("amount", "")),
                str(transaction.get("description", "")),
                str(transaction.get("category", "")),
                str(transaction.get("type", ""))
            ])
        except Exception as e:
            print(f"Sheets backup error: {e}")
    threading.Thread(target=_backup, daemon=True).start()

# ========== System Prompt ==========
SYSTEM_PROMPT_TEMPLATE = """========== Professional Identity ==========
You are a personal professional financial advisor — a combination of:
Certified Public Accountant (CPA) with 20 years of experience
Certified Financial Planner (CFP) specializing in wealth building
Investment advisor with deep understanding of capital markets
Economic analyst specializing in retirement planning and real estate

Your personality:
Strict and precise — no tolerance for financial mistakes
Direct and purposeful — tell the truth even when uncomfortable
Balanced — not overly conservative nor overly aggressive
No empty encouragement — only facts and numbers
Write in clean paragraphs without dashes, asterisks, or markdown signs
Write like an accountant writing a professional letter — plain text only
Respond in the same language the user writes in

========== User Personal Goal ==========
{user_goal}

========== Advanced Agent Capabilities ==========
Learn from every conversation and improve recommendations:
Identify recurring spending patterns
Identify problematic categories based on history
Improve investment recommendations based on past performance
Adapt budget based on seasonality
Identify when the user overspends more

========== Goal Calculation ==========
Calculate total accumulation from all sources:
1. Liquid savings — checking account
2. Pension fund — return 4-6% annually
3. Education fund — return 4-6% annually, accessible after 6 years
4. Investment savings fund — return 5-7% annually
5. Investments — compound interest per asset separately
6. Real estate — value, rent, mortgage

For each asset: FV = PV x (1 + r)^n + PMT x [((1 + r)^n - 1) / r]

========== Onboarding Steps — Ask One at a Time ==========
Step A — Goal:
1. What amount do you want to save?
2. By when?
3. Why? (apartment, emergency, retirement, business, other)

Step B — Existing Assets:
4. Do you own property? (value + mortgage)
5. Pension fund: balance + monthly contribution?
6. Education fund: balance + monthly contribution?
7. Investment savings fund: balance + monthly contribution?
8. Investments: what do you have? balance + return?
9. Liquid savings in account?

Step C — Cash Flow:
10. Monthly net income?
11. Fixed expenses?
12. Average variable expenses?

========== After Data Collection ==========
Show accumulation table per asset
Calculate total expected vs goal
Gap + how much more to save monthly
Monthly budget with limits per category
3 concrete ways to close the gap

========== Smart Ongoing Analysis ==========
Recurring spending pattern — flag sharply
Unusual expense — compare to historical average
Close to goal — encourage with data
Moving away from goal — warn sharply

========== Daily Mode ==========
Every expense — analyze, categorize, calculate impact
Expense over 200 — ask: Is this bringing you closer or further from your goal?
When there is a transaction: TRANSACTION:{{"date":"DD/MM/YYYY","amount":100,"description":"description","category":"category","type":"expense or income"}}
When pattern detected: INSIGHT:{{"type":"pattern","description":"description","suggestion":"recommendation"}}

Categories: housing, food, transport, entertainment, clothing, health, savings, investments, pension, education-fund, income, other
Be direct, brief, strict. No markdown signs."""

user_data = {}

def call_mistral(messages: list) -> str:
    try:
        resp = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
            json={
                "model": "mistral-large-latest",
                "messages": messages,
                "max_tokens": 1500
            },
            timeout=30
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", 60))
            return f"Token limit reached. Please try again in {retry_after} seconds."
        if resp.status_code != 200:
            print(f"MISTRAL ERROR: {resp.status_code} {resp.text[:200]}")
            return "Temporary issue. Please try again."
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return "Request took too long. Please try again."
    except Exception as e:
        print(f"ERROR: {e}")
        return "Temporary issue. Please try again."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Access denied.")
        return
    username = update.effective_user.first_name or f"user_{user_id}"
    user_goal = db_load_goal(user_id)
    user_data[user_id] = {
        "history": db_load_history(user_id),
        "budget": {},
        "goal": user_goal
    }
    opening = f"Hello {username}! I am your personal financial advisor.\n\nI specialize in financial planning, investments, and budget management. I will analyze your situation and help you reach your financial goal.\n\nFirst question: What amount do you want to save?"
    user_data[user_id]["history"].append({"role": "assistant", "content": opening})
    db_save_history(user_id, "assistant", opening)
    backup_to_sheets(user_id, "assistant", opening)
    await update.message.reply_text(opening)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Access denied.")
        return
    if is_rate_limited(user_id):
        await update.message.reply_text("Too many messages. Wait a minute.")
        return

    user_text = str(update.message.text)

    if user_id not in user_data:
        user_goal = db_load_goal(user_id)
        user_data[user_id] = {
            "history": db_load_history(user_id),
            "budget": {},
            "goal": user_goal
        }

    user_data[user_id]["history"].append({"role": "user", "content": user_text})
    db_save_history(user_id, "user", user_text)
    backup_to_sheets(user_id, "user", user_text)

    goal = user_data[user_id].get("goal", "")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        user_goal=goal if goal else "No goal set yet — ask the user about their financial goal"
    )

    messages = [{"role": "system", "content": system_prompt}] + user_data[user_id]["history"][-10:]
    reply = call_mistral(messages)

    if "GOAL:" in reply:
        try:
            goal_match = re.search(r'GOAL:(.*?)(?:\n|$)', reply)
            if goal_match:
                new_goal = goal_match.group(1).strip()
                user_data[user_id]["goal"] = new_goal
                db_save_goal(user_id, new_goal)
                reply = reply.replace(goal_match.group(0), "").strip()
        except:
            pass

    match = re.search(r'TRANSACTION:(\{.*?\})', reply, re.DOTALL)
    if match:
        try:
            transaction = json.loads(match.group(1))
            db_save_transaction(user_id, transaction)
            backup_transaction_to_sheets(user_id, transaction)
            reply = reply.replace(match.group(0), "").strip()
            reply += "\n\nSaved."
        except:
            reply = reply.replace(match.group(0), "").strip()

    insight_match = re.search(r'INSIGHT:(\{.*?\})', reply, re.DOTALL)
    if insight_match:
        try:
            insight = json.loads(insight_match.group(1))
            db_save_insight(user_id, insight)
            reply = reply.replace(insight_match.group(0), "").strip()
        except:
            reply = reply.replace(insight_match.group(0), "").strip()

    user_data[user_id]["history"].append({"role": "assistant", "content": reply})
    db_save_history(user_id, "assistant", reply)
    backup_to_sheets(user_id, "assistant", reply)
    await update.message.reply_text(reply)

async def daily_reminder(context):
    for user_id in user_data:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="Daily check-in — What did you spend today? Tell me everything."
            )
        except Exception as e:
            print(f"Reminder error: {e}")

async def monthly_report(context):
    for user_id in user_data:
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            current_month = datetime.now().strftime("%m/%Y")
            c.execute("SELECT SUM(CAST(amount AS REAL)) FROM transactions WHERE user_id=? AND type='expense' AND date LIKE ?",
                      (user_id, f"%{current_month}%"))
            total_expense = c.fetchone()[0] or 0
            c.execute("SELECT SUM(CAST(amount AS REAL)) FROM transactions WHERE user_id=? AND type='income' AND date LIKE ?",
                      (user_id, f"%{current_month}%"))
            total_income = c.fetchone()[0] or 0
            conn.close()
            surplus = total_income - total_expense
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Monthly Report:\nIncome: {total_income:.0f}\nExpenses: {total_expense:.0f}\nSurplus: {surplus:.0f}"
            )
        except Exception as e:
            print(f"Report error: {e}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
    def log_message(self, format, *args):
        pass

def run_server():
    HTTPServer(("0.0.0.0", 10000), Handler).serve_forever()

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    job_queue = app.job_queue
    job_queue.run_daily(daily_reminder, time=datetime.strptime("17:00", "%H:%M").time())
    job_queue.run_monthly(monthly_report, when=datetime.strptime("09:00", "%H:%M").time(), day=1)
    print("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)