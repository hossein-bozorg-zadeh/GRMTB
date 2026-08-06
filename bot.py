import os
import json
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO

import aiohttp
from aiohttp import web
from cryptography.fernet import Fernet
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, PreCheckoutQueryHandler, filters

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_FILE = os.getenv('DB_FILE', 'bot_data.db')
GITLAB_COM = 'https://gitlab.com'
OWNER_ID = None

class BotData:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.pending_assets = {}
        self._create_tables()
        self._init_encryption()

    def _create_tables(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            );
            CREATE TABLE IF NOT EXISTS repos (
                user_id INTEGER,
                repo TEXT,
                repo_type TEXT NOT NULL DEFAULT 'github',
                PRIMARY KEY (user_id, repo)
            );
            CREATE TABLE IF NOT EXISTS user_tokens (
                user_id INTEGER PRIMARY KEY,
                github_token TEXT,
                gitlab_token TEXT
            );
            CREATE TABLE IF NOT EXISTS check_intervals (
                user_id INTEGER,
                repo TEXT,
                interval_hours INTEGER NOT NULL DEFAULT 24,
                PRIMARY KEY (user_id, repo)
            );
            CREATE TABLE IF NOT EXISTS last_releases (
                user_id INTEGER,
                repo TEXT,
                release_tag TEXT,
                PRIMARY KEY (user_id, repo)
            );
            CREATE TABLE IF NOT EXISTS last_checks (
                user_id INTEGER,
                repo TEXT,
                checked_at TEXT,
                PRIMARY KEY (user_id, repo)
            );
            CREATE TABLE IF NOT EXISTS gitlab_instances (
                user_id INTEGER,
                repo TEXT,
                base_url TEXT,
                PRIMARY KEY (user_id, repo)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS paid_features (
                feature_key TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                stars_price INTEGER NOT NULL DEFAULT 0,
                ton_price REAL NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS purchases (
                user_id INTEGER,
                feature_key TEXT,
                paid_at TEXT,
                method TEXT,
                txn_id TEXT,
                PRIMARY KEY (user_id, feature_key)
            );
            CREATE TABLE IF NOT EXISTS pending_crypto (
                invoice_id TEXT PRIMARY KEY,
                user_id INTEGER,
                feature_key TEXT,
                created_at TEXT
            );
        ''')
        self.conn.commit()

    def _get_setting(self, key, default=None):
        row = self.conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else default

    def _set_setting(self, key, value):
        self.conn.execute(
            'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value)
        )
        self.conn.commit()

    def _init_encryption(self):
        env_key = os.getenv('TOKEN_ENCRYPTION_KEY')
        if env_key:
            self._fernet = Fernet(env_key.encode())
            logger.info("Encryption key loaded from TOKEN_ENCRYPTION_KEY")
            return
        stored = self._get_setting('encryption_key')
        if stored:
            try:
                self._fernet = Fernet(stored.encode())
                logger.info("Encryption key loaded from database")
                return
            except Exception as e:
                logger.error(f"Invalid stored encryption key, generating a new one: {e}")
        key = Fernet.generate_key()
        self._set_setting('encryption_key', key.decode())
        self._fernet = Fernet(key)
        logger.info("Generated new encryption key")

    def encrypt_token(self, token):
        if not token:
            return token
        if token.startswith('enc:'):
            return token
        try:
            return 'enc:' + self._fernet.encrypt(token.encode()).decode()
        except Exception as e:
            logger.error(f"Token encryption failed: {e}")
            return token

    def decrypt_token(self, stored):
        if not stored:
            return None
        if stored.startswith('enc:'):
            try:
                return self._fernet.decrypt(stored[4:].encode()).decode()
            except Exception as e:
                logger.error(f"Token decryption failed: {e}")
                return None
        return stored

    def save_data(self):
        self.conn.commit()

    def get_users(self):
        users = {}
        for row in self.conn.execute('SELECT user_id, username FROM users'):
            users[str(row['user_id'])] = {'username': row['username']}
        return users

    def add_user(self, user_id, username):
        self.conn.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (int(user_id), username))
        self.conn.commit()

    def get_repos(self, user_id):
        rows = self.conn.execute('SELECT repo FROM repos WHERE user_id = ? ORDER BY repo', (int(user_id),)).fetchall()
        return [row['repo'] for row in rows]

    def get_all_repos(self):
        rows = self.conn.execute('SELECT user_id, repo FROM repos ORDER BY user_id, repo').fetchall()
        return [(str(row['user_id']), row['repo']) for row in rows]

    def has_repo(self, user_id, repo):
        row = self.conn.execute('SELECT 1 FROM repos WHERE user_id = ? AND repo = ?', (int(user_id), repo)).fetchone()
        return row is not None

    def add_repo(self, user_id, repo, repo_type='github', gitlab_base_url=None):
        self.conn.execute('INSERT INTO repos (user_id, repo, repo_type) VALUES (?, ?, ?)', (int(user_id), repo, repo_type))
        self.conn.execute('INSERT OR IGNORE INTO check_intervals (user_id, repo, interval_hours) VALUES (?, ?, 24)', (int(user_id), repo))
        if gitlab_base_url:
            self.conn.execute('INSERT OR REPLACE INTO gitlab_instances (user_id, repo, base_url) VALUES (?, ?, ?)', (int(user_id), repo, gitlab_base_url))
        self.conn.commit()

    def remove_repo(self, user_id, repo):
        self.conn.execute('DELETE FROM repos WHERE user_id = ? AND repo = ?', (int(user_id), repo))
        self.conn.execute('DELETE FROM check_intervals WHERE user_id = ? AND repo = ?', (int(user_id), repo))
        self.conn.execute('DELETE FROM last_releases WHERE user_id = ? AND repo = ?', (int(user_id), repo))
        self.conn.execute('DELETE FROM last_checks WHERE user_id = ? AND repo = ?', (int(user_id), repo))
        self.conn.execute('DELETE FROM gitlab_instances WHERE user_id = ? AND repo = ?', (int(user_id), repo))
        self.conn.commit()

    def get_repo_type(self, user_id, repo):
        row = self.conn.execute('SELECT repo_type FROM repos WHERE user_id = ? AND repo = ?', (int(user_id), repo)).fetchone()
        return row['repo_type'] if row else 'github'

    def get_interval(self, user_id, repo):
        row = self.conn.execute('SELECT interval_hours FROM check_intervals WHERE user_id = ? AND repo = ?', (int(user_id), repo)).fetchone()
        return row['interval_hours'] if row else 24

    def set_interval(self, user_id, repo, hours):
        self.conn.execute(
            'INSERT INTO check_intervals (user_id, repo, interval_hours) VALUES (?, ?, ?) '
            'ON CONFLICT(user_id, repo) DO UPDATE SET interval_hours = excluded.interval_hours',
            (int(user_id), repo, hours)
        )
        self.conn.commit()

    def get_last_release(self, user_id, repo):
        row = self.conn.execute('SELECT release_tag FROM last_releases WHERE user_id = ? AND repo = ?', (int(user_id), repo)).fetchone()
        return row['release_tag'] if row else None

    def set_last_release(self, user_id, repo, tag):
        self.conn.execute(
            'INSERT INTO last_releases (user_id, repo, release_tag) VALUES (?, ?, ?) '
            'ON CONFLICT(user_id, repo) DO UPDATE SET release_tag = excluded.release_tag',
            (int(user_id), repo, tag)
        )
        self.conn.commit()

    def get_last_check(self, user_id, repo):
        row = self.conn.execute('SELECT checked_at FROM last_checks WHERE user_id = ? AND repo = ?', (int(user_id), repo)).fetchone()
        if not row or not row['checked_at']:
            return None
        try:
            return datetime.fromisoformat(row['checked_at'])
        except Exception:
            return None

    def set_last_check(self, user_id, repo, checked_at):
        self.set_last_check_raw(user_id, repo, checked_at.isoformat())

    def set_last_check_raw(self, user_id, repo, checked_at):
        self.conn.execute(
            'INSERT INTO last_checks (user_id, repo, checked_at) VALUES (?, ?, ?) '
            'ON CONFLICT(user_id, repo) DO UPDATE SET checked_at = excluded.checked_at',
            (int(user_id), repo, checked_at)
        )
        self.conn.commit()

    def get_gitlab_base_url(self, user_id, repo):
        row = self.conn.execute('SELECT base_url FROM gitlab_instances WHERE user_id = ? AND repo = ?', (int(user_id), repo)).fetchone()
        return row['base_url'] if row else None

    def get_github_token(self, user_id):
        row = self.conn.execute('SELECT github_token FROM user_tokens WHERE user_id = ?', (int(user_id),)).fetchone()
        return self.decrypt_token(row['github_token']) if row else None

    def set_github_token(self, user_id, token):
        encrypted = self.encrypt_token(token)
        self.conn.execute(
            'INSERT INTO user_tokens (user_id, github_token) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET github_token = excluded.github_token',
            (int(user_id), encrypted)
        )
        self.conn.commit()

    def get_gitlab_token(self, user_id):
        row = self.conn.execute('SELECT gitlab_token FROM user_tokens WHERE user_id = ?', (int(user_id),)).fetchone()
        return self.decrypt_token(row['gitlab_token']) if row else None

    def set_gitlab_token(self, user_id, token):
        encrypted = self.encrypt_token(token)
        self.conn.execute(
            'INSERT INTO user_tokens (user_id, gitlab_token) VALUES (?, ?) '
            'ON CONFLICT(user_id) DO UPDATE SET gitlab_token = excluded.gitlab_token',
            (int(user_id), encrypted)
        )
        self.conn.commit()

    def get_bot_public(self):
        return self._get_setting('bot_public', '1') == '1'

    def set_bot_public(self, value):
        self._set_setting('bot_public', '1' if value else '0')

    def get_special_users(self):
        try:
            return set(json.loads(self._get_setting('special_users', '[]')))
        except Exception:
            return set()

    def add_special_user(self, user_id):
        users = self.get_special_users()
        users.add(int(user_id))
        self._set_setting('special_users', json.dumps(sorted(users)))

    def get_banned_users(self):
        try:
            return set(json.loads(self._get_setting('banned_users', '[]')))
        except Exception:
            return set()

    def ban_user(self, user_id):
        users = self.get_banned_users()
        users.add(int(user_id))
        self._set_setting('banned_users', json.dumps(sorted(users)))

    def unban_user(self, user_id):
        users = self.get_banned_users()
        users.discard(int(user_id))
        self._set_setting('banned_users', json.dumps(sorted(users)))

    def get_required_channel(self):
        return self._get_setting('required_channel')

    def set_required_channel(self, channel):
        self._set_setting('required_channel', channel)

    def remove_required_channel(self):
        self._set_setting('required_channel', '')

    def get_required_channel_link(self):
        return self._get_setting('required_channel_link')

    def set_required_channel_link(self, link):
        self._set_setting('required_channel_link', link)

    def remove_required_channel_link(self):
        self._set_setting('required_channel_link', '')

    def get_joined_members(self):
        try:
            return set(json.loads(self._get_setting('joined_members', '[]')))
        except Exception:
            return set()

    def record_join(self, user_id):
        members = self.get_joined_members()
        if int(user_id) in members:
            return
        members.add(int(user_id))
        self._set_setting('joined_members', json.dumps(sorted(members)))

    def get_features(self):
        features = {}
        for row in self.conn.execute('SELECT * FROM paid_features'):
            features[row['feature_key']] = {
                'title': row['title'],
                'description': row['description'],
                'stars_price': row['stars_price'],
                'ton_price': row['ton_price'],
                'enabled': bool(row['enabled']),
            }
        return features

    def get_feature(self, feature_key):
        row = self.conn.execute('SELECT * FROM paid_features WHERE feature_key = ?', (feature_key,)).fetchone()
        if not row:
            return None
        return {
            'title': row['title'],
            'description': row['description'],
            'stars_price': row['stars_price'],
            'ton_price': row['ton_price'],
            'enabled': bool(row['enabled']),
        }

    def upsert_feature(self, feature_key, title, description, stars_price, ton_price, enabled=1):
        self.conn.execute(
            'INSERT INTO paid_features (feature_key, title, description, stars_price, ton_price, enabled) '
            'VALUES (?, ?, ?, ?, ?, ?) '
            'ON CONFLICT(feature_key) DO UPDATE SET title = excluded.title, description = excluded.description, '
            'stars_price = excluded.stars_price, ton_price = excluded.ton_price, enabled = excluded.enabled',
            (feature_key, title, description, int(stars_price or 0), float(ton_price or 0), 1 if enabled else 0)
        )
        self.conn.commit()

    def remove_feature(self, feature_key):
        self.conn.execute('DELETE FROM paid_features WHERE feature_key = ?', (feature_key,))
        self.conn.execute('DELETE FROM purchases WHERE feature_key = ?', (feature_key,))
        self.conn.execute('DELETE FROM pending_crypto WHERE feature_key = ?', (feature_key,))
        self.conn.commit()

    def has_purchased(self, user_id, feature_key):
        row = self.conn.execute('SELECT 1 FROM purchases WHERE user_id = ? AND feature_key = ?', (int(user_id), feature_key)).fetchone()
        return row is not None

    def record_purchase(self, user_id, feature_key, method, txn_id):
        self.conn.execute(
            'INSERT OR IGNORE INTO purchases (user_id, feature_key, paid_at, method, txn_id) VALUES (?, ?, ?, ?, ?)',
            (int(user_id), feature_key, datetime.now().isoformat(), method, txn_id)
        )
        self.conn.commit()

    def get_purchases(self, user_id):
        rows = self.conn.execute('SELECT feature_key, paid_at, method FROM purchases WHERE user_id = ? ORDER BY paid_at DESC', (int(user_id),)).fetchall()
        return [dict(row) for row in rows]

    def get_all_purchases(self):
        rows = self.conn.execute('SELECT * FROM purchases ORDER BY paid_at DESC').fetchall()
        return [dict(row) for row in rows]

    def is_feature_unlocked(self, user_id, feature_key):
        if is_owner(user_id) or int(user_id) in self.get_special_users():
            return True
        return self.has_purchased(user_id, feature_key)

    def save_pending_crypto(self, invoice_id, user_id, feature_key):
        self.conn.execute(
            'INSERT OR REPLACE INTO pending_crypto (invoice_id, user_id, feature_key, created_at) VALUES (?, ?, ?, ?)',
            (invoice_id, int(user_id), feature_key, datetime.now().isoformat())
        )
        self.conn.commit()

    def get_pending_crypto(self, invoice_id):
        row = self.conn.execute('SELECT * FROM pending_crypto WHERE invoice_id = ?', (invoice_id,)).fetchone()
        return dict(row) if row else None

    def remove_pending_crypto(self, invoice_id):
        self.conn.execute('DELETE FROM pending_crypto WHERE invoice_id = ?', (invoice_id,))
        self.conn.commit()

    def get_log_channel(self):
        return self._get_setting('log_channel')

    def set_log_channel(self, channel):
        self._set_setting('log_channel', channel)

    def remove_log_channel(self):
        self._set_setting('log_channel', '')

    def export_data(self):
        users = self.get_users()
        repos = {}
        repo_types = {}
        for row in self.conn.execute('SELECT user_id, repo, repo_type FROM repos'):
            uid = str(row['user_id'])
            repos.setdefault(uid, []).append(row['repo'])
            repo_types[f"{uid}_{row['repo']}"] = row['repo_type']
        check_intervals = {f"{r['user_id']}_{r['repo']}": r['interval_hours'] for r in self.conn.execute('SELECT user_id, repo, interval_hours FROM check_intervals')}
        last_releases = {f"{r['user_id']}_{r['repo']}": r['release_tag'] for r in self.conn.execute('SELECT user_id, repo, release_tag FROM last_releases')}
        last_checks = {f"{r['user_id']}_{r['repo']}": r['checked_at'] for r in self.conn.execute('SELECT user_id, repo, checked_at FROM last_checks')}
        gitlab_instances = {f"{r['user_id']}_{r['repo']}": r['base_url'] for r in self.conn.execute('SELECT user_id, repo, base_url FROM gitlab_instances')}
        user_tokens = {}
        user_gitlab_tokens = {}
        for row in self.conn.execute('SELECT user_id, github_token, gitlab_token FROM user_tokens'):
            uid = str(row['user_id'])
            if row['github_token']:
                user_tokens[uid] = row['github_token']
            if row['gitlab_token']:
                user_gitlab_tokens[uid] = row['gitlab_token']
        return json.dumps({
            'users': users,
            'repos': repos,
            'user_tokens': user_tokens,
            'user_gitlab_tokens': user_gitlab_tokens,
            'check_intervals': check_intervals,
            'last_releases': last_releases,
            'last_checks': last_checks,
            'gitlab_instances': gitlab_instances,
            'repo_types': repo_types,
            'bot_public': self.get_bot_public(),
            'special_users': sorted(self.get_special_users()),
            'banned_users': sorted(self.get_banned_users()),
            'required_channel': self.get_required_channel() or None,
            'required_channel_link': self.get_required_channel_link() or None,
            'joined_members': sorted(self.get_joined_members()),
            'log_channel': self.get_log_channel() or None,
            'features': self.get_features(),
            'purchases': self.get_all_purchases(),
            'export_date': datetime.now().isoformat()
        }, indent=2)

    def _clear_all(self):
        for table in ['users', 'repos', 'user_tokens', 'check_intervals', 'last_releases', 'last_checks', 'gitlab_instances', 'paid_features', 'purchases', 'pending_crypto']:
            self.conn.execute(f'DELETE FROM {table}')
        self.conn.commit()

    def import_data(self, data_str):
        try:
            data = json.loads(data_str)
            self._clear_all()

            for uid, info in data.get('users', {}).items():
                username = info.get('username', 'Unknown') if isinstance(info, dict) else info
                self.add_user(uid, username)

            repo_types = data.get('repo_types', {})
            gitlab_instances = data.get('gitlab_instances', {})
            for uid, repo_list in data.get('repos', {}).items():
                for repo in repo_list:
                    rtype = repo_types.get(f'{uid}_{repo}', 'github')
                    base_url = gitlab_instances.get(f'{uid}_{repo}')
                    self.add_repo(uid, repo, rtype, base_url)

            for key, hours in (data.get('check_intervals') or {}).items():
                uid, repo = key.split('_', 1)
                self.set_interval(uid, repo, hours)
            for key, tag in (data.get('last_releases') or {}).items():
                uid, repo = key.split('_', 1)
                self.set_last_release(uid, repo, tag)
            for key, ts in (data.get('last_checks') or {}).items():
                uid, repo = key.split('_', 1)
                self.set_last_check_raw(uid, repo, ts)
            for uid, token in (data.get('user_tokens') or {}).items():
                self.set_github_token(uid, token)
            for uid, token in (data.get('user_gitlab_tokens') or {}).items():
                self.set_gitlab_token(uid, token)

            self.set_bot_public(data.get('bot_public', True))
            for uid in data.get('special_users', []):
                self.add_special_user(uid)
            for uid in data.get('banned_users', []):
                self.ban_user(uid)
            if data.get('required_channel'):
                self.set_required_channel(data['required_channel'])
            else:
                self.remove_required_channel()
            if data.get('required_channel_link'):
                self.set_required_channel_link(data['required_channel_link'])
            else:
                self.remove_required_channel_link()
            self._set_setting('joined_members', json.dumps(sorted(set(data.get('joined_members', [])))))
            if data.get('log_channel'):
                self.set_log_channel(data['log_channel'])
            else:
                self.remove_log_channel()

            for key, feat in (data.get('features') or {}).items():
                self.upsert_feature(
                    key, feat.get('title', key), feat.get('description', ''),
                    feat.get('stars_price', 0), feat.get('ton_price', 0), feat.get('enabled', True)
                )
            for purchase in (data.get('purchases') or []):
                try:
                    self.conn.execute(
                        'INSERT OR IGNORE INTO purchases (user_id, feature_key, paid_at, method, txn_id) VALUES (?, ?, ?, ?, ?)',
                        (int(purchase['user_id']), purchase['feature_key'], purchase.get('paid_at', datetime.now().isoformat()),
                         purchase.get('method', 'stars'), purchase.get('txn_id', ''))
                    )
                except Exception as e:
                    logger.error(f"Skipping purchase row: {e}")
            self.conn.commit()

            logger.info("Data imported successfully")
            return True
        except Exception as e:
            logger.error(f"Error importing data: {e}")
            return False

bot_data = BotData()

def is_owner(user_id):
    return user_id == OWNER_ID

def _is_numeric_id(value):
    if not value:
        return False
    v = str(value).strip().lstrip('-')
    return bool(v) and v.isdigit()

def _is_invite_link(value):
    if not value:
        return False
    v = str(value).strip().lower()
    return v.startswith('http') or 't.me/+' in v or 't.me/joinchat' in v

def _channel_join_url():
    link = bot_data.get_required_channel_link()
    if link:
        return link
    channel = bot_data.get_required_channel()
    if channel and not _is_numeric_id(channel):
        return f"https://t.me/{channel.strip().lstrip('@')}"
    return None

def can_use_bot(user_id):
    if user_id in bot_data.get_banned_users():
        return False
    if bot_data.get_bot_public() or user_id in bot_data.get_special_users() or is_owner(user_id):
        return True
    return False

def is_feature_unlocked(user_id, feature_key):
    if is_owner(user_id) or int(user_id) in bot_data.get_special_users():
        return True
    return bot_data.has_purchased(user_id, feature_key)

def feature_locked_keyboard(user_id, feature_key):
    if is_feature_unlocked(user_id, feature_key):
        return None
    feature = bot_data.get_feature(feature_key)
    if not feature:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🔒 Unlock {feature['title']}", callback_data=f'buy_feature|{feature_key}')
    ]])

def _finalize_payment(user_id, feature_key, method, txn_id, invoice_id=None):
    feature = bot_data.get_feature(feature_key)
    if not feature:
        return False
    if bot_data.has_purchased(user_id, feature_key):
        return False
    bot_data.record_purchase(user_id, feature_key, method, txn_id)
    if invoice_id is not None:
        bot_data.remove_pending_crypto(invoice_id)
    logger.info(f"User {user_id} purchased feature '{feature_key}' via {method}")
    return True

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    required_channel = bot_data.get_required_channel()
    if not required_channel:
        return True

    user_id = update.effective_user.id

    if is_owner(user_id) or user_id in bot_data.get_special_users():
        return True

    try:
        member = await context.bot.get_chat_member(required_channel, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            bot_data.record_join(user_id)
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return True

def membership_keyboard():
    url = _channel_join_url()
    keyboard = []
    if url:
        keyboard.append([InlineKeyboardButton("📢 Join Channel", url=url)])
    keyboard.append([InlineKeyboardButton("✅ Check Membership", callback_data='check_membership')])
    return InlineKeyboardMarkup(keyboard)

def main_menu_keyboard(user_id):
    keyboard = [
        [InlineKeyboardButton("📋 My Repos", callback_data='my_repos')],
        [InlineKeyboardButton("➕ Add Repo", callback_data='add_repo')],
        [InlineKeyboardButton("🔑 Set API Tokens", callback_data='set_tokens')],
        [InlineKeyboardButton("⏱ Set Check Interval", callback_data='set_interval')],
        [InlineKeyboardButton("🔄 Check Now", callback_data='check_now')],
        [InlineKeyboardButton("✨ Buy Features", callback_data='feature_store')]
    ]
    if is_owner(int(user_id)):
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return

    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            "⚠️ You must join our channel to use this bot.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
            reply_markup=membership_keyboard()
        )
        return

    if user_id not in bot_data.get_users():
        bot_data.add_user(user_id, update.effective_user.username or 'Unknown')
        logger.info(f"New user registered: {user_id}")

    await update.message.reply_text('🔔 GitHub/GitLab Release Notifier\n\nSelect an option:', reply_markup=main_menu_keyboard(user_id))

# ---------------------------------------------------------------- callback handlers

async def _callback_check_membership(update, query, context, user_id, data):
    if await check_channel_membership(update, context):
        await query.edit_message_text(
            '🔔 GitHub/GitLab Release Notifier\n\n✅ Membership verified! Select an option:',
            reply_markup=main_menu_keyboard(user_id)
        )
    else:
        await query.edit_message_text(
            "❌ You haven't joined the channel yet.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
            reply_markup=membership_keyboard()
        )

async def _callback_main_menu(update, query, context, user_id, data):
    await query.edit_message_text('🔔 GitHub/GitLab Release Notifier\n\nSelect an option:', reply_markup=main_menu_keyboard(user_id))

async def _callback_my_repos(update, query, context, user_id, data):
    user_repos = bot_data.get_repos(user_id)
    if not user_repos:
        text = "📋 You have no repositories added.\n\nAdd one using the ➕ Add Repo button."
    else:
        text = "📋 Your Repositories:\n\n"
        for idx, repo in enumerate(user_repos, 1):
            interval = bot_data.get_interval(user_id, repo)
            repo_type = bot_data.get_repo_type(user_id, repo)
            icon = "🤖" if repo_type == 'github' else "🦊"
            suffix = " (self-hosted)" if repo_type == 'gitlab' and bot_data.get_gitlab_base_url(user_id, repo) else ""
            text += f"{idx}. {icon} {repo}{suffix} (Check: {interval}h)\n"

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]]
    if user_repos:
        keyboard.insert(0, [InlineKeyboardButton("🗑 Delete Repo", callback_data='delete_repo')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_add_repo(update, query, context, user_id, data):
    keyboard = [
        [InlineKeyboardButton("🤖 GitHub Repository", callback_data='add_github')],
        [InlineKeyboardButton("🦊 GitLab Repository", callback_data='add_gitlab')],
        [InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]
    ]
    await query.edit_message_text('➕ Add Repository\n\nSelect platform:', reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_add_repo_platform(update, query, context, user_id, data):
    if data == 'add_github':
        context.user_data['awaiting'] = 'github_repo'
        await query.edit_message_text(
            '➕ Add GitHub Repository\n\nSend the repository in format: owner/repo\nExample: torvalds/linux',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]])
        )
    else:
        context.user_data['awaiting'] = 'gitlab_repo'
        await query.edit_message_text(
            '➕ Add GitLab Repository\n\nSend the repository in format: owner/repo\nExample: gitlab-org/gitlab',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]])
        )

async def _callback_set_tokens(update, query, context, user_id, data):
    keyboard = [
        [InlineKeyboardButton("🤖 Set GitHub Token", callback_data='set_github_token')],
        [InlineKeyboardButton("🦊 Set GitLab Token", callback_data='set_gitlab_token')],
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    await query.edit_message_text('🔑 Set API Tokens\n\nSelect platform:', reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_set_token_platform(update, query, context, user_id, data):
    if data == 'set_github_token':
        context.user_data['awaiting'] = 'github_token'
        await query.edit_message_text(
            '🔑 Set GitHub Token\n\nSend your GitHub personal access token.\n\nGet one from: https://github.com/settings/tokens',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='set_tokens')]])
        )
    else:
        context.user_data['awaiting'] = 'gitlab_token'
        await query.edit_message_text(
            '🔑 Set GitLab Token\n\nSend your GitLab personal access token.\n\nGet one from: https://gitlab.com/-/user_settings/personal_access_tokens',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='set_tokens')]])
        )

async def _callback_set_interval(update, query, context, user_id, data):
    user_repos = bot_data.get_repos(user_id)
    if not user_repos:
        await query.edit_message_text(
            "You need to add repositories first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]])
        )
        return

    context.user_data['awaiting'] = 'interval_repo'
    text = "⏱ Set Check Interval\n\nSelect a repository:\n\n"
    keyboard = []
    for idx, repo in enumerate(user_repos, 1):
        repo_type = bot_data.get_repo_type(user_id, repo)
        icon = "🤖" if repo_type == 'github' else "🦊"
        text += f"{idx}. {icon} {repo}\n"
        keyboard.append([InlineKeyboardButton(f"{idx}. {icon} {repo}", callback_data=f'interval_select|{repo}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_interval_select(update, query, context, user_id, data):
    repo = data.split('|', 1)[1]
    context.user_data['interval_repo'] = repo
    keyboard = [
        [InlineKeyboardButton("⏰ 6 hours", callback_data='interval_set|6')],
        [InlineKeyboardButton("⏰ 12 hours", callback_data='interval_set|12')],
        [InlineKeyboardButton("⏰ 24 hours", callback_data='interval_set|24')],
        [InlineKeyboardButton("⏰ 48 hours", callback_data='interval_set|48')],
        [InlineKeyboardButton("⏰ 72 hours", callback_data='interval_set|72')],
        [InlineKeyboardButton("🔙 Back", callback_data='set_interval')]
    ]
    await query.edit_message_text(f'⏱ Set check interval for:\n{repo}', reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_interval_set(update, query, context, user_id, data):
    try:
        hours = int(data.split('|', 1)[1])
    except (ValueError, IndexError):
        await query.answer("Invalid interval.")
        return
    repo = context.user_data.get('interval_repo')
    if repo:
        bot_data.set_interval(user_id, repo, hours)
        await query.edit_message_text(
            f'✅ Check interval set to {hours} hours for {repo}',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
        )
        logger.info(f"User {user_id} set interval {hours}h for {repo}")

async def _callback_delete_repo(update, query, context, user_id, data):
    user_repos = bot_data.get_repos(user_id)
    text = "🗑 Delete Repository\n\nSelect a repository to delete:\n\n"
    keyboard = []
    for idx, repo in enumerate(user_repos, 1):
        repo_type = bot_data.get_repo_type(user_id, repo)
        icon = "🤖" if repo_type == 'github' else "🦊"
        text += f"{idx}. {icon} {repo}\n"
        keyboard.append([InlineKeyboardButton(f"🗑 {icon} {repo}", callback_data=f'delete|{repo}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_repos')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_delete_confirm(update, query, context, user_id, data):
    repo = data.split('|', 1)[1]
    if bot_data.has_repo(user_id, repo):
        bot_data.remove_repo(user_id, repo)
        await query.edit_message_text(
            f'✅ Repository {repo} deleted successfully.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
        )
        logger.info(f"User {user_id} deleted repo {repo}")

async def _callback_check_now(update, query, context, user_id, data):
    user_repos = bot_data.get_repos(user_id)
    if not user_repos:
        await query.edit_message_text(
            "You have no repositories to check.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]])
        )
        return

    github_token = bot_data.get_github_token(user_id)
    gitlab_token = bot_data.get_gitlab_token(user_id)

    if not github_token and not gitlab_token:
        await query.edit_message_text(
            "You need to set at least one API token first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]])
        )
        return

    await query.edit_message_text("🔄 Checking for updates...")
    checked = 0
    for repo in user_repos:
        await check_repo_updates(context, user_id, repo, force=True)
        checked += 1

    await query.edit_message_text(
        f'✅ Checked {checked} repositories.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
    )
    logger.info(f"User {user_id} manually checked {checked} repos")

async def _callback_page_info(update, query, context, user_id, data):
    await query.answer("Use ⬅️ Previous and ➡️ Next to navigate")

async def _callback_asset_page(update, query, context, user_id, data):
    parts = data.split('|')
    if len(parts) != 5:
        await query.answer("Invalid navigation data.")
        return
    _, uid, repo, tag, page_str = parts
    if uid != user_id:
        await query.answer("This is not your download.")
        return
    try:
        page = int(page_str)
    except ValueError:
        await query.answer("Invalid page.")
        return

    pending = bot_data.pending_assets.get(f'{user_id}_{repo}_{tag}')
    if not pending:
        await query.answer("Session expired. Please check for updates again.")
        return

    platform = pending['platform']
    assets = pending['assets']
    keyboard = create_asset_buttons(user_id, platform, repo, assets, page, tag)
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer(f"Page {page + 1}")
    except Exception as e:
        logger.error(f"Error changing page: {e}")
        await query.answer("Error changing page")

async def _callback_download_asset(update, query, context, user_id, data):
    parts = data.split('|')
    if len(parts) != 6:
        await query.answer("Invalid download data.")
        return
    _, uid, platform, repo, tag, idx_str = parts
    if uid != user_id:
        await query.answer("This is not your download.")
        return
    try:
        idx = int(idx_str)
    except ValueError:
        await query.answer("Invalid file selection.")
        return

    await query.answer("Downloading... Please wait.")
    await download_asset(context, user_id, platform, repo, tag, idx)

async def _callback_admin_panel(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        await query.edit_message_text("❌ You don't have permission to access the admin panel.")
        return

    status = "🟢 Public" if bot_data.get_bot_public() else "🔴 Private"
    total_users = len(bot_data.get_users())
    special_users = len(bot_data.get_special_users())
    banned_users = len(bot_data.get_banned_users())
    joined_members = len(bot_data.get_joined_members())

    text = f"👑 Admin Panel\n\nBot Status: {status}\nTotal Users: {total_users}\nSpecial Users: {special_users}\nBanned Users: {banned_users}\nJoined via bot link: {joined_members}\n"

    required_channel = bot_data.get_required_channel()
    log_channel = bot_data.get_log_channel()
    if required_channel:
        text += f"\nRequired Channel: {required_channel}"
        join_url = _channel_join_url()
        text += f"\nJoin Link: {join_url}" if join_url else "\nJoin Link: Not Set"
    else:
        text += "\nRequired Channel: Not Set"
    text += f"\nLog Channel: {log_channel}" if log_channel else "\nLog Channel: Not Set"

    keyboard = [
        [InlineKeyboardButton(f"🔄 Toggle Bot Status ({status})", callback_data='toggle_public')],
        [InlineKeyboardButton("📢 Set Required Channel", callback_data='set_required_channel')],
        [InlineKeyboardButton("📊 Set Log Channel", callback_data='set_log_channel')],
        [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
        [InlineKeyboardButton("💰 Paid Features", callback_data='paid_features')],
        [InlineKeyboardButton("📣 Send Update Message", callback_data='send_update')],
        [InlineKeyboardButton("💾 Download Data", callback_data='download_data')],
        [InlineKeyboardButton("📋 Download Logs", callback_data='download_logs')],
        [InlineKeyboardButton("📥 Import Data", callback_data='import_data')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_set_required_channel(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'required_channel'
    keyboard = [
        [InlineKeyboardButton("🚫 Remove Channel Requirement", callback_data='remove_required_channel')],
        [InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]
    ]
    await query.edit_message_text(
        '📢 Set Required Channel\n\nSend the channel username (e.g., @mychannel) or numeric chat ID.\n\n'
        'For private channels, you will be asked for the invite link (or type "auto" so the bot generates one).\n\n'
        'Users must join this channel to use the bot.',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _callback_remove_required_channel(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    bot_data.remove_required_channel()
    bot_data.remove_required_channel_link()
    await query.edit_message_text(
        '✅ Required channel removed. All users can now access the bot.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
    )
    logger.info("Required channel removed")

async def _callback_set_log_channel(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'log_channel'
    keyboard = [
        [InlineKeyboardButton("🚫 Remove Log Channel", callback_data='remove_log_channel')],
        [InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]
    ]
    await query.edit_message_text(
        '📊 Set Log Channel\n\nSend the channel username (e.g., @mylogs) or ID.\n\nDaily backups will be sent here.',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def _callback_remove_log_channel(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    bot_data.remove_log_channel()
    await query.edit_message_text(
        '✅ Log channel removed. Automatic backups disabled.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
    )
    logger.info("Log channel removed")

async def _callback_toggle_public(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    bot_data.set_bot_public(not bot_data.get_bot_public())
    status = "🟢 Public" if bot_data.get_bot_public() else "🔴 Private"
    await query.edit_message_text(
        f'✅ Bot is now {status}',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
    )
    logger.info(f"Bot status changed to {status}")

async def _callback_download_data(update, query, context, user_id, data):
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
    await query.edit_message_text(
        "✅ Data exported successfully!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
    )
    logger.info("Owner downloaded data export")

async def _callback_download_logs(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return

    if os.path.exists('bot.log'):
        await context.bot.send_document(
            chat_id=int(user_id),
            document=open('bot.log', 'rb'),
            filename=f"bot_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            caption="📋 Bot Logs"
        )
        await query.edit_message_text(
            "✅ Logs downloaded successfully!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
        )
        logger.info("Owner downloaded logs")
    else:
        await query.edit_message_text(
            "❌ No log file found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
        )

async def _callback_import_data(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'import_data'
    await query.edit_message_text(
        '📥 Import Data\n\nSend the JSON file to import.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]])
    )

async def _callback_manage_users(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    keyboard = [
        [InlineKeyboardButton("➕ Add Special User", callback_data='add_special')],
        [InlineKeyboardButton("🚫 Ban User", callback_data='ban_user')],
        [InlineKeyboardButton("✅ Unban User", callback_data='unban_user')],
        [InlineKeyboardButton("📋 List Users", callback_data='list_users')],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]
    ]
    await query.edit_message_text('👥 Manage Users', reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_add_special(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'add_special'
    await query.edit_message_text(
        '➕ Add Special User\n\nSend the user ID:',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='manage_users')]])
    )

async def _callback_ban_user(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'ban_user'
    await query.edit_message_text(
        '🚫 Ban User\n\nSend the user ID:',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='manage_users')]])
    )

async def _callback_unban_user(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'unban_user'
    await query.edit_message_text(
        '✅ Unban User\n\nSend the user ID:',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='manage_users')]])
    )

async def _callback_list_users(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    text = "📋 Users List\n\n"
    for uid, info in bot_data.get_users().items():
        username = info.get('username', 'Unknown')
        special = "⭐" if int(uid) in bot_data.get_special_users() else ""
        banned = "🚫" if int(uid) in bot_data.get_banned_users() else ""
        text += f"{uid} - @{username} {special}{banned}\n"
    await query.edit_message_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]])
    )

async def _callback_send_update(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['awaiting'] = 'update_message'
    await query.edit_message_text(
        '📣 Send Update Message\n\nType the message to send to all users:',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel')]])
    )

# ---------------------------------------------------------------- paid features

async def _callback_feature_store(update, query, context, user_id, data):
    features = bot_data.get_features()
    enabled = {k: v for k, v in features.items() if v['enabled']}
    if not enabled:
        await query.edit_message_text(
            '✨ Feature Store\n\nNo paid features available yet.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='main_menu')]])
        )
        return

    text = '✨ Feature Store\n\nUnlock premium features:\n\n'
    keyboard = []
    for i, (key, feat) in enumerate(enabled.items(), 1):
        owned = is_feature_unlocked(int(user_id), key)
        prices = []
        if feat['stars_price']:
            prices.append(f"{feat['stars_price']}⭐")
        if feat['ton_price']:
            prices.append(f"{feat['ton_price']} TON")
        mark = "✅" if owned else "🔒"
        text += f"{i}. {mark} {feat['title']} — {', '.join(prices)}\n"
        label = f"{mark} {feat['title']}"
        keyboard.append([InlineKeyboardButton(label[:60], callback_data=f'buy_feature|{key}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='main_menu')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_buy_feature(update, query, context, user_id, data):
    key = data.split('|', 1)[1]
    feat = bot_data.get_feature(key)
    if not feat:
        await query.answer("Feature not found.")
        return

    if is_feature_unlocked(int(user_id), key):
        await query.edit_message_text(
            f"✅ You already own: {feat['title']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='feature_store')]])
        )
        return

    text = f"🔒 {feat['title']}\n\n{feat['description'] or 'No description available.'}\n\n"
    prices = []
    if feat['stars_price']:
        prices.append(f"⭐ {feat['stars_price']} Stars")
    if feat['ton_price']:
        prices.append(f"💎 {feat['ton_price']} TON")
    text += "Price: " + " / ".join(prices)

    keyboard = []
    if feat['stars_price']:
        keyboard.append([InlineKeyboardButton(f"⭐ Pay {feat['stars_price']} Stars", callback_data=f'pay_stars|{key}')])
    if feat['ton_price']:
        keyboard.append([InlineKeyboardButton(f"💎 Pay {feat['ton_price']} TON", callback_data=f'pay_ton|{key}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='feature_store')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_pay_stars(update, query, context, user_id, data):
    key = data.split('|', 1)[1]
    feat = bot_data.get_feature(key)
    if not feat or not feat['enabled'] or not feat['stars_price']:
        await query.answer("Feature not available.")
        return
    try:
        await context.bot.send_invoice(
            chat_id=int(user_id),
            title=feat['title'][:64],
            description=(feat['description'] or '')[:255],
            payload=f"stars:{key}",
            provider_token='',
            currency='XTR',
            prices=[LabeledPrice(label='⭐', amount=int(feat['stars_price']))],
        )
        await query.answer("Invoice sent!")
    except Exception as e:
        logger.error(f"send_invoice error for user {user_id}: {e}")
        await query.edit_message_text(f"❌ Could not create the invoice.\n\nMake sure payments (Telegram Stars) are enabled in @BotFather.\n\nError: {e}")

async def _callback_pay_ton(update, query, context, user_id, data):
    key = data.split('|', 1)[1]
    feat = bot_data.get_feature(key)
    if not feat or not feat['enabled'] or not feat['ton_price']:
        await query.answer("Feature not available.")
        return

    token = os.getenv('CRYPTO_BOT_TOKEN')
    if not token:
        await query.edit_message_text("❌ TON payments are not configured yet. Contact the owner.")
        return

    public_url = os.getenv('PUBLIC_URL', '').rstrip('/')
    callback_url = f"{public_url}/cb_webhook" if public_url else None
    payload_str = f"ton:{user_id}:{key}"

    try:
        async with aiohttp.ClientSession() as session:
            body = {
                'asset': 'TON',
                'amount': str(feat['ton_price']),
                'description': feat['title'][:255],
                'payload': payload_str,
            }
            if callback_url:
                body['callback_url'] = callback_url
            async with session.post(
                'https://pay.crypt.bot/api/createInvoice',
                headers={'Crypto-Pay-API-Token': token},
                json=body
            ) as response:
                data = await response.json()
                if data.get('ok'):
                    result = data['result']
                    invoice_id = result['invoice_id']
                    pay_url = result['pay_url']
                    bot_data.save_pending_crypto(invoice_id, user_id, key)
                    keyboard = [
                        [InlineKeyboardButton(f"💎 Pay {feat['ton_price']} TON", url=pay_url)],
                        [InlineKeyboardButton("✅ I've paid — Check", callback_data=f'crypto_check|{invoice_id}|{key}')],
                        [InlineKeyboardButton("🔙 Back", callback_data='feature_store')]
                    ]
                    await query.edit_message_text(
                        f"💎 Pay with TON\n\nFeature: {feat['title']}\nAmount: {feat['ton_price']} TON\n\n"
                        f"1️⃣ Tap the pay button (opens @CryptoBot)\n2️⃣ Complete the payment\n3️⃣ Tap 'I've paid — Check'",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    error_msg = (data.get('error') or {}).get('message', 'unknown error')
                    await query.edit_message_text(f"❌ Failed to create TON invoice: {error_msg}")
    except Exception as e:
        logger.error(f"CryptoBot createInvoice error for user {user_id}: {e}")
        await query.edit_message_text(f"❌ TON payment error: {e}")

async def _callback_crypto_check(update, query, context, user_id, data):
    parts = data.split('|')
    if len(parts) != 3:
        await query.answer("Invalid payment data.")
        return
    _, invoice_id, key = parts
    pending = bot_data.get_pending_crypto(invoice_id)
    if not pending or int(pending['user_id']) != int(user_id):
        await query.answer("This payment does not belong to you.")
        return

    result = await _query_crypto_invoice(invoice_id)
    if result and result.get('status') == 'paid':
        txn_id = result.get('hash') or str(invoice_id)
        if _finalize_payment(int(user_id), key, 'crypto_bot', txn_id, invoice_id):
            await query.edit_message_text(
                "✅ Payment confirmed! Feature unlocked.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Back to Store", callback_data='feature_store')]])
            )
        else:
            await query.edit_message_text(
                "❌ Invalid feature or already unlocked.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='feature_store')]])
            )
    else:
        await query.edit_message_text(
            "⏳ Payment not found yet. If you already paid, wait a moment and try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Check again", callback_data=f'crypto_check|{invoice_id}|{key}')]])
        )

async def _callback_paid_features(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    features = bot_data.get_features()
    if not features:
        text = "💰 Paid Features\n\nNo features yet. Add one with ➕ Add/Edit Feature."
    else:
        text = "💰 Paid Features\n\n"
        for key, feat in features.items():
            status = "🟢" if feat['enabled'] else "🔴"
            stars = f"{feat['stars_price']}⭐" if feat['stars_price'] else "-"
            ton = f"{feat['ton_price']} TON" if feat['ton_price'] else "-"
            text += f"{status} {key}: {feat['title']} — {stars} / {ton}\n"

    keyboard = [
        [InlineKeyboardButton("➕ Add/Edit Feature", callback_data='add_feature')],
        [InlineKeyboardButton("📋 Purchases", callback_data='feature_purchases')],
    ]
    for key in features:
        keyboard.append([
            InlineKeyboardButton(f"🔄 Toggle {key}", callback_data=f'toggle_feature|{key}'),
            InlineKeyboardButton(f"🗑 {key}", callback_data=f'delete_feature|{key}')
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def _callback_add_feature(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    context.user_data['feature_pending'] = {}
    context.user_data['awaiting'] = 'feature_key'
    await query.edit_message_text(
        '➕ Add/Edit Feature\n\nSend the feature key (short snake_case, e.g. "premium_alerts").\nUsing an existing key edits that feature.',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data='paid_features')]])
    )

async def _callback_toggle_feature(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    key = data.split('|', 1)[1]
    feat = bot_data.get_feature(key)
    if not feat:
        await query.answer("Feature not found.")
        return
    bot_data.upsert_feature(key, feat['title'], feat['description'], feat['stars_price'], feat['ton_price'], enabled=not feat['enabled'])
    status = "enabled" if bot_data.get_feature(key)['enabled'] else "disabled"
    await query.edit_message_text(
        f"✅ Feature '{key}' is now {status}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='paid_features')]])
    )

async def _callback_delete_feature(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    key = data.split('|', 1)[1]
    bot_data.remove_feature(key)
    await query.edit_message_text(
        f"✅ Feature '{key}' deleted.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='paid_features')]])
    )

async def _callback_feature_purchases(update, query, context, user_id, data):
    if not is_owner(int(user_id)):
        return
    purchases = bot_data.get_all_purchases()
    if not purchases:
        await query.edit_message_text(
            "📋 Purchases\n\nNo purchases yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='paid_features')]])
        )
        return
    text = "📋 Purchases\n\n"
    for p in purchases:
        text += f"{p['user_id']} — {p['feature_key']} ({p['method']})\n"
    await query.edit_message_text(
        text[:4000],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='paid_features')]])
    )

EXACT_CALLBACK_HANDLERS = {
    'check_membership': _callback_check_membership,
    'main_menu': _callback_main_menu,
    'my_repos': _callback_my_repos,
    'add_repo': _callback_add_repo,
    'add_github': _callback_add_repo_platform,
    'add_gitlab': _callback_add_repo_platform,
    'set_tokens': _callback_set_tokens,
    'set_github_token': _callback_set_token_platform,
    'set_gitlab_token': _callback_set_token_platform,
    'set_interval': _callback_set_interval,
    'delete_repo': _callback_delete_repo,
    'check_now': _callback_check_now,
    'page_info': _callback_page_info,
    'admin_panel': _callback_admin_panel,
    'set_required_channel': _callback_set_required_channel,
    'remove_required_channel': _callback_remove_required_channel,
    'set_log_channel': _callback_set_log_channel,
    'remove_log_channel': _callback_remove_log_channel,
    'toggle_public': _callback_toggle_public,
    'download_data': _callback_download_data,
    'download_logs': _callback_download_logs,
    'import_data': _callback_import_data,
    'manage_users': _callback_manage_users,
    'add_special': _callback_add_special,
    'ban_user': _callback_ban_user,
    'unban_user': _callback_unban_user,
    'list_users': _callback_list_users,
    'send_update': _callback_send_update,
    'feature_store': _callback_feature_store,
    'paid_features': _callback_paid_features,
    'add_feature': _callback_add_feature,
    'feature_purchases': _callback_feature_purchases,
}

PREFIX_CALLBACK_HANDLERS = [
    ('interval_select|', _callback_interval_select),
    ('interval_set|', _callback_interval_set),
    ('delete|', _callback_delete_confirm),
    ('asset_page|', _callback_asset_page),
    ('download_asset|', _callback_download_asset),
    ('buy_feature|', _callback_buy_feature),
    ('pay_stars|', _callback_pay_stars),
    ('pay_ton|', _callback_pay_ton),
    ('crypto_check|', _callback_crypto_check),
    ('toggle_feature|', _callback_toggle_feature),
    ('delete_feature|', _callback_delete_feature),
]

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)

    if not can_use_bot(int(user_id)):
        await query.edit_message_text("🔒 Bot is currently private. You don't have access.")
        return

    if not await check_channel_membership(update, context):
        await query.edit_message_text(
            "⚠️ You must join our channel to use this bot.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
            reply_markup=membership_keyboard()
        )
        return

    data = query.data

    handler = EXACT_CALLBACK_HANDLERS.get(data)
    if handler:
        await handler(update, query, context, user_id, data)
        return

    for prefix, handler in PREFIX_CALLBACK_HANDLERS:
        if data.startswith(prefix):
            await handler(update, query, context, user_id, data)
            return

    logger.warning(f"Unhandled callback: {data}")

# ---------------------------------------------------------------- message handler

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    if not can_use_bot(int(user_id)):
        await update.message.reply_text("🔒 Bot is currently private. You don't have access.")
        return

    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            "⚠️ You must join our channel to use this bot.\n\n1️⃣ Click 'Join Channel' below\n2️⃣ Join the channel\n3️⃣ Click 'Check Membership'",
            reply_markup=membership_keyboard()
        )
        return

    awaiting = context.user_data.get('awaiting')

    if awaiting == 'github_repo':
        repo = update.message.text.strip()
        if '/' not in repo or repo.count('/') != 1:
            await update.message.reply_text('❌ Invalid format. Use: owner/repo')
            return

        if bot_data.has_repo(user_id, repo):
            await update.message.reply_text('❌ Repository already added.')
            return

        bot_data.add_repo(user_id, repo, 'github')
        await update.message.reply_text(
            f'✅ GitHub repository {repo} added successfully!\nDefault check interval: 24 hours',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} added GitHub repo {repo}")

    elif awaiting == 'gitlab_repo':
        repo = update.message.text.strip()
        if '/' not in repo or repo.count('/') != 1:
            await update.message.reply_text('❌ Invalid format. Use: owner/repo')
            return

        if bot_data.has_repo(user_id, repo):
            await update.message.reply_text('❌ Repository already added.')
            return

        context.user_data['pending_gitlab_repo'] = repo
        context.user_data['awaiting'] = 'gitlab_base'
        await update.message.reply_text(
            '✅ Repository format accepted.\n\nSend your GitLab instance URL (e.g., https://gitlab.example.com)\nor send "skip" to use gitlab.com:'
        )

    elif awaiting == 'gitlab_base':
        repo = context.user_data.get('pending_gitlab_repo')
        if not repo:
            await update.message.reply_text('❌ Something went wrong. Please add the repository again.')
            context.user_data.pop('awaiting', None)
            return

        raw = update.message.text.strip()
        base_url = None
        if raw and raw.lower() not in ('skip', '-', 'none', 'no', 'default'):
            if '://' not in raw:
                raw = 'https://' + raw
            base_url = raw.rstrip('/')

        if bot_data.has_repo(user_id, repo):
            await update.message.reply_text('❌ Repository already added.')
            context.user_data.pop('awaiting', None)
            context.user_data.pop('pending_gitlab_repo', None)
            return

        bot_data.add_repo(user_id, repo, 'gitlab', base_url)
        instance = base_url or GITLAB_COM
        await update.message.reply_text(
            f'✅ GitLab repository {repo} added successfully!\nInstance: {instance}\nDefault check interval: 24 hours',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
        )
        context.user_data.pop('awaiting', None)
        context.user_data.pop('pending_gitlab_repo', None)
        logger.info(f"User {user_id} added GitLab repo {repo} on {instance}")

    elif awaiting == 'github_token':
        token = update.message.text.strip()
        bot_data.set_github_token(user_id, token)
        await update.message.delete()
        await update.message.reply_text(
            '✅ GitHub token saved successfully!',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} set GitHub token")

    elif awaiting == 'gitlab_token':
        token = update.message.text.strip()
        bot_data.set_gitlab_token(user_id, token)
        await update.message.delete()
        await update.message.reply_text(
            '✅ GitLab token saved successfully!',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"User {user_id} set GitLab token")

    elif awaiting == 'required_channel':
        if not is_owner(int(user_id)):
            return
        raw = update.message.text.strip()
        if _is_invite_link(raw):
            bot_data.set_required_channel_link(raw)
            context.user_data['awaiting'] = 'required_channel_id'
            await update.message.reply_text(
                '✅ Private channel invite link saved.\n\nNow send the channel username (e.g., @mychannel) or numeric chat ID so the bot can verify membership:'
            )
            return
        bot_data.set_required_channel(raw)
        bot_data.remove_required_channel_link()
        if _is_numeric_id(raw):
            context.user_data['awaiting'] = 'required_channel_link'
            await update.message.reply_text(
                '✅ Channel ID saved. This looks like a private channel.\n\n'
                'Send the invite link (https://t.me/+xxxx) —\nor send "auto" to let the bot generate the invite link (the bot must be an admin of the channel) —\nor send "skip" to set it up later.'
            )
            return
        bot_data.set_required_channel_link(f"https://t.me/{raw.lstrip('@')}")
        await update.message.reply_text(
            f'✅ Required channel set to: {raw}\n\nUsers must now join this channel to use the bot.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"Required channel set to {raw}")

    elif awaiting == 'required_channel_link':
        if not is_owner(int(user_id)):
            return
        raw = update.message.text.strip()
        channel = bot_data.get_required_channel()
        if raw.lower() == 'auto':
            try:
                link = await context.bot.export_chat_invite_link(chat_id=channel)
                bot_data.set_required_channel_link(link)
                await update.message.reply_text(
                    f'✅ Invite link generated by the bot:\n{link}\n\nUsers must now join this channel to use the bot.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
                )
                context.user_data.pop('awaiting', None)
                logger.info(f"Generated invite link for channel {channel}")
            except Exception as e:
                logger.error(f"Failed to generate invite link: {e}")
                await update.message.reply_text(
                    f'❌ Failed to generate invite link. Make sure the bot is an admin of the channel with invite-link permissions.\n\n'
                    f'Error: {e}\n\nSend the invite link manually or send "skip".'
                )
            return
        if raw.lower() != 'skip':
            bot_data.set_required_channel_link(raw)
        link_display = _channel_join_url() or 'Not set'
        await update.message.reply_text(
            f'✅ Required channel set to: {channel}\nJoin link: {link_display}\n\nUsers must now join this channel to use the bot.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"Required channel link set for channel {channel}")

    elif awaiting == 'required_channel_id':
        if not is_owner(int(user_id)):
            return
        raw = update.message.text.strip()
        if not _is_invite_link(raw):
            bot_data.set_required_channel(raw)
        link_display = _channel_join_url() or 'Not set'
        await update.message.reply_text(
            f'✅ Required channel set to: {raw}\nJoin link: {link_display}\n\nUsers must now join this channel to use the bot.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"Required channel set to {raw}")

    elif awaiting == 'log_channel':
        if not is_owner(int(user_id)):
            return
        channel = update.message.text.strip()
        bot_data.set_log_channel(channel)
        await update.message.reply_text(
            f'✅ Log channel set to: {channel}\n\nDaily backups will be sent here automatically.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"Log channel set to {channel}")

    elif awaiting == 'add_special':
        if not is_owner(int(user_id)):
            return
        try:
            special_user_id = int(update.message.text.strip())
            bot_data.add_special_user(special_user_id)
            await update.message.reply_text(
                f'✅ User {special_user_id} added as special user.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]])
            )
            logger.info(f"Owner added special user {special_user_id}")
        except ValueError:
            await update.message.reply_text('❌ Invalid user ID.')
        context.user_data.pop('awaiting', None)

    elif awaiting == 'ban_user':
        if not is_owner(int(user_id)):
            return
        try:
            ban_user_id = int(update.message.text.strip())
            bot_data.ban_user(ban_user_id)
            await update.message.reply_text(
                f'✅ User {ban_user_id} has been banned.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]])
            )
            logger.info(f"Owner banned user {ban_user_id}")
        except ValueError:
            await update.message.reply_text('❌ Invalid user ID.')
        context.user_data.pop('awaiting', None)

    elif awaiting == 'unban_user':
        if not is_owner(int(user_id)):
            return
        try:
            unban_user_id = int(update.message.text.strip())
            bot_data.unban_user(unban_user_id)
            await update.message.reply_text(
                f'✅ User {unban_user_id} has been unbanned.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]])
            )
            logger.info(f"Owner unbanned user {unban_user_id}")
        except ValueError:
            await update.message.reply_text('❌ Invalid user ID.')
        context.user_data.pop('awaiting', None)

    elif awaiting == 'update_message':
        if not is_owner(int(user_id)):
            return
        message = update.message.text
        sent = 0
        for uid in bot_data.get_users().keys():
            try:
                await context.bot.send_message(chat_id=int(uid), text=f"📣 Bot Update\n\n{message}")
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send to {uid}: {e}")
        await update.message.reply_text(
            f'✅ Update message sent to {sent} users.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"Owner sent update message to {sent} users")

    elif awaiting == 'feature_key':
        if not is_owner(int(user_id)):
            return
        key = update.message.text.strip().replace(' ', '_')
        if not key:
            await update.message.reply_text('❌ Invalid feature key.')
            return
        pending = context.user_data.setdefault('feature_pending', {})
        pending['key'] = key
        context.user_data['awaiting'] = 'feature_title'
        await update.message.reply_text(f"✅ Feature key: {key}\n\nNow send the feature title (shown to users):")

    elif awaiting == 'feature_title':
        if not is_owner(int(user_id)):
            return
        pending = context.user_data.get('feature_pending') or {}
        if 'key' not in pending:
            await update.message.reply_text('❌ Please start over from the admin panel.')
            context.user_data.pop('awaiting', None)
            return
        pending['title'] = update.message.text.strip()
        context.user_data['awaiting'] = 'feature_desc'
        await update.message.reply_text("✅ Title saved.\n\nNow send a short description (or send '-' for none):")

    elif awaiting == 'feature_desc':
        if not is_owner(int(user_id)):
            return
        pending = context.user_data.get('feature_pending') or {}
        if 'key' not in pending:
            await update.message.reply_text('❌ Please start over from the admin panel.')
            context.user_data.pop('awaiting', None)
            return
        desc = update.message.text.strip()
        pending['description'] = '' if desc == '-' else desc
        context.user_data['awaiting'] = 'feature_stars'
        await update.message.reply_text("✅ Description saved.\n\nNow send the price in Telegram Stars (integer, e.g. 100). Send 0 to disable Stars payment:")

    elif awaiting == 'feature_stars':
        if not is_owner(int(user_id)):
            return
        pending = context.user_data.get('feature_pending') or {}
        if 'key' not in pending:
            await update.message.reply_text('❌ Please start over from the admin panel.')
            context.user_data.pop('awaiting', None)
            return
        try:
            stars = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text('❌ Invalid number. Send an integer (e.g. 100).')
            return
        pending['stars'] = stars
        context.user_data['awaiting'] = 'feature_ton'
        await update.message.reply_text("✅ Stars price saved.\n\nNow send the price in TON (e.g. 0.5). Send 0 to disable TON payment:")

    elif awaiting == 'feature_ton':
        if not is_owner(int(user_id)):
            return
        pending = context.user_data.get('feature_pending') or {}
        if 'key' not in pending:
            await update.message.reply_text('❌ Please start over from the admin panel.')
            context.user_data.pop('awaiting', None)
            return
        try:
            ton = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text('❌ Invalid number. Send e.g. 0.5.')
            return
        key = pending['key']
        bot_data.upsert_feature(key, pending.get('title', key), pending.get('description', ''), pending.get('stars', 0), ton)
        context.user_data.pop('feature_pending', None)
        await update.message.reply_text(
            f"✅ Feature saved:\nKey: {key}\nTitle: {pending.get('title', key)}\nStars: {pending.get('stars', 0)}⭐\nTON: {ton}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Paid Features", callback_data='paid_features')]])
        )
        context.user_data.pop('awaiting', None)
        logger.info(f"Owner saved paid feature {key}")

    elif awaiting == 'import_data':
        if not is_owner(int(user_id)):
            return

        if update.message.document:
            file = await context.bot.get_file(update.message.document.file_id)
            file_data = await file.download_as_bytearray()
            data_str = file_data.decode('utf-8')

            if bot_data.import_data(data_str):
                await update.message.reply_text(
                    '✅ Data imported successfully!',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]])
                )
                logger.info("Owner imported data")
            else:
                await update.message.reply_text(
                    '❌ Failed to import data. Check format.',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]])
                )
        else:
            await update.message.reply_text('❌ Please send a JSON file.')

        context.user_data.pop('awaiting', None)

# ---------------------------------------------------------------- payments

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    try:
        await query.answer(ok=True)
    except Exception as e:
        logger.error(f"Error answering pre-checkout: {e}")

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    payment = update.message.successful_payment
    payload = payment.invoice_payload or ''
    txn_id = payment.telegram_payment_charge_id

    if payload.startswith('stars:'):
        key = payload[6:]
        if _finalize_payment(int(user_id), key, 'stars', txn_id):
            feature = bot_data.get_feature(key)
            title = feature['title'] if feature else key
            await update.message.reply_text(
                f"✅ Payment received! Feature unlocked: {title}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Back to Store", callback_data='feature_store')]])
            )
        else:
            await update.message.reply_text(
                "❌ Invalid feature or already unlocked.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Back to Store", callback_data='feature_store')]])
            )
    else:
        await update.message.reply_text("✅ Payment received!")

async def _query_crypto_invoice(invoice_id):
    token = os.getenv('CRYPTO_BOT_TOKEN')
    if not token:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://pay.crypt.bot/api/getInvoices',
                headers={'Crypto-Pay-API-Token': token},
                data={'invoice_ids': str(invoice_id)}
            ) as response:
                data = await response.json()
                if data.get('ok') and data.get('result', {}).get('items'):
                    return data['result']['items'][0]
    except Exception as e:
        logger.error(f"CryptoBot getInvoices error: {e}")
    return None

_APPLICATION = None

async def _webhook_handler(request):
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400)
    asyncio.create_task(_handle_crypto_webhook(data))
    return web.Response(status=200)

async def _handle_crypto_webhook(data):
    try:
        if data.get('update_type') != 'invoice_paid':
            return
        payload = data.get('payload') or {}
        our_payload = payload.get('payload') or ''
        if not our_payload.startswith('ton:'):
            return
        parts = our_payload.split(':')
        if len(parts) < 3:
            return
        user_id = int(parts[1])
        feature_key = ':'.join(parts[2:])
        if payload.get('status') != 'paid':
            return
        invoice_id = payload.get('id') or payload.get('invoice_id')
        txn_id = payload.get('hash') or str(invoice_id)
        if _finalize_payment(user_id, feature_key, 'crypto_bot', txn_id, invoice_id):
            feature = bot_data.get_feature(feature_key)
            title = feature['title'] if feature else feature_key
            if _APPLICATION:
                await _APPLICATION.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Payment received! Feature unlocked: {title}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Back to Store", callback_data='feature_store')]])
                )
    except Exception as e:
        logger.error(f"CryptoBot webhook processing error: {e}")

async def start_webhook_server(application):
    global _APPLICATION
    _APPLICATION = application
    port = int(os.getenv('WEBHOOK_PORT', '8080'))
    app = web.Application()
    app.router.add_post('/cb_webhook', _webhook_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=port)
    await site.start()
    logger.info(f"CryptoBot webhook server started on port {port} (POST /cb_webhook)")

# ---------------------------------------------------------------- download & checks

async def download_asset(context, user_id: str, platform: str, repo: str, tag: str, idx: int):
    asset_key = f'{user_id}_{repo}_{tag}'
    pending = bot_data.pending_assets.get(asset_key)
    if not pending:
        await context.bot.send_message(chat_id=int(user_id), text="❌ Download session expired. Please check for updates again.")
        return
    assets = pending['assets']
    if idx >= len(assets):
        await context.bot.send_message(chat_id=int(user_id), text="❌ Invalid file selection.")
        return

    if platform == 'github':
        token = bot_data.get_github_token(user_id)
        if not token:
            await context.bot.send_message(chat_id=int(user_id), text="❌ GitHub token not set.")
            return

        asset = assets[idx]
        asset_id = asset['id']
        filename = asset.get('name', 'download')
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
        asset = assets[idx]
        direct_url = asset.get('direct_asset_url') or asset.get('url')
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"📥 Download link:\n{direct_url}"
        )

async def _fetch_github_releases(session, token, repo, per_page=30, max_pages=10):
    url = f'https://api.github.com/repos/{repo}/releases'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    releases = []
    page = 1
    while page <= max_pages:
        params = {'per_page': per_page, 'page': page}
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                return None, response.status
            batch = await response.json()
            releases.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
    return releases, 200

async def _fetch_gitlab_releases(session, token, base_url, repo, per_page=100, max_pages=5):
    project_id = repo.replace('/', '%2F')
    url = f'{base_url}/api/v4/projects/{project_id}/releases'
    headers = {'PRIVATE-TOKEN': token}
    releases = []
    page = 1
    while page <= max_pages:
        params = {'per_page': per_page, 'page': page}
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                return None, response.status
            batch = await response.json()
            releases.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
    return releases, 200

async def _send_release_notification(context, user_id: str, repo: str, repo_type: str, release: dict, base_url: str = None):
    tag = release.get('tag_name')
    name = release.get('name') or tag
    body = ''

    if repo_type == 'github':
        url = release.get('html_url')
        published = release.get('published_at')
        body = release.get('body', '') or ''
        assets = release.get('assets', []) or []
        message = f"🎉 New GitHub Release for {repo}!\n\n"
        message += f"📦 {name}\n"
        message += f"🏷 Tag: {tag}\n"
        message += f"📅 Published: {published}\n\n"
    else:
        base = base_url or GITLAB_COM
        url = release.get('_links', {}).get('self') or f"{base}/{repo}/-/releases/{tag}"
        created = release.get('created_at')
        body = release.get('description', '') or ''
        assets = release.get('assets', {}).get('links', []) or []
        message = f"🎉 New GitLab Release for {repo}!\n\n"
        message += f"📦 {name}\n"
        message += f"🏷 Tag: {tag}\n"
        message += f"📅 Created: {created}\n\n"

    if body:
        body_preview = body[:500] + "..." if len(body) > 500 else body
        message += f"📝 Release Notes:\n{body_preview}\n\n"

    message += f"🔗 {url}\n"

    if assets:
        message += f"\n📥 {len(assets)} file(s) available"
        bot_data.pending_assets[f'{user_id}_{repo}_{tag}'] = {
            'assets': assets,
            'platform': repo_type,
            'repo': repo,
            'tag': tag
        }
        keyboard = create_asset_buttons(user_id, repo_type, repo, assets, 0, tag)
        await context.bot.send_message(chat_id=int(user_id), text=message, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await context.bot.send_message(chat_id=int(user_id), text=message)

    logger.info(f"Sent {repo_type} release notification to {user_id} for {repo} ({tag})")

async def _process_releases(context, user_id: str, repo: str, repo_type: str, releases: list, force: bool, base_url: str = None):
    if not releases:
        return

    if repo_type == 'github':
        releases = [r for r in releases if not r.get('prerelease') and not r.get('draft')]

    if not releases:
        return

    last_tag = bot_data.get_last_release(user_id, repo)
    newest_tag = releases[0].get('tag_name')

    if force:
        bot_data.set_last_release(user_id, repo, newest_tag)
        return

    if last_tag is None:
        bot_data.set_last_release(user_id, repo, newest_tag)
        logger.info(f"Established baseline for {repo}: {newest_tag}")
        return

    baseline_index = None
    for i, release in enumerate(releases):
        if release.get('tag_name') == last_tag:
            baseline_index = i
            break

    if baseline_index is None:
        bot_data.set_last_release(user_id, repo, newest_tag)
        logger.info(f"Baseline tag {last_tag} not found for {repo}; reset to {newest_tag}")
        return

    new_releases = list(reversed(releases[:baseline_index]))

    if new_releases:
        for release in new_releases:
            await _send_release_notification(context, user_id, repo, repo_type, release, base_url)
        bot_data.set_last_release(user_id, repo, newest_tag)
        logger.info(f"Notified {user_id} about {len(new_releases)} new release(s) for {repo}")

async def check_repo_updates(context: ContextTypes.DEFAULT_TYPE, user_id: str, repo: str, force: bool = False):
    repo_type = bot_data.get_repo_type(user_id, repo)

    if repo_type == 'github':
        token = bot_data.get_github_token(user_id)
        if not token:
            return
        try:
            async with aiohttp.ClientSession() as session:
                releases, status = await _fetch_github_releases(session, token, repo)
                if status != 200:
                    if status == 404:
                        logger.info(f"No releases found for GitHub repo {repo}")
                    else:
                        logger.warning(f"GitHub API returned status {status} for {repo}")
                    return
                await _process_releases(context, user_id, repo, 'github', releases, force)
        except Exception as e:
            logger.error(f"Error checking GitHub repo {repo} for user {user_id}: {e}")

    elif repo_type == 'gitlab':
        token = bot_data.get_gitlab_token(user_id)
        if not token:
            return
        base_url = bot_data.get_gitlab_base_url(user_id, repo) or GITLAB_COM
        try:
            async with aiohttp.ClientSession() as session:
                releases, status = await _fetch_gitlab_releases(session, token, base_url, repo)
                if status != 200:
                    if status == 404:
                        logger.info(f"No releases found for GitLab repo {repo}")
                    else:
                        logger.warning(f"GitLab API returned status {status} for {repo}")
                    return
                await _process_releases(context, user_id, repo, 'gitlab', releases, force, base_url)
        except Exception as e:
            logger.error(f"Error checking GitLab repo {repo} for user {user_id}: {e}")

def create_asset_buttons(user_id, platform, repo, assets, page, tag=None):
    keyboard = []
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_assets = assets[start_idx:end_idx]

    for i, asset in enumerate(page_assets, start=start_idx):
        if platform == 'github':
            asset_name = asset['name']
            asset_size = asset['size'] / 1024 / 1024
            button_text = f"📥 {asset_name} ({asset_size:.1f}MB)"
        else:
            asset_name = asset.get('name', 'Download')
            button_text = f"📥 {asset_name}"
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"download_asset|{user_id}|{platform}|{repo}|{tag or ''}|{i}"
        )])

    nav_buttons = []
    total_pages = (len(assets) + items_per_page - 1) // items_per_page
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"asset_page|{user_id}|{repo}|{tag or ''}|{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"asset_page|{user_id}|{repo}|{tag or ''}|{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    if total_pages > 1:
        keyboard.append([InlineKeyboardButton(f"📄 Page {page + 1}/{total_pages}", callback_data="page_info")])

    return keyboard

async def check_all_repos(context: ContextTypes.DEFAULT_TYPE):
    while True:
        try:
            for user_id, repo in bot_data.get_all_repos():
                key = f"{user_id}_{repo}"
                interval = bot_data.get_interval(user_id, repo)
                last_check = bot_data.get_last_check(user_id, repo)

                now = datetime.now()
                if last_check is None or (now - last_check) >= timedelta(hours=interval):
                    await check_repo_updates(context, user_id, repo)
                    bot_data.set_last_check(user_id, repo, now)
                    logger.debug(f"Checked {key}")

                await asyncio.sleep(2)

            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Error in check loop: {e}")
            await asyncio.sleep(300)

async def send_logs_to_channel(context: ContextTypes.DEFAULT_TYPE):
    log_channel = bot_data.get_log_channel()
    if not log_channel:
        return

    try:
        data_json = bot_data.export_data()
        data_file = BytesIO(data_json.encode('utf-8'))
        data_filename = f"bot_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        await context.bot.send_document(
            chat_id=log_channel,
            document=data_file,
            filename=data_filename,
            caption=f"📊 Daily Data Backup\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        if os.path.exists('bot.log'):
            await context.bot.send_document(
                chat_id=log_channel,
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
    await asyncio.sleep(10)
    asyncio.create_task(check_all_repos(application))
    if bot_data.get_log_channel():
        asyncio.create_task(daily_log_upload(application))

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
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    asyncio.get_event_loop().create_task(start_background_checks(application))
    if os.getenv('CRYPTO_BOT_TOKEN'):
        asyncio.get_event_loop().create_task(start_webhook_server(application))

    logger.info("Bot started successfully!")
    print("Bot started successfully!")

    required_channel = bot_data.get_required_channel()
    log_channel = bot_data.get_log_channel()
    if required_channel:
        logger.info(f"Required channel: {required_channel}")
    if log_channel:
        logger.info(f"Log channel: {log_channel}")

    application.run_polling()

if __name__ == '__main__':
    main()
