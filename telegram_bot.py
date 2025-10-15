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
    AWAIT_BROADCAST_MESSAGE, AWAIT_BROADCAST_CONFIRM, AWAIT_GITHUB_TOKEN
) = range(11)

# --- Configuration and Data Persistence ---
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass  # Will fall through to return a new structure
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
    user_id_str = str(user_id)
    if user_id_str not in bot_data["users"]:
        bot_data["users"][user_id_str] = {
            "repos": {},
            "github_token": None
        }
        save_data(bot_data)
        logger.info(f"New user created: {user_id_str}")
    return bot_data["users"][user_id_str]

async def user_is_authorized(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False

    if user.id == OWNER_ID:
        get_or_create_user(user.id) # Ensure owner is in the user list
        return True

    if user.id in bot_data["banned_users"]:
        if update.message:
            await update.message.reply_text("You have been banned from using this bot.")
        elif update.callback_query:
            await update.callback_query.answer("You have been banned from using this bot.", show_alert=True)
        return False

    if not bot_data["settings"]["is_public"] and user.id not in bot_data["special_users"]:
        if update.message:
            await update.message.reply_text("This bot is currently in private mode. Access denied.")
        elif update.callback_query:
            await update.callback_query.answer("This bot is currently in private mode. Access denied.", show_alert=True)
        return False

    get_or_create_user(user.id)
    return True

# --- GitHub API Helpers ---
def get_api_headers(token: str):
    """Returns the headers for a GitHub API request."""
    if not token:
        return {}
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
def get_a_valid_token_for_repo(repo_name: str) -> str | None:
    """Finds a valid token for a given repo, prioritizing the owner."""
    owner_data = bot_data["users"].get(str(OWNER_ID))
    if owner_data and repo_name in owner_data.get("repos", {}) and owner_data.get("github_token"):
        return owner_data["github_token"]
    
    # Fallback to any user tracking the repo
    for user_data in bot_data["users"].values():
        if repo_name in user_data.get("repos", {}) and user_data.get("github_token"):
            return user_data["github_token"]
            
    return None


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
        [InlineKeyboardButton("🔑 Set GitHub Token", callback_data="set_github_token")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("GitHub Release Notifier Bot Menu:", reply_markup=reply_markup)

# --- Release Checking Logic ---
async def check_releases(context: ContextTypes.DEFAULT_TYPE):
    repo_name = context.job.data["repo_name"]
    token = get_a_valid_token_for_repo(repo_name)

    if not token:
        logger.warning(f"No valid GitHub token found for checking {repo_name}. Skipping.")
        return

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
        response = requests.get(api_url, headers=get_api_headers(token), timeout=15)
        if response.status_code == 404:
            logger.info(f"Repo {repo_name} has no releases yet.")
            return
        response.raise_for_status()
        latest_release = response.json()
        release_id = latest_release.get("id")
        last_known_id = global_repo_info.get("last_release_id")

        if release_id and release_id != last_known_id:
            logger.info(f"New release found for {repo_name}: {latest_release['tag_name']}")
            
            message = (
                f"🚀 **New Release for `{repo_name}`!**\n\n"
                f"**Version:** [{latest_release['tag_name']}]({latest_release['html_url']})\n"
                f"**Name:** {latest_release.get('name') or 'N/A'}\n"
                f"**Published:** {datetime.strptime(latest_release['published_at'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            # Notify all subscribed users and update their last_release_id
            for user_id_str, user_data in bot_data["users"].items():
                if repo_name in user_data["repos"]:
                    bot_data["users"][user_id_str]["repos"][repo_name]["last_release_id"] = release_id
                    try:
                        await context.bot.send_message(chat_id=int(user_id_str), text=message, parse_mode="Markdown")
                    except error.Forbidden:
                        logger.warning(f"User {user_id_str} has blocked the bot.")
                    except Exception as e:
                        logger.error(f"Failed to send message to {user_id_str}: {e}")
            save_data(bot_data)
        else:
            logger.info(f"No new release for {repo_name}.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking {repo_name} with token from pool: {e}")

async def check_now_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)

    if not user_data.get("github_token"):
        await query.answer("Please set your GitHub token first!", show_alert=True)
        return

    if not user_data["repos"]:
        await query.edit_message_text("You are not tracking any repositories.", reply_markup=main_menu_markup(user_id))
        return

    await query.answer(text="🔍 Checking your repositories now...")
    
    checked_repos = 0
    new_releases_found = 0
    for repo_name, repo_info in user_data["repos"].items():
        api_url = f"https://api.github.com/repos/{repo_name}/releases/latest"
        try:
            response = requests.get(api_url, headers=get_api_headers(user_data["github_token"]), timeout=10)
            if response.status_code == 401:
                await context.bot.send_message(chat_id=user_id, text="Your GitHub token is invalid or has expired. Please set a new one.")
                return
            response.raise_for_status()
            latest_release = response.json()
            release_id = latest_release.get("id")
            last_known_id = repo_info.get("last_release_id")
            
            if release_id and release_id != last_known_id:
                new_releases_found += 1
                user_data["repos"][repo_name]["last_release_id"] = release_id
                message = (
                    f"🚀 **New Release for `{repo_name}`!** (Manual Check)\n\n"
                    f"**Version:** [{latest_release['tag_name']}]({latest_release['html_url']})\n"
                    f"**Name:** {latest_release.get('name') or 'N/A'}\n"
                    f"**Published:** {datetime.strptime(latest_release['published_at'], '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
            checked_repos += 1
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on manual check for {repo_name} for user {user_id}: {e}")
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ Could not check `{repo_name}`. The repository might be private, deleted, or your token may lack permissions.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in check_now_user for {repo_name}: {e}")

    save_data(bot_data)
    await context.bot.send_message(chat_id=user_id, text=f"✅ Finished checking {checked_repos} repositories. Found {new_releases_found} new release(s).")


# --- Job Scheduling ---
def schedule_repo_check(scheduler: AsyncIOScheduler, repo_name: str, interval_hours: int):
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
            kwargs={"repo_name": repo_name},
            next_run_time=datetime.now() + timedelta(seconds=15)
        )
        logger.info(f"Scheduled new job for {repo_name} every {interval_hours} hours.")

def is_repo_tracked_by_anyone(repo_name: str) -> bool:
    for user_data in bot_data["users"].values():
        if repo_name in user_data.get("repos", {}):
            return True
    return False

def unschedule_if_unused(scheduler: AsyncIOScheduler, repo_name: str):
    if not is_repo_tracked_by_anyone(repo_name):
        job_id = f"check_{repo_name.replace('/', '_')}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info(f"Unscheduled job for {repo_name} as it's no longer tracked.")

# --- Conversation Handlers and Callbacks for Users ---
async def add_repo_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)
    if not user_data.get("github_token"):
        await query.answer("Please set your GitHub token before adding repositories!", show_alert=True)
        return ConversationHandler.END
    await query.edit_message_text("Please send the full GitHub repository URL (e.g., https://github.com/owner/repo).")
    return AWAIT_REPO_ADD

async def add_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_or_create_user(user_id)
    repo_url = update.message.text.strip()
    try:
        repo_name = "/".join(repo_url.split("github.com/")[1].split("/")[:2])
    except IndexError:
        await update.message.reply_text("Invalid GitHub URL format. Please use `https://github.com/owner/repo`.", parse_mode='Markdown', reply_markup=main_menu_markup(user_id))
        return ConversationHandler.END

    if repo_name in user_data["repos"]:
        await update.message.reply_text(f"You are already tracking `{repo_name}`.", parse_mode='Markdown', reply_markup=main_menu_markup(user_id))
        return ConversationHandler.END

    api_url = f"https://api.github.com/repos/{repo_name}"
    try:
        response = requests.get(api_url, headers=get_api_headers(user_data["github_token"]), timeout=10)
        if response.status_code == 404:
            await update.message.reply_text(f"Repository `{repo_name}` not found. Check the URL.", parse_mode="Markdown")
            return ConversationHandler.END
        response.raise_for_status()
    except requests.exceptions.RequestException:
        await update.message.reply_text(f"Could not validate repository `{repo_name}`. It might be private or your token lacks permissions.", parse_mode='Markdown')
        return ConversationHandler.END

    release_api_url = f"{api_url}/releases/latest"
    last_release_id = None
    try:
        response = requests.get(release_api_url, headers=get_api_headers(user_data["github_token"]), timeout=10)
        if response.status_code == 200:
            last_release_id = response.json().get("id")
    except requests.exceptions.RequestException:
        pass # It's okay if there are no releases yet

    user_data["repos"][repo_name] = {
        "url": f"https://github.com/{repo_name}",
        "interval_hours": 24,
        "last_release_id": last_release_id,
    }
    save_data(bot_data)
    schedule_repo_check(context.application.job_queue.scheduler, repo_name, 24)
    await update.message.reply_text(f"✅ Repository `{repo_name}` added to your list with a default 24-hour check interval.", parse_mode='Markdown', reply_markup=main_menu_markup(user_id))
    return ConversationHandler.END

async def list_repos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)

    if not user_data["repos"]:
        await query.edit_message_text("You are not tracking any repositories.", reply_markup=main_menu_markup(user_id))
        return

    message = "📋 Your Tracked Repositories:\n\n"
    for repo, info in user_data["repos"].items():
        message += f"- `{repo}` (Interval: {info['interval_hours']}h)\n"

    token_status = "Set" if user_data.get("github_token") else "Not Set"
    message += f"\n🔑 GitHub Token Status: **{token_status}**"

    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=main_menu_markup(user_id))

