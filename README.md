# GitHub Release Monitor Telegram Bot

A Python-powered Telegram bot that automatically monitors GitHub repositories for new releases and notifies subscribed users in real-time. The bot supports multi-user subscriptions, admin controls, and scheduled background checks using APScheduler.

---

## 📖 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Usage](#usage)
- [Owner Panel](#owner-panel)
- [Installation](#installation)
- [Configuration](#configuration)
- [Data Persistence](#data-persistence)
- [File Structure](#file-structure)
- [License](#license)

---

## 🧩 Overview

This bot lets Telegram users track GitHub repositories and receive automatic updates whenever a new release is published. It can handle multiple repositories per user and runs periodic background checks to detect changes using the official GitHub API. The bot uses a modern inline keyboard interface for all interactions.

---

## ✨ Features

- **Add & Remove Repositories**: Easily add and remove repositories from your watch list.
- **Interactive Menu**: All actions are handled through an intuitive inline keyboard menu.
- **Custom Check Intervals**: Set a custom check interval for each repository.
- **Manual & Scheduled Checks**: Trigger a manual check for all your repositories at any time, or rely on the background scheduler.
- **GitHub Token Support**: Add your GitHub personal access token to get higher API rate limits and access private repositories.
- **Owner-Only Admin Panel**: A secure owner panel to manage users and the bot's settings.
- **User Management**: Ban, unban, and manage special users who can use the bot in private mode.
- **Broadcast System**: Send a message to all users of the bot.
- **Public/Private Mode**: Control who can use the bot.

---

## 💬 Usage

Start a conversation with the bot and use the inline keyboard to navigate through the options.

| Button | Description |
|----------|-------------|
| ➕ Add Repository | Add a new GitHub repository to your watch list. |
| 📋 My Repositories | View a list of all the repositories you are currently tracking. |
| ➖ Delete Repository | Remove a repository from your watch list. |
| ⏰ Set Check Interval | Set a custom check interval for a repository. |
| 🔍 Check All My Repos Now | Manually trigger a release check for all your repositories. |
| 🔑 Set GitHub Token | Add or update your GitHub personal access token. |

---

## 👑 Owner Panel

The owner panel is only accessible to the `OWNER_ID` configured in the `telegram_bot.py` file.

| Button | Description |
|----------|-------------|
| Mode: Public/Private | Toggle the bot's public/private mode. |
| 📢 Broadcast Message | Send a message to all users. |
| 👥 Manage Users | Ban, unban, and manage special users. |

---

## ⚙️ Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-username/your-repo-name.git
   cd your-repo-name
   ```

2. **Create a virtual environment (optional but recommended):**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the bot:**

    Open `telegram_bot.py` and set your `BOT_TOKEN` and `OWNER_ID` at the top of the file.

5. **Run the bot:**

   ```bash
   python telegram_bot.py
   ```

---

## 🔧 Configuration

The bot is configured by setting the `BOT_TOKEN` and `OWNER_ID` variables directly in the `telegram_bot.py` script.

---

## 💾 Data Persistence

The bot stores all user data, including tracked repositories and settings, in a `bot_data.json` file.

**This file is created automatically** in the same directory as the script when the bot is first run. The script requires write permissions in its directory to create and update this file.

The data structure is as follows:

```json
{
    "settings": {
        "is_public": false
    },
    "users": {
        "123456789": {
            "repos": {
                "owner/repo": {
                    "url": "https://github.com/owner/repo",
                    "interval_hours": 24,
                    "last_release_id": 12345678
                }
            },
            "github_token": "your_github_token"
        }
    },
    "special_users": [],
    "banned_users": []
}
```

---

## 🗂️ File Structure

```
.
├── telegram_bot.py        # Main bot source code
├── bot_data.json          # Persistent user and repository data (created on first run)
├── requirements.txt       # Dependencies
└── README.md              # This file
```

---

## 📜 License

This project is licensed under the MIT License. You are free to modify, distribute, and use it for both personal and commercial purposes.