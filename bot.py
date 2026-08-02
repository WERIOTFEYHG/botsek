"""
Telegram File Uploader Bot - Clean & Simple
Aiogram 3.x | JSON Storage | Railway Ready
"""

import asyncio
import json
import os
import sys
import time
import uuid
import logging
import shutil
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
    InlineKeyboardButton, FSInputFile, BotCommand
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
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
            d["users"][str(uid)] = {"id": uid, "name": data.get("name", ""), "username": data.get("username", ""), "joined": datetime.now().isoformat(), "downloads": 0, "banned": False}
            await self._write(USERS_FILE, d)

    async def is_admin(self, uid: int) -> bool:
        d = await self._read(ADMINS_FILE)
        return str(uid) in d["admins"] or uid == ADMIN_ID

    async def add_file(self, data: Dict) -> str:
        d = await self._read(FILES_FILE)
        fid = data["id"]
        d["files"][fid] = {
            "id": fid, "file_id": data["file_id"], "type": data["type"],
            "caption": data.get("caption", ""), "date": datetime.now().isoformat(),
            "downloads": 0, "admin": data["admin"]
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

    async def get_stats(self) -> Dict:
        users = await self._read(USERS_FILE)
        files = await self._read(FILES_FILE)
        return {
            "users": len(users["users"]),
            "files": len(files["files"]),
            "downloads": sum(f["downloads"] for f in files["files"].values())
        }

    async def add_log(self, action: str, uid: int, detail: str = ""):
        d = await self._read(LOGS_FILE)
        d["logs"].append({"time": datetime.now().isoformat(), "action": action, "admin": uid, "detail": detail})
        if len(d["logs"]) > 500:
            d["logs"] = d["logs"][-500:]
        await self._write(LOGS_FILE, d)

    async def get_settings(self) -> Dict:
        return await self._read(SETTINGS_FILE)

    async def update_setting(self, key: str, val: Any):
        d = await self._read(SETTINGS_FILE)
        d[key] = val
        await self._write(SETTINGS_FILE, d)

db = JSONManager()

# ==================== KEYBOARDS ====================
def admin_panel_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 آپلود فایل", callback_data="upload"))
    b.row(InlineKeyboardButton(text="📂 فایل‌های من", callback_data="myfiles"), InlineKeyboardButton(text="📊 آمار", callback_data="stats"))
    b.row(InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="settings"), InlineKeyboardButton(text="📢 ارسال همگانی", callback_data="broadcast"))
    b.row(InlineKeyboardButton(text="👥 کاربران", callback_data="users"), InlineKeyboardButton(text="📜 گزارشات", callback_data="logs"))
    return b.as_markup()

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel")]])

# ==================== STATES ====================
class UploadState(StatesGroup):
    waiting = State()
    caption = State()

class BroadcastState(StatesGroup):
    waiting = State()

class SettingsState(StatesGroup):
    waiting_welcome = State()
    waiting_timer = State()

# ==================== ROUTER ====================
router = Router()

# ==================== START ====================
@router.message(Command("start"))
async def start_cmd(message: Message):
    user = message.from_user
    await db.add_user(user.id, {"name": user.first_name, "username": user.username})
    
    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        file_data = await db.get_file(file_id)
        if file_data:
            await send_file(message, file_data)
            return
        else:
            await message.answer("❌ فایل مورد نظر پیدا نشد.")
            return
    
    settings = await db.get_settings()
    await message.answer(settings.get("welcome", "سلام! 👋"))

async def send_file(message: Message, file_data: Dict):
    """Send file by its type"""
    fid = file_data["file_id"]
    cap = file_data.get("caption", "")
    ftype = file_data["type"]
    
    try:
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
        
        await db.inc_download(file_data["id"])
        
        # Auto delete after timer
        settings = await db.get_settings()
        timer = settings.get("delete_timer", 300)
        if timer > 0:
            asyncio.create_task(auto_delete(sent, timer))
    
    except Exception as e:
        logger.error(f"Send error: {e}")
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
    else:
        msg = event
    
    if not await db.is_admin(msg.chat.id):
        await msg.answer("⛔ دسترسی غیرمجاز")
        return
    
    await msg.answer("👑 پنل مدیریت:", reply_markup=admin_panel_kb())

