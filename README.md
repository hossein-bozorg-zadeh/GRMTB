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
- **Download Integration**: Download release assets directly through Telegram (files < 50MB)
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
```

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
6. Deploy! ✨

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
2. If files are available, click the download button
3. Files under 50MB are sent directly via Telegram
4. Larger files show a direct download link

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

### Automatic Backups

If you set a log channel:
- Bot data is automatically backed up every 24 hours
- Log files are sent to the channel
- Keeps your data safe without manual intervention

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
