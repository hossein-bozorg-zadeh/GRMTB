# -*- coding: utf-8 -*-
# pylint: disable=invalid-name, missing-module-docstring, missing-class-docstring, missing-function-docstring, too-many-lines

import logging
import os
import json
from datetime import datetime, timedelta
import asyncio

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation handlers
(
    AWAIT_REPO_ADD, AWAIT_REPO_DELETE, AWAIT_INTERVAL_REPO, AWAIT_INTERVAL_HOURS,
    AWAIT_BAN_ID, AWAIT_UNBAN_ID, AWAIT_SPECIAL_ID, AWAIT_UNSPECIAL_ID,
    AWAIT_BROADCAST_MESSAGE, AWAIT_BROADCAST_CONFIRM
) = range(10)

# --- Configuration and Data Persistence ---
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # New data structure for multi-user support
    return {
        "settings": {"is_public": False},
        "users": {},
        "special_users": [],
        "banned_users": []
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

bot_data = load_data()

# --- User Access Control ---
def get_or_create_user(user_id: int):
    """Retrieves a user's data, creating it if it doesn't exist."""
    user_id_str = str(user_id)
    if user_id_str not in bot_data["users"]:
        bot_data["users"][user_id_str] = {"repos": {}}
        save_data(bot_data)
        logger.info(f"New user created: {user_id_str}")
    return bot_data["users"][user_id_str]

async def user_is_authorized(update: Update) -> bool:
    """Checks if a user is allowed to use the bot."""
    user = update.effective_user
    if not user:
        return False
        
    if user.id == OWNER_ID:
        return True

    if user.id in bot_data["banned_users"]:
        await update.message.reply_text("You have been banned from using this bot.")
        return False

    if not bot_data["settings"]["is_public"]:
        if user.id not in bot_data["special_users"]:
            await update.message.reply_text("This bot is currently in private mode. Access denied.")
            return False
            
    get_or_create_user(user.id)
    return True

# --- Helper Functions ---
def get_repo_name_from_url(url: str):
    try:
        return "/".join(url.split("/")[-2:])
    except (IndexError, AttributeError):
        return None

def get_all_unique_repos():
    """Gets a set of all unique repository names across all users."""
    unique_repos = set()
    for user_data in bot_data["users"].values():
        for repo_name in user_data["repos"]:
            unique_repos.add(repo_name)
    return unique_repos

def is_repo_tracked_by_anyone(repo_name: str) -> bool:
    """Checks if any user is still tracking a specific repository."""
    for user_data in bot_data["users"].values():
        if repo_name in user_data["repos"]:
            return True
    return False

# --- Core Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await user_is_authorized(update):
        return

    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("➕ Add Repository", callback_data="add_repo")],
        [InlineKeyboardButton("📋 My Repositories", callback_data="list_repos")],
        [InlineKeyboardButton("➖ Delete Repository", callback_data="delete_repo")],
        [InlineKeyboardButton("⏰ Set Check Interval", callback_data="set_interval")],
        [InlineKeyboardButton("🔍 Check All My Repos Now", callback_data="check_now_user")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("GitHub Release Notifier Bot Menu:", reply_markup=reply_markup)

# --- Release Checking Logic ---
async def check_releases(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to check a single repository for new releases."""
    repo_name = context.job.data["repo_name"]
    
    # We need a reference for the last known ID. We'll use the owner's record or the first one we find.
    # This assumes the last_release_id is consistent globally.
    global_repo_info = None
    for user_data in bot_data["users"].values():
        if repo_name in user_data["repos"]:
            global_repo_info = user_data["repos"][repo_name]
            break

    if not global_repo_info:
        logger.warning(f"Job for {repo_name} ran, but no user tracks it. Removing job.")
        context.job.schedule_removal()
        return

    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 404:
            logger.info(f"Repo {repo_name} has no releases yet.")
            return
        response.raise_for_status()
        latest_release = response.json()
        release_id = latest_release.get("id")
        last_known_id = global_repo_info.get("last_release_id")

        if release_id and release_id != last_known_id:
            logger.info(f"New release found for {repo_name}: {latest_release['tag_name']}")
            # Update last_release_id for ALL users tracking this repo
            for user_id_str, user_data in bot_data["users"].items():
                if repo_name in user_data["repos"]:
                    bot_data["users"][user_id_str]["repos"][repo_name]["last_release_id"] = release_id
            save_data(bot_data)
            
            message = (
                f"🚀 **New Release for `{repo_name}`!**\n\n"
                f"**Version:** [{latest_release['tag_name']}]({latest_release['html_url']})\n"
                f"**Name:** {latest_release.get('name') or 'N/A'}\n"
                f"**Published:** {datetime.strptime(latest_release['published_at'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            # Notify all subscribed users
            for user_id_str, user_data in bot_data["users"].items():
                if repo_name in user_data["repos"]:
                    try:
                        await context.bot.send_message(chat_id=int(user_id_str), text=message, parse_mode="Markdown")
                    except error.Forbidden:
                        logger.warning(f"User {user_id_str} has blocked the bot. Cannot send notification.")
                    except Exception as e:
                        logger.error(f"Failed to send message to {user_id_str}: {e}")
        else:
            logger.info(f"No new release for {repo_name}.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking {repo_name}: {e}")

async def check_now_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually checks all repositories for the requesting user."""
    query = update.callback_query
    await query.answer(text="🔍 Checking your repositories now...")
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)

    if not user_data["repos"]:
        await query.edit_message_text("You are not tracking any repositories.", reply_markup=main_menu_markup())
        return

    checked_repos = 0
    for repo_name in user_data["repos"]:
        class MockJob:
            def __init__(self, data):
                self.data = data
        
        mock_job = MockJob(data={"repo_name": repo_name})
        # Temporarily modify the job's target chat_id to the current user
        # This is a bit of a hack to reuse the check_releases logic for a single user
        async def single_user_check():
            api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
            try:
                response = requests.get(api_url, timeout=10)
                response.raise_for_status()
                latest_release = response.json()
                release_id = latest_release.get("id")
                last_known_id = user_data["repos"][repo_name].get("last_release_id")
                if release_id and release_id != last_known_id:
                    user_data["repos"][repo_name]["last_release_id"] = release_id
                    save_data(bot_data)
                    message = (
                        f"🚀 New Release for `{repo_name}`!\n\n"
                        f"**Version:** [{latest_release['tag_name']}]({latest_release['html_url']})\n"
                        f"**Name:** {latest_release['name']}\n"
                        f"**Published:** {datetime.strptime(latest_release['published_at'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                    await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in single_user_check for {repo_name}: {e}")

        await single_user_check()
        checked_repos += 1
    
    await context.bot.send_message(chat_id=user_id, text=f"✅ Finished checking your {checked_repos} repositories.")


# --- Job Scheduling ---
def schedule_repo_check(scheduler: AsyncIOScheduler, repo_name: str, interval_hours: int):
    """Schedules a global check job for a unique repository."""
    job_id = f"check_{repo_name.replace('/', '_')}"
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger="interval", hours=interval_hours)
        logger.info(f"Rescheduled job for {repo_name} to every {interval_hours} hours.")
    else:
        scheduler.add_job(
            check_releases,
            "interval",
            hours=interval_hours,
            id=job_id,
            data={"repo_name": repo_name},
            next_run_time=datetime.now() + timedelta(seconds=10)
        )
        logger.info(f"Scheduled new job for {repo_name} every {interval_hours} hours.")