async def prompt_delete_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This function now acts as the entry point for the conversation
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)
    
    if not user_data["repos"]:
        await query.edit_message_text("You have no repositories to delete.", reply_markup=main_menu_markup(user_id))
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(repo, callback_data=f"del_repo_{repo}")] for repo in user_data["repos"]]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text("Select a repository to remove from your list:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAIT_REPO_DELETE


async def handle_delete_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)
    repo_name = query.data.split("del_repo_", 1)[1]

    if repo_name in user_data["repos"]:
        del user_data["repos"][repo_name]
        save_data(bot_data)
        unschedule_if_unused(context.application.job_queue.scheduler, repo_name)
        await query.edit_message_text(f"🗑️ Repository `{repo_name}` has been removed.", parse_mode='Markdown', reply_markup=main_menu_markup(user_id))
    else:
        await query.answer("Repository not found in your list.", show_alert=True)
    return ConversationHandler.END

async def prompt_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.effective_user.id
    user_data = get_or_create_user(user_id)

    if not user_data["repos"]:
        await query.edit_message_text("You have no repositories to configure.", reply_markup=main_menu_markup(user_id))
        return ConversationHandler.END
        
    keyboard = [[InlineKeyboardButton(f"{repo} ({info['interval_hours']}h)", callback_data=f"set_interval_{repo}")] for repo, info in user_data["repos"].items()]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
    await query.edit_message_text("Select a repository to set a new check interval:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AWAIT_INTERVAL_REPO

async def prompt_interval_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    repo_name = query.data.split("set_interval_", 1)[1]
    context.user_data["repo_to_set_interval"] = repo_name
    await query.edit_message_text(f"Enter the new check interval in hours for `{repo_name}`.\n\nNote: This is a global setting for this repository.", parse_mode='Markdown')
    return AWAIT_INTERVAL_HOURS
    
async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_or_create_user(user_id)
    try:
        hours = int(update.message.text)
        if not (1 <= hours <= 720): raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid number of hours (e.g., between 1 and 720).")
        return AWAIT_INTERVAL_HOURS

    repo_name = context.user_data.get("repo_to_set_interval")
    if repo_name and repo_name in user_data["repos"]:
        # Set interval for every user tracking this repo
        for uid, udata in bot_data["users"].items():
            if repo_name in udata["repos"]:
                bot_data["users"][uid]["repos"][repo_name]["interval_hours"] = hours
        save_data(bot_data)
        
        schedule_repo_check(context.application.job_queue.scheduler, repo_name, hours)
        await update.message.reply_text(f"⏰ Global check interval for `{repo_name}` updated to {hours} hours.", parse_mode='Markdown', reply_markup=main_menu_markup(user_id))
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("Could not find the repository to update. Please try again.", reply_markup=main_menu_markup(user_id))
        return ConversationHandler.END

async def set_github_token_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("Please send me your GitHub Personal Access Token (PAT). It will be stored to make API requests on your behalf.\n\nSend /cancel to abort.")
    return AWAIT_GITHUB_TOKEN

async def set_github_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_or_create_user(user_id)
    token = update.message.text.strip()
    
    # Simple validation
    api_url = "https://api.github.com/user"
    response = requests.get(api_url, headers=get_api_headers(token), timeout=10)
    
    if response.status_code == 200:
        user_data["github_token"] = token
        save_data(bot_data)
        await update.message.reply_text("✅ Your GitHub token has been saved and verified successfully.", reply_markup=main_menu_markup(user_id))
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ That token appears to be invalid. Please try again or send /cancel.")
        return AWAIT_GITHUB_TOKEN

# --- Owner Panel and User Management ---
# (Owner panel and user management functions are largely unchanged from the previous version,
#  but will be included here for completeness)

async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    is_public_text = "✅ Public" if bot_data['settings']['is_public'] else "❌ Private"
    keyboard = [
        [InlineKeyboardButton(f"Mode: {is_public_text}", callback_data="toggle_public")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="broadcast_message")],
        [InlineKeyboardButton("👥 Manage Users", callback_data="manage_users")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")],
    ]
    await query.edit_message_text("👑 Owner Control Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_public_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    bot_data['settings']['is_public'] = not bot_data['settings']['is_public']
    save_data(bot_data)
    await query.answer(f"Bot is now {'Public' if bot_data['settings']['is_public'] else 'Private'}.")
    await owner_panel(update, context)

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
    
async def prompt_for_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    query = update.callback_query
    await query.edit_message_text(f"Please send the Telegram User ID of the user to {action}.")

# (ban_user, unban_user, add_special_user, remove_special_user are identical to previous version)

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        if user_id == OWNER_ID:
            await update.message.reply_text("You cannot ban the owner.")
        elif user_id not in bot_data["banned_users"]:
            bot_data["banned_users"].append(user_id)
            if user_id in bot_data["special_users"]: bot_data["special_users"].remove(user_id)
            save_data(bot_data)
            await update.message.reply_text(f"🚫 User `{user_id}` has been banned.", parse_mode="Markdown", reply_markup=owner_panel_markup())
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
            await update.message.reply_text(f"✅ User `{user_id}` has been unbanned.", parse_mode="Markdown", reply_markup=owner_panel_markup())
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
            await update.message.reply_text(f"⭐ User `{user_id}` is now a special user.", parse_mode="Markdown", reply_markup=owner_panel_markup())
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
            await update.message.reply_text(f"⚪ Special status removed for `{user_id}`.", parse_mode="Markdown", reply_markup=owner_panel_markup())
        else:
            await update.message.reply_text(f"User `{user_id}` is not a special user.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("Invalid User ID.")
    return ConversationHandler.END

# --- Broadcast Conversation ---
async def broadcast_message_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("Please send the update message you want to broadcast to all users. Markdown is supported.\n\nSend /cancel to abort.")
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
    message_text = context.user_data.get('broadcast_message')
    if not message_text:
        await query.edit_message_text("Error: Message not found.", reply_markup=owner_panel_markup())
        return ConversationHandler.END

    await query.edit_message_text("Broadcasting message...", reply_markup=None)
    all_users = [int(uid) for uid in bot_data['users'].keys() if int(uid) not in bot_data['banned_users']]
    sent_count, failed_count = 0, 0

    for user_id in all_users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")
            sent_count += 1
        except (error.Forbidden, error.BadRequest):
            failed_count += 1
        await asyncio.sleep(0.1)

    report = f"📢 Broadcast Complete!\n\nSent: {sent_count}\nFailed: {failed_count}"
    await query.edit_message_text(report, reply_markup=owner_panel_markup())
    context.user_data.clear()
    return ConversationHandler.END


# --- General Handlers ---
def main_menu_markup(user_id: int):
    keyboard = [
        [InlineKeyboardButton("➕ Add Repository", callback_data="add_repo")],
        [InlineKeyboardButton("📋 My Repositories", callback_data="list_repos")],
        [InlineKeyboardButton("➖ Delete Repository", callback_data="delete_repo")],
        [InlineKeyboardButton("⏰ Set Check Interval", callback_data="set_interval")],
        [InlineKeyboardButton("🔍 Check All My Repos Now", callback_data="check_now_user")],
        [InlineKeyboardButton("🔑 Set GitHub Token", callback_data="set_github_token")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])
    return InlineKeyboardMarkup(keyboard)

def owner_panel_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_panel")]])

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("GitHub Release Notifier Bot Menu:", reply_markup=main_menu_markup(query.effective_user.id))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = "Operation cancelled."
    if update.message:
        await update.message.reply_text(message_text, reply_markup=main_menu_markup(update.effective_user.id))
    elif update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=main_menu_markup(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END

def main():
    if not BOT_TOKEN or not OWNER_ID:
        raise ValueError("BOT_TOKEN and OWNER_ID environment variables must be set.")

    application = Application.builder().token(BOT_TOKEN).build()
    
    # Use the application's job_queue which has an implicit scheduler
    job_queue = application.job_queue
    
    # Reschedule jobs from saved data on startup
    unique_repos = set()
    repo_intervals = {}
    for user_data in bot_data["users"].values():
        for repo_name, repo_info in user_data.get("repos", {}).items():
            unique_repos.add(repo_name)
            if repo_name not in repo_intervals:
                 repo_intervals[repo_name] = repo_info.get("interval_hours", 24)

    if unique_repos:
        logger.info(f"Rescheduling jobs for {len(unique_repos)} unique repositories...")
        for repo_name in unique_repos:
             job_queue.run_repeating(
                check_releases,
                interval=timedelta(hours=repo_intervals[repo_name]),
                first=timedelta(seconds=15),
                name=f"check_{repo_name.replace('/', '_')}",
                data={"repo_name": repo_name}
            )

    # --- Conversation Handlers Setup ---
    # User actions
    add_repo_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_repo_prompt, pattern="^add_repo$")],
        states={AWAIT_REPO_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_repo)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    delete_repo_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_delete_repo, pattern="^delete_repo$")],
        states={AWAIT_REPO_DELETE: [CallbackQueryHandler(handle_delete_repo, pattern="^del_repo_")]},
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(main_menu_handler, pattern="^main_menu$")],
    )
    set_interval_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_set_interval, pattern="^set_interval$")],
        states={
            AWAIT_INTERVAL_REPO: [CallbackQueryHandler(prompt_interval_hours, pattern="^set_interval_")],
            AWAIT_INTERVAL_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_interval)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(main_menu_handler, pattern="^main_menu$")],
    )
    set_token_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(set_github_token_prompt, pattern="^set_github_token$")],
        states={AWAIT_GITHUB_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_github_token)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # Owner actions
    broadcast_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_message_prompt, pattern="^broadcast_message$")],
        states={
            AWAIT_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_confirm)],
            AWAIT_BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_send, pattern="^broadcast_send$")],
        },
        fallbacks=[CommandHandler("cancel", cancel), CallbackQueryHandler(owner_panel, pattern="^owner_panel$")],
    )
    ban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: prompt_for_user_id(u,c,"ban"), pattern="^ban_user$")],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    unban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: prompt_for_user_id(u,c,"unban"), pattern="^unban_user$")],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    add_special_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: prompt_for_user_id(u,c,"add as special"), pattern="^add_special$")],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_special_user)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    remove_special_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(lambda u,c: prompt_for_user_id(u,c,"remove from special"), pattern="^remove_special$")],
        states={0: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_special_user)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )


    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_repo_handler)
    application.add_handler(delete_repo_handler)
    application.add_handler(set_interval_handler)
    application.add_handler(set_token_handler)
    application.add_handler(broadcast_handler)
    application.add_handler(ban_handler)
    application.add_handler(unban_handler)
    application.add_handler(add_special_handler)
    application.add_handler(remove_special_handler)
    
    # Simple callback handlers
    application.add_handler(CallbackQueryHandler(list_repos, pattern="^list_repos$"))
    application.add_handler(CallbackQueryHandler(check_now_user, pattern="^check_now_user$"))
    application.add_handler(CallbackQueryHandler(main_menu_handler, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(owner_panel, pattern="^owner_panel$"))
    application.add_handler(CallbackQueryHandler(toggle_public_mode, pattern="^toggle_public$"))
    application.add_handler(CallbackQueryHandler(manage_users_panel, pattern="^manage_users$"))
    

    logger.info("Bot started successfully!")
    application.run_polling()


if __name__ == "__main__":
    main()

