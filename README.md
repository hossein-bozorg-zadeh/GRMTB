# 🔔 GRMTB — GitHub/GitLab Release Monitor

A Telegram bot that watches GitHub and GitLab repositories for new releases and
notifies you instantly — with one-tap download buttons for release assets.

[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue?logo=telegram)](https://t.me/gitchekerbot)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Try it live:** [@gitchekerbot](https://t.me/gitchekerbot)

## ✨ Features

- **Multi-platform** — track both GitHub 🤖 and GitLab 🦊 repositories, each with
  its own icon and token
- **Per-repo check intervals** — 6h, 12h, 24h, 48h or 72h
- **Release notifications** — tag, notes preview and asset list, only for
  releases you haven't seen
- **Asset downloads** — GitHub assets under 50 MB are sent as documents right in
  the chat; GitLab assets open via direct link
- **Personal tokens** — every user supplies their own GitHub/GitLab token, so
  rate limits stay yours (5,000 req/hour on GitHub with a token)
- **Access control** — public/private mode, required-channel gate, ban list and
  special users
- **Admin panel** — user management, broadcast message, JSON export/import, log
  download, and daily data+log backups to a log channel
- **Persistent storage** — everything survives restarts in a single JSON file

## 🚀 Quick Start

```bash
git clone https://github.com/hossein-bozorg-zadeh/GRMTB
cd GRMTB
pip install -r requirements.txt

export BOT_TOKEN="your_telegram_bot_token"
export OWNER_ID="your_telegram_user_id"

python bot.py
```

- `BOT_TOKEN` — from [@BotFather](https://t.me/BotFather) (`/newbot`)
- `OWNER_ID` — your numeric Telegram ID, e.g. from [@userinfobot](https://t.me/userinfobot)

> The bot reads plain environment variables. A `.env` file is **not** loaded
> automatically (there is no `python-dotenv` dependency) — export the variables
> or use your platform's env-var settings.

## 🌐 Deployment

The repo ships with everything for one-click deploys:

| File | Used by |
| --- | --- |
| `Procfile` | Heroku, Render, any Buildpack platform |
| `nixpacks.toml` | Railway (Nixpacks builder) |
| `runtime.txt` | Heroku-style Python version pin (3.11) |

**Railway** — fork this repo, create a project from it, set `BOT_TOKEN` and
`OWNER_ID`, deploy as a **Worker** service.

**Render** — fork, create a Web Service from the repo, set the two variables,
use the included `Procfile`.

**Anywhere else** — any Linux box/VPS with Python 3.11: install, export, run
under `systemd`/`tmux`.

## 📱 Using the Bot

1. `/start` and open the menu
2. **🔑 Set API Tokens** — paste a GitHub token
   ([create](https://github.com/settings/tokens), classic, `public_repo` scope)
   and/or a GitLab token
   ([create](https://gitlab.com/-/user_settings/personal_access_tokens),
   `read_api` scope). Messages containing tokens are deleted immediately after
   they are saved.
3. **➕ Add Repo** — pick the platform and send `owner/repo`
   (e.g. `torvalds/linux`, `gitlab-org/gitlab`)
4. **⏱ Set Check Interval** — pick a repo, then 6–72 hours
5. **🔄 Check Now** — force an immediate check of all your repos

When a new release is published you get a message with the tag, notes preview
and — for GitHub — paged buttons for each asset. Files under 50 MB arrive as
Telegram documents; larger ones and GitLab assets open via direct link.

## 👑 Admin Panel (owner only)

| Screen | What you can do |
| --- | --- |
| Bot status | Toggle public/private mode |
| Required channel | Users must join a channel before using the bot |
| Log channel | Daily automatic backup of data + logs |
| Manage users | Add special users, ban/unban, list everyone |
| Broadcast | Send a message to every user |
| Data | Export/import all bot data as JSON, download logs |

Backups go to the log channel every 24 hours once it is configured.

## 📁 Project Structure

```
GRMTB/
├── bot.py            # The whole bot
├── requirements.txt  # python-telegram-bot, aiohttp
├── Procfile          # Heroku/Render worker process
├── nixpacks.toml     # Railway build config
├── runtime.txt       # Python 3.11 pin
└── LICENSE           # MIT

bot_data.json        # created at runtime — all persistent state
bot.log              # created at runtime — file log
```

## 🔧 Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `OWNER_ID` | Yes | Telegram user ID of the bot owner |

Everything else (channels, mode, intervals, repos, tokens) is managed from
inside the bot and stored in `bot_data.json`.

## 🛠️ Troubleshooting

| Symptom | Check |
| --- | --- |
| Bot not responding | Both env vars set? Process running? Have you pressed Start in Telegram? |
| No notifications | Token set for that platform? Does the repo actually publish *releases* (not just tags)? Interval elapsed? Try **🔄 Check Now** |
| Channel gate won't pass | Bot must be **admin** in the required channel; username must include `@` |
| Rate limits | GitHub: 5,000 req/h with token, 60/h without — use long intervals or always set a token |

## 🤝 Contributing

PRs are welcome — fork, branch, commit, open a PR.

## 📄 License

MIT — see [LICENSE](LICENSE).

**Star ⭐ this repository if you find it useful!**
