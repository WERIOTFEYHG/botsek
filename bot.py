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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

USERS_FILE = "users.json"
FILES_FILE = "files.json"
ADMINS_FILE = "admins.json"
SETTINGS_FILE = "settings.json"
LOGS_FILE = "logs.json"
FOLDERS_FILE = "folders.json"

TEMP_FOLDER_NAME = "فایل‌های موقت"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def safe_html(text: str) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_time(minutes: int) -> str:
    if minutes == 0:
        return "خاموش"
    if minutes < 60:
        return f"{minutes} دقیقه"
    elif minutes < 1440:
        h = minutes // 60
        m = minutes % 60
        return f"{h} ساعت و {m} دقیقه" if m > 0 else f"{h} ساعت"
    else:
        d = minutes // 1440
        h = (minutes % 1440) // 60
        return f"{d} روز و {h} ساعت" if h > 0 else f"{d} روز"

def format_number(num: int) -> str:
    return f"{num:,}"

def get_default_texts():
    return {
        "welcome_type": "text",
        "welcome_text": "سلام! به ربات آپلود فایل خوش اومدی.",
        "welcome_media": "",
        "welcome_caption": "",
        "help_text": "راهنمای ربات:\n\nبرای دریافت فایل، لینک را باز کنید.",
        "force_join_text": "لطفاً ابتدا در چنل‌های زیر عضو شوید\n\nپس از عضویت، دکمه بررسی را بزنید.",
        "force_join_success": "عضویت شما تایید شد!",
        "force_join_fail": "هنوز عضو نشدید!",
        "password_text": "این فایل دارای رمز عبور است.\nلطفا رمز را وارد کنید:",
        "password_correct": "رمز صحیح است. در حال ارسال فایل...",
        "password_wrong": "رمز اشتباه است. دوباره تلاش کنید.",
        "banned_text": "شما مسدود شده‌اید.",
        "file_not_found": "فایل پیدا نشد.",
        "file_deleted": "فایل حذف شد.",
        "maintenance_text": "ربات در حال بروزرسانی ست\n\nلطفاً بعداً مراجعه کنید.",
        "maintenance_retry": "تلاش دوباره",
    }

class JSONManager:
    def __init__(self):
        self.locks = {}
        for f in [USERS_FILE, FILES_FILE, ADMINS_FILE, SETTINGS_FILE, LOGS_FILE, FOLDERS_FILE]:
            self.locks[f] = asyncio.Lock()

    def init_files(self):
        defaults = {
            USERS_FILE: {"users": {}},
            FILES_FILE: {"files": {}},
            ADMINS_FILE: {"admins": {}, "vip_users": {}},
            SETTINGS_FILE: {
                "delete_timer": 300,
                "force_join": [],
                "log_channel": "",
                "bot_active": True,
                "forward_lock": False,
                "texts": get_default_texts(),
                "chat_sessions": {}
            },
            LOGS_FILE: {"logs": []},
            FOLDERS_FILE: {"folders": {}}
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
        return (await self.get_settings()).get("bot_active", True)

    async def toggle_bot(self) -> bool:
        s = await self.get_settings()
        s["bot_active"] = not s.get("bot_active", True)
        await self.update_setting("bot_active", s["bot_active"])
        return s["bot_active"]

    async def is_forward_locked(self) -> bool:
        return (await self.get_settings()).get("forward_lock", False)

    async def toggle_forward_lock(self) -> bool:
        s = await self.get_settings()
        s["forward_lock"] = not s.get("forward_lock", False)
        await self.update_setting("forward_lock", s["forward_lock"])
        return s["forward_lock"]

    async def start_chat(self, admin_id: int, user_id: int):
        s = await self.get_settings()
        sessions = s.get("chat_sessions", {})
        sessions[str(admin_id)] = str(user_id)
        await self.update_setting("chat_sessions", sessions)

    async def end_chat(self, admin_id: int):
        s = await self.get_settings()
        sessions = s.get("chat_sessions", {})
        sessions.pop(str(admin_id), None)
        await self.update_setting("chat_sessions", sessions)

    async def get_chat(self, admin_id: int) -> Optional[int]:
        s = await self.get_settings()
        sessions = s.get("chat_sessions", {})
        uid = sessions.get(str(admin_id))
        return int(uid) if uid else None

    async def add_user(self, uid: int, data: Dict):
        d = await self._read(USERS_FILE)
        if str(uid) not in d["users"]:
            d["users"][str(uid)] = {
                "id": uid,
                "name": data.get("name", ""),
                "username": data.get("username", ""),
                "joined": datetime.now().isoformat(),
                "downloads": 0,
                "views": 0,
                "banned": False
            }
            await self._write(USERS_FILE, d)

    async def inc_views(self, uid: int):
        d = await self._read(USERS_FILE)
        if str(uid) in d["users"]:
            if "views" not in d["users"][str(uid)]:
                d["users"][str(uid)]["views"] = 0
            d["users"][str(uid)]["views"] += 1
            await self._write(USERS_FILE, d)

    async def is_banned(self, uid: int) -> bool:
        return (await self._read(USERS_FILE))["users"].get(str(uid), {}).get("banned", False)

    async def toggle_ban(self, uid: int) -> tuple:
        d = await self._read(USERS_FILE)
        if str(uid) in d["users"]:
            d["users"][str(uid)]["banned"] = not d["users"][str(uid)].get("banned", False)
            await self._write(USERS_FILE, d)
            name = d["users"][str(uid)].get("name", "کاربر")
            status = "مسدود شد" if d["users"][str(uid)]["banned"] else "آزاد شد"
            return (status, name)
        return ("کاربر پیدا نشد", "")

    async def get_user_info(self, uid: int) -> Optional[Dict]:
        return (await self._read(USERS_FILE))["users"].get(str(uid))

    async def get_all_users(self) -> Dict:
        return (await self._read(USERS_FILE))["users"]

    async def get_banned_users(self) -> Dict:
        users = await self.get_all_users()
        return {k: v for k, v in users.items() if v.get("banned", False)}

    async def resolve_user_search(self, bot: Bot, message: Message) -> Optional[int]:
        if message.forward_from:
            return message.forward_from.id
        text = message.text.strip() if message.text else ""
        if not text:
            return None
        if text.isdigit():
            return int(text)
        text = text.lstrip("@")
        users = await self.get_all_users()
        for uid, u in users.items():
            if u.get("username", "").lower() == text.lower():
                return int(uid)
            if u.get("name", "").lower() == text.lower():
                return int(uid)
        try:
            chat = await bot.get_chat(f"@{text}")
            if chat.type == "private":
                return chat.id
        except:
            pass
        return None

    async def is_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        return str(uid) in d.get("admins", {}) or uid == ADMIN_ID

    async def is_vip(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        return str(uid) in d.get("vip_users", {})

    async def is_privileged(self, uid: int) -> bool:
        return await self.is_admin(uid) or await self.is_vip(uid)

    async def add_admin(self, uid: int, username: str = "", role: str = "admin"):
        d = await self._read(ADMINS_FILE)
        if "admins" not in d:
            d["admins"] = {}
        d["admins"][str(uid)] = {"role": role, "username": username, "added": datetime.now().isoformat()}
        await self._write(ADMINS_FILE, d)

    async def remove_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        if str(uid) in d.get("admins", {}) and str(uid) != str(ADMIN_ID):
            del d["admins"][str(uid)]
            await self._write(ADMINS_FILE, d)
            return True
        return False

    async def get_admins(self) -> Dict:
        return (await self._read(ADMINS_FILE)).get("admins", {})

    async def add_vip(self, uid: int, username: str = ""):
        d = await self._read(ADMINS_FILE)
        if "vip_users" not in d:
            d["vip_users"] = {}
        d["vip_users"][str(uid)] = {"username": username, "added": datetime.now().isoformat()}
        await self._write(ADMINS_FILE, d)

    async def remove_vip(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        if str(uid) in d.get("vip_users", {}):
            del d["vip_users"][str(uid)]
            await self._write(ADMINS_FILE, d)
            return True
        return False

    async def get_vips(self) -> Dict:
        return (await self._read(ADMINS_FILE)).get("vip_users", {})

    async def resolve_user_from_input(self, bot: Bot, message: Message) -> tuple:
        if message.forward_from:
            user = message.forward_from
            return (user.id, user.username or "", user.first_name, None)
        if message.forward_sender_name:
            return (None, None, None, "Privacy Forward فعال است.")
        if message.forward_from_chat:
            return (None, None, None, "پیام از کانال/گروه فوروارد شده!")
        text = message.text.strip() if message.text else ""
        if not text:
            return (None, None, None, "متن دریافت نشد.")
        if text.isdigit():
            uid = int(text)
            try:
                chat = await bot.get_chat(uid)
                return (uid, chat.username or "", chat.first_name or "", None)
            except:
                return (None, None, None, f"کاربر با آیدی {uid} پیدا نشد.")
        return (None, None, None, "آیدی عددی یا فوروارد پیام.")

    async def add_file(self, data: Dict) -> str:
        d = await self._read(FILES_FILE)
        fid = data["id"]
        d["files"][fid] = {
            "id": fid,
            "file_id": data["file_id"],
            "type": data["type"],
            "caption": data.get("caption", ""),
            "file_name": data.get("file_name", ""),
            "password": data.get("password", ""),
            "date": datetime.now().isoformat(),
            "downloads": 0,
            "views": 0,
            "admin": data["admin"],
            "folder": data.get("folder", "")
        }
        await self._write(FILES_FILE, d)
        return fid

    async def get_file(self, fid: str) -> Optional[Dict]:
        return (await self._read(FILES_FILE))["files"].get(fid)

    async def get_all_files(self) -> Dict:
        return (await self._read(FILES_FILE))["files"]

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

    async def inc_file_views(self, fid: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            if "views" not in d["files"][fid]:
                d["files"][fid]["views"] = 0
            d["files"][fid]["views"] += 1
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

    async def update_file_folder(self, fid: str, folder: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            d["files"][fid]["folder"] = folder
            await self._write(FILES_FILE, d)

    async def get_files_by_folder(self, folder: str) -> Dict:
        d = await self._read(FILES_FILE)
        return {fid: f for fid, f in d["files"].items() if f.get("folder", "") == folder}

    async def add_folder(self, name: str, admin_id: int) -> str:
        d = await self._read(FOLDERS_FILE)
        fid = str(uuid.uuid4())[:8]
        d["folders"][fid] = {
            "id": fid,
            "name": name,
            "admin": admin_id,
            "created": datetime.now().isoformat(),
            "file_count": 0
        }
        await self._write(FOLDERS_FILE, d)
        return fid

    async def get_folder(self, fid: str) -> Optional[Dict]:
        return (await self._read(FOLDERS_FILE))["folders"].get(fid)

    async def get_all_folders(self) -> Dict:
        return (await self._read(FOLDERS_FILE))["folders"]

    async def delete_folder(self, fid: str) -> bool:
        d = await self._read(FOLDERS_FILE)
        if fid in d["folders"]:
            # Get all files in this folder
            files = await self.get_files_by_folder(fid)
            
            # Get or create temp folder
            temp_folder_id = await self.get_or_create_temp_folder()
            
            # Move all files to temp folder
            for file_id in files:
                await self.update_file_folder(file_id, temp_folder_id)
            
            # Update file counts
            await self.update_folder_file_count(temp_folder_id)
            
            # Delete the folder
            del d["folders"][fid]
            await self._write(FOLDERS_FILE, d)
            return True
        return False

    async def get_or_create_temp_folder(self) -> str:
        folders = await self.get_all_folders()
        for fid, folder in folders.items():
            if folder.get("name", "") == TEMP_FOLDER_NAME:
                return fid
        
        # Create temp folder
        fid = str(uuid.uuid4())[:8]
        d = await self._read(FOLDERS_FILE)
        d["folders"][fid] = {
            "id": fid,
            "name": TEMP_FOLDER_NAME,
            "admin": 0,
            "created": datetime.now().isoformat(),
            "file_count": 0
        }
        await self._write(FOLDERS_FILE, d)
        return fid

    async def update_folder_file_count(self, fid: str):
        d = await self._read(FOLDERS_FILE)
        if fid in d["folders"]:
            files = await self.get_files_by_folder(fid)
            d["folders"][fid]["file_count"] = len(files)
            await self._write(FOLDERS_FILE, d)

    async def get_enhanced_stats(self) -> Dict:
        users = await self._read(USERS_FILE)
        files = await self._read(FILES_FILE)
        total_users = len(users["users"])
        active_users = sum(1 for u in users["users"].values() if u.get("downloads", 0) > 0)
        total_files = len(files["files"])
        total_downloads = sum(f.get("downloads", 0) for f in files["files"].values())
        total_views = sum(f.get("views", 0) for f in files["files"].values()) + sum(u.get("views", 0) for u in users["users"].values())
        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_files": total_files,
            "total_downloads": total_downloads,
            "total_views": total_views
        }

    async def add_log(self, action: str, uid: int, detail: str = ""):
        d = await self._read(LOGS_FILE)
        d["logs"].append({"time": datetime.now().isoformat(), "action": action, "admin": uid, "detail": detail})
        if len(d["logs"]) > 500:
            d["logs"] = d["logs"][-500:]
        await self._write(LOGS_FILE, d)

    async def get_logs(self, limit: int = 20) -> List:
        return (await self._read(LOGS_FILE))["logs"][-limit:]

    async def get_settings(self) -> Dict:
        return await self._read(SETTINGS_FILE)

    async def update_setting(self, key: str, val: Any):
        d = await self._read(SETTINGS_FILE)
        d[key] = val
        await self._write(SETTINGS_FILE, d)

    async def get_texts(self) -> Dict:
        return (await self.get_settings()).get("texts", get_default_texts())

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

async def get_admin_panel_kb():
    is_active = await db.is_bot_active()
    toggle_text = "🟢 ربات فعال است (کلیک برای خاموش)" if is_active else "🔴 ربات خاموش است (کلیک برای روشن)"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📤 آپلود فایل جدید")],
            [KeyboardButton(text="📂 مدیریت فایل‌ها"), KeyboardButton(text="📊 آمار ربات")],
            [KeyboardButton(text="📢 ارسال همگانی"), KeyboardButton(text="⚙️ تنظیمات")],
            [KeyboardButton(text="👥 کاربران"), KeyboardButton(text="👮 ادمین‌ها")],
            [KeyboardButton(text="📜 گزارشات"), KeyboardButton(text="🔗 لینک‌های فعال")],
            [KeyboardButton(text="💾 پشتیبان‌گیری")],
            [KeyboardButton(text=toggle_text)]
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
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]])

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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 تلاش دوباره", callback_data=f"retry_{file_id}")]
    ])

