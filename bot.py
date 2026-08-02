"""
Telegram File Uploader Bot - v4 Professional
Aiogram 3.x | JSON Storage | Railway Ready
Password Protection | Colored Buttons | Professional UI
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
    InlineKeyboardButton, FSInputFile, BotCommand, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove, WebAppInfo
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
            SETTINGS_FILE: {"welcome": "👋 سلام! به ربات آپلود فایل خوش اومدی.", "delete_timer": 300, "force_join": []},
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

# ==================== KEYBOARDS (Colored with emoji & WebApp style) ====================

# Color codes for Telegram buttons (using emoji for visual effect)
# 🔵 blue | 🟢 green | 🔴 red | 🟡 yellow | 🟣 purple | ⚪ white | 🟠 orange

def panel_kb():
    """Main admin panel with colored buttons"""
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 آپلود فایل", callback_data="upload"))
    b.row(
        InlineKeyboardButton(text="📂 فایل‌ها", callback_data="files_list"),
        InlineKeyboardButton(text="📊 آمار", callback_data="stats")
    )
    b.row(
        InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="broadcast"),
        InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="settings")
    )
    b.row(
        InlineKeyboardButton(text="👥 کاربران", callback_data="users_list"),
        InlineKeyboardButton(text="👮 ادمین‌ها", callback_data="admins_list")
    )
    b.row(InlineKeyboardButton(text="📜 گزارشات", callback_data="logs"))
    return b.as_markup()

def back_kb(cb: str = "panel"):
    """Back button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]
    ])

def back_and_skip_kb(back_cb: str = "panel"):
    """Back button with skip option"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ رد کردن", callback_data="skip_caption")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)]
    ])

def files_kb(files: Dict, page: int = 0):
    """Files list with pagination"""
    b = InlineKeyboardBuilder()
    items = list(files.items())
    per_page = 8
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    
    for fid, f in items[start:start+per_page]:
        cap = f.get("caption", "بدون کپشن")[:20]
        dn = f.get("downloads", 0)
        lock = "🔒" if f.get("password") else "🔓"
        b.row(InlineKeyboardButton(
            text=f"{lock} {cap} | 📥{dn}",
            callback_data=f"file_{fid}"
        ))
    
    # Navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"files_pg_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"files_pg_{page+1}"))
    if nav_buttons:
        b.row(*nav_buttons)
    
    b.row(InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="panel"))
    return b.as_markup()

def file_actions_kb(fid: str, has_password: bool = False):
    """File actions with all options"""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📥 دانلود", callback_data=f"dl_{fid}"),
        InlineKeyboardButton(text="🔗 دریافت لینک", callback_data=f"link_{fid}")
    )
    b.row(
        InlineKeyboardButton(text="✏️ ویرایش کپشن", callback_data=f"editcap_{fid}"),
        InlineKeyboardButton(text="🔒 تغییر رمز", callback_data=f"setpass_{fid}")
    )
    b.row(
        InlineKeyboardButton(text="🗑 حذف فایل", callback_data=f"del_{fid}")
    )
    b.row(InlineKeyboardButton(text="🔙 بازگشت به فایل‌ها", callback_data="files_list"))
    return b.as_markup()

def confirm_delete_kb(fid: str):
    """Delete confirmation"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ بله، حذف کن", callback_data=f"delyes_{fid}"),
            InlineKeyboardButton(text="❌ خیر", callback_data=f"file_{fid}")
        ]
    ])

def users_kb(users: Dict, page: int = 0):
    """Users list with pagination"""
    b = InlineKeyboardBuilder()
    items = list(users.items())
    per_page = 8
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    start = page * per_page
    
    for uid, u in items[start:start+per_page]:
        name = u.get("name", "کاربر")[:15]
        ban_status = "🚫" if u.get("banned") else "✅"
        b.row(InlineKeyboardButton(
            text=f"{ban_status} {name} | 📥{u.get('downloads',0)}",
            callback_data=f"user_{uid}"
        ))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"users_pg_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"users_pg_{page+1}"))
    if nav_buttons:
        b.row(*nav_buttons)
    
    b.row(InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="panel"))
    return b.as_markup()

