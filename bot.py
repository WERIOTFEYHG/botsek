"""
Telegram File Uploader Bot - v9.0 Professional
Aiogram 3.x | JSON Storage | Railway Ready
ON/OFF Toggle | Maintenance Mode | Smart Retry | Full Control
"""

import asyncio
import json
import os
import sys
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, FSInputFile, BotCommand,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv
import aiofiles

# ==================== CONFIG ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

USERS_FILE = "users.json"
FILES_FILE = "files.json"
ADMINS_FILE = "admins.json"
SETTINGS_FILE = "settings.json"
LOGS_FILE = "logs.json"

# ==================== LOGGER ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def safe_html(text: str) -> str:
    """Escape HTML special characters"""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_time(minutes: int) -> str:
    """Format minutes to readable Persian time"""
    if minutes == 0:
        return "خاموش"
    if minutes < 60:
        return f"{minutes} دقیقه"
    elif minutes < 1440:
        h = minutes // 60
        m = minutes % 60
        if m > 0:
            return f"{h} ساعت و {m} دقیقه"
        return f"{h} ساعت"
    else:
        d = minutes // 1440
        h = (minutes % 1440) // 60
        if h > 0:
            return f"{d} روز و {h} ساعت"
        return f"{d} روز"

def get_default_texts():
    """Get default texts for all bot messages"""
    return {
        "welcome_type": "text",
        "welcome_text": "👋 سلام! به ربات آپلود فایل خوش اومدی.",
        "welcome_media": "",
        "welcome_caption": "",
        
        "help_text": "📎 راهنمای ربات:\n\nبرای دریافت فایل، لینک را باز کنید.\nبرای آپلود، از پنل مدیریت استفاده کنید.",
        
        "force_join_text": "📢 **لطفاً ابتدا در چنل‌های زیر عضو شوید**\n\nپس از عضویت، دکمه بررسی را بزنید.",
        "force_join_success": "✅ **عضویت شما تایید شد!**\n\nحالا می‌تونید از ربات استفاده کنید.",
        "force_join_fail": "⚠️ **هنوز عضو نشدید!**\n\nلطفاً در چنل‌های زیر عضو شوید:",
        
        "password_text": "🔒 این فایل دارای رمز عبور است.\nلطفا رمز را وارد کنید:",
        "password_correct": "✅ رمز صحیح است. در حال ارسال فایل...",
        "password_wrong": "❌ رمز اشتباه است. دوباره تلاش کنید.",
        
        "banned_text": "🚫 شما مسدود شده‌اید.",
        "file_not_found": "❌ فایل پیدا نشد یا حذف شده است.",
        "file_deleted": "✅ فایل با موفقیت حذف شد.",
        
        "maintenance_text": "🔧 ربات در حال بروزرسانی ست\n\nلطفاً بعداً مراجعه کنید.",
        "maintenance_retry": "🔄 تلاش دوباره",
    }

# ==================== JSON MANAGER ====================
class JSONManager:
    def __init__(self):
        self.locks = {}
        for f in [USERS_FILE, FILES_FILE, ADMINS_FILE, SETTINGS_FILE, LOGS_FILE]:
            self.locks[f] = asyncio.Lock()

    def init_files(self):
        defaults = {
            USERS_FILE: {"users": {}},
            FILES_FILE: {"files": {}},
            ADMINS_FILE: {"admins": {}},
            SETTINGS_FILE: {
                "delete_timer": 300,
                "force_join": [],
                "log_channel": "",
                "bot_active": True,  # NEW: Bot ON/OFF toggle
                "texts": get_default_texts()
            },
            LOGS_FILE: {"logs": []}
        }
        for fn, data in defaults.items():
            if not os.path.exists(fn):
                with open(fn, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)

    async def _read(self, fn: str) -> Dict:
        async with self.locks[fn]:
            async with aiofiles.open(fn, 'r', encoding='utf-8') as f:
                return json.loads(await f.read())

    async def _write(self, fn: str, data: Dict):
        async with self.locks[fn]:
            async with aiofiles.open(fn, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))

    async def is_bot_active(self) -> bool:
        s = await self.get_settings()
        return s.get("bot_active", True)

    async def toggle_bot(self) -> bool:
        s = await self.get_settings()
        current = s.get("bot_active", True)
        s["bot_active"] = not current
        await self.update_setting("bot_active", s["bot_active"])
        return s["bot_active"]

    async def add_user(self, uid: int, data: Dict):
        d = await self._read(USERS_FILE)
        if str(uid) not in d["users"]:
            d["users"][str(uid)] = {
                "id": uid, "name": data.get("name", ""),
                "username": data.get("username", ""),
                "joined": datetime.now().isoformat(),
                "downloads": 0, "banned": False
            }
            await self._write(USERS_FILE, d)

    async def is_banned(self, uid: int) -> bool:
        d = await self._read(USERS_FILE)
        u = d["users"].get(str(uid), {})
        return u.get("banned", False)

    async def toggle_ban(self, uid: int) -> str:
        d = await self._read(USERS_FILE)
        if str(uid) in d["users"]:
            current = d["users"][str(uid)].get("banned", False)
            d["users"][str(uid)]["banned"] = not current
            await self._write(USERS_FILE, d)
            return "✅ آزاد شد" if current else "🚫 مسدود شد"
        return "کاربر پیدا نشد"

    async def is_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        return str(uid) in d["admins"] or uid == ADMIN_ID

    async def add_admin(self, uid: int, role: str = "admin"):
        d = await self._read(ADMINS_FILE)
        d["admins"][str(uid)] = {"role": role, "added": datetime.now().isoformat()}
        await self._write(ADMINS_FILE, d)

    async def remove_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        if str(uid) in d["admins"] and str(uid) != str(ADMIN_ID):
            del d["admins"][str(uid)]
            await self._write(ADMINS_FILE, d)
            return True
        return False

    async def get_admins(self) -> Dict:
        d = await self._read(ADMINS_FILE)
        return d["admins"]

    async def add_file(self, data: Dict) -> str:
        d = await self._read(FILES_FILE)
        fid = data["id"]
        d["files"][fid] = {
            "id": fid, "file_id": data["file_id"], "type": data["type"],
            "caption": data.get("caption", ""), "file_name": data.get("file_name", ""),
            "password": data.get("password", ""),
            "date": datetime.now().isoformat(), "downloads": 0, "admin": data["admin"]
        }
        await self._write(FILES_FILE, d)
        return fid

    async def get_file(self, fid: str) -> Optional[Dict]:
        d = await self._read(FILES_FILE)
        return d["files"].get(fid)

    async def get_all_files(self) -> Dict:
        d = await self._read(FILES_FILE)
        return d["files"]

    async def delete_file(self, fid: str) -> bool:
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            del d["files"][fid]
            await self._write(FILES_FILE, d)
            return True
        return False

    async def inc_download(self, fid: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            d["files"][fid]["downloads"] += 1
            await self._write(FILES_FILE, d)

    async def update_caption(self, fid: str, caption: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            d["files"][fid]["caption"] = caption
            await self._write(FILES_FILE, d)

    async def update_password(self, fid: str, password: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            d["files"][fid]["password"] = password
            await self._write(FILES_FILE, d)

    async def get_stats(self) -> Dict:
        users = await self._read(USERS_FILE)
        files = await self._read(FILES_FILE)
        return {
            "users": len(users["users"]),
            "files": len(files["files"]),
            "downloads": sum(f["downloads"] for f in files["files"].values())
        }

    async def get_all_users(self) -> Dict:
        d = await self._read(USERS_FILE)
        return d["users"]

    async def add_log(self, action: str, uid: int, detail: str = ""):
        d = await self._read(LOGS_FILE)
        d["logs"].append({
            "time": datetime.now().isoformat(), "action": action,
            "admin": uid, "detail": detail
        })
        if len(d["logs"]) > 500:
            d["logs"] = d["logs"][-500:]
        await self._write(LOGS_FILE, d)

    async def get_logs(self, limit: int = 20) -> List:
        d = await self._read(LOGS_FILE)
        return d["logs"][-limit:]

    async def get_settings(self) -> Dict:
        return await self._read(SETTINGS_FILE)

    async def update_setting(self, key: str, val: Any):
        d = await self._read(SETTINGS_FILE)
        d[key] = val
        await self._write(SETTINGS_FILE, d)

    async def get_texts(self) -> Dict:
        s = await self.get_settings()
        return s.get("texts", get_default_texts())

    async def update_text(self, key: str, val: Any):
        s = await self.get_settings()
        texts = s.get("texts", get_default_texts())
        texts[key] = val
        await self.update_setting("texts", texts)

    async def add_force_join(self, channel: str) -> bool:
        s = await self.get_settings()
        channels = s.get("force_join", [])
        if channel not in channels:
            channels.append(channel)
            await self.update_setting("force_join", channels)
            return True
        return False

    async def remove_force_join(self, channel: str) -> bool:
        s = await self.get_settings()
        channels = s.get("force_join", [])
        if channel in channels:
            channels.remove(channel)
            await self.update_setting("force_join", channels)
            return True
        return False

db = JSONManager()

# ==================== KEYBOARDS ====================

def admin_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📤 آپلود فایل جدید")],
            [KeyboardButton(text="📂 مدیریت فایل‌ها"), KeyboardButton(text="📊 آمار ربات")],
            [KeyboardButton(text="📢 ارسال همگانی"), KeyboardButton(text="⚙️ تنظیمات")],
            [KeyboardButton(text="👥 کاربران"), KeyboardButton(text="👮 ادمین‌ها")],
            [KeyboardButton(text="📜 گزارشات"), KeyboardButton(text="🔗 لینک‌های فعال")],
            [KeyboardButton(text="💾 پشتیبان‌گیری")]
        ],
        resize_keyboard=True,
        input_field_placeholder="👑 یک گزینه انتخاب کنید...",
        selective=True
    )

def user_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 دانلود فایل")],
            [KeyboardButton(text="📊 آمار من"), KeyboardButton(text="ℹ️ راهنما")]
        ],
        resize_keyboard=True,
        input_field_placeholder="👋 یک گزینه انتخاب کنید...",
        selective=True
    )