def users_main_menu_kb(total: int, banned: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👤 کل کاربران: {format_number(total)}", callback_data="users_list_all")],
        [InlineKeyboardButton(text=f"🚫 کاربران مسدود: {format_number(banned)}", callback_data="users_list_banned")],
        [InlineKeyboardButton(text="🔍 جستجوی کاربران", callback_data="user_search")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel")]
    ])

def users_list_kb(users: List[tuple], page: int, total_pages: int, prefix: str = "u"):
    b = InlineKeyboardBuilder()
    for uid, u in users:
        name = u.get("name", "کاربر")[:15]
        joined = u.get("joined", "")[:10].replace("-", "/") if u.get("joined") else ""
        b.row(InlineKeyboardButton(text=f"👤 {name} | 📅 {joined}", callback_data=f"userinfo_{uid}"))
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"{prefix}_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"{prefix}_pg_{page+1}"))
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔍 جستجوی کاربران", callback_data="user_search"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="users_menu"))
    return b.as_markup()

def banned_users_list_kb(users: List[tuple], page: int, total_pages: int):
    b = InlineKeyboardBuilder()
    for uid, u in users:
        name = u.get("name", "کاربر")[:12]
        b.row(
            InlineKeyboardButton(text=f"👤 {name}", callback_data=f"userinfo_{uid}"),
            InlineKeyboardButton(text="✅ رفع مسدودیت", callback_data=f"unban_{uid}")
        )
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"ban_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"ban_pg_{page+1}"))
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="users_menu"))
    return b.as_markup()

def user_info_kb(uid: int, is_banned: bool):
    ban_text = "✅ رفع مسدودیت" if is_banned else "🚫 مسدود کردن"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_text, callback_data=f"toggleban_{uid}")],
        [InlineKeyboardButton(text="💬 چت با کاربر", callback_data=f"chatstart_{uid}")],
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="users_list_all")]
    ])

def chat_active_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 پایان گفتگو", callback_data="chatend")]
    ])

def settings_kb(settings: Dict):
    timer_val = settings.get("delete_timer", 300)
    timer_text = f"⏱ تایمر حذف پست: {format_time(timer_val // 60) if timer_val else 'خاموش'}"
    fj_count = len(settings.get("force_join", []))
    forward_locked = settings.get("forward_lock", False)
    forward_text = "🔒 قفل فوروارد: فعال ✅" if forward_locked else "🔓 قفل فوروارد: غیرفعال ❌"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=forward_text, callback_data="toggle_forward_lock"))
    b.row(InlineKeyboardButton(text=f"🔗 عضویت اجباری ({fj_count})", callback_data="set_forcejoin"))
    b.row(InlineKeyboardButton(text="📝 ویرایش متن‌های ربات", callback_data="edit_texts"))
    b.row(InlineKeyboardButton(text="📢 کانال گزارش", callback_data="set_logchan"))
    b.row(InlineKeyboardButton(text=timer_text, callback_data="set_timer"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel"))
    return b.as_markup()

def stats_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی آمار", callback_data="refresh_stats")],
        [InlineKeyboardButton(text="📊 آمار عضویت اجباری", callback_data="force_join_stats")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel")]
    ])

def force_join_stats_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به آمار", callback_data="show_stats")]
    ])

async def folders_main_kb():
    folders = await db.get_all_folders()
    files = await db.get_all_files()
    total_folders = len(folders)
    total_files = len(files)
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ ایجاد پوشه جدید", callback_data="create_folder"))
    
    if folders:
        for fid, folder in folders.items():
            name = folder.get("name", "بدون نام")[:25]
            count = folder.get("file_count", 0)
            b.row(InlineKeyboardButton(text=f"📂 {name} ({count})", callback_data=f"folder_{fid}"))
    
    b.row(InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel"))
    return b.as_markup()

def folder_files_kb(files: List[tuple], folder_id: str, page: int, total_pages: int):
    b = InlineKeyboardBuilder()
    
    b.row(InlineKeyboardButton(text="➕ اضافه کردن فایل", callback_data=f"addfile_{folder_id}"))
    
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    
    for fid, f in files:
        cap = f.get("caption", "بدون کپشن")[:15]
        icon = type_icons.get(f.get("type", "document"), "📁")
        lock = "🔒" if f.get("password") else ""
        fid_short = fid[:8]
        b.row(InlineKeyboardButton(text=f"{icon} {lock} {fid_short} {cap}", callback_data=f"folderfile_{fid}_{folder_id}"))
    
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"folderpg_{folder_id}_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"folderpg_{folder_id}_{page+1}"))
        b.row(*nav)
    
    b.row(InlineKeyboardButton(text="🔙 بازگشت به پوشه‌ها", callback_data="folders_menu"))
    return b.as_markup()

def folder_file_info_kb(fid: str, folder_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دریافت", callback_data=f"dl_{fid}"), InlineKeyboardButton(text="🔗 لینک", callback_data=f"link_{fid}")],
        [InlineKeyboardButton(text="✏️ کپشن", callback_data=f"editcap_{fid}"), InlineKeyboardButton(text="🔒 قفل", callback_data=f"setpass_{fid}")],
        [InlineKeyboardButton(text="🗑 حذف فایل", callback_data=f"deletefile_{fid}_{folder_id}")],
        [InlineKeyboardButton(text="🗑 حذف از پوشه", callback_data=f"remfromfolder_{fid}_{folder_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت به پوشه", callback_data=f"folder_{folder_id}")]
    ])

def folder_delete_confirm_kb(fid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 حذف فایل", callback_data=f"confirm_deletefile_{fid}")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data=f"folder_{fid}")]
    ])

def add_file_to_folder_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 ارسال فایل جدید", callback_data="add_new_file")],
        [InlineKeyboardButton(text="🔗 ارسال لینک فایل موجود", callback_data="add_existing_file")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="cancel_add_file")]
    ])

def confirm_remove_from_folder_kb(fid: str, folder_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله حذف کن", callback_data=f"confirm_remove_{fid}_{folder_id}")],
        [InlineKeyboardButton(text="❌ خیر", callback_data=f"folder_{folder_id}")]
    ])

def admins_main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن ادمین", callback_data="add_admin_prompt")],
        [InlineKeyboardButton(text="⭐ افزودن کاربر VIP", callback_data="add_vip_prompt")],
        [InlineKeyboardButton(text="❌ حذف ادمین / VIP", callback_data="remove_privileged")],
        [InlineKeyboardButton(text="🔙 بازگشت به منو", callback_data="panel")]
    ])

