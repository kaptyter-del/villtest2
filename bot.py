import asyncio
import uuid
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

TOKEN = "8541180036:AAEkHwABu3slQgRdOILbTdWcE6LI-AWRLzE"
ADMINS = [1750230081]

PROMOCODES = {
    "AXDWR2": 0.10
    "2026FXS": 0.10
}

COMMISSION_RATE = 0.25  # 25%

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =========================
#  PERSISTENCE (history/)
# =========================
HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)

STATE_FILE = os.path.join(HISTORY_DIR, "state.json")
EVENTS_FILE = os.path.join(HISTORY_DIR, "events.log")


def _atomic_write_json(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state():
    data = {
        "orders": orders,
        "archive": archive,
        "banned_users": list(banned_users),
        "user_activity": {str(k): v for k, v in user_activity.items()},
        "user_profiles": {str(k): v for k, v in user_profiles.items()},
    }
    _atomic_write_json(STATE_FILE, data)


# =========================
#  DATA
# =========================
# order_id -> data
orders = {}
archive = {}  # archived orders
user_state = {}  # uid -> {"stage": ...}

banned_users = set()
user_activity = {}  # uid -> count
user_profiles = {}  # uid -> {"username": ..., "first_name": ...}

# Load persisted state
_loaded = load_state()
orders = _loaded.get("orders", {}) or {}
archive = _loaded.get("archive", {}) or {}

banned_users = set(_loaded.get("banned_users", []) or [])

ua = _loaded.get("user_activity", {}) or {}
user_activity = {int(k): int(v) for k, v in ua.items()}

up = _loaded.get("user_profiles", {}) or {}
user_profiles = {int(k): v for k, v in up.items()}


# =========================
#  STATUSES
# =========================
ORDER_STATUSES = {
    "NEW": "🆕 Нове",
    "WAIT_PAYMENT": "💳 Очікує оплату",
    "PREPARING": "📦 Підготовка",
    "ON_THE_WAY": "🚚 В дорозі",
    "DONE": "✅ Отримано",
    "REJECTED": "❌ Відхилено"
}


def is_admin(uid: int) -> bool:
    return uid in ADMINS


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_username(u: types.User) -> str:
    return f"@{u.username}" if u.username else "—"


def order_card_text(oid: str, o: dict) -> str:
    return (
        f"📦 ЗАМОВЛЕННЯ #{oid}\n\n"
        f"👤 Юзер: {o.get('username', '—')}\n"
        f"🆔 ID: {o.get('user_id', '—')}\n\n"
        f"🔗 Посилання:\n{o.get('link', '—')}\n\n"
        f"📝 Опис:\n{o.get('desc', '—')}\n\n"
        f"📱 Контакт:\n{o.get('contact', '—')}\n\n"
        f"🎟 Промокод: {o.get('promo') or 'немає'}\n"
        f"💰 Ціна: {o.get('final_price', '—')} грн\n"
        f"📌 Статус: {ORDER_STATUSES.get(o.get('status',''), o.get('status','—'))}"
    )


# =========================
#  KEYBOARDS
# =========================
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📦 Зробити замовлення")],
        [KeyboardButton(text="📋 Мої замовлення")],
        [KeyboardButton(text="📞 Підтримка")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Скасувати")]],
    resize_keyboard=True
)

admin_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🛠 Адмін-панель")],
        [KeyboardButton(text="❌ Скасувати")]
    ],
    resize_keyboard=True
)

admin_dashboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🆕 Нові")],
        [KeyboardButton(text="💳 Очікує оплату")],
        [KeyboardButton(text="📦 Підготовка")],
        [KeyboardButton(text="🚚 В дорозі")],
        [KeyboardButton(text="📁 Архів"), KeyboardButton(text="❌ Відхилені")],
        [KeyboardButton(text="👥 Користувачі")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="❌ Скасувати")]
    ],
    resize_keyboard=True
)


