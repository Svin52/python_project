import os
import aiosqlite
import sqlite3
import secrets
import io
import qrcode
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = set()
if ADMIN_IDS_STR:
    for x in ADMIN_IDS_STR.split(","):
        if x.strip():
            ADMIN_IDS.add(int(x.strip()))

BOT_USERNAME = "attendance12331_bot"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
conn = None

async def init_db():
    global conn
    conn = await aiosqlite.connect("attendance.db")
    async with conn.cursor() as cursor:

        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                registered_at TEXT
            )
        ''')
        
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                status TEXT DEFAULT 'присутствует',
                UNIQUE(user_id, date)
            )
        ''')

        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS qr_tokens (
                token TEXT PRIMARY KEY,
                admin_id INTEGER,
                expires_at TEXT
            )
        ''')
    await conn.commit()


@dp.message(Command("qr"))
async def cmd_generate_qr(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта команда доступна только преподавателю.")
        return

    token = secrets.token_hex(16)
    
    now = datetime.now()
    expires_at = now + timedelta(minutes=30)
    
    async with conn.cursor() as cursor:
        await cursor.execute(
            "INSERT INTO qr_tokens (token, admin_id, expires_at) VALUES (?, ?, ?)",
            (token, message.from_user.id, expires_at.strftime("%Y-%m-%d %H:%M:%S"))
        )
    await conn.commit()

    deep_link = f"https://t.me/{BOT_USERNAME}?start={token}"


    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    await message.answer_photo(
        photo=types.BufferedInputFile(buf.getvalue(), filename="qr.png"),
        caption=(
            "QR-код сгенерирован.\n"
            f"Действителен до: {expires_at.strftime('%H:%M')}\n\n"
        )
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    parts = message.text.split()
    
    if len(parts) > 1:
        token = parts[1]
        await handle_qr_scan(message, token)
    else:
        await register_user(message)

async def register_user(message: types.Message):
    """Функция регистрации"""
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,))
        if not await cursor.fetchone():
            await cursor.execute(
                "INSERT INTO users (id, username, registered_at) VALUES (?, ?, ?)",
                (message.from_user.id, message.from_user.username or "unknown", datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            await conn.commit()
            await message.answer("Вы зарегистрированы в системе учета посещаемости.")
        else:
            await message.answer("Вы уже зарегистрированы в системе.")

async def handle_qr_scan(message: types.Message, token: str):
    """Функция для QR"""
    async with conn.cursor() as cursor:

        await cursor.execute("SELECT expires_at FROM qr_tokens WHERE token = ?", (token,))
        row = await cursor.fetchone()
        
        if not row:
            await message.answer("Неверный QR-код или он уже был использован.")
            return

        expires_at_str = row[0]
        expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")

        if datetime.now() > expires_at:
            await message.answer(" Срок действия этого QR-кода истек. Попросите преподавателя сгенерировать новый.")
            return

        await cursor.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,))
        user = await cursor.fetchone()
        
        if not user:
            await cursor.execute(
                "INSERT INTO users (id, username, registered_at) VALUES (?, ?, ?)",
                (message.from_user.id, message.from_user.username or "unknown", datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
        
        date = datetime.now().strftime("%Y-%m-%d")
        try:
            await cursor.execute(
                "INSERT INTO attendance (user_id, date, status) VALUES (?, ?, 'присутствует')",
                (message.from_user.id, date)
            )
            await conn.commit()
            await message.answer("Вы успешно отмечены как присутствующий!")
        except sqlite3.IntegrityError:
            await message.answer("Вы уже были отмечены на сегодня.")


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта команда доступна только преподавателю.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT COUNT(*) FROM attendance WHERE date = ?", (today,))
        present_count = (await cursor.fetchone())[0]
        
        await cursor.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0]

    await message.answer(
        f" Статистика за ({today}):\n"
        f"Присутствовало: {present_count} чел.\n"
    )


@dp.message(Command("my"))
async def cmd_my(message: types.Message):
    async with conn.cursor() as cursor:
        await cursor.execute(
            "SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC",
            (message.from_user.id,)
        )
        records = await cursor.fetchall()

    if not records:
        await message.answer("У вас нет записей о присутствии.")
        return

    text = "Дни вашего присутствия:\n"
    for (date,) in records:
        text += f"--- {date}\n"
    
    await message.answer(text)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Для студентов:\n"
        "/start — регистрация в системе\n"
        "/my — посмотреть свои дни присутствия\n\n"
        "Для преподавателя:\n"
        "/qr — сгенерировать QR-код для отметки присутствия\n"
        "/stats — общая статистика за сегодня"
    )


async def main():
    print("Бот запущен.")
    await init_db()
    try:
        await dp.start_polling(bot)
    finally:
        await conn.close()
        print("Соединение с БД закрыто.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())