def remove_privileged_kb(admins: Dict, vips: Dict):
    b = InlineKeyboardBuilder()
    if admins:
        for aid, a in admins.items():
            if str(aid) == str(ADMIN_ID):
                continue
            uname = a.get('username', '')
            display = f"@{uname}-admin" if uname else f"ID:{aid}-admin"
            b.row(InlineKeyboardButton(text=f"❌ حذف {display}", callback_data=f"ra_{aid}"))
    if vips:
        for vid, v in vips.items():
            uname = v.get('username', '')
            display = f"@{uname}-vip" if uname else f"ID:{vid}-vip"
            b.row(InlineKeyboardButton(text=f"❌ حذف {display}", callback_data=f"rv_{vid}"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admins_menu"))
    return b.as_markup()

def texts_editor_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👋 پیام خوشامد (مدیا)", callback_data="edit_welcome"))
    b.row(InlineKeyboardButton(text="📎 متن راهنما", callback_data="edit_help"))
    b.row(InlineKeyboardButton(text="📢 متن عضویت اجباری", callback_data="edit_forcejoin"))
    b.row(InlineKeyboardButton(text="✅ متن تایید عضویت", callback_data="edit_forcejoin_ok"))
    b.row(InlineKeyboardButton(text="⚠️ متن عدم عضویت", callback_data="edit_forcejoin_fail"))
    b.row(InlineKeyboardButton(text="🔒 متن رمز عبور", callback_data="edit_password"))
    b.row(InlineKeyboardButton(text="🚫 متن مسدودیت", callback_data="edit_banned"))
    b.row(InlineKeyboardButton(text="🔧 متن بروزرسانی", callback_data="edit_maintenance"))
    b.row(InlineKeyboardButton(text="🔙 تنظیمات", callback_data="settings"))
    return b.as_markup()

def welcome_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 متن", callback_data="wel_type_text")],
        [InlineKeyboardButton(text="🖼 عکس", callback_data="wel_type_photo"), InlineKeyboardButton(text="🎬 ویدیو", callback_data="wel_type_video")],
        [InlineKeyboardButton(text="✨ گیف", callback_data="wel_type_animation"), InlineKeyboardButton(text="🏷 استیکر", callback_data="wel_type_sticker")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="edit_texts")]
    ])

def back_to_texts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="edit_texts")]
    ])

def timer_settings_kb(settings: Dict):
    timer_val = settings.get("delete_timer", 300)
    b = InlineKeyboardBuilder()
    if timer_val == 0:
        b.row(InlineKeyboardButton(text="⏱ خاموش 🔴", callback_data="noop"))
        b.row(InlineKeyboardButton(text="🔵 روشن کردن", callback_data="timer_on"))
    else:
        b.row(InlineKeyboardButton(text=f"⏱ {format_time(timer_val // 60)} 🟢", callback_data="noop"))
        b.row(InlineKeyboardButton(text="🔴 خاموش کردن", callback_data="timer_off"))
    b.row(InlineKeyboardButton(text="⏰ تنظیم زمان", callback_data="timer_set"))
    b.row(InlineKeyboardButton(text="🔙 تنظیمات", callback_data="settings"))
    return b.as_markup()

def back_to_timer_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="set_timer")]
    ])

def force_join_admin_kb(channels: List[str]):
    b = InlineKeyboardBuilder()
    if channels:
        for i, ch in enumerate(channels, 1):
            b.row(InlineKeyboardButton(text=f"❌ حذف چنل {i}: {ch}", callback_data=f"fjdel_{ch[:20]}"))
    b.row(InlineKeyboardButton(text="➕ افزودن", callback_data="fj_add"))
    b.row(InlineKeyboardButton(text="🔙 تنظیمات", callback_data="settings"))
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
        [InlineKeyboardButton(text="📁 فایل", callback_data=f"file_{file_id}"), InlineKeyboardButton(text="👤 کاربر", callback_data=f"user_{user_id}")]
    ])

class UploadState(StatesGroup):
    waiting = State()
    caption = State()
    password = State()
    folder_select = State()

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
    waiting_add_admin = State()
    waiting_add_vip = State()
    waiting_search_user = State()

class BroadcastState(StatesGroup):
    waiting = State()

class PasswordState(StatesGroup):
    waiting = State()

class ChatState(StatesGroup):
    waiting = State()

class FolderState(StatesGroup):
    waiting_name = State()
    waiting_file = State()
    waiting_link = State()

class DeleteState(StatesGroup):
    waiting_password = State()

router = Router()

@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    user = message.from_user
    await db.add_user(user.id, {"name": user.first_name, "username": user.username})
    await db.inc_views(user.id)
    if await db.is_banned(user.id):
        texts = await db.get_texts()
        await message.answer(texts.get("banned_text", "🚫 مسدود هستید."))
        return
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        await db.inc_file_views(file_id)
        if not await db.is_bot_active() and not await db.is_privileged(user.id):
            texts = await db.get_texts()
            await message.answer(texts.get("maintenance_text", "🔧 در حال بروزرسانی"), reply_markup=maintenance_kb(file_id))
            return
        file_data = await db.get_file(file_id)
        if file_data:
            if not await db.is_privileged(user.id):
                settings = await db.get_settings()
                force_channels = settings.get("force_join", [])
                if force_channels:
                    not_joined = await check_user_joined(message.bot, user.id, force_channels)
                    if not_joined:
                        await state.update_data(pending_file=file_id)
                        texts = await db.get_texts()
                        await message.answer(texts.get("force_join_text", "📢 عضو شوید"), reply_markup=force_join_user_kb(force_channels, not_joined))
                        return
                if file_data.get("password"):
                    await state.update_data(pending_file=file_id)
                    await state.set_state(PasswordState.waiting)
                    texts = await db.get_texts()
                    await message.answer(texts.get("password_text", "🔒 رمز:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 انصراف", callback_data="cancel_download")]]))
                    return
            await send_file_to_user(message, file_data)
            await notify_admins_download(message.bot, file_data, user)
            return
        else:
            texts = await db.get_texts()
            await message.answer(texts.get("file_not_found", "❌ پیدا نشد."))
            return
    await send_welcome_message(message, user)

@router.callback_query(F.data.startswith("retry_"))
async def retry_download(callback: CallbackQuery):
    await callback.answer()
    file_id = callback.data.replace("retry_", "")
    if not await db.is_bot_active():
        texts = await db.get_texts()
        await callback.message.edit_text(texts.get("maintenance_text", "🔧 در حال بروزرسانی"), reply_markup=maintenance_kb(file_id))
        await callback.answer("🔧 هنوز در حال بروزرسانی", show_alert=True)
        return
    file_data = await db.get_file(file_id)
    if file_data:
        await callback.message.edit_text("✅ فعال است! در حال ارسال...")
        await send_file_to_user(callback.message, file_data)
        await notify_admins_download(callback.bot, file_data, callback.from_user)
    else:
        await callback.message.edit_text("❌ فایل پیدا نشد.")

async def send_welcome_message(message: Message, user):
    texts = await db.get_texts()
    w_type = texts.get("welcome_type", "text")
    w_text = texts.get("welcome_text", "👋 سلام!")
    w_media = texts.get("welcome_media", "")
    w_cap = texts.get("welcome_caption", "")
    kb = await get_admin_panel_kb() if await db.is_admin(user.id) else user_main_menu()
    try:
        if w_type == "photo" and w_media:
            await message.answer_photo(w_media, caption=w_cap or w_text, reply_markup=kb)
        elif w_type == "video" and w_media:
            await message.answer_video(w_media, caption=w_cap or w_text, reply_markup=kb)
        elif w_type == "animation" and w_media:
            await message.answer_animation(w_media, caption=w_cap or w_text, reply_markup=kb)
        elif w_type == "sticker" and w_media:
            await message.answer_sticker(w_media)
            await message.answer(w_cap or w_text, reply_markup=kb)
        else:
            await message.answer(w_text, reply_markup=kb)
    except:
        await message.answer(w_text, reply_markup=kb)

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

@router.callback_query(F.data == "fj_check")
async def force_join_check(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    settings = await db.get_settings()
    force_channels = settings.get("force_join", [])
    texts = await db.get_texts()
    not_joined = await check_user_joined(callback.bot, user_id, force_channels)
    if not_joined:
        await callback.message.edit_text(texts.get("force_join_fail", "⚠️ عضو نشدید!"), reply_markup=force_join_user_kb(force_channels, not_joined))
        await callback.answer("❌ عضو نشدید!", show_alert=True)
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
            await callback.message.edit_text(texts.get("force_join_success", "✅ تایید شد!"), reply_markup=user_main_menu())
            await state.clear()

@router.callback_query(F.data == "cancel_download")
async def cancel_download(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ لغو شد.")

@router.message(PasswordState.waiting)
async def check_password(message: Message, state: FSMContext):
    data = await state.get_data()
    file_data = await db.get_file(data.get("pending_file", ""))
    texts = await db.get_texts()
    if file_data and message.text == file_data.get("password", ""):
        await state.clear()
        await message.answer(texts.get("password_correct", "✅ صحیح"))
        await send_file_to_user(message, file_data)
        await notify_admins_download(message.bot, file_data, message.from_user)
    else:
        await message.answer(texts.get("password_wrong", "❌ اشتباه"))

async def notify_admins_download(bot: Bot, file_data: Dict, user):
    settings = await db.get_settings()
    log_ch = settings.get("log_channel", "")
    icon = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}.get(file_data.get("type", "document"), "📁")
    fid_short = file_data.get("id", "")[:8]
    txt = f"📥 دانلود جدید\n\n{icon}\n🆔: {fid_short}\n📊: {file_data.get('downloads', 0)}\n\n👤: {safe_html(user.first_name)}\n🆔: {user.id}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    if log_ch:
        try:
            await bot.send_message(log_ch, txt)
        except:
            pass

async def send_file_to_user(message: Message, file_data: Dict):
    fid = file_data["file_id"]
    cap = file_data.get("caption", "")
    ftype = file_data["type"]
    protect = await db.is_forward_locked()
    try:
        sent = None
        if ftype == "photo":
            sent = await message.answer_photo(fid, caption=cap, protect_content=protect)
        elif ftype == "video":
            sent = await message.answer_video(fid, caption=cap, protect_content=protect)
        elif ftype == "audio":
            sent = await message.answer_audio(fid, caption=cap, protect_content=protect)
        elif ftype == "voice":
            sent = await message.answer_voice(fid, protect_content=protect)
        elif ftype == "animation":
            sent = await message.answer_animation(fid, caption=cap, protect_content=protect)
        elif ftype == "sticker":
            sent = await message.answer_sticker(fid)
        else:
            sent = await message.answer_document(fid, caption=cap, protect_content=protect)
        if sent:
            await db.inc_download(file_data["id"])
            timer = (await db.get_settings()).get("delete_timer", 300)
            if timer > 0:
                asyncio.create_task(auto_delete(sent, timer))
    except:
        try:
            await message.answer_document(fid, caption=cap, protect_content=protect)
            await db.inc_download(file_data["id"])
        except:
            pass

async def auto_delete(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass

@router.message(F.text == "📤 آپلود فایل جدید")
async def menu_upload(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    
    folders = await db.get_all_folders()
    
    if not folders:
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="➕ ایجاد پوشه", callback_data="create_folder"))
        b.row(InlineKeyboardButton(text="🔙 انصراف", callback_data="panel"))
        await message.answer(
            "📁 **هیچ پوشه‌ای وجود ندارد!**\n\n"
            "لطفاً ابتدا یک پوشه ایجاد کنید.",
            reply_markup=b.as_markup()
        )
        return
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📁 انتخاب پوشه", callback_data="noop"))
    for fid, folder in folders.items():
        name = folder.get("name", "بدون نام")[:25]
        b.row(InlineKeyboardButton(text=f"📂 {name}", callback_data=f"upload_to_{fid}"))
    b.row(InlineKeyboardButton(text="🔙 انصراف", callback_data="panel"))
    
    await message.answer(
        "📁 **یک پوشه را انتخاب کنید:**\n\n"
        "فایل شما در پوشه انتخاب شده ذخیره خواهد شد.",
        reply_markup=b.as_markup()
    )

@router.callback_query(F.data.startswith("upload_to_"))
async def upload_to_folder(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    folder_id = callback.data.replace("upload_to_", "")
    folder = await db.get_folder(folder_id)
    
    if not folder:
        await callback.message.edit_text("❌ پوشه پیدا نشد.")
        return
    
    await state.update_data(upload_folder=folder_id)
    await state.set_state(UploadState.waiting)
    
    await callback.message.edit_text(
        f"📤 **آپلود فایل به پوشه: {safe_html(folder.get('name', 'بدون نام'))}**\n\n"
        "لطفاً فایل خود را ارسال کنید.",
        reply_markup=back_inline("panel")
    )

@router.callback_query(F.data == "create_folder")
async def create_folder_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FolderState.waiting_name)
    await callback.message.edit_text(
        "📁 **ایجاد پوشه جدید**\n\n"
        "لطفاً نام پوشه را وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="folders_menu")]
        ])
    )

