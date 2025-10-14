🤖 Telegram GitHub Release Monitor Bot

This is a unified, 24/7 Telegram bot designed to monitor GitHub repositories for new releases and send instant notifications to your specified Telegram chat. The bot manages its configuration (repository list and update schedules) entirely through Telegram commands.

The bot runs on a single Python script using APScheduler to handle the background worker job, ensuring continuous monitoring.
⚙️ Deployment & Setup Tutorial
Step 1: Prerequisites

Before running the bot, you must gather all necessary credentials.

    A Private Server (VPS, Cloud Instance, etc.) that can run Python 3.8+ 24/7.

    Telegram Credentials:

        Bot Token (TELEGRAM_BOT_TOKEN): Obtain this from @BotFather.

        Chat ID (TELEGRAM_CHAT_ID): Get the ID of your target chat (personal or group) by forwarding a message to @getmyid_bot. Group/channel IDs start with a negative sign (e.g., -1234567890).

    Firebase Credentials (from your environment):

        App ID (APP_ID): The value of the __app_id string.

        Bot User ID (BOT_USER_ID): A consistent, unique ID you define (e.g., your Telegram username) to scope your data in Firestore.

        Firebase Config JSON (FIREBASE_CONFIG_JSON): The entire JSON string of the __firebase_config.

    GitHub Token (Optional but Recommended):

        GitHub PAT (GITHUB_PAT): Create a Personal Access Token on GitHub with no permissions (it just needs to exist to raise your GitHub API rate limit from 60 to 5,000 requests per hour).

Step 2: Install Dependencies

    Clone this repository to your private server:

    git clone [your_repo_url]
    cd [your_repo_folder_name]

    Install the required Python libraries:

    pip install python-telegram-bot firebase-admin requests apscheduler

Step 3: Configure Environment Variables (CRITICAL)

The bot requires these variables to be set in your server's environment. You must execute these export commands before running the Python script.

# Set required variables
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
export TELEGRAM_CHAT_ID="YOUR_CHAT_ID_HERE"
export APP_ID="YOUR_APP_ID_HERE"
export BOT_USER_ID="YOUR_UNIQUE_USER_ID"

# The FIREBASE_CONFIG_JSON must be the entire JSON object as a single string.
export FIREBASE_CONFIG_JSON='{"type": "service_account", "project_id": "...", "private_key_id": "...", "client_email": "..."}' 

# Set optional variable (Highly Recommended)
export GITHUB_PAT="YOUR_PAT_HERE"

Step 4: Run the Bot 24/7

Start the Python script. Use a process manager like nohup or screen / tmux to ensure the bot remains running after you close your terminal.

# Starts the bot in the background and redirects output to nohup.out
nohup python telegram_bot.py &

Your Telegram Bot is now running: it handles commands instantly and the background worker starts checking for releases every 30 minutes.
💡 Bot Command Panel Usage

Interact with the bot using these commands in your Telegram chat:

Command
	

Usage Example
	

Functionality

/start
	

/start
	

Displays the welcome message and command summary.

/add
	

/add owner/repository
	

Adds a new repository to monitor. The default check interval is 24 hours.

/set_interval
	

/set_interval owner/repo 48
	

Changes the check frequency to the specified number of hours (e.g., 48 hours, 72 hours).

/list
	

/list
	

Shows all currently monitored repositories, their last detected tag, and their set check interval.

/delete
	

/delete owner/repo
	

Stops monitoring the repository and removes it from the database.