def unschedule_if_unused(scheduler: AsyncIOScheduler, repo_name: str):
    """Removes a scheduled job if no user is tracking the repo anymore."""
    if not is_repo_tracked_by_anyone(repo_name):
        job_id = f"check_{repo_name.replace('/', '_')}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Unscheduled and removed job for {repo_name} as it's no longer tracked.")

# --- Conversation Handlers and Callbacks for Users ---
async def add_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await user_is_authorized(update): return ConversationHandler.END
    user_data = get_or_create_user(user_id)

    repo_url = update.message.text
    repo_name = get_repo_name_from_url(repo_url)

    if not repo_name or len(repo_name.split('/')) != 2:
        await update.message.reply_text("Invalid GitHub URL format. Please use `https://github.com/owner/repo`.", parse_mode='Markdown')
        return ConversationHandler.END

    if repo_name in user_data["repos"]:
        await update.message.reply_text(f"You are already tracking `{repo_name}`.", parse_mode='Markdown')
        return ConversationHandler.END

    api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        latest_release = response.json()
        last_release_id = latest_release.get("id")
    except requests.exceptions.RequestException:
        last_release_id = None
        await update.message.reply_text(f"Warning: Could not fetch initial release for `{repo_name}`. It will be tracked from the next new release.", parse_mode='Markdown')

    user_data["repos"][repo_name] = {
        "url": f"https://github.com/{repo_name}",
        "interval_hours": 24, # User-specific interval, though job runs on its own schedule
        "last_release_id": last_release_id,
    }
    save_data(bot_data)
    # The job interval is global. We just use the default of 24h for new jobs.
    schedule_repo_check(context.application.job_queue.scheduler, repo_name, 24)
    await update.message.reply_text(f"✅ Repository `{repo_name}` added to your list with a default 24-hour check interval.", parse_mode='Markdown', reply_markup=main_menu_markup())
    return ConversationHandler.END

