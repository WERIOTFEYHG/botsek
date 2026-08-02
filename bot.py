"""
Telegram File Uploader Bot - v5 Professional
Aiogram 3.x | JSON Storage | Railway Ready
Password Protection | Colored WebApp Buttons | Download Reports | Beautiful Links
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
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
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

# ==================== COLORED WEBAPP KEYBOARDS ====================
# Telegram Mini App button colors: https://core.telegram.org/bots/webapps

def make_button(text: str, callback_data: str = None, url: str = None, 
                pay: bool = False, web_app: WebAppInfo = None) -> InlineKeyboardButton:
    """Create a button with proper formatting"""
    if web_app:
        return InlineKeyboardButton(text=text, web_app=web_app)
    elif url:
        return InlineKeyboardButton(text=text, url=url)
    elif pay:
        return InlineKeyboardButton(text=text, pay=pay)
    else:
        return InlineKeyboardButton(text=text, callback_data=callback_data)

def panel_kb():
    """Main admin panel with colored sections"""
    b = InlineKeyboardBuilder()
    
    # Upload section
    b.row(make_button("📤 آپلود فایل جدید", "upload"))
    
    # Management section
    b.row(
        make_button("📂 مدیریت فایل‌ها", "files_list"),
        make_button("📊 آمار و اطلاعات", "stats")
    )
    
    # Communication section
    b.row(
        make_button("📢 ارسال همگانی", "broadcast"),
        make_button("⚙️ تنظیمات ربات", "settings")
    )
    
    # Admin section
    b.row(
        make_button("👥 مدیریت کاربران", "users_list"),
        make_button("👮 مدیریت ادمین‌ها", "admins_list")
    )
    
    # Logs
    b.row(make_button("📜 گزارشات و لاگ‌ها", "logs"))
    
    return b.as_markup()

def back_kb(cb: str = "panel"):
    """Back button with nice styling"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [make_button("🔙 بازگشت به منوی قبل", cb)]
    ])

def back_and_skip_kb(back_cb: str = "panel"):
    """Back button with skip option"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [make_button("⏭ رد کردن این مرحله", "skip_caption")],
        [make_button("🔙 بازگشت", back_cb)]
    ])

def back_skip_pass_kb(back_cb: str = "panel"):
    """Back button with skip for password"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [make_button("⏭ بدون رمز ادامه بده", "skip_password")],
        [make_button("🔙 بازگشت", back_cb)]
    ])

def files_kb(files: Dict, page: int = 0):
    """Files list with beautiful pagination"""
    b = InlineKeyboardBuilder()
    items = list(files.items())
    per_page = 6
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    
    for fid, f in items[start:start+per_page]:
        cap = f.get("caption", "بدون کپشن")[:25]
        dn = f.get("downloads", 0)
        lock = "🔒" if f.get("password") else ""
        file_type_icon = {
            "photo": "🖼", "video": "🎬", "audio": "🎵",
            "voice": "🎤", "animation": "✨", "sticker": "🏷",
            "document": "📄"
        }.get(f.get("type", "document"), "📁")
        
        b.row(make_button(
            f"{file_type_icon} {lock} {cap} | 📥{dn}",
            f"file_{fid}"
        ))
    
    # Beautiful navigation
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(make_button("◀️ قبلی", f"files_pg_{page-1}"))
        nav_buttons.append(make_button(f"📋 صفحه {page+1} از {total_pages}", "noop"))
        if page < total_pages - 1:
            nav_buttons.append(make_button("بعدی ▶️", f"files_pg_{page+1}"))
        b.row(*nav_buttons)
    
    b.row(make_button("🔙 بازگشت به پنل مدیریت", "panel"))
    return b.as_markup()

