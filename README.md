# GitHub Release Monitor Telegram Bot

A Python-powered Telegram bot that automatically monitors GitHub repositories for new releases and notifies subscribed users in real-time. The bot supports multi-user subscriptions, admin controls, and scheduled background checks using APScheduler.

---

## 📖 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Commands](#commands)
- [Admin Commands](#admin-commands)
- [Installation](#installation)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [File Structure](#file-structure)
- [Detailed Walkthrough](#detailed-walkthrough)
- [Future Improvements](#future-improvements)
- [License](#license)

---

## 🧩 Overview

This bot lets Telegram users track GitHub repositories and receive automatic updates whenever a new release is published. It can handle multiple repositories per user and runs periodic background checks to detect changes using the official GitHub API.

---

## ✨ Features

- Subscribe/unsubscribe to any public GitHub repository.
- Receive Telegram notifications for new releases.
- List and manage your tracked repositories.
- Persistent data storage using JSON (`bot_data.json`).
- Background monitoring via `APScheduler`.
- Admin panel for bot control (ban, unban, broadcast, etc.).
- Lightweight, asynchronous, and reliable.

---

## 💬 Commands

| Command | Description |
|----------|-------------|
| `/start` | Start the bot and display a welcome message. |
| `/help` | Show available commands and usage guide. |
| `/add <owner/repo>` | Add a GitHub repository to your watch list. |
| `/remove <owner/repo>` | Stop tracking a specific repository. |
| `/list` | Show all repositories you’re currently watching. |
| `/check` | Force an immediate check for new releases. |
| `/about` | Learn about the bot and its developer. |

---

## 👑 Admin Commands

> Admin-only features are protected and available only to users listed as admins in the configuration.

| Command | Description |
|----------|-------------|
| `/broadcast <message>` | Send a message to all users. |
| `/ban <user_id>` | Restrict a user from using the bot. |
| `/unban <user_id>` | Remove ban for a specific user. |
| `/stats` | Display total users, repositories, and system uptime. |
| `/mode` | Toggle maintenance or debug mode. |

---

## ⚙️ Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/hossein-bozorg-zadeh/GitHub-Release-Monitor-Telegram-Bot.git
   cd GitHub-Release-Monitor-Telegram-Bot
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

   **Contents of `requirements.txt`:**
   ```
   python-telegram-bot==20.8
   APScheduler==3.10.4
   requests==2.31.0
   python-dotenv==1.0.1
   aiohttp==3.9.5
   ```

4. **Set up environment variables:**

   Create a `.env` file or export these variables:

   ```bash
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   GITHUB_API_TOKEN=your_github_token_here
   ADMIN_IDS=123456789,987654321  # comma-separated list of Telegram admin IDs
   ```

5. **Run the bot:**

   ```bash
   python telegram_bot.py
   ```

---

## 🧠 How It Works

1. **User Interaction:**  
   Users interact with the bot through Telegram commands.

2. **Data Storage:**  
   The bot keeps track of user subscriptions and repository states in `bot_data.json`.

3. **Release Checking:**  
   Every few minutes, the bot checks GitHub repositories using the GitHub API and compares the latest release tag with the last stored one.

4. **Notifications:**  
   If a new release is detected, the bot automatically sends a formatted message to all subscribed users.

5. **Scheduler:**  
   APScheduler runs in the background to handle recurring release checks without blocking Telegram updates.

---

## 🗂️ File Structure

```
GitHub-Release-Monitor-Telegram-Bot/
│
├── telegram_bot.py        # Main bot source code
├── bot_data.json          # Persistent user and repository data
├── requirements.txt       # Dependencies
├── .env                   # Environment variables (not committed)
└── README.md              # This file
```

---

## 🧩 Detailed Walkthrough

### 1. Telegram Command Handlers

All user commands are defined as async functions and registered via `CommandHandler`. The bot responds dynamically to user input and maintains a conversational interface.

### 2. GitHub API Polling

The bot uses asynchronous requests to GitHub’s REST API (`https://api.github.com/repos/<owner>/<repo>/releases/latest`).

Each repository entry is stored with its last known release tag, so duplicate notifications are prevented.

### 3. APScheduler Background Jobs

A background scheduler periodically invokes a `check_releases()` function that polls all tracked repositories and updates users accordingly.

### 4. Admin Panel

Admin users can manage others, broadcast messages, and toggle bot modes — all protected via Telegram user ID authentication.

### 5. Persistent Storage

`bot_data.json` stores all subscriptions and metadata in this structure:

```json
{
  "users": {
    "123456": {
      "repos": ["owner1/repo1", "owner2/repo2"]
    }
  },
  "banned_users": [],
  "settings": { "maintenance": false }
}
```

---

## 🚀 Future Improvements

- Add inline buttons for easier repo management.
- Integrate with GitHub webhooks for real-time updates.
- Add analytics dashboard for admins.
- Support for private repositories.
- Add localization and multi-language support.

---

## 📜 License

This project is licensed under the MIT License. You are free to modify, distribute, and use it for both personal and commercial purposes.

---

### 🧑‍💻 Author
**Hossein Bozorg Zadeh**  
GitHub: [hossein-bozorg-zadeh](https://github.com/hossein-bozorg-zadeh)

---

**⭐ If you find this bot useful, please give it a star on GitHub!**