async def list_repos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)

    if not user_data["repos"]:
        await query.edit_message_text("You are not tracking any repositories.", reply_markup=main_menu_markup())
        return

    message = "📋 Your Tracked Repositories:\n\n"
    for repo, info in user_data["repos"].items():
        message += f"- `{repo}` (Interval: {info['interval_hours']}h)\n"

    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=main_menu_markup())

async def prompt_delete_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)
    
    if not user_data["repos"]:
        await query.edit_message_text("You have no repositories to delete.", reply_markup=main_menu_markup())
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(repo, callback_data=f"del_repo_{repo}")]
        for repo in user_data["repos"]
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text("Select a repository to remove from your list:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAIT_REPO_DELETE

async def handle_delete_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)
    repo_name = query.data.split("_", 2)[2]

    if repo_name in user_data["repos"]:
        del user_data["repos"][repo_name]
        save_data(bot_data)
        unschedule_if_unused(context.application.job_queue.scheduler, repo_name)
        await query.edit_message_text(f"🗑️ Repository `{repo_name}` has been removed from your list.", parse_mode='Markdown', reply_markup=main_menu_markup())
    else:
        await query.edit_message_text(f"Repository `{repo_name}` not found in your list.", parse_mode='Markdown', reply_markup=main_menu_markup())
    return ConversationHandler.END

