import json
import re
import os
import threading
import time
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

# ========== חיבורים ==========
credentials_path = f"/etc/secrets/{GOOGLE_CREDENTIALS_FILE}" if os.path.exists(f"/etc/secrets/{GOOGLE_CREDENTIALS_FILE}") else GOOGLE_CREDENTIALS_FILE
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
gc = gspread.authorize(creds)

# ========== System Prompt ==========
SYSTEM_PROMPT_TEMPLATE = """========== זהות מקצועית ==========
אתה יועץ פיננסי אישי מקצועי — שילוב של:
- רואה חשבון מוסמך (CPA) עם 20 שנות ניסיון
- מתכנן פיננסי מוסמך (CFP) המתמחה בבניית עושר
- יועץ השקעות עם הבנה עמוקה בשוק ההון
- אנליסט כלכלי המתמחה בתכנון פרישה ונדל"ן

האישיות שלך:
- מחמיר וקפדן — לא מוחל על טעויות כספיות
- ישיר ותכליתי — אומר את האמת גם כשהיא לא נעימה
- מאוזן — לא שמרן יתר ולא אגרסיבי מדי
- לא מנחם — רק עובדות ומספרים

========== המטרה האישית ==========
{user_goal}

========== יכולות סוכן מתקדם ==========
אתה לומד מכל שיחה ומשתפר בהמלצות:
- זיהוי דפוסי בזבוז חוזרים
- זיהוי קטגוריות בעייתיות לפי היסטוריה
- שיפור המלצות השקעה לפי ביצועי העבר
- התאמת תקציב לפי עונתיות
- זיהוי מתי המשתמש חורג יותר

========== חישוב המטרה ==========
חשב צבירה כוללת מכל המקורות:
1. חיסכון נזיל — חשבון עו"ש
2. קרן פנסיה — תשואה 4-6% שנתי
3. קרן השתלמות — תשואה 4-6% שנתי, נגיש אחרי 6 שנים
4. קופת גמל — תשואה 5-7% שנתי
5. השקעות — ריבית דריבית על כל נכס בנפרד
6. נדל"ן — שווי, שכירות, משכנתא

לכל נכס: FV = PV × (1 + r)^n + PMT × [((1 + r)^n - 1) / r]

========== שלבי הכרות — שאל אחד אחד ==========
שלב א — מטרה:
1. מה הסכום שאתה רוצה לצבור?
2. עד מתי?
3. למה? (דירה, חירום, פרישה, עסק, אחר)

שלב ב — נכסים:
4. יש לך דירה? (שווי + משכנתא)
5. קרן פנסיה: יתרה + הפרשה חודשית?
6. קרן השתלמות: יתרה + הפרשה חודשית?
7. קופת גמל: יתרה + הפרשה חודשית?
8. השקעות: מה יש? יתרה + תשואה?
9. חיסכון נזיל בחשבון?

שלב ג — תזרים:
10. הכנסה חודשית נטו?
11. הוצאות קבועות?
12. הוצאות משתנות ממוצעות?

========== אחרי איסוף ==========
- הצג טבלת צבירה לכל נכס
- חשב סה"כ צפוי vs יעד
- פער + כמה לחסוך בחודש
- תקציב חודשי עם תקרות
- 3 דרכים לסגור פער

========== ניתוח חכם ==========
- דפוס בזבוז חוזר → דגל בחדות
- הוצאה חריגה → השווה לממוצע היסטורי
- קרוב ליעד → עדד עם נתונים
- מתרחק מיעד → התריע בחדות

========== מצב יומי ==========
- כל הוצאה — נתח, קטלג, חשב השפעה
- הוצאה מעל 200 — שאל: "האם זה מקרב או מרחיק?"
- כשיש עסקה: TRANSACTION:{{"date":"DD/MM/YYYY","amount":100,"description":"תיאור","category":"קטגוריה","type":"expense או income"}}
- כשזיהית דפוס: INSIGHT:{{"type":"pattern","description":"תיאור","suggestion":"המלצה"}}

קטגוריות: דיור, מזון, תחבורה, בילויים, ביגוד, בריאות, חיסכון, השקעות, פנסיה, גמל, השתלמות, הכנסה, אחר
דבר בשפת המשתמש, קצר, ישיר, מחמיר."""

