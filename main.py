import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import logging
import threading
import re
import sys
import atexit
import signal
import requests
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# FLASK KEEP ALIVE
# ============================================================
from flask import Flask
app = Flask('')

@app.route('/')
def home():
    return "HINDUSTAN HOSTING BOT"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive started.")

# ============================================================
# CONFIG
# ============================================================
TOKEN = os.getenv('TOKEN', '8890034549:AAHQm5lAPLd_dOcsqyYbdTAya0GQxo-3IoM')
OWNER_ID = int(os.getenv('OWNER_ID', 7658271153))
ADMIN_ID = int(os.getenv('ADMIN_ID', 7658271153))
YOUR_USERNAME = os.getenv('YOUR_USERNAME', '@Rolexseller1')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'HINDUSTANHACK')

FORWARD_BOT_TOKEN = "8890034549:AAGl6Cc2j4nIG5TDOwoD9ujX3jLtxsfuKS4"
FORWARD_BOT = telebot.TeleBot(FORWARD_BOT_TOKEN)

PRIVATE_CHANNEL_ID = -1003977505145

DEFAULT_MANDATORY_CHANNELS = [
    {"identifier": "@hindustanhack", "name": "Hindustan Hack"},
    {"identifier": "@Rolexseller1", "name": "Rolex Seller"},
]

FREE_USER_LIMIT = 1
TRIAL_DAYS = 15

PLAN_LIMITS = {
    'free':     {'files': 1,   'ram_mb': 312,  'label': '🆓 Free'},
    'baby':     {'files': 5,   'ram_mb': 512,  'label': '🍼 Baby'},
    'basic':    {'files': 10,  'ram_mb': 1024, 'label': '⭐ Basic'},
    'premium':  {'files': 25,  'ram_mb': 2048, 'label': '💎 Premium'},
    'god':      {'files': 150, 'ram_mb': 4096, 'label': '👑 God'},
    'ultimate': {'files': 999, 'ram_mb': 8192, 'label': '⚡ Ultimate'},
    'lifetime': {'files': float('inf'), 'ram_mb': float('inf'), 'label': '♾️ Lifetime'},
    'admin':    {'files': float('inf'), 'ram_mb': float('inf'), 'label': '🛡️ Admin'},
    'owner':    {'files': float('inf'), 'ram_mb': float('inf'), 'label': '👑 Owner'},
}

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# ============================================================
# DATA
# ============================================================
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()
user_limits = {}
user_plans = {}
user_trials = {}
custom_ram_mb = {}
approved_files = {}
bot_locked = False
maintenance_mode = False
mandatory_channels = {}
pending_zip_files = {}

DB_LOCK = threading.Lock()

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# DATABASE
# ============================================================
def init_db():
    logger.info(f"Init DB: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mandatory_channels
                     (channel_id TEXT PRIMARY KEY, channel_username TEXT,
                      channel_name TEXT, added_by INTEGER, added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_plans
                     (user_id INTEGER PRIMARY KEY, plan TEXT, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_trials
                     (user_id INTEGER PRIMARY KEY, trial_start TEXT, trial_end TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS custom_ram
                     (user_id INTEGER PRIMARY KEY, ram_mb INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS approved_files
                     (user_id INTEGER, file_name TEXT, approved_at TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS running_processes
                     (user_id INTEGER, file_name TEXT, pid INTEGER,
                      file_type TEXT, started_at TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)',
                  (OWNER_ID, OWNER_ID, datetime.now().isoformat()))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)',
                      (ADMIN_ID, OWNER_ID, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info("DB initialized.")
    except Exception as e:
        logger.error(f"DB init err: {e}", exc_info=True)

def load_data():
    logger.info("Loading data...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        for uid, exp in c.execute('SELECT user_id, expiry FROM subscriptions').fetchall():
            try: user_subscriptions[uid] = {'expiry': datetime.fromisoformat(exp)}
            except: pass
        for uid, fn, ft in c.execute('SELECT user_id, file_name, file_type FROM user_files').fetchall():
            user_files.setdefault(uid, []).append((fn, ft))
        active_users.update(u for (u,) in c.execute('SELECT user_id FROM active_users').fetchall())
        admin_ids.update(u for (u,) in c.execute('SELECT user_id FROM admins').fetchall())
        banned_users.update(u for (u,) in c.execute('SELECT user_id FROM banned_users').fetchall())
        for uid, fl in c.execute('SELECT user_id, file_limit FROM user_limits').fetchall():
            user_limits[uid] = fl
        for cid, un, nm in c.execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels').fetchall():
            mandatory_channels[cid] = {'username': un, 'name': nm}
        for uid, pl in c.execute('SELECT user_id, plan FROM user_plans').fetchall():
            user_plans[uid] = pl
        for uid, ts, te in c.execute('SELECT user_id, trial_start, trial_end FROM user_trials').fetchall():
            try: user_trials[uid] = {'start': datetime.fromisoformat(ts), 'end': datetime.fromisoformat(te)}
            except: pass
        for uid, rm in c.execute('SELECT user_id, ram_mb FROM custom_ram').fetchall():
            custom_ram_mb[uid] = rm
        for uid, fn in c.execute('SELECT user_id, file_name FROM approved_files').fetchall():
            approved_files.setdefault(uid, set()).add(fn)
        conn.close()
        logger.info(f"Loaded: {len(active_users)} users, {len(user_files)} users w/ files, {len(approved_files)} w/ approved")
    except Exception as e:
        logger.error(f"Load err: {e}", exc_info=True)

init_db()
load_data()

# ============================================================
# DISK SCAN — ORPHAN FILES RECOVERY
# ============================================================
def scan_disk_for_user_files(uid):
    """Disk pe jo bhi .py/.js files hain user folder mein."""
    folder = get_user_folder(uid)
    found = []
    try:
        if not os.path.exists(folder):
            return []
        for f in os.listdir(folder):
            fp = os.path.join(folder, f)
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext == '.py':
                found.append((f, 'py'))
            elif ext == '.js':
                found.append((f, 'js'))
    except Exception as e:
        logger.error(f"scan_disk {uid}: {e}")
    return found

def sync_user_files_from_disk(uid):
    """Disk aur DB ko sync karo — orphans recover, stale remove."""
    disk_files = dict(scan_disk_for_user_files(uid))
    db_files = {fn: ft for fn, ft in user_files.get(uid, [])}
    added = 0
    for fn, ft in disk_files.items():
        if fn not in db_files:
            save_user_file(uid, fn, ft)
            approve_file(uid, fn)
            added += 1
            logger.info(f"♻️ Orphan file recovered: {uid}/{fn}")
    removed = 0
    for fn in db_files.keys():
        if fn not in disk_files:
            remove_user_file_db(uid, fn)
            removed += 1
            logger.info(f"🧹 Stale DB entry removed: {uid}/{fn}")
    return added, removed

def sync_all_users_from_disk():
    logger.info("Syncing all user files from disk...")
    total_added = 0
    total_removed = 0
    try:
        if not os.path.exists(UPLOAD_BOTS_DIR):
            return
        for user_dir in os.listdir(UPLOAD_BOTS_DIR):
            try:
                uid = int(user_dir)
            except ValueError:
                continue
            a, r = sync_user_files_from_disk(uid)
            total_added += a
            total_removed += r
    except Exception as e:
        logger.error(f"sync_all err: {e}", exc_info=True)
    logger.info(f"Sync done: +{total_added} added, -{total_removed} removed")

# ============================================================
# PLAN / RAM / TRIAL HELPERS
# ============================================================
def get_user_plan(uid):
    if uid == OWNER_ID: return 'owner'
    if uid in admin_ids: return 'admin'
    if uid in user_plans: return user_plans[uid]
    if uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now():
        return 'basic'
    return 'free'

def get_plan_ram_limit(uid):
    if uid in custom_ram_mb: return custom_ram_mb[uid]
    return PLAN_LIMITS.get(get_user_plan(uid), PLAN_LIMITS['free'])['ram_mb']

def get_plan_file_limit(uid):
    """Admin/Owner/Lifetime = unlimited."""
    if uid == OWNER_ID or uid in admin_ids:
        return float('inf')
    if uid in user_limits: return user_limits[uid]
    plan = get_user_plan(uid)
    if plan in ('admin', 'owner', 'lifetime'):
        return float('inf')
    return PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])['files']

def has_active_trial(uid):
    if uid not in user_trials: return False
    te = user_trials[uid].get('end')
    return te and te > datetime.now()

def has_active_subscription(uid):
    return uid in user_subscriptions and user_subscriptions[uid].get('expiry', datetime.min) > datetime.now()

def is_file_approved(uid, fn):
    if uid == OWNER_ID or uid in admin_ids:
        return True
    return fn in approved_files.get(uid, set())

def approve_file(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO approved_files (user_id, file_name, approved_at) VALUES (?, ?, ?)',
                      (uid, fn, datetime.now().isoformat()))
            conn.commit()
            approved_files.setdefault(uid, set()).add(fn)
            return True
        except Exception as e:
            logger.error(f"approve_file err: {e}")
            return False
        finally: conn.close()

def unapprove_file(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM approved_files WHERE user_id = ? AND file_name = ?', (uid, fn))
            conn.commit()
            if uid in approved_files: approved_files[uid].discard(fn)
            return True
        except: return False
        finally: conn.close()

def start_trial(uid):
    now = datetime.now()
    end = now + timedelta(days=TRIAL_DAYS)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_trials (user_id, trial_start, trial_end) VALUES (?, ?, ?)',
                      (uid, now.isoformat(), end.isoformat()))
            conn.commit()
            user_trials[uid] = {'start': now, 'end': end}
            logger.info(f"Trial started: {uid} until {end}")
        except: pass
        finally: conn.close()

def can_run_bots(uid, fn=None):
    if uid == OWNER_ID or uid in admin_ids: return True, ""
    if has_active_subscription(uid): return True, ""
    if fn and is_file_approved(uid, fn): return True, ""
    if uid not in user_trials:
        start_trial(uid)
        return True, ""
    if has_active_trial(uid): return True, ""
    return False, "trial_expired"

def save_user_plan(uid, plan, set_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_plans (user_id, plan, set_by, set_date) VALUES (?, ?, ?, ?)',
                      (uid, plan, set_by, datetime.now().isoformat()))
            conn.commit()
            user_plans[uid] = plan
            return True
        except: return False
        finally: conn.close()

def save_custom_ram(uid, ram_mb, set_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO custom_ram (user_id, ram_mb, set_by, set_date) VALUES (?, ?, ?, ?)',
                      (uid, ram_mb, set_by, datetime.now().isoformat()))
            conn.commit()
            custom_ram_mb[uid] = ram_mb
            return True
        except: return False
        finally: conn.close()

def remove_custom_ram(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM custom_ram WHERE user_id = ?', (uid,))
            conn.commit()
            custom_ram_mb.pop(uid, None)
            return True
        except: return False
        finally: conn.close()

# ============================================================
# RUNNING PROCESS PERSISTENCE
# ============================================================
def save_running_process(uid, fn, pid, ft):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO running_processes (user_id, file_name, pid, file_type, started_at) VALUES (?, ?, ?, ?, ?)',
                      (uid, fn, pid, ft, datetime.now().isoformat()))
            conn.commit()
        except Exception as e:
            logger.error(f"save_running err: {e}")
        finally: conn.close()

def remove_running_process(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM running_processes WHERE user_id = ? AND file_name = ?', (uid, fn))
            conn.commit()
        except: pass
        finally: conn.close()

def rehydrate_running_processes():
    logger.info("Rehydrating running processes...")
    count = 0
    stale = []
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        rows = c.execute('SELECT user_id, file_name, pid, file_type FROM running_processes').fetchall()
        conn.close()
        for uid, fn, pid, ft in rows:
            try:
                if not psutil.pid_exists(pid):
                    stale.append((uid, fn)); continue
                p = psutil.Process(pid)
                if p.status() == psutil.STATUS_ZOMBIE:
                    stale.append((uid, fn)); continue
                key = f"{uid}_{fn}"
                folder = get_user_folder(uid)
                lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
                lf = None
                try: lf = open(lp, 'a', encoding='utf-8', errors='ignore')
                except: pass
                bot_scripts[key] = {
                    'process': p, 'pid': pid, 'log_file': lf, 'file_name': fn,
                    'chat_id': uid, 'script_owner_id': uid,
                    'start_time': datetime.now(), 'user_folder': folder,
                    'type': ft, 'script_key': key, 'rehydrated': True
                }
                count += 1
                logger.info(f"♻️ Rehydrated: {key} PID={pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                stale.append((uid, fn))
    except Exception as e:
        logger.error(f"Rehydrate err: {e}")
    for uid, fn in stale:
        remove_running_process(uid, fn)
    logger.info(f"Rehydrated {count} processes, cleaned {len(stale)} stale.")

def get_process_ram_mb(pid):
    try:
        p = psutil.Process(pid)
        total = p.memory_info().rss / (1024 * 1024)
        for ch in p.children(recursive=True):
            try: total += ch.memory_info().rss / (1024 * 1024)
            except: pass
        return total
    except: return 0

# ============================================================
# RAM MONITOR
# ============================================================
def ram_monitor_loop():
    logger.info("RAM Monitor started")
    while True:
        try:
            time.sleep(30)
            for key, info in list(bot_scripts.items()):
                try:
                    proc = info.get('process')
                    pid = info.get('pid') or (proc.pid if proc and hasattr(proc, 'pid') else None)
                    if not pid or not psutil.pid_exists(pid): continue
                    oid = info.get('script_owner_id')
                    if not oid: continue
                    limit = get_plan_ram_limit(oid)
                    if limit == float('inf'): continue
                    cur = get_process_ram_mb(pid)
                    if cur > limit:
                        logger.warning(f"{key} RAM {cur:.0f}>{limit}. Killing.")
                        try:
                            bot.send_message(oid,
                                f"⚠️ **RAM Limit Exceeded!**\n\n"
                                f"📁 `{info.get('file_name')}`\n"
                                f"🧠 Used: {cur:.0f} MB\n"
                                f"📊 Limit: {limit} MB\n\n"
                                f"🛑 Auto-stopped.",
                                parse_mode='Markdown')
                        except: pass
                        for aid in admin_ids:
                            try:
                                bot.send_message(aid,
                                    f"🚨 RAM Auto-Kill\n👤 `{oid}`\n📁 `{info.get('file_name')}`\n"
                                    f"🧠 {cur:.0f}MB / {limit}MB", parse_mode='Markdown')
                            except: pass
                        kill_process_tree(info)
                        bot_scripts.pop(key, None)
                        remove_running_process(oid, info.get('file_name'))
                except Exception as e:
                    logger.error(f"RAM iter err: {e}")
        except Exception as e:
            logger.error(f"RAM loop err: {e}", exc_info=True)

# ============================================================
# BAN / MAINTENANCE
# ============================================================
def is_user_banned(uid): return uid in banned_users
def is_maintenance_blocked(uid): return maintenance_mode and uid not in admin_ids

def banned_response(cid, msg=None):
    t = "🚫 **You are banned.**\nContact owner."
    try:
        if msg: bot.reply_to(msg, t, parse_mode='Markdown')
        else: bot.send_message(cid, t, parse_mode='Markdown')
    except: pass

def maintenance_response(cid, msg=None):
    t = "🛠️ **Bot under maintenance.**\nTry later."
    try:
        if msg: bot.reply_to(msg, t, parse_mode='Markdown')
        else: bot.send_message(cid, t, parse_mode='Markdown')
    except: pass

# ============================================================
# CHANNELS
# ============================================================
def is_user_member(uid, cid):
    try:
        cm = bot.get_chat_member(cid, uid)
        return cm.status in ['member', 'administrator', 'creator']
    except: return False

def check_mandatory_subscription(uid):
    if not mandatory_channels: return True, []
    nj = []
    for cid, cinfo in mandatory_channels.items():
        if not is_user_member(uid, cid):
            nj.append((cid, cinfo))
    return (len(nj) == 0), nj

def save_mandatory_channel(cid, un, nm, added_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_username, channel_name, added_by, added_date) VALUES (?, ?, ?, ?, ?)',
                      (cid, un, nm, added_by, datetime.now().isoformat()))
            conn.commit()
            mandatory_channels[cid] = {'username': un, 'name': nm}
            return True
        except: return False
        finally: conn.close()

def remove_mandatory_channel_db(cid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (cid,))
            conn.commit()
            mandatory_channels.pop(cid, None)
            return True
        except: return False
        finally: conn.close()

def setup_default_channels():
    logger.info("Setting up default mandatory channels...")
    for ch in DEFAULT_MANDATORY_CHANNELS:
        try:
            chat = bot.get_chat(ch["identifier"])
            cid = str(chat.id)
            un = f"@{chat.username}" if chat.username else ""
            nm = chat.title or ch["name"]
            try:
                bm = bot.get_chat_member(cid, bot.get_me().id)
                if bm.status not in ['administrator', 'creator']:
                    logger.warning(f"Bot not admin in {nm}")
                    continue
            except Exception as e:
                logger.warning(f"Cannot access {ch['identifier']}: {e}")
                continue
            if save_mandatory_channel(cid, un, nm, OWNER_ID):
                logger.info(f"✅ Added: {nm} ({cid})")
        except Exception as e:
            logger.error(f"Failed {ch['identifier']}: {e}")

def create_mandatory_channels_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton('➕ Add', callback_data='add_mandatory_channel'),
          types.InlineKeyboardButton('➖ Remove', callback_data='remove_mandatory_channel'))
    m.row(types.InlineKeyboardButton('📋 List', callback_data='list_mandatory_channels'))
    m.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_subscription_check_message(nj):
    txt = "📢 **Join These Channels First:**\n\n"
    mk = types.InlineKeyboardMarkup()
    for cid, cinfo in nj:
        un = cinfo.get('username', '')
        nm = cinfo.get('name', 'Channel')
        link = f"https://t.me/{un.replace('@', '')}" if un else f"https://t.me/c/{cid.replace('-100', '')}"
        txt += f"• {nm}\n"
        mk.add(types.InlineKeyboardButton(f"Join {nm}", url=link))
    mk.add(types.InlineKeyboardButton("✅ Verify", callback_data='check_subscription_status'))
    return txt, mk

# ============================================================
# DB USER MGMT
# ============================================================
def ban_user_db(uid, reason, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, ban_date) VALUES (?, ?, ?, ?)',
                      (uid, reason, by, datetime.now().isoformat()))
            conn.commit()
            banned_users.add(uid)
            return True
        except: return False
        finally: conn.close()

def unban_user_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (uid,))
            conn.commit()
            banned_users.discard(uid)
            return True
        except: return False
        finally: conn.close()

def set_user_limit_db(uid, limit, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_limits (user_id, file_limit, set_by, set_date) VALUES (?, ?, ?, ?)',
                      (uid, limit, by, datetime.now().isoformat()))
            conn.commit()
            user_limits[uid] = limit
            return True
        except: return False
        finally: conn.close()

def remove_user_limit_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_limits WHERE user_id = ?', (uid,))
            conn.commit()
            user_limits.pop(uid, None)
            return True
        except: return False
        finally: conn.close()

def save_user_file(uid, fn, ft='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (uid, fn, ft))
            conn.commit()
            user_files.setdefault(uid, [])
            user_files[uid] = [(f, t) for f, t in user_files[uid] if f != fn]
            user_files[uid].append((fn, ft))
        except: pass
        finally: conn.close()

def remove_user_file_db(uid, fn):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (uid, fn))
            conn.commit()
            if uid in user_files:
                user_files[uid] = [f for f in user_files[uid] if f[0] != fn]
                if not user_files[uid]: del user_files[uid]
        except: pass
        finally: conn.close()
    unapprove_file(uid, fn)

def add_active_user(uid):
    active_users.add(uid)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            now = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO active_users (user_id, join_date, last_seen) VALUES (?, ?, ?)',
                      (uid, now, now))
            conn.commit()
        except: pass
        finally: conn.close()

def save_subscription(uid, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                      (uid, expiry.isoformat()))
            conn.commit()
            user_subscriptions[uid] = {'expiry': expiry}
        except: pass
        finally: conn.close()

def remove_subscription_db(uid):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (uid,))
            conn.commit()
            user_subscriptions.pop(uid, None)
        except: pass
        finally: conn.close()