async def prompt_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)

    if not user_data["repos"]:
        await query.edit_message_text("You have no repositories to configure.", reply_markup=main_menu_markup())
        return ConversationHandler.END
        
    keyboard = [
        [InlineKeyboardButton(f"{repo} ({info['interval_hours']}h)", callback_data=f"set_interval_{repo}")]
        for repo, info in user_data["repos"].items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text("Select one of your repositories to set a new check interval:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAIT_INTERVAL_REPO

async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_or_create_user(user_id)
    try:
        hours = int(update.message.text)
        if hours <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid positive number for the hours.")
        return AWAIT_INTERVAL_HOURS

    repo_name = context.user_data.get("repo_to_set_interval")
    if repo_name and repo_name in user_data["repos"]:
        user_data["repos"][repo_name]["interval_hours"] = hours
        save_data(bot_data)
        # Reschedule the global job with the new interval
        schedule_repo_check(context.application.job_queue.scheduler, repo_name, hours)
        await update.message.reply_text(f"⏰ Global check interval for `{repo_name}` updated to {hours} hours. This affects all users tracking this repo.", parse_mode='Markdown')
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("Could not find the repository to update. Please try again.", reply_markup=main_menu_markup())
        return ConversationHandler.END

# --- Owner Panel ---
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.effective_user.id != OWNER_ID:
        await query.answer("Access Denied.", show_alert=True)
        return

    is_public_text = "✅ Public" if bot_data['settings']['is_public'] else "❌ Private"
    keyboard = [
        [InlineKeyboardButton(f"Mode: {is_public_text}", callback_data="toggle_public")],
        [InlineKeyboardButton("Broadcast Update Message", callback_data="broadcast_message")],
        [InlineKeyboardButton("Manage Users", callback_data="manage_users")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")],
    ]
    await query.edit_message_text("👑 Owner Control Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_public_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    bot_data['settings']['is_public'] = not bot_data['settings']['is_public']
    save_data(bot_data)
    await query.answer(f"Bot is now {'Public' if bot_data['settings']['is_public'] else 'Private'}.")
    await owner_panel(update, context) # Refresh panel

async def manage_users_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    stats = (
        f"Total Users: {len(bot_data['users'])}\n"
        f"Special Users: {len(bot_data['special_users'])}\n"
        f"Banned Users: {len(bot_data['banned_users'])}"
    )
    keyboard = [
        [InlineKeyboardButton("🚫 Ban User", callback_data="ban_user")],
        [InlineKeyboardButton("✅ Unban User", callback_data="unban_user")],
        [InlineKeyboardButton("⭐ Add Special User", callback_data="add_special")],
        [InlineKeyboardButton("⚪ Remove Special User", callback_data="remove_special")],
        [InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_panel")],
    ]
    await query.edit_message_text(f"User Management\n\n{stats}", reply_markup=InlineKeyboardMarkup(keyboard))

# --- User Management Conversations ---
async def prompt_for_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    """Generic function to ask for a user ID for an action."""
    query = update.callback_query
    await query.edit_message_text(f"Please send the Telegram User ID of the user to {action}.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        if user_id == OWNER_ID:
            await update.message.reply_text("You cannot ban the owner.")
        elif user_id not in bot_data["banned_users"]:
            bot_data["banned_users"].append(user_id)
            if user_id in bot_data["special_users"]: # Banning removes special status
                bot_data["special_users"].remove(user_id)
            save_data(bot_data)
            await update.message.reply_text(f"🚫 User `{user_id}` has been banned.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"User `{user_id}` is already banned.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Invalid User ID.")
    return ConversationHandler.END

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        if user_id in bot_data["banned_users"]:
            bot_data["banned_users"].remove(user_id)
            save_data(bot_data)
            await update.message.reply_text(f"✅ User `{user_id}` has been unbanned.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"User `{user_id}` is not banned.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Invalid User ID.")
    return ConversationHandler.END

async def add_special_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        if user_id in bot_data["banned_users"]:
            await update.message.reply_text("You cannot make a banned user special. Unban them first.")
        elif user_id not in bot_data["special_users"]:
            bot_data["special_users"].append(user_id)
            save_data(bot_data)
            await update.message.reply_text(f"⭐ User `{user_id}` is now a special user.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"User `{user_id}` is already a special user.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Invalid User ID.")
    return ConversationHandler.END

async def remove_special_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        if user_id in bot_data["special_users"]:
            bot_data["special_users"].remove(user_id)
            save_data(bot_data)
            await update.message.reply_text(f"⚪ Special status removed for user `{user_id}`.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"User `{user_id}` is not a special user.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Invalid User ID.")
    return ConversationHandler.END

# --- Broadcast Conversation ---
async def broadcast_message_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("Please send the update message you want to broadcast to all users. Markdown is supported.")
    return AWAIT_BROADCAST_MESSAGE

async def broadcast_message_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    context.user_data['broadcast_message'] = message_text
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Send Now", callback_data="broadcast_send")],
        [InlineKeyboardButton("❌ Cancel", callback_data="owner_panel")],
    ]
    await update.message.reply_text(f"**Broadcast Preview:**\n\n---\n{message_text}\n---\n\nAre you sure you want to send this to all users?", 
                                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return AWAIT_BROADCAST_CONFIRM

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("Broadcasting message...", reply_markup=None)
    
    message_text = context.user_data.get('broadcast_message')
    if not message_text:
        await query.edit_message_text("Error: Message not found. Aborting.", reply_markup=owner_panel_markup())
        return ConversationHandler.END

    all_users = [int(uid) for uid in bot_data['users'].keys() if int(uid) not in bot_data['banned_users']]
    sent_count = 0
    failed_count = 0

    for user_id in all_users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")
            sent_count += 1
        except (error.Forbidden, error.BadRequest):
            failed_count += 1
            logger.warning(f"Failed to send broadcast to {user_id} (user blocked or invalid).")
        await asyncio.sleep(0.1) # Avoid hitting rate limits

    report = f"📢 Broadcast Complete!\n\nSent: {sent_count}\nFailed: {failed_count}"
    await query.edit_message_text(report, reply_markup=owner_panel_markup())
    context.user_data.clear()
    return ConversationHandler.END

# --- General Handlers ---
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    keyboard = [
        [InlineKeyboardButton("➕ Add Repository", callback_data="add_repo")],
        [InlineKeyboardButton("📋 My Repositories", callback_data="list_repos")],
        [InlineKeyboardButton("➖ Delete Repository", callback_data="delete_repo")],
        [InlineKeyboardButton("⏰ Set Check Interval", callback_data="set_interval")],
        [InlineKeyboardButton("🔍 Check All My Repos Now", callback_data="check_now_user")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])
    await query.edit_message_text("GitHub Release Notifier Bot Menu:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main router for callback queries."""
    query = update.callback_query
    await query.answer()

    # User Actions
    if query.data == "main_menu": await main_menu_handler(update, context)
    elif query.data == "add_repo":
        await query.edit_message_text("Please send the full GitHub repository URL (e.g., https://github.com/owner/repo).")
        return AWAIT_REPO_ADD
    elif query.data == "list_repos": await list_repos(update, context)
    elif query.data == "delete_repo": return await prompt_delete_repo(update, context)
    elif query.data == "set_interval": return await prompt_set_interval(update, context)
    elif query.data == "check_now_user": await check_now_user(update, context)
    
    # Owner Actions
    elif query.data == "owner_panel": await owner_panel(update, context)
    elif query.data == "toggle_public": await toggle_public_mode(update, context)
    elif query.data == "manage_users": await manage_users_panel(update, context)
    elif query.data == "ban_user": 
        await prompt_for_user_id(update, context, "ban")
        return AWAIT_BAN_ID
    elif query.data == "unban_user": 
        await prompt_for_user_id(update, context, "unban")
        return AWAIT_UNBAN_ID
    elif query.data == "add_special": 
        await prompt_for_user_id(update, context, "add as special")
        return AWAIT_SPECIAL_ID
    elif query.data == "remove_special": 
        await prompt_for_user_id(update, context, "remove from special")
        return AWAIT_UNSPECIAL_ID
    elif query.data == "broadcast_message": return await broadcast_message_prompt(update, context)

    # Conversation step handlers (that aren't just message inputs)
    elif query.data.startswith("del_repo_"): return await handle_delete_repo(update, context)
    elif query.data.startswith("set_interval_"):
        repo_name = query.data.split("_", 2)[2]
        context.user_data["repo_to_set_interval"] = repo_name
        await query.edit_message_text(f"Enter the new check interval in hours for `{repo_name}`.\n\nNote: This is a global setting for this repository.", parse_mode='Markdown')
        return AWAIT_INTERVAL_HOURS
    elif query.data == "broadcast_send": return await broadcast_send(update, context)


def main_menu_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]])

def owner_panel_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_panel")]])

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    if not BOT_TOKEN or not OWNER_ID:
        raise ValueError("BOT_TOKEN and OWNER_ID environment variables must be set.")

    application = Application.builder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Reschedule jobs from saved data on startup
    unique_repos = get_all_unique_repos()
    if unique_repos:
        logger.info(f"Rescheduling jobs for {len(unique_repos)} unique repositories...")
        for repo_name in unique_repos:
            # Find an interval for this repo, defaults to 24h if inconsistent
            interval = 24
            for user_data in bot_data["users"].values():
                if repo_name in user_data["repos"]:
                    interval = user_data["repos"][repo_name].get("interval_hours", 24)
                    break
            schedule_repo_check(scheduler, repo_name, interval)
    
    scheduler.start()
    # This line is crucial to link the application with the scheduler
    application.job_queue.set_scheduler(scheduler)
    
    # --- Conversation Handler Setup ---
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            AWAIT_REPO_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_repo)],
            AWAIT_REPO_DELETE: [CallbackQueryHandler(handle_delete_repo, pattern="^del_repo_")],
            AWAIT_INTERVAL_REPO: [CallbackQueryHandler(button_handler, pattern="^set_interval_")],
            AWAIT_INTERVAL_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_interval)],
            AWAIT_BAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user)],
            AWAIT_UNBAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user)],
            AWAIT_SPECIAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_special_user)],
            AWAIT_UNSPECIAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_special_user)],
            AWAIT_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_confirm)],
            AWAIT_BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_send, pattern="^broadcast_send$")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(owner_panel, pattern="^owner_panel$"),
            CallbackQueryHandler(main_menu_handler, pattern="^main_menu$")
        ],
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler)) # Fallback for any buttons missed

    logger.info("Bot started successfully!")
    application.run_polling()


if __name__ == "__main__":
    main()

