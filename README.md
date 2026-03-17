# 🤖 Insta Reel Bot

An automated Instagram Reel reposting bot that monitors source accounts, downloads new reels, reposts them to your account in batches, and sends real-time status updates via Telegram.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)
![Instagram](https://img.shields.io/badge/Instagram-Reels-E4405F?logo=instagram&logoColor=white)

---

## ✨ Features

- 🔍 **Auto-Discovery** — Monitors selected Instagram accounts for new reels
- ⬇️ **Smart Download** — Downloads reels with duplicate detection
- 📤 **Batch Upload** — Uploads reels in configurable batches (e.g., 3 at a time, 30-min gap)
- 🤖 **Telegram Bot** — Real-time notifications + interactive commands
- 🗄️ **SQLite Tracking** — Full lifecycle tracking (discovered → downloaded → uploaded)
- 🧹 **Cleanup Worker** — Automatically deletes files after upload, catches missed files
- 🔐 **Session Caching** — Saves Instagram session to avoid repeated logins
- 🛡️ **Rate Limit Handling** — Built-in delays and retry logic

## 📁 Project Structure

```
insta-reel-bot/
├── .env                 # Credentials & settings (not tracked by git)
├── .gitignore           # Git ignore rules
├── requirements.txt     # Python dependencies
├── config.py            # Config loader with validation
├── database.py          # SQLite database manager
├── scraper.py           # Reel discovery from source accounts
├── downloader.py        # Video file downloader
├── uploader.py          # Reel uploader to target account
├── telegram_bot.py      # Telegram notifications & commands
└── main.py              # Main orchestrator
```

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/insta-reel-bot.git
cd insta-reel-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy and edit the `.env` file with your credentials:

```env
# Instagram Target Account (the one that reposts)
IG_USERNAME=your_username
IG_PASSWORD=your_password

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
CAPTION_TEMPLATE=link in bio 🔗
```

### 4. Run the bot

```bash
python main.py
```

## 🤖 Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Show current bot stats |
| `/recent` | Show last 5 tracked reels |
| `/pause` | Pause the bot |
| `/resume` | Resume the bot |
| `/help` | Show all commands |

## ⚙️ How It Works

```
┌──────────┐     ┌────────────┐     ┌──────────┐
│ Scraper  │────▶│ Downloader │────▶│ Uploader │
│ (discover)│    │ (save .mp4)│     │ (repost) │
└──────────┘     └────────────┘     └──────────┘
      │                │                  │
      └───────┬────────┴──────────────────┘
              ▼
       ┌─────────────┐     ┌──────────────┐
       │  Database   │     │ Telegram Bot │
       │  (SQLite)   │     │ (notifications)│
       └─────────────┘     └──────────────┘
```

1. **Scrape** — Discovers new reels from source accounts via private API
2. **Download** — Downloads video files to local `downloads/` folder
3. **Upload** — Uploads in batches (3 at a time by default) with delays between batches
4. **Cleanup** — Deletes video files after successful upload
5. **Notify** — Sends status updates to Telegram at every step
6. **Sleep** — Waits for the configured interval before the next cycle

## ⚠️ Disclaimer

This tool is for **educational purposes only**. Automating actions on Instagram may violate their [Terms of Service](https://help.instagram.com/581066165581870). Use at your own risk. The authors are not responsible for any account restrictions or bans resulting from the use of this software.

## 📄 License

MIT License