# =========================
#  START / CANCEL
# =========================
@dp.message(CommandStart())
async def start(message: types.Message):
    user_state.pop(message.from_user.id, None)

    uid = message.from_user.id
    user_profiles[uid] = {
        "username": message.from_user.username,
        "first_name": message.from_user.first_name
    }
    user_activity[uid] = user_activity.get(uid, 0) + 1
    save_state()

    kb = admin_menu if is_admin(uid) else main_menu
    await message.answer(
        "👋 Вітаємо у сервісі замовлень!\n\n"
        "📍 Вільнянськ\n"
        "Ми — посередник, а не магазин.",
        reply_markup=kb
    )


@dp.message(F.text == "❌ Скасувати")
async def cancel(message: types.Message):
    user_state.pop(message.from_user.id, None)
    kb = admin_menu if is_admin(message.from_user.id) else main_menu
    await message.answer("❌ Скасовано.", reply_markup=kb)


def banned_block(message: types.Message) -> bool:
    """Return True if user is banned (and we already responded/ignored)."""
    if message.from_user.id in banned_users:
        # Можна або ігнорувати, або показувати повідомлення разово.
        return True
    return False


# =========================
#  SUPPORT (user -> admin) + admin reply
# =========================
@dp.message(F.text == "📞 Підтримка")
async def support(message: types.Message):
    if banned_block(message):
        return
    user_state[message.from_user.id] = {"stage": "support"}
    await message.answer("✍️ Напиши повідомлення для підтримки.", reply_markup=cancel_kb)


# =========================
#  MY ORDERS (user)
# =========================
@dp.message(F.text == "📋 Мої замовлення")
async def my_orders(message: types.Message):
    if banned_block(message):
        return

    uid = message.from_user.id
    found = False

    # показуємо кожне замовлення окремим повідомленням (так можна додати кнопки)
    for oid, o in orders.items():
        if o.get("user_id") != uid:
            continue
        found = True

        text = (
            f"📦 Замовлення #{oid}\n"
            f"Статус: {ORDER_STATUSES.get(o.get('status',''), o.get('status','—'))}\n"
            f"Сума: {o.get('final_price','—')} грн"
        )

        # Якщо очікує оплату — даємо кнопки "Оплатити/Відмовитись"
        if o.get("status") == "WAIT_PAYMENT":
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатити (Mono)", callback_data=f"pay_mono:{oid}")],
                    [InlineKeyboardButton(text="❌ Відмовитись", callback_data=f"user_cancel:{oid}")]
                ]
            )
            await message.answer(text, reply_markup=kb)
        else:
            await message.answer(text)

    if not found:
        await message.answer("📋 У тебе ще немає замовлень.", reply_markup=main_menu)
    else:
        await message.answer("⬆️ Це твої замовлення.", reply_markup=main_menu)


# =========================
#  ORDER FLOW (user)
# =========================
@dp.message(F.text == "📦 Зробити замовлення")
async def order_start(message: types.Message):
    if banned_block(message):
        return
    user_state[message.from_user.id] = {"stage": "link"}
    await message.answer("🔗 Надішли посилання на товар.", reply_markup=cancel_kb)


# =========================
#  ADMIN PANEL
# =========================
@dp.message(F.text == "🛠 Адмін-панель")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 Адмін-панель", reply_markup=admin_dashboard)


@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "📊 Статистика\n\n"
        f"👥 Користувачів: {len(user_activity)}\n"
        f"📦 Активних замовлень: {len(orders)}\n"
        f"📁 В архіві: {len(archive)}\n"
        f"🚫 Забанених: {len(banned_users)}",
        reply_markup=admin_dashboard
    )


