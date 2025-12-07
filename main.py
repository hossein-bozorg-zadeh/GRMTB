import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
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

class BotData:
    def __init__(self):
        self.users = {}
        self.repos = {}
        self.user_tokens = {}
        self.check_intervals = {}
        self.last_releases = {}
        self.bot_public = True
        self.special_users = set()
        self.banned_users = set()
        self.load_data()
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                    self.repos = data.get('repos', {})
                    self.user_tokens = data.get('user_tokens', {})
                    self.check_intervals = data.get('check_intervals', {})
                    self.last_releases = data.get('last_releases', {})
                    self.bot_public = data.get('bot_public', True)
                    self.special_users = set(data.get('special_users', []))
                    self.banned_users = set(data.get('banned_users', []))
                logger.info("Data loaded successfully")
            except Exception as e:
                logger.error(f"Error loading data: {e}")
    
    def save_data(self):
        data = {
            'users': self.users,
            'repos': self.repos,
            'user_tokens': self.user_tokens,
            'check_intervals': self.check_intervals,
            'last_releases': self.last_releases,
            'bot_public': self.bot_public,
            'special_users': list(self.special_users),
            'banned_users': list(self.banned_users)
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
            'check_intervals': self.check_intervals,
            'last_releases': self.last_releases,
            'bot_public': self.bot_public,
            'special_users': list(self.special_users),
            'banned_users': list(self.banned_users),
            'export_date': datetime.now().isoformat()
        }, indent=2)
    
    def import_data(self, data_str):
        try:
            data = json.loads(data_str)
            self.users = data.get('users', {})
            self.repos = data.get('repos', {})
            self.user_tokens = data.get('user_tokens', {})
            self.check_intervals = data.get('check_intervals', {})
            self.last_releases = data.get('last_releases', {})
            self.bot_public = data.get('bot_public', True)
            self.special_users = set(data.get('special_users', []))
            self.banned_users = set(data.get('banned_users', []))
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if user_id not in bot_data.users:
        bot_data.users[user_id] = {'username': update.effective_user.username or 'Unknown'}
        bot_data.save_data()
        logger.info(f"New user registered: {user_id}")
    
    keyboard = [
        [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
        [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
        [InlineKeyboardButton("🔑 Set GitHub Token", callback_data='set_token')],
        [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
        [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
    ]
    
    if is_owner(int(user_id)):
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🤖 GitHub Release Notifier Bot\n\nSelect an option:', reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if not can_use_bot(int(user_id)):
        await query.edit_message_text("🔒 Bot is currently private. You don't have access.")
        return
    
    if query.data == 'main_menu':
        keyboard = [
            [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
            [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
            [InlineKeyboardButton("🔑 Set GitHub Token", callback_data='set_token')],
            [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
            [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')]
        ]
        if is_owner(int(user_id)):
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🤖 GitHub Release Notifier Bot\n\nSelect an option:', reply_markup=reply_markup)
    
    elif query.data == 'my_repos':
        user_repos = bot_data.repos.get(user_id, [])
        if not user_repos:
            text = "📋 You have no repositories added.\n\nAdd one using the ➕ Add Repo button."
        else:
            text = "📋 Your Repositories:\n\n"
            for idx, repo in enumerate(user_repos, 1):
                interval = bot_data.check_intervals.get(f"{user_id}_{repo}", 24)
                text += f"{idx}. {repo} (Check: {interval}h)\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
        if user_repos:
            keyboard.insert(0, [InlineKeyboardButton("🗑 Delete Repo", callback_data='delete_repo')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data == 'add_repo':
        context.user_data['awaiting'] = 'repo'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('➕ Add Repository\n\nSend the repository in format: owner/repo\nExample: torvalds/linux', reply_markup=reply_markup)
    
    elif query.data == 'set_token':
        context.user_data['awaiting'] = 'token'
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('🔑 Set GitHub Token\n\nSend your GitHub personal access token.\n\nGet one from: https://github.com/settings/tokens', reply_markup=reply_markup)
    
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
            text += f"{idx}. {repo}\n"
            keyboard.append([InlineKeyboardButton(f"{idx}. {repo}", callback_data=f'interval_select_{repo}')])
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
            text += f"{idx}. {repo}\n"
            keyboard.append([InlineKeyboardButton(f"🗑 {repo}", callback_data=f'delete_{repo}')])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_repos')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif query.data.startswith('delete_'):
        repo = query.data.replace('delete_', '')
        if user_id in bot_data.repos and repo in bot_data.repos[user_id]:
            bot_data.repos[user_id].remove(repo)
            bot_data.check_intervals.pop(f"{user_id}_{repo}", None)
            bot_data.last_releases.pop(f"{user_id}_{repo}", None)
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
        
        if user_id not in bot_data.user_tokens:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("You need to set your GitHub token first.", reply_markup=reply_markup)
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
        parts = query.data.replace('download_asset_', '').split('_', 2)
        user_id_data = parts[0]
        repo = parts[1]
        asset_id = parts[2]
        
        if user_id_data != user_id:
            await query.answer("This is not your download.")
            return
        
        await query.answer("Downloading... Please wait.")
        
        if user_id not in bot_data.user_tokens:
            await query.edit_message_text("❌ GitHub token not set.")
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
                            logger.info(f"User {user_id} downloaded asset {asset_id} from {repo}")
                    else:
                        await context.bot.send_message(
                            chat_id=int(user_id),
                            text=f"❌ Failed to download file. Status: {response.status}"
                        )
        except Exception as e:
            logger.error(f"Download error for user {user_id}: {e}")
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"❌ Download failed: {str(e)}"
            )
    
    elif query.data.startswith('download_all_'):
        parts = query.data.replace('download_all_', '').split('_', 1)
        user_id_data = parts[0]
        repo = parts[1]
        
        if user_id_data != user_id:
            await query.answer("This is not your download.")
            return
        
        await query.answer("Downloading all files... Please wait.")
        
        release_data = context.user_data.get(f'release_{repo}')
        if not release_data:
            await query.edit_message_text("❌ Release data not found.")
            return
        
        assets = release_data.get('assets', [])
        if not assets:
            await query.edit_message_text("❌ No assets found.")
            return
        
        for asset in assets:
            asset_id = asset['id']
            callback_data = f'download_asset_{user_id}_{repo}_{asset_id}'
            fake_query = type('obj', (object,), {'data': callback_data, 'from_user': query.from_user, 'answer': query.answer, 'edit_message_text': query.edit_message_text})()
            await button_callback(update, context)
            await asyncio.sleep(1)
    
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
    
    awaiting = context.user_data.get('awaiting')
    
    if awaiting == 'repo':
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
        bot_data.save_data()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'✅ Repository {repo} added successfully!\nDefault check interval: 24 hours', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} added repo {repo}")
    
    elif awaiting == 'token':
        token = update.message.text.strip()
        bot_data.user_tokens[user_id] = token
        bot_data.save_data()
        await update.message.delete()
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('✅ GitHub token saved successfully!', reply_markup=reply_markup)
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} set GitHub token")
    
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
                await context.bot.send_message(chat_id=int(uid), text=f"📢 Bot Update\n\n{message}")
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

async def check_repo_updates(context: ContextTypes.DEFAULT_TYPE, user_id: str, repo: str, force: bool = False):
    key = f"{user_id}_{repo}"
    
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
                    assets = data.get('assets', [])
                    
                    last_release = bot_data.last_releases.get(key)
                    
                    if force or last_release != release_tag:
                        bot_data.last_releases[key] = release_tag
                        bot_data.save_data()
                        
                        if not force and last_release:
                            message = f"🎉 New Release for {repo}!\n\n"
                            message += f"📦 {release_name}\n"
                            message += f"🏷 Tag: {release_tag}\n"
                            message += f"📅 Published: {published_at}\n"
                            message += f"🔗 {release_url}\n"
                            
                            if assets:
                                message += f"\n📥 {len(assets)} file(s) available"
                                
                                keyboard = []
                                
                                if len(assets) == 1:
                                    asset = assets[0]
                                    keyboard.append([InlineKeyboardButton(
                                        f"📥 Download {asset['name']}", 
                                        callback_data=f"download_asset_{user_id}_{repo}_{asset['id']}"
                                    )])
                                else:
                                    for idx, asset in enumerate(assets[:10], 1):
                                        asset_name = asset['name']
                                        asset_size = asset['size'] / 1024 / 1024
                                        button_text = f"📥 {asset_name} ({asset_size:.1f}MB)"
                                        if len(button_text) > 60:
                                            button_text = button_text[:57] + "..."
                                        
                                        keyboard.append([InlineKeyboardButton(
                                            button_text,
                                            callback_data=f"download_asset_{user_id}_{repo}_{asset['id']}"
                                        )])
                                    
                                    if len(assets) > 1:
                                        keyboard.append([InlineKeyboardButton(
                                            "📦 Download All Files",
                                            callback_data=f"download_all_{user_id}_{repo}"
                                        )])
                                
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                
                                context.user_data[f'release_{repo}'] = data
                                
                                await context.bot.send_message(
                                    chat_id=int(user_id), 
                                    text=message,
                                    reply_markup=reply_markup
                                )
                                logger.info(f"Sent release notification to {user_id} for {repo}")
                            else:
                                await context.bot.send_message(chat_id=int(user_id), text=message)
                                logger.info(f"Sent release notification to {user_id} for {repo} (no assets)")
                
                elif response.status == 404:
                    logger.info(f"No releases found for {repo}")
                else:
                    logger.warning(f"GitHub API returned status {response.status} for {repo}")
    except Exception as e:
        logger.error(f"Error checking {repo} for user {user_id}: {e}")

async def check_all_repos(context: ContextTypes.DEFAULT_TYPE):
    while True:
        try:
            for user_id, repos in bot_data.repos.items():
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
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    
    application.job_queue.run_once(lambda context: asyncio.create_task(check_all_repos(context)), 10)
    
    logger.info("Bot started successfully!")
    print("Bot started successfully!")
    application.run_polling()

if __name__ == '__main__':
    main()