user_data = {}

def get_user_sheet(user_id: int):
    try:
        sh = gc.open_by_key(SHEET_ID)
        try:
            return sh.worksheet(f"User_{user_id}")
        except:
            ws = sh.add_worksheet(title=f"User_{user_id}", rows=1000, cols=6)
            ws.append_row(["תאריך", "סכום", "תיאור", "קטגוריה", "סוג"])
            return ws
    except Exception as e:
        print(f"שגיאת Sheets: {e}")
        return None

def save_history(user_id: int, role: str, content: str):
    try:
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(f"History_{user_id}")
        except:
            ws = sh.add_worksheet(title=f"History_{user_id}", rows=10000, cols=3)
            ws.append_row(["תאריך", "תפקיד", "תוכן"])
        ws.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), role, content])
    except Exception as e:
        print(f"שגיאת היסטוריה: {e}")

def load_history(user_id: int):
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(f"History_{user_id}")
        records = ws.get_all_records()
        return [{"role": r["תפקיד"], "content": r["תוכן"]} for r in records[-10:]]
    except:
        return []

def save_user_goal(user_id: int, goal: str):
    try:
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(f"Profile_{user_id}")
            ws.update("A2", [[goal]])
        except:
            ws = sh.add_worksheet(title=f"Profile_{user_id}", rows=10, cols=2)
            ws.append_row(["מטרה"])
            ws.append_row([goal])
    except Exception as e:
        print(f"שגיאת מטרה: {e}")

def load_user_goal(user_id: int):
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(f"Profile_{user_id}")
        return ws.cell(2, 1).value or ""
    except:
        return ""

def save_insight(user_id: int, insight: dict):
    try:
        sh = gc.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(f"Insights_{user_id}")
        except:
            ws = sh.add_worksheet(title=f"Insights_{user_id}", rows=1000, cols=4)
            ws.append_row(["תאריך", "סוג", "תיאור", "המלצה"])
        ws.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            insight.get("type", ""),
            insight.get("description", ""),
            insight.get("suggestion", "")
        ])
    except Exception as e:
        print(f"שגיאת insight: {e}")

def save_to_sheet(sheet, transaction):
    try:
        row = [
            transaction.get("date", datetime.now().strftime("%d/%m/%Y")),
            transaction.get("amount", ""),
            transaction.get("description", ""),
            transaction.get("category", ""),
            transaction.get("type", "")
        ]
        sheet.append_row(row)
        return True
    except Exception as e:
        print(f"שגיאה ב-Sheets: {e}")
        return False

