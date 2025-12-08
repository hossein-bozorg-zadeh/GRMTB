import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import TelegramError
import aiohttp
from io import BytesIO

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = 'bot_data.json'
OWNER_ID = None
REQUIRED_CHANNEL = None
LOG_CHANNEL = None

class BotData:
    def __init__(self):
        self.users = {}
        self.repos = {}
        self.user_tokens = {}
        self.user_gitlab_tokens = {}
        self.check_intervals = {}
        self.last_releases = {}
        self.bot_public = True
        self.special_users = set()
        self.banned_users = set()
        self.repo_types = {}
        self.load_data()
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                    self.repos = data.get('repos', {})
                    self.user_tokens = data.get('user_tokens', {})
                    self.user_gitlab_tokens = data.get('user_gitlab_tokens', {})
                    self.check_intervals = data.get('check_intervals', {})
                    self.last_releases = data.get('last_releases', {})
                    self.bot_public = data.get('bot_public', True)
                    self.special_users = set(data.get('special_users', []))
                    self.banned_users = set(data.get('banned_users', []))
                    self.repo_types = data.get('repo_types', {})
                logger.info("Data loaded successfully")
            except Exception as e:
                logger.error(f"Error loading data: {e}")
    
    def save_data(self):
        data = {
            'users': self.users,
            'repos': self.repos,
            'user_tokens': self.user_tokens,
            'user_gitlab_tokens': self.user_gitlab_tokens,
            'check_intervals': self.check_intervals,
            'last_releases': self.last_releases,
            'bot_public': self.bot_public,
            'special_users': list(self.special_users),
            'banned_users': list(self.banned_users),
            'repo_types': self.repo_types
        }
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def export_data(self):
        return json.dumps({
            'users': self.users,
            'repos': self.repos,
            'user_tokens': self.user_tokens,
            'user_gitlab_tokens': self.user_gitlab_tokens,
            'check_intervals': self.check_intervals,
            'last_releases': self.last_releases,
            'bot_public': self.bot_public,
            'special_users': list(self.special_users),
            'banned_users': list(self.banned_users),
            'repo_types': self.repo_types,
            'export_date': datetime.now().isoformat()
        }, indent=2)
    
    def import_data(self, data_str):
        try:
            data = json.loads(data_str)
            self.users = data.get('users', {})
            self.repos = data.get('repos', {})
            self.user_tokens = data.get('user_tokens', {})
            self.user_gitlab_tokens = data.get('user_gitlab_tokens', {})
            self.check_intervals = data.get('check_intervals', {})
            self.last_releases = data.get('last_releases', {})
            self.bot_public = data.get('bot_public', True)
            self.special_users = set(data.get('special_users', []))
            self.banned_users = set(data.get('banned_users', []))
            self.repo_types = data.get('repo_types', {})
            self.save_data()
            logger.info("Data imported successfully")
            return True
        except Exception as e:
            logger.error(f"Error importing data: {e}")
            return False

bot_data = BotData()

def is_owner(user_id):
    return user_id == OWNER_ID

