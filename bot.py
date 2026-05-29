import os
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

conn = sqlite3.connect("attendance.db")

def init_db():
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            registered_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            status TEXT DEFAULT 'отсутствует',
            UNIQUE(user_id, date)  -- Защита от дублей в один день
        )
    ''')
    conn.commit()

init_db()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    cursor = conn.cursor()
    if not cursor.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,)).fetchone():
        cursor.execute("INSERT INTO users (id, username, registered_at) VALUES (?, ?, ?)",
                       (message.from_user.id, message.from_user.username or "unknown", datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
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
    cursor = conn.cursor()

    marked, skipped, not_found = [], [], []

    for uname in usernames:
        user = cursor.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()
        if not user:
            not_found.append(uname)
            continue

        try:
            cursor.execute("INSERT INTO attendance (user_id, date, status) VALUES (?, ?, 'отсутствует')",
                           (user[0], date))
            conn.commit()
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
    cursor = conn.cursor()
    records = cursor.execute(
        "SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC",
        (message.from_user.id,)
    ).fetchall()

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
    cursor = conn.cursor()
    user = cursor.execute("SELECT id FROM users WHERE username = ?", (target,)).fetchone()
    if not user:
        await message.answer("Студент не найден в базе.")
        return

    absent_count = cursor.execute("SELECT COUNT(*) FROM attendance WHERE user_id = ?", (user[0],)).fetchone()[0]
    total_students = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]

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
    try:
        await dp.start_polling(bot)
    finally:
        conn.close()
        print("Соединение с БД закрыто.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())