# ==================== UPLOAD ====================
@router.callback_query(F.data == "upload")
async def upload_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not await db.is_admin(callback.from_user.id):
        return
    
    await state.set_state(UploadState.waiting)
    await callback.message.edit_text("📤 فایل خود را ارسال کنید (عکس، ویدیو، صوت، گیف، استیکر، فایل و...):", reply_markup=back_kb())

@router.message(UploadState.waiting)
async def upload_receive(message: Message, state: FSMContext):
    # Detect file type
    file_id = None
    file_type = "document"
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "animation"
    elif message.sticker:
        file_id = message.sticker.file_id
        file_type = "sticker"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    
    if not file_id:
        await message.answer("❌ فایل معتبر نیست. دوباره تلاش کنید.")
        return
    
    await state.update_data(file_id=file_id, file_type=file_type)
    await state.set_state(UploadState.caption)
    await message.answer("✅ فایل دریافت شد! حالا کپشن را بفرستید یا /skip بزنید:", reply_markup=back_kb())

@router.message(UploadState.caption)
async def upload_caption(message: Message, state: FSMContext):
    caption = "" if message.text == "/skip" else (message.text or "")
    
    data = await state.get_data()
    fid = str(uuid.uuid4())[:8]
    
    await db.add_file({
        "id": fid, "file_id": data["file_id"], "type": data["file_type"],
        "caption": caption, "admin": message.from_user.id
    })
    await db.add_log("upload", message.from_user.id, f"Uploaded {fid}")
    
    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    
    await message.answer(
        f"✅ آپلود موفق!\n\n🆔: `{fid}`\n📎 لینک:\n`{link}`\n\nکاربر با این لینک فایل را دریافت می‌کند.",
        reply_markup=admin_panel_kb()
    )
    await state.clear()