@router.message(FolderState.waiting_name)
async def create_folder_save(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ نام پوشه نمی‌تواند خالی باشد.")
        return
    
    folders = await db.get_all_folders()
    for fid, folder in folders.items():
        if folder.get("name", "").lower() == name.lower():
            await message.answer("❌ پوشه‌ای با این نام قبلاً وجود دارد. لطفاً نام دیگری انتخاب کنید.")
            return
    
    folder_id = await db.add_folder(name, message.from_user.id)
    await db.add_log("folder_create", message.from_user.id, f"Created folder: {name}")
    
    await message.answer(
        f"✅ **پوشه با موفقیت ساخته شد!**\n\n"
        f"📁 نام: {safe_html(name)}\n"
        f"🆔 شناسه: <code>{folder_id}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 مشاهده پوشه", callback_data=f"folder_{folder_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت به پوشه‌ها", callback_data="folders_menu")]
        ])
    )
    await state.clear()

@router.callback_query(F.data == "folders_menu")
async def folders_menu(callback: CallbackQuery):
    await callback.answer()
    folders = await db.get_all_folders()
    files = await db.get_all_files()
    total_folders = len(folders)
    total_files = len(files)
    
    txt = f"📂 **مدیریت فایل‌ها و پوشه‌ها**\n\n📁 تعداد پوشه‌ها: {total_folders}\n📄 تعداد فایل‌ها: {total_files}"
    
    await callback.message.edit_text(txt, reply_markup=await folders_main_kb())

@router.message(F.text == "📂 مدیریت فایل‌ها")
async def menu_files(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    folders = await db.get_all_folders()
    files = await db.get_all_files()
    total_folders = len(folders)
    total_files = len(files)
    
    txt = f"📂 **مدیریت فایل‌ها و پوشه‌ها**\n\n📁 تعداد پوشه‌ها: {total_folders}\n📄 تعداد فایل‌ها: {total_files}"
    
    await message.answer(txt, reply_markup=await folders_main_kb())

@router.callback_query(F.data.startswith("folder_"))
async def view_folder(callback: CallbackQuery):
    await callback.answer()
    folder_id = callback.data.replace("folder_", "")
    folder = await db.get_folder(folder_id)
    
    if not folder:
        await callback.message.edit_text("❌ پوشه پیدا نشد.", reply_markup=await folders_main_kb())
        return
    
    files = await db.get_files_by_folder(folder_id)
    await show_folder_files(callback.message, folder, files, folder_id, 0)

async def show_folder_files(message: Message, folder: Dict, files: Dict, folder_id: str, page: int):
    items = list(files.items())
    per_page = 15
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    page_items = items[start:start+per_page]
    
    folder_name = folder.get("name", "بدون نام")
    file_count = len(items)
    
    txt = f"📂 **{safe_html(folder_name)}**\n\n"
    txt += f"📄 تعداد فایل‌ها: {file_count}\n"
    txt += f"📅 ایجاد: {folder.get('created', '')[:10]}"
    
    await db.update_folder_file_count(folder_id)
    
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(txt, reply_markup=folder_files_kb(page_items, folder_id, page, total_pages))
    else:
        await message.answer(txt, reply_markup=folder_files_kb(page_items, folder_id, page, total_pages))

@router.callback_query(F.data.startswith("folderpg_"))
async def folder_page(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.replace("folderpg_", "").split("_")
    folder_id = parts[0]
    page = int(parts[1])
    
    folder = await db.get_folder(folder_id)
    if not folder:
        await callback.message.edit_text("❌ پوشه پیدا نشد.")
        return
    
    files = await db.get_files_by_folder(folder_id)
    await show_folder_files(callback.message, folder, files, folder_id, page)

@router.callback_query(F.data.startswith("folderfile_"))
async def view_folder_file(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.replace("folderfile_", "").split("_")
    fid = parts[0]
    folder_id = parts[1]
    
    f = await db.get_file(fid)
    if not f:
        await callback.answer("❌ فایل پیدا نشد", show_alert=True)
        return
    
    has_password = True if f.get("password") else False
    lock = "🔒 دارد" if has_password else "🔓 ندارد"
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    icon = type_icons.get(f.get("type", "document"), "📁")
    
    bot = await callback.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    fid_short = fid[:8]
    
    txt = f"{icon} **مشخصات فایل**\n\n"
    txt += f"🆔 شناسه: {fid_short}\n"
    txt += f"📝 کپشن: {safe_html(f.get('caption', 'بدون کپشن'))}\n"
    txt += f"📂 نوع: {f.get('type', 'ناشناس')}\n"
    txt += f"📥 دانلودها: {f.get('downloads', 0)}\n"
    txt += f"👁 بازدیدها: {f.get('views', 0)}\n"
    txt += f"{lock}\n"
    txt += f"📅 تاریخ: {f.get('date', '')[:10]}\n\n"
    txt += f"🔗 لینک استارت:\n{link}"
    
    await callback.message.edit_text(txt, reply_markup=folder_file_info_kb(fid, folder_id))

@router.callback_query(F.data.startswith("addfile_"))
async def add_file_to_folder_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    folder_id = callback.data.replace("addfile_", "")
    folder = await db.get_folder(folder_id)
    
    if not folder:
        await callback.message.edit_text("❌ پوشه پیدا نشد.")
        return
    
    await state.update_data(add_folder=folder_id)
    await callback.message.edit_text(
        f"📤 **اضافه کردن فایل به {safe_html(folder.get('name', 'بدون نام'))}**\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=add_file_to_folder_kb()
    )

@router.callback_query(F.data == "add_new_file")
async def add_new_file_to_folder(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FolderState.waiting_file)
    await callback.message.edit_text(
        "📤 **ارسال فایل جدید**\n\n"
        "لطفاً فایل خود را ارسال کنید.",
        reply_markup=back_inline(f"addfile_{(await state.get_data()).get('add_folder', '')}")
    )

@router.message(FolderState.waiting_file)
async def receive_new_file_for_folder(message: Message, state: FSMContext):
    data = await state.get_data()
    folder_id = data.get("add_folder")
    
    if not folder_id:
        await message.answer("❌ خطا در شناسایی پوشه.")
        await state.clear()
        return
    
    folder = await db.get_folder(folder_id)
    if not folder:
        await message.answer("❌ پوشه پیدا نشد.")
        await state.clear()
        return
    
    file_id, file_type, file_name = None, "document", ""
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, file_type, file_name = message.video.file_id, "video", message.video.file_name or ""
    elif message.audio:
        file_id, file_type, file_name = message.audio.file_id, "audio", message.audio.file_name or ""
    elif message.voice:
        file_id, file_type = message.voice.file_id, "voice"
    elif message.animation:
        file_id, file_type, file_name = message.animation.file_id, "animation", message.animation.file_name or ""
    elif message.sticker:
        file_id, file_type = message.sticker.file_id, "sticker"
    elif message.document:
        file_id, file_type, file_name = message.document.file_id, "document", message.document.file_name or ""
    
    if not file_id:
        await message.answer("❌ فایل معتبر نیست. لطفاً دوباره ارسال کنید.")
        return
    
    fid = str(uuid.uuid4())[:8]
    await db.add_file({
        "id": fid,
        "file_id": file_id,
        "type": file_type,
        "caption": message.caption or "",
        "file_name": file_name,
        "password": "",
        "admin": message.from_user.id,
        "folder": folder_id
    })
    
    await db.update_folder_file_count(folder_id)
    await db.add_log("file_add_to_folder", message.from_user.id, f"Added file {fid} to folder {folder_id}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    await message.answer(
        f"✅ **فایل با موفقیت به پوشه اضافه شد!**\n\n"
        f"📁 پوشه: {safe_html(folder.get('name', 'بدون نام'))}\n"
        f"🆔 شناسه: {fid}\n"
        f"🔗 لینک استارت:\n{link}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 مشاهده پوشه", callback_data=f"folder_{folder_id}")],
            [InlineKeyboardButton(text="➕ اضافه کردن فایل دیگر", callback_data=f"addfile_{folder_id}")],
            [InlineKeyboardButton(text="🔙 پوشه‌ها", callback_data="folders_menu")]
        ])
    )
    await state.clear()