def file_actions_kb(fid: str, has_password: bool = False):
    """File actions with all options beautifully arranged"""
    b = InlineKeyboardBuilder()
    
    b.row(
        make_button("📥 دریافت فایل", f"dl_{fid}"),
        make_button("🔗 کپی لینک دانلود", f"link_{fid}")
    )
    b.row(
        make_button("✏️ ویرایش کپشن", f"editcap_{fid}"),
        make_button("🔒 تغییر رمز عبور", f"setpass_{fid}")
    )
    b.row(make_button("🗑 حذف این فایل", f"del_{fid}"))
    b.row(make_button("🔙 بازگشت به لیست فایل‌ها", "files_list"))
    
    return b.as_markup()

def confirm_delete_kb(fid: str):
    """Delete confirmation with clear options"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            make_button("✅ بله، حذف شود", f"delyes_{fid}"),
            make_button("❌ خیر، منصرف شدم", f"file_{fid}")
        ]
    ])

def users_kb(users: Dict, page: int = 0):
    """Users list with beautiful layout"""
    b = InlineKeyboardBuilder()
    items = list(users.items())
    per_page = 6
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    
    for uid, u in items[start:start+per_page]:
        name = u.get("name", "کاربر")[:20]
        ban_status = "🚫" if u.get("banned") else "✅"
        b.row(make_button(
            f"{ban_status} {name} | 📥{u.get('downloads',0)}",
            f"user_{uid}"
        ))
    
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(make_button("◀️ قبلی", f"users_pg_{page-1}"))
        nav_buttons.append(make_button(f"📋 {page+1}/{total_pages}", "noop"))
        if page < total_pages - 1:
            nav_buttons.append(make_button("بعدی ▶️", f"users_pg_{page+1}"))
        b.row(*nav_buttons)
    
    b.row(make_button("🔙 بازگشت به پنل", "panel"))
    return b.as_markup()

def user_actions_kb(uid: str):
    """User actions"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [make_button("🚫 تغییر وضعیت مسدودیت", f"ban_{uid}")],
        [make_button("📊 مشاهده آمار کاربر", f"user_stats_{uid}")],
        [make_button("🔙 بازگشت به لیست کاربران", "users_list")]
    ])

def admins_kb(admins: Dict):
    """Admins list"""
    b = InlineKeyboardBuilder()
    for aid, a in admins.items():
        role_icon = "👑" if a['role'] == 'owner' else "👮"
        b.row(make_button(
            f"{role_icon} {aid} - {a['role']}",
            f"admin_{aid}"
        ))
    b.row(make_button("➕ افزودن ادمین جدید", "add_admin"))
    b.row(make_button("🔙 بازگشت به پنل", "panel"))
    return b.as_markup()

def settings_kb(settings: Dict):
    """Settings menu"""
    b = InlineKeyboardBuilder()
    timer = settings.get("delete_timer", 300) // 60
    log_ch = settings.get("log_channel", "تنظیم نشده")
    
    b.row(make_button(f"👋 ویرایش پیام خوشامد", "set_welcome"))
    b.row(make_button(f"⏱ تایمر حذف فایل: {timer} دقیقه", "set_timer"))
    b.row(make_button(f"📢 کانال گزارش: {log_ch}", "set_logchan"))
    b.row(make_button("🔙 بازگشت به پنل", "panel"))
    return b.as_markup()

