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

from logging.handlers import RotatingFileHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        RotatingFileHandler('bot.log', maxBytes=10 * 1024 * 1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DATA_FILE = 'bot_data.json'
OWNER_ID = None

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
        self.required_channel = None
        self.log_channel = None
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
                    self.required_channel = data.get('required_channel')
                    self.log_channel = data.get('log_channel')
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
            'repo_types': self.repo_types,
            'required_channel': self.required_channel,
            'log_channel': self.log_channel
        }
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def export_data(self):
        # API tokens are deliberately excluded: exports are downloaded and
        # posted to the log channel, where they would leak every user's
        # credentials. Users simply re-enter their tokens after a restore.
        return json.dumps({
            'users': self.users,
            'repos': self.repos,
            'check_intervals': self.check_intervals,
            'last_releases': self.last_releases,
            'bot_public': self.bot_public,
            'special_users': list(self.special_users),
            'banned_users': list(self.banned_users),
            'repo_types': self.repo_types,
            'required_channel': self.required_channel,
            'log_channel': self.log_channel,
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
            self.required_channel = data.get('required_channel')
            self.log_channel = data.get('log_channel')
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
    if not bot_data.required_channel:
        return True
    
    user_id = update.effective_user.id
    
    if is_owner(user_id) or user_id in bot_data.special_users:
        return True
    
    try:
        member = await context.bot.get_chat_member(bot_data.required_channel, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if not await check_channel_membership(update, context):
        channel_link = bot_data.required_channel.replace('@', '')
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel_link}")],
            [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ You must join our channel to use this bot.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
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
        [InlineKeyboardButton("🔑 Set API Tokens", callback_data='set_tokens')],
        [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
        [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
    ]
    
    if is_owner(int(user_id)):
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🔔 GitHub/GitLab Release Notifier\n\nSelect an option:', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if not can_use_bot(int(user_id)):
        await query.edit_message_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if not await check_channel_membership(update, context):
        channel_link = bot_data.required_channel.replace('@', '')
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel_link}")],
            [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚠️ You must join our channel to use this bot.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
            reply_markup=reply_markup
        )
        return
    
    if query.data == 'check_membership':
        if await check_channel_membership(update, context):
            keyboard = [
                [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
                [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
                [InlineKeyboardButton("🔑 Set API Tokens", callback_data='set_tokens')],
                [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
                [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
            ]
            if is_owner(int(user_id)):
                keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text('🔔 GitHub/GitLab Release Notifier\n\n✅ Membership verified! Select an option:', reply_markup=reply_markup)
        else:
            channel_link = bot_data.required_channel.replace('@', '')
            keyboard = [
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel_link}")],
                [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ You haven't joined the channel yet.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
                reply_markup=reply_markup
            )
        return
    
    if query.data == 'main_menu':
        keyboard = [
            [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
            [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
            [InlineKeyboardButton("🔑 Set API Tokens", callback_data='set_tokens')],
            [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
            [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
        ]
        if is_owner(int(user_id)):
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🔔 GitHub/GitLab Release Notifier\n\nSelect an option:', reply_markup=reply_markup)
    
    elif query.data == 'my_repos':
        user_repos = bot_data.repos.get(user_id, [])
        if not user_repos:
            text = "📋 You have no repositories added.\n\nAdd one using the ➕ Add Repo button."
        else:
            text = "📋 Your Repositories:\n\n"
            for idx, repo in enumerate(user_repos, 1):
                interval = bot_data.check_intervals.get(f"{user_id}_{repo}", 24)
                repo_type = bot_data.repo_types.get(f"{user_id}_{repo}", 'github')
                icon = "🤖" if repo_type == 'github' else "🦊"
                text += f"{idx}. {icon} {repo} (Check: {interval}h)\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
        if user_repos:
            keyboard.insert(0, [InlineKeyboardButton("🗑 Delete Repo", callback_data='delete_repo')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == 'add_repo':
        keyboard = [
            [InlineKeyboardButton("🤖 GitHub Repository", callback_data='add_github')],
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
            [InlineKeyboardButton("🤖 Set GitHub Token", callback_data='set_github_token')],
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
        await query.edit_message_text('🔑 Set GitLab Token\n\nSend your GitLab personal access token.\n\nGet one from: https://gitlab.com/-/user_settings/personal_access_tokens', reply_markup=reply_markup)
    
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
            icon = "🤖" if repo_type == 'github' else "🦊"
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
            icon = "🤖" if repo_type == 'github' else "🦊"
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
    
    elif query.data.startswith('asset_page_'):
        parts = query.data.replace('asset_page_', '').rsplit('_', 1)
        user_repo = parts[0]
        page = int(parts[1])
        
        user_id_check = user_repo.split('_')[0]
        if user_id_check != user_id:
            await query.answer("This is not your download.")
            return
        
        repo = '_'.join(user_repo.split('_')[1:])
        asset_data = context.bot_data.get(f'assets_{user_id}_{repo}')
        
        if not asset_data:
            await query.answer("Session expired. Please check for updates again.")
            return
        
        platform = asset_data['platform']
        assets = asset_data['assets']
        tag = asset_data.get('tag')
        
        keyboard = create_asset_buttons(user_id, platform, repo, assets, page, tag)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer(f"Page {page + 1}")
        except Exception as e:
            logger.error(f"Error changing page: {e}")
            await query.answer("Error changing page")
        return
    
    elif query.data == 'page_info':
        await query.answer("Use ⬅️ Previous and ➡️ Next to navigate")
        return
    
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
        
        text = f"👑 Admin Panel\n\nBot Status: {status}\nTotal Users: {total_users}\nSpecial Users: {special_users}\nBanned Users: {banned_users}\n"
        
        if bot_data.required_channel:
            text += f"\nRequired Channel: {bot_data.required_channel}"
        else:
            text += f"\nRequired Channel: Not Set"
            
        if bot_data.log_channel:
            text += f"\nLog Channel: {bot_data.log_channel}"
        else:
            text += f"\nLog Channel: Not Set"
        
        keyboard = [
            [InlineKeyboardButton(f"🔄 Toggle Bot Status ({status})", callback_data='toggle_public')],
            [InlineKeyboardButton("📢 Set Required Channel", callback_data='set_required_channel')],
            [InlineKeyboardButton("📊 Set Log Channel", callback_data='set_log_channel')],
            [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
            [InlineKeyboardButton("📣 Send Update Message", callback_data='send_update')],
            [InlineKeyboardButton("💾 Download Data", callback_data='download_data')],
            [InlineKeyboardButton("📋 Download Logs", callback_data='download_logs')],
            [InlineKeyboardButton("📥 Import Data", callback_data='import_data')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == 'set_required_channel':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'required_channel'
        keyboard = [
            [InlineKeyboardButton("🚫 Remove Channel Requirement", callback_data='remove_required_channel')],
            [InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📢 Set Required Channel\n\nSend the channel username (e.g., @mychannel) or ID.\n\nUsers must join this channel to use the bot.', reply_markup=reply_markup)
    
    elif query.data == 'remove_required_channel':
        if not is_owner(int(user_id)):
            return
        bot_data.required_channel = None
        bot_data.save_data()
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('✅ Required channel removed. All users can now access the bot.', reply_markup=reply_markup)
        logger.info("Required channel removed")
    
    elif query.data == 'set_log_channel':
        if not is_owner(int(user_id)):
            return
        context.user_data['awaiting'] = 'log_channel'
        keyboard = [
            [InlineKeyboardButton("🚫 Remove Log Channel", callback_data='remove_log_channel')],
            [InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📊 Set Log Channel\n\nSend the channel username (e.g., @mylogs) or ID.\n\nDaily backups will be sent here.', reply_markup=reply_markup)
    
    elif query.data == 'remove_log_channel':
        if not is_owner(int(user_id)):
            return
        bot_data.log_channel = None
        bot_data.save_data()
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('✅ Log channel removed. Automatic backups disabled.', reply_markup=reply_markup)
        logger.info("Log channel removed")
    
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
        await query.edit_message_text('📣 Send Update Message\n\nType the message to send to all users:', reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if not await check_channel_membership(update, context):
        channel_link = bot_data.required_channel.replace('@', '')
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel_link}")],
            [InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ You must join our channel to use this bot.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
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
        logger.info(f"User {user_id} set GitLab token")
    
    elif awaiting == 'required_channel':
        if not is_owner(int(user_id)):
            return
        channel = update.message.text.strip()
        bot_data.required_channel = channel
        bot_data.save_data()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'✅ Required channel set to: {channel}\n\nUsers must now join this channel to use the bot.', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"Required channel set to {channel}")
    
    elif awaiting == 'log_channel':
        if not is_owner(int(user_id)):
            return
        channel = update.message.text.strip()
        bot_data.log_channel = channel
        bot_data.save_data()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'✅ Log channel set to: {channel}\n\nDaily backups will be sent here automatically.', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"Log channel set to {channel}")
    
    elif awaiting == 'add_special':
        if not is_owner(int(user_id)):
            return
        try:
            special_user_id = int(update.message.text.strip())
            bot_data.special_users.add(special_user_id)
            bot_data.save_data()
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f'✅ User {special_user_id} added as special user.', reply_markup=reply_markup)
            logger.info(f"Owner added special user {special_user_id}")
        except ValueError:
            await update.message.reply_text('❌ Invalid user ID.')
        context.user_data.pop('awaiting', None)
    
    elif awaiting == 'ban_user':
        if not is_owner(int(user_id)):
            return
        try:
            ban_user_id = int(update.message.text.strip())
            bot_data.banned_users.add(ban_user_id)
            bot_data.save_data()
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f'✅ User {ban_user_id} has been banned.', reply_markup=reply_markup)
            logger.info(f"Owner banned user {ban_user_id}")
        except ValueError:
            await update.message.reply_text('❌ Invalid user ID.')
        context.user_data.pop('awaiting', None)
    
    elif awaiting == 'unban_user':
        if not is_owner(int(user_id)):
            return
        try:
            unban_user_id = int(update.message.text.strip())
            bot_data.banned_users.discard(unban_user_id)
            bot_data.save_data()
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f'✅ User {unban_user_id} has been unbanned.', reply_markup=reply_markup)
            logger.info(f"Owner unbanned user {unban_user_id}")
        except ValueError:
            await update.message.reply_text('❌ Invalid user ID.')
        context.user_data.pop('awaiting', None)
    
    elif awaiting == 'update_message':
        if not is_owner(int(user_id)):
            return
        message = update.message.text
        sent = 0
        for uid in bot_data.users.keys():
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📣 Bot Update\n\n{message}")
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send to {uid}: {e}")
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'✅ Update message sent to {sent} users.', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"Owner sent update message to {sent} users")
    
    elif awaiting == 'import_data':
        if not is_owner(int(user_id)):
            return
        
        if update.message.document:
            file = await context.bot.get_file(update.message.document.file_id)
            file_data = await file.download_as_bytearray()
            data_str = file_data.decode('utf-8')
            
            if bot_data.import_data(data_str):
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text('✅ Data imported successfully!', reply_markup=reply_markup)
                logger.info("Owner imported data")
            else:
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text('❌ Failed to import data. Check format.', reply_markup=reply_markup)
        else:
            await update.message.reply_text('❌ Please send a JSON file.')
        
        context.user_data.pop('awaiting', None)

async def download_asset(context: ContextTypes.DEFAULT_TYPE, user_id: str, platform: str, repo: str, asset_id: str):
    if platform == 'github':
        if user_id not in bot_data.user_tokens:
            await context.bot.send_message(chat_id=int(user_id), text="❌ GitHub token not set.")
            return
        token = bot_data.user_tokens[user_id]
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/octet-stream'
                }
                
                url = f'https://api.github.com/repos/{repo}/releases/assets/{asset_id}'
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        # Refuse oversized files before downloading them, so a
                        # 2 GB asset is not pulled into memory just to be
                        # rejected. Assets without a Content-Length fall back
                        # to the post-download size check below.
                        declared = response.headers.get('Content-Length')
                        if declared and declared.isdigit() and int(declared) > 50 * 1024 * 1024:
                            await context.bot.send_message(
                                chat_id=int(user_id),
                                text=f"❌ File is too large to send via Telegram (>50MB).\n\nDownload directly: {response.url}"
                            )
                            return

                        file_data = await response.read()

                        content_disposition = response.headers.get('Content-Disposition', '')
                        filename = 'download'
                        if 'filename=' in content_disposition:
                            filename = content_disposition.split('filename=')[1].strip('"')
                        
                        if len(file_data) > 50 * 1024 * 1024:
                            await context.bot.send_message(
                                chat_id=int(user_id),
                                text=f"❌ File is too large to send via Telegram (>50MB).\n\nDownload directly: {response.url}"
                            )
                        else:
                            await context.bot.send_document(
                                chat_id=int(user_id),
                                document=BytesIO(file_data),
                                filename=filename,
                                caption=f"📦 {filename}"
                            )
                            logger.info(f"User {user_id} downloaded GitHub asset {asset_id} from {repo}")
                    else:
                        await context.bot.send_message(
                            chat_id=int(user_id),
                            text=f"❌ Failed to download file. Status: {response.status}"
                        )
        except Exception as e:
            logger.error(f"GitHub download error for user {user_id}: {e}")
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"❌ Download failed: {str(e)}"
            )
    
    elif platform == 'gitlab':
        # GitLab buttons carry an index into the asset list captured when the
        # release notification was sent, so the direct URL is already here and
        # no API round-trip is needed.
        store = context.bot_data.get(f'assets_{user_id}_{repo}')
        if not store or store.get('platform') != 'gitlab':
            await context.bot.send_message(
                chat_id=int(user_id),
                text="⚠️ Session expired. Use 🔄 Check Now to refresh the release list."
            )
            return

        try:
            link = store['assets'][int(asset_id)]
        except (ValueError, IndexError, KeyError):
            await context.bot.send_message(
                chat_id=int(user_id),
                text="⚠️ Could not find that file. Use 🔄 Check Now to refresh."
            )
            return

        direct_url = link.get('direct_asset_url') or link.get('url')
        if direct_url:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"📥 Download link:\n{direct_url}"
            )

async def check_repo_updates(context: ContextTypes.DEFAULT_TYPE, user_id: str, repo: str, force: bool = False):
    key = f"{user_id}_{repo}"
    repo_type = bot_data.repo_types.get(key, 'github')
    
    if repo_type == 'github':
        if user_id not in bot_data.user_tokens:
            return
        token = bot_data.user_tokens[user_id]
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                url = f'https://api.github.com/repos/{repo}/releases/latest'
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        release_tag = data.get('tag_name')
                        release_name = data.get('name') or release_tag
                        release_url = data.get('html_url')
                        published_at = data.get('published_at')
                        body = data.get('body', '')
                        assets = data.get('assets', [])
                        
                        last_release = bot_data.last_releases.get(key)
                        
                        if force or last_release != release_tag:
                            bot_data.last_releases[key] = release_tag
                            bot_data.save_data()
                            
                            if not force and last_release:
                                message = f"🎉 New GitHub Release for {repo}!\n\n"
                                message += f"📦 {release_name}\n"
                                message += f"🏷 Tag: {release_tag}\n"
                                message += f"📅 Published: {published_at}\n\n"
                                
                                if body:
                                    body_preview = body[:500] + "..." if len(body) > 500 else body
                                    message += f"📝 Release Notes:\n{body_preview}\n\n"
                                
                                message += f"🔗 {release_url}\n"
                                
                                if assets:
                                    message += f"\n📥 {len(assets)} file(s) available"
                                    
                                    context.bot_data[f'assets_{user_id}_{repo}'] = {
                                        'assets': assets,
                                        'platform': 'github',
                                        'repo': repo,
                                        'page': 0
                                    }
                                    
                                    keyboard = create_asset_buttons(user_id, 'github', repo, assets, 0)
                                    reply_markup = InlineKeyboardMarkup(keyboard)
                                    
                                    await context.bot.send_message(
                                        chat_id=int(user_id), 
                                        text=message,
                                        reply_markup=reply_markup
                                    )
                                    logger.info(f"Sent GitHub release notification to {user_id} for {repo}")
                                else:
                                    await context.bot.send_message(chat_id=int(user_id), text=message)
                                    logger.info(f"Sent GitHub release notification to {user_id} for {repo} (no assets)")
                    
                    elif response.status == 404:
                        logger.info(f"No releases found for GitHub repo {repo}")
                    else:
                        logger.warning(f"GitHub API returned status {response.status} for {repo}")
        except Exception as e:
            logger.error(f"Error checking GitHub repo {repo} for user {user_id}: {e}")
    
    elif repo_type == 'gitlab':
        if user_id not in bot_data.user_gitlab_tokens:
            return
        token = bot_data.user_gitlab_tokens[user_id]
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'PRIVATE-TOKEN': token
                }
                
                project_id = repo.replace('/', '%2F')
                url = f'https://gitlab.com/api/v4/projects/{project_id}/releases'
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        releases = await response.json()
                        if releases:
                            data = releases[0]
                            release_tag = data.get('tag_name')
                            release_name = data.get('name') or release_tag
                            created_at = data.get('created_at')
                            description = data.get('description', '')
                            assets = data.get('assets', {}).get('links', [])
                            
                            last_release = bot_data.last_releases.get(key)
                            
                            if force or last_release != release_tag:
                                bot_data.last_releases[key] = release_tag
                                bot_data.save_data()
                                
                                if not force and last_release:
                                    message = f"🎉 New GitLab Release for {repo}!\n\n"
                                    message += f"📦 {release_name}\n"
                                    message += f"🏷 Tag: {release_tag}\n"
                                    message += f"📅 Created: {created_at}\n\n"
                                    
                                    if description:
                                        desc_preview = description[:500] + "..." if len(description) > 500 else description
                                        message += f"📝 Release Notes:\n{desc_preview}\n\n"
                                    
                                    message += f"🔗 https://gitlab.com/{repo}/-/releases/{release_tag}\n"
                                    
                                    if assets:
                                        message += f"\n📥 {len(assets)} file(s) available"
                                        
                                        context.bot_data[f'assets_{user_id}_{repo}'] = {
                                            'assets': assets,
                                            'platform': 'gitlab',
                                            'repo': repo,
                                            'tag': release_tag,
                                            'page': 0
                                        }
                                        
                                        keyboard = create_asset_buttons(user_id, 'gitlab', repo, assets, 0, release_tag)
                                        reply_markup = InlineKeyboardMarkup(keyboard)
                                        
                                        await context.bot.send_message(
                                            chat_id=int(user_id), 
                                            text=message,
                                            reply_markup=reply_markup
                                        )
                                        logger.info(f"Sent GitLab release notification to {user_id} for {repo}")
                                    else:
                                        await context.bot.send_message(chat_id=int(user_id), text=message)
                                        logger.info(f"Sent GitLab release notification to {user_id} for {repo} (no assets)")
                    
                    elif response.status == 404:
                        logger.info(f"No releases found for GitLab repo {repo}")
                    else:
                        logger.warning(f"GitLab API returned status {response.status} for {repo}")
        except Exception as e:
            logger.error(f"Error checking GitLab repo {repo} for user {user_id}: {e}")

def create_asset_buttons(user_id, platform, repo, assets, page, tag=None):
    keyboard = []
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_assets = assets[start_idx:end_idx]
    
    for i, asset in enumerate(page_assets):
        if platform == 'github':
            asset_name = asset['name']
            asset_size = asset['size'] / 1024 / 1024
            button_text = f"📥 {asset_name} ({asset_size:.1f}MB)"
            if len(button_text) > 60:
                button_text = button_text[:57] + "..."

            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"download_asset_{user_id}_github_{repo}_{asset['id']}"
            )])
        else:
            asset_name = asset.get('name', 'Download')
            button_text = f"📥 {asset_name}"
            if len(button_text) > 60:
                button_text = button_text[:57] + "..."

            # The absolute index into the stored asset list, not the release
            # tag: tags can be arbitrarily long and would break Telegram's
            # 64-byte callback_data limit.
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"download_asset_{user_id}_gitlab_{repo}_{start_idx + i}"
            )])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"asset_page_{user_id}_{repo}_{page-1}"))
    
    total_pages = (len(assets) + items_per_page - 1) // items_per_page
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"asset_page_{user_id}_{repo}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    if total_pages > 1:
        keyboard.append([InlineKeyboardButton(f"📄 Page {page + 1}/{total_pages}", callback_data="page_info")])
    
    return keyboard

async def check_all_repos(context: ContextTypes.DEFAULT_TYPE):
    while True:
        try:
            # Copy the mapping: users add/remove repos while this loop runs,
            # and iterating a dict while it changes raises RuntimeError.
            for user_id, repos in list(bot_data.repos.items()):
                for repo in repos:
                    key = f"{user_id}_{repo}"
                    interval = bot_data.check_intervals.get(key, 24)
                    
                    last_check_key = f"last_check_{key}"
                    last_check = context.bot_data.get(last_check_key)
                    
                    now = datetime.now()
                    
                    if last_check is None or (now - last_check) >= timedelta(hours=interval):
                        await check_repo_updates(context, user_id, repo)
                        context.bot_data[last_check_key] = now
                    
                    await asyncio.sleep(2)
            
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Error in check loop: {e}")
            await asyncio.sleep(300)

async def send_logs_to_channel(context: ContextTypes.DEFAULT_TYPE):
    if not bot_data.log_channel:
        return
    
    try:
        data_json = bot_data.export_data()
        data_file = BytesIO(data_json.encode('utf-8'))
        data_filename = f"bot_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        await context.bot.send_document(
            chat_id=bot_data.log_channel,
            document=data_file,
            filename=data_filename,
            caption=f"📊 Daily Data Backup\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        if os.path.exists('bot.log'):
            await context.bot.send_document(
                chat_id=bot_data.log_channel,
                document=open('bot.log', 'rb'),
                filename=f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                caption=f"📋 Daily Log Backup\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        logger.info("Logs and data sent to channel successfully")
    except Exception as e:
        logger.error(f"Error sending logs to channel: {e}")

async def daily_log_upload(context: ContextTypes.DEFAULT_TYPE):
    while True:
        try:
            await asyncio.sleep(86400)
            await send_logs_to_channel(context)
        except Exception as e:
            logger.error(f"Error in daily log upload: {e}")
            await asyncio.sleep(3600)

async def start_background_checks(application):
    """post_init hook: runs inside the polling event loop, where create_task
    is safe (unlike before run_polling starts)."""
    application.create_task(check_all_repos(application))
    if bot_data.log_channel:
        application.create_task(daily_log_upload(application))

def main():
    global OWNER_ID
    
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    OWNER_ID_STR = os.getenv('OWNER_ID')
    
    if not BOT_TOKEN or not OWNER_ID_STR:
        logger.error("BOT_TOKEN and OWNER_ID environment variables must be set")
        print("Error: BOT_TOKEN and OWNER_ID environment variables must be set")
        return
    
    try:
        OWNER_ID = int(OWNER_ID_STR)
    except ValueError:
        logger.error("OWNER_ID must be a valid integer")
        print("Error: OWNER_ID must be a valid integer")
        return
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(start_background_checks)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    logger.info("Bot started successfully!")
    print("Bot started successfully!")
    
    if bot_data.required_channel:
        logger.info(f"Required channel: {bot_data.required_channel}")
    if bot_data.log_channel:
        logger.info(f"Log channel: {bot_data.log_channel}")
    
    application.run_polling()

if __name__ == '__main__':
    main()
