"""
Telegram File Uploader Bot - v5.1 Professional
Aiogram 3.x | JSON Storage | Railway Ready
Password Protection | Colored Reply Keyboard | Download Reports | Beautiful Links
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
from aiogram.enums import ParseMode
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
            SETTINGS_FILE: {"welcome": "👋 سلام! به ربات آپلود فایل خوش اومدی.", "delete_timer": 300, "force_join": [], "log_channel": ""},
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

db = JSONManager()

# ==================== KEYBOARDS ====================

def admin_main_menu():
    """Main admin ReplyKeyboard with colored buttons"""
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
        input_field_placeholder="👑 یک گزینه از منوی مدیریت انتخاب کنید...",
        selective=True
    )

def user_main_menu():
    """Main user ReplyKeyboard"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 دانلود فایل")],
            [KeyboardButton(text="📊 آمار من"), KeyboardButton(text="ℹ️ راهنما")]
        ],
        resize_keyboard=True,
        input_field_placeholder="👋 یک گزینه انتخاب کنید...",
        selective=True
    )

def back_button():
    """Simple back button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel")]
    ])

def skip_back_buttons(back_cb: str = "panel"):
    """Skip and back buttons"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ رد کردن", callback_data="skip_caption")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]
    ])

def skip_pass_buttons(back_cb: str = "panel"):
    """Skip password and back buttons"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ بدون رمز", callback_data="skip_password")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]
    ])

def files_kb(files: Dict, page: int = 0):
    """Files list inline keyboard"""
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
    """File actions inline keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 دریافت فایل", callback_data=f"dl_{fid}"),
         InlineKeyboardButton(text="🔗 کپی لینک", callback_data=f"link_{fid}")],
        [InlineKeyboardButton(text="✏️ ویرایش کپشن", callback_data=f"editcap_{fid}"),
         InlineKeyboardButton(text="🔒 تغییر رمز", callback_data=f"setpass_{fid}")],
        [InlineKeyboardButton(text="🗑 حذف فایل", callback_data=f"del_{fid}")],
        [InlineKeyboardButton(text="🔙 لیست فایل‌ها", callback_data="files_list")]
    ])

def confirm_delete_kb(fid: str):
    """Delete confirmation"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ بله حذف شود", callback_data=f"delyes_{fid}"),
         InlineKeyboardButton(text="❌ منصرف شدم", callback_data=f"file_{fid}")]
    ])

def users_kb(users: Dict, page: int = 0):
    """Users list inline keyboard"""
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
    """User actions"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 تغییر وضعیت مسدودیت", callback_data=f"ban_{uid}")],
        [InlineKeyboardButton(text="🔙 لیست کاربران", callback_data="users_list")]
    ])

