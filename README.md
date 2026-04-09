\# Finance Bot 🤖💰

AI-powered personal finance advisor Telegram bot built with Mistral AI.



\## Features

\- 🎯 Personal financial goal setting

\- 📊 Budget tracking \& analysis

\- 💹 Investment portfolio analysis

\- 🔔 Daily spending reminders at 20:00

\- 📈 Monthly financial reports

\- 🧠 Persistent memory via Google Sheets

\- 🔒 Rate limiting \& access control

\- 👥 Multi-user support (each user gets their own Sheet)



\## Prerequisites

\- Python 3.9+

\- Telegram account

\- Google account

\- Mistral AI account



\---



\## Step 1 — Create Telegram Bot

1\. Open Telegram and search for `@BotFather`

2\. Send `/newbot`

3\. Choose a name for your bot (e.g. `MyFinanceBot`)

4\. Choose a username ending with `bot` (e.g. `my\_finance\_123\_bot`)

5\. Copy the token you receive — you'll need it later



\---



\## Step 2 — Get Mistral API Key

1\. Go to \[console.mistral.ai](https://console.mistral.ai)

2\. Sign up or log in

3\. Click \*\*API Keys\*\* in the left menu

4\. Click \*\*Create new key\*\*

5\. Copy the key — you'll need it later



\---



\## Step 3 — Set Up Google Sheets \& Credentials

1\. Go to \[console.cloud.google.com](https://console.cloud.google.com)

2\. Click \*\*Create Project\*\* → give it a name → \*\*Create\*\*

3\. Go to \*\*APIs \& Services\*\* → \*\*Enable APIs\*\*

4\. Search and enable \*\*Google Sheets API\*\*

5\. Search and enable \*\*Google Drive API\*\*

6\. Go to \*\*APIs \& Services\*\* → \*\*Credentials\*\*

7\. Click \*\*Create Credentials\*\* → \*\*Service Account\*\*

8\. Give it a name → click \*\*Done\*\*

9\. Click on the Service Account → \*\*Keys\*\* → \*\*Add Key\*\* → \*\*JSON\*\*

10\. A JSON file will download — rename it to `credentials.json`

11\. Go to \[sheets.google.com](https://sheets.google.com) and create a new spreadsheet

12\. Name it `Finance Bot`

13\. Open `credentials.json` and find `client\_email`

14\. Share the spreadsheet with that email address as \*\*Editor\*\*

15\. Copy the spreadsheet ID from the URL:

&#x20;   `https://docs.google.com/spreadsheets/d/YOUR\_SHEET\_ID/edit`



\---



\## Step 4 — Installation

```bash

\# Clone the repository

git clone https://github.com/YOUR\_USERNAME/finance-bot-public.git

cd finance-bot-public



\# Install dependencies

pip install -r requirements.txt

```



\---



\## Step 5 — Configuration

Create a `.env` file in the project folder:

TELEGRAM\_TOKEN=your\_telegram\_bot\_token

MISTRAL\_API\_KEY=your\_mistral\_api\_key

SHEET\_ID=your\_google\_sheet\_id

GOOGLE\_CREDENTIALS\_FILE=credentials.json


Place your `credentials.json` file in the same folder.



\---



\## Step 6 — Run Locally

```bash

python bot.py

```



Open Telegram, find your bot, and send `/start`



\---



\## Step 7 — Deploy to Render (Free 24/7 Hosting)

1\. Push your code to GitHub (without `.env` and `credentials.json`)

2\. Go to \[render.com](https://render.com) and sign up with GitHub

3\. Click \*\*New\*\* → \*\*Web Service\*\*

4\. Select your repository

5\. Configure:

&#x20;  - \*\*Runtime:\*\* Python

&#x20;  - \*\*Build Command:\*\* `pip install -r requirements.txt`

&#x20;  - \*\*Start Command:\*\* `python bot.py`

6\. Go to \*\*Environment\*\* → Add these variables:

&#x20;  - `TELEGRAM\_TOKEN` = your token

&#x20;  - `MISTRAL\_API\_KEY` = your key

&#x20;  - `SHEET\_ID` = your sheet ID

&#x20;  - `GOOGLE\_CREDENTIALS\_FILE` = credentials.json

7\. Go to \*\*Environment\*\* → \*\*Secret Files\*\* → Add:

&#x20;  - Filename: `credentials.json`

&#x20;  - Contents: paste the full content of your credentials.json file

8\. Click \*\*Deploy\*\*



\---



\## Step 8 — Keep Bot Alive (Prevent Sleep)

1\. Go to \[uptimerobot.com](https://uptimerobot.com) and sign up

2\. Click \*\*Add New Monitor\*\*

3\. Select \*\*HTTP(s)\*\*

4\. URL: `https://your-app-name.onrender.com`

5\. Interval: \*\*5 minutes\*\*

6\. Save



\---



\## Usage

\- Send `/start` to begin

\- The bot will ask you about your financial goals and assets

\- Report daily expenses by simply messaging the bot

\- Receive daily reminders at 20:00

\- Get monthly reports automatically on the 1st of each month



\---



\## Security

\- All API keys stored in `.env` (never committed to GitHub)

\- Google credentials stored as Secret File on Render

\- Rate limiting enabled

\- To restrict access to specific users, add their Telegram IDs:

```python

ALLOWED\_USERS = {123456789, 987654321}

```



\---



\## Tech Stack

\- \*\*AI:\*\* Mistral Large

\- \*\*Bot:\*\* python-telegram-bot

\- \*\*Storage:\*\* Google Sheets

\- \*\*Hosting:\*\* Render.com

\- \*\*Language:\*\* Python 3.9+