def back_inline(cb: str = "panel"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]
    ])

def skip_back_inline(back_cb: str = "panel"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ رد کردن", callback_data="skip_caption")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]
    ])

def skip_pass_inline(back_cb: str = "panel"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ بدون رمز", callback_data="skip_password")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]
    ])

def maintenance_kb(file_id: str = ""):
    """Keyboard for maintenance mode - retry button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 تلاش دوباره", callback_data=f"retry_{file_id}")]
    ])

def files_kb(files: Dict, page: int = 0):
    b = InlineKeyboardBuilder()
    items = list(files.items())
    per_page = 6
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    
    for fid, f in items[start:start+per_page]:
        cap = f.get("caption", "بدون کپشن")[:25]
        dn = f.get("downloads", 0)
        lock = "🔒" if f.get("password") else ""
        icon = type_icons.get(f.get("type", "document"), "📁")
        b.row(InlineKeyboardButton(text=f"{icon} {lock} {cap} | 📥{dn}", callback_data=f"file_{fid}"))
    
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"files_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📋 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"files_pg_{page+1}"))
        b.row(*nav)
    
    b.row(InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel"))
    return b.as_markup()

def file_actions_kb(fid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دریافت فایل", callback_data=f"dl_{fid}"),
         InlineKeyboardButton(text="🔗 کپی لینک", callback_data=f"link_{fid}")],
        [InlineKeyboardButton(text="✏️ ویرایش کپشن", callback_data=f"editcap_{fid}"),
         InlineKeyboardButton(text="🔒 تغییر رمز", callback_data=f"setpass_{fid}")],
        [InlineKeyboardButton(text="🗑 حذف فایل", callback_data=f"del_{fid}")],
        [InlineKeyboardButton(text="🔙 لیست فایل‌ها", callback_data="files_list")]
    ])

def confirm_delete_kb(fid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله حذف شود", callback_data=f"delyes_{fid}"),
         InlineKeyboardButton(text="❌ منصرف شدم", callback_data=f"file_{fid}")]
    ])

def users_kb(users: Dict, page: int = 0):
    b = InlineKeyboardBuilder()
    items = list(users.items())
    per_page = 6
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    
    for uid, u in items[start:start+per_page]:
        name = u.get("name", "کاربر")[:20]
        ban = "🚫" if u.get("banned") else "✅"
        b.row(InlineKeyboardButton(text=f"{ban} {name} | 📥{u.get('downloads',0)}", callback_data=f"user_{uid}"))
    
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"users_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"users_pg_{page+1}"))
        b.row(*nav)
    
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    return b.as_markup()

def user_actions_kb(uid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 تغییر وضعیت مسدودیت", callback_data=f"ban_{uid}")],
        [InlineKeyboardButton(text="🔙 لیست کاربران", callback_data="users_list")]
    ])

def admins_kb(admins: Dict):
    b = InlineKeyboardBuilder()
    for aid, a in admins.items():
        icon = "👑" if a['role'] == 'owner' else "👮"
        b.row(InlineKeyboardButton(text=f"{icon} {aid} - {a['role']}", callback_data=f"admin_{aid}"))
    b.row(InlineKeyboardButton(text="➕ افزودن ادمین", callback_data="add_admin"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    return b.as_markup()

def settings_kb(settings: Dict):
    """Settings menu with Bot ON/OFF toggle"""
    timer_val = settings.get("delete_timer", 300)
    if timer_val == 0:
        timer_text = "⏱ تایمر حذف پست: خاموش"
    else:
        timer_text = f"⏱ تایمر حذف پست: {format_time(timer_val // 60)}"
    
    fj = settings.get("force_join", [])
    fj_count = len(fj)
    
    # Bot status button
    bot_active = settings.get("bot_active", True)
    if bot_active:
        bot_btn_text = "🟢 ربات فعال است"
        bot_btn_callback = "toggle_bot"
    else:
        bot_btn_text = "🔴 ربات خاموش است"
        bot_btn_callback = "toggle_bot"
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=bot_btn_text, callback_data=bot_btn_callback))
    b.row(InlineKeyboardButton(text=f"🔗 عضویت اجباری ({fj_count})", callback_data="set_forcejoin"))
    b.row(InlineKeyboardButton(text="📝 ویرایش متن‌های ربات", callback_data="edit_texts"))
    b.row(InlineKeyboardButton(text="📢 کانال گزارش", callback_data="set_logchan"))
    b.row(InlineKeyboardButton(text=timer_text, callback_data="set_timer"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel"))
    return b.as_markup()

def timer_settings_kb(settings: Dict):
    timer_val = settings.get("delete_timer", 300)
    b = InlineKeyboardBuilder()
    
    if timer_val == 0:
        b.row(InlineKeyboardButton(text="⏱ وضعیت: خاموش 🔴", callback_data="noop"))
        b.row(InlineKeyboardButton(text="🔵 روشن کردن تایمر", callback_data="timer_on"))
    else:
        b.row(InlineKeyboardButton(text=f"⏱ وضعیت: {format_time(timer_val // 60)} 🟢", callback_data="noop"))
        b.row(InlineKeyboardButton(text="🔴 خاموش کردن تایمر", callback_data="timer_off"))
    
    b.row(InlineKeyboardButton(text="⏰ تنظیم زمان جدید", callback_data="timer_set"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به تنظیمات", callback_data="settings"))
    return b.as_markup()

def back_to_timer_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به تنظیمات تایمر", callback_data="set_timer")]
    ])

def texts_editor_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👋 پیام خوشامد (قابل تنظیم با مدیا)", callback_data="edit_welcome"))
    b.row(InlineKeyboardButton(text="📎 متن راهنما", callback_data="edit_help"))
    b.row(InlineKeyboardButton(text="📢 متن عضویت اجباری", callback_data="edit_forcejoin"))
    b.row(InlineKeyboardButton(text="✅ متن تایید عضویت", callback_data="edit_forcejoin_ok"))
    b.row(InlineKeyboardButton(text="⚠️ متن عدم عضویت", callback_data="edit_forcejoin_fail"))
    b.row(InlineKeyboardButton(text="🔒 متن درخواست رمز", callback_data="edit_password"))
    b.row(InlineKeyboardButton(text="🚫 متن کاربر مسدود", callback_data="edit_banned"))
    b.row(InlineKeyboardButton(text="🔧 متن بروزرسانی (Maintenance)", callback_data="edit_maintenance"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به تنظیمات", callback_data="settings"))
    return b.as_markup()

def welcome_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 متن ساده", callback_data="wel_type_text")],
        [InlineKeyboardButton(text="🖼 عکس", callback_data="wel_type_photo"),
         InlineKeyboardButton(text="🎬 ویدیو", callback_data="wel_type_video")],
        [InlineKeyboardButton(text="✨ گیف", callback_data="wel_type_animation"),
         InlineKeyboardButton(text="🏷 استیکر", callback_data="wel_type_sticker")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="edit_texts")]
    ])

def back_to_texts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به ویرایش متن‌ها", callback_data="edit_texts")]
    ])

def force_join_admin_kb(channels: List[str]):
    b = InlineKeyboardBuilder()
    if channels:
        for i, ch in enumerate(channels, 1):
            b.row(InlineKeyboardButton(text=f"❌ حذف چنل {i}: {ch}", callback_data=f"fj_del_{ch}"))
    b.row(InlineKeyboardButton(text="➕ افزودن چنل/گروه جدید", callback_data="fj_add"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به تنظیمات", callback_data="settings"))
    return b.as_markup()

def force_join_user_kb(channels: List[str], not_joined: List[tuple]):
    b = InlineKeyboardBuilder()
    for idx, ch in not_joined:
        display = ch.lstrip("@")
        url = f"https://t.me/{display}" if ch.startswith("@") else f"https://t.me/c/{ch.replace('-100','')}"
        b.row(InlineKeyboardButton(text=f"📢 چنل {idx}", url=url))
    b.row(InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="fj_check"))
    return b.as_markup()

def download_notify_kb(file_id: str, user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 مشاهده فایل", callback_data=f"file_{file_id}"),
         InlineKeyboardButton(text="👤 پروفایل کاربر", callback_data=f"user_{user_id}")]
    ])

# ==================== STATES ====================
class UploadState(StatesGroup):
    waiting = State()
    caption = State()
    password = State()

class EditState(StatesGroup):
    waiting_caption = State()
    waiting_password = State()

class SettingsState(StatesGroup):
    waiting_welcome = State()
    waiting_welcome_media = State()
    waiting_welcome_caption = State()
    waiting_timer = State()
    waiting_admin_id = State()
    waiting_logchan = State()
    waiting_forcejoin = State()
    waiting_text = State()

class BroadcastState(StatesGroup):
    waiting = State()

class PasswordState(StatesGroup):
    waiting = State()

# ==================== ROUTER ====================
router = Router()

# ==================== START ====================
@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    user = message.from_user
    await db.add_user(user.id, {"name": user.first_name, "username": user.username})
    
    if await db.is_banned(user.id):
        texts = await db.get_texts()
        await message.answer(texts.get("banned_text", "🚫 شما مسدود شده‌اید."))
        return
    
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        
        # Check if bot is active
        if not await db.is_bot_active():
            texts = await db.get_texts()
            await message.answer(
                texts.get("maintenance_text", "🔧 ربات در حال بروزرسانی ست"),
                reply_markup=maintenance_kb(file_id)
            )
            return
        
        file_data = await db.get_file(file_id)
        if file_data:
            settings = await db.get_settings()
            force_channels = settings.get("force_join", [])
            
            if force_channels:
                not_joined = await check_user_joined(message.bot, user.id, force_channels)
                if not_joined:
                    await state.update_data(pending_file=file_id)
                    texts = await db.get_texts()
                    await message.answer(
                        texts.get("force_join_text", "📢 لطفاً عضو شوید"),
                        reply_markup=force_join_user_kb(force_channels, not_joined)
                    )
                    return
            
            if file_data.get("password"):
                await state.update_data(pending_file=file_id)
                await state.set_state(PasswordState.waiting)
                texts = await db.get_texts()
                await message.answer(
                    texts.get("password_text", "🔒 رمز را وارد کنید:"),
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 انصراف", callback_data="cancel_download")]
                    ])
                )
                return
            else:
                await send_file_to_user(message, file_data)
                await notify_admins_download(message.bot, file_data, user)
                return
        else:
            texts = await db.get_texts()
            await message.answer(texts.get("file_not_found", "❌ فایل پیدا نشد."))
            return
    
    await send_welcome_message(message, user)

# ==================== RETRY AFTER MAINTENANCE ====================
@router.callback_query(F.data.startswith("retry_"))
async def retry_download(callback: CallbackQuery, state: FSMContext):
    """Retry download after maintenance mode"""
    await callback.answer()
    
    file_id = callback.data.replace("retry_", "")
    
    # Check if bot is now active
    if not await db.is_bot_active():
        texts = await db.get_texts()
        await callback.message.edit_text(
            texts.get("maintenance_text", "🔧 ربات در حال بروزرسانی ست"),
            reply_markup=maintenance_kb(file_id)
        )
        await callback.answer("🔧 ربات هنوز در حال بروزرسانی است", show_alert=True)
        return
    
    # Bot is active now - send the file
    file_data = await db.get_file(file_id)
    if file_data:
        await callback.message.edit_text("✅ ربات فعال است! در حال ارسال فایل...")
        await send_file_to_user(callback.message, file_data)
        await notify_admins_download(callback.bot, file_data, callback.from_user)
    else:
        await callback.message.edit_text("❌ فایل پیدا نشد.")

async def send_welcome_message(message: Message, user):
    texts = await db.get_texts()
    welcome_type = texts.get("welcome_type", "text")
    welcome_text = texts.get("welcome_text", "👋 سلام!")
    welcome_media = texts.get("welcome_media", "")
    welcome_caption = texts.get("welcome_caption", "")
    
    if await db.is_admin(user.id):
        kb = admin_main_menu()
    else:
        kb = user_main_menu()
    
    try:
        if welcome_type == "photo" and welcome_media:
            await message.answer_photo(photo=welcome_media, caption=welcome_caption or welcome_text, reply_markup=kb)
        elif welcome_type == "video" and welcome_media:
            await message.answer_video(video=welcome_media, caption=welcome_caption or welcome_text, reply_markup=kb)
        elif welcome_type == "animation" and welcome_media:
            await message.answer_animation(animation=welcome_media, caption=welcome_caption or welcome_text, reply_markup=kb)
        elif welcome_type == "sticker" and welcome_media:
            await message.answer_sticker(sticker=welcome_media)
            await message.answer(welcome_caption or welcome_text, reply_markup=kb)
        else:
            await message.answer(welcome_text, reply_markup=kb)
    except:
        await message.answer(welcome_text, reply_markup=kb)

async def check_user_joined(bot: Bot, user_id: int, channels: List[str]) -> List[tuple]:
    not_joined = []
    for i, ch in enumerate(channels, 1):
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                not_joined.append((i, ch))
        except:
            not_joined.append((i, ch))
    return not_joined

# ==================== FORCE JOIN CHECK ====================
@router.callback_query(F.data == "fj_check")
async def force_join_check(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    settings = await db.get_settings()
    force_channels = settings.get("force_join", [])
    texts = await db.get_texts()
    
    if not force_channels:
        await callback.answer("⚠️ هیچ چنلی تنظیم نشده.", show_alert=True)
        return
    
    not_joined = await check_user_joined(callback.bot, user_id, force_channels)
    
    if not_joined:
        txt = texts.get("force_join_fail", "⚠️ هنوز عضو نشدید!")
        try:
            await callback.message.edit_text(txt, reply_markup=force_join_user_kb(force_channels, not_joined))
            await callback.answer("❌ هنوز همه چنل‌ها رو عضو نشدید!", show_alert=True)
        except:
            await callback.answer("❌ لطفاً همه چنل‌ها رو عضو شوید!", show_alert=True)
    else:
        data = await state.get_data()
        file_id = data.get("pending_file")
        
        if file_id:
            file_data = await db.get_file(file_id)
            if file_data:
                await callback.message.edit_text(texts.get("force_join_success", "✅ تایید شد!"))
                await send_file_to_user(callback.message, file_data)
                await notify_admins_download(callback.bot, file_data, callback.from_user)
                await state.clear()
        else:
            await callback.message.edit_text(
                texts.get("force_join_success", "✅ تایید شد!"),
                reply_markup=user_main_menu()
            )
            await state.clear()

@router.callback_query(F.data == "cancel_download")
async def cancel_download(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ دانلود لغو شد.")

# ==================== PASSWORD CHECK ====================
@router.message(PasswordState.waiting)
async def check_password(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = data.get("pending_file")
    file_data = await db.get_file(file_id)
    texts = await db.get_texts()
    
    if not file_data:
        await message.answer("❌ فایل پیدا نشد.")
        await state.clear()
        return
    
    if message.text == file_data.get("password", ""):
        await state.clear()
        await message.answer(texts.get("password_correct", "✅ رمز صحیح"))
        await send_file_to_user(message, file_data)
        await notify_admins_download(message.bot, file_data, message.from_user)
    else:
        await message.answer(texts.get("password_wrong", "❌ رمز اشتباه"))

# ==================== DOWNLOAD NOTIFICATION ====================
async def notify_admins_download(bot: Bot, file_data: Dict, user):
    settings = await db.get_settings()
    log_channel = settings.get("log_channel", "")
    file_caption = file_data.get("caption", "بدون کپشن")
    file_id = file_data["id"]
    downloads = file_data.get("downloads", 0)
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    icon = type_icons.get(file_data.get("type", "document"), "📁")
    
    txt = (
        f"📥 **دانلود جدید**\n\n"
        f"{icon} فایل: {safe_html(file_caption[:50])}\n"
        f"🆔: <code>{safe_html(file_id)}</code>\n"
        f"📊 دانلود: {downloads}\n\n"
        f"👤 کاربر: {safe_html(user.first_name)}\n"
        f"🆔: <code>{user.id}</code>\n"
        f"📎 @{safe_html(user.username or 'ندارد')}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    
    if log_channel:
        try:
            await bot.send_message(chat_id=log_channel, text=txt, reply_markup=download_notify_kb(file_id, user.id))
        except:
            pass
    
    admins = await db.get_admins()
    for admin_id in admins.keys():
        try:
            if admin_id != str(user.id):
                await bot.send_message(chat_id=int(admin_id), text=txt, reply_markup=download_notify_kb(file_id, user.id))
        except:
            pass

# ==================== SEND FILE ====================
async def send_file_to_user(message: Message, file_data: Dict):
    fid = file_data["file_id"]
    cap = file_data.get("caption", "")
    ftype = file_data["type"]
    
    try:
        sent = None
        if ftype == "photo":
            sent = await message.answer_photo(fid, caption=cap)
        elif ftype == "video":
            sent = await message.answer_video(fid, caption=cap)
        elif ftype == "audio":
            sent = await message.answer_audio(fid, caption=cap)
        elif ftype == "voice":
            sent = await message.answer_voice(fid)
        elif ftype == "animation":
            sent = await message.answer_animation(fid, caption=cap)
        elif ftype == "sticker":
            sent = await message.answer_sticker(fid)
        else:
            sent = await message.answer_document(fid, caption=cap)
        
        if sent:
            await db.inc_download(file_data["id"])
            timer = (await db.get_settings()).get("delete_timer", 300)
            if timer > 0:
                asyncio.create_task(auto_delete(sent, timer))
    except:
        try:
            sent = await message.answer_document(fid, caption=cap)
            if sent:
                await db.inc_download(file_data["id"])
        except:
            await message.answer("❌ خطا در ارسال فایل.")

async def auto_delete(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass

# ==================== REPLY KEYBOARD HANDLERS ====================
@router.message(F.text == "📤 آپلود فایل جدید")
async def menu_upload(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(UploadState.waiting)
    await message.answer(
        "📤 **آپلود فایل جدید**\n\nلطفا فایل خود را ارسال کنید.",
        reply_markup=back_inline()
    )

@router.message(F.text == "📂 مدیریت فایل‌ها")
async def menu_files(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    files = await db.get_all_files()
    if not files:
        await message.answer("📂 فایلی آپلود نشده.", reply_markup=admin_main_menu())
        return
    await message.answer(f"📂 **فایل‌ها ({len(files)})**", reply_markup=files_kb(files))

@router.message(F.text == "📊 آمار ربات")
async def menu_stats(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    s = await db.get_stats()
    await message.answer(
        f"📊 **آمار**\n\n👥 کاربران: {s['users']}\n📁 فایل‌ها: {s['files']}\n📥 دانلود: {s['downloads']}",
        reply_markup=admin_main_menu()
    )

@router.message(F.text == "📢 ارسال همگانی")
async def menu_broadcast(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.waiting)
    await message.answer("📢 پیام خود را بفرستید:", reply_markup=back_inline())

@router.message(F.text == "⚙️ تنظیمات")
async def menu_settings(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    s = await db.get_settings()
    await message.answer("⚙️ **تنظیمات**", reply_markup=settings_kb(s))

@router.message(F.text == "👥 کاربران")
async def menu_users(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    users = await db.get_all_users()
    if not users:
        await message.answer("👥 کاربری نیست.", reply_markup=admin_main_menu())
        return
    await message.answer(f"👥 **کاربران ({len(users)})**", reply_markup=users_kb(users))

@router.message(F.text == "👮 ادمین‌ها")
async def menu_admins(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    admins = await db.get_admins()
    txt = "👮 **ادمین‌ها:**\n"
    for aid, a in admins.items():
        txt += f"• <code>{safe_html(str(aid))}</code> - {safe_html(a['role'])}\n"
    await message.answer(txt, reply_markup=admins_kb(admins))

@router.message(F.text == "📜 گزارشات")
async def menu_logs(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    logs_list = await db.get_logs(20)
    if not logs_list:
        await message.answer("📜 گزارشی نیست.", reply_markup=admin_main_menu())
        return
    txt = "📜 **گزارشات:**\n\n"
    for l in logs_list:
        txt += f"<code>{safe_html(l['time'][:19])}</code> {safe_html(l['action'])}\n"
    await message.answer(txt[:4000], reply_markup=admin_main_menu())

@router.message(F.text == "🔗 لینک‌های فعال")
async def menu_links(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    files = await db.get_all_files()
    if not files:
        await message.answer("🔗 لینکی نیست.", reply_markup=admin_main_menu())
        return
    bot = await message.bot.get_me()
    txt = "🔗 **لینک‌ها:**\n\n"
    for fid, f in list(files.items())[:10]:
        txt += f"• {safe_html(f.get('caption','')[:20])}\n  /start {safe_html(fid)}\n\n"
    await message.answer(txt, reply_markup=admin_main_menu())

@router.message(F.text == "💾 پشتیبان‌گیری")
async def menu_backup(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    import shutil
    os.makedirs("backups", exist_ok=True)
    fn = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    shutil.make_archive(fn.replace('.zip', ''), 'zip', '.', lambda x: x.endswith('.json'))
    await message.answer_document(FSInputFile(fn), caption="✅ پشتیبان آماده شد")
    await message.answer("💾 پشتیبان با موفقیت ساخته شد.", reply_markup=admin_main_menu())

# ==================== UPLOAD FLOW ====================
@router.message(UploadState.waiting)
async def upload_receive(message: Message, state: FSMContext):
    file_id = None
    file_type = "document"
    file_name = ""
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
        file_name = message.video.file_name or ""
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
        file_name = message.audio.file_name or ""
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "animation"
        file_name = message.animation.file_name or ""
    elif message.sticker:
        file_id = message.sticker.file_id
        file_type = "sticker"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name or ""
    
    if not file_id:
        await message.answer("❌ فایل معتبر نیست.")
        return
    
    await state.update_data(file_id=file_id, file_type=file_type, file_name=file_name)
    await state.set_state(UploadState.caption)
    await message.answer("✅ فایل دریافت شد! کپشن:", reply_markup=skip_back_inline())

@router.callback_query(F.data == "skip_caption")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(caption="")
    await state.set_state(UploadState.password)
    await callback.message.edit_text("🔒 رمز عبور؟", reply_markup=skip_pass_inline())

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    await state.update_data(caption=message.text or "")
    await state.set_state(UploadState.password)
    await message.answer("🔒 رمز عبور؟", reply_markup=skip_pass_inline())

@router.callback_query(F.data == "skip_password")
async def skip_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(password="")
    await finalize_upload(callback.message, state, callback.from_user.id)

@router.message(UploadState.password)
async def upload_password(message: Message, state: FSMContext):
    await state.update_data(password=message.text or "")
    await finalize_upload(message, state, message.from_user.id)

async def finalize_upload(message: Message, state: FSMContext, admin_id: int):
    data = await state.get_data()
    fid = str(uuid.uuid4())[:8]
    
    await db.add_file({
        "id": fid, "file_id": data["file_id"], "type": data["file_type"],
        "caption": data.get("caption", ""), "file_name": data.get("file_name", ""),
        "password": data.get("password", ""), "admin": admin_id
    })
    await db.add_log("upload", admin_id, f"Uploaded {fid}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    icon = type_icons.get(data.get("file_type", "document"), "📁")
    lock = "🔒 دارد" if data.get("password") else "🔓 ندارد"
    
    txt = (
        f"✅ **آپلود موفق!**\n\n{icon} فایل آپلود شد\n"
        f"🆔: <code>{safe_html(fid)}</code>\n"
        f"📝: {safe_html(data.get('caption') or 'بدون کپشن')}\n{lock}\n"
    )
    if data.get("password"):
        txt += f"🔑 رمز: <code>{safe_html(data.get('password'))}</code>\n\n"
    txt += f"🔗 **لینک:**\n<a href='{safe_html(link)}'>📎 کلیک کنید</a>\n<code>{safe_html(link)}</code>"
    
    await message.answer(txt, reply_markup=admin_main_menu())
    await state.clear()

# ==================== INLINE CALLBACKS ====================
@router.callback_query(F.data == "panel")
async def panel_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("👑 پنل مدیریت:", reply_markup=admin_main_menu())

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

# ==================== BOT ON/OFF TOGGLE ====================
@router.callback_query(F.data == "toggle_bot")
async def toggle_bot_status(callback: CallbackQuery):
    """Toggle bot active/inactive"""
    await callback.answer()
    
    new_status = await db.toggle_bot()
    await db.add_log("toggle", callback.from_user.id, f"Bot {'ON' if new_status else 'OFF'}")
    
    s = await db.get_settings()
    
    # Just refresh the settings keyboard - button text changes automatically
    await callback.message.edit_text("⚙️ **تنظیمات**", reply_markup=settings_kb(s))
    
    if new_status:
        await callback.answer("🟢 ربات فعال شد", show_alert=True)
    else:
        await callback.answer("🔴 ربات خاموش شد", show_alert=True)

@router.callback_query(F.data == "files_list")
async def files_list_cb(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("📂 فایلی نیست.")
        return
    await callback.message.edit_text(f"📂 فایل‌ها ({len(files)})", reply_markup=files_kb(files))

@router.callback_query(F.data.startswith("files_pg_"))
async def files_page(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("files_pg_", ""))
    files = await db.get_all_files()
    await callback.message.edit_text(f"📂 فایل‌ها (صفحه {page+1})", reply_markup=files_kb(files, page))

@router.callback_query(F.data.startswith("file_"))
async def file_info(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("file_", "")
    f = await db.get_file(fid)
    if not f:
        await callback.answer("❌ پیدا نشد", show_alert=True)
        return
    lock = "🔒 دارد" if f.get("password") else "🔓 ندارد"
    txt = f"📁 **اطلاعات فایل**\n\n🆔: <code>{safe_html(fid)}</code>\n📝: {safe_html(f.get('caption',''))}\n📥: {f['downloads']}\n{lock}\n📅: {f['date'][:10]}"
    await callback.message.edit_text(txt, reply_markup=file_actions_kb(fid))

@router.callback_query(F.data.startswith("dl_"))
async def dl_file(callback: CallbackQuery):
    await callback.answer("📥 در حال ارسال...")
    fid = callback.data.replace("dl_", "")
    f = await db.get_file(fid)
    if f:
        await send_file_to_user(callback.message, f)
        await notify_admins_download(callback.bot, f, callback.from_user)

@router.callback_query(F.data.startswith("link_"))
async def get_link(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("link_", "")
    f = await db.get_file(fid)
    if not f:
        await callback.answer("❌ پیدا نشد", show_alert=True)
        return
    bot = await callback.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    pw = f"\n🔑 رمز: <code>{safe_html(f['password'])}</code>" if f.get("password") else ""
    await callback.message.answer(f"🔗 <a href='{safe_html(link)}'>کلیک کنید</a>\n<code>{safe_html(link)}</code>{pw}")

@router.callback_query(F.data.startswith("editcap_"))
async def edit_cap_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_caption)
    await callback.message.edit_text("✏️ کپشن جدید:", reply_markup=back_inline(f"file_{fid}"))

@router.message(EditState.waiting_caption)
async def edit_cap_save(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = data.get("edit_fid")
    if fid:
        await db.update_caption(fid, message.text)
        await message.answer("✅ کپشن ویرایش شد.", reply_markup=admin_main_menu())
    await state.clear()

@router.callback_query(F.data.startswith("setpass_"))
async def set_pass_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("setpass_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_password)
    await callback.message.edit_text("🔒 رمز جدید (remove برای حذف):", reply_markup=back_inline(f"file_{fid}"))

@router.message(EditState.waiting_password)
async def set_pass_save(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = data.get("edit_fid")
    if fid:
        p = "" if message.text.lower() == "remove" else message.text
        await db.update_password(fid, p)
        await message.answer(f"✅ رمز {'حذف' if not p else 'تنظیم'} شد.", reply_markup=admin_main_menu())
    await state.clear()

@router.callback_query(F.data.startswith("del_"))
async def del_confirm(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("del_", "")
    await callback.message.edit_text("⚠️ حذف شود؟", reply_markup=confirm_delete_kb(fid))

@router.callback_query(F.data.startswith("delyes_"))
async def del_exec(callback: CallbackQuery):
    fid = callback.data.replace("delyes_", "")
    if await db.delete_file(fid):
        await callback.answer("✅ حذف شد")
        await files_list_cb(callback)
    else:
        await callback.answer("❌ خطا", show_alert=True)

@router.callback_query(F.data == "users_list")
async def users_list_cb(callback: CallbackQuery):
    await callback.answer()
    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text("👥 کاربری نیست.")
        return
    await callback.message.edit_text(f"👥 کاربران ({len(users)})", reply_markup=users_kb(users))

@router.callback_query(F.data.startswith("users_pg_"))
async def users_page(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("users_pg_", ""))
    users = await db.get_all_users()
    await callback.message.edit_text(f"👥 کاربران (صفحه {page+1})", reply_markup=users_kb(users, page))

@router.callback_query(F.data.startswith("user_"))
async def user_info_cb(callback: CallbackQuery):
    await callback.answer()
    uid = callback.data.replace("user_", "")
    u = (await db.get_all_users()).get(uid)
    if not u:
        await callback.answer("❌ پیدا نشد", show_alert=True)
        return
    txt = f"👤 {safe_html(u.get('name'))}\n🆔: <code>{safe_html(uid)}</code>\n📥: {u.get('downloads',0)}\n🚫: {'مسدود' if u.get('banned') else 'آزاد'}"
    await callback.message.edit_text(txt, reply_markup=user_actions_kb(uid))

@router.callback_query(F.data.startswith("ban_"))
async def toggle_ban(callback: CallbackQuery):
    await callback.answer()
    uid = callback.data.replace("ban_", "")
    result = await db.toggle_ban(int(uid))
    await callback.answer(result)
    await user_info_cb(callback)

@router.callback_query(F.data == "admins_list")
async def admins_list_cb(callback: CallbackQuery):
    await callback.answer()
    admins = await db.get_admins()
    txt = "👮 ادمین‌ها:\n"
    for aid, a in admins.items():
        txt += f"• <code>{safe_html(str(aid))}</code> - {safe_html(a['role'])}\n"
    await callback.message.edit_text(txt, reply_markup=admins_kb(admins))

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_admin_id)
    await callback.message.edit_text("➕ آیدی عددی:", reply_markup=back_inline("admins_list"))

@router.message(SettingsState.waiting_admin_id)
async def add_admin_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        await db.add_admin(uid)
        await message.answer(f"✅ ادمین <code>{uid}</code> اضافه شد.", reply_markup=admin_main_menu())
        await state.clear()
    except:
        await message.answer("❌ آیدی معتبر نیست.")
        return

@router.callback_query(F.data.startswith("admin_"))
async def remove_admin_cb(callback: CallbackQuery):
    await callback.answer()
    aid = callback.data.replace("admin_", "")
    if aid == str(ADMIN_ID):
        await callback.answer("❌ مالک حذف نمی‌شود.", show_alert=True)
        return
    if await db.remove_admin(int(aid)):
        await callback.answer("✅ حذف شد")
    await admins_list_cb(callback)

# ==================== SETTINGS ====================
@router.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    await callback.message.edit_text("⚙️ تنظیمات", reply_markup=settings_kb(s))

# ==================== TEXTS EDITOR (same as v8.0) ====================
@router.callback_query(F.data == "edit_texts")
async def texts_editor_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("📝 **ویرایش متن‌های ربات**", reply_markup=texts_editor_kb())

@router.callback_query(F.data == "edit_welcome")
async def edit_welcome_menu(callback: CallbackQuery):
    await callback.answer()
    texts = await db.get_texts()
    w_type = texts.get("welcome_type", "text")
    type_names = {"text": "📝 متن", "photo": "🖼 عکس", "video": "🎬 ویدیو", "animation": "✨ گیف", "sticker": "🏷 استیکر"}
    await callback.message.edit_text(
        f"👋 **ویرایش پیام خوشامد**\n\n📌 نوع: {type_names.get(w_type)}\n📝 متن: {texts.get('welcome_text','')[:100]}...",
        reply_markup=welcome_type_kb()
    )

@router.callback_query(F.data.startswith("wel_type_"))
async def set_welcome_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    wtype = callback.data.replace("wel_type_", "")
    await db.update_text("welcome_type", wtype)
    if wtype == "text":
        await state.set_state(SettingsState.waiting_welcome)
        await callback.message.edit_text("📝 متن خوشامد جدید:", reply_markup=back_inline("edit_texts"))
    else:
        await state.set_state(SettingsState.waiting_welcome_media)
        await state.update_data(welcome_media_type=wtype)
        type_names = {"photo": "عکس", "video": "ویدیو", "animation": "گیف", "sticker": "استیکر"}
        await callback.message.edit_text(f"📤 {type_names.get(wtype)} را ارسال کنید:", reply_markup=back_inline("edit_texts"))

@router.message(SettingsState.waiting_welcome)
async def save_welcome_text(message: Message, state: FSMContext):
    await db.update_text("welcome_text", message.text)
    await db.update_text("welcome_media", "")
    await db.update_text("welcome_caption", "")
    await db.add_log("texts", message.from_user.id, "Updated welcome text")
    await message.answer("✅ ذخیره شد.", reply_markup=admin_main_menu())
    await state.clear()

@router.message(SettingsState.waiting_welcome_media)
async def receive_welcome_media(message: Message, state: FSMContext):
    data = await state.get_data()
    wtype = data.get("welcome_media_type", "photo")
    file_id = None
    if wtype == "photo" and message.photo:
        file_id = message.photo[-1].file_id
    elif wtype == "video" and message.video:
        file_id = message.video.file_id
    elif wtype == "animation" and message.animation:
        file_id = message.animation.file_id
    elif wtype == "sticker" and message.sticker:
        file_id = message.sticker.file_id
    if not file_id:
        await message.answer("❌ فایل معتبر نیست.")
        return
    await state.update_data(welcome_media_id=file_id)
    await state.set_state(SettingsState.waiting_welcome_caption)
    await message.answer("✅ فایل دریافت شد! کپشن (اختیاری):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ بدون کپشن", callback_data="skip_wel_cap")]
    ]))

@router.callback_query(F.data == "skip_wel_cap")
async def skip_wel_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await db.update_text("welcome_media", data.get("welcome_media_id", ""))
    await db.update_text("welcome_caption", "")
    await callback.message.edit_text("✅ ذخیره شد.")
    await callback.message.answer("👑 پنل مدیریت:", reply_markup=admin_main_menu())
    await state.clear()

@router.message(SettingsState.waiting_welcome_caption)
async def save_welcome_caption(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_text("welcome_media", data.get("welcome_media_id", ""))
    await db.update_text("welcome_caption", message.text or "")
    await message.answer("✅ ذخیره شد.", reply_markup=admin_main_menu())
    await state.clear()

@router.callback_query(F.data.startswith("edit_"))
async def edit_text_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    key = callback.data.replace("edit_", "")
    key_map = {
        "help": "help_text", "forcejoin": "force_join_text",
        "forcejoin_ok": "force_join_success", "forcejoin_fail": "force_join_fail",
        "password": "password_text", "banned": "banned_text",
        "maintenance": "maintenance_text",
    }
    text_key = key_map.get(key, key)
    texts = await db.get_texts()
    current = texts.get(text_key, "")
    await state.update_data(edit_text_key=text_key)
    await state.set_state(SettingsState.waiting_text)
    title_map = {
        "help": "📎 متن راهنما", "forcejoin": "📢 متن عضویت",
        "forcejoin_ok": "✅ متن تایید", "forcejoin_fail": "⚠️ متن عدم عضویت",
        "password": "🔒 متن رمز", "banned": "🚫 متن مسدود",
        "maintenance": "🔧 متن بروزرسانی",
    }
    await callback.message.edit_text(
        f"{title_map.get(key, '📝')}\n\n📌 فعلی:\n{current[:200]}\n\n✏️ متن جدید:",
        reply_markup=back_to_texts_kb()
    )

@router.message(SettingsState.waiting_text)
async def save_text(message: Message, state: FSMContext):
    data = await state.get_data()
    text_key = data.get("edit_text_key", "")
    if text_key:
        await db.update_text(text_key, message.text)
        await message.answer("✅ ذخیره شد.", reply_markup=admin_main_menu())
    await state.clear()

# ==================== TIMER MANAGEMENT ====================
@router.callback_query(F.data == "set_timer")
async def timer_menu(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    await callback.message.edit_text("⏱ **تنظیمات تایمر**", reply_markup=timer_settings_kb(s))

@router.callback_query(F.data == "timer_on")
async def timer_on(callback: CallbackQuery):
    await callback.answer()
    await db.update_setting("delete_timer", 300)
    s = await db.get_settings()
    await callback.message.edit_text("✅ روشن شد (۵ دقیقه)", reply_markup=timer_settings_kb(s))

@router.callback_query(F.data == "timer_off")
async def timer_off(callback: CallbackQuery):
    await callback.answer()
    await db.update_setting("delete_timer", 0)
    s = await db.get_settings()
    await callback.message.edit_text("✅ خاموش شد", reply_markup=timer_settings_kb(s))

@router.callback_query(F.data == "timer_set")
async def timer_set_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text("⏰ زمان به دقیقه:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="set_timer")]
    ]))

@router.message(SettingsState.waiting_timer)
async def timer_set_save(message: Message, state: FSMContext):
    try:
        mins = int(message.text)
        if mins == 0:
            await db.update_setting("delete_timer", 0)
            await message.answer("✅ خاموش شد 🔴", reply_markup=back_to_timer_kb())
        elif mins < 0:
            await message.answer("❌ عدد منفی!")
            return
        else:
            await db.update_setting("delete_timer", mins * 60)
            await message.answer(f"✅ {format_time(mins)} 🟢", reply_markup=back_to_timer_kb())
    except:
        await message.answer("❌ عدد معتبر نیست!")
        return
    await db.add_log("settings", message.from_user.id, f"Timer: {mins}min")
    await state.clear()

# ==================== LOG CHANNEL ====================
@router.callback_query(F.data == "set_logchan")
async def set_logchan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_logchan)
    await callback.message.edit_text("📢 آیدی کانال:", reply_markup=back_inline("settings"))

@router.message(SettingsState.waiting_logchan)
async def save_logchan(message: Message, state: FSMContext):
    ch = message.text.strip()
    try:
        await message.bot.get_chat(ch)
        await db.update_setting("log_channel", ch)
        await message.answer("✅ تنظیم شد.", reply_markup=admin_main_menu())
        await state.clear()
    except:
        await message.answer("❌ خطا!")
        return

# ==================== FORCE JOIN ====================
@router.callback_query(F.data == "set_forcejoin")
async def forcejoin_menu(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    channels = s.get("force_join", [])
    if channels:
        txt = "🔗 **چنل‌ها:**\n\n" + "\n".join([f"{i}. {safe_html(ch)}" for i, ch in enumerate(channels, 1)])
    else:
        txt = "🔗 هیچ چنلی تنظیم نشده."
    await callback.message.edit_text(txt, reply_markup=force_join_admin_kb(channels))

@router.callback_query(F.data == "fj_add")
async def fj_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_forcejoin)
    await callback.message.edit_text("➕ آیدی چنل:", reply_markup=back_inline("set_forcejoin"))

@router.message(SettingsState.waiting_forcejoin)
async def fj_add_save(message: Message, state: FSMContext):
    ch = message.text.strip()
    if not (ch.startswith("@") or ch.startswith("-100")):
        await message.answer("❌ فرمت اشتباه!")
        return
    try:
        await message.bot.get_chat(ch)
        if await db.add_force_join(ch):
            await message.answer(f"✅ اضافه شد:\n{safe_html(ch)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 لیست چنل‌ها", callback_data="set_forcejoin")]
            ]))
            await state.clear()
    except Exception as e:
        await message.answer(f"❌ خطا: {safe_html(str(e)[:100])}")
        return

@router.callback_query(F.data.startswith("fj_del_"))
async def fj_delete(callback: CallbackQuery):
    ch = callback.data.replace("fj_del_", "")
    if await db.remove_force_join(ch):
        await callback.answer("✅ حذف شد")
    await forcejoin_menu(callback)

# ==================== BROADCAST ====================
@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=admin_main_menu())
        return
    users = await db.get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    prog = await message.answer(f"📢 0/{total}")
    for i, uid in enumerate(users.keys()):
        try:
            await message.copy_to(int(uid))
            sent += 1
        except:
            failed += 1
        if (i+1) % 20 == 0:
            await prog.edit_text(f"📢 {i+1}/{total}")
        await asyncio.sleep(0.05)
    await prog.edit_text(f"✅ {sent}/{total}\n❌ {failed}", reply_markup=admin_main_menu())
    await state.clear()

# ==================== MAIN ====================
async def on_startup(bot: Bot):
    db.init_files()
    d = await db._read(ADMINS_FILE)
    if str(ADMIN_ID) not in d["admins"]:
        d["admins"][str(ADMIN_ID)] = {"role": "owner", "added": datetime.now().isoformat()}
        await db._write(ADMINS_FILE, d)
    s = await db.get_settings()
    if "force_join" not in s:
        await db.update_setting("force_join", [])
    if "texts" not in s:
        await db.update_setting("texts", get_default_texts())
    if "bot_active" not in s:
        await db.update_setting("bot_active", True)
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 شروع"),
        BotCommand(command="admin", description="👑 پنل مدیریت")
    ])
    logger.info("Bot started successfully!")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
