"""
Telegram File Uploader Bot - v11.6 Professional - FULLY FIXED
Aiogram 3.x | JSON Storage | Railway Ready
Fixed Syntax | Code Block Display | All Features
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
    if not text: return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def format_time(minutes: int) -> str:
    if minutes == 0: return "خاموش"
    if minutes < 60: return f"{minutes} دقیقه"
    elif minutes < 1440:
        h = minutes // 60; m = minutes % 60
        return f"{h} ساعت و {m} دقیقه" if m > 0 else f"{h} ساعت"
    else:
        d = minutes // 1440; h = (minutes % 1440) // 60
        return f"{d} روز و {h} ساعت" if h > 0 else f"{d} روز"

def format_number(num: int) -> str: return f"{num:,}"

def get_default_texts():
    return {
        "welcome_type": "text",
        "welcome_text": "👋 سلام! به ربات آپلود فایل خوش اومدی.",
        "welcome_media": "", "welcome_caption": "",
        "help_text": "📎 راهنمای ربات:\n\nبرای دریافت فایل، لینک را باز کنید.",
        "force_join_text": "📢 **لطفاً ابتدا در چنل‌های زیر عضو شوید**\n\nپس از عضویت، دکمه بررسی را بزنید.",
        "force_join_success": "✅ **عضویت شما تایید شد!**",
        "force_join_fail": "⚠️ **هنوز عضو نشدید!**",
        "password_text": "🔒 این فایل دارای رمز عبور است.\nلطفا رمز را وارد کنید:",
        "password_correct": "✅ رمز صحیح است. در حال ارسال فایل...",
        "password_wrong": "❌ رمز اشتباه است. دوباره تلاش کنید.",
        "banned_text": "🚫 شما مسدود شده‌اید.",
        "file_not_found": "❌ فایل پیدا نشد.",
        "file_deleted": "✅ فایل حذف شد.",
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
            ADMINS_FILE: {"admins": {}, "vip_users": {}},
            SETTINGS_FILE: {
                "delete_timer": 300, "force_join": [], "log_channel": "",
                "bot_active": True, "forward_lock": False,
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

    async def is_bot_active(self) -> bool: return (await self.get_settings()).get("bot_active", True)
    
    async def toggle_bot(self) -> bool:
        s = await self.get_settings(); s["bot_active"] = not s.get("bot_active", True)
        await self.update_setting("bot_active", s["bot_active"]); return s["bot_active"]

    async def is_forward_locked(self) -> bool: return (await self.get_settings()).get("forward_lock", False)
    
    async def toggle_forward_lock(self) -> bool:
        s = await self.get_settings(); s["forward_lock"] = not s.get("forward_lock", False)
        await self.update_setting("forward_lock", s["forward_lock"]); return s["forward_lock"]

    async def add_user(self, uid: int, data: Dict):
        d = await self._read(USERS_FILE)
        if str(uid) not in d["users"]:
            d["users"][str(uid)] = {"id": uid, "name": data.get("name", ""), "username": data.get("username", ""), "joined": datetime.now().isoformat(), "downloads": 0, "views": 0, "banned": False}
            await self._write(USERS_FILE, d)

    async def inc_views(self, uid: int):
        d = await self._read(USERS_FILE)
        if str(uid) in d["users"]:
            if "views" not in d["users"][str(uid)]: d["users"][str(uid)]["views"] = 0
            d["users"][str(uid)]["views"] += 1; await self._write(USERS_FILE, d)

    async def is_banned(self, uid: int) -> bool: return (await self._read(USERS_FILE))["users"].get(str(uid), {}).get("banned", False)
    
    async def toggle_ban(self, uid: int) -> str:
        d = await self._read(USERS_FILE)
        if str(uid) in d["users"]:
            d["users"][str(uid)]["banned"] = not d["users"][str(uid)].get("banned", False)
            await self._write(USERS_FILE, d)
            return "✅ آزاد شد" if not d["users"][str(uid)]["banned"] else "🚫 مسدود شد"
        return "کاربر پیدا نشد"

    async def is_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE); return str(uid) in d.get("admins", {}) or uid == ADMIN_ID

    async def is_vip(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE); return str(uid) in d.get("vip_users", {})

    async def is_privileged(self, uid: int) -> bool: return await self.is_admin(uid) or await self.is_vip(uid)

    async def add_admin(self, uid: int, username: str = "", role: str = "admin"):
        d = await self._read(ADMINS_FILE)
        if "admins" not in d: d["admins"] = {}
        d["admins"][str(uid)] = {"role": role, "username": username, "added": datetime.now().isoformat()}
        await self._write(ADMINS_FILE, d)

    async def remove_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        if str(uid) in d.get("admins", {}) and str(uid) != str(ADMIN_ID):
            del d["admins"][str(uid)]; await self._write(ADMINS_FILE, d); return True
        return False

    async def get_admins(self) -> Dict: return (await self._read(ADMINS_FILE)).get("admins", {})

    async def add_vip(self, uid: int, username: str = ""):
        d = await self._read(ADMINS_FILE)
        if "vip_users" not in d: d["vip_users"] = {}
        d["vip_users"][str(uid)] = {"username": username, "added": datetime.now().isoformat()}
        await self._write(ADMINS_FILE, d)

    async def remove_vip(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        if str(uid) in d.get("vip_users", {}): del d["vip_users"][str(uid)]; await self._write(ADMINS_FILE, d); return True
        return False

    async def get_vips(self) -> Dict: return (await self._read(ADMINS_FILE)).get("vip_users", {})

    async def resolve_user_from_input(self, bot: Bot, message: Message) -> tuple:
        if message.forward_from: user = message.forward_from; return (user.id, user.username or "", user.first_name, None)
        if message.forward_sender_name: return (None, None, None, "⚠️ Privacy Forward فعال است.\nاز آیدی عددی استفاده کنید.")
        if message.forward_from_chat: return (None, None, None, "❌ پیام از کانال/گروه فوروارد شده!")
        text = message.text.strip() if message.text else ""
        if not text: return (None, None, None, "❌ متنی دریافت نشد.")
        if text.isdigit():
            uid = int(text)
            try:
                chat = await bot.get_chat(uid); return (uid, chat.username or "", chat.first_name or "", None)
            except: return (None, None, None, f"❌ کاربر با آیدی {uid} پیدا نشد.")
        return (None, None, None, "❌ آیدی عددی یا فوروارد پیام.")

    async def add_file(self, data: Dict) -> str:
        d = await self._read(FILES_FILE); fid = data["id"]
        d["files"][fid] = {"id": fid, "file_id": data["file_id"], "type": data["type"], "caption": data.get("caption", ""), "file_name": data.get("file_name", ""), "password": data.get("password", ""), "date": datetime.now().isoformat(), "downloads": 0, "views": 0, "admin": data["admin"]}
        await self._write(FILES_FILE, d); return fid

    async def get_file(self, fid: str) -> Optional[Dict]: return (await self._read(FILES_FILE))["files"].get(fid)
    async def get_all_files(self) -> Dict: return (await self._read(FILES_FILE))["files"]

    async def delete_file(self, fid: str) -> bool:
        d = await self._read(FILES_FILE)
        if fid in d["files"]: del d["files"][fid]; await self._write(FILES_FILE, d); return True
        return False

    async def inc_download(self, fid: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]: d["files"][fid]["downloads"] += 1; await self._write(FILES_FILE, d)

    async def inc_file_views(self, fid: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]:
            if "views" not in d["files"][fid]: d["files"][fid]["views"] = 0
            d["files"][fid]["views"] += 1; await self._write(FILES_FILE, d)

    async def update_caption(self, fid: str, caption: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]: d["files"][fid]["caption"] = caption; await self._write(FILES_FILE, d)

    async def update_password(self, fid: str, password: str):
        d = await self._read(FILES_FILE)
        if fid in d["files"]: d["files"][fid]["password"] = password; await self._write(FILES_FILE, d)

    async def get_enhanced_stats(self) -> Dict:
        users = await self._read(USERS_FILE); files = await self._read(FILES_FILE)
        total_users = len(users["users"])
        active_users = sum(1 for u in users["users"].values() if u.get("downloads", 0) > 0)
        total_files = len(files["files"])
        total_downloads = sum(f.get("downloads", 0) for f in files["files"].values())
        total_views = sum(f.get("views", 0) for f in files["files"].values()) + sum(u.get("views", 0) for u in users["users"].values())
        return {"total_users": total_users, "active_users": active_users, "total_files": total_files, "total_downloads": total_downloads, "total_views": total_views}

    async def get_all_users(self) -> Dict: return (await self._read(USERS_FILE))["users"]

    async def add_log(self, action: str, uid: int, detail: str = ""):
        d = await self._read(LOGS_FILE)
        d["logs"].append({"time": datetime.now().isoformat(), "action": action, "admin": uid, "detail": detail})
        if len(d["logs"]) > 500: d["logs"] = d["logs"][-500:]
        await self._write(LOGS_FILE, d)

    async def get_logs(self, limit: int = 20) -> List: return (await self._read(LOGS_FILE))["logs"][-limit:]
    async def get_settings(self) -> Dict: return await self._read(SETTINGS_FILE)

    async def update_setting(self, key: str, val: Any):
        d = await self._read(SETTINGS_FILE); d[key] = val; await self._write(SETTINGS_FILE, d)

    async def get_texts(self) -> Dict: return (await self.get_settings()).get("texts", get_default_texts())

    async def update_text(self, key: str, val: Any):
        s = await self.get_settings(); texts = s.get("texts", get_default_texts())
        texts[key] = val; await self.update_setting("texts", texts)

    async def add_force_join(self, channel: str) -> bool:
        s = await self.get_settings(); channels = s.get("force_join", [])
        if channel not in channels: channels.append(channel); await self.update_setting("force_join", channels); return True
        return False

    async def remove_force_join(self, channel: str) -> bool:
        s = await self.get_settings(); channels = s.get("force_join", [])
        if channel in channels: channels.remove(channel); await self.update_setting("force_join", channels); return True
        return False

db = JSONManager()

# ==================== KEYBOARDS ====================
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
        ], resize_keyboard=True, input_field_placeholder="👑 یک گزینه انتخاب کنید...", selective=True
    )

def user_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📥 دانلود فایل")], [KeyboardButton(text="📊 آمار من"), KeyboardButton(text="ℹ️ راهنما")]],
        resize_keyboard=True, input_field_placeholder="👋 یک گزینه انتخاب کنید...", selective=True
    )

def back_inline(cb: str = "panel"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]])
def skip_back_inline(back_cb: str = "panel"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ رد کردن", callback_data="skip_caption")], [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]])
def skip_pass_inline(back_cb: str = "panel"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ بدون رمز", callback_data="skip_password")], [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]])
def maintenance_kb(file_id: str = ""): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 تلاش دوباره", callback_data=f"retry_{file_id}")]])

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

def force_join_stats_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت به آمار", callback_data="show_stats")]])

def files_kb(files: Dict, page: int = 0):
    b = InlineKeyboardBuilder(); items = list(files.items()); per_page = 6; total_pages = max(1, (len(items) + per_page - 1) // per_page); start = page * per_page
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    for fid, f in items[start:start+per_page]:
        cap = f.get("caption", "بدون کپشن")[:25]; icon = type_icons.get(f.get("type", "document"), "📁"); lock = "🔒" if f.get("password") else ""
        b.row(InlineKeyboardButton(text=f"{icon} {lock} {cap} | 📥{f['downloads']}", callback_data=f"file_{fid}"))
    if total_pages > 1:
        nav = []
        if page > 0: nav.append(InlineKeyboardButton(text="◀️", callback_data=f"files_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1: nav.append(InlineKeyboardButton(text="▶️", callback_data=f"files_pg_{page+1}"))
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel")); return b.as_markup()

def file_actions_kb(fid: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دریافت", callback_data=f"dl_{fid}"), InlineKeyboardButton(text="🔗 لینک", callback_data=f"link_{fid}")],
        [InlineKeyboardButton(text="✏️ کپشن", callback_data=f"editcap_{fid}"), InlineKeyboardButton(text="🔒 رمز", callback_data=f"setpass_{fid}")],
        [InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_{fid}")], [InlineKeyboardButton(text="🔙 فایل‌ها", callback_data="files_list")]
    ])

def confirm_delete_kb(fid: str): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ بله", callback_data=f"delyes_{fid}"), InlineKeyboardButton(text="❌ خیر", callback_data=f"file_{fid}")]])

def users_kb(users: Dict, page: int = 0):
    b = InlineKeyboardBuilder(); items = list(users.items()); per_page = 6; total_pages = max(1, (len(items) + per_page - 1) // per_page); start = page * per_page
    for uid, u in items[start:start+per_page]:
        name = u.get("name", "کاربر")[:20]; ban = "🚫" if u.get("banned") else "✅"
        b.row(InlineKeyboardButton(text=f"{ban} {name} | 📥{u.get('downloads',0)}", callback_data=f"user_{uid}"))
    if total_pages > 1:
        nav = []
        if page > 0: nav.append(InlineKeyboardButton(text="◀️", callback_data=f"users_pg_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1: nav.append(InlineKeyboardButton(text="▶️", callback_data=f"users_pg_{page+1}"))
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel")); return b.as_markup()

def user_actions_kb(uid: str): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚫 مسدود/آزاد", callback_data=f"ban_{uid}")], [InlineKeyboardButton(text="🔙 کاربران", callback_data="users_list")]])

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
            if str(aid) == str(ADMIN_ID): continue
            uname = a.get('username', ''); display = f"@{uname}-admin" if uname else f"ID:{aid}-admin"
            b.row(InlineKeyboardButton(text=f"❌ {display}", callback_data=f"ra_{aid}"))
    if vips:
        for vid, v in vips.items():
            uname = v.get('username', ''); display = f"@{uname}-vip" if uname else f"ID:{vid}-vip"
            b.row(InlineKeyboardButton(text=f"❌ {display}", callback_data=f"rv_{vid}"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admins_menu")); return b.as_markup()

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
    b.row(InlineKeyboardButton(text="🔙 تنظیمات", callback_data="settings")); return b.as_markup()

def welcome_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 متن", callback_data="wel_type_text")],
        [InlineKeyboardButton(text="🖼 عکس", callback_data="wel_type_photo"), InlineKeyboardButton(text="🎬 ویدیو", callback_data="wel_type_video")],
        [InlineKeyboardButton(text="✨ گیف", callback_data="wel_type_animation"), InlineKeyboardButton(text="🏷 استیکر", callback_data="wel_type_sticker")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="edit_texts")]
    ])

def back_to_texts_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="edit_texts")]])

def timer_settings_kb(settings: Dict):
    timer_val = settings.get("delete_timer", 300); b = InlineKeyboardBuilder()
    if timer_val == 0:
        b.row(InlineKeyboardButton(text="⏱ خاموش 🔴", callback_data="noop")); b.row(InlineKeyboardButton(text="🔵 روشن کردن", callback_data="timer_on"))
    else:
        b.row(InlineKeyboardButton(text=f"⏱ {format_time(timer_val // 60)} 🟢", callback_data="noop")); b.row(InlineKeyboardButton(text="🔴 خاموش کردن", callback_data="timer_off"))
    b.row(InlineKeyboardButton(text="⏰ تنظیم زمان", callback_data="timer_set")); b.row(InlineKeyboardButton(text="🔙 تنظیمات", callback_data="settings"))
    return b.as_markup()

def back_to_timer_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="set_timer")]])

def force_join_admin_kb(channels: List[str]):
    b = InlineKeyboardBuilder()
    if channels:
        for i, ch in enumerate(channels, 1): b.row(InlineKeyboardButton(text=f"❌ چنل {i}: {ch}", callback_data=f"fjdel_{ch[:20]}"))
    b.row(InlineKeyboardButton(text="➕ افزودن", callback_data="fj_add")); b.row(InlineKeyboardButton(text="🔙 تنظیمات", callback_data="settings"))
    return b.as_markup()

def force_join_user_kb(channels: List[str], not_joined: List[tuple]):
    b = InlineKeyboardBuilder()
    for idx, ch in not_joined:
        display = ch.lstrip("@"); url = f"https://t.me/{display}" if ch.startswith("@") else f"https://t.me/c/{ch.replace('-100','')}"
        b.row(InlineKeyboardButton(text=f"📢 چنل {idx}", url=url))
    b.row(InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="fj_check")); return b.as_markup()

def download_notify_kb(file_id: str, user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📁 فایل", callback_data=f"file_{file_id}"), InlineKeyboardButton(text="👤 کاربر", callback_data=f"user_{user_id}")]])

# ==================== STATES ====================
class UploadState(StatesGroup): waiting = State(); caption = State(); password = State()
class EditState(StatesGroup): waiting_caption = State(); waiting_password = State()
class SettingsState(StatesGroup):
    waiting_welcome = State(); waiting_welcome_media = State(); waiting_welcome_caption = State()
    waiting_timer = State(); waiting_admin_id = State(); waiting_logchan = State()
    waiting_forcejoin = State(); waiting_text = State(); waiting_add_admin = State(); waiting_add_vip = State()
class BroadcastState(StatesGroup): waiting = State()
class PasswordState(StatesGroup): waiting = State()

# ==================== ROUTER ====================
router = Router()

# ==================== START ====================
@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    user = message.from_user
    await db.add_user(user.id, {"name": user.first_name, "username": user.username})
    await db.inc_views(user.id)
    if await db.is_banned(user.id):
        texts = await db.get_texts(); await message.answer(texts.get("banned_text", "🚫 مسدود هستید.")); return
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]; await db.inc_file_views(file_id)
        if not await db.is_bot_active() and not await db.is_privileged(user.id):
            texts = await db.get_texts(); await message.answer(texts.get("maintenance_text", "🔧 در حال بروزرسانی"), reply_markup=maintenance_kb(file_id)); return
        file_data = await db.get_file(file_id)
        if file_data:
            if not await db.is_privileged(user.id):
                settings = await db.get_settings(); force_channels = settings.get("force_join", [])
                if force_channels:
                    not_joined = await check_user_joined(message.bot, user.id, force_channels)
                    if not_joined:
                        await state.update_data(pending_file=file_id); texts = await db.get_texts()
                        await message.answer(texts.get("force_join_text", "📢 عضو شوید"), reply_markup=force_join_user_kb(force_channels, not_joined)); return
                if file_data.get("password"):
                    await state.update_data(pending_file=file_id); await state.set_state(PasswordState.waiting); texts = await db.get_texts()
                    await message.answer(texts.get("password_text", "🔒 رمز:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 انصراف", callback_data="cancel_download")]])); return
            await send_file_to_user(message, file_data); await notify_admins_download(message.bot, file_data, user); return
        else: texts = await db.get_texts(); await message.answer(texts.get("file_not_found", "❌ پیدا نشد.")); return
    await send_welcome_message(message, user)

@router.callback_query(F.data.startswith("retry_"))
async def retry_download(callback: CallbackQuery):
    await callback.answer(); file_id = callback.data.replace("retry_", "")
    if not await db.is_bot_active():
        texts = await db.get_texts(); await callback.message.edit_text(texts.get("maintenance_text", "🔧 در حال بروزرسانی"), reply_markup=maintenance_kb(file_id))
        await callback.answer("🔧 هنوز در حال بروزرسانی", show_alert=True); return
    file_data = await db.get_file(file_id)
    if file_data: await callback.message.edit_text("✅ فعال است! در حال ارسال..."); await send_file_to_user(callback.message, file_data); await notify_admins_download(callback.bot, file_data, callback.from_user)
    else: await callback.message.edit_text("❌ فایل پیدا نشد.")

async def send_welcome_message(message: Message, user):
    texts = await db.get_texts(); w_type = texts.get("welcome_type", "text"); w_text = texts.get("welcome_text", "👋 سلام!"); w_media = texts.get("welcome_media", ""); w_cap = texts.get("welcome_caption", "")
    kb = await get_admin_panel_kb() if await db.is_admin(user.id) else user_main_menu()
    try:
        if w_type == "photo" and w_media: await message.answer_photo(w_media, caption=w_cap or w_text, reply_markup=kb)
        elif w_type == "video" and w_media: await message.answer_video(w_media, caption=w_cap or w_text, reply_markup=kb)
        elif w_type == "animation" and w_media: await message.answer_animation(w_media, caption=w_cap or w_text, reply_markup=kb)
        elif w_type == "sticker" and w_media: await message.answer_sticker(w_media); await message.answer(w_cap or w_text, reply_markup=kb)
        else: await message.answer(w_text, reply_markup=kb)
    except: await message.answer(w_text, reply_markup=kb)

async def check_user_joined(bot: Bot, user_id: int, channels: List[str]) -> List[tuple]:
    not_joined = []
    for i, ch in enumerate(channels, 1):
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]: not_joined.append((i, ch))
        except: not_joined.append((i, ch))
    return not_joined

# ==================== FORCE JOIN CHECK ====================
@router.callback_query(F.data == "fj_check")
async def force_join_check(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); user_id = callback.from_user.id; settings = await db.get_settings(); force_channels = settings.get("force_join", []); texts = await db.get_texts()
    not_joined = await check_user_joined(callback.bot, user_id, force_channels)
    if not_joined: await callback.message.edit_text(texts.get("force_join_fail", "⚠️ عضو نشدید!"), reply_markup=force_join_user_kb(force_channels, not_joined)); await callback.answer("❌ عضو نشدید!", show_alert=True)
    else:
        data = await state.get_data(); file_id = data.get("pending_file")
        if file_id:
            file_data = await db.get_file(file_id)
            if file_data: await callback.message.edit_text(texts.get("force_join_success", "✅ تایید شد!")); await send_file_to_user(callback.message, file_data); await notify_admins_download(callback.bot, file_data, callback.from_user); await state.clear()
        else: await callback.message.edit_text(texts.get("force_join_success", "✅ تایید شد!"), reply_markup=user_main_menu()); await state.clear()

@router.callback_query(F.data == "cancel_download")
async def cancel_download(callback: CallbackQuery, state: FSMContext): await callback.answer(); await state.clear(); await callback.message.edit_text("❌ لغو شد.")

# ==================== PASSWORD ====================
@router.message(PasswordState.waiting)
async def check_password(message: Message, state: FSMContext):
    data = await state.get_data(); file_data = await db.get_file(data.get("pending_file", "")); texts = await db.get_texts()
    if file_data and message.text == file_data.get("password", ""): await state.clear(); await message.answer(texts.get("password_correct", "✅ صحیح")); await send_file_to_user(message, file_data); await notify_admins_download(message.bot, file_data, message.from_user)
    else: await message.answer(texts.get("password_wrong", "❌ اشتباه"))

# ==================== NOTIFICATIONS ====================
async def notify_admins_download(bot: Bot, file_data: Dict, user):
    settings = await db.get_settings(); log_ch = settings.get("log_channel", "")
    icon = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}.get(file_data.get("type", "document"), "📁")
    txt = f"📥 **دانلود جدید**\n\n{icon} {safe_html(file_data.get('caption','')[:50])}\n🆔: <code>{safe_html(file_data['id'])}</code>\n📊: {file_data.get('downloads',0)}\n\n👤: {safe_html(user.first_name)}\n🆔: <code>{user.id}</code>\n⏰ {datetime.now().strftime('%H:%M:%S')}"
    if log_ch:
        try: await bot.send_message(log_ch, txt, reply_markup=download_notify_kb(file_data["id"], user.id))
        except: pass
    for aid in (await db.get_admins()).keys():
        if aid != str(user.id):
            try: await bot.send_message(int(aid), txt, reply_markup=download_notify_kb(file_data["id"], user.id))
            except: pass

# ==================== SEND FILE ====================
async def send_file_to_user(message: Message, file_data: Dict):
    fid, cap, ftype = file_data["file_id"], file_data.get("caption", ""), file_data["type"]; protect = await db.is_forward_locked()
    try:
        sent = None
        if ftype == "photo": sent = await message.answer_photo(fid, caption=cap, protect_content=protect)
        elif ftype == "video": sent = await message.answer_video(fid, caption=cap, protect_content=protect)
        elif ftype == "audio": sent = await message.answer_audio(fid, caption=cap, protect_content=protect)
        elif ftype == "voice": sent = await message.answer_voice(fid, protect_content=protect)
        elif ftype == "animation": sent = await message.answer_animation(fid, caption=cap, protect_content=protect)
        elif ftype == "sticker": sent = await message.answer_sticker(fid)
        else: sent = await message.answer_document(fid, caption=cap, protect_content=protect)
        if sent:
            await db.inc_download(file_data["id"]); timer = (await db.get_settings()).get("delete_timer", 300)
            if timer > 0: asyncio.create_task(auto_delete(sent, timer))
    except:
        try: await message.answer_document(fid, caption=cap, protect_content=protect); await db.inc_download(file_data["id"])
        except: pass

async def auto_delete(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

# ==================== REPLY KEYBOARD HANDLERS ====================
@router.message(F.text == "📤 آپلود فایل جدید")
async def menu_upload(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id): return
    await state.set_state(UploadState.waiting); await message.answer("📤 فایل را ارسال کنید:", reply_markup=back_inline())

@router.message(F.text == "📂 مدیریت فایل‌ها")
async def menu_files(message: Message):
    if not await db.is_admin(message.from_user.id): return
    files = await db.get_all_files()
    if not files: await message.answer("📂 فایلی نیست.", reply_markup=await get_admin_panel_kb()); return
    await message.answer(f"📂 فایل‌ها ({len(files)})", reply_markup=files_kb(files))

# ==================== ENHANCED STATISTICS ====================
@router.message(F.text == "📊 آمار ربات")
async def menu_stats(message: Message):
    if not await db.is_admin(message.from_user.id): return
    await show_stats_message(message, edit_mode=False)

@router.callback_query(F.data == "show_stats")
async def stats_callback(callback: CallbackQuery): await callback.answer(); await show_stats_message(callback.message, edit_mode=True)

@router.callback_query(F.data == "refresh_stats")
async def refresh_stats(callback: CallbackQuery): await callback.answer("🔄 بروزرسانی شد"); await show_stats_message(callback.message, edit_mode=True)

async def show_stats_message(message: Message, edit_mode: bool = False):
    stats = await db.get_enhanced_stats(); now = datetime.now()
    lines = ["═══════════════════════", "  📊 آمار ربات", "═══════════════════════", "", f"👤 کل کاربران: {format_number(stats['total_users'])}", f"🟢 کاربران فعال: {format_number(stats['active_users'])}", f"📁 کل فایل‌ها: {format_number(stats['total_files'])}", f"📥 کل دانلودها: {format_number(stats['total_downloads'])}", f"👁 مجموع بازدیدها: {format_number(stats['total_views'])}", "", "═══════════════════════", f"📅 {now.strftime('%Y/%m/%d')}  ⏰ {now.strftime('%H:%M:%S')}"]
    table = "```\n" + "\n".join(lines) + "\n```"
    if edit_mode: await message.edit_text(table, reply_markup=stats_kb(), parse_mode=ParseMode.MARKDOWN_V2)
    else: await message.answer(table, reply_markup=stats_kb(), parse_mode=ParseMode.MARKDOWN_V2)

# ==================== FORCE JOIN STATISTICS ====================
@router.callback_query(F.data == "force_join_stats")
async def force_join_stats_handler(callback: CallbackQuery):
    await callback.answer(); s = await db.get_settings(); channels = s.get("force_join", [])
    if not channels: await callback.message.edit_text("📊 **آمار عضویت اجباری**\n\n❌ هیچ چنلی تنظیم نشده است.", reply_markup=force_join_stats_kb()); return
    txt = "📊 **آمار عضویت اجباری**\n\n"; total_members = 0; bot = callback.bot
    for i, ch in enumerate(channels, 1):
        try: count = await bot.get_chat_member_count(ch); total_members += count; txt += f"🔗 چنل {i} ({safe_html(ch)}): {format_number(count)} عضو\n"
        except: txt += f"🔗 چنل {i} ({safe_html(ch)}): ❌ دسترسی ندارم\n"
    txt += f"\n➖➖➖➖➖➖➖➖➖➖➖➖➖\n\n📌 **مجموع اعضای یکتا:** {format_number(total_members)}\n📅 بروزرسانی: {datetime.now().strftime('%H:%M:%S')}"
    await callback.message.edit_text(txt, reply_markup=force_join_stats_kb())

# ==================== REST OF HANDLERS ====================
@router.message(F.text == "📢 ارسال همگانی")
async def menu_broadcast(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id): return
    await state.set_state(BroadcastState.waiting); await message.answer("📢 پیام را بفرستید:", reply_markup=back_inline())

@router.message(F.text == "⚙️ تنظیمات")
async def menu_settings(message: Message):
    if not await db.is_admin(message.from_user.id): return
    s = await db.get_settings(); await message.answer("⚙️ تنظیمات", reply_markup=settings_kb(s))

@router.message(F.text == "👥 کاربران")
async def menu_users(message: Message):
    if not await db.is_admin(message.from_user.id): return
    users = await db.get_all_users()
    if not users: await message.answer("👥 کاربری نیست.", reply_markup=await get_admin_panel_kb()); return
    await message.answer(f"👥 کاربران ({len(users)})", reply_markup=users_kb(users))

@router.message(F.text == "👮 ادمین‌ها")
async def menu_admins_vip(message: Message):
    if not await db.is_admin(message.from_user.id): return
    admins = await db.get_admins(); vips = await db.get_vips()
    txt = "👮 **مدیریت ادمین‌ها و VIP**\n\n**ADMIN:**\n\n"
    if admins:
        for aid, a in admins.items():
            uname = a.get('username', ''); display = f"@{uname}-admin" if uname else f"`{aid}`-admin"; txt += f"{display}\n"
    else: txt += "هیچ ادمینی نیست\n"
    txt += "\n➖➖➖➖➖➖➖➖➖➖\n\n**VIP:**\n\n"
    if vips:
        for vid, v in vips.items():
            uname = v.get('username', ''); display = f"@{uname}-vip" if uname else f"`{vid}`-vip"; txt += f"{display}\n"
    else: txt += "هیچ VIP ای نیست\n"
    await message.answer(txt, reply_markup=admins_main_menu_kb())

@router.callback_query(F.data == "admins_menu")
async def admins_menu_cb(callback: CallbackQuery):
    await callback.answer(); admins = await db.get_admins(); vips = await db.get_vips()
    txt = "👮 **مدیریت ادمین‌ها و VIP**\n\n**ADMIN:**\n\n"
    if admins:
        for aid, a in admins.items():
            uname = a.get('username', ''); display = f"@{uname}-admin" if uname else f"`{aid}`-admin"; txt += f"{display}\n"
    else: txt += "هیچ ادمینی نیست\n"
    txt += "\n➖➖➖➖➖➖➖➖➖➖\n\n**VIP:**\n\n"
    if vips:
        for vid, v in vips.items():
            uname = v.get('username', ''); display = f"@{uname}-vip" if uname else f"`{vid}`-vip"; txt += f"{display}\n"
    else: txt += "هیچ VIP ای نیست\n"
    await callback.message.edit_text(txt, reply_markup=admins_main_menu_kb())

@router.callback_query(F.data == "add_admin_prompt")
async def add_admin_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(SettingsState.waiting_add_admin)
    await callback.message.edit_text("👮 **افزودن ادمین**\n\n📌 آیدی عددی یا فوروارد:", reply_markup=back_inline("admins_menu"))

@router.message(SettingsState.waiting_add_admin)
async def save_admin(message: Message, state: FSMContext):
    uid, username, first_name, error = await db.resolve_user_from_input(message.bot, message)
    if error: await message.answer(f"{error}", reply_markup=back_inline("admins_menu")); return
    if uid:
        if await db.is_admin(uid): await message.answer("❌ قبلاً ادمین است.", reply_markup=await get_admin_panel_kb())
        else:
            await db.add_admin(uid, username); await db.add_log("admin_add", message.from_user.id, f"Added {uid}")
            display = f"@{username}" if username else first_name or uid
            await message.answer(f"✅ ادمین {display} اضافه شد.", reply_markup=await get_admin_panel_kb())
        await state.clear()

@router.callback_query(F.data == "add_vip_prompt")
async def add_vip_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(SettingsState.waiting_add_vip)
    await callback.message.edit_text("⭐ **افزودن VIP**\n\n📌 آیدی عددی یا فوروارد:", reply_markup=back_inline("admins_menu"))

@router.message(SettingsState.waiting_add_vip)
async def save_vip(message: Message, state: FSMContext):
    uid, username, first_name, error = await db.resolve_user_from_input(message.bot, message)
    if error: await message.answer(f"{error}", reply_markup=back_inline("admins_menu")); return
    if uid:
        if await db.is_vip(uid): await message.answer("❌ قبلاً VIP است.", reply_markup=await get_admin_panel_kb())
        else:
            await db.add_vip(uid, username); await db.add_log("vip_add", message.from_user.id, f"Added VIP {uid}")
            display = f"@{username}" if username else first_name or uid
            await message.answer(f"✅ VIP {display} اضافه شد.", reply_markup=await get_admin_panel_kb())
        await state.clear()

@router.callback_query(F.data == "remove_privileged")
async def remove_priv(callback: CallbackQuery):
    await callback.answer(); admins = await db.get_admins(); vips = await db.get_vips()
    admins_show = {k: v for k, v in admins.items() if str(k) != str(ADMIN_ID)}
    if not admins_show and not vips: await callback.answer("❌ هیچکس برای حذف نیست.", show_alert=True); return
    await callback.message.edit_text("❌ انتخاب کنید:", reply_markup=remove_privileged_kb(admins_show, vips))

@router.callback_query(F.data.startswith("ra_"))
async def rem_admin(callback: CallbackQuery):
    aid = callback.data.replace("ra_", "")
    if await db.remove_admin(int(aid)): await callback.answer("✅ حذف شد")
    await remove_priv(callback)

@router.callback_query(F.data.startswith("rv_"))
async def rem_vip(callback: CallbackQuery):
    vid = callback.data.replace("rv_", "")
    if await db.remove_vip(int(vid)): await callback.answer("✅ حذف شد")
    await remove_priv(callback)

@router.message(F.text == "📜 گزارشات")
async def menu_logs(message: Message):
    if not await db.is_admin(message.from_user.id): return
    logs_list = await db.get_logs(20)
    if not logs_list: await message.answer("📜 گزارشی نیست.", reply_markup=await get_admin_panel_kb()); return
    txt = "📜 گزارشات:\n\n" + "\n".join([f"<code>{l['time'][:19]}</code> {l['action']}" for l in logs_list])
    await message.answer(txt[:4000], reply_markup=await get_admin_panel_kb())

@router.message(F.text == "🔗 لینک‌های فعال")
async def menu_links(message: Message):
    if not await db.is_admin(message.from_user.id): return
    files = await db.get_all_files()
    if not files: await message.answer("🔗 لینکی نیست.", reply_markup=await get_admin_panel_kb()); return
    bot = await message.bot.get_me()
    txt = "🔗 لینک‌ها:\n\n" + "\n".join([f"• {safe_html(f.get('caption','')[:20])}\n  /start {safe_html(fid)}" for fid, f in list(files.items())[:10]])
    await message.answer(txt, reply_markup=await get_admin_panel_kb())

@router.message(F.text == "💾 پشتیبان‌گیری")
async def menu_backup(message: Message):
    if not await db.is_admin(message.from_user.id): return
    import shutil; os.makedirs("backups", exist_ok=True)
    fn = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    shutil.make_archive(fn.replace('.zip', ''), 'zip', '.', lambda x: x.endswith('.json'))
    await message.answer_document(FSInputFile(fn), caption="✅ پشتیبان آماده")
    await message.answer("💾 آماده شد.", reply_markup=await get_admin_panel_kb())

@router.message(F.text.contains("ربات فعال است"))
@router.message(F.text.contains("ربات خاموش است"))
async def toggle_bot_from_panel(message: Message):
    if not await db.is_admin(message.from_user.id): return
    new_status = await db.toggle_bot(); await db.add_log("toggle", message.from_user.id, f"Bot {'ON' if new_status else 'OFF'}")
    kb = await get_admin_panel_kb()
    if new_status: await message.answer("🟢 **ربات روشن شد!**", reply_markup=kb)
    else: await message.answer("🔴 **ربات خاموش شد!**", reply_markup=kb)

@router.callback_query(F.data == "toggle_forward_lock")
async def toggle_forward_lock_handler(callback: CallbackQuery):
    await callback.answer(); new_status = await db.toggle_forward_lock()
    await db.add_log("settings", callback.from_user.id, f"Forward Lock {'ON' if new_status else 'OFF'}")
    s = await db.get_settings(); await callback.message.edit_text("⚙️ تنظیمات", reply_markup=settings_kb(s))
    if new_status: await callback.message.answer("🔒 **قفل فوروارد فعال شد!**")
    else: await callback.message.answer("🔓 **قفل فوروارد غیرفعال شد!**")

# ==================== UPLOAD ====================
@router.message(UploadState.waiting)
async def upload_receive(message: Message, state: FSMContext):
    file_id, file_type, file_name = None, "document", ""
    if message.photo: file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video: file_id, file_type, file_name = message.video.file_id, "video", message.video.file_name or ""
    elif message.audio: file_id, file_type, file_name = message.audio.file_id, "audio", message.audio.file_name or ""
    elif message.voice: file_id, file_type = message.voice.file_id, "voice"
    elif message.animation: file_id, file_type, file_name = message.animation.file_id, "animation", message.animation.file_name or ""
    elif message.sticker: file_id, file_type = message.sticker.file_id, "sticker"
    elif message.document: file_id, file_type, file_name = message.document.file_id, "document", message.document.file_name or ""
    if not file_id: await message.answer("❌ فایل معتبر نیست."); return
    await state.update_data(file_id=file_id, file_type=file_type, file_name=file_name)
    await state.set_state(UploadState.caption)
    await message.answer("✅ دریافت شد! کپشن:", reply_markup=skip_back_inline())

@router.callback_query(F.data == "skip_caption")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.update_data(caption="")
    await state.set_state(UploadState.password); await callback.message.edit_text("🔒 رمز؟", reply_markup=skip_pass_inline())

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    await state.update_data(caption=message.text or "")
    await state.set_state(UploadState.password); await message.answer("🔒 رمز؟", reply_markup=skip_pass_inline())

@router.callback_query(F.data == "skip_password")
async def skip_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.update_data(password="")
    await finalize_upload(callback.message, state, callback.from_user.id)

@router.message(UploadState.password)
async def upload_password(message: Message, state: FSMContext):
    await state.update_data(password=message.text or "")
    await finalize_upload(message, state, message.from_user.id)

async def finalize_upload(message: Message, state: FSMContext, admin_id: int):
    data = await state.get_data(); fid = str(uuid.uuid4())[:8]
    await db.add_file({"id": fid, "file_id": data["file_id"], "type": data["file_type"], "caption": data.get("caption", ""), "file_name": data.get("file_name", ""), "password": data.get("password", ""), "admin": admin_id})
    await db.add_log("upload", admin_id, f"Uploaded {fid}")
    bot = await message.bot.get_me(); link = f"https://t.me/{bot.username}?start={fid}"
    icon = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}.get(data["file_type"], "📁")
    txt = f"✅ آپلود موفق!\n\n{icon}\n🆔: <code>{fid}</code>\n📝: {safe_html(data.get('caption',''))}\n"
    if data.get("password"): txt += f"🔑: <code>{safe_html(data['password'])}</code>\n\n"
    txt += f"🔗: <a href='{link}'>کلیک</a>\n<code>{link}</code>"
    await message.answer(txt, reply_markup=await get_admin_panel_kb()); await state.clear()

# ==================== INLINE CALLBACKS ====================
@router.callback_query(F.data == "panel")
async def panel_callback(callback: CallbackQuery):
    await callback.answer(); await callback.message.answer("👑 پنل مدیریت:", reply_markup=await get_admin_panel_kb())

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery): await callback.answer()

@router.callback_query(F.data == "files_list")
async def files_list_cb(callback: CallbackQuery):
    await callback.answer(); files = await db.get_all_files()
    if not files: await callback.message.edit_text("📂 فایلی نیست."); return
    await callback.message.edit_text(f"📂 فایل‌ها ({len(files)})", reply_markup=files_kb(files))

@router.callback_query(F.data.startswith("files_pg_"))
async def files_page(callback: CallbackQuery):
    await callback.answer(); page = int(callback.data.replace("files_pg_", ""))
    await callback.message.edit_text(f"📂 صفحه {page+1}", reply_markup=files_kb(await db.get_all_files(), page))

@router.callback_query(F.data.startswith("file_"))
async def file_info(callback: CallbackQuery):
    await callback.answer(); f = await db.get_file(callback.data.replace("file_", ""))
    if not f: await callback.answer("❌ پیدا نشد", show_alert=True); return
    lock = "🔒 دارد" if f.get("password") else "🔓 ندارد"
    await callback.message.edit_text(f"📁 {safe_html(f.get('caption',''))}\n🆔: <code>{safe_html(f['id'])}</code>\n📥: {f['downloads']}\n{lock}\n📅: {f['date'][:10]}", reply_markup=file_actions_kb(f['id']))

@router.callback_query(F.data.startswith("dl_"))
async def dl_file(callback: CallbackQuery):
    await callback.answer("📥 ارسال..."); f = await db.get_file(callback.data.replace("dl_", ""))
    if f: await send_file_to_user(callback.message, f); await notify_admins_download(callback.bot, f, callback.from_user)

@router.callback_query(F.data.startswith("link_"))
async def get_link(callback: CallbackQuery):
    await callback.answer(); f = await db.get_file(callback.data.replace("link_", ""))
    if f:
        bot = await callback.bot.get_me(); link = f"https://t.me/{bot.username}?start={f['id']}"
        await callback.message.answer(f"🔗 <a href='{link}'>کلیک</a>\n<code>{link}</code>")

@router.callback_query(F.data.startswith("editcap_"))
async def edit_cap_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid); await state.set_state(EditState.waiting_caption)
    await callback.message.edit_text("✏️ کپشن:", reply_markup=back_inline(f"file_{fid}"))

@router.message(EditState.waiting_caption)
async def edit_cap_save(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_fid"): await db.update_caption(data["edit_fid"], message.text); await message.answer("✅ ویرایش شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("setpass_"))
async def set_pass_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); fid = callback.data.replace("setpass_", "")
    await state.update_data(edit_fid=fid); await state.set_state(EditState.waiting_password)
    await callback.message.edit_text("🔒 رمز:", reply_markup=back_inline(f"file_{fid}"))

@router.message(EditState.waiting_password)
async def set_pass_save(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_fid"):
        p = "" if message.text.lower() == "remove" else message.text
        await db.update_password(data["edit_fid"], p); await message.answer("✅ تنظیم شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("del_"))
async def del_confirm(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("⚠️ حذف شود؟", reply_markup=confirm_delete_kb(callback.data.replace("del_", "")))

@router.callback_query(F.data.startswith("delyes_"))
async def del_exec(callback: CallbackQuery):
    if await db.delete_file(callback.data.replace("delyes_", "")): await callback.answer("✅ حذف شد")
    await files_list_cb(callback)

@router.callback_query(F.data == "users_list")
async def users_list_cb(callback: CallbackQuery):
    await callback.answer(); users = await db.get_all_users()
    if not users: await callback.message.edit_text("👥 کاربری نیست."); return
    await callback.message.edit_text(f"👥 کاربران ({len(users)})", reply_markup=users_kb(users))

@router.callback_query(F.data.startswith("users_pg_"))
async def users_page(callback: CallbackQuery):
    await callback.answer(); page = int(callback.data.replace("users_pg_", ""))
    await callback.message.edit_text(f"👥 صفحه {page+1}", reply_markup=users_kb(await db.get_all_users(), page))

@router.callback_query(F.data.startswith("user_"))
async def user_info_cb(callback: CallbackQuery):
    await callback.answer(); uid = callback.data.replace("user_", ""); u = (await db.get_all_users()).get(uid)
    if u:
        txt = f"👤 {safe_html(u.get('name'))}\n🆔: <code>{uid}</code>\n📥: {u.get('downloads',0)}\n🚫: {'مسدود' if u.get('banned') else 'آزاد'}"
        await callback.message.edit_text(txt, reply_markup=user_actions_kb(uid))

@router.callback_query(F.data.startswith("ban_"))
async def toggle_ban(callback: CallbackQuery):
    await callback.answer(); await callback.answer(await db.toggle_ban(int(callback.data.replace("ban_", ""))))
    await user_info_cb(callback)

# ==================== SETTINGS ====================
@router.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer(); await callback.message.edit_text("⚙️ تنظیمات", reply_markup=settings_kb(await db.get_settings()))

# ==================== TEXTS EDITOR ====================
@router.callback_query(F.data == "edit_texts")
async def texts_menu(callback: CallbackQuery):
    await callback.answer(); await callback.message.edit_text("📝 ویرایش متن‌ها", reply_markup=texts_editor_kb())

@router.callback_query(F.data == "edit_welcome")
async def edit_welcome(callback: CallbackQuery):
    await callback.answer(); texts = await db.get_texts()
    await callback.message.edit_text(f"👋 نوع: {texts.get('welcome_type','text')}", reply_markup=welcome_type_kb())

@router.callback_query(F.data.startswith("wel_type_"))
async def set_wel_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); wtype = callback.data.replace("wel_type_", ""); await db.update_text("welcome_type", wtype)
    if wtype == "text": await state.set_state(SettingsState.waiting_welcome); await callback.message.edit_text("📝 متن:", reply_markup=back_inline("edit_texts"))
    else: await state.set_state(SettingsState.waiting_welcome_media); await state.update_data(welcome_media_type=wtype); await callback.message.edit_text(f"📤 {wtype}:", reply_markup=back_inline("edit_texts"))

@router.message(SettingsState.waiting_welcome)
async def save_wel_text(message: Message, state: FSMContext):
    await db.update_text("welcome_text", message.text); await db.update_text("welcome_media", "")
    await message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb()); await state.clear()

@router.message(SettingsState.waiting_welcome_media)
async def recv_wel_media(message: Message, state: FSMContext):
    data = await state.get_data(); wtype = data.get("welcome_media_type", "photo"); file_id = None
    if wtype == "photo" and message.photo: file_id = message.photo[-1].file_id
    elif wtype == "video" and message.video: file_id = message.video.file_id
    elif wtype == "animation" and message.animation: file_id = message.animation.file_id
    elif wtype == "sticker" and message.sticker: file_id = message.sticker.file_id
    if not file_id: await message.answer("❌ نامعتبر."); return
    await state.update_data(welcome_media_id=file_id); await state.set_state(SettingsState.waiting_welcome_caption)
    await message.answer("✅ دریافت شد! کپشن:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ بدون کپشن", callback_data="skip_wel_cap")]]))

@router.callback_query(F.data == "skip_wel_cap")
async def skip_wel_cap(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); data = await state.get_data()
    await db.update_text("welcome_media", data.get("welcome_media_id", "")); await db.update_text("welcome_caption", "")
    await callback.message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb()); await state.clear()

@router.message(SettingsState.waiting_welcome_caption)
async def save_wel_cap(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_text("welcome_media", data.get("welcome_media_id", "")); await db.update_text("welcome_caption", message.text or "")
    await message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb()); await state.clear()

@router.callback_query(F.data.startswith("edit_"))
async def edit_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); key = callback.data.replace("edit_", "")
    key_map = {"help": "help_text", "forcejoin": "force_join_text", "forcejoin_ok": "force_join_success", "forcejoin_fail": "force_join_fail", "password": "password_text", "banned": "banned_text", "maintenance": "maintenance_text"}
    text_key = key_map.get(key, key); texts = await db.get_texts()
    await state.update_data(edit_text_key=text_key); await state.set_state(SettingsState.waiting_text)
    await callback.message.edit_text(f"📝 فعلی:\n{texts.get(text_key,'')[:200]}\n\n✏️ جدید:", reply_markup=back_to_texts_kb())

@router.message(SettingsState.waiting_text)
async def save_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_text_key"): await db.update_text(data["edit_text_key"], message.text); await message.answer("✅ ذخیره شد.", reply_markup=await get_admin_panel_kb())
    await state.clear()

# ==================== TIMER ====================
@router.callback_query(F.data == "set_timer")
async def timer_menu(callback: CallbackQuery):
    await callback.answer(); await callback.message.edit_text("⏱ تایمر", reply_markup=timer_settings_kb(await db.get_settings()))

@router.callback_query(F.data == "timer_on")
async def timer_on(callback: CallbackQuery):
    await callback.answer(); await db.update_setting("delete_timer", 300)
    await callback.message.edit_text("✅ روشن (۵ دقیقه)", reply_markup=timer_settings_kb(await db.get_settings()))

@router.callback_query(F.data == "timer_off")
async def timer_off(callback: CallbackQuery):
    await callback.answer(); await db.update_setting("delete_timer", 0)
    await callback.message.edit_text("✅ خاموش", reply_markup=timer_settings_kb(await db.get_settings()))

@router.callback_query(F.data == "timer_set")
async def timer_set_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text("⏰ زمان (دقیقه):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="set_timer")]]))

@router.message(SettingsState.waiting_timer)
async def timer_save(message: Message, state: FSMContext):
    try:
        mins = int(message.text)
        if mins == 0: await db.update_setting("delete_timer", 0); await message.answer("✅ خاموش 🔴", reply_markup=back_to_timer_kb())
        elif mins > 0: await db.update_setting("delete_timer", mins * 60); await message.answer(f"✅ {format_time(mins)} 🟢", reply_markup=back_to_timer_kb())
        await state.clear()
    except: await message.answer("❌ عدد معتبر نیست.")

# ==================== LOG CHAN & FORCE JOIN ====================
@router.callback_query(F.data == "set_logchan")
async def set_logchan(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(SettingsState.waiting_logchan)
    await callback.message.edit_text("📢 آیدی:", reply_markup=back_inline("settings"))

@router.message(SettingsState.waiting_logchan)
async def save_logchan(message: Message, state: FSMContext):
    try:
        await message.bot.get_chat(message.text.strip())
        await db.update_setting("log_channel", message.text.strip())
        await message.answer("✅ تنظیم شد.", reply_markup=await get_admin_panel_kb()); await state.clear()
    except: await message.answer("❌ خطا!")

@router.callback_query(F.data == "set_forcejoin")
async def fj_menu(callback: CallbackQuery):
    await callback.answer(); channels = (await db.get_settings()).get("force_join", [])
    txt = "🔗 چنل‌ها:\n\n" + "\n".join([f"{i}. {ch}" for i, ch in enumerate(channels, 1)]) if channels else "🔗 هیچ چنلی نیست."
    await callback.message.edit_text(txt, reply_markup=force_join_admin_kb(channels))

@router.callback_query(F.data == "fj_add")
async def fj_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer(); await state.set_state(SettingsState.waiting_forcejoin)
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
        if ch[:20] == prefix: await db.remove_force_join(ch); break
    await callback.answer("✅ حذف شد"); await fj_menu(callback)

# ==================== BROADCAST ====================
@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    users = await db.get_all_users(); total, sent, failed = len(users), 0, 0
    prog = await message.answer(f"📢 0/{total}")
    for i, uid in enumerate(users.keys()):
        try: await message.copy_to(int(uid)); sent += 1
        except: failed += 1
        if (i+1) % 20 == 0: await prog.edit_text(f"📢 {i+1}/{total}")
        await asyncio.sleep(0.05)
    await prog.edit_text(f"✅ {sent}/{total}\n❌ {failed}", reply_markup=await get_admin_panel_kb()); await state.clear()

# ==================== MAIN ====================
async def on_startup(bot: Bot):
    db.init_files()
    d = await db._read(ADMINS_FILE)
    if str(ADMIN_ID) not in d.get("admins", {}):
        if "admins" not in d: d["admins"] = {}
        d["admins"][str(ADMIN_ID)] = {"role": "owner", "username": ""}
        await db._write(ADMINS_FILE, d)
    s = await db.get_settings()
    if "forward_lock" not in s: await db.update_setting("forward_lock", False)
    await bot.set_my_commands([BotCommand(command="start", description="🚀 شروع"), BotCommand(command="admin", description="👑 پنل مدیریت")])

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage()); dp.include_router(router); dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