def add_admin_db(aid, by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)',
                      (aid, by, datetime.now().isoformat()))
            conn.commit()
            admin_ids.add(aid)
        except: pass
        finally: conn.close()

def remove_admin_db(aid):
    if aid == OWNER_ID: return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (aid,))
            conn.commit()
            admin_ids.discard(aid)
            return True
        except: return False
        finally: conn.close()

# ============================================================
# HELPERS
# ============================================================
def get_user_folder(uid):
    f = os.path.join(UPLOAD_BOTS_DIR, str(uid))
    os.makedirs(f, exist_ok=True)
    return f

def get_user_file_limit(uid): return get_plan_file_limit(uid)

def get_user_file_count(uid):
    """Disk se count — hamesha accurate."""
    folder = get_user_folder(uid)
    try:
        if not os.path.exists(folder): return 0
        count = 0
        for f in os.listdir(folder):
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.py', '.js'):
                count += 1
        return count
    except: return 0

def is_bot_running(oid, fn):
    key = f"{oid}_{fn}"
    info = bot_scripts.get(key)
    if info:
        try:
            pid = info.get('pid') or (info['process'].pid if info.get('process') else None)
            if pid and psutil.pid_exists(pid):
                p = psutil.Process(pid)
                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                    return True
            if 'log_file' in info and info['log_file'] and not info['log_file'].closed:
                try: info['log_file'].close()
                except: pass
            bot_scripts.pop(key, None)
            remove_running_process(oid, fn)
            return False
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            if 'log_file' in info and info['log_file'] and not info['log_file'].closed:
                try: info['log_file'].close()
                except: pass
            bot_scripts.pop(key, None)
            remove_running_process(oid, fn)
            return False
        except: return False
    return False

def kill_process_tree(info):
    try:
        if 'log_file' in info and info['log_file'] and hasattr(info['log_file'], 'close') and not info['log_file'].closed:
            try: info['log_file'].close()
            except: pass
        proc = info.get('process')
        pid = info.get('pid') or (proc.pid if proc and hasattr(proc, 'pid') else None)
        if pid:
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for ch in children:
                    try: ch.terminate()
                    except:
                        try: ch.kill()
                        except: pass
                gone, alive = psutil.wait_procs(children, timeout=1)
                for p in alive:
                    try: p.kill()
                    except: pass
                try:
                    parent.terminate()
                    try: parent.wait(timeout=1)
                    except psutil.TimeoutExpired: parent.kill()
                except:
                    try: parent.kill()
                    except: pass
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    except Exception as e:
        logger.error(f"Kill err: {e}")

# ============================================================
# FORCE KILL
# ============================================================
def force_kill_user(uid):
    killed = []
    files = list(user_files.get(uid, []))
    disk = scan_disk_for_user_files(uid)
    all_fns = set(f for f, _ in files) | set(f for f, _ in disk)
    for fn in all_fns:
        key = f"{uid}_{fn}"
        try:
            if is_bot_running(uid, fn):
                info = bot_scripts.get(key)
                if info:
                    kill_process_tree(info)
                    logger.info(f"🔪 Force killed: {uid}/{fn}")
                    killed.append(fn)
                bot_scripts.pop(key, None)
                remove_running_process(uid, fn)
            else:
                remove_running_process(uid, fn)
        except Exception as e:
            logger.error(f"force_kill {uid}/{fn}: {e}")
    for key in list(bot_scripts.keys()):
        try:
            oid = int(key.split('_', 1)[0])
            if oid == uid:
                info = bot_scripts[key]
                kill_process_tree(info)
                bot_scripts.pop(key, None)
                remove_running_process(uid, info.get('file_name', ''))
                if info.get('file_name') not in killed:
                    killed.append(info.get('file_name'))
        except: pass
    return killed

def force_kill_all():
    killed = 0
    for key in list(bot_scripts.keys()):
        try:
            info = bot_scripts[key]
            kill_process_tree(info)
            oid = info.get('script_owner_id')
            fn = info.get('file_name')
            if oid and fn: remove_running_process(oid, fn)
            bot_scripts.pop(key, None)
            killed += 1
        except: pass
    return killed

