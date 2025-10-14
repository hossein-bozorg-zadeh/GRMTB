import os
import json
import logging
import requests
import time
from datetime import datetime, timedelta

# Core Telegram Bot Library
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Firebase Admin SDK for persistent Firestore access
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

# APScheduler for background job execution (the 24/7 worker/cron part)
from apscheduler.schedulers.background import BackgroundScheduler

# --- 1. CONFIGURATION AND INITIALIZATION ---

# Set up basic logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables (These MUST be set on your persistent server)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GITHUB_PAT = os.environ.get("GITHUB_PAT") # Optional, but recommended for higher rate limits
APP_ID = os.environ.get("APP_ID")
BOT_USER_ID = os.environ.get("BOT_USER_ID")
FIREBASE_CONFIG_JSON = os.environ.get("FIREBASE_CONFIG_JSON")

# Ensure all critical variables are set
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, APP_ID, BOT_USER_ID, FIREBASE_CONFIG_JSON]):
    logger.error("Missing critical environment variables. The bot cannot start.")
    exit(1)

# Initialize Firebase Firestore
try:
    # Load the Firebase configuration JSON string from the environment variable
    cred = credentials.Certificate(json.loads(FIREBASE_CONFIG_JSON)) 
    initialize_app(cred)
    db = firestore.client()
    logger.info("Firebase Firestore initialized successfully.")
except Exception as e:
    logger.error(f"Error initializing Firebase. Check FIREBASE_CONFIG_JSON format. Error: {e}")
    exit(1)

# --- 2. FIREBASE & GITHUB HELPER FUNCTIONS ---

def get_repo_collection_ref():
    """Returns the Firestore collection reference for the bot's data scope."""
    # MANDATORY PATH STRUCTURE for private user data
    collection_path = f"artifacts/{APP_ID}/users/{BOT_USER_ID}/monitored_repos"
    return db.collection(collection_path)

def get_github_headers():
    """Returns headers for GitHub API requests, including PAT if available."""
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if GITHUB_PAT:
        headers['Authorization'] = f'token {GITHUB_PAT}'
    return headers

def fetch_latest_release(repo_name):
    """Fetches the latest release data from the GitHub API."""
    url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    try:
        response = requests.get(url, headers=get_github_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            'tag_name': data.get('tag_name'),
            'html_url': data.get('html_url'),
            'published_at': data.get('published_at'),
            'name': data.get('name')
        }
    except requests.exceptions.RequestException as e:
        if response.status_code == 404 and "Not Found" in str(e):
             logger.warning(f"No releases found or repo {repo_name} not accessible.")
             return {'tag_name': 'N/A_NO_RELEASE'}
        logger.error(f"GitHub API error for {repo_name}: {e}")
        return None

