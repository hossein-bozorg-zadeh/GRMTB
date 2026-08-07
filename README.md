# 🔔 GitHub/GitLab Release Notifier Bot

A powerful Telegram bot that monitors GitHub and GitLab repositories for new releases and sends instant notifications with download options.

[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-blue?logo=telegram)](https://t.me/gitchekerbot)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## ✨ Features

### 🚀 Core Features
- **Multi-Platform Support**: Monitor both GitHub 🤖 and GitLab 🦊 repositories
- **Self-Hosted GitLab**: Track releases from your own GitLab instances
- **Real-time Notifications**: Get instant alerts when new releases are published
- **Missed Release Catch-Up**: If the bot is offline when releases are published, it notifies you about every release you missed (not just the newest one)
- **Download Integration**: Subscribers can download release assets through Telegram (bot-file or direct-link mode)
- **Customizable Intervals**: Set check intervals per repository (6h, 12h, 24h, 48h, 72h)
- **Manual Check**: Force check all repositories on demand

### 🔐 Security & Access Control
- **Dual Token System**: Each user sets their own GitHub and GitLab tokens
- **Encrypted Tokens**: API tokens are encrypted at rest with Fernet (AES) before being stored
- **Channel Requirement**: Optional mandatory channel membership for bot access (public and private channels, with bot-generated invite links and a joined-member counter)
- **User Management**: Ban/unban users, special user privileges
- **Public/Private Mode**: Toggle bot accessibility

### 👑 Admin Features
- **Admin Panel**: Comprehensive control panel for bot owners
- **Channel Configuration**: Set required channel and log channel from bot
- **Data Management**: Export/import bot data as JSON
- **Log Access**: Download bot logs for monitoring
- **Broadcast Messages**: Send update notifications to all users
- **Automatic Backups**: Daily backups to configured log channel

### 📊 Advanced Features
- **Repository Icons**: Visual distinction between GitHub 🤖 and GitLab 🦊 repos
- **Persistent Storage**: All data stored in a SQLite database (`bot_data.db`)
- **User-Specific Settings**: Each user manages their own repositories and tokens
- **Smart Notifications**: Only notifies on new releases, not duplicates
- **Persistent Check History**: Last-check timestamps survive restarts (no re-check storm after redeploy)
- **Subscriptions**: Monetize with subscription plans paid via Telegram Stars and/or TON (via CryptoBot)
- **Channel Notifications**: Subscribers can mirror release alerts to their own channel

## 📋 Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- GitHub Personal Access Token (optional, per user)
- GitLab Personal Access Token (optional, per user)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/hossein-bozorg-zadeh/GRMTB
cd GRMTB
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Environment Variables

Create a `.env` file or set environment variables:

```bash
export BOT_TOKEN="your_telegram_bot_token"
export OWNER_ID="your_telegram_user_id"
```

**Optional environment variables:**

```bash
export TOKEN_ENCRYPTION_KEY="your_fernet_key"  # recommended: use a fixed key across restarts
export DB_FILE="/path/to/volume/bot_data.db"   # default: bot_data.db in the working directory
export CRYPTO_BOT_TOKEN="your_crypto_bot_api_token"  # enables TON payments via CryptoBot
export PUBLIC_URL="https://your-public-url"          # required for CryptoBot webhook callbacks
export WEBHOOK_PORT="8080"                            # port for the CryptoBot webhook server (default 8080)
```

The webhook server only starts when `CRYPTO_BOT_TOKEN` is set. `PUBLIC_URL` must be a public HTTPS URL reachable by CryptoBot (e.g. `https://your-railway-url.up.railway.app`); the webhook endpoint is `POST {PUBLIC_URL}/cb_webhook`.

If `TOKEN_ENCRYPTION_KEY` is not set, the bot generates a key on first run and stores it inside the database. For real security and portable backups, set this variable to a fixed Fernet key — generate one with:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> **Warning**: Encrypted tokens can only be decrypted with the key that encrypted them. If you restore a data backup on a new deployment, use the same `TOKEN_ENCRYPTION_KEY` so tokens remain usable.

**Get Your Bot Token:**
1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the instructions
3. Copy the token provided

**Get Your User ID:**
1. Open Telegram and search for [@userinfobot](https://t.me/userinfobot)
2. Send `/start`
3. Copy your user ID

### 4. Run the Bot

```bash
python bot.py
```

## 🌐 Deploy to Free Hosting

### Railway.app (Recommended)

1. Fork this repository
2. Sign up at [Railway.app](https://railway.com?referralCode=s2rrDU)
3. Create new project from GitHub repo
4. Add environment variables:
   - `BOT_TOKEN`
   - `OWNER_ID`
   - `TOKEN_ENCRYPTION_KEY` (recommended)
5. **Add a persistent volume** (Settings → Volumes → Mount `/data`) and set `DB_FILE=/data/bot_data.db` so your data survives redeploys
6. *(Optional for TON payments)* Add `CRYPTO_BOT_TOKEN`, then **generate a domain** (Settings → Networking) and set `PUBLIC_URL=https://<your-app>.up.railway.app`
7. Deploy! ✨

### Render.com

1. Fork this repository
2. Sign up at [Render.com](https://render.com)
3. Create new Web Service
4. Connect your GitHub repo
5. Set environment variables
6. Deploy! ✨

### Other Options
- **Heroku**: Use `Procfile` included
- **PythonAnywhere**: Upload and run
- **Fly.io**: Use flyctl CLI
- **VPS**: Any Linux server with Python

## 📱 How to Use

### Initial Setup

1. Start the bot: `/start`
2. Set your API tokens:
   - Click **🔑 Set API Tokens**
   - Choose **🤖 GitHub** or **🦊 GitLab**
   - Send your personal access token

**Get GitHub Token:**
- Visit: https://github.com/settings/tokens
- Generate new token (classic)
- Select `public_repo` scope
- Copy and send to bot

**Get GitLab Token:**
- Visit: https://gitlab.com/-/user_settings/personal_access_tokens
- Create new token
- Select `read_api` scope
- Copy and send to bot

### Adding Repositories

1. Click **➕ Add Repo**
2. Select platform (GitHub 🤖 or GitLab 🦊)
3. Send repository in format: `owner/repo`
   - Example: `torvalds/linux`
   - Example: `gitlab-org/gitlab`

#### Self-Hosted GitLab Instances

After sending a GitLab repository, the bot asks for the GitLab instance URL:

- Send your instance URL, e.g. `https://gitlab.example.com`
- Or send `skip` to use the default `https://gitlab.com`

Self-hosted repos are marked as `(self-hosted)` in your repository list.

### Managing Repositories

- **📋 My Repos**: View all tracked repositories
- **⏱ Set Check Interval**: Change how often to check each repo
- **🗑 Delete Repo**: Remove a repository from tracking
- **🔄 Check Now**: Manually check all repos immediately

### Downloading Releases

When a new release is detected:
1. You'll receive a notification with release details
2. **Download links require an active subscription** — free users only see the release info with a subscribe prompt
3. Subscribers click the download button; the delivery depends on the user's download mode (`Bot file` / `Direct link`):
   - **Bot file**: files ≤ 50MB are uploaded to Telegram; larger files show a direct download link
   - **Direct link**: a download URL is posted instead
4. Files above the admin-configured **download limit** (default 1.9 GB, set in Shop Settings) are not served, even for subscribers

If several releases were published while the bot was offline, you receive a separate notification for **each** release (oldest first).

## 👑 Admin Features

Access the admin panel by clicking **👑 Admin Panel** (owner only).

### Bot Configuration
- **🔄 Toggle Bot Status**: Switch between Public/Private mode
- **📢 Set Required Channel**: Users must join to use bot (supports public and private channels)
- **📊 Set Log Channel**: Receive daily backups automatically

### Required Channel (public or private)
- **Public channel**: send the username (e.g. `@mychannel`) — the bot builds the join link automatically
- **Private channel**: send the numeric chat ID, then:
  - send the invite link (`https://t.me/+xxxx`), or
  - send `auto` so the bot generates its own invite link (requires the bot to be an admin with invite-link permission), or
  - send `skip` to add a link later
- You can also paste an invite link first and then provide the username/ID for the membership check
- The admin panel shows the current join link and **how many users joined via the bot's link**

### User Management
- **➕ Add Special User**: Grant access when bot is private
- **🚫 Ban User**: Block user from bot
- **✅ Unban User**: Restore user access
- **📋 List Users**: View all bot users

### Data Management
- **💾 Download Data**: Export all bot data as JSON
- **📋 Download Logs**: Download bot activity logs
- **📥 Import Data**: Restore data from backup
- **📣 Send Update Message**: Broadcast to all users
- **🛒 Shop Settings**: Manage subscription plans, toggle which plans are visible, view subscriptions, set the download limit (owner only)

### Automatic Backups

If you set a log channel:
- Bot data is automatically backed up every 24 hours
- Log files are sent to the channel
- Keeps your data safe without manual intervention

## 💰 Subscriptions (Telegram Stars + TON)

The bot sells **subscription plans** (e.g. 1 month, 3 months, 6 months, 1 year) with two payment methods. An active subscription unlocks release download links and channel notifications.

### 1. Telegram Stars

Telegram's native in-app currency. To enable:

1. Send `/mybots` to [@BotFather](https://t.me/BotFather), select your bot
2. Choose **Payments** and create/attach a payment provider (Telegram Stars)
3. No additional environment variables needed — stars use the bot token directly

Users tap the `⭐ Subscribe` button and pay with Stars inline. Payments are confirmed automatically via Telegram's pre-checkout flow. Buying a plan while subscribed **extends** the remaining time.

### 2. TON (via CryptoBot)

Users pay with TON coins through [CryptoBot](https://t.me/CryptoBot). To enable:

1. Open [@CryptoBot](https://t.me/CryptoBot) and get your API token (Settings → API)
2. Set `CRYPTO_BOT_TOKEN`
3. Set `PUBLIC_URL` to a public HTTPS URL that CryptoBot can reach (Railway generates one for you under Settings → Networking → Generate Domain)
4. The webhook endpoint is `POST {PUBLIC_URL}/cb_webhook`; the bot listens on `WEBHOOK_PORT` (default `8080`)

Users pay via a CryptoBot invoice link. The bot confirms payment through the webhook and also offers a "I've paid — Check" button that polls CryptoBot as a fallback.

> **Note**: For the CryptoBot webhook to work, your deployment must expose a public HTTPS URL on `WEBHOOK_PORT`. The "I've paid — Check" button still works without a public URL.

### Admin: Managing the Shop (owner only)

The owner can open **🛒 Shop Settings** from the admin panel to:
- Add/edit plans (key, title, description, duration in days, price in Stars, price in TON)
- **Toggle plans on/off** — only enabled plans appear in the store (e.g. hide the 6-month and 1-year plans to show just the first 2)
- Delete plans
- View subscriptions and their expiry (`feature_purchases`)
- Set the **download limit** in MB (e.g. `1900` for 1.9 GB) — files above this size are not served

Only the **owner** can change shop settings; special users cannot.

### Subscription Logic

- One active subscription per user; buying any plan adds its duration to the remaining time
- The owner and special users bypass the subscription check automatically
- Plans and subscriptions are included in data export/import, so they survive backup restore

## 📢 Subscriber Channel Notifications

Subscribers can have release notifications (with download links) posted to their own channel as well as their private chat:

1. Open **📢 Channel Notifications** in the main menu
2. **📡 Set Channel** — send the channel username or ID (the bot must be an admin of that channel)
3. **📦 Select Repos** — choose which of your tracked repos should also be posted to the channel
4. **📥 Download mode** — `Bot file` (small files are uploaded to Telegram) or `Direct link` (download URLs are posted instead)

Free users see a subscribe prompt instead of the channel-notifications page.

## 📁 Project Structure

```
release-notifier-bot/
├── bot.py                 # Main bot code
├── requirements.txt       # Python dependencies
├── Procfile              # For Railway/Heroku deployment
├── railway.json          # Railway configuration
├── runtime.txt           # Python version specification
├── bot_data.db           # SQLite data storage (auto-created)
├── bot.log              # Log file (auto-created)
├── README.md            # This file
└── .gitignore           # Git ignore rules
```

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `OWNER_ID` | Yes | Telegram user ID of bot owner |
| `TOKEN_ENCRYPTION_KEY` | No | Fernet key used to encrypt API tokens (recommended for portability) |
| `DB_FILE` | No | Path to the SQLite database file (default: `bot_data.db`) |
| `CRYPTO_BOT_TOKEN` | No | CryptoBot API token; enables TON payments and starts the webhook server |
| `PUBLIC_URL` | No | Public HTTPS URL used as the CryptoBot callback URL |
| `WEBHOOK_PORT` | No | Port for the CryptoBot webhook server (default: `8080`) |

### Bot Settings (Configurable in Bot)

| Setting | Default | Description |
|---------|---------|-------------|
| Required Channel | None | Channel users must join |
| Log Channel | None | Channel for daily backups |
| Bot Mode | Public | Public or Private access |
| Check Interval | 24h | Default check interval for new repos |

## 📊 Data Storage

All data is stored in a **SQLite database** (`bot_data.db`, configurable via `DB_FILE`):
- User information
- Repository lists
- API tokens (encrypted with Fernet)
- Check intervals
- Last release information
- Last-check timestamps
- Bot settings
- Subscription plans and active subscriptions
- Subscriber channel bindings and download modes

**Backup regularly!** Use the admin panel to download data exports. Note that exported tokens are encrypted — use the same `TOKEN_ENCRYPTION_KEY` when restoring on another deployment.

> **Railway**: add a persistent volume and set `DB_FILE` to a path inside it so the database survives redeploys.

## 🛠️ Troubleshooting

### Bot Not Responding
- Check if `BOT_TOKEN` and `OWNER_ID` are set correctly
- Verify bot is running: look for "Bot started successfully!" in logs
- Ensure you've started a chat with the bot in Telegram

### No Notifications Received
- Verify you've set the correct API token (GitHub or GitLab)
- Check if repository has releases
- Ensure check interval has passed
- Use "🔄 Check Now" to manually trigger

### Channel Membership Issues
- Make sure bot is administrator in the required channel (for private channels the bot also needs invite-link permission to generate a link with `auto`)
- Verify channel username is correct (include `@`)
- For private channels, set the channel ID and invite link in the admin panel
- Click "✅ Check Membership" after joining
- Use the "Joined via bot link" counter in the admin panel to monitor how many users joined

### API Rate Limits
- GitHub: 5000 requests/hour with token
- GitLab: Varies by token type
- Use longer check intervals to avoid limits

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- Uses GitHub API and GitLab API
- Inspired by the need for instant release notifications

## 🔗 Links

- **GitHub Repository**: https://github.com/hossein-bozorg-zadeh/GRMTB
- **Bot Demo**: [@gitchekerbot](https://t.me/gitchekerbot)

---

Made with ❤️ by AI

**Star ⭐ this repository if you find it useful!**