def user_actions_kb(uid: str):
    """User actions"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 مسدود/آزاد کردن", callback_data=f"ban_{uid}")],
        [InlineKeyboardButton(text="🔙 بازگشت به کاربران", callback_data="users_list")]
    ])

def admins_kb(admins: Dict):
    """Admins list"""
    b = InlineKeyboardBuilder()
    for aid, a in admins.items():
        role_icon = "👑" if a['role'] == 'owner' else "👮"
        b.row(InlineKeyboardButton(
            text=f"{role_icon} {aid} - {a['role']}",
            callback_data=f"admin_{aid}"
        ))
    b.row(InlineKeyboardButton(text="➕ افزودن ادمین جدید", callback_data="add_admin"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="panel"))
    return b.as_markup()

def settings_kb(settings: Dict):
    """Settings menu"""
    b = InlineKeyboardBuilder()
    timer = settings.get("delete_timer", 300) // 60
    b.row(InlineKeyboardButton(text=f"👋 پیام خوشامد", callback_data="set_welcome"))
    b.row(InlineKeyboardButton(text=f"⏱ تایمر حذف: {timer} دقیقه", callback_data="set_timer"))
    b.row(InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="panel"))
    return b.as_markup()

def broadcast_kb():
    """Broadcast menu"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="panel")]
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
                        [InlineKeyboardButton(text="🔙 انصراف", callback_data="panel")]
                    ])
                )
                return
            else:
                await send_file_to_user(message, file_data)
                return
        else:
            await message.answer("❌ فایل پیدا نشد یا حذف شده است.")
            return
    
    settings = await db.get_settings()
    await message.answer(settings.get("welcome", "👋 سلام!"))

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
    else:
        await message.answer(
            "❌ رمز عبور اشتباه است.\n"
            "لطفا دوباره تلاش کنید یا /start را بزنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به خانه", callback_data="panel")]
            ])
        )

@router.callback_query(F.data == "panel", PasswordState.waiting)
async def cancel_password(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    settings = await db.get_settings()
    await callback.message.edit_text(settings.get("welcome", "👋 سلام!"))

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
    
    text = "👑 **پنل مدیریت**\n\nبه پنل مدیریت خوش آمدید!"
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
        "📤 **آپلود فایل جدید**\n\n"
        "لطفا فایل خود را ارسال کنید.\n"
        "پشتیبانی از تمامی فرمت‌ها: عکس، ویدیو، صوت، گیف، استیکر، فایل و...",
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
        "✅ فایل دریافت شد!\n\n"
        "حالا کپشن فایل را وارد کنید (اختیاری):\n"
        "می‌توانید از دکمه رد کردن استفاده کنید.",
        reply_markup=back_and_skip_kb()
    )