def can_use_bot(user_id):
    if user_id in bot_data.banned_users:
        return False
    if bot_data.bot_public or user_id in bot_data.special_users or is_owner(user_id):
        return True
    return False

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not REQUIRED_CHANNEL:
        return True
    
    user_id = update.effective_user.id
    
    if is_owner(user_id) or user_id in bot_data.special_users:
        return True
    
    try:
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if not await check_channel_membership(update, context):
        keyboard = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ You must join our channel to use this bot.\n\nClick the button below to join:",
            reply_markup=reply_markup
        )
        return
    
    if user_id not in bot_data.users:
        bot_data.users[user_id] = {'username': update.effective_user.username or 'Unknown'}
        bot_data.save_data()
        logger.info(f"New user registered: {user_id}")
    
    keyboard = [
        [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
        [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
        [InlineKeyboardButton("🔑 Set Tokens", callback_data='set_tokens')],
        [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
        [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
    ]
    
    if is_owner(int(user_id)):
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🤖 GitHub/GitLab Release Notifier Bot\n\nSelect an option:', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if not can_use_bot(int(user_id)):
        await query.edit_message_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if not await check_channel_membership(update, context):
        keyboard = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚠️ You must join our channel to use this bot.\n\nClick the button below to join:",
            reply_markup=reply_markup
        )
        return
    
    if query.data == 'main_menu':
        keyboard = [
            [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
            [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
            [InlineKeyboardButton("🔑 Set Tokens", callback_data='set_tokens')],
            [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
            [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
        ]
        if is_owner(int(user_id)):
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🤖 GitHub/GitLab Release Notifier Bot\n\nSelect an option:', reply_markup=reply_markup)
    
    elif query.data == 'my_repos':
        user_repos = bot_data.repos.get(user_id, [])
        if not user_repos:
            text = "📋 You have no repositories added.\n\nAdd one using the ➕ Add Repo button."
        else:
            text = "📋 Your Repositories:\n\n"
            for idx, repo in enumerate(user_repos, 1):
                interval = bot_data.check_intervals.get(f"{user_id}_{repo}", 24)
                repo_type = bot_data.repo_types.get(f"{user_id}_{repo}", 'github')
                icon = "🐙" if repo_type == 'github' else "🦊"
                text += f"{idx}. {icon} {repo} (Check: {interval}h)\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
        if user_repos:
            keyboard.insert(0, [InlineKeyboardButton("🗑 Delete Repo", callback_data='delete_repo')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == 'add_repo':
        keyboard = [
            [InlineKeyboardButton("🐙 GitHub Repository", callback_data='add_github')],
            [InlineKeyboardButton("🦊 GitLab Repository", callback_data='add_gitlab')],
            [InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('➕ Add Repository\n\nSelect platform:', reply_markup=reply_markup)
    
    elif query.data == 'add_github':
        context.user_data['awaiting'] = 'github_repo'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('➕ Add GitHub Repository\n\nSend the repository in format: owner/repo\nExample: torvalds/linux', reply_markup=reply_markup)
    
    elif query.data == 'add_gitlab':
        context.user_data['awaiting'] = 'gitlab_repo'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('➕ Add GitLab Repository\n\nSend the repository in format: owner/repo\nExample: gitlab-org/gitlab', reply_markup=reply_markup)
    
    elif query.data == 'set_tokens':
        keyboard = [
            [InlineKeyboardButton("🐙 Set GitHub Token", callback_data='set_github_token')],
            [InlineKeyboardButton("🦊 Set GitLab Token", callback_data='set_gitlab_token')],
            [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🔑 Set API Tokens\n\nSelect platform:', reply_markup=reply_markup)
    
    elif query.data == 'set_github_token':
        context.user_data['awaiting'] = 'github_token'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='set_tokens')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🔑 Set GitHub Token\n\nSend your GitHub personal access token.\n\nGet one from: https://github.com/settings/tokens', reply_markup=reply_markup)
    
    elif query.data == 'set_gitlab_token':
        context.user_data['awaiting'] = 'gitlab_token'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='set_tokens')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🔑 Set GitLab Token\n\nSend your GitLab personal access token.\n\nGet one from: https://gitlab.com/-/profile/personal_access_tokens', reply_markup=reply_markup)
    
    elif query.data == 'set_interval':
        user_repos = bot_data.repos.get(user_id, [])
        if not user_repos:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("You need to add repositories first.", reply_markup=reply_markup)
            return
        
        context.user_data['awaiting'] = 'interval_repo'
        text = "⏱ Set Check Interval\n\nSelect a repository:\n\n"
        keyboard = []
        for idx, repo in enumerate(user_repos, 1):
            repo_type = bot_data.repo_types.get(f"{user_id}_{repo}", 'github')
            icon = "🐙" if repo_type == 'github' else "🦊"
            text += f"{idx}. {icon} {repo}\n"
            keyboard.append([InlineKeyboardButton(f"{idx}. {icon} {repo}", callback_data=f'interval_select_{repo}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data.startswith('interval_select_'):
        repo = query.data.replace('interval_select_', '')
        context.user_data['interval_repo'] = repo
        keyboard = [
            [InlineKeyboardButton("⏰ 6 hours", callback_data='interval_6')],
            [InlineKeyboardButton("⏰ 12 hours", callback_data='interval_12')],
            [InlineKeyboardButton("⏰ 24 hours", callback_data='interval_24')],
            [InlineKeyboardButton("⏰ 48 hours", callback_data='interval_48')],
            [InlineKeyboardButton("⏰ 72 hours", callback_data='interval_72')],
            [InlineKeyboardButton("🔙 Back", callback_data='set_interval')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f'⏱ Set check interval for:\n{repo}', reply_markup=reply_markup)
    
    elif query.data.startswith('interval_'):
        hours = int(query.data.replace('interval_', ''))
        repo = context.user_data.get('interval_repo')
        if repo:
            bot_data.check_intervals[f"{user_id}_{repo}"] = hours
            bot_data.save_data()
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f'✅ Check interval set to {hours} hours for {repo}', reply_markup=reply_markup)
            logger.info(f"User {user_id} set interval {hours}h for {repo}")
    
    elif query.data == 'delete_repo':
        user_repos = bot_data.repos.get(user_id, [])
        text = "🗑 Delete Repository\n\nSelect a repository to delete:\n\n"
        keyboard = []
        for idx, repo in enumerate(user_repos, 1):
            repo_type = bot_data.repo_types.get(f"{user_id}_{repo}", 'github')
            icon = "🐙" if repo_type == 'github' else "🦊"
            text += f"{idx}. {icon} {repo}\n"
            keyboard.append([InlineKeyboardButton(f"🗑 {icon} {repo}", callback_data=f'delete_{repo}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_repos')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data.startswith('delete_'):
        repo = query.data.replace('delete_', '')
        if user_id in bot_data.repos and repo in bot_data.repos[user_id]:
            bot_data.repos[user_id].remove(repo)
            bot_data.check_intervals.pop(f"{user_id}_{repo}", None)
            bot_data.last_releases.pop(f"{user_id}_{repo}", None)
            bot_data.repo_types.pop(f"{user_id}_{repo}", None)
            bot_data.save_data()
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f'✅ Repository {repo} deleted successfully.', reply_markup=reply_markup)
            logger.info(f"User {user_id} deleted repo {repo}")
    
    elif query.data == 'check_now':
        user_repos = bot_data.repos.get(user_id, [])
        if not user_repos:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("You have no repositories to check.", reply_markup=reply_markup)
            return
        
        github_token = bot_data.user_tokens.get(user_id)
        gitlab_token = bot_data.user_gitlab_tokens.get(user_id)
        
        if not github_token and not gitlab_token:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("You need to set at least one API token first.", reply_markup=reply_markup)
            return
        
        await query.edit_message_text("🔄 Checking for updates...")
        checked = 0
        for repo in user_repos:
            await check_repo_updates(context, user_id, repo, force=True)
            checked += 1
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f'✅ Checked {checked} repositories.', reply_markup=reply_markup)
        logger.info(f"User {user_id} manually checked {checked} repos")
    
    elif query.data.startswith('download_asset_'):
        parts = query.data.replace('download_asset_', '').split('_', 3)
        user_id_data = parts[0]
        platform = parts[1]
        repo = parts[2]
        asset_id = parts[3]
        
        if user_id_data != user_id:
            await query.answer("This is not your download.")
            return
        
        await query.answer("Downloading... Please wait.")
        await download_asset(context, user_id, platform, repo, asset_id)
    
    elif query.data == 'admin_panel':
        if not is_owner(int(user_id)):
            await query.edit_message_text("❌ You don't have permission to access the admin panel.")
            return
        
        status = "🟢 Public" if bot_data.bot_public else "🔴 Private"
        total_users = len(bot_data.users)
        special_users = len(bot_data.special_users)
        banned_users = len(bot_data.banned_users)
        
        keyboard = [
            [InlineKeyboardButton(f"🔄 Toggle Bot Status ({status})", callback_data='toggle_public')],
            [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
            [InlineKeyboardButton("📢 Send Update Message", callback_data='send_update')],
            [InlineKeyboardButton("💾 Download Data", callback_data='download_data')],
            [InlineKeyboardButton("📋 Download Logs", callback_data='download_logs')],
            [InlineKeyboardButton("📥 Import Data", callback_data='import_data')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = f"👑 Admin Panel\n\nBot Status: {status}\nTotal Users: {total_users}\nSpecial Users: {special_users}\nBanned Users: {banned_users}"
        if REQUIRED_CHANNEL:
            text += f"\n\nRequired Channel: {REQUIRED_CHANNEL}"
        if LOG_CHANNEL:
            text += f"\nLog Channel: {LOG_CHANNEL}"
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == 'toggle_public':
        if not is_owner(int(user_id)):
            return
        bot_data.bot_public = not bot_data.bot_public
        bot_data.save_data()
        status = "🟢 Public" if bot_data.bot_public else "🔴 Private"
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f'✅ Bot is now {status}', reply_markup=reply_markup)
        logger.info(f"Bot status changed to {status}")
    
    elif query.data == 'download_data':
        if not is_owner(int(user_id)):
            return
        
        data_json = bot_data.export_data()
        file_data = BytesIO(data_json.encode('utf-8'))
        filename = f"bot_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        await context.bot.send_document(
            chat_id=int(user_id),
            document=file_data,
            filename=filename,
            caption="💾 Bot Data Export"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("✅ Data exported successfully!", reply_markup=reply_markup)
        logger.info(f"Owner downloaded data export")
    
    elif query.data == 'download_logs':
        if not is_owner(int(user_id)):
            return
        
        if os.path.exists('bot.log'):
            await context.bot.send_document(
                chat_id=int(user_id),
                document=open('bot.log', 'rb'),
                filename=f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                caption="📋 Bot Logs"
            )
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("✅ Logs downloaded successfully!", reply_markup=reply_markup)
            logger.info(f"Owner downloaded logs")
        else:
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ No log file found.", reply_markup=reply_markup)
    
    elif query.data == 'import_data':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'import_data'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📥 Import Data\n\nSend the JSON file to import.', reply_markup=reply_markup)
    
    elif query.data == 'manage_users':
        if not is_owner(int(user_id)):
            return
        keyboard = [
            [InlineKeyboardButton("➕ Add Special User", callback_data='add_special')],
            [InlineKeyboardButton("🚫 Ban User", callback_data='ban_user')],
            [InlineKeyboardButton("✅ Unban User", callback_data='unban_user')],
            [InlineKeyboardButton("📋 List Users", callback_data='list_users')],
            [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('👥 Manage Users', reply_markup=reply_markup)
    
    elif query.data == 'add_special':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'add_special'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='manage_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('➕ Add Special User\n\nSend the user ID:', reply_markup=reply_markup)
    
    elif query.data == 'ban_user':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'ban_user'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='manage_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🚫 Ban User\n\nSend the user ID:', reply_markup=reply_markup)
    
    elif query.data == 'unban_user':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'unban_user'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='manage_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('✅ Unban User\n\nSend the user ID:', reply_markup=reply_markup)
    
    elif query.data == 'list_users':
        if not is_owner(int(user_id)):
            return
        text = "📋 Users List\n\n"
        for uid, info in bot_data.users.items():
            username = info.get('username', 'Unknown')
            special = "⭐" if int(uid) in bot_data.special_users else ""
            banned = "🚫" if int(uid) in bot_data.banned_users else ""
            text += f"{uid} - @{username} {special}{banned}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text[:4000], reply_markup=reply_markup)
    
    elif query.data == 'send_update':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'update_message'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📢 Send Update Message\n\nType the message to send to all users:', reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if not await check_channel_membership(update, context):
        keyboard = [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ You must join our channel to use this bot.\n\nClick the button below to join:",
            reply_markup=reply_markup
        )
        return
    
    awaiting = context.user_data.get('awaiting')
    
    if awaiting == 'github_repo':
        repo = update.message.text.strip()
        if '/' not in repo or repo.count('/') != 1:
            await update.message.reply_text('❌ Invalid format. Use: owner/repo')
            return
        
        if user_id not in bot_data.repos:
            bot_data.repos[user_id] = []
        
        if repo in bot_data.repos[user_id]:
            await update.message.reply_text('❌ Repository already added.')
            return
        
        bot_data.repos[user_id].append(repo)
        bot_data.check_intervals[f"{user_id}_{repo}"] = 24
        bot_data.repo_types[f"{user_id}_{repo}"] = 'github'
        bot_data.save_data()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'✅ GitHub repository {repo} added successfully!\nDefault check interval: 24 hours', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} added GitHub repo {repo}")
    
    elif awaiting == 'gitlab_repo':
        repo = update.message.text.strip()
        if '/' not in repo or repo.count('/') != 1:
            await update.message.reply_text('❌ Invalid format. Use: owner/repo')
            return
        
        if user_id not in bot_data.repos:
            bot_data.repos[user_id] = []
        
        if repo in bot_data.repos[user_id]:
            await update.message.reply_text('❌ Repository already added.')
            return
        
        bot_data.repos[user_id].append(repo)
        bot_data.check_intervals[f"{user_id}_{repo}"] = 24
        bot_data.repo_types[f"{user_id}_{repo}"] = 'gitlab'
        bot_data.save_data()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'✅ GitLab repository {repo} added successfully!\nDefault check interval: 24 hours', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} added GitLab repo {repo}")
    
    elif awaiting == 'github_token':
        token = update.message.text.strip()
        bot_data.user_tokens[user_id] = token
        bot_data.save_data()
        await update.message.delete()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('✅ GitHub token saved successfully!', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} set GitHub token")
    
    elif awaiting == 'gitlab_token':
        token = update.message.text.strip()
        bot_data.user_gitlab_tokens[user_id] = token
        bot_data.save_data()
        await update.message.delete()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('✅ GitLab token saved successfully!', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} set GitLab token