# =========================
#  ADMIN: SHOW ORDERS BY STATUS
# =========================
async def show_orders(message: types.Message, status: str):
    if not is_admin(message.from_user.id):
        return

    found = False
    for oid, o in orders.items():
        if o.get("status") != status:
            continue
        found = True

        # Кнопки залежать від статусу
        if status == "NEW":
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Одобрити", callback_data=f"approve:{oid}")],
                    [InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject:{oid}")],
                    [InlineKeyboardButton(text="💬 Написати клієнту", callback_data=f"msg:{oid}")]
                ]
            )
        elif status == "WAIT_PAYMENT":
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    # це "підготовка під оплату": зараз натискається вручну, пізніше стане автоматично
                    [InlineKeyboardButton(text="✅ Оплату отримано", callback_data=f"mark_paid:{oid}")],
                    [InlineKeyboardButton(text="💬 Написати клієнту", callback_data=f"msg:{oid}")]
                ]
            )
        elif status in ("PREPARING", "ON_THE_WAY"):
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Наступний статус", callback_data=f"next:{oid}")],
                    [InlineKeyboardButton(text="💬 Написати клієнту", callback_data=f"msg:{oid}")]
                ]
            )
        else:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Написати клієнту", callback_data=f"msg:{oid}")]
                ]
            )

        await message.answer(order_card_text(oid, o), reply_markup=kb)

    if not found:
        await message.answer("📭 Замовлень немає.", reply_markup=admin_dashboard)


@dp.message(F.text == "🆕 Нові")
async def s_new(m: types.Message):
    await show_orders(m, "NEW")


@dp.message(F.text == "💳 Очікує оплату")
async def s_wait(m: types.Message):
    await show_orders(m, "WAIT_PAYMENT")


@dp.message(F.text == "📦 Підготовка")
async def s_prep(m: types.Message):
    await show_orders(m, "PREPARING")


@dp.message(F.text == "🚚 В дорозі")
async def s_way(m: types.Message):
    await show_orders(m, "ON_THE_WAY")


@dp.message(F.text == "❌ Відхилені")
async def s_rej(m: types.Message):
    await show_orders(m, "REJECTED")


@dp.message(F.text == "📁 Архів")
async def s_arch(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    if not archive:
        await m.answer("📁 Архів порожній.", reply_markup=admin_dashboard)
        return

    # показуємо останні 20 (простенько)
    items = list(archive.items())[-20:]
    for oid, o in items:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Видалити з архіву", callback_data=f"del_arch:{oid}")]
            ]
        )
        await m.answer(order_card_text(oid, o), reply_markup=kb)


# =========================
#  ADMIN: USERS LIST (click user -> ban/unban)
# =========================
USERS_PAGE_SIZE = 10


def build_users_page(offset: int = 0) -> InlineKeyboardMarkup:
    uids = sorted(user_activity.keys(), key=lambda x: user_activity.get(x, 0), reverse=True)
    page = uids[offset: offset + USERS_PAGE_SIZE]

    rows = []
    for uid in page:
        prof = user_profiles.get(uid, {})
        username = prof.get("username")
        first_name = prof.get("first_name")

        name = f"@{username}" if username else (first_name or "Без юзера")
        mark = "🚫" if uid in banned_users else "✅"
        rows.append([InlineKeyboardButton(text=f"{mark} {name} ({uid})", callback_data=f"user:{uid}")])

    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"users_page:{offset - USERS_PAGE_SIZE}"))
    if offset + USERS_PAGE_SIZE < len(uids):
        nav.append(InlineKeyboardButton(text="➡️ Далі", callback_data=f"users_page:{offset + USERS_PAGE_SIZE}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.message(F.text == "👥 Користувачі")
async def admin_users(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    kb = build_users_page(0)
    await message.answer(f"👥 Користувачі (усього: {len(user_activity)})", reply_markup=kb)


@dp.callback_query(F.data.startswith("users_page:"))
async def admin_users_page(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    offset = int(callback.data.split(":")[1])
    kb = build_users_page(offset)
    await callback.message.edit_text(f"👥 Користувачі (усього: {len(user_activity)})")
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("user:"))
async def admin_user_card(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    uid = int(callback.data.split(":")[1])
    prof = user_profiles.get(uid, {})
    username = prof.get("username")
    first_name = prof.get("first_name")

    status = "🚫 Забанений" if uid in banned_users else "✅ Активний"
    msgs = user_activity.get(uid, 0)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚫 Забанити", callback_data=f"ban:{uid}"),
                InlineKeyboardButton(text="✅ Розбанити", callback_data=f"unban:{uid}")
            ]
        ]
    )

    text = (
        "👤 Користувач\n\n"
        f"Юзер: @{username}" if username else "Юзер: —"
    )
    # формуємо акуратно, щоб не ламати перенос
    text = (
        "👤 Користувач\n\n"
        f"Юзер: @{username}\n" if username else "👤 Користувач\n\nЮзер: —\n"
    )
    text += f"Імʼя: {first_name or '—'}\n"
    text += f"ID: {uid}\n"
    text += f"Повідомлень: {msgs}\n"
    text += f"Статус: {status}"

    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("ban:"))
