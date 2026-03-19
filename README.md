# 🤖 Insta Reel Bot

An automated Instagram Reel reposting bot that monitors source accounts, downloads new reels, reposts them to **multiple target accounts** in batches, and sends real-time status updates via Telegram.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![Instagram](https://img.shields.io/badge/Instagram-Reels-E4405F?logo=instagram&logoColor=white)

---

## ✨ Features

- 🔍 **Auto-Discovery** — Monitors selected Instagram accounts for new reels
- ⬇️ **Smart Download** — Downloads reels with duplicate detection
- 📤 **Batch Upload** — Uploads reels in configurable batches (e.g., 3 at a time, 30-min gap)
- 📱 **Multi-Account Targets** — Distribute reels across multiple reposting accounts (round-robin)
- 🤖 **Telegram Bot** — Real-time notifications + interactive commands with per-account stats
- 🗄️ **SQLite Tracking** — Full lifecycle tracking (discovered → downloaded → uploaded) with target account info
- 🧹 **Cleanup Worker** — Automatically deletes files after upload, catches missed files
- 🔐 **Session Caching** — Saves Instagram session per account to avoid repeated logins
- 🛡️ **Rate Limit Handling** — Independent rate-limit tracking per target account

## 📁 Project Structure

```
insta-reel-bot/
├── .env                 # Credentials & settings (not tracked by git)
├── .gitignore           # Git ignore rules
├── requirements.txt     # Python dependencies
├── config.py            # Config loader with multi-account support
├── database.py          # SQLite database manager with target tracking
├── scraper.py           # Reel discovery from source accounts
├── downloader.py        # Video file downloader
├── uploader.py          # Multi-account uploader with round-robin
├── telegram_bot.py      # Telegram notifications & commands
└── main.py              # Main orchestrator
```

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/Lukerman/insta-reel-bot.git
cd insta-reel-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy and edit the `.env` file with your credentials:

```env
# Instagram Target Accounts (the ones that repost)
# Add as many as needed with numbered suffixes
IG_USERNAME_1=your_first_account
IG_PASSWORD_1=your_first_password

IG_USERNAME_2=your_second_account
IG_PASSWORD_2=your_second_password

# Telegram Bot (create via @BotFather)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Source accounts to monitor (comma-separated)
SOURCE_ACCOUNTS=account1,account2

# Timing
CHECK_INTERVAL_MINUTES=360
UPLOAD_DELAY_MINUTES=30
MAX_REELS_PER_CYCLE=6
BATCH_SIZE=3

# Caption for reposted reels
CAPTION_TEMPLATE=🎬 Reposted | Credit: @{source}
```

> **Note:** The old single-account format (`IG_USERNAME` / `IG_PASSWORD`) still works as a fallback.

### 4. Run the bot

```bash
python main.py
```

## 🤖 Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Show current bot stats & per-account upload counts |
| `/recent` | Show last 5 tracked reels with target account info |
| `/pause` | Pause the bot |
| `/resume` | Resume the bot |
| `/help` | Show all commands |

## ⚙️ How It Works

```
┌──────────┐     ┌────────────┐     ┌──────────────────┐
│ Scraper  │────▶│ Downloader │────▶│ UploaderManager  │
│ (discover)│    │ (save .mp4)│     │ (round-robin)    │
└──────────┘     └────────────┘     └──────────────────┘
      │                │              │    │    │
      │                │           ┌──┘    │    └──┐
      │                │           ▼       ▼       ▼
      │                │        Account  Account  Account
      │                │          #1       #2       #3
      └───────┬────────┴──────────┴────────┴───────┘
              ▼
       ┌─────────────┐     ┌──────────────┐
       │  Database   │     │ Telegram Bot │
       │  (SQLite)   │     │ (notifications)│
       └─────────────┘     └──────────────┘
```

1. **Scrape** — Discovers new reels from source accounts via private API
2. **Download** — Downloads video files to local `downloads/` folder
3. **Upload** — Distributes reels round-robin across target accounts in batches with delays
4. **Cleanup** — Deletes video files after successful upload
5. **Notify** — Sends status updates to Telegram at every step (with target account info)
6. **Sleep** — Waits for the configured interval before the next cycle

## 📱 Multi-Account Upload

Reels are distributed across target accounts in **round-robin** fashion:
- Reel 1 → Account #1
- Reel 2 → Account #2
- Reel 3 → Account #1
- ...

Each account maintains its own:
- 🔐 **Login session** (`ig_session_<username>.json`)
- ⏳ **Rate-limit state** — if one account gets throttled, the others keep uploading
- 📊 **Upload stats** — tracked in the database and shown via `/status`

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Automating actions on Instagram may violate their [Terms of Service](https://help.instagram.com/581066165581870). Use at your own risk. The authors are not responsible for any account restrictions or bans resulting from the use of this software.

## 📄 License

MIT License
