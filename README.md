# GitHub Release Monitor — Telegram Bot

A Python Telegram bot that monitors GitHub repositories for new releases and notifies subscribed users when new releases become available.

## Table of Contents

- [Features](#features)  
- [Architecture & Design](#architecture--design)  
- [Prerequisites](#prerequisites)  
- [Installation](#installation)  
  - [Clone & Setup](#clone--setup)  
  - [Configuration](#configuration)  
  - [Running the Bot](#running-the-bot)  
- [Bot Commands / Usage](#bot-commands--usage)  
  - [User Commands](#user-commands)  
  - [Admin / Owner Commands](#admin--owner-commands)  
- [How It Works](#how-it-works)  
- [Error Handling & Logging](#error-handling--logging)  
- [Deployment / Hosting](#deployment--hosting)  
- [Security Considerations](#security-considerations)  
- [Possible Enhancements](#possible-enhancements)  
- [Contributing](#contributing)  
- [License](#license)  

---

## Features

- Each Telegram user can subscribe to GitHub repositories (owner/repo).  
- The bot periodically checks for new releases on those repos.  
- When a new release is published, the bot sends a message (tag, release name, notes, URL).  
- Users can manually trigger checks.  
- Admin (bot owner) can ban/unban users, broadcast messages, manage privileged users.  
- Public/private mode — optionally restrict access to only allowed users.  
- Supports multiple users with individual subscriptions.

---

## Architecture & Design

Here’s a common layout (adjust as per your actual code):

```
/
├─ telegram_bot.py              # main entry / command handlers
├─ scheduler.py                 # scheduling periodic checks
├─ github_client.py             # logic to fetch GitHub releases
├─ storage.py                   # persistent storage (file, JSON, SQLite, etc.)
├─ admin.py                     # admin / owner-only methods
├─ utils/                       # helper functions (parsing, formatting)
├─ requirements.txt
└─ README.md
```

- **telegram_bot.py** — sets up the Telegram bot handlers.  
- **scheduler.py** — uses a scheduler (e.g. APScheduler) to run periodic jobs.  
- **github_client.py** — interacts with the GitHub API to get the latest release info.  
- **storage.py** — tracks user subscriptions and last-seen release tags.  
- **admin.py** — handles administration (ban, broadcast, mode toggles).  
- **utils/** — helper code (e.g. formatting Markdown, validation).

---

## Prerequisites

- Python 3.8+  
- A Telegram Bot token (via BotFather)  
- Your Telegram user ID (for owner/admin control)  
- Internet access  
- Optional: GitHub Personal Access Token (to increase API rate limits)  
- Storage backend (JSON file, SQLite, or your choice)

---

## Installation

### Clone & Setup

```bash
git clone https://github.com/hossein-bozorg-zadeh/GitHub-Release-Monitor-Telegram-Bot.git
cd GitHub-Release-Monitor-Telegram-Bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file (or set environment variables) with the following:

```text
BOT_TOKEN=your_telegram_bot_token
OWNER_ID=your_telegram_user_id
CHECK_INTERVAL_MINUTES=10          # how often to poll GitHub
GITHUB_TOKEN=your_github_token     # optional, for higher rate limits
MODE=public                        # or “private”
# Add any other variables your implementation requires
```

If you use a file-based storage (e.g. `data.json`) or SQLite, ensure the bot process has write access to the folder.

### Running the Bot

For local/testing:

```bash
python telegram_bot.py
```

For production, you might want to use a process manager (e.g. systemd, supervisor) or run in Docker.

---

## Bot Commands / Usage

Here are typical commands (modify to match your actual command names):

### User Commands

| Command                      | Description |
|------------------------------|-------------|
| `/start`                     | Start / register with the bot |
| `/help`                      | Show help / usage info |
| `/add owner/repo`             | Subscribe to a GitHub repository |
| `/remove owner/repo`          | Unsubscribe |
| `/list`                      | List your current subscriptions |
| `/check`                     | Manually force a check now |
| `/status owner/repo`         | Show last known release info of a repo |

### Admin / Owner Commands

- `/ban <user_id>` — ban a user  
- `/unban <user_id>` — unban  
- `/broadcast <message>` — send a message to all users  
- `/setmode public|private` — switch bot access mode  
- `/listusers` — list users & status  
- `/stats` — show stats (subscriptions, checks, etc.)  

---

## How It Works

1. **Subscription**: User issues `/add owner/repo`. Bot validates and stores `(user_id, repo_full_name)`.  
2. **Scheduler**: Every `CHECK_INTERVAL_MINUTES`, the scheduler iterates through all distinct repositories.  
3. **Fetch latest release**: Using GitHub API (and `GITHUB_TOKEN` if provided), get the latest release for that repo.  
4. **Compare**: Compare the fetched release tag with the last stored tag for that repo.  
5. **Notify users**: If it's newer, notify all users subscribed to that repo (tag name, link, notes).  
6. **Update storage**: Save new tag as the last-seen for future checks.  
7. **Manual check**: `/check` triggers the same logic immediately for one user’s repos.  
8. **Admin commands**: Manipulate user list, mode, broadcast, etc.

---

## Error Handling & Logging

- Catch HTTP / network errors when calling GitHub or Telegram APIs.  
- Retry transient failures (e.g. timeouts).  
- Log errors (file or stdout) with context (which repo, which user).  
- Handle edge cases: repo renamed, deleted, or made private.  
- If rate limited, log a warning and back off.

---

## Deployment / Hosting

- Use a small VPS or cloud instance (DigitalOcean, AWS, etc.).  
- Use `supervisor`, `systemd`, or a Docker container to keep bot running reliably.  
- Backup your storage (subscriptions, last seen data).  
- Use environment variables for secrets, don’t commit `.env`.  
- Monitor logs / resource usage if many users/repos.

---

## Security Considerations

- Never commit API tokens or secrets.  
- Validate user inputs (e.g. `owner/repo` format) to avoid injection or errors.  
- Rate-limit commands if necessary to prevent abuse.  
- Sanitize release notes before sending (if they include markdown).  
- Restrict access in “private mode” if you don’t want public usage.

---

## Possible Enhancements & To-Do

- Support GitHub webhooks (instead of polling).  
- Per-repo polling intervals.  
- Support private GitHub repos (with access tokens).  
- Richer notification formatting: attachments, diff summaries.  
- Web / dashboard interface for users.  
- Multi-language support.  
- Analytics / usage dashboard.  
- Better storage backend (e.g. PostgreSQL).  

---

## Contributing

1. Fork this repository  
2. Create a new branch (`feature/my-feature`)  
3. Implement changes & write tests / update docs  
4. Submit a pull request  
5. I’ll review and merge  

Please follow consistent style, test thoroughly, and update README if adding new commands or behavior.

---

## License

This project is licensed under the **MIT License** (or your chosen license).  

---

**Enjoy, and happy monitoring!** 🚀
