GitHub Release Notifier Telegram Bot

A powerful, multi-user Telegram bot built with Python that monitors GitHub repositories for new releases and sends instant notifications.
🌟 Features

This bot provides a complete solution for both users and the bot owner to track GitHub projects seamlessly.
For Users:

    Personal Repository Lists: Each user manages their own list of repositories to follow.

    Add & Remove Repos: Easily add new repositories via URL or remove existing ones from your list.

    Set Check Intervals: Customize the update check frequency for any repository. (Note: This is a global setting).

    Manual Check: Trigger an immediate check for new releases on all your tracked repos with a single button press.

For the Bot Owner:

    👑 Owner Control Panel: A dedicated admin menu with powerful management tools.

    Public/Private Mode: Switch the bot between being publicly available to everyone or restricted to special users only.

    User Management:

        Ban/Unban: Block or unblock users from accessing the bot.

        Special Users: Grant specific users access to the bot even when it's in private mode.

    Broadcast System: Send update messages or announcements to all active users of the bot.

🛠️ Tech Stack

    Language: Python 3.8+

    Telegram Framework: python-telegram-bot

    Scheduling: apscheduler for periodic release checks.

    HTTP Requests: requests to interact with the GitHub API.

🚀 Getting Started

To get your own instance of this bot running, you will need a Linux server, a Telegram account, and Python 3.8+.

For a complete, step-by-step guide on setup, configuration, and deployment (including how to host the code on GitHub), please refer to the Full Setup and Hosting Tutorial.
Quick Configuration

The bot is configured using environment variables for security. You must set the following before running the script:

export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
export OWNER_ID="YOUR_TELEGRAM_USER_ID"

Running the Bot

    Clone the repository.

    Install the dependencies: pip install -r requirements.txt

    Set the environment variables as shown above.

    Run the bot: python github_release_bot.py