def download_notification_kb(file_id: str, user_id: int):
    """Beautiful download notification for admin"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [make_button("📁 مشاهده فایل", f"file_{file_id}")],
        [make_button("👤 پروفایل کاربر", f"user_{user_id}")]
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

# ==================== START COMMAND ====================
@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    user = message.from_user
    await db.add_user(user.id, {"name": user.first_name, "username": user.username})
    
    # Check ban
    if await db.is_banned(user.id):
        await message.answer("🚫 شما مسدود شده‌اید.")
        return
    
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        file_data = await db.get_file(file_id)
        if file_data:
            # Check if file has password
            if file_data.get("password"):
                await state.update_data(pending_file=file_id)
                await state.set_state(PasswordState.waiting)
                await message.answer(
                    "🔒 این فایل دارای رمز عبور است.\n"
                    "لطفا رمز عبور را وارد کنید:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [make_button("🔙 انصراف", callback_data="cancel_download")]
                    ])
                )
                return
            else:
                # Send file and notify admins
                await send_file_to_user(message, file_data)
                await notify_admins_download(message.bot, file_data, user)
                return
        else:
            await message.answer("❌ فایل پیدا نشد یا حذف شده است.")
            return
    
    settings = await db.get_settings()
    await message.answer(settings.get("welcome", "👋 سلام!"))

@router.callback_query(F.data == "cancel_download")
async def cancel_download(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    settings = await db.get_settings()
    await callback.message.edit_text(settings.get("welcome", "👋 سلام!"))

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
        await message.answer("✅ رمز عبور صحیح است. در حال ارسال فایل...")
        await send_file_to_user(message, file_data)
        # Notify admins about download
        await notify_admins_download(message.bot, file_data, message.from_user)
    else:
        await message.answer(
            "❌ رمز عبور اشتباه است.\n"
            "لطفا دوباره تلاش کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [make_button("🔙 انصراف", callback_data="cancel_download")]
            ])
        )

# ==================== DOWNLOAD NOTIFICATION ====================
async def notify_admins_download(bot: Bot, file_data: Dict, user):
    """Send download notification to all admins"""
    settings = await db.get_settings()
    log_channel = settings.get("log_channel", "")
    
    # Get file info
    file_caption = file_data.get("caption", "بدون کپشن")
    file_id = file_data["id"]
    file_type = file_data.get("type", "document")
    downloads = file_data.get("downloads", 0)
    
    type_emoji = {
        "photo": "🖼", "video": "🎬", "audio": "🎵",
        "voice": "🎤", "animation": "✨", "sticker": "🏷",
        "document": "📄"
    }.get(file_type, "📁")
    
    notification_text = (
        f"📥 **دانلود جدید**\n\n"
        f"{type_emoji} فایل: {file_caption[:50]}\n"
        f"🆔 شناسه: <code>{file_id}</code>\n"
        f"📊 تعداد دانلود: {downloads}\n\n"
        f"👤 کاربر: {user.first_name}\n"
        f"🆔 کاربر: <code>{user.id}</code>\n"
        f"📎 یوزرنیم: @{user.username or 'ندارد'}\n"
        f"⏰ زمان: {datetime.now().strftime('%H:%M:%S')}"
    )
    
    # Send to log channel
    if log_channel:
        try:
            await bot.send_message(
                chat_id=log_channel,
                text=notification_text,
                reply_markup=download_notification_kb(file_id, user.id)
            )
        except Exception as e:
            logger.error(f"Failed to send to log channel: {e}")
    
    # Send to all admins
    admins = await db.get_admins()
    for admin_id in admins.keys():
        try:
            if admin_id != str(user.id):  # Don't notify if admin downloaded their own file
                await bot.send_message(
                    chat_id=int(admin_id),
                    text=notification_text,
                    reply_markup=download_notification_kb(file_id, user.id)
                )
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
        else:
            raise Exception("No message sent")
    
    except Exception as e:
        logger.error(f"Send error: {e}")
        try:
            sent = await message.answer_document(fid, caption=cap)
            if sent:
                await db.inc_download(file_data["id"])
                timer = (await db.get_settings()).get("delete_timer", 300)
                if timer > 0:
                    asyncio.create_task(auto_delete(sent, timer))
        except Exception as e2:
            logger.error(f"Fallback error: {e2}")
            await message.answer("❌ خطا در ارسال فایل.")

async def auto_delete(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass

# ==================== ADMIN PANEL ====================
@router.message(Command("admin"))
@router.callback_query(F.data == "panel")
async def admin_panel(event: Message | CallbackQuery):
    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
        edit_mode = True
    else:
        msg = event
        edit_mode = False
    
    if not await db.is_admin(msg.chat.id):
        await msg.answer("⛔ دسترسی غیرمجاز")
        return
    
    text = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃   👑 **پنل مدیریت**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        "به پنل مدیریت حرفه‌ای خوش آمدید!\n"
        "از منوی زیر گزینه مورد نظر را انتخاب کنید."
    )
    
    if edit_mode:
        await msg.edit_text(text, reply_markup=panel_kb())
    else:
        await msg.answer(text, reply_markup=panel_kb())

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

# ==================== UPLOAD ====================
@router.callback_query(F.data == "upload")
async def upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UploadState.waiting)
    await callback.message.edit_text(
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  📤 **آپلود فایل جدید**  ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        "📎 لطفا فایل خود را ارسال کنید.\n\n"
        "✨ **فرمت‌های پشتیبانی شده:**\n"
        "🖼 عکس | 🎬 ویدیو | 🎵 صوت\n"
        "🎤 ویس | ✨ گیف | 🏷 استیکر\n"
        "📄 فایل | 📦 ZIP | 📱 APK | 📕 PDF\n\n"
        "📌 فقط یک فایل ارسال کنید.",
        reply_markup=back_kb()
    )

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
        await message.answer("❌ فایل معتبر نیست. لطفا دوباره تلاش کنید.")
        return
    
    await state.update_data(file_id=file_id, file_type=file_type, file_name=file_name)
    await state.set_state(UploadState.caption)
    await message.answer(
        "✅ **فایل با موفقیت دریافت شد!**\n\n"
        "📝 حالا یک کپشن برای فایل بنویسید.\n"
        "می‌توانید از دکمه رد کردن استفاده کنید.",
        reply_markup=back_and_skip_kb()
    )

@router.callback_query(F.data == "skip_caption")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(caption="")
    await state.set_state(UploadState.password)
    await callback.message.edit_text(
        "🔒 **تنظیم رمز عبور**\n\n"
        "آیا می‌خواهید برای فایل رمز عبور تعیین کنید؟\n"
        "در صورت تمایل رمز را وارد کنید.",
        reply_markup=back_skip_pass_kb()
    )

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    caption = message.text or ""
    await state.update_data(caption=caption)
    await state.set_state(UploadState.password)
    await message.answer(
        "🔒 **تنظیم رمز عبور**\n\n"
        "آیا می‌خواهید برای فایل رمز عبور تعیین کنید؟\n"
        "در صورت تمایل رمز را وارد کنید.",
        reply_markup=back_skip_pass_kb()
    )

@router.callback_query(F.data == "skip_password")
async def skip_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(password="")
    await finalize_upload(callback.message, state)

@router.message(UploadState.password)
async def upload_password(message: Message, state: FSMContext):
    password = message.text or ""
    await state.update_data(password=password)
    await finalize_upload(message, state)

async def finalize_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = str(uuid.uuid4())[:8]
    
    await db.add_file({
        "id": fid,
        "file_id": data["file_id"],
        "type": data["file_type"],
        "caption": data.get("caption", ""),
        "file_name": data.get("file_name", ""),
        "password": data.get("password", ""),
        "admin": message.from_user.id if hasattr(message, 'from_user') else message.chat.id
    })
    await db.add_log("upload", message.from_user.id if hasattr(message, 'from_user') else message.chat.id, f"Uploaded {fid}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    lock_status = "🔒 دارای رمز" if data.get("password") else "🔓 بدون رمز"
    file_type_emoji = {
        "photo": "🖼", "video": "🎬", "audio": "🎵",
        "voice": "🎤", "animation": "✨", "sticker": "🏷",
        "document": "📄"
    }.get(data.get("file_type", "document"), "📁")
    
    success_text = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ✅ **آپلود موفقیت‌آمیز**  ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{file_type_emoji} **فایل با موفقیت ذخیره شد**\n\n"
        f"🆔 شناسه فایل:\n<code>{fid}</code>\n\n"
        f"📝 کپشن: {data.get('caption') or 'بدون کپشن'}\n"
        f"{lock_status}\n"
    )
    
    if data.get("password"):
        success_text += f"🔑 رمز عبور: <code>{data.get('password')}</code>\n\n"
    
    success_text += (
        f"🔗 **لینک دانلود:**\n"
        f"<a href='{link}'>📎 برای دانلود کلیک کنید</a>\n\n"
        f"<code>{link}</code>\n\n"
        f"📌 این لینک را برای کاربران ارسال کنید."
    )
    
    await message.answer(success_text, reply_markup=panel_kb())
    await state.clear()

# ==================== FILES LIST & ACTIONS ====================
@router.callback_query(F.data == "files_list")
async def files_list(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text(
            "📂 **فایل‌ها**\n\n"
            "هنوز هیچ فایلی آپلود نشده است!\n"
            "از دکمه آپلود برای اضافه کردن فایل استفاده کنید.",
            reply_markup=panel_kb()
        )
        return
    
    total_downloads = sum(f["downloads"] for f in files.values())
    
    await callback.message.edit_text(
        f"📂 **فایل‌های آپلود شده**\n\n"
        f"📁 تعداد فایل‌ها: {len(files)}\n"
        f"📥 مجموع دانلودها: {total_downloads}\n\n"
        f"🔒 = دارای رمز | 🔓 = بدون رمز",
        reply_markup=files_kb(files)
    )

@router.callback_query(F.data.startswith("files_pg_"))
async def files_page(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("files_pg_", ""))
    files = await db.get_all_files()
    await callback.message.edit_text(
        f"📂 **فایل‌ها** (صفحه {page+1}):",
        reply_markup=files_kb(files, page)
    )

@router.callback_query(F.data.startswith("file_"))
async def file_info(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("file_", "")
    f = await db.get_file(fid)
    if not f:
        await callback.answer("❌ فایل پیدا نشد.", show_alert=True)
        return
    
    lock = "🔒 دارد" if f.get("password") else "🔓 ندارد"
    file_type_emoji = {
        "photo": "🖼", "video": "🎬", "audio": "🎵",
        "voice": "🎤", "animation": "✨", "sticker": "🏷",
        "document": "📄"
    }.get(f.get("type", "document"), "📁")
    
    txt = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        f"┃  {file_type_emoji} **اطلاعات فایل**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🆔 شناسه: <code>{f['id']}</code>\n"
        f"📝 کپشن: {f.get('caption') or 'بدون کپشن'}\n"
        f"📄 نام فایل: {f.get('file_name') or 'نامشخص'}\n"
        f"🔒 وضعیت رمز: {lock}\n"
        f"📥 تعداد دانلود: {f['downloads']} بار\n"
        f"📅 تاریخ آپلود: {f['date'][:10]}\n"
    )
    await callback.message.edit_text(txt, reply_markup=file_actions_kb(fid, bool(f.get("password"))))

@router.callback_query(F.data.startswith("dl_"))
async def download_file(callback: CallbackQuery):
    await callback.answer("📥 در حال ارسال فایل...")
    fid = callback.data.replace("dl_", "")
    f = await db.get_file(fid)
    if f:
        await send_file_to_user(callback.message, f)
        await notify_admins_download(callback.bot, f, callback.from_user)

@router.callback_query(F.data.startswith("link_"))
async def get_file_link(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("link_", "")
    f = await db.get_file(fid)
    if not f:
        await callback.answer("❌ فایل پیدا نشد.", show_alert=True)
        return
    
    bot = await callback.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    password_text = f"\n🔑 رمز عبور: <code>{f['password']}</code>" if f.get("password") else ""
    
    link_text = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  🔗 **لینک دانلود فایل**  ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"📎 <a href='{link}'>برای دانلود کلیک کنید</a>\n\n"
        f"<code>{link}</code>\n"
        f"{password_text}\n\n"
        f"📌 این لینک را کپی کرده و برای دیگران ارسال کنید."
    )
    
    await callback.message.answer(link_text)

@router.callback_query(F.data.startswith("editcap_"))
async def edit_caption_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_caption)
    await callback.message.edit_text(
        "✏️ **ویرایش کپشن**\n\n"
        "لطفا کپشن جدید را وارد کنید:",
        reply_markup=back_kb(f"file_{fid}")
    )

@router.message(EditState.waiting_caption)
async def edit_caption_save(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = data.get("edit_fid")
    if fid:
        await db.update_caption(fid, message.text)
        await db.add_log("edit", message.from_user.id, f"Edited caption {fid}")
        await message.answer("✅ کپشن با موفقیت ویرایش شد.", reply_markup=panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("setpass_"))
async def set_password_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("setpass_", "")
    f = await db.get_file(fid)
    current = f.get("password", "") if f else ""
    
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_password)
    
    await callback.message.edit_text(
        f"🔒 **تغییر رمز عبور**\n\n"
        f"رمز فعلی: {current or 'ندارد'}\n\n"
        "رمز جدید را وارد کنید.\n"
        "برای حذف رمز، کلمه remove را بفرستید.",
        reply_markup=back_kb(f"file_{fid}")
    )

@router.message(EditState.waiting_password)
async def set_password_save(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = data.get("edit_fid")
    if fid:
        new_pass = "" if message.text.lower() == "remove" else message.text
        await db.update_password(fid, new_pass)
        await db.add_log("edit", message.from_user.id, f"Changed password for {fid}")
        
        if new_pass:
            await message.answer(f"✅ رمز عبور تنظیم شد: <code>{new_pass}</code>", reply_markup=panel_kb())
        else:
            await message.answer("✅ رمز عبور حذف شد.", reply_markup=panel_kb())
    await state.clear()

@router.callback_query(F.data.startswith("del_"))
async def delete_file_confirm(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("del_", "")
    await callback.message.edit_text(
        "⚠️ **هشدار حذف فایل**\n\n"
        "آیا از حذف این فایل اطمینان دارید؟\n"
        "این عمل قابل بازگشت نیست و لینک فایل از کار می‌افتد.",
        reply_markup=confirm_delete_kb(fid)
    )

@router.callback_query(F.data.startswith("delyes_"))
async def delete_file_exec(callback: CallbackQuery):
    fid = callback.data.replace("delyes_", "")
    if await db.delete_file(fid):
        await db.add_log("delete", callback.from_user.id, f"Deleted {fid}")
        await callback.answer("✅ فایل با موفقیت حذف شد.")
        await files_list(callback)
    else:
        await callback.answer("❌ خطا در حذف فایل.", show_alert=True)

# ==================== USERS ====================
@router.callback_query(F.data == "users_list")
async def users_list(callback: CallbackQuery):
    await callback.answer()
    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text(
            "👥 **کاربران**\n\n"
            "هنوز هیچ کاربری ثبت نام نکرده است.",
            reply_markup=panel_kb()
        )
        return
    await callback.message.edit_text(
        f"👥 **کاربران ثبت نام شده** ({len(users)} نفر):",
        reply_markup=users_kb(users)
    )

@router.callback_query(F.data.startswith("users_pg_"))
async def users_page(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("users_pg_", ""))
    users = await db.get_all_users()
    await callback.message.edit_text(f"👥 **کاربران** (صفحه {page+1}):", reply_markup=users_kb(users, page))

@router.callback_query(F.data.startswith("user_"))
async def user_info(callback: CallbackQuery):
    await callback.answer()
    uid = callback.data.replace("user_", "")
    users = await db.get_all_users()
    u = users.get(uid)
    if not u:
        await callback.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    
    txt = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  👤 **اطلاعات کاربر**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"🆔 شناسه: <code>{uid}</code>\n"
        f"👤 نام: {u.get('name', 'نامشخص')}\n"
        f"📎 یوزرنیم: @{u.get('username') or 'ندارد'}\n"
        f"📥 تعداد دانلود: {u.get('downloads', 0)}\n"
        f"🚫 وضعیت: {'مسدود' if u.get('banned') else 'آزاد'}\n"
        f"📅 تاریخ عضویت: {u.get('joined', '')[:10]}\n"
    )
    await callback.message.edit_text(txt, reply_markup=user_actions_kb(uid))

@router.callback_query(F.data.startswith("ban_"))
async def toggle_ban(callback: CallbackQuery):
    await callback.answer()
    uid = callback.data.replace("ban_", "")
    result = await db.toggle_ban(int(uid))
    await db.add_log("ban", callback.from_user.id, f"Toggled ban for {uid}")
    await callback.answer(result)
    await user_info(callback)

@router.callback_query(F.data.startswith("user_stats_"))
async def user_stats(callback: CallbackQuery):
    await callback.answer()
    uid = callback.data.replace("user_stats_", "")
    users = await db.get_all_users()
    u = users.get(uid)
    if u:
        await callback.answer(
            f"📊 {u.get('name')}: {u.get('downloads', 0)} دانلود",
            show_alert=True
        )

# ==================== ADMINS ====================
@router.callback_query(F.data == "admins_list")
async def admins_list(callback: CallbackQuery):
    await callback.answer()
    admins = await db.get_admins()
    txt = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  👮 **لیست ادمین‌ها**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
    )
    for aid, a in admins.items():
        txt += f"• <code>{aid}</code> - {a['role']}\n"
    await callback.message.edit_text(txt, reply_markup=admins_kb(admins))

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_admin_id)
    await callback.message.edit_text(
        "➕ **افزودن ادمین جدید**\n\n"
        "لطفا آیدی عددی ادمین جدید را ارسال کنید:",
        reply_markup=back_kb("admins_list")
    )

@router.message(SettingsState.waiting_admin_id)
async def add_admin_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        await db.add_admin(uid)
        await db.add_log("admin_add", message.from_user.id, f"Added admin {uid}")
        await message.answer(f"✅ ادمین <code>{uid}</code> با موفقیت اضافه شد.", reply_markup=panel_kb())
    except:
        await message.answer("❌ لطفا یک آیدی عددی معتبر وارد کنید.")
    await state.clear()

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    await callback.answer()
    aid = callback.data.replace("admin_", "")
    if aid == str(ADMIN_ID):
        await callback.answer("❌ نمی‌توانید مالک اصلی را حذف کنید.", show_alert=True)
        return
    if await db.remove_admin(int(aid)):
        await db.add_log("admin_remove", callback.from_user.id, f"Removed {aid}")
        await callback.answer("✅ ادمین حذف شد.")
    else:
        await callback.answer("❌ خطا در حذف ادمین.", show_alert=True)
    await admins_list(callback)

# ==================== STATS ====================
@router.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_stats()
    await callback.message.edit_text(
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  📊 **آمار و اطلاعات**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"👥 تعداد کاربران: {s['users']}\n"
        f"📁 تعداد فایل‌ها: {s['files']}\n"
        f"📥 مجموع دانلودها: {s['downloads']}\n\n"
        f"📌 بروزرسانی: {datetime.now().strftime('%H:%M:%S')}",
        reply_markup=panel_kb()
    )

# ==================== SETTINGS ====================
@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    await callback.message.edit_text(
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ⚙️ **تنظیمات ربات**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯",
        reply_markup=settings_kb(s)
    )

@router.callback_query(F.data == "set_welcome")
async def set_welcome(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_welcome)
    await callback.message.edit_text(
        "👋 **ویرایش پیام خوشامد**\n\n"
        "لطفا متن پیام خوشامد جدید را وارد کنید:",
        reply_markup=back_kb("settings")
    )

@router.message(SettingsState.waiting_welcome)
async def save_welcome(message: Message, state: FSMContext):
    await db.update_setting("welcome", message.text)
    await db.add_log("settings", message.from_user.id, "Updated welcome")
    await message.answer("✅ پیام خوشامد با موفقیت ذخیره شد.", reply_markup=panel_kb())
    await state.clear()

@router.callback_query(F.data == "set_timer")
async def set_timer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text(
        "⏱ **تنظیم تایمر حذف فایل**\n\n"
        "لطفا زمان را به دقیقه وارد کنید:\n"
        "0 = غیرفعال | 1-60 دقیقه\n\n"
        "پیش‌فرض: 5 دقیقه",
        reply_markup=back_kb("settings")
    )

@router.message(SettingsState.waiting_timer)
async def save_timer(message: Message, state: FSMContext):
    try:
        mins = int(message.text)
        if 0 <= mins <= 60:
            await db.update_setting("delete_timer", mins * 60)
            await db.add_log("settings", message.from_user.id, f"Timer set to {mins}m")
            await message.answer(f"✅ تایمر روی {mins} دقیقه تنظیم شد.", reply_markup=panel_kb())
        else:
            await message.answer("❌ عدد باید بین 0 تا 60 باشد.")
            return
    except:
        await message.answer("❌ لطفا یک عدد معتبر وارد کنید.")
    await state.clear()

@router.callback_query(F.data == "set_logchan")
async def set_logchan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_logchan)
    await callback.message.edit_text(
        "📢 **تنظیم کانال گزارش**\n\n"
        "لطفا آیدی کانال یا گروه را ارسال کنید.\n"
        "مثال: @channel یا -100123456\n\n"
        "گزارش دانلودها به این کانال ارسال می‌شود.",
        reply_markup=back_kb("settings")
    )

@router.message(SettingsState.waiting_logchan)
async def save_logchan(message: Message, state: FSMContext):
    await db.update_setting("log_channel", message.text)
    await db.add_log("settings", message.from_user.id, f"Log channel set to {message.text}")
    await message.answer(f"✅ کانال گزارش تنظیم شد: {message.text}", reply_markup=panel_kb())
    await state.clear()

# ==================== BROADCAST ====================
@router.callback_query(F.data == "broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BroadcastState.waiting)
    await callback.message.edit_text(
        "📢 **ارسال همگانی**\n\n"
        "لطفا پیام خود را ارسال کنید.\n"
        "می‌توانید متن، عکس، ویدیو یا هر فایلی بفرستید.\n\n"
        "⚠️ این پیام برای همه کاربران ارسال خواهد شد.",
        reply_markup=back_kb()
    )

@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    users = await db.get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    
    progress = await message.answer(f"📢 در حال ارسال به {total} کاربر...\n0%")
    
    for i, uid in enumerate(users.keys()):
        try:
            await message.copy_to(chat_id=int(uid))
            sent += 1
        except:
            failed += 1
        
        if (i + 1) % 20 == 0:
            pct = int((i+1)/total*100)
            try:
                await progress.edit_text(f"📢 در حال ارسال...\n{i+1}/{total} ({pct}%)")
            except:
                pass
        await asyncio.sleep(0.05)
    
    await db.add_log("broadcast", message.from_user.id, f"Sent to {sent}/{total}")
    await progress.edit_text(
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  ✅ **ارسال پایان یافت**  ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
        f"✅ موفق: {sent}\n"
        f"❌ ناموفق: {failed}\n"
        f"📊 مجموع: {total}\n\n"
        f"📈成功率: {int(sent/total*100) if total > 0 else 0}%",
        reply_markup=panel_kb()
    )
    await state.clear()

# ==================== LOGS ====================
@router.callback_query(F.data == "logs")
async def logs(callback: CallbackQuery):
    await callback.answer()
    logs_list = await db.get_logs(20)
    if not logs_list:
        await callback.message.edit_text("📜 هیچ گزارشی ثبت نشده.", reply_markup=panel_kb())
        return
    
    txt = (
        "╭━━━━━━━━━━━━━━━━━━╮\n"
        "┃  📜 **گزارشات ربات**   ┃\n"
        "╰━━━━━━━━━━━━━━━━━━╯\n\n"
    )
    for l in logs_list:
        txt += f"<code>{l['time'][:19]}</code>\n"
        txt += f"📌 {l['action']} | ادمین: {l['admin']}\n"
        if l.get('detail'):
            txt += f"  ↳ {l['detail'][:50]}\n"
        txt += "─" * 20 + "\n"
    
    await callback.message.edit_text(txt[:4000], reply_markup=panel_kb())

# ==================== MAIN ====================
async def on_startup(bot: Bot):
    db.init_files()
    d = await db._read(ADMINS_FILE)
    if str(ADMIN_ID) not in d["admins"]:
        d["admins"][str(ADMIN_ID)] = {"role": "owner", "added": datetime.now().isoformat()}
        await db._write(ADMINS_FILE, d)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 شروع ربات"),
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