@router.callback_query(F.data == "skip_caption")
async def skip_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(caption="")
    await state.set_state(UploadState.password)
    await callback.message.edit_text(
        "🔒 آیا می‌خواهید برای فایل رمز عبور تعیین کنید؟\n\n"
        "در صورت تمایل رمز را وارد کنید یا از دکمه رد کردن استفاده کنید.",
        reply_markup=back_and_skip_kb()
    )

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    caption = message.text or ""
    await state.update_data(caption=caption)
    await state.set_state(UploadState.password)
    await message.answer(
        "🔒 آیا می‌خواهید برای فایل رمز عبور تعیین کنید؟\n\n"
        "در صورت تمایل رمز را وارد کنید یا از دکمه رد کردن استفاده کنید.",
        reply_markup=back_and_skip_kb()
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
        "admin": message.chat.id if hasattr(message, 'chat') else message.from_user.id
    })
    await db.add_log("upload", message.from_user.id if hasattr(message, 'from_user') else message.chat.id, f"Uploaded {fid}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    lock_status = "🔒 دارای رمز" if data.get("password") else "🔓 بدون رمز"
    
    await message.answer(
        f"✅ **فایل با موفقیت آپلود شد!**\n\n"
        f"🆔 شناسه: <code>{fid}</code>\n"
        f"📝 کپشن: {data.get('caption') or 'بدون کپشن'}\n"
        f"{lock_status}\n"
        f"🔑 رمز: <code>{data.get('password')}</code>\n" if data.get("password") else ""
        f"\n📎 لینک دانلود:\n<code>{link}</code>\n\n"
        f"این لینک را برای کاربران ارسال کنید.",
        reply_markup=panel_kb()
    )
    await state.clear()

# ==================== FILES LIST & ACTIONS ====================
@router.callback_query(F.data == "files_list")
async def files_list(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("📂 هیچ فایلی آپلود نشده.", reply_markup=panel_kb())
        return
    await callback.message.edit_text(
        f"📂 **فایل‌های آپلود شده** ({len(files)} عدد):\n\n"
        "🔒 = دارای رمز | 🔓 = بدون رمز",
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
    
    txt = (
        f"📁 **اطلاعات فایل**\n\n"
        f"🆔: <code>{f['id']}</code>\n"
        f"📝 کپشن: {f.get('caption') or 'بدون کپشن'}\n"
        f"📄 نام: {f.get('file_name') or 'نامشخص'}\n"
        f"🔒 رمز: {lock}\n"
        f"📥 دانلود: {f['downloads']} بار\n"
        f"📅 تاریخ: {f['date'][:10]}\n"
    )
    await callback.message.edit_text(txt, reply_markup=file_actions_kb(fid, bool(f.get("password"))))

@router.callback_query(F.data.startswith("dl_"))
async def download_file(callback: CallbackQuery):
    await callback.answer("📥 در حال ارسال...")
    fid = callback.data.replace("dl_", "")
    f = await db.get_file(fid)
    if f:
        await send_file_to_user(callback.message, f)

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
    
    password_text = f"\n🔑 رمز: <code>{f['password']}</code>" if f.get("password") else ""
    
    await callback.message.answer(
        f"🔗 **لینک فایل**\n\n"
        f"📎 <code>{link}</code>{password_text}\n\n"
        f"کاربران با این لینک می‌توانند فایل را دریافت کنند."
    )

@router.callback_query(F.data.startswith("editcap_"))
async def edit_caption_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(EditState.waiting_caption)
    await callback.message.edit_text(
        "✏️ کپشن جدید را وارد کنید:",
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
        f"🔒 رمز فعلی: {current or 'ندارد'}\n\n"
        "رمز جدید را وارد کنید (برای حذف رمز، کلمه remove را بفرستید):",
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
        "⚠️ **حذف فایل**\n\n"
        "آیا از حذف این فایل اطمینان دارید؟\n"
        "این عمل قابل بازگشت نیست.",
        reply_markup=confirm_delete_kb(fid)
    )

@router.callback_query(F.data.startswith("delyes_"))
async def delete_file_exec(callback: CallbackQuery):
    fid = callback.data.replace("delyes_", "")
    if await db.delete_file(fid):
        await db.add_log("delete", callback.from_user.id, f"Deleted {fid}")
        await callback.answer("✅ فایل حذف شد.")
        await files_list(callback)
    else:
        await callback.answer("❌ خطا در حذف.", show_alert=True)

# ==================== USERS ====================
@router.callback_query(F.data == "users_list")
async def users_list(callback: CallbackQuery):
    await callback.answer()
    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text("👥 هیچ کاربری ثبت نشده.", reply_markup=panel_kb())
        return
    await callback.message.edit_text(
        f"👥 **کاربران** ({len(users)} نفر):",
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
        f"👤 **اطلاعات کاربر**\n\n"
        f"🆔: <code>{uid}</code>\n"
        f"👤 نام: {u.get('name', 'نامشخص')}\n"
        f"📎 یوزرنیم: @{u.get('username') or 'ندارد'}\n"
        f"📥 دانلود: {u.get('downloads', 0)}\n"
        f"🚫 وضعیت: {'مسدود' if u.get('banned') else 'آزاد'}\n"
        f"📅 عضویت: {u.get('joined', '')[:10]}\n"
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

# ==================== ADMINS ====================
@router.callback_query(F.data == "admins_list")
async def admins_list(callback: CallbackQuery):
    await callback.answer()
    admins = await db.get_admins()
    txt = "👮 **لیست ادمین‌ها:**\n\n"
    for aid, a in admins.items():
        txt += f"• <code>{aid}</code> - {a['role']}\n"
    await callback.message.edit_text(txt, reply_markup=admins_kb(admins))

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_admin_id)
    await callback.message.edit_text(
        "➕ آیدی عددی ادمین جدید را ارسال کنید:",
        reply_markup=back_kb("admins_list")
    )

@router.message(SettingsState.waiting_admin_id)
async def add_admin_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        await db.add_admin(uid)
        await db.add_log("admin_add", message.from_user.id, f"Added admin {uid}")
        await message.answer(f"✅ ادمین <code>{uid}</code> اضافه شد.", reply_markup=panel_kb())
    except:
        await message.answer("❌ آیدی عددی معتبر نیست.")
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
        await callback.answer("❌ خطا.", show_alert=True)
    await admins_list(callback)

# ==================== STATS ====================
@router.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_stats()
    await callback.message.edit_text(
        f"📊 **آمار ربات**\n\n"
        f"👥 کاربران: {s['users']}\n"
        f"📁 فایل‌ها: {s['files']}\n"
        f"📥 دانلودها: {s['downloads']}",
        reply_markup=panel_kb()
    )

# ==================== SETTINGS ====================
@router.callback_query(F.data == "settings")
async def settings_menu(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    await callback.message.edit_text("⚙️ **تنظیمات ربات**", reply_markup=settings_kb(s))

@router.callback_query(F.data == "set_welcome")
async def set_welcome(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_welcome)
    await callback.message.edit_text(
        "👋 پیام خوشامد جدید را وارد کنید:",
        reply_markup=back_kb("settings")
    )

@router.message(SettingsState.waiting_welcome)
async def save_welcome(message: Message, state: FSMContext):
    await db.update_setting("welcome", message.text)
    await db.add_log("settings", message.from_user.id, "Updated welcome")
    await message.answer("✅ پیام خوشامد ذخیره شد.", reply_markup=panel_kb())
    await state.clear()

@router.callback_query(F.data == "set_timer")
async def set_timer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text(
        "⏱ زمان حذف خودکار فایل (دقیقه):\n"
        "0 = غیرفعال | 1-60 دقیقه",
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

# ==================== BROADCAST ====================
@router.callback_query(F.data == "broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BroadcastState.waiting)
    await callback.message.edit_text(
        "📢 **ارسال همگانی**\n\n"
        "پیام خود را ارسال کنید (متن، عکس، ویدیو، فایل...)\n"
        "این پیام برای همه کاربران ارسال خواهد شد.",
        reply_markup=broadcast_kb()
    )

@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text == "/back":
        await state.clear()
        await message.answer("❌ لغو شد.", reply_markup=panel_kb())
        return
    
    users = await db.get_all_users()
    total = len(users)
    sent = 0
    failed = 0
    
    progress = await message.answer(f"📢 در حال ارسال... 0/{total}")
    
    for i, uid in enumerate(users.keys()):
        try:
            await message.copy_to(chat_id=int(uid))
            sent += 1
        except:
            failed += 1
        
        if (i + 1) % 20 == 0:
            try:
                await progress.edit_text(f"📢 در حال ارسال... {i+1}/{total}")
            except:
                pass
        await asyncio.sleep(0.05)
    
    await db.add_log("broadcast", message.from_user.id, f"Sent to {sent}/{total}")
    await progress.edit_text(
        f"✅ **ارسال همگانی پایان یافت**\n\n"
        f"✅ موفق: {sent}\n"
        f"❌ ناموفق: {failed}\n"
        f"📊 مجموع: {total}",
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
    
    txt = "📜 **آخرین گزارشات:**\n\n"
    for l in logs_list:
        txt += f"<code>{l['time'][:19]}</code> | {l['action']} | {l['admin']}\n"
        if l.get('detail'):
            txt += f"  ↳ {l['detail'][:50]}\n"
    
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