@router.callback_query(F.data == "add_existing_file")
async def add_existing_file_to_folder(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FolderState.waiting_link)
    await callback.message.edit_text(
        "🔗 **اضافه کردن فایل موجود**\n\n"
        "لطفاً لینک استارت فایل را ارسال کنید:\n"
        "مثال: `/start abc123` یا `https://t.me/bot?start=abc123`\n\n"
        "⚠️ اگر فایل در پوشه دیگری باشد، به این پوشه منتقل می‌شود.",
        reply_markup=back_inline(f"addfile_{(await state.get_data()).get('add_folder', '')}")
    )

@router.message(FolderState.waiting_link)
async def receive_existing_file_link(message: Message, state: FSMContext):
    data = await state.get_data()
    folder_id = data.get("add_folder")
    
    if not folder_id:
        await message.answer("❌ خطا در شناسایی پوشه.")
        await state.clear()
        return
    
    folder = await db.get_folder(folder_id)
    if not folder:
        await message.answer("❌ پوشه پیدا نشد.")
        await state.clear()
        return
    
    text = message.text.strip()
    fid = None
    
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1:
            fid = parts[1].strip()
    elif "?start=" in text:
        fid = text.split("?start=")[-1].strip().split()[0]
    else:
        fid = text.strip()
    
    if not fid:
        await message.answer("❌ لینک معتبر نیست. لطفاً مجدداً ارسال کنید.")
        return
    
    file_data = await db.get_file(fid)
    if not file_data:
        await message.answer("❌ فایل با این شناسه یافت نشد.")
        return
    
    if file_data.get("folder", "") == folder_id:
        await message.answer("❌ این فایل قبلاً در این پوشه وجود دارد.")
        return
    
    old_folder_id = file_data.get("folder", "")
    old_folder_name = "بدون پوشه"
    if old_folder_id:
        old_folder = await db.get_folder(old_folder_id)
        if old_folder:
            old_folder_name = old_folder.get("name", "بدون نام")
    
    await db.update_file_folder(fid, folder_id)
    await db.update_folder_file_count(folder_id)
    if old_folder_id:
        await db.update_folder_file_count(old_folder_id)
    
    await db.add_log("file_move", message.from_user.id, f"Moved file {fid} from {old_folder_id} to {folder_id}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    await message.answer(
        f"✅ **فایل با موفقیت منتقل شد!**\n\n"
        f"📁 پوشه جدید: {safe_html(folder.get('name', 'بدون نام'))}\n"
        f"📁 پوشه قبلی: {safe_html(old_folder_name)}\n"
        f"🆔 شناسه: {fid}\n"
        f"🔗 لینک استارت:\n{link}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 مشاهده پوشه", callback_data=f"folder_{folder_id}")],
            [InlineKeyboardButton(text="➕ اضافه کردن فایل دیگر", callback_data=f"addfile_{folder_id}")],
            [InlineKeyboardButton(text="🔙 پوشه‌ها", callback_data="folders_menu")]
        ])
    )
    await state.clear()

@router.callback_query(F.data == "cancel_add_file")
async def cancel_add_file(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ عملیات لغو شد.", reply_markup=await folders_main_kb())

@router.callback_query(F.data.startswith("remfromfolder_"))
async def remove_from_folder_confirm(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.replace("remfromfolder_", "").split("_")
    fid = parts[0]
    folder_id = parts[1]
    
    await callback.message.edit_text(
        "⚠️ **آیا از حذف این فایل از پوشه اطمینان دارید؟**\n\n"
        "فایل از پوشه حذف می‌شود اما از ربات پاک نمی‌شود.",
        reply_markup=confirm_remove_from_folder_kb(fid, folder_id)
    )

@router.callback_query(F.data.startswith("confirm_remove_"))
async def confirm_remove_from_folder(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.replace("confirm_remove_", "").split("_")
    fid = parts[0]
    folder_id = parts[1]
    
    await db.update_file_folder(fid, "")
    await db.update_folder_file_count(folder_id)
    await db.add_log("file_remove_from_folder", callback.from_user.id, f"Removed file {fid} from folder {folder_id}")
    
    await callback.message.edit_text(
        "✅ فایل از پوشه حذف شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 بازگشت به پوشه", callback_data=f"folder_{folder_id}")],
            [InlineKeyboardButton(text="🔙 پوشه‌ها", callback_data="folders_menu")]
        ])
    )

@router.callback_query(F.data.startswith("deletefile_"))
async def delete_file_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = callback.data.replace("deletefile_", "").split("_")
    fid = parts[0]
    folder_id = parts[1]
    
    await state.update_data(delete_fid=fid, delete_folder=folder_id)
    await state.set_state(DeleteState.waiting_password)
    await callback.message.edit_text(
        "🗑 **حذف فایل**\n\n"
        "برای تایید حذف، لطفاً رمز ۳ حرفی انگلیسی را وارد کنید:",
        reply_markup=back_inline(f"folder_{folder_id}")
    )

@router.message(DeleteState.waiting_password)
async def delete_file_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = data.get("delete_fid")
    folder_id = data.get("delete_folder")
    
    if not fid or not folder_id:
        await message.answer("❌ خطا در شناسایی فایل.")
        await state.clear()
        return
    
    password = message.text.strip()
    
    if password.lower() != "del":
        await message.answer("❌ رمز اشتباه است. لطفاً مجدداً تلاش کنید.")
        return
    
    # Delete the file
    await db.delete_file(fid)
    await db.update_folder_file_count(folder_id)
    await db.add_log("file_delete", message.from_user.id, f"Deleted file {fid} from folder {folder_id}")
    
    await message.answer(
        "✅ فایل با موفقیت حذف شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 بازگشت به پوشه", callback_data=f"folder_{folder_id}")],
            [InlineKeyboardButton(text="🔙 پوشه‌ها", callback_data="folders_menu")]
        ])
    )
    await state.clear()

@router.callback_query(F.data.startswith("deletefolder_"))
async def delete_folder_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    folder_id = callback.data.replace("deletefolder_", "")
    folder = await db.get_folder(folder_id)
    
    if not folder:
        await callback.message.edit_text("❌ پوشه پیدا نشد.")
        return
    
    if folder.get("name") == TEMP_FOLDER_NAME:
        await callback.message.edit_text(
            "❌ پوشه فایل‌های موقت قابل حذف نیست.",
            reply_markup=await folders_main_kb()
        )
        return
    
    await state.update_data(delete_folder=folder_id)
    await state.set_state(DeleteState.waiting_password)
    await callback.message.edit_text(
        f"🗑 **حذف پوشه: {safe_html(folder.get('name', 'بدون نام'))}**\n\n"
        "⚠️ تمام فایل‌های این پوشه به پوشه فایل‌های موقت منتقل می‌شوند.\n\n"
        "برای تایید حذف، لطفاً رمز ۳ حرفی انگلیسی را وارد کنید:",
        reply_markup=back_inline("folders_menu")
    )

@router.message(DeleteState.waiting_password)
async def delete_folder_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    folder_id = data.get("delete_folder")
    
    if not folder_id:
        await message.answer("❌ خطا در شناسایی پوشه.")
        await state.clear()
        return
    
    password = message.text.strip()
    
    if password.lower() != "del":
        await message.answer("❌ رمز اشتباه است. لطفاً مجدداً تلاش کنید.")
        return
    
    # Delete the folder (files will be moved to temp)
    await db.delete_folder(folder_id)
    await db.add_log("folder_delete", message.from_user.id, f"Deleted folder {folder_id}")
    
    # Get temp folder info
    temp_folder_id = await db.get_or_create_temp_folder()
    temp_folder = await db.get_folder(temp_folder_id)
    
    await message.answer(
        f"✅ **پوشه با موفقیت حذف شد!**\n\n"
        f"📁 تمام فایل‌ها به پوشه فایل‌های موقت منتقل شدند.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 مشاهده فایل‌های موقت", callback_data=f"folder_{temp_folder_id}")],
            [InlineKeyboardButton(text="🔙 پوشه‌ها", callback_data="folders_menu")]
        ])
    )
    await state.clear()

def files_kb(files: Dict, page: int = 0):
    b = InlineKeyboardBuilder()
    items = list(files.items())
    per_page = 6
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    for fid, f in items[start:start+per_page]:
        cap = f.get("caption", "بدون کپشن")[:25]
        icon = type_icons.get(f.get("type", "document"), "📁")
        lock = "🔒" if f.get("password") else ""
        b.row(InlineKeyboardButton(text=f"{icon} {lock} {cap} | 📥{f['downloads']}", callback_data=f"file_{fid}"))
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"files_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"files_pg_{page+1}"))
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    return b.as_markup()

def file_actions_kb(fid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دریافت", callback_data=f"dl_{fid}"), InlineKeyboardButton(text="🔗 لینک", callback_data=f"link_{fid}")],
        [InlineKeyboardButton(text="✏️ کپشن", callback_data=f"editcap_{fid}"), InlineKeyboardButton(text="🔒 قفل", callback_data=f"setpass_{fid}")],
        [InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_{fid}")],
        [InlineKeyboardButton(text="🔙 فایل‌ها", callback_data="files_list")]
    ])

def confirm_delete_kb(fid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله", callback_data=f"delyes_{fid}"), InlineKeyboardButton(text="❌ خیر", callback_data=f"file_{fid}")]
    ])

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
    await callback.message.edit_text(f"📂 صفحه {page+1}", reply_markup=files_kb(await db.get_all_files(), page))

@router.callback_query(F.data.startswith("file_"))
async def file_info(callback: CallbackQuery):
    await callback.answer()
    f = await db.get_file(callback.data.replace("file_", ""))
    if not f:
        await callback.answer("❌ پیدا نشد", show_alert=True)
        return
    lock = "🔒 دارد" if f.get("password") else "🔓 ندارد"
    await callback.message.edit_text(
        f"📁 {safe_html(f.get('caption',''))}\n"
        f"🆔: <code>{safe_html(f['id'])}</code>\n"
        f"📥: {f['downloads']}\n"
        f"{lock}\n"
        f"📅: {f['date'][:10]}",
        reply_markup=file_actions_kb(f['id'])
    )

@router.callback_query(F.data.startswith("dl_"))
async def dl_file(callback: CallbackQuery):
    await callback.answer("📥 ارسال...")
    f = await db.get_file(callback.data.replace("dl_", ""))
    if f:
        await send_file_to_user(callback.message, f)
        await notify_admins_download(callback.bot, f, callback.from_user)

@router.callback_query(F.data.startswith("link_"))
async def get_link(callback: CallbackQuery):
    await callback.answer()
    f = await db.get_file(callback.data.replace("link_", ""))
    if f:
        bot = await callback.bot.get_me()
        link = f"https://t.me/{bot.username}?start={f['id']}"
        await callback.message.answer(f"🔗 <a href='{link}'>کلیک</a>\n<code>{link}</code>")