def admins_kb(admins: Dict):
    """Admins management"""
    b = InlineKeyboardBuilder()
    for aid, a in admins.items():
        icon = "👑" if a['role'] == 'owner' else "👮"
        b.row(InlineKeyboardButton(text=f"{icon} {aid} - {a['role']}", callback_data=f"admin_{aid}"))
    b.row(InlineKeyboardButton(text="➕ افزودن ادمین", callback_data="add_admin"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    return b.as_markup()

def settings_kb(settings: Dict):
    """Settings menu"""
    timer = settings.get("delete_timer", 300) // 60
    log_ch = settings.get("log_channel", "تنظیم نشده")
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👋 پیام خوشامد", callback_data="set_welcome"))
    b.row(InlineKeyboardButton(text=f"⏱ تایمر حذف: {timer} دقیقه", callback_data="set_timer"))
    b.row(InlineKeyboardButton(text=f"📢 کانال گزارش: {log_ch}", callback_data="set_logchan"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    return b.as_markup()

def download_notify_kb(file_id: str, user_id: int):
    """Download notification buttons"""
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
    waiting_timer = State()
    waiting_admin_id = State()
    waiting_logchan = State()

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
        await message.answer("🚫 شما مسدود شده‌اید.")
        return
    
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        file_data = await db.get_file(file_id)
        if file_data:
            if file_data.get("password"):
                await state.update_data(pending_file=file_id)
                await state.set_state(PasswordState.waiting)
                await message.answer(
                    "🔒 این فایل دارای رمز عبور است.\nلطفا رمز را وارد کنید:",
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
            await message.answer("❌ فایل پیدا نشد.")
            return
    
    settings = await db.get_settings()
    
    if await db.is_admin(user.id):
        await message.answer(
            settings.get("welcome", "👋 سلام!"),
            reply_markup=admin_main_menu()
        )
    else:
        await message.answer(
            settings.get("welcome", "👋 سلام!"),
            reply_markup=user_main_menu()
        )

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
    
    if not file_data:
        await message.answer("❌ فایل پیدا نشد.")
        await state.clear()
        return
    
    if message.text == file_data.get("password", ""):
        await state.clear()
        await message.answer("✅ رمز صحیح است. در حال ارسال...")
        await send_file_to_user(message, file_data)
        await notify_admins_download(message.bot, file_data, message.from_user)
    else:
        await message.answer("❌ رمز اشتباه است. دوباره تلاش کنید.")

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
        f"{icon} فایل: {file_caption[:50]}\n"
        f"🆔: <code>{file_id}</code>\n"
        f"📊 دانلود: {downloads}\n\n"
        f"👤 کاربر: {user.first_name}\n"
        f"🆔: <code>{user.id}</code>\n"
        f"📎 @{user.username or 'ندارد'}\n"
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

# ==================== REPLY KEYBOARD HANDLERS (منوی رنگی) ====================
@router.message(F.text == "📤 آپلود فایل جدید")
async def menu_upload(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        return
    await state.set_state(UploadState.waiting)
    await message.answer(
        "📤 **آپلود فایل جدید**\n\n"
        "لطفا فایل خود را ارسال کنید.\n"
        "🖼 عکس | 🎬 ویدیو | 🎵 صوت | 🎤 ویس\n"
        "✨ گیف | 🏷 استیکر | 📄 فایل",
        reply_markup=back_button()
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
    await message.answer("📢 پیام خود را برای ارسال همگانی بفرستید:", reply_markup=back_button())

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
        txt += f"• <code>{aid}</code> - {a['role']}\n"
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
        txt += f"<code>{l['time'][:19]}</code> {l['action']}\n"
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
        txt += f"• {f.get('caption','')[:20]}\n  /start {fid}\n\n"
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
    await message.answer("✅ فایل دریافت شد! حالا کپشن را بفرستید:", reply_markup=skip_back_buttons())

@router.callback_query(F.data == "skip_caption")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(caption="")
    await state.set_state(UploadState.password)
    await callback.message.edit_text("🔒 رمز عبور می‌خواهید؟", reply_markup=skip_pass_buttons())

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    await state.update_data(caption=message.text or "")
    await state.set_state(UploadState.password)
    await message.answer("🔒 رمز عبور می‌خواهید؟", reply_markup=skip_pass_buttons())

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
        "id": fid,
        "file_id": data["file_id"],
        "type": data["file_type"],
        "caption": data.get("caption", ""),
        "file_name": data.get("file_name", ""),
        "password": data.get("password", ""),
        "admin": admin_id
    })
    await db.add_log("upload", admin_id, f"Uploaded {fid}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    type_icons = {"photo": "🖼", "video": "🎬", "audio": "🎵", "voice": "🎤", "animation": "✨", "sticker": "🏷", "document": "📄"}
    icon = type_icons.get(data.get("file_type", "document"), "📁")
    lock = "🔒 دارد" if data.get("password") else "🔓 ندارد"
    
    txt = (
        f"✅ **آپلود موفق!**\n\n"
        f"{icon} فایل آپلود شد\n"
        f"🆔: <code>{fid}</code>\n"
        f"📝: {data.get('caption') or 'بدون کپشن'}\n"
        f"{lock}\n"
    )
    if data.get("password"):
        txt += f"🔑 رمز: <code>{data.get('password')}</code>\n\n"
    
    txt += (
        f"🔗 **لینک دانلود:**\n"
        f"<a href='{link}'>📎 کلیک کنید</a>\n"
        f"<code>{link}</code>"
    )
    
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

@router.callback_query(F.data == "files_list")
async def files_list_cb(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("📂 فایلی نیست.", reply_markup=admin_main_menu())
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
    txt = (
        f"📁 **اطلاعات فایل**\n\n"
        f"🆔: <code>{fid}</code>\n"
        f"📝: {f.get('caption','')}\n"
        f"📥: {f['downloads']}\n"
        f"{lock}\n"
        f"📅: {f['date'][:10]}"
    )
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
    pw = f"\n🔑 رمز: <code>{f['password']}</code>" if f.get("password") else ""
    await callback.message.answer(f"🔗 <a href='{link}'>کلیک کنید</a>\n<code>{link}</code>{pw}")

@router.callback_query(F.data.startswith("editcap_"))
async def edit_cap_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_caption)
    await callback.message.edit_text("✏️ کپشن جدید را بفرستید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"file_{fid}")]
    ]))

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
    await callback.message.edit_text("🔒 رمز جدید (remove برای حذف):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"file_{fid}")]
    ]))

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
        await callback.message.edit_text("👥 کاربری نیست.", reply_markup=admin_main_menu())
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
    txt = f"👤 {u.get('name')}\n🆔: <code>{uid}</code>\n📥: {u.get('downloads',0)}\n🚫: {'مسدود' if u.get('banned') else 'آزاد'}"
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
        txt += f"• <code>{aid}</code> - {a['role']}\n"
    await callback.message.edit_text(txt, reply_markup=admins_kb(admins))

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_admin_id)
    await callback.message.edit_text("➕ آیدی عددی ادمین جدید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admins_list")]
    ]))