async def admin_ban(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    uid = int(callback.data.split(":")[1])
    banned_users.add(uid)
    save_state()
    await callback.answer("🚫 Забанено")


@dp.callback_query(F.data.startswith("unban:"))
async def admin_unban(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    uid = int(callback.data.split(":")[1])
    banned_users.discard(uid)
    save_state()
    await callback.answer("✅ Розбанено")


# =========================
#  CALLBACKS: ORDER ACTIONS
# =========================
@dp.callback_query(F.data.startswith("approve:"))
async def approve(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    oid = callback.data.split(":")[1]
    if oid not in orders or orders[oid].get("status") != "NEW":
        await callback.answer("⚠️ Уже не NEW", show_alert=True)
        return

    user_state[callback.from_user.id] = {"stage": "set_price", "order": oid}
    await callback.message.answer("💰 Введи ціну товару (без комісії):")
    await callback.answer()


@dp.callback_query(F.data.startswith("reject:"))
async def reject(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    oid = callback.data.split(":")[1]
    if oid not in orders:
        await callback.answer("Не знайдено", show_alert=True)
        return

    orders[oid]["status"] = "REJECTED"
    save_state()

    # Попросимо причину
    user_state[callback.from_user.id] = {"stage": "reject_reason", "order": oid}
    await callback.message.answer("✍️ Напиши причину відмови:")
    await callback.answer()


@dp.callback_query(F.data.startswith("msg:"))
async def admin_msg(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    oid = callback.data.split(":")[1]
    if oid not in orders:
        await callback.answer("Не знайдено", show_alert=True)
        return

    user_state[callback.from_user.id] = {"stage": "admin_msg", "order": oid}
    await callback.message.answer("💬 Напиши повідомлення клієнту:")
    await callback.answer()


@dp.callback_query(F.data.startswith("mark_paid:"))
async def mark_paid(callback: types.CallbackQuery):
    """Підготовка під реальну оплату: зараз адмін ставить вручну, потім зробимо автоматично."""
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    oid = callback.data.split(":")[1]
    o = orders.get(oid)
    if not o:
        await callback.answer("Не знайдено", show_alert=True)
        return
    if o.get("status") != "WAIT_PAYMENT":
        await callback.answer("Не той статус", show_alert=True)
        return

    # у майбутньому тут буде webhook/перевірка mono
    o["payment"] = o.get("payment", {})
    o["payment"]["status"] = "PAID"
    o["payment"]["paid_at"] = now_iso()

    o["status"] = "PREPARING"
    save_state()

    await bot.send_message(o["user_id"], f"✅ Оплату за замовлення #{oid} підтверджено.\n📦 Статус: Підготовка")
    await callback.answer("✅ Оплату підтверджено")
    await callback.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data.startswith("next:"))
async def next_status(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    oid = callback.data.split(":")[1]
    o = orders.get(oid)
    if not o:
        await callback.answer("Не знайдено", show_alert=True)
        return

    st = o.get("status")

    if st == "PREPARING":
        o["status"] = "ON_THE_WAY"
        save_state()
        await bot.send_message(o["user_id"], f"🚚 Замовлення #{oid} в дорозі!")
        await callback.answer("🚚 В дорозі")
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    if st == "ON_THE_WAY":
        o["status"] = "DONE"
        archive[oid] = o
        orders.pop(oid, None)
        save_state()
        await bot.send_message(o["user_id"], f"✅ Замовлення #{oid} позначено як отримане. Дякуємо!")
        await callback.answer("✅ В архів")
        await callback.message.edit_reply_markup(reply_markup=None)
        return

    await callback.answer("Немає наступного кроку", show_alert=True)


@dp.callback_query(F.data.startswith("del_arch:"))
async def del_arch(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    oid = callback.data.split(":")[1]
    if oid in archive:
        archive.pop(oid, None)
        save_state()
        await callback.answer("🗑 Видалено")
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("Не знайдено", show_alert=True)


# =========================
#  USER: CANCEL ORDER while WAIT_PAYMENT
# =========================
@dp.callback_query(F.data.startswith("user_cancel:"))
async def user_cancel_order(callback: types.CallbackQuery):
    oid = callback.data.split(":")[1]
    o = orders.get(oid)

    if not o:
        await callback.answer("Замовлення не знайдено", show_alert=True)
        return

    if callback.from_user.id != o.get("user_id"):
        await callback.answer("Це не твоє замовлення", show_alert=True)
        return

    if o.get("status") != "WAIT_PAYMENT":
        await callback.answer("Замовлення вже в обробці", show_alert=True)
        return

    o["status"] = "REJECTED"
    o["rejected_by_user_at"] = now_iso()
    save_state()

    # повідомляємо адмінів
    for a in ADMINS:
        try:
            await bot.send_message(
                a,
                "❌ Клієнт скасував замовлення\n\n" + order_card_text(oid, o)
            )
        except Exception:
            pass

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "❌ Ти відмовився від замовлення.\n"
        "Якщо передумаєш — можеш створити нове 😊",
        reply_markup=main_menu
    )
    await callback.answer("Скасовано")


# =========================
#  PAYMENT STUB (Mono)
# =========================
@dp.callback_query(F.data.startswith("pay_mono:"))
async def pay_mono_stub(callback: types.CallbackQuery):
    oid = callback.data.split(":")[1]
    o = orders.get(oid)
    if not o:
        await callback.answer("Не знайдено", show_alert=True)
        return

    # тільки власник
    if callback.from_user.id != o.get("user_id"):
        await callback.answer("Це не твоє замовлення", show_alert=True)
        return

    if o.get("status") != "WAIT_PAYMENT":
        await callback.answer("Оплата вже неактуальна", show_alert=True)
        return

    # Заготовка під Monobank:
    # Тут пізніше буде створення інвойсу/посилання, і кнопка відкриття.
    await callback.message.answer(
        "💳 Оплата через Monobank\n\n"
        "⏳ Поки що це підготовлено як заглушка.\n"
        "Наступним кроком підключимо реальну оплату (інвойс/посилання/перевірка)."
    )
    await callback.answer()


# =========================
#  EVENTS (admin broadcast) - optional
# =========================
@dp.message(F.text.startswith("/event"))
async def event_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.answer("❌ Формат: /event <текст>")
        return

    text = parts[1]
    sent = 0
    for uid in list(user_activity.keys()):
        try:
            await bot.send_message(uid, f"🎉 АКЦІЯ!\n\n{text}")
            sent += 1
        except Exception:
            pass

    try:
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{now_iso()} | {text} | sent={sent}\n")
    except Exception:
        pass

    await message.answer(f"✅ Івент надіслано {sent} користувачам.")


# =========================
#  TEXT ROUTER (single)
# =========================
@dp.message()
async def router(message: types.Message):
    uid = message.from_user.id

    # профіль + активність
    user_profiles[uid] = {
        "username": message.from_user.username,
        "first_name": message.from_user.first_name
    }
    user_activity[uid] = user_activity.get(uid, 0) + 1

    # бан — ігноруємо
    if uid in banned_users:
        save_state()
        return

    state = user_state.get(uid)

    # якщо нема state — нічого не робимо (щоб бот не відповідав на будь-що)
    if not state:
        save_state()
        return

    stage = state.get("stage")

    # -------------------------
    # SUPPORT: user -> admin
    # -------------------------
    if stage == "support":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💬 Відповісти", callback_data=f"support_reply:{uid}")]
            ]
        )

        for a in ADMINS:
            try:
                await bot.send_message(
                    a,
                    "💬 Звернення в підтримку\n\n"
                    f"👤 Юзер: {safe_username(message.from_user)}\n"
                    f"🆔 ID: {uid}\n\n"
                    f"{message.text}",
                    reply_markup=kb
                )
            except Exception:
                pass

        user_state.pop(uid, None)
        await message.answer("✅ Повідомлення передано підтримці.", reply_markup=main_menu)
        save_state()
        return

    # -------------------------
    # ORDER FLOW (user)
    # -------------------------
    if stage == "link":
        state["link"] = message.text.strip()
        state["stage"] = "desc"
        await message.answer("📝 Опиши товар (колір, розмір тощо).")
        save_state()
        return

    if stage == "desc":
        state["desc"] = message.text.strip()
        state["stage"] = "contact"
        await message.answer("📱 Залиш контакт для звʼязку.")
        save_state()
        return

    if stage == "contact":
        state["contact"] = message.text.strip()
        state["stage"] = "promo"
        await message.answer("🎟 Маєш промокод? Якщо ні — напиши `ні`.")
        save_state()
        return

    if stage == "promo":
        promo_raw = message.text.strip().upper()
        promo = promo_raw if promo_raw in PROMOCODES else None

        oid = str(uuid.uuid4())[:8]
        orders[oid] = {
            "created_at": now_iso(),
            "user_id": uid,
            "username": safe_username(message.from_user),
            "link": state.get("link"),
            "desc": state.get("desc"),
            "contact": state.get("contact"),
            "promo": promo,
            "discount": PROMOCODES.get(promo, 0.0),
            "status": "NEW",
            # підготовка під оплату (заповниться після підтвердження ціни)
            "payment": {
                "method": None,
                "required": 0.0,
                "paid": 0.0,
                "status": "NOT_PAID"
            }
        }

        user_state.pop(uid, None)

        # детальне повідомлення адміну + кнопки
        for a in ADMINS:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Одобрити", callback_data=f"approve:{oid}")],
                    [InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject:{oid}")],
                    [InlineKeyboardButton(text="💬 Написати клієнту", callback_data=f"msg:{oid}")]
                ]
            )
            try:
                await bot.send_message(a, order_card_text(oid, orders[oid]), reply_markup=kb)
            except Exception:
                pass

        await message.answer("✅ Замовлення створено. Очікуй відповідь адміністратора.", reply_markup=main_menu)
        save_state()
        return

    # -------------------------
    # ADMIN: set price after approve
    # -------------------------
    if stage == "set_price":
        if not is_admin(uid):
            user_state.pop(uid, None)
            save_state()
            return

        oid = state.get("order")
        o = orders.get(oid)
        if not o:
            user_state.pop(uid, None)
            await message.answer("⚠️ Замовлення не знайдено.", reply_markup=admin_dashboard)
            save_state()
            return

        try:
            base = float(message.text.replace(",", "."))
            if base <= 0:
                raise ValueError
        except ValueError:
            await message.answer("❌ Введи число (наприклад: 999 або 999.50).")
            save_state()
            return

        commission = base * COMMISSION_RATE
        discount = commission * float(o.get("discount", 0.0))
        final = round(base + commission - discount, 2)

        o["base_price"] = base
        o["commission"] = round(commission, 2)
        o["discount_value"] = round(discount, 2)
        o["final_price"] = final
        o["status"] = "WAIT_PAYMENT"

        o["payment"] = o.get("payment", {})
        o["payment"]["method"] = "mono"  # підготовка (можна буде вибір)
        o["payment"]["required"] = final
        o["payment"]["paid"] = 0.0
        o["payment"]["status"] = "NOT_PAID"

        user_state.pop(uid, None)
        save_state()

        # user gets payment buttons (stub + cancel)
        pay_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатити (Mono)", callback_data=f"pay_mono:{oid}")],
                [InlineKeyboardButton(text="❌ Відмовитись", callback_data=f"user_cancel:{oid}")]
            ]
        )

        await bot.send_message(
            o["user_id"],
            f"✅ Замовлення #{oid} підтверджено!\n\n"
            f"💰 Ціна товару: {base} грн\n"
            f"💼 Комісія: {o['commission']} грн\n"
            f"🎟 Знижка: {o['discount_value']} грн\n\n"
            f"👉 До сплати: **{final} грн**\n"
            f"⏳ Статус: Очікує оплату",
            reply_markup=pay_kb
        )

        await message.answer("💳 Готово. Статус: Очікує оплату.", reply_markup=admin_dashboard)
        return

    # -------------------------
    # ADMIN: reject reason
    # -------------------------
    if stage == "reject_reason":
        if not is_admin(uid):
            user_state.pop(uid, None)
            save_state()
            return

        oid = state.get("order")
        o = orders.get(oid)
        if not o:
            user_state.pop(uid, None)
            await message.answer("⚠️ Замовлення не знайдено.", reply_markup=admin_dashboard)
            save_state()
            return

        reason = message.text.strip()
        o["reject_reason"] = reason
        o["rejected_at"] = now_iso()
        save_state()

        await bot.send_message(
            o["user_id"],
            f"❌ Замовлення #{oid} відхилено.\n"
            f"Причина: {reason}"
        )

        user_state.pop(uid, None)
        await message.answer("❌ Відмову надіслано.", reply_markup=admin_dashboard)
        return

    # -------------------------
    # ADMIN: message user
    # -------------------------
    if stage == "admin_msg":
        if not is_admin(uid):
            user_state.pop(uid, None)
            save_state()
            return

        oid = state.get("order")
        o = orders.get(oid)
        if not o:
            user_state.pop(uid, None)
            await message.answer("⚠️ Замовлення не знайдено.", reply_markup=admin_dashboard)
            save_state()
            return

        await bot.send_message(
            o["user_id"],
            f"💬 Від адміністратора (замовлення #{oid}):\n\n{message.text}"
        )

        user_state.pop(uid, None)
        await message.answer("✅ Надіслано.", reply_markup=admin_dashboard)
        save_state()
        return

    # -------------------------
    # ADMIN: reply support
    # -------------------------
    if stage == "support_answer":
        if not is_admin(uid):
            user_state.pop(uid, None)
            save_state()
            return

        target = state.get("user_id")
        if not target:
            user_state.pop(uid, None)
            save_state()
            return

        await bot.send_message(
            int(target),
            f"💬 Відповідь адміністратора:\n\n{message.text}"
        )
        user_state.pop(uid, None)
        await message.answer("✅ Відповідь надіслано.", reply_markup=admin_dashboard)
        save_state()
        return

    # fallback
    save_state()


# =========================
#  SUPPORT REPLY BUTTON
# =========================
@dp.callback_query(F.data.startswith("support_reply:"))
async def support_reply(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    target_uid = int(callback.data.split(":")[1])
    user_state[callback.from_user.id] = {"stage": "support_answer", "user_id": target_uid}

    await callback.message.answer("✍️ Напиши відповідь користувачу:", reply_markup=cancel_kb)
    await callback.answer()


# =========================
#  RUN
# =========================
async def main():
    # на випадок якщо хтось видалив папку під час роботи
    os.makedirs(HISTORY_DIR, exist_ok=True)
    save_state()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