# ============================================================
# AUTO FORWARD
# ============================================================
def forward_uploaded_file(message, fn, ft, uid, size=0):
    user_info = f"👤 {message.from_user.first_name}"
    if message.from_user.username:
        user_info += f" (@{message.from_user.username})"
    cap = (
        f"📤 **NEW FILE UPLOAD**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{user_info}\n"
        f"🆔 User ID: `{uid}`\n"
        f"📁 File: `{fn}`\n"
        f"📦 Type: `{ft.upper()}`\n"
        f"📊 Size: `{size / 1024:.1f} KB`\n"
        f"🕐 Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    forward_ok = False
    try:
        FORWARD_BOT.forward_message(chat_id=PRIVATE_CHANNEL_ID,
                                    from_chat_id=message.chat.id,
                                    message_id=message.message_id)
        FORWARD_BOT.send_message(chat_id=PRIVATE_CHANNEL_ID, text=cap,
                                 parse_mode='Markdown', disable_web_page_preview=True)
        forward_ok = True
    except Exception as e:
        logger.error(f"❌ [FORWARD_BOT]: {e}")
    if not forward_ok:
        try:
            bot.forward_message(chat_id=PRIVATE_CHANNEL_ID,
                                from_chat_id=message.chat.id,
                                message_id=message.message_id)
            bot.send_message(chat_id=PRIVATE_CHANNEL_ID, text=cap,
                             parse_mode='Markdown', disable_web_page_preview=True)
            forward_ok = True
        except Exception as e:
            logger.error(f"❌ [MAIN_BOT] fallback: {e}")
    if not forward_ok:
        try:
            bot.send_message(OWNER_ID,
                f"⚠️ **Forward Failed!**\n\n👤 `{uid}`\n📁 `{fn}`",
                parse_mode='Markdown')
        except: pass
    return forward_ok

# ============================================================
# SECURITY
# ============================================================
def check_code_security(fp, ft):
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        patterns = [
            r'\bos\.system\b', r'\bsubprocess\b', r'\beval\b', r'\bexec\b',
            r'\b__import__\b', r'\bshutil\.rmtree\b', r'\bos\.remove\b',
            r'\bos\.unlink\b', r'rm\s+-rf', r'/etc/passwd', r'/etc/shadow'
        ]
        found = [p for p in patterns if re.search(p, content, re.IGNORECASE)]
        if found: return False, f"Dangerous: {', '.join(found[:3])}"
        return True, "Safe"
    except Exception as e:
        return False, f"Err: {e}"

def scan_zip_security(zp):
    try:
        patterns = [r'\bos\.system\b', r'\bsubprocess\b', r'\beval\b', r'\bexec\b', r'\bshutil\.rmtree\b']
        with zipfile.ZipFile(zp, 'r') as z:
            for fi in z.infolist():
                if fi.filename.endswith(('.py', '.js')):
                    with z.open(fi.filename) as f:
                        try: content = f.read().decode('utf-8', errors='ignore')
                        except: continue
                        for p in patterns:
                            if re.search(p, content, re.IGNORECASE):
                                return False, f"{fi.filename}: {p}"
        return True, "Safe"
    except Exception as e:
        return False, f"Scan err: {e}"

# ============================================================
# MENUS
# ============================================================
def create_main_menu_inline(uid):
    m = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'),
        types.InlineKeyboardButton('📤 Upload', callback_data='upload'),
        types.InlineKeyboardButton('📂 Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Speed', callback_data='speed'),
        types.InlineKeyboardButton('📦 Install', callback_data='manual_install'),
        types.InlineKeyboardButton('📞 Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]
    if uid in admin_ids:
        m.add(buttons[0])
        m.add(buttons[1], buttons[2])
        m.add(buttons[3], types.InlineKeyboardButton('💳 Subs', callback_data='subscription'))
        m.add(types.InlineKeyboardButton('📊 Stats', callback_data='stats'),
              types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'))
        m.add(types.InlineKeyboardButton('🔒 Lock' if not bot_locked else '🔓 Unlock',
              callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
              types.InlineKeyboardButton('🟢 Run All', callback_data='run_all_scripts'))
        m.add(types.InlineKeyboardButton('📢 Channels', callback_data='manage_mandatory_channels'),
              types.InlineKeyboardButton('🛠️ Install', callback_data='admin_install'))
        m.add(types.InlineKeyboardButton('👥 Users', callback_data='user_management'),
              types.InlineKeyboardButton('🧠 RAM', callback_data='ram_plans'))
        m.add(types.InlineKeyboardButton('🔪 Kill User', callback_data='kill_user_panel'),
              types.InlineKeyboardButton('🔄 Sync Files', callback_data='sync_files'))
        m.add(types.InlineKeyboardButton('🛠️ Maintenance', callback_data='maintenance'))
        m.add(types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'))
        m.add(buttons[5])
    else:
        m.add(buttons[0])
        m.add(buttons[1], buttons[2])
        m.add(buttons[3], buttons[4])
        m.add(types.InlineKeyboardButton('📊 Stats', callback_data='stats'))
        m.add(buttons[5])
    return m

def create_reply_keyboard(uid):
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if uid in admin_ids:
        rows = [
            ["📢 Updates Channel"],
            ["📤 Upload File", "📂 Check Files"],
            ["⚡ Bot Speed", "📊 Statistics"],
            ["💳 Subscriptions", "📢 Broadcast"],
            ["🔒 Lock Bot", "🟢 Running All Code"],
            ["👑 Admin Panel", "📞 Contact Owner"],
            ["📢 Channel Add", "🛠️ Manual Install"],
            ["👥 User Management", "🧠 RAM & Plans"],
            ["🔪 Kill User", "🔄 Sync Files"],
            ["🛠️ Maintenance", "⚙️ Settings"]
        ]
    else:
        rows = [
            ["📢 Updates Channel"],
            ["📤 Upload File", "📂 Check Files"],
            ["⚡ Bot Speed", "📊 Statistics"],
            ["📞 Contact Owner"],
            ["📦 Manual Install", "🆘 Help"]
        ]
    for r in rows:
        m.add(*[types.KeyboardButton(t) for t in r])
    return m

def create_control_buttons(oid, fn, running=True):
    m = types.InlineKeyboardMarkup(row_width=2)
    if running:
        m.row(types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{oid}_{fn}'),
              types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{oid}_{fn}'))
        m.row(types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{oid}_{fn}'),
              types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{oid}_{fn}'))
    else:
        m.row(types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{oid}_{fn}'),
              types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{oid}_{fn}'))
        m.row(types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{oid}_{fn}'))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data='check_files'))
    return m

def create_admin_panel():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton('➕ Add', callback_data='add_admin'),
          types.InlineKeyboardButton('➖ Remove', callback_data='remove_admin'))
    m.row(types.InlineKeyboardButton('📋 List', callback_data='list_admins'))
    m.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_user_management_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton('🚫 Ban', callback_data='ban_user'),
          types.InlineKeyboardButton('✅ Unban', callback_data='unban_user'))
    m.row(types.InlineKeyboardButton('📊 Info', callback_data='user_info'),
          types.InlineKeyboardButton('👥 All', callback_data='all_users'))
    m.row(types.InlineKeyboardButton('🔧 Set Limit', callback_data='set_user_limit'),
          types.InlineKeyboardButton('🗑️ Remove Limit', callback_data='remove_user_limit'))
    m.row(types.InlineKeyboardButton('🔪 Force Kill User', callback_data='kill_user_panel'))
    m.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_kill_user_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton('🔪 Kill By User ID', callback_data='kill_by_id'))
    m.add(types.InlineKeyboardButton('🔪 Kill All Bots', callback_data='kill_all_bots'))
    m.add(types.InlineKeyboardButton('✅ Approve File', callback_data='approve_file_panel'))
    m.add(types.InlineKeyboardButton('❌ Unapprove File', callback_data='unapprove_file_panel'))
    m.add(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_subscription_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton('➕ Add', callback_data='add_subscription'),
          types.InlineKeyboardButton('➖ Remove', callback_data='remove_subscription'))
    m.row(types.InlineKeyboardButton('🔍 Check', callback_data='check_subscription'))
    m.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_admin_settings_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton('📊 Sys Info', callback_data='system_info'),
          types.InlineKeyboardButton('📈 Perf', callback_data='bot_performance'))
    m.row(types.InlineKeyboardButton('🧹 Cleanup', callback_data='cleanup_files'),
          types.InlineKeyboardButton('🔄 Sync All Files', callback_data='sync_files'))
    m.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_ram_plans_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.row(types.InlineKeyboardButton('📊 Set Plan', callback_data='set_plan'),
          types.InlineKeyboardButton('🧠 Set RAM', callback_data='set_custom_ram'))
    m.row(types.InlineKeyboardButton('❌ Remove RAM', callback_data='remove_custom_ram_cb'),
          types.InlineKeyboardButton('👁️ View RAM', callback_data='view_user_ram'))
    m.row(types.InlineKeyboardButton('📋 All Plans', callback_data='view_all_plans'))
    m.row(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

def create_maintenance_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    st = "🟢 ON" if maintenance_mode else "🔴 OFF"
    m.add(types.InlineKeyboardButton(f"🛠️ Toggle ({st})", callback_data='toggle_maintenance'))
    m.add(types.InlineKeyboardButton('🔙 Back', callback_data='back_to_main'))
    return m

# ============================================================
# FILE HANDLERS
# ============================================================
def handle_zip_file(content, fn_zip, message):
    uid = message.from_user.id
    folder = get_user_folder(uid)
    tmp = None
    try:
        tmp = tempfile.mkdtemp(prefix=f"u{uid}_z_")
        zp = os.path.join(tmp, fn_zip)
        with open(zp, 'wb') as f: f.write(content)
        safe, smsg = scan_zip_security(zp)
        if not safe:
            warn = f"🚨 Approval:\n👤 {uid}\n📁 {fn_zip}\n⚠️ {smsg}"
            mk = types.InlineKeyboardMarkup()
            mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_zip_{uid}_{fn_zip}"),
                   types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_zip_{uid}_{fn_zip}"))
            for aid in admin_ids:
                try: bot.send_message(aid, warn, reply_markup=mk)
                except: pass
            pending_zip_files.setdefault(uid, {})[fn_zip] = content
            bot.reply_to(message, "⏳ Under review.")
            return
        process_zip_file(zp, uid, folder, fn_zip, message, tmp)
    except Exception as e:
        logger.error(f"Zip err: {e}")
        bot.reply_to(message, f"❌ {e}")
    finally:
        if tmp and os.path.exists(tmp):
            try: shutil.rmtree(tmp)
            except: pass

def process_zip_file(zp, uid, folder, fn_zip, message, tmp=None):
    cleanup = False
    if tmp is None:
        tmp = tempfile.mkdtemp(prefix=f"u{uid}_z_")
        cleanup = True
    try:
        with zipfile.ZipFile(zp, 'r') as z:
            for m in z.infolist():
                mp = os.path.abspath(os.path.join(tmp, m.filename))
                if not mp.startswith(os.path.abspath(tmp)):
                    raise zipfile.BadZipFile(f"Unsafe: {m.filename}")
            z.extractall(tmp)
        items = os.listdir(tmp)
        py = [f for f in items if f.endswith('.py')]
        js = [f for f in items if f.endswith('.js')]
        req = 'requirements.txt' if 'requirements.txt' in items else None
        pkg = 'package.json' if 'package.json' in items else None
        if req:
            bot.reply_to(message, f"🔄 Installing `{req}`...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', os.path.join(tmp, req)],
                               capture_output=True, text=True, check=True)
                bot.reply_to(message, "✅ Deps installed.")
            except subprocess.CalledProcessError as e:
                bot.reply_to(message, f"❌ pip: {str(e.stderr)[:300]}"); return
        if pkg:
            bot.reply_to(message, "🔄 npm install...")
            try: subprocess.run(['npm', 'install'], cwd=tmp, capture_output=True, text=True, check=True)
            except Exception as e: bot.reply_to(message, f"❌ npm: {e}"); return
        main = None; ftype = None
        for p in ['main.py', 'bot.py', 'app.py']:
            if p in py: main = p; ftype = 'py'; break
        if not main:
            for p in ['index.js', 'main.js', 'bot.js']:
                if p in js: main = p; ftype = 'js'; break
        if not main:
            if py: main = py[0]; ftype = 'py'
            elif js: main = js[0]; ftype = 'js'
        if not main:
            bot.reply_to(message, "❌ No .py/.js found"); return
        for item in os.listdir(tmp):
            src = os.path.join(tmp, item)
            dst = os.path.join(folder, item)
            if os.path.isdir(dst): shutil.rmtree(dst)
            elif os.path.exists(dst): os.remove(dst)
            shutil.move(src, dst)
        all_files = scan_disk_for_user_files(uid)
        for f_fn, f_ft in all_files:
            save_user_file(uid, f_fn, f_ft)
            approve_file(uid, f_fn)
        mp = os.path.join(folder, main)
        bot.reply_to(message, f"✅ Extracted. Starting `{main}`...")
        if ftype == 'py':
            threading.Thread(target=run_script, args=(mp, uid, folder, main, message)).start()
        else:
            threading.Thread(target=run_js_script, args=(mp, uid, folder, main, message)).start()
    except Exception as e:
        logger.error(f"Process zip err: {e}")
        bot.reply_to(message, f"❌ {e}")
    finally:
        if cleanup and tmp and os.path.exists(tmp):
            try: shutil.rmtree(tmp)
            except: pass

def handle_js_file(fp, oid, folder, fn, msg):
    try:
        save_user_file(oid, fn, 'js')
        approve_file(oid, fn)
        threading.Thread(target=run_js_script, args=(fp, oid, folder, fn, msg)).start()
    except Exception as e:
        logger.error(f"JS err: {e}")
        bot.reply_to(msg, f"❌ {e}")

def handle_py_file(fp, oid, folder, fn, msg):
    try:
        save_user_file(oid, fn, 'py')
        approve_file(oid, fn)
        threading.Thread(target=run_script, args=(fp, oid, folder, fn, msg)).start()
    except Exception as e:
        logger.error(f"PY err: {e}")
        bot.reply_to(msg, f"❌ {e}")

# ============================================================
# MODULE INSTALL
# ============================================================
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram', 'pyrogram': 'pyrogram', 'telethon': 'telethon',
    'bs4': 'beautifulsoup4', 'requests': 'requests', 'pillow': 'Pillow',
    'cv2': 'opencv-python', 'yaml': 'PyYAML', 'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil', 'psutil': 'psutil',
    'asyncio': None, 'json': None, 'datetime': None, 'os': None, 'sys': None,
    're': None, 'time': None, 'math': None, 'random': None, 'logging': None,
    'threading': None, 'subprocess': None, 'zipfile': None, 'tempfile': None,
    'shutil': None, 'sqlite3': None, 'atexit': None
}

def attempt_install_pip(mod, message):
    pkg = TELEGRAM_MODULES.get(mod.lower(), mod)
    if pkg is None: return False, "Core module"
    try:
        bot.reply_to(message, f"🐍 Installing `{pkg}`...", parse_mode='Markdown')
        r = subprocess.run([sys.executable, '-m', 'pip', 'install', pkg],
                           capture_output=True, text=True, check=False)
        if r.returncode == 0:
            bot.reply_to(message, f"✅ `{pkg}` installed!", parse_mode='Markdown')
            return True, r.stdout
        else:
            bot.reply_to(message, f"❌ Failed `{pkg}`")
            return False, r.stderr
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")
        return False, str(e)

def attempt_install_npm(mod, folder, message):
    try:
        bot.reply_to(message, f"🟠 npm `{mod}`...")
        r = subprocess.run(['npm', 'install', mod], capture_output=True, text=True,
                           check=False, cwd=folder)
        if r.returncode == 0:
            bot.reply_to(message, f"✅ npm `{mod}` installed!")
            return True, r.stdout
        else:
            bot.reply_to(message, f"❌ {str(r.stderr)[:300]}")
            return False, r.stderr
    except FileNotFoundError:
        bot.reply_to(message, "❌ npm not found"); return False, ""
    except Exception as e:
        bot.reply_to(message, f"❌ {e}"); return False, ""

def manual_install_module_init(message):
    uid = message.from_user.id
    if is_user_banned(uid): banned_response(message.chat.id, message); return
    if is_maintenance_blocked(uid): maintenance_response(message.chat.id, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(message, txt, reply_markup=mk, parse_mode='Markdown'); return
    if bot_locked and uid not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked."); return
    m = bot.reply_to(message, "📦 Send module name (`requests` or `npm:express`)\n/cancel")
    bot.register_next_step_handler(m, process_manual_install)

def process_manual_install(message):
    uid = message.from_user.id
    if is_user_banned(uid): banned_response(message.chat.id, message); return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    mod = message.text.strip()
    if mod.lower().startswith('npm:'):
        mod = mod[4:].strip()
        attempt_install_npm(mod, get_user_folder(uid), message)
    else:
        attempt_install_pip(mod, message)

# ============================================================
# DETACHED PROCESS LAUNCH
# ============================================================
def _popen_detached(cmd, cwd, log_file):
    kwargs = {
        'cwd': cwd,
        'stdout': log_file,
        'stderr': log_file,
        'stdin': subprocess.DEVNULL,
    }
    if os.name == 'nt':
        kwargs['creationflags'] = (
            subprocess.DETACHED_PROCESS |
            subprocess.CREATE_NEW_PROCESS_GROUP |
            subprocess.CREATE_NO_WINDOW
        )
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs['startupinfo'] = si
    else:
        kwargs['start_new_session'] = True
    return subprocess.Popen(cmd, **kwargs)

# ============================================================
# RUN SCRIPTS
# ============================================================
def run_script(path, oid, folder, fn, msg, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(msg, f"❌ Failed `{fn}` after {max_attempts} tries.")
        return
    key = f"{oid}_{fn}"
    logger.info(f"Run py {path} for {oid} (attempt {attempt})")
    try:
        if not os.path.exists(path):
            bot.reply_to(msg, f"❌ Not found: `{fn}`")
            remove_user_file_db(oid, fn); return
        can_run, reason = can_run_bots(oid, fn)
        if not can_run:
            try:
                bot.send_message(oid,
                    f"⏰ **Trial Expired!**\n\n"
                    f"📁 `{fn}` needs approval or subscription.\n"
                    f"📞 Contact @{YOUR_USERNAME}",
                    parse_mode='Markdown')
            except: pass
            return
        if attempt == 1:
            chk = None
            try:
                chk = subprocess.Popen([sys.executable, path], cwd=folder,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', errors='ignore')
                so, se = chk.communicate(timeout=5)
                if chk.returncode != 0 and se:
                    m = re.search(r"ModuleNotFoundError: No module named '(.+?)'", se)
                    if m:
                        mod = m.group(1).strip().strip("'\"")
                        ok, _ = attempt_install_pip(mod, msg)
                        if ok:
                            time.sleep(2)
                            threading.Thread(target=run_script,
                                             args=(path, oid, folder, fn, msg, attempt+1)).start()
                            return
                        else: return
                    else:
                        bot.reply_to(msg, f"❌ Pre-check:\n```\n{se[:400]}\n```", parse_mode='Markdown')
                        return
            except subprocess.TimeoutExpired:
                if chk and chk.poll() is None: chk.kill(); chk.communicate()
            except FileNotFoundError:
                bot.reply_to(msg, f"❌ Python not found"); return
            except Exception as e:
                logger.error(f"Pre-check err: {e}")
            finally:
                if chk and chk.poll() is None:
                    try: chk.kill(); chk.communicate()
                    except: pass
        lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
        try: lf = open(lp, 'a', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(msg, f"❌ Log err: {e}"); return
        try:
            p = _popen_detached([sys.executable, path], folder, lf)
            bot_scripts[key] = {
                'process': p, 'pid': p.pid, 'log_file': lf, 'file_name': fn,
                'chat_id': msg.chat.id, 'script_owner_id': oid,
                'start_time': datetime.now(), 'user_folder': folder,
                'type': 'py', 'script_key': key, 'detached': True
            }
            save_running_process(oid, fn, p.pid, 'py')
            rl = get_plan_ram_limit(oid)
            rs = f"{rl}MB" if rl != float('inf') else "Unlimited"
            bot.reply_to(msg, f"✅ Python `{fn}` started! (PID: {p.pid})\n🧠 RAM: {rs}")
        except FileNotFoundError:
            bot.reply_to(msg, "❌ Python not found")
            if lf and not lf.closed: lf.close()
        except Exception as e:
            if lf and not lf.closed: lf.close()
            bot.reply_to(msg, f"❌ {e}")
            if key in bot_scripts: del bot_scripts[key]
    except Exception as e:
        logger.error(f"run_script err: {e}")
        bot.reply_to(msg, f"❌ {e}")

def run_js_script(path, oid, folder, fn, msg, attempt=1):
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(msg, f"❌ Failed `{fn}` after {max_attempts} tries.")
        return
    key = f"{oid}_{fn}"
    logger.info(f"Run js {path} for {oid}")
    try:
        if not os.path.exists(path):
            bot.reply_to(msg, f"❌ Not found: `{fn}`")
            remove_user_file_db(oid, fn); return
        can_run, reason = can_run_bots(oid, fn)
        if not can_run:
            try:
                bot.send_message(oid,
                    f"⏰ **Trial Expired!**\n\n"
                    f"📁 `{fn}` needs approval or subscription.\n"
                    f"📞 Contact @{YOUR_USERNAME}",
                    parse_mode='Markdown')
            except: pass
            return
        if attempt == 1:
            chk = None
            try:
                chk = subprocess.Popen(['node', path], cwd=folder,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', errors='ignore')
                so, se = chk.communicate(timeout=5)
                if chk.returncode != 0 and se:
                    m = re.search(r"Cannot find module '(.+?)'", se)
                    if m:
                        mod = m.group(1).strip().strip("'\"")
                        if not mod.startswith('.') and not mod.startswith('/'):
                            ok, _ = attempt_install_npm(mod, folder, msg)
                            if ok:
                                time.sleep(2)
                                threading.Thread(target=run_js_script,
                                                 args=(path, oid, folder, fn, msg, attempt+1)).start()
                                return
                            else: return
                    bot.reply_to(msg, f"❌ Pre-check:\n```\n{se[:400]}\n```", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                if chk and chk.poll() is None: chk.kill(); chk.communicate()
            except FileNotFoundError:
                bot.reply_to(msg, "❌ 'node' not found"); return
            except Exception as e:
                logger.error(f"JS pre-check err: {e}")
            finally:
                if chk and chk.poll() is None:
                    try: chk.kill(); chk.communicate()
                    except: pass
        lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
        try: lf = open(lp, 'a', encoding='utf-8', errors='ignore')
        except Exception as e:
            bot.reply_to(msg, f"❌ Log err: {e}"); return
        try:
            p = _popen_detached(['node', path], folder, lf)
            bot_scripts[key] = {
                'process': p, 'pid': p.pid, 'log_file': lf, 'file_name': fn,
                'chat_id': msg.chat.id, 'script_owner_id': oid,
                'start_time': datetime.now(), 'user_folder': folder,
                'type': 'js', 'script_key': key, 'detached': True
            }
            save_running_process(oid, fn, p.pid, 'js')
            rl = get_plan_ram_limit(oid)
            rs = f"{rl}MB" if rl != float('inf') else "Unlimited"
            bot.reply_to(msg, f"✅ JS `{fn}` started! (PID: {p.pid})\n🧠 RAM: {rs}")
        except FileNotFoundError:
            bot.reply_to(msg, "❌ 'node' not found")
            if lf and not lf.closed: lf.close()
        except Exception as e:
            if lf and not lf.closed: lf.close()
            bot.reply_to(msg, f"❌ {e}")
            if key in bot_scripts: del bot_scripts[key]
    except Exception as e:
        logger.error(f"run_js err: {e}")
        bot.reply_to(msg, f"❌ {e}")

# ============================================================
# WELCOME / LOGIC
# ============================================================
def _logic_send_welcome(message):
    uid = message.from_user.id
    cid = message.chat.id
    uname = message.from_user.first_name
    if is_user_banned(uid): banned_response(cid, message); return
    if is_maintenance_blocked(uid): maintenance_response(cid, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.send_message(cid, txt, reply_markup=mk, parse_mode='Markdown'); return
    if bot_locked and uid not in admin_ids:
        bot.send_message(cid, "⚠️ Bot locked."); return
    if uid not in admin_ids and uid != OWNER_ID:
        if uid not in user_trials and not has_active_subscription(uid):
            start_trial(uid)
    plan = get_user_plan(uid)
    pi = PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])
    ram = get_plan_ram_limit(uid)
    rs = f"{ram} MB" if ram != float('inf') else "Unlimited"
    fl = get_plan_file_limit(uid)
    fls = "Unlimited" if fl == float('inf') else str(fl)
    cur = get_user_file_count(uid)
    ti = ""
    if has_active_trial(uid):
        dl = (user_trials[uid]['end'] - datetime.now()).days
        ti = f"\n🎁 Trial: {dl} day(s) left"
    msg = (f"〽️ Welcome, {uname}!\n\n"
           f"🆔 ID: `{uid}`\n"
           f"💎 Plan: {pi['label']}{ti}\n"
           f"🧠 RAM: {rs}\n"
           f"📁 Files: {cur} / {fls}\n\n"
           f"🤖 Host Python/JS scripts\n"
           f"📦 Manual module install\n\n"
           f"👇 Use buttons or type commands.")
    try: bot.send_message(cid, msg, reply_markup=create_reply_keyboard(uid), parse_mode='Markdown')
    except Exception as e: logger.error(f"Welcome err: {e}")

def _logic_updates(message):
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton('📢 Updates', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'))
    bot.reply_to(message, "Updates Channel:", reply_markup=m)

def _logic_upload(message):
    uid = message.from_user.id
    if is_user_banned(uid): banned_response(message.chat.id, message); return
    if is_maintenance_blocked(uid): maintenance_response(message.chat.id, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(message, txt, reply_markup=mk, parse_mode='Markdown'); return
    if bot_locked and uid not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked."); return
    lim = get_plan_file_limit(uid); cur = get_user_file_count(uid)
    if cur >= lim:
        ls = "Unlimited" if lim == float('inf') else str(lim)
        bot.reply_to(message, f"⚠️ Limit ({cur}/{ls}) reached."); return
    bot.reply_to(message, "📤 Send `.py`, `.js`, or `.zip` file.")

def _logic_check_files(message):
    uid = message.from_user.id
    if is_user_banned(uid): banned_response(message.chat.id, message); return
    if is_maintenance_blocked(uid): maintenance_response(message.chat.id, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(message, txt, reply_markup=mk, parse_mode='Markdown'); return

    try: sync_user_files_from_disk(uid)
    except Exception as e: logger.error(f"sync {uid}: {e}")

    db_files = {fn: ft for fn, ft in user_files.get(uid, [])}
    disk_files = dict(scan_disk_for_user_files(uid))
    merged = {}
    for fn, ft in disk_files.items(): merged[fn] = ft
    for fn, ft in db_files.items():
        if fn not in merged: merged[fn] = ft

    if not merged:
        bot.reply_to(message, "📂 Your files:\n\n(No files)"); return

    m = types.InlineKeyboardMarkup(row_width=1)
    for fn in sorted(merged.keys()):
        ft = merged[fn]
        r = is_bot_running(uid, fn)
        ic = "🟢 Running" if r else "🔴 Stopped"
        ap = "✅" if is_file_approved(uid, fn) else ""
        m.add(types.InlineKeyboardButton(f"{ap} {fn} ({ft}) - {ic}", callback_data=f'file_{uid}_{fn}'))

    total = len(merged)
    lim = get_plan_file_limit(uid)
    ls = "Unlimited" if lim == float('inf') else str(lim)
    header = f"📂 Your files ({total}/{ls}):"
    try: bot.reply_to(message, header, reply_markup=m, parse_mode='Markdown')
    except Exception as e: logger.error(f"check_files send: {e}")

def _logic_bot_speed(message):
    uid = message.from_user.id
    if is_user_banned(uid): banned_response(message.chat.id, message); return
    if is_maintenance_blocked(uid): maintenance_response(message.chat.id, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(message, txt, reply_markup=mk, parse_mode='Markdown'); return
    st = time.time()
    w = bot.reply_to(message, "🏃 Testing...")
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        rt = round((time.time() - st) * 1000, 2)
        status = "🔓" if not bot_locked else "🔒"
        plan = get_user_plan(uid)
        pl = PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])['label']
        ram = get_plan_ram_limit(uid)
        rs = f"{ram} MB" if ram != float('inf') else "Unlimited"
        msg = f"⚡ Speed:\n\n⏱️ {rt} ms\n🚦 {status}\n💎 {pl}\n🧠 RAM: {rs}"
        bot.edit_message_text(msg, message.chat.id, w.message_id)
    except: pass

def _logic_contact_owner(message):
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton('📞 Contact', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact:", reply_markup=m)

def _logic_manual_install(message): manual_install_module_init(message)

def _logic_help(message):
    t = """
🤖 **Tobi Hosting Bot Help**

**📌 Commands:**
• /start, /help, /status, /ping
• /killuser <id> — admin only
• /killall — owner only
• /approve <id> <file> — admin
• /syncfiles — admin

**📁 Files:** Upload .py / .js / .zip
**📂 All files hamesha dikhengi (disk scan)**

**📦 Modules:** Auto/Manual install

**💎 Plans:** Free, Baby, Basic, Premium, God, Ultimate, Lifetime
🎁 Free Trial: 15 days (1 file)

**🧠 RAM Auto-monitored**
**👑 Admin/Owner = Unlimited files**

**Support:** @Rolexseller1
"""
    bot.reply_to(message, t, parse_mode='Markdown')

def _logic_statistics(message):
    uid = message.from_user.id
    if is_user_banned(uid): banned_response(message.chat.id, message); return
    if is_maintenance_blocked(uid): maintenance_response(message.chat.id, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(message, txt, reply_markup=mk, parse_mode='Markdown'); return
    total = len(active_users)
    files = 0
    try:
        for ud in os.listdir(UPLOAD_BOTS_DIR):
            up = os.path.join(UPLOAD_BOTS_DIR, ud)
            if os.path.isdir(up):
                for f in os.listdir(up):
                    if os.path.splitext(f)[1].lower() in ('.py', '.js'):
                        files += 1
    except: pass
    running = 0; user_run = 0
    for key, info in list(bot_scripts.items()):
        try:
            oid = int(key.split('_', 1)[0])
            if is_bot_running(oid, info['file_name']):
                running += 1
                if oid == uid: user_run += 1
        except: pass
    txt = (f"📊 **Statistics:**\n\n"
           f"👥 Users: {total}\n"
           f"🚫 Banned: {len(banned_users)}\n"
           f"📂 Total Files (disk): {files}\n"
           f"🟢 Active Bots: {running}\n")
    if uid in admin_ids:
        txt += (f"🔒 Lock: {'🔴' if bot_locked else '🟢'}\n"
                f"🛠️ Maint: {'🟢' if maintenance_mode else '🔴'}\n"
                f"📢 Channels: {len(mandatory_channels)}\n"
                f"💎 Plans: {len(user_plans)}\n"
                f"🧠 Custom RAM: {len(custom_ram_mb)}\n"
                f"✅ Approved: {sum(len(s) for s in approved_files.values())}\n")
    txt += f"🤖 Your Bots: {user_run}"
    bot.reply_to(message, txt, parse_mode='Markdown')

def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "💳 Subscription:", reply_markup=create_subscription_menu())

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    m = bot.reply_to(message, "📢 Send message.\n/cancel")
    bot.register_next_step_handler(m, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    global bot_locked
    bot_locked = not bot_locked
    st = "locked" if bot_locked else "unlocked"
    bot.reply_to(message, f"🔒 Bot {st}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "👑 Admin Panel:", reply_markup=create_admin_panel())

def _logic_user_management(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "👥 User Mgmt:", reply_markup=create_user_management_menu())

def _logic_admin_settings(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "⚙️ Settings:", reply_markup=create_admin_settings_menu())

def _logic_ram_plans(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "🧠 RAM & Plans:", reply_markup=create_ram_plans_menu())

def _logic_maintenance(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "🛠️ Maintenance:", reply_markup=create_maintenance_menu())

def _logic_kill_user_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "🔪 Kill / Approve Panel:", reply_markup=create_kill_user_menu())

def _logic_sync_files(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    w = bot.reply_to(message, "🔄 Syncing all user files from disk...")
    try:
        sync_all_users_from_disk()
        rehydrate_running_processes()
        bot.edit_message_text("✅ Sync complete. All orphan files recovered.",
                              message.chat.id, w.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Sync error: {e}", message.chat.id, w.message_id)

def _logic_run_all_scripts(mc):
    if isinstance(mc, telebot.types.Message):
        aid = mc.from_user.id; cid = mc.chat.id
        reply = lambda t, **k: bot.reply_to(mc, t, **k)
        mo = mc
    elif isinstance(mc, telebot.types.CallbackQuery):
        aid = mc.from_user.id; cid = mc.message.chat.id
        bot.answer_callback_query(mc.id)
        reply = lambda t, **k: bot.send_message(cid, t, **k)
        mo = mc.message
    else: return
    if aid not in admin_ids:
        reply("⚠️ Admin only."); return
    reply("⏳ Starting all scripts...")
    started = 0
    try:
        for ud in os.listdir(UPLOAD_BOTS_DIR):
            try: tgt = int(ud)
            except: continue
            folder = get_user_folder(tgt)
            for f in os.listdir(folder):
                if os.path.splitext(f)[1].lower() not in ('.py', '.js'): continue
                ft = 'py' if f.endswith('.py') else 'js'
                if not is_bot_running(tgt, f):
                    p = os.path.join(folder, f)
                    try:
                        if ft == 'py':
                            threading.Thread(target=run_script, args=(p, tgt, folder, f, mo)).start()
                            started += 1
                        else:
                            threading.Thread(target=run_js_script, args=(p, tgt, folder, f, mo)).start()
                            started += 1
                        time.sleep(0.3)
                    except: pass
    except Exception as e:
        logger.error(f"run_all err: {e}")
    reply(f"✅ Started {started} scripts.")

def _logic_manage_channels(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    bot.reply_to(message, "📢 Channels:", reply_markup=create_mandatory_channels_menu())

def _logic_admin_install(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    m = bot.reply_to(message, "🛠️ Send `user_id module`\n/cancel")
    bot.register_next_step_handler(m, process_admin_install)

def process_admin_install(message):
    aid = message.from_user.id
    if aid not in admin_ids: return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: `user_id module`"); return
        uid = int(parts[0])
        mod = ' '.join(parts[1:])
        if mod.lower().startswith('npm:'):
            mod = mod[4:].strip()
            attempt_install_npm(mod, get_user_folder(uid), message)
        else:
            attempt_install_pip(mod, message)
        try: bot.send_message(uid, f"📦 Admin installed `{mod}`.")
        except: pass
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")

# ============================================================
# COMMANDS
# ============================================================
@bot.message_handler(commands=['start', 'help'])
def cmd_start_help(m):
    if m.text == '/help': _logic_help(m)
    else: _logic_send_welcome(m)

@bot.message_handler(commands=['status'])
def cmd_status(m): _logic_statistics(m)

@bot.message_handler(commands=['ping'])
def cmd_ping(m):
    uid = m.from_user.id
    if is_user_banned(uid): banned_response(m.chat.id, m); return
    if is_maintenance_blocked(uid): maintenance_response(m.chat.id, m); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(m, txt, reply_markup=mk, parse_mode='Markdown'); return
    st = time.time()
    msg = bot.reply_to(m, "Pong!")
    lat = round((time.time() - st) * 1000, 2)
    bot.edit_message_text(f"Pong! {lat} ms", m.chat.id, msg.message_id)

@bot.message_handler(commands=['killuser'])
def cmd_kill_user(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Usage: `/killuser 123456789`", parse_mode='Markdown'); return
        uid = int(parts[1])
        killed = force_kill_user(uid)
        if killed:
            bot.reply_to(message,
                f"🔪 **Killed {len(killed)} bot(s)** for `{uid}`\n\n" +
                "\n".join(f"• `{k}`" for k in killed),
                parse_mode='Markdown')
            try: bot.send_message(uid, "⚠️ Your bots were stopped by admin.")
            except: pass
        else:
            bot.reply_to(message, f"ℹ️ No running bots for `{uid}`.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")

@bot.message_handler(commands=['killall'])
def cmd_kill_all(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "⚠️ Owner only."); return
    n = force_kill_all()
    bot.reply_to(message, f"🔪 Killed {n} process(es).")

@bot.message_handler(commands=['approve'])
def cmd_approve(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    try:
        parts = message.text.split(None, 2)
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ Usage: `/approve 123456789 main.py`", parse_mode='Markdown'); return
        uid = int(parts[1]); fn = parts[2].strip()
        if approve_file(uid, fn):
            bot.reply_to(message, f"✅ `{uid}/{fn}` approved.", parse_mode='Markdown')
            try: bot.send_message(uid, f"✅ File `{fn}` approved. Trial ke baad bhi chalegi.")
            except: pass
        else:
            bot.reply_to(message, "❌ Failed.")
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")

@bot.message_handler(commands=['syncfiles'])
def cmd_sync_files(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    _logic_sync_files(message)

@bot.message_handler(commands=['setforwardchannel'])
def cmd_set_forward_channel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Usage: `/setforwardchannel -1001234567890`", parse_mode='Markdown')
            return
        new_id = int(parts[1])
        global PRIVATE_CHANNEL_ID
        PRIVATE_CHANNEL_ID = new_id
        FORWARD_BOT.send_message(new_id, "✅ Forward channel set successfully!")
        bot.reply_to(message, f"✅ Forward channel: `{new_id}`", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")

@bot.message_handler(commands=['testforward'])
def cmd_test_forward(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin only."); return
    try:
        FORWARD_BOT.send_message(PRIVATE_CHANNEL_ID, "🧪 Test message from bot!")
        bot.reply_to(message, "✅ Test sent to private channel.")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed: {e}")

BUTTON_MAP = {
    "📢 Updates Channel": _logic_updates,
    "📤 Upload File": _logic_upload,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "💳 Subscriptions": _logic_subscriptions_panel,
    "📢 Broadcast": _logic_broadcast_init,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "👑 Admin Panel": _logic_admin_panel,
    "📢 Channel Add": _logic_manage_channels,
    "👥 User Management": _logic_user_management,
    "🛠️ Manual Install": _logic_manual_install,
    "⚙️ Settings": _logic_admin_settings,
    "📦 Manual Install": _logic_manual_install,
    "🧠 RAM & Plans": _logic_ram_plans,
    "🛠️ Maintenance": _logic_maintenance,
    "🔪 Kill User": _logic_kill_user_panel,
    "🔄 Sync Files": _logic_sync_files,
    "🆘 Help": _logic_help
}

@bot.message_handler(func=lambda m: m.text in BUTTON_MAP)
def handle_button(m):
    fn = BUTTON_MAP.get(m.text)
    if fn: fn(m)

# ============================================================
# DOCUMENT HANDLER
# ============================================================
@bot.message_handler(content_types=['document'])
def handle_doc(message):
    uid = message.from_user.id
    cid = message.chat.id
    if is_user_banned(uid): banned_response(cid, message); return
    if is_maintenance_blocked(uid): maintenance_response(cid, message); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.reply_to(message, txt, reply_markup=mk, parse_mode='Markdown'); return
    doc = message.document
    if bot_locked and uid not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked."); return
    lim = get_plan_file_limit(uid); cur = get_user_file_count(uid)
    if cur >= lim:
        ls = "Unlimited" if lim == float('inf') else str(lim)
        bot.reply_to(message, f"⚠️ Limit ({cur}/{ls}) reached.\n🗑️ Delete old files first.")
        return
    fn = doc.file_name
    if not fn:
        bot.reply_to(message, "⚠️ No filename."); return
    ext = os.path.splitext(fn)[1].lower()
    if ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only .py/.js/.zip"); return
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(message, "⚠️ Max 20MB."); return

    forward_uploaded_file(message, fn, ext[1:], uid, doc.file_size)

    try:
        bot.forward_message(OWNER_ID, cid, message.message_id)
        bot.send_message(OWNER_ID,
            f"⬆️ `{fn}` from {message.from_user.first_name} (`{uid}`)\n📊 {doc.file_size/1024:.1f} KB",
            parse_mode='Markdown')
    except: pass

    try:
        w = bot.reply_to(message, f"⏳ Downloading `{fn}`...")
        fi = bot.get_file(doc.file_id)
        content = bot.download_file(fi.file_path)
        bot.edit_message_text(f"✅ Downloaded. Processing...", cid, w.message_id)
        folder = get_user_folder(uid)
        if ext == '.zip':
            handle_zip_file(content, fn, message)
        else:
            fp = os.path.join(folder, fn)
            with open(fp, 'wb') as f: f.write(content)
            safe, smsg = check_code_security(fp, ext[1:])
            if not safe:
                warn = f"🚨 Approval:\n👤 {uid}\n📁 {fn}\n⚠️ {smsg}"
                mk = types.InlineKeyboardMarkup()
                mk.row(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_file_{uid}_{fn}"),
                       types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_file_{uid}_{fn}"))
                for aid in admin_ids:
                    try: bot.send_message(aid, warn, reply_markup=mk)
                    except: pass
                bot.reply_to(message, "⏳ Under review.")
                return
            if ext == '.js': handle_js_file(fp, uid, folder, fn, message)
            elif ext == '.py': handle_py_file(fp, uid, folder, fn, message)
    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"TG err: {e}")
        bot.reply_to(message, f"❌ API: {str(e)[:200]}")
    except Exception as e:
        logger.error(f"Doc err: {e}", exc_info=True)
        bot.reply_to(message, f"❌ {str(e)}")

# ============================================================
# CALLBACK HANDLER
# ============================================================
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    uid = call.from_user.id
    data = call.data
    if is_user_banned(uid) and data != 'back_to_main':
        bot.answer_callback_query(call.id, "🚫 Banned.", show_alert=True); return
    if data not in ['check_subscription_status', 'back_to_main', 'manual_install']:
        ok, nj = check_mandatory_subscription(uid)
        if not ok and uid not in admin_ids:
            txt, mk = create_subscription_check_message(nj)
            bot.answer_callback_query(call.id)
            try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=mk, parse_mode='Markdown')
            except: bot.send_message(call.message.chat.id, txt, reply_markup=mk, parse_mode='Markdown')
            return
    if maintenance_mode and uid not in admin_ids and data not in ['back_to_main', 'speed', 'stats', 'check_subscription_status']:
        bot.answer_callback_query(call.id, "🛠️ Maintenance.", show_alert=True); return
    if bot_locked and uid not in admin_ids and data not in ['back_to_main', 'speed', 'stats', 'check_subscription_status', 'manual_install']:
        bot.answer_callback_query(call.id, "⚠️ Locked.", show_alert=True); return
    try:
        if data == 'upload': cb_upload(call)
        elif data == 'check_files': cb_check_files(call)
        elif data.startswith('file_'): cb_file_ctrl(call)
        elif data.startswith('start_'): cb_start(call)
        elif data.startswith('stop_'): cb_stop(call)
        elif data.startswith('restart_'): cb_restart(call)
        elif data.startswith('delete_'): cb_delete(call)
        elif data.startswith('logs_'): cb_logs(call)
        elif data == 'speed': cb_speed(call)
        elif data == 'back_to_main': cb_back_main(call)
        elif data.startswith('confirm_broadcast_'): cb_confirm_bc(call)
        elif data == 'cancel_broadcast': cb_cancel_bc(call)
        elif data == 'manual_install': cb_manual_install(call)
        elif data == 'subscription': admin_only(call, cb_sub_menu)
        elif data == 'stats': cb_stats(call)
        elif data == 'lock_bot': admin_only(call, cb_lock)
        elif data == 'unlock_bot': admin_only(call, cb_unlock)
        elif data == 'run_all_scripts': admin_only(call, lambda c: _logic_run_all_scripts(c))
        elif data == 'broadcast': admin_only(call, cb_bc_init)
        elif data == 'admin_panel': admin_only(call, cb_admin_panel)
        elif data == 'add_admin': owner_only(call, cb_add_admin)
        elif data == 'remove_admin': owner_only(call, cb_remove_admin)
        elif data == 'list_admins': admin_only(call, cb_list_admins)
        elif data == 'add_subscription': admin_only(call, cb_add_sub)
        elif data == 'remove_subscription': admin_only(call, cb_remove_sub)
        elif data == 'check_subscription': admin_only(call, cb_check_sub)
        elif data == 'user_management': admin_only(call, cb_user_mgmt)
        elif data == 'ban_user': admin_only(call, cb_ban)
        elif data == 'unban_user': admin_only(call, cb_unban)
        elif data == 'user_info': admin_only(call, cb_user_info)
        elif data == 'all_users': admin_only(call, cb_all_users)
        elif data == 'set_user_limit': admin_only(call, cb_set_limit)
        elif data == 'remove_user_limit': admin_only(call, cb_remove_limit)
        elif data == 'admin_settings': admin_only(call, cb_admin_settings)
        elif data == 'system_info': admin_only(call, cb_sys_info)
        elif data == 'bot_performance': admin_only(call, cb_perf)
        elif data == 'cleanup_files': admin_only(call, cb_cleanup)
        elif data == 'admin_install': admin_only(call, cb_admin_install)
        elif data == 'manage_mandatory_channels': admin_only(call, cb_manage_channels)
        elif data == 'add_mandatory_channel': admin_only(call, cb_add_ch)
        elif data == 'remove_mandatory_channel': admin_only(call, cb_remove_ch_menu)
        elif data == 'list_mandatory_channels': admin_only(call, cb_list_ch)
        elif data.startswith('remove_channel_'): admin_only(call, cb_proc_remove_ch)
        elif data == 'check_subscription_status': cb_check_sub_status(call)
        elif data == 'ram_plans': admin_only(call, cb_ram_plans)
        elif data == 'maintenance': admin_only(call, cb_maintenance)
        elif data == 'toggle_maintenance': admin_only(call, cb_toggle_maint)
        elif data == 'set_plan': admin_only(call, cb_set_plan)
        elif data == 'set_custom_ram': admin_only(call, cb_set_ram)
        elif data == 'remove_custom_ram_cb': admin_only(call, cb_rm_ram)
        elif data == 'view_user_ram': admin_only(call, cb_view_ram)
        elif data == 'view_all_plans': admin_only(call, cb_all_plans)
        elif data.startswith('approve_file_'): admin_only(call, cb_approve_file)
        elif data.startswith('reject_file_'): admin_only(call, cb_reject_file)
        elif data.startswith('approve_zip_'): admin_only(call, cb_approve_zip)
        elif data.startswith('reject_zip_'): admin_only(call, cb_reject_zip)
        elif data == 'kill_user_panel': admin_only(call, cb_kill_panel)
        elif data == 'kill_by_id': admin_only(call, cb_kill_by_id)
        elif data == 'kill_all_bots': admin_only(call, cb_kill_all)
        elif data == 'approve_file_panel': admin_only(call, cb_approve_panel)
        elif data == 'unapprove_file_panel': admin_only(call, cb_unapprove_panel)
        elif data == 'sync_files': admin_only(call, cb_sync_files)
        else: bot.answer_callback_query(call.id, "Unknown.")
    except Exception as e:
        logger.error(f"CB err '{data}': {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Error.", show_alert=True)
        except: pass

def admin_only(call, fn):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True); return
    fn(call)

def owner_only(call, fn):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True); return
    fn(call)

# ============================================================
# CALLBACK IMPLS
# ============================================================
def cb_upload(call):
    uid = call.from_user.id
    if is_user_banned(uid): bot.answer_callback_query(call.id, "🚫", show_alert=True); return
    if is_maintenance_blocked(uid): bot.answer_callback_query(call.id, "🛠️", show_alert=True); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=mk, parse_mode='Markdown')
        except: bot.send_message(call.message.chat.id, txt, reply_markup=mk, parse_mode='Markdown')
        return
    lim = get_plan_file_limit(uid); cur = get_user_file_count(uid)
    if cur >= lim:
        bot.answer_callback_query(call.id, "⚠️ Limit.", show_alert=True); return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📤 Send `.py`, `.js`, `.zip`.")

def cb_check_files(call):
    uid = call.from_user.id
    if is_user_banned(uid): bot.answer_callback_query(call.id, "🚫", show_alert=True); return
    if is_maintenance_blocked(uid): bot.answer_callback_query(call.id, "🛠️", show_alert=True); return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=mk, parse_mode='Markdown')
        except: bot.send_message(call.message.chat.id, txt, reply_markup=mk, parse_mode='Markdown')
        return

    try: sync_user_files_from_disk(uid)
    except Exception as e: logger.error(f"sync {uid}: {e}")

    db_files = {fn: ft for fn, ft in user_files.get(uid, [])}
    disk_files = dict(scan_disk_for_user_files(uid))
    merged = {}
    for fn, ft in disk_files.items(): merged[fn] = ft
    for fn, ft in db_files.items():
        if fn not in merged: merged[fn] = ft

    bot.answer_callback_query(call.id)
    if not merged:
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
        try: bot.edit_message_text("📂 No files.", call.message.chat.id, call.message.message_id, reply_markup=mk)
        except: pass
        return
    m = types.InlineKeyboardMarkup(row_width=1)
    for fn in sorted(merged.keys()):
        ft = merged[fn]
        r = is_bot_running(uid, fn)
        ic = "🟢 Running" if r else "🔴 Stopped"
        ap = "✅" if is_file_approved(uid, fn) else ""
        m.add(types.InlineKeyboardButton(f"{ap} {fn} ({ft}) - {ic}", callback_data=f'file_{uid}_{fn}'))
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    total = len(merged)
    lim = get_plan_file_limit(uid)
    ls = "Unlimited" if lim == float('inf') else str(lim)
    header = f"📂 Your files ({total}/{ls}):"
    try: bot.edit_message_text(header, call.message.chat.id, call.message.message_id, reply_markup=m, parse_mode='Markdown')
    except: pass

def cb_file_ctrl(call):
    try:
        _, oid_s, fn = call.data.split('_', 2)
        oid = int(oid_s); ruid = call.from_user.id
        if not (ruid == oid or ruid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ No perm.", show_alert=True); return
        folder = get_user_folder(oid)
        fp = os.path.join(folder, fn)
        if not os.path.exists(fp):
            bot.answer_callback_query(call.id, "⚠️ File not on disk.", show_alert=True); return
        bot.answer_callback_query(call.id)
        ft = 'py' if fn.endswith('.py') else 'js'
        r = is_bot_running(oid, fn)
        st = '🟢 Running' if r else '🔴 Stopped'
        ap = "✅ Approved" if is_file_approved(oid, fn) else "⏳ Not approved"
        try: bot.edit_message_text(f"⚙️ `{fn}` ({ft}) of `{oid}`\nStatus: {st}\n{ap}",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_control_buttons(oid, fn, r), parse_mode='Markdown')
        except: pass
    except Exception as e:
        logger.error(f"file_ctrl err: {e}")

def cb_start(call):
    try:
        _, oid_s, fn = call.data.split('_', 2)
        oid = int(oid_s); ruid = call.from_user.id
        if not (ruid == oid or ruid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️", show_alert=True); return
        folder = get_user_folder(oid)
        p = os.path.join(folder, fn)
        if not os.path.exists(p):
            bot.answer_callback_query(call.id, "⚠️ Not on disk!", show_alert=True); return
        if is_bot_running(oid, fn):
            bot.answer_callback_query(call.id, "⚠️ Already running.", show_alert=True); return
        ft = 'py' if fn.endswith('.py') else 'js'
        save_user_file(oid, fn, ft)
        bot.answer_callback_query(call.id, "⏳ Starting...")
        if ft == 'py':
            threading.Thread(target=run_script, args=(p, oid, folder, fn, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(p, oid, folder, fn, call.message)).start()
        time.sleep(1.5)
        r = is_bot_running(oid, fn)
        st = '🟢 Running' if r else '🟡 Starting...'
        ap = "✅ Approved" if is_file_approved(oid, fn) else "⏳ Not approved"
        try: bot.edit_message_text(f"⚙️ `{fn}` ({ft}) of `{oid}`\nStatus: {st}\n{ap}",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_control_buttons(oid, fn, r), parse_mode='Markdown')
        except: pass
    except Exception as e:
        logger.error(f"start err: {e}")

def cb_stop(call):
    try:
        _, oid_s, fn = call.data.split('_', 2)
        oid = int(oid_s); ruid = call.from_user.id
        if not (ruid == oid or ruid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️", show_alert=True); return
        ft = 'py' if fn.endswith('.py') else 'js'
        key = f"{oid}_{fn}"
        if not is_bot_running(oid, fn):
            bot.answer_callback_query(call.id, "⚠️ Already stopped.", show_alert=True); return
        bot.answer_callback_query(call.id, "⏳ Stopping...")
        info = bot_scripts.get(key)
        if info: kill_process_tree(info); bot_scripts.pop(key, None)
        remove_running_process(oid, fn)
        try: bot.edit_message_text(f"⚙️ `{fn}` ({ft}) of `{oid}`\nStatus: 🔴 Stopped",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_control_buttons(oid, fn, False), parse_mode='Markdown')
        except: pass
    except Exception as e:
        logger.error(f"stop err: {e}")

def cb_restart(call):
    try:
        _, oid_s, fn = call.data.split('_', 2)
        oid = int(oid_s); ruid = call.from_user.id
        if not (ruid == oid or ruid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️", show_alert=True); return
        folder = get_user_folder(oid); p = os.path.join(folder, fn)
        if not os.path.exists(p):
            bot.answer_callback_query(call.id, "⚠️ Missing!", show_alert=True); return
        ft = 'py' if fn.endswith('.py') else 'js'
        bot.answer_callback_query(call.id, "⏳ Restarting...")
        key = f"{oid}_{fn}"
        if is_bot_running(oid, fn):
            info = bot_scripts.get(key)
            if info: kill_process_tree(info)
            bot_scripts.pop(key, None)
            remove_running_process(oid, fn)
            time.sleep(1.5)
        if ft == 'py':
            threading.Thread(target=run_script, args=(p, oid, folder, fn, call.message)).start()
        else:
            threading.Thread(target=run_js_script, args=(p, oid, folder, fn, call.message)).start()
        time.sleep(1.5)
        r = is_bot_running(oid, fn)
        st = '🟢 Running' if r else '🟡 Starting...'
        try: bot.edit_message_text(f"⚙️ `{fn}` ({ft}) of `{oid}`\nStatus: {st}",
            call.message.chat.id, call.message.message_id,
            reply_markup=create_control_buttons(oid, fn, r), parse_mode='Markdown')
        except: pass
    except Exception as e:
        logger.error(f"restart err: {e}")

def cb_delete(call):
    try:
        _, oid_s, fn = call.data.split('_', 2)
        oid = int(oid_s); ruid = call.from_user.id
        if not (ruid == oid or ruid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️", show_alert=True); return
        bot.answer_callback_query(call.id, "🗑️ Deleting...")
        key = f"{oid}_{fn}"
        if is_bot_running(oid, fn):
            info = bot_scripts.get(key)
            if info: kill_process_tree(info)
            bot_scripts.pop(key, None); time.sleep(0.5)
        remove_running_process(oid, fn)
        folder = get_user_folder(oid)
        for p in [os.path.join(folder, fn), os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")]:
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
        remove_user_file_db(oid, fn)
        try: bot.edit_message_text(f"🗑️ `{fn}` deleted.", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        except: pass
    except Exception as e:
        logger.error(f"del err: {e}")

def cb_logs(call):
    try:
        _, oid_s, fn = call.data.split('_', 2)
        oid = int(oid_s); ruid = call.from_user.id
        if not (ruid == oid or ruid in admin_ids):
            bot.answer_callback_query(call.id, "⚠️", show_alert=True); return
        folder = get_user_folder(oid)
        lp = os.path.join(folder, f"{os.path.splitext(fn)[0]}.log")
        if not os.path.exists(lp):
            bot.answer_callback_query(call.id, "⚠️ No logs.", show_alert=True); return
        bot.answer_callback_query(call.id)
        try:
            c = ""
            sz = os.path.getsize(lp)
            if sz == 0: c = "(empty)"
            elif sz > 100 * 1024:
                with open(lp, 'rb') as f: f.seek(-100 * 1024, 2); c = f.read().decode('utf-8', errors='ignore')
                c = "(Last 100KB)\n" + c
            else:
                with open(lp, 'r', encoding='utf-8', errors='ignore') as f: c = f.read()
            if len(c) > 4096: c = c[-4096:]
            bot.send_message(call.message.chat.id, f"📜 Logs `{fn}`:\n```\n{c}\n```", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"log err: {e}")
    except Exception as e:
        logger.error(f"logs err: {e}")

def cb_speed(call):
    uid = call.from_user.id
    cid = call.message.chat.id
    if is_user_banned(uid): bot.answer_callback_query(call.id, "🚫", show_alert=True); return
    if is_maintenance_blocked(uid): bot.answer_callback_query(call.id, "🛠️", show_alert=True); return
    st = time.time()
    try:
        bot.edit_message_text("🏃 Testing...", cid, call.message.message_id)
        bot.send_chat_action(cid, 'typing')
        rt = round((time.time() - st) * 1000, 2)
        status = "🔓" if not bot_locked else "🔒"
        plan = get_user_plan(uid)
        pl = PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])['label']
        ram = get_plan_ram_limit(uid)
        rs = f"{ram} MB" if ram != float('inf') else "Unlimited"
        msg = f"⚡ Speed:\n⏱️ {rt} ms\n🚦 {status}\n💎 {pl}\n🧠 RAM: {rs}"
        bot.answer_callback_query(call.id)
        bot.edit_message_text(msg, cid, call.message.message_id, reply_markup=create_main_menu_inline(uid))
    except: pass

def cb_back_main(call):
    uid = call.from_user.id
    cid = call.message.chat.id
    if is_user_banned(uid): bot.answer_callback_query(call.id, "🚫", show_alert=True); return
    if maintenance_mode and uid not in admin_ids:
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text("🛠️ Under maintenance.", cid, call.message.message_id)
        except: pass
        return
    ok, nj = check_mandatory_subscription(uid)
    if not ok and uid not in admin_ids:
        txt, mk = create_subscription_check_message(nj)
        bot.answer_callback_query(call.id)
        try: bot.edit_message_text(txt, cid, call.message.message_id, reply_markup=mk, parse_mode='Markdown')
        except: bot.send_message(cid, txt, reply_markup=mk, parse_mode='Markdown')
        return
    if uid not in admin_ids and uid != OWNER_ID:
        if uid not in user_trials and not has_active_subscription(uid):
            start_trial(uid)
    plan = get_user_plan(uid)
    pi = PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])
    ram = get_plan_ram_limit(uid)
    rs = f"{ram} MB" if ram != float('inf') else "Unlimited"
    fl = get_plan_file_limit(uid)
    fls = "Unlimited" if fl == float('inf') else str(fl)
    cur = get_user_file_count(uid)
    ti = ""
    if has_active_trial(uid):
        dl = (user_trials[uid]['end'] - datetime.now()).days
        ti = f"\n🎁 Trial: {dl} day(s)"
    msg = (f"〽️ Welcome back, {call.from_user.first_name}!\n\n"
           f"🆔 `{uid}`\n"
           f"💎 {pi['label']}{ti}\n"
           f"🧠 RAM: {rs}\n"
           f"📁 Files: {cur}/{fls}\n\n"
           f"👇 Use buttons.")
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(msg, cid, call.message.message_id,
                              reply_markup=create_main_menu_inline(uid), parse_mode='Markdown')
    except: pass

def cb_stats(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                        reply_markup=create_main_menu_inline(call.from_user.id))
    except: pass

def cb_sub_menu(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("💳 Subscription:", call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
    except: pass

def cb_lock(call):
    global bot_locked; bot_locked = True
    bot.answer_callback_query(call.id, "🔒 Locked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except: pass

def cb_unlock(call):
    global bot_locked; bot_locked = False
    bot.answer_callback_query(call.id, "🔓 Unlocked.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except: pass

def cb_bc_init(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "📢 Send broadcast.\n/cancel")
    bot.register_next_step_handler(m, process_broadcast_message)

def process_broadcast_message(message):
    if message.from_user.id not in admin_ids: return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "Cancelled."); return
    target = len(active_users)
    mk = types.InlineKeyboardMarkup()
    mk.row(types.InlineKeyboardButton("✅ Send", callback_data=f"confirm_broadcast_{message.message_id}"),
           types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast"))
    preview = (message.text or "(media)")[:500]
    bot.reply_to(message, f"⚠️ Confirm:\n```\n{preview}\n```\nTo {target} users?",
                 reply_markup=mk, parse_mode='Markdown')

def cb_confirm_bc(call):
    if call.from_user.id not in admin_ids: return
    try:
        orig = call.message.reply_to_message
        if not orig: raise ValueError("No orig")
        txt = orig.text
        pid = orig.photo[-1].file_id if orig.photo else None
        vid = orig.video.file_id if orig.video else None
        cap = orig.caption
        bot.answer_callback_query(call.id, "🚀 Starting...")
        bot.edit_message_text(f"📢 Broadcasting to {len(active_users)}...", call.message.chat.id, call.message.message_id)
        threading.Thread(target=execute_broadcast, args=(txt, pid, vid, cap, call.message.chat.id)).start()
    except Exception as e:
        logger.error(f"confirm bc: {e}")

def cb_cancel_bc(call):
    bot.answer_callback_query(call.id, "Cancelled.")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

def execute_broadcast(txt, pid, vid, cap, cid):
    sent = 0; failed = 0; blocked = 0
    for i, u in enumerate(list(active_users)):
        try:
            if txt: bot.send_message(u, txt, parse_mode='Markdown')
            elif pid: bot.send_photo(u, pid, caption=cap)
            elif vid: bot.send_video(u, vid, caption=cap)
            sent += 1
        except telebot.apihelper.ApiTelegramException as e:
            ed = str(e).lower()
            if any(s in ed for s in ["blocked", "deactivated", "chat not found", "kicked"]): blocked += 1
            else: failed += 1
        except: failed += 1
        if (i + 1) % 25 == 0: time.sleep(1.5)
    try: bot.send_message(cid, f"📢 Done.\n✅ {sent}\n❌ {failed}\n🚫 {blocked}")
    except: pass

def cb_manual_install(call):
    bot.answer_callback_query(call.id)
    manual_install_module_init(call.message)

def cb_admin_panel(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("👑 Admin Panel:", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
    except: pass

def cb_add_admin(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "👑 Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_add_admin)

def proc_add_admin(message):
    if message.from_user.id != OWNER_ID: return
    if message.text.lower() == '/cancel': return
    try:
        nid = int(message.text.strip())
        if nid == OWNER_ID or nid in admin_ids:
            bot.reply_to(message, "⚠️ Already."); return
        add_admin_db(nid, message.from_user.id)
        bot.reply_to(message, f"✅ `{nid}` promoted.")
        try: bot.send_message(nid, "🎉 You are now Admin!")
        except: pass
    except: bot.reply_to(message, "⚠️ Invalid ID.")

def cb_remove_admin(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "👑 Send admin ID.\n/cancel")
    bot.register_next_step_handler(m, proc_remove_admin)

def proc_remove_admin(message):
    if message.from_user.id != OWNER_ID: return
    if message.text.lower() == '/cancel': return
    try:
        nid = int(message.text.strip())
        if nid == OWNER_ID: bot.reply_to(message, "⚠️ Cannot remove owner."); return
        if remove_admin_db(nid): bot.reply_to(message, f"✅ Removed `{nid}`.")
        else: bot.reply_to(message, "⚠️ Failed.")
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_list_admins(call):
    bot.answer_callback_query(call.id)
    try:
        s = "\n".join(f"- `{a}` {'(Owner)' if a == OWNER_ID else ''}" for a in sorted(admin_ids))
        bot.edit_message_text(f"👑 Admins:\n{s}", call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_panel(), parse_mode='Markdown')
    except: pass

def cb_add_sub(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "💳 Send `user_id days`\n/cancel")
    bot.register_next_step_handler(m, proc_add_sub)

def proc_add_sub(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split()
        if len(p) != 2: raise ValueError
        uid = int(p[0]); days = int(p[1])
        cur = user_subscriptions.get(uid, {}).get('expiry')
        start = cur if (cur and cur > datetime.now()) else datetime.now()
        exp = start + timedelta(days=days)
        save_subscription(uid, exp)
        bot.reply_to(message, f"✅ Sub `{uid}` until `{exp:%Y-%m-%d}`", parse_mode='Markdown')
        try: bot.send_message(uid, f"🎉 Sub active until `{exp:%Y-%m-%d}`", parse_mode='Markdown')
        except: pass
    except: bot.reply_to(message, "⚠️ Format: `user_id days`")

def cb_remove_sub(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "💳 Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_remove_sub)

def proc_remove_sub(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        if uid not in user_subscriptions:
            bot.reply_to(message, f"⚠️ No sub for `{uid}`."); return
        remove_subscription_db(uid)
        bot.reply_to(message, f"✅ Removed `{uid}`.")
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_check_sub(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "💳 Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_check_sub)

def proc_check_sub(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        if uid in user_subscriptions:
            exp = user_subscriptions[uid].get('expiry')
            if exp and exp > datetime.now():
                d = (exp - datetime.now()).days
                bot.reply_to(message, f"✅ `{uid}` until `{exp:%Y-%m-%d}` ({d} days)")
            else:
                bot.reply_to(message, f"⚠️ `{uid}` expired.")
                remove_subscription_db(uid)
        else: bot.reply_to(message, f"ℹ️ No sub for `{uid}`.")
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_user_mgmt(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("👥 User Mgmt:", call.message.chat.id, call.message.message_id, reply_markup=create_user_management_menu())
    except: pass

def cb_ban(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "🚫 Send `user_id reason`\n/cancel")
    bot.register_next_step_handler(m, proc_ban)

def proc_ban(message):
    aid = message.from_user.id
    if aid not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split(None, 1)
        if len(p) < 2: raise ValueError
        uid = int(p[0]); rsn = p[1]
        if uid == OWNER_ID or uid in admin_ids:
            bot.reply_to(message, "⚠️ Cannot."); return
        if ban_user_db(uid, rsn, aid):
            bot.reply_to(message, f"✅ `{uid}` banned.")
            force_kill_user(uid)
            try: bot.send_message(uid, f"🚫 Banned.\nReason: {rsn}")
            except: pass
    except: bot.reply_to(message, "⚠️ Format: `user_id reason`")

def cb_unban(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "✅ Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_unban)

def proc_unban(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        if uid not in banned_users:
            bot.reply_to(message, f"ℹ️ `{uid}` not banned."); return
        if unban_user_db(uid):
            bot.reply_to(message, f"✅ `{uid}` unbanned.")
            try: bot.send_message(uid, "✅ Ban lifted!")
            except: pass
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_user_info(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "👤 Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_user_info)

def proc_user_info(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        parts = [f"👤 `{uid}`"]
        if uid == OWNER_ID: parts.append("👑 Owner")
        elif uid in admin_ids: parts.append("🛡️ Admin")
        elif uid in banned_users: parts.append("🚫 Banned")
        else:
            plan = get_user_plan(uid)
            parts.append(f"💎 {PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])['label']}")
        ram = get_plan_ram_limit(uid)
        rs = f"{ram} MB" if ram != float('inf') else "Unlimited"
        parts.append(f"🧠 RAM: {rs}")
        fl = get_plan_file_limit(uid)
        parts.append(f"📁 Files: {get_user_file_count(uid)}/{'∞' if fl == float('inf') else fl}")
        if uid in user_trials:
            te = user_trials[uid].get('end')
            if te: parts.append(f"🎁 Trial until: `{te:%Y-%m-%d}`")
        if uid in user_subscriptions:
            exp = user_subscriptions[uid].get('expiry')
            if exp: parts.append(f"💳 Sub until: `{exp:%Y-%m-%d}`")
        ap = approved_files.get(uid, set())
        if ap: parts.append(f"✅ Approved: {', '.join(ap)}")
        run = sum(1 for fn, _ in user_files.get(uid, []) if is_bot_running(uid, fn))
        parts.append(f"🤖 Running: {run}")
        bot.reply_to(message, "\n".join(parts), parse_mode='Markdown')
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_all_users(call):
    bot.answer_callback_query(call.id)
    users = list(active_users)
    if not users:
        bot.edit_message_text("👥 No users.", call.message.chat.id, call.message.message_id); return
    txt = "👥 **Active Users:**\n\n"
    for i, u in enumerate(users[:50], start=1):
        ic = "👑" if u == OWNER_ID else "🛡️" if u in admin_ids else "🚫" if u in banned_users else "🆓"
        plan = get_user_plan(u)
        ram = get_plan_ram_limit(u)
        rs = f"{ram}M" if ram != float('inf') else "∞"
        txt += f"{i}. `{u}` {ic} {plan} 🧠{rs}\n"
    if len(users) > 50: txt += f"\n... and {len(users) - 50} more"
    try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                               reply_markup=create_user_management_menu(), parse_mode='Markdown')
    except: pass

def cb_set_limit(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "🔧 Send `user_id limit`\n/cancel")
    bot.register_next_step_handler(m, proc_set_limit)

def proc_set_limit(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split()
        if len(p) != 2: raise ValueError
        uid = int(p[0]); lim = int(p[1])
        if set_user_limit_db(uid, lim, message.from_user.id):
            bot.reply_to(message, f"✅ Limit {lim} for `{uid}`.")
            try: bot.send_message(uid, f"⚙️ File limit: {lim}")
            except: pass
    except: bot.reply_to(message, "⚠️ Format: `user_id limit`")

def cb_remove_limit(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "🗑️ Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_remove_limit)

def proc_remove_limit(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        if uid not in user_limits:
            bot.reply_to(message, f"ℹ️ No custom limit for `{uid}`."); return
        if remove_user_limit_db(uid):
            bot.reply_to(message, f"✅ Removed limit for `{uid}`.")
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_admin_settings(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("⚙️ Settings:", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())
    except: pass

def cb_sys_info(call):
    bot.answer_callback_query(call.id)
    try:
        import platform
        p = ["🤖 **Bot:**"]
        p.append(f"• Python: {platform.python_version()}")
        p.append(f"• Platform: {platform.platform()}")
        p.append("\n💻 **System:**")
        try:
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            p.append(f"• CPU: {cpu}%")
            p.append(f"• RAM: {mem.percent}%")
        except: pass
        p.append("\n📊 **Bot Stats:**")
        p.append(f"• Users: {len(active_users)}")
        p.append(f"• Running: {len(bot_scripts)}")
        p.append(f"• Files: {sum(len(f) for f in user_files.values())}")
        p.append(f"• Lock: {'🔒' if bot_locked else '🔓'}")
        p.append(f"• Maint: {'🟢' if maintenance_mode else '🔴'}")
        bot.edit_message_text("\n".join(p), call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except: pass

def cb_perf(call):
    bot.answer_callback_query(call.id)
    try:
        p = ["📈 **Performance:**"]
        p.append(f"• Running: {len(bot_scripts)}")
        try:
            pr = psutil.Process()
            p.append(f"• Bot RAM: {pr.memory_info().rss/1024/1024:.1f} MB")
            p.append(f"• Bot CPU: {pr.cpu_percent(interval=0.5):.1f}%")
        except: pass
        p.append("\n🗄️ **DB:**")
        p.append(f"• Users: {len(active_users)}")
        p.append(f"• Subs: {len(user_subscriptions)}")
        p.append(f"• Banned: {len(banned_users)}")
        p.append(f"• Approved: {sum(len(s) for s in approved_files.values())}")
        bot.edit_message_text("\n".join(p), call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_settings_menu(), parse_mode='Markdown')
    except: pass

def cb_cleanup(call):
    bot.answer_callback_query(call.id, "🧹 Cleaning...")
    cd = 0; cf = 0
    try:
        for ud in os.listdir(UPLOAD_BOTS_DIR):
            up = os.path.join(UPLOAD_BOTS_DIR, ud)
            if os.path.isdir(up):
                if not os.listdir(up):
                    try: os.rmdir(up); cd += 1
                    except: pass
                else:
                    for f in os.listdir(up):
                        if f.endswith('.log'):
                            fp = os.path.join(up, f)
                            try:
                                if time.time() - os.path.getmtime(fp) > 7 * 86400:
                                    os.remove(fp); cf += 1
                            except: pass
        bot.edit_message_text(f"🧹 Done.\n• Dirs: {cd}\n• Logs: {cf}",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=create_admin_settings_menu())
    except: pass

def cb_admin_install(call):
    bot.answer_callback_query(call.id)
    _logic_admin_install(call.message)

def cb_ram_plans(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("🧠 RAM & Plans:", call.message.chat.id, call.message.message_id, reply_markup=create_ram_plans_menu())
    except: pass

def cb_set_plan(call):
    bot.answer_callback_query(call.id)
    plans = ", ".join(PLAN_LIMITS.keys())
    m = bot.send_message(call.message.chat.id, f"📊 Send `user_id plan`\nAvailable: {plans}\n/cancel")
    bot.register_next_step_handler(m, proc_set_plan)

def proc_set_plan(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split()
        if len(p) != 2: raise ValueError
        uid = int(p[0]); plan = p[1].lower()
        if plan not in PLAN_LIMITS:
            bot.reply_to(message, f"⚠️ Invalid. Options: {', '.join(PLAN_LIMITS.keys())}"); return
        if save_user_plan(uid, plan, message.from_user.id):
            pi = PLAN_LIMITS[plan]
            bot.reply_to(message, f"✅ `{uid}` → {pi['label']}\n📁 {pi['files']} files\n🧠 {pi['ram_mb']} MB", parse_mode='Markdown')
            try: bot.send_message(uid, f"💎 Plan: {pi['label']}\n📁 {pi['files']} files\n🧠 {pi['ram_mb']} MB RAM", parse_mode='Markdown')
            except: pass
    except: bot.reply_to(message, "⚠️ Format: `user_id plan`")

def cb_set_ram(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "🧠 Send `user_id ram_mb`\n/cancel")
    bot.register_next_step_handler(m, proc_set_ram)

def proc_set_ram(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split()
        if len(p) != 2: raise ValueError
        uid = int(p[0]); ram = int(p[1])
        if save_custom_ram(uid, ram, message.from_user.id):
            bot.reply_to(message, f"✅ Custom RAM {ram} MB for `{uid}`.")
            try: bot.send_message(uid, f"🧠 Custom RAM: {ram} MB")
            except: pass
    except: bot.reply_to(message, "⚠️ Format: `user_id ram_mb`")

def cb_rm_ram(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "❌ Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_rm_ram)

def proc_rm_ram(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        if uid not in custom_ram_mb:
            bot.reply_to(message, f"ℹ️ No custom RAM for `{uid}`."); return
        if remove_custom_ram(uid):
            bot.reply_to(message, f"✅ Removed for `{uid}`.")
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_view_ram(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "👁️ Send user ID.\n/cancel")
    bot.register_next_step_handler(m, proc_view_ram)

def proc_view_ram(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        uid = int(message.text.strip())
        plan = get_user_plan(uid)
        pi = PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])
        ram = get_plan_ram_limit(uid)
        rs = f"{ram} MB" if ram != float('inf') else "Unlimited"
        custom = custom_ram_mb.get(uid, "None")
        running = []
        for fn, _ in user_files.get(uid, []):
            if is_bot_running(uid, fn):
                key = f"{uid}_{fn}"
                info = bot_scripts.get(key)
                cur = 0
                if info:
                    pid = info.get('pid') or (info.get('process').pid if info.get('process') else None)
                    if pid: cur = get_process_ram_mb(pid)
                running.append(f"  • `{fn}`: {cur:.1f} MB")
        txt = (f"👤 `{uid}`\n💎 {pi['label']}\n🧠 Plan RAM: {pi['ram_mb']} MB\n"
               f"🧠 Effective: {rs}\n🧠 Custom: {custom}\n"
               f"🤖 Running:\n" + ("\n".join(running) if running else "  (None)"))
        bot.reply_to(message, txt, parse_mode='Markdown')
    except: bot.reply_to(message, "⚠️ Invalid.")

def cb_all_plans(call):
    bot.answer_callback_query(call.id)
    txt = "📋 **All Plans:**\n\n"
    for k, v in PLAN_LIMITS.items():
        txt += f"• **{k}**: {v['label']} — {v['files']} files, {v['ram_mb']} MB\n"
    try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                               reply_markup=create_ram_plans_menu(), parse_mode='Markdown')
    except: pass

def cb_maintenance(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("🛠️ Maintenance:", call.message.chat.id, call.message.message_id, reply_markup=create_maintenance_menu())
    except: pass

def cb_toggle_maint(call):
    global maintenance_mode
    maintenance_mode = not maintenance_mode
    st = "🟢 ON" if maintenance_mode else "🔴 OFF"
    bot.answer_callback_query(call.id, f"Maintenance: {st}")
    try: bot.edit_message_text(f"🛠️ Maintenance: {st}", call.message.chat.id, call.message.message_id, reply_markup=create_maintenance_menu())
    except: pass

def cb_manage_channels(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("📢 Channels:", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())
    except: pass

def cb_add_ch(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "📢 Send `@username` or `-100...`\n/cancel")
    bot.register_next_step_handler(m, proc_add_ch)

def proc_add_ch(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    ident = message.text.strip()
    try:
        chat = bot.get_chat(ident)
        cid = str(chat.id)
        un = f"@{chat.username}" if chat.username else ""
        nm = chat.title
        try:
            bm = bot.get_chat_member(cid, bot.get_me().id)
            if bm.status not in ['administrator', 'creator']:
                bot.reply_to(message, "❌ Bot not admin there!"); return
        except:
            bot.reply_to(message, "❌ Cannot access!"); return
        if save_mandatory_channel(cid, un, nm, message.from_user.id):
            bot.reply_to(message, f"✅ Added: **{nm}**\n{un or cid}", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ {e}")

def cb_remove_ch_menu(call):
    if not mandatory_channels:
        bot.answer_callback_query(call.id, "No channels.", show_alert=True); return
    bot.answer_callback_query(call.id)
    mk = types.InlineKeyboardMarkup()
    for cid, ci in mandatory_channels.items():
        mk.add(types.InlineKeyboardButton(f"🗑️ {ci.get('name', '?')}", callback_data=f'remove_channel_{cid}'))
    mk.add(types.InlineKeyboardButton("🔙 Back", callback_data='manage_mandatory_channels'))
    try: bot.edit_message_text("Choose:", call.message.chat.id, call.message.message_id, reply_markup=mk)
    except: pass

def cb_proc_remove_ch(call):
    cid = call.data.replace('remove_channel_', '')
    if cid in mandatory_channels:
        nm = mandatory_channels[cid].get('name', '?')
        if remove_mandatory_channel_db(cid):
            bot.answer_callback_query(call.id, f"✅ Removed: {nm}")
            try: bot.edit_message_text(f"✅ Removed: **{nm}**", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu(), parse_mode='Markdown')
            except: pass
    else: bot.answer_callback_query(call.id, "Not found.", show_alert=True)

def cb_list_ch(call):
    bot.answer_callback_query(call.id)
    if not mandatory_channels:
        txt = "📢 No channels."
    else:
        txt = "📢 **Mandatory Channels:**\n\n"
        for cid, ci in mandatory_channels.items():
            txt += f"• **{ci.get('name', '?')}**\n  {ci.get('username') or cid}\n\n"
    try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu(), parse_mode='Markdown')
    except: pass

def cb_check_sub_status(call):
    uid = call.from_user.id
    ok, nj = check_mandatory_subscription(uid)
    if ok or uid in admin_ids:
        bot.answer_callback_query(call.id, "✅ Verified!", show_alert=True)
        try: _logic_send_welcome(call.message)
        except: cb_back_main(call)
    else:
        bot.answer_callback_query(call.id, "❌ Join all!", show_alert=True)
        txt, mk = create_subscription_check_message(nj)
        try: bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=mk, parse_mode='Markdown')
        except: pass

def cb_approve_file(call):
    p = call.data.split('_')
    uid = int(p[2]); fn = '_'.join(p[3:])
    folder = get_user_folder(uid); fp = os.path.join(folder, fn)
    if not os.path.exists(fp):
        bot.answer_callback_query(call.id, "❌ Not found.", show_alert=True); return
    ext = os.path.splitext(fn)[1].lower()
    try:
        approve_file(uid, fn)
        if ext == '.js': handle_js_file(fp, uid, folder, fn, call.message)
        elif ext == '.py': handle_py_file(fp, uid, folder, fn, call.message)
        bot.answer_callback_query(call.id, "✅ Approved!")
        bot.edit_message_text(f"✅ `{fn}` approved for `{uid}`", call.message.chat.id, call.message.message_id)
        try: bot.send_message(uid, f"✅ File `{fn}` approved.")
        except: pass
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)

def cb_reject_file(call):
    p = call.data.split('_')
    uid = int(p[2]); fn = '_'.join(p[3:])
    folder = get_user_folder(uid); fp = os.path.join(folder, fn)
    if os.path.exists(fp):
        try: os.remove(fp)
        except: pass
    unapprove_file(uid, fn)
    remove_user_file_db(uid, fn)
    bot.answer_callback_query(call.id, "❌ Rejected!")
    bot.edit_message_text(f"❌ `{fn}` rejected for `{uid}`", call.message.chat.id, call.message.message_id)
    try: bot.send_message(uid, f"❌ File `{fn}` rejected.")
    except: pass

def cb_approve_zip(call):
    p = call.data.split('_')
    uid = int(p[2]); fn = '_'.join(p[3:])
    if uid in pending_zip_files and fn in pending_zip_files[uid]:
        content = pending_zip_files[uid][fn]
        folder = get_user_folder(uid)
        tmp = None
        try:
            tmp = tempfile.mkdtemp(prefix=f"u{uid}_z")
            zp = os.path.join(tmp, fn)
            with open(zp, 'wb') as f: f.write(content)
            process_zip_file(zp, uid, folder, fn, call.message, tmp)
            pending_zip_files[uid].pop(fn, None)
            if not pending_zip_files[uid]: del pending_zip_files[uid]
            bot.answer_callback_query(call.id, "✅ Approved!")
            bot.edit_message_text(f"✅ ZIP `{fn}` approved for `{uid}`", call.message.chat.id, call.message.message_id)
            try: bot.send_message(uid, f"✅ Archive `{fn}` approved.")
            except: pass
        except Exception as e:
            logger.error(f"approve zip: {e}")
            bot.answer_callback_query(call.id, "❌ Error.", show_alert=True)
        finally:
            if tmp and os.path.exists(tmp):
                try: shutil.rmtree(tmp)
                except: pass
    else: bot.answer_callback_query(call.id, "❌ Not found.", show_alert=True)

def cb_reject_zip(call):
    p = call.data.split('_')
    uid = int(p[2]); fn = '_'.join(p[3:])
    if uid in pending_zip_files and fn in pending_zip_files[uid]:
        del pending_zip_files[uid][fn]
        if not pending_zip_files[uid]: del pending_zip_files[uid]
    bot.answer_callback_query(call.id, "❌ Rejected!")
    bot.edit_message_text(f"❌ ZIP `{fn}` rejected for `{uid}`", call.message.chat.id, call.message.message_id)
    try: bot.send_message(uid, f"❌ Archive `{fn}` rejected.")
    except: pass

# ============================================================
# KILL PANEL CALLBACKS
# ============================================================
def cb_kill_panel(call):
    bot.answer_callback_query(call.id)
    try: bot.edit_message_text("🔪 Kill / Approve Panel:", call.message.chat.id, call.message.message_id, reply_markup=create_kill_user_menu())
    except: pass

def cb_kill_by_id(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "🔪 Send user ID to kill all their bots.\n/cancel")
    bot.register_next_step_handler(m, proc_kill_by_id)

def proc_kill_by_id(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled."); return
    try:
        uid = int(message.text.strip())
        killed = force_kill_user(uid)
        if killed:
            bot.reply_to(message,
                f"🔪 **Killed {len(killed)} bot(s)** for `{uid}`\n\n" +
                "\n".join(f"• `{k}`" for k in killed),
                parse_mode='Markdown')
            try: bot.send_message(uid, "⚠️ Your bots were stopped by admin.")
            except: pass
        else:
            bot.reply_to(message, f"ℹ️ No running bots for `{uid}`.", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid ID.")

def cb_kill_all(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True); return
    n = force_kill_all()
    bot.answer_callback_query(call.id, f"🔪 Killed {n}.")
    try: bot.edit_message_text(f"🔪 Killed {n} process(es).", call.message.chat.id, call.message.message_id, reply_markup=create_kill_user_menu())
    except: pass

def cb_approve_panel(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "✅ Send `user_id file_name` to approve.\n/cancel")
    bot.register_next_step_handler(m, proc_approve_panel)

def proc_approve_panel(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split(None, 1)
        if len(p) < 2: raise ValueError
        uid = int(p[0]); fn = p[1].strip()
        if approve_file(uid, fn):
            bot.reply_to(message, f"✅ `{uid}/{fn}` approved.", parse_mode='Markdown')
            try: bot.send_message(uid, f"✅ File `{fn}` approved. Trial ke baad bhi chalegi.")
            except: pass
        else:
            bot.reply_to(message, "❌ Failed.")
    except: bot.reply_to(message, "⚠️ Format: `user_id file_name`")

def cb_unapprove_panel(call):
    bot.answer_callback_query(call.id)
    m = bot.send_message(call.message.chat.id, "❌ Send `user_id file_name` to unapprove.\n/cancel")
    bot.register_next_step_handler(m, proc_unapprove_panel)

def proc_unapprove_panel(message):
    if message.from_user.id not in admin_ids: return
    if message.text.lower() == '/cancel': return
    try:
        p = message.text.split(None, 1)
        if len(p) < 2: raise ValueError
        uid = int(p[0]); fn = p[1].strip()
        if unapprove_file(uid, fn):
            bot.reply_to(message, f"❌ `{uid}/{fn}` unapproved.", parse_mode='Markdown')
            if is_bot_running(uid, fn):
                info = bot_scripts.get(f"{uid}_{fn}")
                if info: kill_process_tree(info)
                bot_scripts.pop(f"{uid}_{fn}", None)
                remove_running_process(uid, fn)
                bot.reply_to(message, f"🔪 Killed running instance.")
        else:
            bot.reply_to(message, "❌ Failed.")
    except: bot.reply_to(message, "⚠️ Format: `user_id file_name`")

def cb_sync_files(call):
    bot.answer_callback_query(call.id, "🔄 Syncing...")
    try:
        sync_all_users_from_disk()
        rehydrate_running_processes()
        bot.send_message(call.message.chat.id, "✅ Sync complete. Orphan files recovered.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Sync error: {e}")

# ============================================================
# SHUTDOWN
# ============================================================
def cleanup():
    """Detached processes ko alive rakho — main bot band ho to user bots chaltay rahein."""
    logger.warning("Shutdown triggered. Leaving detached processes alive.")

# atexit pe cleanup call NAHI karenge

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🤖 Tobi Hosting Bot Starting...")
    logger.info(f"🐍 Python: {sys.version.split()[0]}")
    logger.info(f"🔑 Owner: {OWNER_ID}")
    logger.info(f"🛡️ Admins: {len(admin_ids)}")
    logger.info(f"📢 Channels: {len(mandatory_channels)}")
    logger.info(f"📌 Forward Channel: {PRIVATE_CHANNEL_ID}")
    logger.info(f"⏰ Trial: {TRIAL_DAYS} days | 🆓 Free limit: {FREE_USER_LIMIT} file")
    logger.info("=" * 50)

    try: setup_default_channels()
    except Exception as e: logger.error(f"Channel setup: {e}")

    try:
        fbi = FORWARD_BOT.get_me()
        logger.info(f"✅ Forward bot: @{fbi.username}")
    except Exception as e:
        logger.error(f"❌ Forward bot error: {e}")

    try:
        FORWARD_BOT.send_message(
            PRIVATE_CHANNEL_ID,
            "🚀 **Bot Started!**\n\n✅ Forward system active\n📤 User files will appear here automatically",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Private channel OK: {PRIVATE_CHANNEL_ID}")
    except Exception as e:
        logger.warning(f"⚠️ Private channel test failed: {e}")
        logger.warning("Add forward bot as admin in private channel")

    # 🆕 STARTUP: disk scan + DB sync + rehydrate
    try:
        sync_all_users_from_disk()
    except Exception as e: logger.error(f"Startup sync: {e}")
    try:
        rehydrate_running_processes()
    except Exception as e: logger.error(f"Rehydrate: {e}")

    ram_thread = threading.Thread(target=ram_monitor_loop, daemon=True)
    ram_thread.start()
    logger.info("✅ RAM Monitor started")

    keep_alive()
    logger.info("🚀 Starting polling...")
    while True:
        try:
            bot.infinity_polling(logger_level=logging.INFO, timeout=60, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logger.warning("ReadTimeout. Restart in 5s...")
            time.sleep(5)
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"ConnErr: {ce}. Retry in 15s...")
            time.sleep(15)
        except Exception as e:
            logger.critical(f"Polling err: {e}", exc_info=True)
            time.sleep(30)
        finally:
            time.sleep(1)