@router.message(SettingsState.waiting_admin_id)
async def add_admin_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        await db.add_admin(uid)
        await message.answer(f"✅ ادمین <code>{uid}</code> اضافه شد.", reply_markup=admin_main_menu())
    except:
        await message.answer("❌ آیدی معتبر نیست.")
    await state.clear()

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

@router.callback_query(F.data == "set_welcome")
async def set_welcome(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_welcome)
    await callback.message.edit_text("👋 پیام خوشامد جدید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]
    ]))

@router.message(SettingsState.waiting_welcome)
async def save_welcome(message: Message, state: FSMContext):
    await db.update_setting("welcome", message.text)
    await message.answer("✅ ذخیره شد.", reply_markup=admin_main_menu())
    await state.clear()

@router.callback_query(F.data == "set_timer")
async def set_timer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text("⏱ زمان (دقیقه):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]
    ]))

@router.message(SettingsState.waiting_timer)
async def save_timer(message: Message, state: FSMContext):
    try:
        m = int(message.text)
        if 0 <= m <= 60:
            await db.update_setting("delete_timer", m*60)
            await message.answer(f"✅ {m} دقیقه.", reply_markup=admin_main_menu())
    except:
        await message.answer("❌ عدد معتبر نیست.")
    await state.clear()

@router.callback_query(F.data == "set_logchan")
async def set_logchan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_logchan)
    await callback.message.edit_text("📢 آیدی کانال:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="settings")]
    ]))

@router.message(SettingsState.waiting_logchan)
async def save_logchan(message: Message, state: FSMContext):
    await db.update_setting("log_channel", message.text)
    await message.answer(f"✅ تنظیم شد.", reply_markup=admin_main_menu())
    await state.clear()

@router.callback_query(F.data == "settings")
async def settings_cb(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    await callback.message.edit_text("⚙️ تنظیمات", reply_markup=settings_kb(s))

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
    await db.add_log("broadcast", message.from_user.id, f"Sent {sent}/{total}")
    await state.clear()

# ==================== MAIN ====================
async def on_startup(bot: Bot):
    db.init_files()
    d = await db._read(ADMINS_FILE)
    if str(ADMIN_ID) not in d["admins"]:
        d["admins"][str(ADMIN_ID)] = {"role": "owner", "added": datetime.now().isoformat()}
        await db._write(ADMINS_FILE, d)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 شروع"),
        BotCommand(command="admin", description="👑 پنل مدیریت")
    ])
    logger.info("Bot started!")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
