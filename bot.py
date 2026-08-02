"""
Telegram File Uploader Bot - Complete Single File
Aiogram 3.x | JSON Storage | Docker Ready
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
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

USERS_FILE = "users.json"
FILES_FILE = "files.json"
ADMINS_FILE = "admins.json"
SETTINGS_FILE = "settings.json"
LOGS_FILE = "logs.json"

DEFAULT_DELETE_TIMER = 300
FLOOD_RATE = 0.5

PERMISSION_LEVELS = {"owner": 4, "super_admin": 3, "admin": 2, "uploader": 1}

# ==================== LOGGER ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('bot.log')]
)
logger = logging.getLogger(__name__)

# ==================== JSON MANAGER ====================
class JSONManager:
    def __init__(self):
        self.locks = {}
        files = [USERS_FILE, FILES_FILE, ADMINS_FILE, SETTINGS_FILE, LOGS_FILE]
        for f in files:
            self.locks[f] = asyncio.Lock()

    def initialize_files(self):
        defaults = {
            USERS_FILE: {"users": {}},
            FILES_FILE: {"files": {}, "deleted_files": {}},
            ADMINS_FILE: {"admins": {}},
            SETTINGS_FILE: {
                "welcome_message": "👋 Welcome!\nUse /start to get your link.",
                "delete_timer": DEFAULT_DELETE_TIMER,
                "force_join_channels": [],
                "bot_photo": None,
                "support_username": None,
                "admin_log_channel": None,
                "maintenance_mode": False
            },
            LOGS_FILE: {"logs": []}
        }
        for filename, data in defaults.items():
            if not os.path.exists(filename):
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

    async def _read(self, filename: str) -> Dict:
        async with self.locks.get(filename, asyncio.Lock()):
            try:
                async with aiofiles.open(filename, 'r', encoding='utf-8') as f:
                    return json.loads(await f.read())
            except:
                return {}

    async def _write(self, filename: str, data: Dict):
        async with self.locks.get(filename, asyncio.Lock()):
            async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))

    # Users
    async def add_user(self, user_id: int, user_data: Dict):
        data = await self._read(USERS_FILE)
        uid = str(user_id)
        if uid not in data["users"]:
            data["users"][uid] = {
                "user_id": user_id,
                "username": user_data.get("username", ""),
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
                "join_date": datetime.now().isoformat(),
                "downloads": 0,
                "banned": False,
                "ban_reason": None
            }
        else:
            data["users"][uid]["username"] = user_data.get("username", "")
            data["users"][uid]["first_name"] = user_data.get("first_name", "")
        await self._write(USERS_FILE, data)

    async def get_user(self, user_id: int) -> Optional[Dict]:
        data = await self._read(USERS_FILE)
        return data["users"].get(str(user_id))

    async def get_all_users(self) -> Dict:
        data = await self._read(USERS_FILE)
        return data["users"]

    async def ban_user(self, user_id: int, reason: str = None) -> bool:
        data = await self._read(USERS_FILE)
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["banned"] = True
            data["users"][uid]["ban_reason"] = reason
            await self._write(USERS_FILE, data)
            return True
        return False

    async def unban_user(self, user_id: int) -> bool:
        data = await self._read(USERS_FILE)
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["banned"] = False
            data["users"][uid]["ban_reason"] = None
            await self._write(USERS_FILE, data)
            return True
        return False

    async def inc_downloads(self, user_id: int):
        data = await self._read(USERS_FILE)
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["downloads"] += 1
            await self._write(USERS_FILE, data)

    # Files
    async def add_file(self, file_data: Dict) -> str:
        data = await self._read(FILES_FILE)
        fid = file_data["id"]
        data["files"][fid] = {
            "id": fid,
            "telegram_file_id": file_data["telegram_file_id"],
            "media_type": file_data["media_type"],
            "caption": file_data.get("caption", ""),
            "upload_date": datetime.now().isoformat(),
            "download_count": 0,
            "creator_admin": file_data["creator_admin"],
            "file_name": file_data.get("file_name", ""),
            "file_size": file_data.get("file_size", 0),
            "is_deleted": False
        }
        await self._write(FILES_FILE, data)
        return fid

    async def get_file(self, file_id: str) -> Optional[Dict]:
        data = await self._read(FILES_FILE)
        f = data["files"].get(file_id)
        return f if f and not f["is_deleted"] else None

    async def get_all_files(self) -> Dict:
        data = await self._read(FILES_FILE)
        return {k: v for k, v in data["files"].items() if not v["is_deleted"]}

    async def delete_file(self, file_id: str) -> bool:
        data = await self._read(FILES_FILE)
        if file_id in data["files"]:
            data["files"][file_id]["is_deleted"] = True
            data["deleted_files"][file_id] = data["files"][file_id]
            await self._write(FILES_FILE, data)
            return True
        return False

    async def restore_file(self, file_id: str) -> bool:
        data = await self._read(FILES_FILE)
        if file_id in data["files"]:
            data["files"][file_id]["is_deleted"] = False
            data["deleted_files"].pop(file_id, None)
            await self._write(FILES_FILE, data)
            return True
        return False

    async def inc_file_download(self, file_id: str):
        data = await self._read(FILES_FILE)
        if file_id in data["files"]:
            data["files"][file_id]["download_count"] += 1
            await self._write(FILES_FILE, data)

    async def update_caption(self, file_id: str, caption: str) -> bool:
        data = await self._read(FILES_FILE)
        if file_id in data["files"]:
            data["files"][file_id]["caption"] = caption
            await self._write(FILES_FILE, data)
            return True
        return False

    async def search_files(self, query: str) -> List[Dict]:
        data = await self._read(FILES_FILE)
        q = query.lower()
        return [v for v in data["files"].values() if not v["is_deleted"] and
                (q in v.get("caption", "").lower() or q in v.get("file_name", "").lower())]

    async def get_deleted_files(self) -> Dict:
        data = await self._read(FILES_FILE)
        return data.get("deleted_files", {})

    # Admins
    async def add_admin(self, user_id: int, role: str = "admin") -> bool:
        data = await self._read(ADMINS_FILE)
        perms = {
            "owner": ["upload", "delete", "ban", "broadcast", "settings", "admins", "backup", "view_logs", "edit_files"],
            "super_admin": ["upload", "delete", "ban", "broadcast", "settings", "admins", "view_logs", "edit_files"],
            "admin": ["upload", "delete", "ban", "broadcast", "view_logs", "edit_files"],
            "uploader": ["upload"]
        }
        data["admins"][str(user_id)] = {
            "user_id": user_id, "role": role,
            "added_date": datetime.now().isoformat(),
            "permissions": perms.get(role, [])
        }
        await self._write(ADMINS_FILE, data)
        return True

    async def add_admin_if_not_exists(self, user_id: int, role: str = "owner"):
        data = await self._read(ADMINS_FILE)
        if str(user_id) not in data["admins"]:
            await self.add_admin(user_id, role)

    async def remove_admin(self, user_id: int) -> bool:
        data = await self._read(ADMINS_FILE)
        uid = str(user_id)
        if uid in data["admins"] and data["admins"][uid]["role"] != "owner":
            del data["admins"][uid]
            await self._write(ADMINS_FILE, data)
            return True
        return False

    async def is_admin(self, user_id: int) -> bool:
        data = await self._read(ADMINS_FILE)
        return str(user_id) in data["admins"]

    async def get_admin(self, user_id: int) -> Optional[Dict]:
        data = await self._read(ADMINS_FILE)
        return data["admins"].get(str(user_id))

    async def get_all_admins(self) -> Dict:
        data = await self._read(ADMINS_FILE)
        return data["admins"]

    async def has_permission(self, user_id: int, perm: str) -> bool:
        a = await self.get_admin(user_id)
        return perm in a.get("permissions", []) if a else False

    # Settings
    async def get_settings(self) -> Dict:
        return await self._read(SETTINGS_FILE)

    async def update_setting(self, key: str, value: Any) -> bool:
        data = await self._read(SETTINGS_FILE)
        if key in data:
            data[key] = value
            await self._write(SETTINGS_FILE, data)
            return True
        return False

    async def add_force_join(self, channel: str) -> bool:
        data = await self._read(SETTINGS_FILE)
        if channel not in data["force_join_channels"]:
            data["force_join_channels"].append(channel)
            await self._write(SETTINGS_FILE, data)
            return True
        return False

    async def remove_force_join(self, channel: str) -> bool:
        data = await self._read(SETTINGS_FILE)
        if channel in data["force_join_channels"]:
            data["force_join_channels"].remove(channel)
            await self._write(SETTINGS_FILE, data)
            return True
        return False

    # Logs
    async def add_log(self, action: str, admin_id: int, details: str = ""):
        data = await self._read(LOGS_FILE)
        data["logs"].append({
            "timestamp": datetime.now().isoformat(),
            "action": action, "admin_id": admin_id, "details": details
        })
        if len(data["logs"]) > 1000:
            data["logs"] = data["logs"][-1000:]
        await self._write(LOGS_FILE, data)

    async def get_logs(self, limit: int = 50) -> List[Dict]:
        data = await self._read(LOGS_FILE)
        return data["logs"][-limit:]

    # Statistics
    async def get_stats(self) -> Dict:
        users_data = await self._read(USERS_FILE)
        files_data = await self._read(FILES_FILE)
        total_users = len(users_data["users"])
        total_files = len([f for f in files_data["files"].values() if not f["is_deleted"]])
        total_downloads = sum(f["download_count"] for f in files_data["files"].values())
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week = today - timedelta(days=7)
        month = today - timedelta(days=30)
        today_u = weekly_u = monthly_u = 0
        for u in users_data["users"].values():
            jd = datetime.fromisoformat(u["join_date"])
            if jd >= month:
                monthly_u += 1
                if jd >= week:
                    weekly_u += 1
                    if jd >= today:
                        today_u += 1
        active = [f for f in files_data["files"].values() if not f["is_deleted"]]
        top = sorted(active, key=lambda x: x["download_count"], reverse=True)[:10]
        return {
            "total_users": total_users, "today_users": today_u,
            "weekly_users": weekly_u, "monthly_users": monthly_u,
            "total_files": total_files, "total_downloads": total_downloads,
            "most_downloaded": top, "active_links": total_files
        }

    async def create_backup(self) -> str:
        os.makedirs("backups", exist_ok=True)
        filename = f"backups/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        shutil.make_archive(filename.replace('.zip', ''), 'zip', '.',
                          include=lambda x: x.endswith('.json'))
        return filename

db = JSONManager()

# ==================== KEYBOARDS ====================
class KB:
    @staticmethod
    def main_admin():
        b = InlineKeyboardBuilder()
        rows = [
            [("➕ Upload", "admin_upload"), ("📂 Files", "admin_files")],
            [("👥 Users", "admin_users"), ("📈 Stats", "admin_stats")],
            [("📢 Broadcast", "admin_broadcast"), ("⚙ Settings", "admin_settings")],
            [("👮 Admins", "admin_admins"), ("🔗 Links", "admin_links")],
            [("🚫 Ban", "admin_ban"), ("🔍 Search", "admin_search")],
            [("🗑 Delete", "admin_delete"), ("♻ Restore", "admin_restore")],
            [("💾 Backup", "admin_backup"), ("📜 Logs", "admin_logs")]
        ]
        for row in rows:
            b.row(*[InlineKeyboardButton(text=t, callback_data=c) for t, c in row])
        return b.as_markup()

    @staticmethod
    def upload_type():
        b = InlineKeyboardBuilder()
        types = [
            [("📸 Photo", "upload_photo"), ("🎥 Video", "upload_video")],
            [("🎵 Audio", "upload_audio"), ("🎤 Voice", "upload_voice")],
            [("🎬 Animation", "upload_animation"), ("🏷 Sticker", "upload_sticker")],
            [("📄 Document", "upload_document"), ("🗜 ZIP", "upload_zip")],
            [("📱 APK", "upload_apk"), ("📕 PDF", "upload_pdf")],
        ]
        for row in types:
            b.row(*[InlineKeyboardButton(text=t, callback_data=c) for t, c in row])
        b.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel"))
        return b.as_markup()

    @staticmethod
    def back(callback="admin_panel"):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data=callback)]
        ])

    @staticmethod
    def confirm(action: str, item_id: str = ""):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Yes", callback_data=f"confirm_{action}_{item_id}"),
             InlineKeyboardButton(text="❌ No", callback_data=f"cancel_{action}")]
        ])

    @staticmethod
    def force_join(channels: List[str]):
        b = InlineKeyboardBuilder()
        for ch in channels:
            b.row(InlineKeyboardButton(text=f"📢 Join {ch}", url=f"https://t.me/{ch.lstrip('@')}"))
        b.row(InlineKeyboardButton(text="✅ Check", callback_data="check_joined"))
        return b.as_markup()

    @staticmethod
    def file_actions(file_id: str):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Download", callback_data=f"download_{file_id}"),
             InlineKeyboardButton(text="✏️ Edit", callback_data=f"editcap_{file_id}")],
            [InlineKeyboardButton(text="🔗 Link", callback_data=f"getlink_{file_id}"),
             InlineKeyboardButton(text="🗑 Delete", callback_data=f"delfile_{file_id}")],
            [InlineKeyboardButton(text="🔙 Files", callback_data="admin_files")]
        ])

    @staticmethod
    def settings_menu():
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="👋 Welcome", callback_data="set_welcome"))
        b.row(InlineKeyboardButton(text="⏱ Timer", callback_data="set_timer"))
        b.row(InlineKeyboardButton(text="🔗 Force Join", callback_data="set_forcejoin"))
        b.row(InlineKeyboardButton(text="💬 Support", callback_data="set_support"))
        b.row(InlineKeyboardButton(text="📢 Log Channel", callback_data="set_logchan"))
        b.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel"))
        return b.as_markup()

    @staticmethod
    def paginated(items: list, prefix: str, page: int, per_page: int = 10):
        b = InlineKeyboardBuilder()
        total = max(1, (len(items) - 1) // per_page + 1)
        start = page * per_page
        for item in items[start:start + per_page]:
            b.row(InlineKeyboardButton(
                text=item.get("text", "Item"),
                callback_data=item.get("callback", "noop")
            ))
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_p{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{total}", callback_data="noop"))
        if page < total - 1:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_p{page+1}"))
        if nav:
            b.row(*nav)
        b.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel"))
        return b.as_markup()

# ==================== MIDDLEWARES ====================
class FloodProtection:
    def __init__(self):
        self.last_req = {}
        self.msg_count = {}
        self.warned = {}

    async def check(self, user_id: int) -> bool:
        now = time.time()
        if user_id in self.last_req:
            if now - self.last_req[user_id] < FLOOD_RATE:
                self.msg_count[user_id] = self.msg_count.get(user_id, 0) + 1
                if self.msg_count.get(user_id, 0) > 5:
                    return False
        self.last_req[user_id] = now
        if now - self.last_req.get(user_id, 0) > 1:
            self.msg_count[user_id] = 0
        return True

flood = FloodProtection()

# ==================== STATES ====================
class UploadStates(StatesGroup):
    waiting_media = State()
    waiting_caption = State()

class BroadcastStates(StatesGroup):
    waiting_content = State()
    waiting_confirm = State()

class SettingsStates(StatesGroup):
    waiting_welcome = State()
    waiting_timer = State()
    waiting_channel = State()
    waiting_support = State()
    waiting_logchan = State()
    waiting_caption = State()
    waiting_ban = State()
    waiting_search = State()
    waiting_add_admin = State()
    waiting_remove_admin = State()

# ==================== HANDLERS ====================
router = Router()

# --- START ---
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext = None):
    if not await flood.check(message.from_user.id):
        return
    user = message.from_user
    await db.add_user(user.id, {"username": user.username, "first_name": user.first_name, "last_name": user.last_name})

    args = message.text.split()
    if len(args) > 1:
        file_id = args[1]
        await send_file_by_id(message, file_id)
        return

    settings = await db.get_settings()
    await message.answer(settings.get("welcome_message", "Welcome!"))

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return
    await message.answer("👑 Admin Panel:", reply_markup=KB.main_admin())

@router.callback_query(F.data == "admin_panel")
async def show_admin(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👑 Admin Panel:", reply_markup=KB.main_admin())

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

# --- UPLOAD ---
@router.callback_query(F.data == "admin_upload")
async def upload_menu(callback: CallbackQuery):
    await callback.answer()
    if not await db.has_permission(callback.from_user.id, "upload"):
        await callback.answer("⛔ No permission", show_alert=True)
        return
    await callback.message.edit_text("📤 Select file type:", reply_markup=KB.upload_type())

@router.callback_query(F.data.startswith("upload_"))
async def set_upload_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    mtype = callback.data.replace("upload_", "")
    await state.update_data(upload_type=mtype)
    await state.set_state(UploadStates.waiting_media)
    await callback.message.edit_text(f"📤 Send {mtype} file:", reply_markup=KB.back())

@router.message(UploadStates.waiting_media)
async def handle_media(message: Message, state: FSMContext):
    data = await state.get_data()
    mtype = data.get("upload_type")
    file_id = None
    fname = "unknown"
    fsize = 0

    if mtype == "photo" and message.photo:
        file_id = message.photo[-1].file_id
    elif mtype == "video" and message.video:
        file_id = message.video.file_id
        fname = message.video.file_name or "video.mp4"
    elif mtype == "audio" and message.audio:
        file_id = message.audio.file_id
        fname = message.audio.file_name or "audio.mp3"
    elif mtype == "voice" and message.voice:
        file_id = message.voice.file_id
    elif mtype == "animation" and message.animation:
        file_id = message.animation.file_id
        fname = message.animation.file_name or "animation.gif"
    elif mtype == "sticker" and message.sticker:
        file_id = message.sticker.file_id
    elif message.document:
        file_id = message.document.file_id
        fname = message.document.file_name or f"{mtype}.file"

    if not file_id:
        await message.answer("❌ Invalid file. Try again.")
        await state.clear()
        return

    await state.update_data(file_id=file_id, file_name=fname, file_size=fsize)
    await state.set_state(UploadStates.waiting_caption)
    await message.answer("✅ File received! Send caption (/skip to skip):", reply_markup=KB.back())

@router.message(UploadStates.waiting_caption)
async def handle_caption(message: Message, state: FSMContext):
    if message.text == "/skip":
        caption = ""
    elif message.text == "/cancel":
        await message.answer("❌ Cancelled.")
        await state.clear()
        return
    else:
        caption = message.text

    data = await state.get_data()
    uid = str(uuid.uuid4())[:8]
    file_data = {
        "id": uid, "telegram_file_id": data["file_id"],
        "media_type": data["upload_type"], "caption": caption,
        "creator_admin": message.from_user.id,
        "file_name": data.get("file_name", ""), "file_size": data.get("file_size", 0)
    }
    await db.add_file(file_data)
    await db.add_log("upload", message.from_user.id, f"Uploaded {data['upload_type']}: {uid}")

    bot = await message.bot.get_me()
    link = f"https://t.me/{bot.username}?start={uid}"
    await message.answer(
        f"✅ Uploaded!\n🆔: `{uid}`\n🔗: `{link}`",
        reply_markup=KB.main_admin()
    )
    await state.clear()

# --- SEND FILE ---
async def send_file_by_id(message: Message, file_id: str):
    file_data = await db.get_file(file_id)
    if not file_data:
        await message.answer("❌ File not found.")
        return

    user = await db.get_user(message.from_user.id)
    if user and user.get("banned"):
        await message.answer("🚫 You are banned.")
        return

    settings = await db.get_settings()
    mtype = file_data["media_type"]
    fid = file_data["telegram_file_id"]
    cap = file_data.get("caption", "")

    sent = None
    try:
        if mtype == "photo":
            sent = await message.answer_photo(fid, caption=cap)
        elif mtype == "video":
            sent = await message.answer_video(fid, caption=cap)
        elif mtype == "audio":
            sent = await message.answer_audio(fid, caption=cap)
        elif mtype == "voice":
            sent = await message.answer_voice(fid)
        elif mtype == "animation":
            sent = await message.answer_animation(fid, caption=cap)
        elif mtype == "sticker":
            sent = await message.answer_sticker(fid)
        else:
            sent = await message.answer_document(fid, caption=cap)

        await db.inc_file_download(file_id)
        await db.inc_downloads(message.from_user.id)
        await db.add_log("download", message.from_user.id, f"Downloaded {file_id}")

        timer = settings.get("delete_timer", 300)
        if timer > 0 and sent:
            asyncio.create_task(delete_later(sent, timer))
    except Exception as e:
        logger.error(f"Send error: {e}")
        await message.answer("❌ Error sending file.")

async def delete_later(msg: Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except:
        pass

# --- FILES ---
@router.callback_query(F.data == "admin_files")
async def files_list(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("📭 No files.", reply_markup=KB.main_admin())
        return
    items = []
    for fid, f in files.items():
        cap = f.get("caption", "No caption")[:25]
        items.append({"text": f"📁 {cap} (📥{f['download_count']})", "callback": f"fileinfo_{fid}"})
    await callback.message.edit_text("📂 Files:", reply_markup=KB.paginated(items, "files", 0))

@router.callback_query(F.data.startswith("fileinfo_"))
async def file_info(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("fileinfo_", "")
    f = await db.get_file(fid)
    if not f:
        await callback.answer("Not found!", show_alert=True)
        return
    await callback.message.edit_text(
        f"📁 ID: `{fid}`\n📝: {f.get('caption','')}\n📥: {f['download_count']}\n📅: {f['upload_date'][:10]}",
        reply_markup=KB.file_actions(fid)
    )

@router.callback_query(F.data.startswith("download_"))
async def download_file(callback: CallbackQuery):
    await callback.answer("📥 Sending...")
    fid = callback.data.replace("download_", "")
    f = await db.get_file(fid)
    if f:
        await send_file_by_id(callback.message, fid)

@router.callback_query(F.data.startswith("getlink_"))
async def get_link(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("getlink_", "")
    bot = await callback.bot.get_me()
    link = f"https://t.me/{bot.username}?start={fid}"
    await callback.message.answer(f"🔗: `{link}`")

@router.callback_query(F.data.startswith("editcap_"))
async def edit_caption(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    fid = callback.data.replace("editcap_", "")
    await state.update_data(edit_fid=fid)
    await state.set_state(SettingsStates.waiting_caption)
    await callback.message.edit_text("✏️ Send new caption:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_caption)
async def save_caption(message: Message, state: FSMContext):
    data = await state.get_data()
    fid = data.get("edit_fid")
    if fid:
        await db.update_caption(fid, message.text)
        await db.add_log("edit", message.from_user.id, f"Edited caption {fid}")
        await message.answer("✅ Caption updated!")
    await state.clear()

@router.callback_query(F.data.startswith("delfile_"))
async def delete_file_ask(callback: CallbackQuery):
    await callback.answer()
    fid = callback.data.replace("delfile_", "")
    await callback.message.edit_text("⚠️ Delete this file?", reply_markup=KB.confirm("delfile", fid))

@router.callback_query(F.data.startswith("confirm_delfile_"))
async def delete_file_confirm(callback: CallbackQuery):
    fid = callback.data.replace("confirm_delfile_", "")
    if await db.delete_file(fid):
        await db.add_log("delete", callback.from_user.id, f"Deleted {fid}")
        await callback.answer("✅ Deleted!")
        await callback.message.edit_text("✅ File deleted.", reply_markup=KB.main_admin())
    else:
        await callback.answer("❌ Failed!", show_alert=True)

@router.callback_query(F.data == "admin_restore")
async def restore_menu(callback: CallbackQuery):
    await callback.answer()
    deleted = await db.get_deleted_files()
    if not deleted:
        await callback.message.edit_text("♻ No deleted files.", reply_markup=KB.main_admin())
        return
    items = []
    for fid, f in list(deleted.items())[:10]:
        items.append({"text": f"♻ {f.get('caption','')[:25]}", "callback": f"restore_{fid}"})
    await callback.message.edit_text("♻ Select to restore:", reply_markup=KB.paginated(items, "rest", 0))

@router.callback_query(F.data.startswith("restore_"))
async def restore_file(callback: CallbackQuery):
    fid = callback.data.replace("restore_", "")
    if await db.restore_file(fid):
        await db.add_log("restore", callback.from_user.id, f"Restored {fid}")
        await callback.answer("✅ Restored!")
    await callback.message.edit_text("✅ Restored.", reply_markup=KB.main_admin())

@router.callback_query(F.data == "admin_delete")
async def delete_menu(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("🗑 No files.", reply_markup=KB.main_admin())
        return
    items = [{"text": f"🗑 {f.get('caption','')[:25]}", "callback": f"delfile_{fid}"} for fid, f in files.items()]
    await callback.message.edit_text("🗑 Select to delete:", reply_markup=KB.paginated(items, "del", 0))

@router.callback_query(F.data == "admin_search")
async def search_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_search)
    await callback.message.edit_text("🔍 Send search term:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_search)
async def search_results(message: Message, state: FSMContext):
    results = await db.search_files(message.text)
    if not results:
        await message.answer("🔍 No results.")
    else:
        for f in results[:10]:
            await message.answer(f"📁 {f.get('caption','')} (📥{f['download_count']})\n🆔: `{f['id']}`")
    await state.clear()

# --- USERS ---
@router.callback_query(F.data == "admin_users")
async def users_list(callback: CallbackQuery):
    await callback.answer()
    users = await db.get_all_users()
    if not users:
        await callback.message.edit_text("👥 No users.", reply_markup=KB.main_admin())
        return
    items = []
    for uid, u in list(users.items())[:50]:
        name = u.get("first_name", "User")
        items.append({"text": f"{'🚫' if u.get('banned') else '✅'} {name}", "callback": f"userinfo_{uid}"})
    await callback.message.edit_text("👥 Users:", reply_markup=KB.paginated(items, "users", 0))

@router.callback_query(F.data.startswith("userinfo_"))
async def user_info(callback: CallbackQuery):
    await callback.answer()
    uid = callback.data.replace("userinfo_", "")
    u = await db.get_user(int(uid))
    if not u:
        await callback.answer("Not found!", show_alert=True)
        return
    txt = f"👤 {u['first_name']} (@{u.get('username','')})\n📥 Downloads: {u['downloads']}\n🚫 Banned: {u['banned']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Ban/Unban", callback_data=f"toggleban_{uid}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")]
    ])
    await callback.message.edit_text(txt, reply_markup=kb)

@router.callback_query(F.data.startswith("toggleban_"))
async def toggle_ban(callback: CallbackQuery):
    uid = int(callback.data.replace("toggleban_", ""))
    u = await db.get_user(uid)
    if u and u.get("banned"):
        await db.unban_user(uid)
        await callback.answer("✅ Unbanned!")
    else:
        await db.ban_user(uid)
        await callback.answer("🚫 Banned!")
    await user_info(callback)

@router.callback_query(F.data == "admin_ban")
async def ban_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_ban)
    await callback.message.edit_text("🚫 Send User ID to ban/unban:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_ban)
async def ban_user(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        u = await db.get_user(uid)
        if u and u.get("banned"):
            await db.unban_user(uid)
            await message.answer("✅ User unbanned!")
        else:
            await db.ban_user(uid)
            await message.answer("🚫 User banned!")
    except:
        await message.answer("❌ Invalid ID.")
    await state.clear()

# --- STATS ---
@router.callback_query(F.data == "admin_stats")
async def stats(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_stats()
    txt = (f"📈 Stats\n\n👥 Total: {s['total_users']}\n📅 Today: {s['today_users']}\n"
           f"📆 Weekly: {s['weekly_users']}\n📊 Monthly: {s['monthly_users']}\n\n"
           f"📁 Files: {s['total_files']}\n📥 Downloads: {s['total_downloads']}\n🔗 Links: {s['active_links']}")
    await callback.message.edit_text(txt, reply_markup=KB.main_admin())

# --- BROADCAST ---
@router.callback_query(F.data == "admin_broadcast")
async def broadcast_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    if not await db.has_permission(callback.from_user.id, "broadcast"):
        await callback.answer("⛔ No permission", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Text", callback_data="bcast_text")],
        [InlineKeyboardButton(text="📸 Photo", callback_data="bcast_photo")],
        [InlineKeyboardButton(text="🎥 Video", callback_data="bcast_video")],
        [InlineKeyboardButton(text="📄 Document", callback_data="bcast_doc")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("📢 Broadcast type:", reply_markup=kb)

@router.callback_query(F.data.startswith("bcast_"))
async def broadcast_type(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    btype = callback.data.replace("bcast_", "")
    await state.update_data(bcast_type=btype)
    await state.set_state(BroadcastStates.waiting_content)
    await callback.message.edit_text(f"📢 Send {btype} for broadcast:", reply_markup=KB.back())

@router.message(BroadcastStates.waiting_content)
async def broadcast_content(message: Message, state: FSMContext):
    data = await state.get_data()
    btype = data.get("bcast_type")
    content = {}
    if btype == "text":
        content["text"] = message.text or ""
    elif btype == "photo" and message.photo:
        content["photo"] = message.photo[-1].file_id
        content["caption"] = message.caption or ""
    elif btype == "video" and message.video:
        content["video"] = message.video.file_id
        content["caption"] = message.caption or ""
    elif btype == "doc" and message.document:
        content["document"] = message.document.file_id
        content["caption"] = message.caption or ""
    else:
        await message.answer("❌ Invalid content.")
        await state.clear()
        return
    await state.update_data(content=content)
    await state.set_state(BroadcastStates.waiting_confirm)
    await message.answer("📢 Confirm broadcast?", reply_markup=KB.confirm("bcast"))

@router.callback_query(F.data == "confirm_bcast")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    await callback.answer("📢 Sending...")
    data = await state.get_data()
    content = data.get("content", {})
    btype = data.get("bcast_type", "text")
    users = await db.get_all_users()
    total = len(users)
    sent = 0
    failed = 0

    msg = await callback.message.edit_text(f"📢 0/{total} (0%)")

    for i, (uid, _) in enumerate(users.items()):
        try:
            if btype == "text":
                await callback.bot.send_message(int(uid), content.get("text", ""))
            elif btype == "photo":
                await callback.bot.send_photo(int(uid), content.get("photo"), caption=content.get("caption", ""))
            elif btype == "video":
                await callback.bot.send_video(int(uid), content.get("video"), caption=content.get("caption", ""))
            elif btype == "doc":
                await callback.bot.send_document(int(uid), content.get("document"), caption=content.get("caption", ""))
            sent += 1
        except:
            failed += 1
        if i % 20 == 0:
            await msg.edit_text(f"📢 {i+1}/{total} ({(i+1)/total*100:.0f}%)")
        await asyncio.sleep(0.05)

    await db.add_log("broadcast", callback.from_user.id, f"Sent to {sent}/{total}")
    await msg.edit_text(f"✅ Done!\n✅ {sent}\n❌ {failed}", reply_markup=KB.main_admin())
    await state.clear()

@router.callback_query(F.data == "cancel_bcast")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Cancelled.")
    await state.clear()
    await callback.message.edit_text("❌ Cancelled.", reply_markup=KB.main_admin())

# --- SETTINGS ---
@router.callback_query(F.data == "admin_settings")
async def settings_menu(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    timer = s.get("delete_timer", 300) // 60
    fj = len(s.get("force_join_channels", []))
    txt = (f"⚙ Settings\n\n👋 Welcome: {s.get('welcome_message','')[:20]}...\n"
           f"⏱ Timer: {timer} min\n🔗 Force Join: {fj} channels\n💬 Support: @{s.get('support_username','N/A')}")
    await callback.message.edit_text(txt, reply_markup=KB.settings_menu())

@router.callback_query(F.data == "set_welcome")
async def set_welcome(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_welcome)
    await callback.message.edit_text("👋 Send new welcome message:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_welcome)
async def save_welcome(message: Message, state: FSMContext):
    await db.update_setting("welcome_message", message.text)
    await message.answer("✅ Updated!", reply_markup=KB.settings_menu())
    await state.clear()

@router.callback_query(F.data == "set_timer")
async def set_timer(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_timer)
    await callback.message.edit_text("⏱ Send minutes (0-60):", reply_markup=KB.back())

@router.message(SettingsStates.waiting_timer)
async def save_timer(message: Message, state: FSMContext):
    try:
        mins = int(message.text)
        if 0 <= mins <= 60:
            await db.update_setting("delete_timer", mins * 60)
            await message.answer(f"✅ Timer: {mins} min", reply_markup=KB.settings_menu())
    except:
        await message.answer("❌ Invalid number.")
    await state.clear()

@router.callback_query(F.data == "set_forcejoin")
async def forcejoin_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    s = await db.get_settings()
    chs = s.get("force_join_channels", [])
    txt = "🔗 Force Join Channels:\n" + "\n".join([f"• {c}" for c in chs]) if chs else "No channels."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add", callback_data="fj_add")],
        [InlineKeyboardButton(text="➖ Remove", callback_data="fj_remove")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_settings")]
    ])
    await callback.message.edit_text(txt, reply_markup=kb)

@router.callback_query(F.data == "fj_add")
async def fj_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_channel)
    await callback.message.edit_text("➕ Send channel (@username):", reply_markup=KB.back())

@router.message(SettingsStates.waiting_channel)
async def fj_save(message: Message, state: FSMContext):
    ch = message.text.strip()
    if await db.add_force_join(ch):
        await message.answer(f"✅ {ch} added!")
    else:
        await message.answer("❌ Already exists.")
    await state.clear()

@router.callback_query(F.data == "fj_remove")
async def fj_remove_list(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    chs = s.get("force_join_channels", [])
    if not chs:
        await callback.answer("No channels.", show_alert=True)
        return
    items = [{"text": f"❌ {c}", "callback": f"fj_del_{c}"} for c in chs]
    await callback.message.edit_text("Select to remove:", reply_markup=KB.paginated(items, "fjrm", 0))

@router.callback_query(F.data.startswith("fj_del_"))
async def fj_delete(callback: CallbackQuery):
    ch = callback.data.replace("fj_del_", "")
    await db.remove_force_join(ch)
    await callback.answer(f"✅ {ch} removed!")
    await forcejoin_menu(callback, None)

@router.callback_query(F.data == "set_support")
async def set_support(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_support)
    await callback.message.edit_text("💬 Send support username (without @):", reply_markup=KB.back())

@router.message(SettingsStates.waiting_support)
async def save_support(message: Message, state: FSMContext):
    await db.update_setting("support_username", message.text.replace("@", ""))
    await message.answer("✅ Updated!", reply_markup=KB.settings_menu())
    await state.clear()

@router.callback_query(F.data == "set_logchan")
async def set_logchan(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_logchan)
    await callback.message.edit_text("📢 Forward a message from log channel:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_logchan)
async def save_logchan(message: Message, state: FSMContext):
    ch_id = str(message.forward_from_chat.id) if message.forward_from_chat else message.text.strip()
    await db.update_setting("admin_log_channel", ch_id)
    await message.answer("✅ Log channel set!", reply_markup=KB.settings_menu())
    await state.clear()

# --- ADMINS ---
@router.callback_query(F.data == "admin_admins")
async def admins_list(callback: CallbackQuery):
    await callback.answer()
    if not await db.has_permission(callback.from_user.id, "admins"):
        await callback.answer("⛔ No permission", show_alert=True)
        return
    admins = await db.get_all_admins()
    txt = "👮 Admins:\n"
    for aid, a in admins.items():
        txt += f"• {aid} - {a['role']}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add", callback_data="adm_add"),
         InlineKeyboardButton(text="➖ Remove", callback_data="adm_remove")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(txt, reply_markup=kb)

@router.callback_query(F.data == "adm_add")
async def adm_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_add_admin)
    await callback.message.edit_text("➕ Send user ID to add as admin:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_add_admin)
async def adm_save(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        await db.add_admin(uid, "admin")
        await db.add_log("admin_add", message.from_user.id, f"Added admin {uid}")
        await message.answer("✅ Admin added!")
    except:
        await message.answer("❌ Invalid ID.")
    await state.clear()

@router.callback_query(F.data == "adm_remove")
async def adm_remove(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SettingsStates.waiting_remove_admin)
    await callback.message.edit_text("➖ Send user ID to remove:", reply_markup=KB.back())

@router.message(SettingsStates.waiting_remove_admin)
async def adm_delete(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        if await db.remove_admin(uid):
            await db.add_log("admin_remove", message.from_user.id, f"Removed admin {uid}")
            await message.answer("✅ Admin removed!")
        else:
            await message.answer("❌ Cannot remove owner.")
    except:
        await message.answer("❌ Invalid ID.")
    await state.clear()

# --- LINKS ---
@router.callback_query(F.data == "admin_links")
async def links_view(callback: CallbackQuery):
    await callback.answer()
    files = await db.get_all_files()
    if not files:
        await callback.message.edit_text("🔗 No links.", reply_markup=KB.main_admin())
        return
    bot = await callback.bot.get_me()
    txt = "🔗 Active Links:\n\n"
    for fid, f in list(files.items())[:15]:
        txt += f"• {f.get('caption','')[:20]} - 📥{f['download_count']}\n  /start {fid}\n\n"
    await callback.message.edit_text(txt, reply_markup=KB.main_admin())

# --- BACKUP ---
@router.callback_query(F.data == "admin_backup")
async def backup_menu(callback: CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Create Backup", callback_data="backup_create")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("💾 Backup:", reply_markup=kb)

@router.callback_query(F.data == "backup_create")
async def backup_create(callback: CallbackQuery):
    await callback.answer("💾 Creating backup...")
    try:
        filename = await db.create_backup()
        await callback.message.answer_document(FSInputFile(filename))
        await callback.message.answer("✅ Backup created!")
    except Exception as e:
        await callback.answer(f"❌ Error: {e}", show_alert=True)

# --- LOGS ---
@router.callback_query(F.data == "admin_logs")
async def view_logs(callback: CallbackQuery):
    await callback.answer()
    logs = await db.get_logs(20)
    if not logs:
        await callback.message.edit_text("📜 No logs.", reply_markup=KB.main_admin())
        return
    txt = "📜 Last 20 Logs:\n\n"
    for l in logs[-20:]:
        txt += f"[{l['timestamp'][:19]}] {l['action']} - {l['admin_id']}\n"
    await callback.message.edit_text(txt[:4000], reply_markup=KB.main_admin())

# --- FORCE JOIN CHECK ---
@router.callback_query(F.data == "check_joined")
async def check_joined(callback: CallbackQuery):
    await callback.answer()
    s = await db.get_settings()
    channels = s.get("force_join_channels", [])
    bot = callback.bot
    user_id = callback.from_user.id
    not_joined = False
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                not_joined = True
                break
        except:
            not_joined = True
            break
    if not_joined:
        await callback.answer("❌ Join all channels first!", show_alert=True)
    else:
        await callback.answer("✅ Verified! Use /start to continue.", show_alert=True)

# --- PAGINATION ---
@router.callback_query(F.data.startswith("files_p"))
@router.callback_query(F.data.startswith("users_p"))
@router.callback_query(F.data.startswith("del_p"))
@router.callback_query(F.data.startswith("rest_p"))
@router.callback_query(F.data.startswith("fjrm_p"))
async def handle_pagination(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_p")
    prefix = parts[0]
    page = int(parts[1])
    items = []
    text = ""

    if prefix == "files":
        files = await db.get_all_files()
        items = [{"text": f"📁 {f.get('caption','')[:25]} (📥{f['download_count']})", "callback": f"fileinfo_{fid}"} for fid, f in files.items()]
        text = "📂 Files:"
    elif prefix == "users":
        users = await db.get_all_users()
        items = [{"text": f"{'🚫' if u.get('banned') else '✅'} {u.get('first_name','')}", "callback": f"userinfo_{uid}"} for uid, u in list(users.items())[:50]]
        text = "👥 Users:"
    elif prefix == "del":
        files = await db.get_all_files()
        items = [{"text": f"🗑 {f.get('caption','')[:25]}", "callback": f"delfile_{fid}"} for fid, f in files.items()]
        text = "🗑 Delete:"
    elif prefix == "rest":
        deleted = await db.get_deleted_files()
        items = [{"text": f"♻ {f.get('caption','')[:25]}", "callback": f"restore_{fid}"} for fid, f in deleted.items()]
        text = "♻ Restore:"
    elif prefix == "fjrm":
        s = await db.get_settings()
        items = [{"text": f"❌ {c}", "callback": f"fj_del_{c}"} for c in s.get("force_join_channels", [])]
        text = "Remove channel:"

    await callback.message.edit_text(text, reply_markup=KB.paginated(items, prefix, page))

# ==================== MAIN ====================
async def on_startup(bot: Bot):
    logger.info("Bot starting...")
    db.initialize_files()
    await db.add_admin_if_not_exists(ADMIN_ID, "owner")
    await bot.set_my_commands([
        BotCommand(command="start", description="Start"),
        BotCommand(command="admin", description="Admin panel")
    ])
    try:
        await bot.send_message(ADMIN_ID, "✅ Bot started!")
    except:
        pass

async def on_shutdown(bot: Bot):
    logger.info("Bot shutting down...")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
