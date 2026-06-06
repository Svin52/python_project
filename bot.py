import os
import aiosqlite
import sqlite3
from datetime import datetime
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
                status TEXT DEFAULT 'отсутствует',
                UNIQUE(user_id, date)
            )
        ''')
    await conn.commit()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,))
        if not await cursor.fetchone():
            await cursor.execute(
                "INSERT INTO users (id, username, registered_at) VALUES (?, ?, ?)",
                (message.from_user.id, message.from_user.username or "unknown", datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            await conn.commit()
            await message.answer("Вы зарегистрированы в боте.\n"
                                 "Преподаватель сможет отмечать ваши отсутствия.")
        else:
            await message.answer("Вы уже зарегистрированы в системе.")


@dp.message(Command("отсутствующие"))
async def cmd_absent(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта команда доступна только преподавателю.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Формат: `/отсутствующие @ivanov @petrov`")
        return

    usernames = [u.lstrip("@") for u in args[1:]]
    date = datetime.now().strftime("%Y-%m-%d")
    marked, skipped, not_found = [], [], []

    async with conn.cursor() as cursor:
        for uname in usernames:
            await cursor.execute("SELECT id FROM users WHERE username = ?", (uname,))
            user = await cursor.fetchone()
            if not user:
                not_found.append(uname)
                continue

            try:
                await cursor.execute(
                    "INSERT INTO attendance (user_id, date, status) VALUES (?, ?, 'отсутствует')",
                    (user[0], date)
                )
                await conn.commit()
                marked.append(uname)
            except sqlite3.IntegrityError:
                skipped.append(uname)

    text = f"Отметка отсутствующих ({date}):\n"
    if marked: text += f"Отмечены: {', '.join('@'+u for u in marked)}\n"
    if skipped: text += f"Уже отмечены: {', '.join('@'+u for u in skipped)}\n"
    if not_found: text += f"Не в базе (не нажали /start): {', '.join('@'+u for u in not_found)}\n"
    await message.answer(text)


@dp.message(Command("моя_посещаемость"))
async def cmd_my_attendance(message: types.Message):
    async with conn.cursor() as cursor:
        await cursor.execute(
            "SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC",
            (message.from_user.id,)
        )
        records = await cursor.fetchall()

    if not records:
        await message.answer("У вас нет записей об отсутствиях. Всё отлично!")
        return

    text = "Ваши пропуски:\n"
    for (date,) in records:
        text += f"{date} | Отсутствовал\n"
    await message.answer(text)


@dp.message(Command("статистика"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Эта команда доступна только преподавателю.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Пример: `/статистика @ivanov`")
        return

    target = args[1].lstrip("@")
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT id FROM users WHERE username = ?", (target,))
        user = await cursor.fetchone()
        if not user:
            await message.answer("Студент не найден в базе.")
            return

        await cursor.execute("SELECT COUNT(*) FROM attendance WHERE user_id = ?", (user[0],))
        absent_count = (await cursor.fetchone())[0]
        
        await cursor.execute("SELECT COUNT(*) FROM users")
        total_students = (await cursor.fetchone())[0]

    await message.answer(
        f"Статистика @{target}:\n"
        f"Отсутствовал: {absent_count} раз(а)\n"
        f"Всего в системе: {total_students} чел."
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Справка по боту посещаемости:\n\n"
        " Студентам:\n"
        "/start — зарегистрироваться в системе\n"
        "/моя_посещаемость — посмотреть свои пропуски\n\n"
        " Преподавателю:\n"
        "/отсутствующие @ivanov @petrov — отметить пропуски за сегодня\n"
        "/статистика @ivanov — количество пропусков студента\n\n"
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