# ==================== MY FILES ====================
@router.callback_query(F.data == "myfiles")
async def my_files(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("📂 هیچ فایلی آپلود نشده.", reply_markup=admin_panel_kb())
        return
    
    txt = "📂 فایل‌های آپلود شده:\n\n"
    for fid, f in files.items():
        cap = f.get("caption", "بدون کپشن")[:30]
        txt += f"• {cap} (📥{f['downloads']})\n  `/start {fid}`\n  [حذف](callback:del_{fid})\n\n"
    
    # Telegram has limits, show first 30
    lines = txt.split('\n')[:90]
    txt = '\n'.join(lines)
    
    kb = InlineKeyboardBuilder()
    for fid, f in list(files.items())[:20]:
        cap = f.get("caption", "بدون کپشن")[:20]
        kb.row(InlineKeyboardButton(text=f"🗑 {cap}", callback_data=f"del_{fid}"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    
    await callback.message.edit_text("📂 برای حذف فایل روی آن کلیک کنید:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("del_"))
async def delete_file(callback: CallbackQuery):
    fid = callback.data.replace("del_", "")
    if await db.delete_file(fid):
        await db.add_log("delete", callback.from_user.id, f"Deleted {fid}")
        await callback.answer("✅ حذف شد!")
        await my_files(callback)
    else:
        await callback.answer("❌ خطا!", show_alert=True)

# ==================== STATS ====================
@router.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_stats()
    await callback.message.edit_text(
        f"📊 آمار ربات:\n\n👥 کاربران: {s['users']}\n📁 فایل‌ها: {s['files']}\n📥 دانلودها: {s['downloads']}",
        reply_markup=admin_panel_kb()
    )

# ==================== SETTINGS ====================
@router.callback_query(F.data == "settings")
async def settings(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    timer = s.get("delete_timer", 300) // 60
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👋 پیام خوشامد", callback_data="set_welcome"))
    kb.row(InlineKeyboardButton(text=f"⏱ تایمر حذف: {timer} دقیقه", callback_data="set_timer"))
    kb.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="panel"))
    await callback.message.edit_text("⚙️ تنظیمات:", reply_markup=kb.as_markup())

@router.callback_query(F.data == "set_welcome")
async def set_welcome(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_welcome)
    await callback.message.edit_text("👋 پیام خوشامد جدید را بفرستید:", reply_markup=back_kb())

@router.message(SettingsState.waiting_welcome)
async def save_welcome(message: Message, state: FSMContext):
    await db.update_setting("welcome", message.text)
    await message.answer("✅ ذخیره شد!", reply_markup=admin_panel_kb())
    await state.clear()

@router.callback_query(F.data == "set_timer")
async def set_timer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsState.waiting_timer)
    await callback.message.edit_text("⏱ زمان به دقیقه (0 برای غیرفعال کردن):", reply_markup=back_kb())

@router.message(SettingsState.waiting_timer)
async def save_timer(message: Message, state: FSMContext):
    try:
        mins = int(message.text)
        if 0 <= mins <= 60:
            await db.update_setting("delete_timer", mins * 60)
            await message.answer(f"✅ تایمر روی {mins} دقیقه تنظیم شد.", reply_markup=admin_panel_kb())
    except:
        await message.answer("❌ عدد معتبر نیست.")
    await state.clear()

# ==================== BROADCAST ====================
@router.callback_query(F.data == "broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BroadcastState.waiting)
    await callback.message.edit_text("📢 پیام خود را برای ارسال همگانی بفرستید:", reply_markup=back_kb())

@router.message(BroadcastState.waiting)
async def broadcast_send(message: Message, state: FSMContext):
    users = await db._read(USERS_FILE)
    total = len(users["users"])
    sent = 0
    
    msg = await message.answer(f"📢 در حال ارسال... 0/{total}")
    
    for i, uid in enumerate(users["users"]):
        try:
            await message.copy_to(int(uid))
            sent += 1
        except:
            pass
        if i % 20 == 0:
            await msg.edit_text(f"📢 در حال ارسال... {i+1}/{total}")
        await asyncio.sleep(0.05)
    
    await msg.edit_text(f"✅ ارسال شد به {sent} از {total} کاربر", reply_markup=admin_panel_kb())
    await db.add_log("broadcast", message.from_user.id, f"Sent to {sent}/{total}")
    await state.clear()

# ==================== USERS ====================
@router.callback_query(F.data == "users")
async def users_list(callback: CallbackQuery):
    await callback.answer()
    users = await db._read(USERS_FILE)
    total = len(users["users"])
    txt = f"👥 کاربران ({total}):\n\n"
    for uid, u in list(users["users"].items())[:20]:
        txt += f"• {u.get('name','')} (@{u.get('username','')}) | 📥{u.get('downloads',0)}\n"
    await callback.message.edit_text(txt, reply_markup=admin_panel_kb())

# ==================== LOGS ====================
@router.callback_query(F.data == "logs")
async def logs(callback: CallbackQuery):
    await callback.answer()
    logs = await db._read(LOGS_FILE)
    txt = "📜 آخرین گزارشات:\n\n"
    for l in logs["logs"][-15:]:
        txt += f"[{l['time'][:19]}] {l['action']} - {l['admin']}\n"
    await callback.message.edit_text(txt[:4000], reply_markup=admin_panel_kb())

# ==================== MAIN ====================
async def on_startup(bot: Bot):
    db.init_files()
    # Add owner
    d = await db._read(ADMINS_FILE)
    if str(ADMIN_ID) not in d["admins"]:
        d["admins"][str(ADMIN_ID)] = {"role": "owner"}
        await db._write(ADMINS_FILE, d)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="شروع"),
        BotCommand(command="admin", description="پنل مدیریت")
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