def analyze_spending(sheet, budget: dict):
    try:
        records = sheet.get_all_records()
        current_month = datetime.now().strftime("%m/%Y")
        monthly_expenses = {}
        for row in records:
            if row.get("סוג") == "expense" and current_month in str(row.get("תאריך", "")):
                cat = row.get("קטגוריה", "אחר")
                monthly_expenses[cat] = monthly_expenses.get(cat, 0) + float(row.get("סכום", 0))
        alerts = []
        for cat, limit in budget.items():
            spent = monthly_expenses.get(cat, 0)
            if spent > limit:
                alerts.append(f"⚠️ {cat}: הוצאת ₪{spent:.0f} מתוך תקציב ₪{limit}")
        return alerts
    except:
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Access denied.")
        return
    username = update.effective_user.first_name or f"user_{user_id}"
    user_goal = load_user_goal(user_id)
    user_data[user_id] = {
        "history": load_history(user_id),
        "sheet": get_user_sheet(user_id),
        "budget": {},
        "goal": user_goal
    }
    opening = f"👋 Hello {username}! I'm your personal finance advisor.\n\nI'm an expert in financial planning, investments, and budget management.\nI'll analyze your situation and help you reach your financial goal.\n\n🎯 First question: What amount do you want to save?"
    user_data[user_id]["history"].append({"role": "assistant", "content": opening})
    save_history(user_id, "assistant", opening)
    await update.message.reply_text(opening)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ Access denied.")
        return
    if is_rate_limited(user_id):
        await update.message.reply_text("⏳ Too many messages. Wait a minute.")
        return
    username = update.effective_user.first_name or f"user_{user_id}"
    user_text = update.message.text
    if user_id not in user_data:
        user_goal = load_user_goal(user_id)
        user_data[user_id] = {
            "history": load_history(user_id),
            "sheet": get_user_sheet(user_id),
            "budget": {},
            "goal": user_goal
        }
    user_data[user_id]["history"].append({"role": "user", "content": user_text})
    save_history(user_id, "user", user_text)
    goal = user_data[user_id].get("goal", "")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        user_goal=goal if goal else "No goal set yet — ask the user about their financial goal"
    )
    alerts = []
    if user_data[user_id]["budget"] and user_data[user_id]["sheet"]:
        alerts = analyze_spending(user_data[user_id]["sheet"], user_data[user_id]["budget"])
    try:
        resp = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
            json={
                "model": "mistral-large-latest",
                "messages": [{"role": "system", "content": system_prompt}] + user_data[user_id]["history"][-10:],
                "max_tokens": 4096
            },
            timeout=60
        )
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
    except Exception as e:
        reply = f"Error: {str(e)}"
        print(f"ERROR: {e}")

    if "GOAL:" in reply:
        try:
            goal_match = re.search(r'GOAL:(.*?)(?:\n|$)', reply)
            if goal_match:
                new_goal = goal_match.group(1).strip()
                user_data[user_id]["goal"] = new_goal
                save_user_goal(user_id, new_goal)
                reply = reply.replace(goal_match.group(0), "").strip()
        except:
            pass

    match = re.search(r'TRANSACTION:(\{.*?\})', reply, re.DOTALL)
    if match:
        try:
            transaction = json.loads(match.group(1))
            if user_data[user_id]["sheet"] and save_to_sheet(user_data[user_id]["sheet"], transaction):
                reply = reply.replace(match.group(0), "").strip()
                reply += "\n\n✅ Saved to Google Sheets"
        except:
            reply = reply.replace(match.group(0), "").strip()

    insight_match = re.search(r'INSIGHT:(\{.*?\})', reply, re.DOTALL)
    if insight_match:
        try:
            insight = json.loads(insight_match.group(1))
            save_insight(user_id, insight)
            reply = reply.replace(insight_match.group(0), "").strip()
        except:
            reply = reply.replace(insight_match.group(0), "").strip()

    if alerts:
        reply += "\n\n" + "\n".join(alerts)

    user_data[user_id]["history"].append({"role": "assistant", "content": reply})
    save_history(user_id, "assistant", reply)
    await update.message.reply_text(reply)

async def daily_reminder(context):
    for user_id in user_data:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🔔 Daily check-in — What did you spend today?"
            )
        except Exception as e:
            print(f"Reminder error: {e}")

async def monthly_report(context):
    for user_id, data in user_data.items():
        try:
            if not data["sheet"]:
                continue
            records = data["sheet"].get_all_records()
            current_month = datetime.now().strftime("%m/%Y")
            total_expense = sum(float(r.get("סכום", 0)) for r in records if r.get("סוג") == "expense" and current_month in str(r.get("תאריך", "")))
            total_income = sum(float(r.get("סכום", 0)) for r in records if r.get("סוג") == "income" and current_month in str(r.get("תאריך", "")))
            surplus = total_income - total_expense
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📊 Monthly Report:\n💰 Income: {total_income:.0f}\n💸 Expenses: {total_expense:.0f}\n✅ Surplus: {surplus:.0f}"
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
    threading.Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    job_queue = app.job_queue
    job_queue.run_daily(daily_reminder, time=datetime.strptime("20:00", "%H:%M").time())
    job_queue.run_monthly(monthly_report, when=datetime.strptime("09:00", "%H:%M").time(), day=1)
    print("✅ Bot is running!")
    app.run_polling()