@router.callback_query(F.data.startswith("editcap_"))
async def edit_cap_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_caption)
    await callback.message.edit_text("✏️ کپشن:", reply_markup=back_inline(f"file_{fid}"))

@router.message(EditState.waiting_caption)
async def edit_cap_save(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_fid"):
        await db.update_caption(data["edit_fid"], message.text)
        await message.answer("✅ ویرایش شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("setpass_"))
async def set_pass_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("setpass_", "")
    f = await db.get_file(fid)
    
    if not f:
        await callback.answer("❌ فایل پیدا نشد", show_alert=True)
        return
    
    if not f.get("password"):
        await callback.message.edit_text(
            "🔓 این فایل رمز ندارد.\nبرای تنظیم رمز، متن مورد نظر را وارد کنید.\n\n"
            "💡 برای حذف رمز، عبارت `remove` را وارد کنید.",
            reply_markup=back_inline(f"file_{fid}")
        )
        await state.update_data(edit_fid=fid)
        await state.set_state(EditState.waiting_password)
        return
    
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_password)
    await callback.message.edit_text(
        f"🔒 رمز فعلی: {f.get('password')}\n\n"
        "✏️ رمز جدید را وارد کنید:\n"
        "💡 برای حذف رمز، عبارت `remove` را وارد کنید.",
        reply_markup=back_inline(f"file_{fid}")
    )

@router.message(EditState.waiting_password)
async def set_pass_save(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_fid"):
        p = "" if message.text.lower() == "remove" else message.text
        await db.update_password(data["edit_fid"], p)
        await message.answer("✅ تنظیم شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("del_"))
async def del_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("⚠️ حذف شود؟", reply_markup=confirm_delete_kb(callback.data.replace("del_", "")))

@router.callback_query(F.data.startswith("delyes_"))
async def del_exec(callback: CallbackQuery):
    fid = callback.data.replace("delyes_", "")
    file_data = await db.get_file(fid)
    folder_id = file_data.get("folder", "") if file_data else ""
    
    await db.delete_file(fid)
    if folder_id:
        await db.update_folder_file_count(folder_id)
    
    await callback.answer("✅ حذف شد")
    await files_list_cb(callback)

@router.message(F.text == "📢 ارسال همگانی")
async def menu_broadcast(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.waiting)
    await message.answer("📢 پیام را بفرستید:", reply_markup=back_inline())

@router.message(F.text == "⚙️ تنظیمات")
async def menu_settings(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    s = await db.get_settings()
    await message.answer("⚙️ تنظیمات", reply_markup=settings_kb(s))

@router.message(F.text == "👮 ادمین‌ها")
async def menu_admins_vip(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    admins = await db.get_admins()
    vips = await db.get_vips()
    txt = "👮 **مدیریت ادمین‌ها و VIP**\n\n**ADMIN:**\n\n"
    if admins:
        for aid, a in admins.items():
            uname = a.get('username', '')
            display = f"@{uname}-admin" if uname else f"`{aid}`-admin"
            txt += f"{display}\n"
    else:
        txt += "هیچ ادمینی نیست\n"
    txt += "\n➖➖➖➖➖➖➖➖➖➖\n\n**VIP:**\n\n"
    if vips:
        for vid, v in vips.items():
            uname = v.get('username', '')
            display = f"@{uname}-vip" if uname else f"`{vid}`-vip"
            txt += f"{display}\n"
    else:
        txt += "هیچ VIP ای نیست\n"
    await message.answer(txt, reply_markup=admins_main_menu_kb())

@router.callback_query(F.data == "admins_menu")
async def admins_menu_cb(callback: CallbackQuery):
    await callback.answer()
    admins = await db.get_admins()
    vips = await db.get_vips()
    txt = "👮 **مدیریت ادمین‌ها و VIP**\n\n**ADMIN:**\n\n"
    if admins:
        for aid, a in admins.items():
            uname = a.get('username', '')
            display = f"@{uname}-admin" if uname else f"`{aid}`-admin"
            txt += f"{display}\n"
    else:
        txt += "هیچ ادمینی نیست\n"
    txt += "\n➖➖➖➖➖➖➖➖➖➖\n\n**VIP:**\n\n"
    if vips:
        for vid, v in vips.items():
            uname = v.get('username', '')
            display = f"@{uname}-vip" if uname else f"`{vid}`-vip"
            txt += f"{display}\n"
    else:
        txt += "هیچ VIP ای نیست\n"
    await callback.message.edit_text(txt, reply_markup=admins_main_menu_kb())

@router.callback_query(F.data == "add_admin_prompt")
async def add_admin_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_add_admin)
    await callback.message.edit_text("👮 **افزودن ادمین**\n\n📌 آیدی عددی یا فوروارد:", reply_markup=back_inline("admins_menu"))

@router.message(SettingsState.waiting_add_admin)
async def save_admin(message: Message, state: FSMContext):
    uid, username, first_name, error = await db.resolve_user_from_input(message.bot, message)
    if error:
        await message.answer(f"{error}", reply_markup=back_inline("admins_menu"))
        return
    if uid:
        if await db.is_admin(uid):
            await message.answer("❌ قبلاً ادمین است.", reply_markup=await get_admin_panel_kb())
        else:
            await db.add_admin(uid, username)
            await db.add_log("admin_add", message.from_user.id, f"Added {uid}")
            display = f"@{username}" if username else first_name or uid
            await message.answer(f"✅ ادمین {display} اضافه شد.", reply_markup=await get_admin_panel_kb())
        await state.clear()

@router.callback_query(F.data == "add_vip_prompt")
async def add_vip_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_add_vip)
    await callback.message.edit_text("⭐ **افزودن VIP**\n\n📌 آیدی عددی یا فوروارد:", reply_markup=back_inline("admins_menu"))

@router.message(SettingsState.waiting_add_vip)
async def save_vip(message: Message, state: FSMContext):
    uid, username, first_name, error = await db.resolve_user_from_input(message.bot, message)
    if error:
        await message.answer(f"{error}", reply_markup=back_inline("admins_menu"))
        return
    if uid:
        if await db.is_vip(uid):
            await message.answer("❌ قبلاً VIP است.", reply_markup=await get_admin_panel_kb())
        else:
            await db.add_vip(uid, username)
            await db.add_log("vip_add", message.from_user.id, f"Added VIP {uid}")
            display = f"@{username}" if username else first_name or uid
            await message.answer(f"✅ VIP {display} اضافه شد.", reply_markup=await get_admin_panel_kb())
        await state.clear()

@router.callback_query(F.data == "remove_privileged")
async def remove_priv(callback: CallbackQuery):
    await callback.answer()
    admins = await db.get_admins()
    vips = await db.get_vips()
    admins_show = {k: v for k, v in admins.items() if str(k) != str(ADMIN_ID)}
    if not admins_show and not vips:
        await callback.answer("❌ هیچکس برای حذف نیست.", show_alert=True)
        return
    await callback.message.edit_text("❌ انتخاب کنید:", reply_markup=remove_privileged_kb(admins_show, vips))

@router.callback_query(F.data.startswith("ra_"))
async def rem_admin(callback: CallbackQuery):
    aid = callback.data.replace("ra_", "")
    await db.remove_admin(int(aid))
    await callback.answer("✅ حذف شد")
    await remove_priv(callback)

@router.callback_query(F.data.startswith("rv_"))
async def rem_vip(callback: CallbackQuery):
    vid = callback.data.replace("rv_", "")
    await db.remove_vip(int(vid))
    await callback.answer("✅ حذف شد")
    await remove_priv(callback)

@router.message(F.text == "📜 گزارشات")
async def menu_logs(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    logs_list = await db.get_logs(20)
    if not logs_list:
        await message.answer("📜 گزارشی نیست.", reply_markup=await get_admin_panel_kb())
        return
    txt = "📜 گزارشات:\n\n" + "\n".join([f"<code>{l['time'][:19]}</code> {l['action']}" for l in logs_list])
    await message.answer(txt[:4000], reply_markup=await get_admin_panel_kb())

@router.message(F.text == "🔗 لینک‌های فعال")
async def menu_links(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    files = await db.get_all_files()
    if not files:
        await message.answer("🔗 لینکی نیست.", reply_markup=await get_admin_panel_kb())
        return
    bot = await message.bot.get_me()
    txt = "🔗 لینک‌ها:\n\n" + "\n".join([f"• {safe_html(f.get('caption','')[:20])}\n  /start {safe_html(fid)}" for fid, f in list(files.items())[:10]])
    await message.answer(txt, reply_markup=await get_admin_panel_kb())

@router.message(F.text == "💾 پشتیبان‌گیری")
async def menu_backup(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    import shutil
    os.makedirs("backups", exist_ok=True)
    fn = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    shutil.make_archive(fn.replace('.zip', ''), 'zip', '.', lambda x: x.endswith('.json'))
    await message.answer_document(FSInputFile(fn), caption="✅ پشتیبان آماده")
    await message.answer("💾 آماده شد.", reply_markup=await get_admin_panel_kb())

@router.message(F.text.contains("ربات فعال است"))
@router.message(F.text.contains("ربات خاموش است"))
async def toggle_bot_from_panel(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    new_status = await db.toggle_bot()
    await db.add_log("toggle", message.from_user.id, f"Bot {'ON' if new_status else 'OFF'}")
    kb = await get_admin_panel_kb()
    if new_status:
        await message.answer("🟢 **ربات روشن شد!**", reply_markup=kb)
    else:
        await message.answer("🔴 **ربات خاموش شد!**", reply_markup=kb)

@router.callback_query(F.data == "toggle_forward_lock")
async def toggle_forward_lock_handler(callback: CallbackQuery):
    await callback.answer()
    new_status = await db.toggle_forward_lock()
    await db.add_log("settings", callback.from_user.id, f"Forward Lock {'ON' if new_status else 'OFF'}")
    s = await db.get_settings()
    await callback.message.edit_text("⚙️ تنظیمات", reply_markup=settings_kb(s))
    if new_status:
        await callback.message.answer("🔒 **قفل فوروارد فعال شد!**")
    else:
        await callback.message.answer("🔓 **قفل فوروارد غیرفعال شد!**")

@router.message(UploadState.waiting)
async def upload_receive(message: Message, state: FSMContext):
    file_id, file_type, file_name = None, "document", ""
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, file_type, file_name = message.video.file_id, "video", message.video.file_name or ""
    elif message.audio:
        file_id, file_type, file_name = message.audio.file_id, "audio", message.audio.file_name or ""
    elif message.voice:
        file_id, file_type = message.voice.file_id, "voice"
    elif message.animation:
        file_id, file_type, file_name = message.animation.file_id, "animation", message.animation.file_name or ""
    elif message.sticker:
        file_id, file_type = message.sticker.file_id, "sticker"
    elif message.document:
        file_id, file_type, file_name = message.document.file_id, "document", message.document.file_name or ""
    if not file_id:
        await message.answer("❌ فایل معتبر نیست.")
        return
    
    data = await state.get_data()
    folder_id = data.get("upload_folder", "")
    
    await state.update_data(file_id=file_id, file_type=file_type, file_name=file_name)
    await state.set_state(UploadState.caption)
    await message.answer("✅ دریافت شد! کپشن:", reply_markup=skip_back_inline())

@router.callback_query(F.data == "skip_caption")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(caption="")
    await state.set_state(UploadState.password)
    await callback.message.edit_text("🔒 رمز؟", reply_markup=skip_pass_inline())

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    await state.update_data(caption=message.text or "")
    await state.set_state(UploadState.password)
    await message.answer("🔒 رمز؟", reply_markup=skip_pass_inline())

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
    folder_id = data.get("upload_folder", "")
    
    await db.add_file({
        "id": fid,
        "file_id": data["file_id"],
        "type": data["file_type"],
        "caption": data.get("caption", ""),
        "file_name": data.get("file_name", ""),
        "password": data.get("password", ""),
        "admin": admin_id,
        "folder": folder_id
    })
    
    if folder_id:
        await db.update_folder_file_count(folder_id)
    
    await db.add_log("upload", admin_id, f"Uploaded {fid} to folder {folder_id}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    icon = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}.get(data["file_type"], "📁")
    
    folder_name = ""
    if folder_id:
        folder = await db.get_folder(folder_id)
        if folder:
            folder_name = folder.get("name", "")
    
    txt = f"✅ **آپلود موفق!**\n\n"
    txt += f"{icon} نوع: {data['file_type']}\n"
    txt += f"🆔 شناسه: <code>{fid}</code>\n"
    if folder_name:
        txt += f"📁 پوشه: {safe_html(folder_name)}\n"
    txt += f"📝 کپشن: {safe_html(data.get('caption', 'بدون کپشن'))}\n"
    if data.get("password"):
        txt += f"🔑 رمز: <code>{safe_html(data['password'])}</code>\n"
    txt += f"\n🔗 لینک استارت کامل:\n<code>{link}</code>"
    
    await message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 مشاهده پوشه", callback_data=f"folder_{folder_id}") if folder_id else InlineKeyboardButton(text="📂 مدیریت فایل‌ها", callback_data="folders_menu")],
        [InlineKeyboardButton(text="🔙 پنل مدیریت", callback_data="panel")]
    ]))
    await state.clear()

@router.message(F.text == "📊 آمار ربات")
async def menu_stats(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    await show_stats_message(message, edit_mode=False)

@router.callback_query(F.data == "show_stats")
async def stats_callback(callback: CallbackQuery):
    await callback.answer()
    await show_stats_message(callback.message, edit_mode=True)

@router.callback_query(F.data == "refresh_stats")
async def refresh_stats(callback: CallbackQuery):
    await callback.answer("🔄 بروزرسانی شد")
    await show_stats_message(callback.message, edit_mode=True)

async def show_stats_message(message: Message, edit_mode: bool = False):
    stats = await db.get_enhanced_stats()
    now = datetime.now()
    lines = [
        "═══════════════════════",
        "  📊 آمار ربات",
        "═══════════════════════",
        "",
        f"👤 کل کاربران: {format_number(stats['total_users'])}",
        f"🟢 کاربران فعال: {format_number(stats['active_users'])}",
        f"📁 کل فایل‌ها: {format_number(stats['total_files'])}",
        f"📥 کل دانلودها: {format_number(stats['total_downloads'])}",
        f"👁 مجموع بازدیدها: {format_number(stats['total_views'])}",
        "",
        "═══════════════════════",
        f"📅 {now.strftime('%Y/%m/%d')}  ⏰ {now.strftime('%H:%M:%S')}"
    ]
    table = "```\n" + "\n".join(lines) + "\n```"
    if edit_mode:
        await message.edit_text(table, reply_markup=stats_kb(), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await message.answer(table, reply_markup=stats_kb(), parse_mode=ParseMode.MARKDOWN_V2)

@router.callback_query(F.data == "force_join_stats")
async def force_join_stats_handler(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    channels = s.get("force_join", [])
    if not channels:
        await callback.message.edit_text("📊 **آمار عضویت اجباری**\n\n❌ هیچ چنلی تنظیم نشده است.", reply_markup=force_join_stats_kb())
        return
    txt = "📊 **آمار عضویت اجباری**\n\n"
    total_members = 0
    bot = callback.bot
    for i, ch in enumerate(channels, 1):
        try:
            count = await bot.get_chat_member_count(ch)
            total_members += count
            txt += f"🔗 چنل {i} ({safe_html(ch)}): {format_number(count)} عضو\n"
        except:
            txt += f"🔗 چنل {i} ({safe_html(ch)}): ❌ دسترسی ندارم\n"
    txt += f"\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n📌 **مجموع اعضای یکتا:** {format_number(total_members)}\n📅 بروزرسانی: {datetime.now().strftime('%H:%M:%S')}"
    await callback.message.edit_text(txt, reply_markup=force_join_stats_kb())

@router.message(F.text == "👥 کاربران")
async def menu_users(message: Message):
    if not await db.is_admin(message.from_user.id):
        return
    await show_users_main_menu(message)

@router.callback_query(F.data == "users_menu")
async def users_menu_cb(callback: CallbackQuery):
    await callback.answer()
    await show_users_main_menu(callback.message)

async def show_users_main_menu(message: Message):
    users = await db.get_all_users()
    total = len(users)
    banned_users = await db.get_banned_users()
    banned = len(banned_users)
    txt = f"👥 **مدیریت کاربران**\n\n👤 کل کاربران: {format_number(total)}\n🚫 کاربران مسدود: {format_number(banned)}"
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(txt, reply_markup=users_main_menu_kb(total, banned))
    else:
        await message.answer(txt, reply_markup=users_main_menu_kb(total, banned))

@router.callback_query(F.data == "users_list_all")
async def users_list_all(callback: CallbackQuery):
    await callback.answer()
    await show_users_page(callback.message, 0)

@router.callback_query(F.data.startswith("u_pg_"))
async def users_page_cb(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("u_pg_", ""))
    await show_users_page(callback.message, page)

async def show_users_page(message: Message, page: int):
    users = await db.get_all_users()
    items = list(users.items())
    per_page = 10
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    page_items = items[start:start+per_page]
    txt = f"📋 کاربران - صفحه {page+1}"
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(txt, reply_markup=users_list_kb(page_items, page, total_pages, "u"))
    else:
        await message.answer(txt, reply_markup=users_list_kb(page_items, page, total_pages, "u"))

@router.callback_query(F.data == "users_list_banned")
async def users_list_banned(callback: CallbackQuery):
    await callback.answer()
    await show_banned_page(callback.message, 0)

@router.callback_query(F.data.startswith("ban_pg_"))
async def banned_page_cb(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("ban_pg_", ""))
    await show_banned_page(callback.message, page)

async def show_banned_page(message: Message, page: int):
    banned = await db.get_banned_users()
    items = list(banned.items())
    per_page = 10
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    page_items = items[start:start+per_page]
    txt = f"🚫 کاربران مسدود - صفحه {page+1}"
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(txt, reply_markup=banned_users_list_kb(page_items, page, total_pages))
    else:
        await message.answer(txt, reply_markup=banned_users_list_kb(page_items, page, total_pages))

@router.callback_query(F.data.startswith("unban_"))
async def unban_user_from_list(callback: CallbackQuery):
    uid = int(callback.data.replace("unban_", ""))
    status, name = await db.toggle_ban(uid)
    await callback.answer(f"✅ {name} رفع مسدود شد")
    await show_banned_page(callback.message, 0)

@router.callback_query(F.data.startswith("userinfo_"))
async def user_info_handler(callback: CallbackQuery):
    await callback.answer()
    uid = int(callback.data.replace("userinfo_", ""))
    u = await db.get_user_info(uid)
    if not u:
        await callback.answer("❌ کاربر پیدا نشد", show_alert=True)
        return
    banned_status = "🚫 مسدود" if u.get("banned") else "✅ آزاد"
    joined = u.get("joined", "")[:10].replace("-", "/") if u.get("joined") else "نامشخص"
    txt = (
        f"╭━━━━━━━━━━━━━━━━━━━━━━━╮\n│   👤 اطلاعات کاربر      │\n╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🆔 آیدی: <code>{uid}</code>\n👤 نام: {safe_html(u.get('name', 'نامشخص'))}\n"
        f"📎 یوزرنیم: @{safe_html(u.get('username', 'ندارد'))}\n📅 تاریخ عضویت: {joined}\n"
        f"📥 تعداد دانلود: {u.get('downloads', 0)}\n👁 تعداد بازدید: {u.get('views', 0)}\n🚫 وضعیت: {banned_status}"
    )
    await callback.message.edit_text(txt, reply_markup=user_info_kb(uid, u.get("banned", False)))

@router.callback_query(F.data.startswith("toggleban_"))
async def toggle_ban_handler(callback: CallbackQuery):
    uid = int(callback.data.replace("toggleban_", ""))
    status, name = await db.toggle_ban(uid)
    await db.add_log("ban", callback.from_user.id, f"Toggled ban for {uid}: {status}")
    await callback.answer(f"{name} {status}")
    await user_info_handler(callback)

@router.callback_query(F.data == "user_search")
async def user_search_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_search_user)
    await callback.message.edit_text(
        "🔍 **جستجوی کاربران**\n\n"
        "📌 لطفاً یکی از موارد زیر را وارد کنید:\n"
        "• 🔢 آیدی عددی\n"
        "• 📎 یوزرنیم\n"
        "• 📤 فوروارد پیام کاربر\n"
        "• 👤 نام کاربر",
        reply_markup=back_inline("users_menu")
    )

@router.message(SettingsState.waiting_search_user)
async def user_search_result(message: Message, state: FSMContext):
    uid = await db.resolve_user_search(message.bot, message)
    if uid:
        u = await db.get_user_info(uid)
        if u:
            banned_status = "🚫 مسدود" if u.get("banned") else "✅ آزاد"
            joined = u.get("joined", "")[:10].replace("-", "/") if u.get("joined") else "نامشخص"
            txt = (
                f"╭━━━━━━━━━━━━━━━━━━━━━━━╮\n│   👤 اطلاعات کاربر      │\n╰━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"🆔 آیدی: <code>{uid}</code>\n👤 نام: {safe_html(u.get('name', 'نامشخص'))}\n"
                f"📎 یوزرنیم: @{safe_html(u.get('username', 'ندارد'))}\n📅 تاریخ عضویت: {joined}\n"
                f"📥 تعداد دانلود: {u.get('downloads', 0)}\n👁 تعداد بازدید: {u.get('views', 0)}\n🚫 وضعیت: {banned_status}"
            )
            await message.answer(txt, reply_markup=user_info_kb(uid, u.get("banned", False)))
            await state.clear()
            return
    await message.answer("❌ کاربری با این مشخصات یافت نشد.\n🔄 لطفاً دوباره تلاش کنید:", reply_markup=back_inline("users_menu"))

@router.callback_query(F.data.startswith("chatstart_"))
async def chat_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    uid = int(callback.data.replace("chatstart_", ""))
    u = await db.get_user_info(uid)
    if not u:
        await callback.answer("❌ کاربر پیدا نشد", show_alert=True)
        return
    await db.start_chat(callback.from_user.id, uid)
    await state.set_state(ChatState.waiting)
    await callback.message.edit_text(
        f"💬 **حالت چت با کاربر {safe_html(u.get('name', 'کاربر'))} (@{safe_html(u.get('username', 'ندارد'))}) فعال شد.**\n\n"
        f"📝 لطفاً پیام خود را ارسال کنید.\nپیام شما مستقیماً برای این کاربر ارسال می‌شود.\nپاسخ کاربر نیز به شما منتقل می‌شود.",
        reply_markup=chat_active_kb()
    )

@router.message(ChatState.waiting)
async def chat_send_message(message: Message, state: FSMContext):
    target_uid = await db.get_chat(message.from_user.id)
    if not target_uid:
        await message.answer("❌ حالت چت فعال نیست.", reply_markup=await get_admin_panel_kb())
        await state.clear()
        return
    try:
        await message.copy_to(target_uid)
        await message.answer("✅ پیام ارسال شد.")
    except Exception as e:
        await message.answer(f"❌ خطا در ارسال پیام: {safe_html(str(e)[:100])}")

@router.callback_query(F.data == "chatend")
async def chat_end(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await db.end_chat(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("🔴 **گفتگو پایان یافت.**", reply_markup=await get_admin_panel_kb())

@router.message(~F.text.startswith("/"), ~F.text.startswith("📤"), ~F.text.startswith("📂"), ~F.text.startswith("📊"), ~F.text.startswith("📢"), ~F.text.startswith("⚙️"), ~F.text.startswith("👥"), ~F.text.startswith("👮"), ~F.text.startswith("📜"), ~F.text.startswith("🔗"), ~F.text.startswith("💾"), ~F.text.contains("ربات فعال"), ~F.text.contains("ربات خاموش"))
async def handle_incoming_message(message: Message):
    if await db.is_admin(message.from_user.id):
        return
    settings = await db.get_settings()
    sessions = settings.get("chat_sessions", {})
    for admin_id_str, user_id_str in sessions.items():
        if int(user_id_str) == message.from_user.id:
            admin_id = int(admin_id_str)
            try:
                await message.copy_to(admin_id)
                await message.answer("✅ پیام شما به پشتیبانی ارسال شد.")
            except:
                pass
            return

@router.callback_query(F.data == "panel")
async def panel_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("👑 پنل مدیریت:", reply_markup=await get_admin_panel_kb())

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("⚙️ تنظیمات", reply_markup=settings_kb(await db.get_settings()))

@router.callback_query(F.data == "edit_texts")
async def texts_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("📝 ویرایش متن‌ها", reply_markup=texts_editor_kb())

@router.callback_query(F.data == "edit_welcome")
async def edit_welcome(callback: CallbackQuery):
    await callback.answer()
    texts = await db.get_texts()
    await callback.message.edit_text(f"👋 نوع: {texts.get('welcome_type','text')}", reply_markup=welcome_type_kb())

@router.callback_query(F.data.startswith("wel_type_"))
async def set_wel_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    wtype = callback.data.replace("wel_type_", "")
    await db.update_text("welcome_type", wtype)
    if wtype == "text":
        await state.set_state(SettingsState.waiting_welcome)
        await callback.message.edit_text("📝 متن:", reply_markup=back_inline("edit_texts"))
    else:
        await state.set_state(SettingsState.waiting_welcome_media)
        await state.update_data(welcome_media_type=wtype)
        await callback.message.edit_text(f"📤 {wtype}:", reply_markup=back_inline("edit_texts"))

@router.message(SettingsState.waiting_welcome)
async def save_wel_text(message: Message, state: FSMContext):
    await db.update_text("welcome_text", message.text)
    await db.update_text("welcome_media", "")
    await message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.message(SettingsState.waiting_welcome_media)
async def recv_wel_media(message: Message, state: FSMContext):
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
        await message.answer("❌ نامعتبر.")
        return
    await state.update_data(welcome_media_id=file_id)
    await state.set_state(SettingsState.waiting_welcome_caption)
    await message.answer("✅ دریافت شد! کپشن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ بدون کپشن", callback_data="skip_wel_cap")]]))

@router.callback_query(F.data == "skip_wel_cap")
async def skip_wel_cap(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await db.update_text("welcome_media", data.get("welcome_media_id", ""))
    await db.update_text("welcome_caption", "")
    await callback.message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.message(SettingsState.waiting_welcome_caption)
async def save_wel_cap(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_text("welcome_media", data.get("welcome_media_id", ""))
    await db.update_text("welcome_caption", message.text or "")
    await message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("edit_"))
async def edit_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    key = callback.data.replace("edit_", "")
    key_map = {
        "help": "help_text",
        "forcejoin": "force_join_text",
        "forcejoin_ok": "force_join_success",
        "forcejoin_fail": "force_join_fail",
        "password": "password_text",
        "banned": "banned_text",
        "maintenance": "maintenance_text"
    }
    text_key = key_map.get(key, key)
    texts = await db.get_texts()
    await state.update_data(edit_text_key=text_key)
    await state.set_state(SettingsState.waiting_text)
    await callback.message.edit_text(
        f"📝 فعلی:\n{texts.get(text_key,'')[:200]}\n\n"
        f"✏️ جدید:",
        reply_markup=back_to_texts_kb()
    )

@router.message(SettingsState.waiting_text)
async def save_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_text_key"):
        await db.update_text(data["edit_text_key"], message.text)
        await message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.callback_query(F.data == "set_timer")
async def timer_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("⏱ تایمر", reply_markup=timer_settings_kb(await db.get_settings()))

@router.callback_query(F.data == "timer_on")
async def timer_on(callback: CallbackQuery):
    await callback.answer()
    await db.update_setting("delete_timer", 300)
    await callback.message.edit_text("✅ روشن (۵ دقیقه)", reply_markup=timer_settings_kb(await db.get_settings()))

@router.callback_query(F.data == "timer_off")
async def timer_off(callback: CallbackQuery):
    await callback.answer()
    await db.update_setting("delete_timer", 0)
    await callback.message.edit_text("✅ خاموش", reply_markup=timer_settings_kb(await db.get_settings()))

@router.callback_query(F.data == "timer_set")
async def timer_set_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text("⏰ زمان (دقیقه):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="set_timer")]]))

@router.message(SettingsState.waiting_timer)
async def timer_save(message: Message, state: FSMContext):
    try:
        mins = int(message.text)
        if mins == 0:
            await db.update_setting("delete_timer", 0)
            await message.answer("✅ خاموش 🔴", reply_markup=back_to_timer_kb())
        elif mins > 0:
            await db.update_setting("delete_timer", mins * 60)
            await message.answer(f"✅ {format_time(mins)} 🟢", reply_markup=back_to_timer_kb())
        await state.clear()
    except:
        await message.answer("❌ عدد معتبر نیست.")

@router.callback_query(F.data == "set_logchan")
async def set_logchan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_logchan)
    await callback.message.edit_text("📢 آیدی:", reply_markup=back_inline("settings"))

@router.message(SettingsState.waiting_logchan)
async def save_logchan(message: Message, state: FSMContext):
    try:
        await message.bot.get_chat(message.text.strip())
        await db.update_setting("log_channel", message.text.strip())
        await message.answer("✅ تنظیم شد.", reply_markup=await get_admin_panel_kb())
        await state.clear()
    except:
        await message.answer("❌ خطا!")

@router.callback_query(F.data == "set_forcejoin")
async def fj_menu(callback: CallbackQuery):
    await callback.answer()
    channels = (await db.get_settings()).get("force_join", [])
    txt = "🔗 چنل‌ها:\n\n" + "\n".join([f"{i}. {ch}" for i, ch in enumerate(channels, 1)]) if channels else "🔗 هیچ چنلی نیست."
    await callback.message.edit_text(txt, reply_markup=force_join_admin_kb(channels))

@router.callback_query(F.data == "fj_add")
async def fj_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_forcejoin)
    await callback.message.edit_text("➕ آیدی:", reply_markup=back_inline("set_forcejoin"))

@router.message(SettingsState.waiting_forcejoin)
async def fj_save(message: Message, state: FSMContext):
    ch = message.text.strip()
    if ch.startswith("@") or ch.startswith("-100"):
        try:
            await message.bot.get_chat(ch)
            if await db.add_force_join(ch):
                await message.answer("✅ اضافه شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 لیست", callback_data="set_forcejoin")]]))
                await state.clear()
        except:
            await message.answer("❌ خطا!")

@router.callback_query(F.data.startswith("fjdel_"))
async def fj_del(callback: CallbackQuery):
    channels = (await db.get_settings()).get("force_join", [])
    prefix = callback.data.replace("fjdel_", "")
    for ch in channels:
        if ch[:20] == prefix:
            await db.remove_force_join(ch)
            break
    await callback.answer("✅ حذف شد")
    await fj_menu(callback)

@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
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
    await prog.edit_text(f"✅ {sent}/{total}\n❌ {failed}", reply_markup=await get_admin_panel_kb())
    await state.clear()

async def on_startup(bot: Bot):
    db.init_files()
    
    # Create temp folder if doesn't exist
    await db.get_or_create_temp_folder()
    
    d = await db._read(ADMINS_FILE)
    if str(ADMIN_ID) not in d.get("admins", {}):
        if "admins" not in d:
            d["admins"] = {}
        d["admins"][str(ADMIN_ID)] = {"role": "owner", "username": ""}
        await db._write(ADMINS_FILE, d)
    s = await db.get_settings()
    if "forward_lock" not in s:
        await db.update_setting("forward_lock", False)
    if "chat_sessions" not in s:
        await db.update_setting("chat_sessions", {})
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 شروع"),
        BotCommand(command="admin", description="👑 پنل مدیریت")
    ])

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