def send_telegram_message_sync(message: str):
    """Sends a notification message to the configured Telegram chat (blocking call)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram notification: {e}")

# --- 3. TELEGRAM COMMAND HANDLERS (Control Panel) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instructions."""
    message = (
        "🚀 **GitHub Release Monitor Bot**\n\n"
        "I monitor your specified repositories and send new release alerts to this chat.\n\n"
        "**Control Panel Commands:**\n"
        "• `/add <owner/repo>`: Start monitoring (Default: **24h**).\n"
        "• `/list`: Show all monitored repositories.\n"
        "• `/set_interval <owner/repo> <hours>`: Change the check frequency.\n"
        "• `/delete <owner/repo>`: Stop monitoring a repository."
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def add_repo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a repository to the monitoring list with a default 24h interval."""
    if not context.args or context.args[0].count('/') != 1:
        await update.message.reply_text("Usage: `/add <owner/repo>` (e.g., `/add google/gemini-api-python`)")
        return

    repo_name = context.args[0].strip()
    release_data = fetch_latest_release(repo_name)

    if release_data is None:
        await update.message.reply_text(f"❌ Failed to access GitHub API for `{repo_name}`. Check repo name or API limits.", parse_mode='Markdown')
        return

    repo_doc_id = repo_name.replace('/', '_')
    repo_ref = get_repo_collection_ref().document(repo_doc_id)
    
    try:
        initial_tag = release_data.get('tag_name') or 'N/A' 
        
        repo_ref.set({
            'repo_name': repo_name,
            'last_tag': initial_tag,
            'interval_hours': 24,  # DEFAULT CHECK TIME IS 24 HOURS
            'last_checked': firestore.SERVER_TIMESTAMP
        })
        message = (
            f"✅ Started monitoring `{repo_name}`.\n"
            f"Initial Tag: `{initial_tag}`\n"
            f"Check Interval: **24 hours** (Default)."
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error adding repo to Firestore: {e}")
        await update.message.reply_text(f"❌ An error occurred while saving to the database.")

async def list_repos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all monitored repositories."""
    repo_ref = get_repo_collection_ref()
    try:
        docs = repo_ref.stream()
        repos = []
        for doc in docs:
            data = doc.to_dict()
            last_checked_dt = data.get('last_checked')
            
            last_checked_str = "N/A"
            if last_checked_dt and hasattr(last_checked_dt, 'strftime'):
                last_checked_str = last_checked_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

            repos.append(
                f"• `{data['repo_name']}`\n"
                f"  - **Interval:** {data.get('interval_hours', 'N/A')}h\n"
                f"  - **Last Tag:** `{data.get('last_tag', 'N/A')}`\n"
                f"  - **Last Check:** {last_checked_str}"
            )
        
        if repos:
            message = "📝 **Monitored Repositories:**\n" + "\n".join(repos)
        else:
            message = "You are not currently monitoring any repositories. Use `/add <owner/repo>`."
        
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error listing repos: {e}")
        await update.message.reply_text("❌ An error occurred while retrieving the list from the database.")

async def delete_repo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes a repository from the monitoring list."""
    if not context.args:
        await update.message.reply_text("Usage: `/delete <owner/repo>`")
        return

    repo_name = context.args[0].strip()
    repo_doc_id = repo_name.replace('/', '_')
    repo_ref = get_repo_collection_ref().document(repo_doc_id)
    
    try:
        repo_ref.delete()
        await update.message.reply_text(f"🗑️ Successfully stopped monitoring `{repo_name}`.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error deleting repo: {e}")
        await update.message.reply_text(f"❌ An error occurred while deleting `{repo_name}` from the database.")

async def set_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets a custom check interval (in hours) for a repository."""
    if len(context.args) != 2:
        await update.message.reply_text("Usage: `/set_interval <owner/repo> <hours>` (e.g., `/set_interval owner/repo 72`)")
        return

    repo_name = context.args[0].strip()
    repo_doc_id = repo_name.replace('/', '_')
    
    try:
        interval = int(context.args[1])
        if interval < 1:
            raise ValueError("Interval must be a positive integer.")
    except ValueError:
        await update.message.reply_text("❌ The interval must be a valid number of hours (e.g., 12, 24, 72).")
        return

    repo_ref = get_repo_collection_ref().document(repo_doc_id)
    
    try:
        if not repo_ref.get().exists:
            await update.message.reply_text(f"❌ Repository `{repo_name}` is not currently being monitored. Use `/add` first.", parse_mode='Markdown')
            return

        repo_ref.update({'interval_hours': interval})
        await update.message.reply_text(f"⏱️ Updated check interval for `{repo_name}` to **{interval} hours**.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error setting interval: {e}")
        await update.message.reply_text("❌ An error occurred while updating the interval.")

# --- 4. SCHEDULER FUNCTION (THE 24/7 WORKER) ---

def check_for_releases():
    """The main scheduled job to check all user's repositories for new releases."""
    repo_ref = get_repo_collection_ref()
    
    try:
        docs = repo_ref.stream()
        current_time = datetime.utcnow()
        
        logger.info(f"--- Starting periodic release check ---")

        for doc in docs:
            repo_data = doc.to_dict()
            repo_id = doc.id
            repo_name = repo_data['repo_name']
            
            last_checked_ts = repo_data.get('last_checked')
            interval_hours = repo_data.get('interval_hours', 24)
            
            # --- Custom Polling Logic: Check if the interval has passed ---
            is_due = True
            if last_checked_ts:
                # Convert Firestore Timestamp to UTC datetime object
                last_checked_dt = last_checked_ts.replace(tzinfo=None) 
                check_interval = timedelta(hours=interval_hours)
                next_check_time = last_checked_dt + check_interval
                
                if current_time < next_check_time:
                    is_due = False
            
            if not is_due:
                logger.info(f"[SKIP] {repo_name} - Not due yet (Interval: {interval_hours}h).")
                continue
            
            logger.info(f"[CHECKING] {repo_name} - Check is due.")

            latest_release = fetch_latest_release(repo_name)
            
            if latest_release and latest_release.get('tag_name') and latest_release['tag_name'] != 'N/A_NO_RELEASE':
                new_tag = latest_release['tag_name']
                old_tag = repo_data.get('last_tag')
                
                if new_tag != old_tag:
                    
                    if old_tag is not None:
                        # Found a new release! Send notification.
                        message = (
                            f"🔔 *NEW RELEASE ALERT* 🚀\n"
                            f"Repository: [*{repo_name}*]({latest_release['html_url']})\n"
                            f"Version: `{new_tag}` (was `{old_tag}`)\n"
                            f"Title: {latest_release.get('name', 'N/A')}"
                        )
                        send_telegram_message_sync(message)
                    
                    # Update Firestore with the new tag and check time
                    doc.reference.update({
                        'last_tag': new_tag,
                        'last_checked': firestore.SERVER_TIMESTAMP
                    })
                    logger.info(f"[UPDATE] {repo_name} tag updated to {new_tag}.")
                    
                else:
                    # Same tag, just update the check time to reset the timer
                    doc.reference.update({'last_checked': firestore.SERVER_TIMESTAMP})
                    logger.info(f"[NO CHANGE] {repo_name} tag is still {new_tag}. Check time updated.")
            else:
                 # No valid release found, update last_checked to reset timer
                doc.reference.update({'last_checked': firestore.SERVER_TIMESTAMP})
                logger.warning(f"[ERROR] Could not fetch valid release for {repo_name}. Timer reset.")
            
            time.sleep(0.5) 

        logger.info(f"--- Periodic release check complete ---")

    except Exception as e:
        logger.error(f"Scheduler failed to execute check: {e}")


# --- 5. MAIN BOT EXECUTION ---

def main() -> None:
    """Start the bot (for commands) and the scheduler (for monitoring)."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Setup Bot Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_repo_command))
    application.add_handler(CommandHandler("list", list_repos_command))
    application.add_handler(CommandHandler("delete", delete_repo_command))
    application.add_handler(CommandHandler("set_interval", set_interval_command))

    # Setup the Scheduler (The 24/7 Worker)
    scheduler = BackgroundScheduler()
    # The worker runs every 30 minutes. The logic inside check_for_releases
    # enforces the custom 24h/12h/72h intervals defined in Firestore.
    scheduler.add_job(check_for_releases, 'interval', minutes=30, id='release_checker')
    scheduler.start()
    logger.info("Scheduler started (runs every 30 minutes).")

    # Start the Bot (Long Polling for commands)
    logger.info("Bot is starting polling for commands...")
    # This call blocks the thread and keeps the bot running 24/7
    application.run_polling(poll_interval=1.0, timeout=20)
    
    try:
        scheduler.shutdown()
    except Exception:
        pass


if __name__ == '__main__':
    main()
