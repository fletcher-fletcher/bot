import logging
import sqlite3
import asyncio
import os
import sys
import traceback
from datetime import datetime
from typing import Optional
from aiohttp import web
from functools import wraps

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/data/debug.log', mode='a')
    ]
)
logging.debug("="*50)
logging.debug("🚀 БОТ ЗАПУСКАЕТСЯ")
logging.debug("="*50)

DB_PATH = os.getenv('DB_PATH', '/data/efir_bot.db')

# Декоратор для логирования функций
def log_function_call(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logging.debug(f"🔵 Вход в функцию: {func.__name__}")
        try:
            result = await func(*args, **kwargs)
            logging.debug(f"🟢 Выход из функции: {func.__name__}")
            return result
        except Exception as e:
            logging.error(f"🔴 Ошибка в функции {func.__name__}: {e}", exc_info=True)
            raise
    return wrapper

# Обработка необработанных исключений
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logging.error("❌ Необработанное исключение", 
                  exc_info=(exc_type, exc_value, exc_traceback))
    
    try:
        with open('/data/error.log', 'a') as f:
            f.write(f"\n--- {datetime.now()} ---\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except:
        pass

sys.excepthook = handle_exception

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8379899619:AAFZm9gC4r8nbZ0j_Xe7DzrbRKSxyi7_UlI"
ADMIN_IDS = [5333876901]

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Варианты для поля "Кто вы"
PROFESSION_OPTIONS = [
    "Предприниматель",
    "Юрист", 
    "Бухгалтер",
    "Наёмный сотрудник",
    "Другое"
]

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    """Создание таблиц при первом запуске"""
    logging.debug("Инициализация базы данных")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            room_link TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            profession TEXT NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, event_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.debug("База данных инициализирована")

# [Все ваши функции работы с БД остаются без изменений]
def create_event(code: str, title: str, room_link: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO events (code, title, room_link) VALUES (?, ?, ?)",
            (code, title, room_link)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_event_by_code(code: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE code = ?", (code,))
    event = cur.fetchone()
    conn.close()
    return dict(event) if event else None

def get_event_by_id(event_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = cur.fetchone()
    conn.close()
    return dict(event) if event else None

def check_registration(user_id: int, event_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM registrations WHERE user_id = ? AND event_id = ?",
        (user_id, event_id)
    )
    result = cur.fetchone()
    conn.close()
    return result is not None

def save_registration(user_id: int, event_id: int, username: str, full_name: str, phone: str, profession: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO registrations 
               (user_id, event_id, username, full_name, phone, profession) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, event_id, username, full_name, phone, profession)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_registrations_count(event_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def export_event_registrations(event_code: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT r.*, e.title as event_title 
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        WHERE e.code = ?
        ORDER BY r.registered_at
    """, (event_code,))
    registrations = cur.fetchall()
    conn.close()
    return registrations

# ==================== СОСТОЯНИЯ FSM ====================
class Registration(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_profession = State()
    waiting_for_custom_profession = State()

# ==================== КОМАНДЫ АДМИНА ====================
@dp.message(Command("new"))
@log_function_call
async def cmd_new_event(message: types.Message):
    # ... ваш код без изменений ...
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ У вас нет прав на выполнение этой команды.")
        return
    
    try:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            await message.reply(
                "❌ Неправильный формат. Используйте:\n"
                "/new КОД | НАЗВАНИЕ | ССЫЛКА НА КОМНАТУ\n\n"
                "Пример: /new may2025 | Майский эфир 2025 | https://zoom.us/j/123"
            )
            return
        
        parts = command_parts[1].strip().split('|')
        if len(parts) < 3:
            await message.reply(
                "❌ Неправильный формат. Используйте:\n"
                "/new КОД | НАЗВАНИЕ | ССЫЛКА НА КОМНАТУ\n\n"
                "Пример: /new may2025 | Майский эфир 2025 | https://zoom.us/j/123"
            )
            return
        
        code = parts[0].strip()
        title = parts[1].strip()
        room_link = parts[2].strip()
        
        if not room_link.startswith(('http://', 'https://')):
            await message.reply("❌ Ссылка должна начинаться с http:// или https://")
            return
        
        if create_event(code, title, room_link):
            bot_info = await bot.me()
            bot_link = f"https://t.me/{bot_info.username}?start={code}"
            
            response = (
                f"✅ Эфир успешно создан!\n\n"
                f"📌 Код: {code}\n"
                f"📝 Название: {title}\n"
                f"🔗 Комната: {room_link}\n\n"
                f"🔗 Ссылка для поста в канале:\n"
                f"<code>{bot_link}</code>\n\n"
                f"📊 Статистика будет доступна по команде:\n"
                f"/stats {code}"
            )
            
            await message.reply(response)
        else:
            await message.reply("❌ Эфир с таким кодом уже существует!")
            
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")

@dp.message(Command("stats"))
@log_function_call
async def cmd_event_stats(message: types.Message):
    # ... ваш код без изменений ...
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ У вас нет прав на выполнение этой команды.")
        return
    
    command_parts = message.text.split()
    if len(command_parts) < 2:
        await message.reply("❌ Укажите код эфира. Пример: /stats may2025")
        return
    
    args = command_parts[1]
    registrations = export_event_registrations(args)
    
    if not registrations:
        await message.reply(f"📭 На эфир с кодом '{args}' пока никто не зарегистрировался")
        return
    
    event_title = registrations[0]['event_title']
    response = f"📊 Статистика по эфиру: {event_title}\n"
    response += f"📌 Код: {args}\n"
    response += f"👥 Всего регистраций: {len(registrations)}\n\n"
    response += "📋 Список участников:\n"
    
    for i, reg in enumerate(registrations, 1):
        response += f"{i}. {reg['full_name']}\n"
        response += f"   📱 {reg['phone']}\n"
        response += f"   💼 {reg['profession']}\n"
        response += f"   🆔 @{reg['username'] if reg['username'] else 'нет'}\n"
        response += f"   🕐 {reg['registered_at'][:16]}\n\n"
        
        if len(response) > 3500:
            response += "... (продолжение в следующем сообщении)"
            await message.reply(response)
            response = ""
    
    if response:
        await message.reply(response)

@dp.message(Command("events"))
@log_function_call
async def cmd_list_events(message: types.Message):
    # ... ваш код без изменений ...
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("⛔ У вас нет прав на выполнение этой команды.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM events ORDER BY created_at DESC")
    events = cur.fetchall()
    conn.close()
    
    if not events:
        await message.reply("📭 Пока нет созданных эфиров")
        return
    
    response = "📋 Все эфиры:\n\n"
    for event in events:
        count = get_registrations_count(event['id'])
        response += (
            f"🔹 {event['title']}\n"
            f"   Код: {event['code']}\n"
            f"   Участников: {count}\n"
            f"   Создан: {event['created_at'][:16]}\n"
            f"   /stats {event['code']}\n\n"
        )
    
    await message.reply(response)

# ==================== РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЕЙ ====================
@dp.message(Command("start"))
@log_function_call
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработка команды /start с параметром или без"""
    logging.debug(f"🔥 /start от пользователя {message.from_user.id}")
    
    command_parts = message.text.split()
    args = command_parts[1] if len(command_parts) > 1 else ""
    
    if not args:
        await message.reply(
            "👋 Добро пожаловать!\n\n"
            "Это бот для регистрации на прямые эфиры.\n"
            "Чтобы зарегистрироваться, перейдите по специальной ссылке из поста в канале."
        )
        return
    
    logging.debug(f"📌 Код эфира: {args}")
    event = get_event_by_code(args)
    
    if not event:
        logging.debug(f"❌ Эфир {args} не найден")
        await message.reply("❌ Эфир не найден или ссылка устарела.")
        return
    
    logging.debug(f"✅ Эфир найден: {event['title']}")
    await state.update_data(event_id=event['id'], event_code=args)
    
    if check_registration(message.from_user.id, event['id']):
        logging.debug(f"👤 Пользователь уже зарегистрирован")
        event = get_event_by_id(event['id'])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти в комнату", url=event['room_link'])]
        ])
        await message.reply(
            f"🔔 Вы уже зарегистрированы на этот эфир!\n\n"
            f"🎥 {event['title']}\n\n"
            f"🔗 Ссылка для входа:",
            reply_markup=keyboard
        )
        return
    
    logging.debug(f"📝 Начинаем регистрацию")
    await message.reply(
        f"📝 <b>Регистрация на эфир:</b>\n"
        f"<i>{event['title']}</i>\n\n"
        f"Пожалуйста, введите ваше <b>полное имя</b> (ФИО):"
    )
    await state.set_state(Registration.waiting_for_full_name)

# [Все остальные обработчики остаются без изменений]
@dp.message(Registration.waiting_for_full_name)
@log_function_call
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if len(full_name.split()) < 2:
        await message.reply("❌ Пожалуйста, введите полное имя (имя и фамилию):")
        return
    
    await state.update_data(full_name=full_name)
    await message.reply(
        "📞 Теперь введите ваш <b>номер телефона</b>:\n"
        "Например: +7 (999) 123-45-67"
    )
    await state.set_state(Registration.waiting_for_phone)

@dp.message(Registration.waiting_for_phone)
@log_function_call
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if len(phone) < 10:
        await message.reply("❌ Слишком короткий номер. Введите корректный телефон:")
        return
    
    await state.update_data(phone=phone)
    
    keyboard_builder = ReplyKeyboardBuilder()
    for prof in PROFESSION_OPTIONS:
        keyboard_builder.button(text=prof)
    keyboard_builder.adjust(2)
    
    await message.reply(
        "💼 Кто вы по роду деятельности?\n"
        "Выберите из списка или напишите свой вариант:",
        reply_markup=keyboard_builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
    )
    await state.set_state(Registration.waiting_for_profession)

@dp.message(Registration.waiting_for_profession)
@log_function_call
async def process_profession(message: types.Message, state: FSMContext):
    profession = message.text.strip()
    
    if profession == "Другое":
        await message.reply(
            "✍️ Напишите ваш вариант:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(Registration.waiting_for_custom_profession)
    else:
        await complete_registration(message, state, profession)

@dp.message(Registration.waiting_for_custom_profession)
@log_function_call
async def process_custom_profession(message: types.Message, state: FSMContext):
    profession = message.text.strip()
    if len(profession) < 2:
        await message.reply("❌ Слишком короткое значение. Опишите подробнее:")
        return
    
    await complete_registration(message, state, profession)

@log_function_call
async def complete_registration(message: types.Message, state: FSMContext, profession: str):
    data = await state.get_data()
    event = get_event_by_id(data['event_id'])
    
    if not event:
        await message.reply(
            "❌ Произошла ошибка. Эфир не найден.",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.clear()
        return
    
    username = message.from_user.username or ""
    
    if save_registration(
        message.from_user.id,
        event['id'],
        username,
        data['full_name'],
        data['phone'],
        profession
    ):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти в комнату", url=event['room_link'])]
        ])
        
        response = (
            f"✅ <b>Регистрация завершена!</b>\n\n"
            f"Спасибо, {data['full_name']}!\n"
            f"Вы зарегистрированы на эфир:\n"
            f"<i>{event['title']}</i>\n\n"
            f"🔗 <b>Ссылка для входа:</b>"
        )
        
        await message.reply(response, reply_markup=keyboard)
        
        reg_count = get_registrations_count(event['id'])
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📝 <b>Новая регистрация!</b>\n"
                    f"🎥 Эфир: {event['title']}\n"
                    f"👤 Имя: {data['full_name']}\n"
                    f"📞 Телефон: {data['phone']}\n"
                    f"💼 Кто: {profession}\n"
                    f"🆔 @{username if username else 'нет username'}\n"
                    f"📊 Всего на эфире: {reg_count}"
                )
            except:
                pass
    else:
        await message.reply(
            "❌ Ошибка при сохранении. Возможно, вы уже регистрировались на этот эфир.",
            reply_markup=ReplyKeyboardRemove()
        )
    
    await state.clear()

@dp.message(Command("cancel"))
@log_function_call
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.reply(
        "❌ Регистрация отменена.",
        reply_markup=ReplyKeyboardRemove()
    )

# ==================== ЗАПУСК ====================
async def handle_health(request):
    return web.Response(text="🤖 Bot is running")

async def run_web():
    app = web.Application()
    app.router.add_get('/', handle_health)
    app.router.add_get('/health', handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    logging.info("🌐 Веб-сервер запущен на порту 8000")
    
async def self_ping():
    """Периодически пингуем свой веб-сервер"""
    import aiohttp
    while True:
        try:
            await asyncio.sleep(60)  # Каждую минуту
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8000/health', timeout=5) as resp:
                    if resp.status == 200:
                        logging.debug("✅ Self-ping successful")
                    else:
                        logging.warning(f"⚠️ Self-ping returned {resp.status}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"❌ Self-ping error: {e}")

async def main():
    """Главная функция запуска бота"""
    logging.debug("🔥 main() стартовала")
    
    try:
        # Запускаем веб-сервер
        asyncio.create_task(run_web())
        
        # 👇 ДОБАВЬТЕ ЭТУ СТРОКУ 👇
        asyncio.create_task(self_ping())  # Пингуем свой сервер каждую минуту
        
        # Проверяем папку /data
        try:
            os.makedirs('/data', exist_ok=True)
            # Проверяем запись
            with open('/data/test.txt', 'w') as f:
                f.write('test')
            os.remove('/data/test.txt')
            logging.info("✅ Папка /data доступна для записи")
        except Exception as e:
            logging.error(f"❌ Папка /data НЕ доступна: {e}")
        
        # Инициализируем БД
        init_db()
        
        print("="*50)
        print("🤖 Бот для регистрации на эфиры запущен!")
        print("="*50)
        print(f"📁 База данных: {DB_PATH}")
        print("\n📋 Команды администратора:")
        print("/new КОД | НАЗВАНИЕ | ССЫЛКА - создать эфир")
        print("/events - список всех эфиров")
        print("/stats КОД - статистика по эфиру")
        print("\n👤 Команды пользователей:")
        print("/start - начать работу с ботом")
        print("/cancel - отменить регистрацию")
        print("="*50)
        
        logging.info("🚀 Запуск polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logging.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    asyncio.run(main())