import os
import logging
import asyncio
import random
import threading
import aiohttp
from io import BytesIO
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from flask import Flask

# ========== ТОЛЬКО ТОКЕН TELEGRAM (из переменных окружения) ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Не задана переменная окружения TELEGRAM_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Редкости и генерация имен (без изменений) -----
RARITIES = [
    {"name": "обычный", "chance": 70, "emoji": "⬜", "prompt_prefix": "simple, common"},
    {"name": "редкий", "chance": 20, "emoji": "🟦", "prompt_prefix": "intricate, glowing"},
    {"name": "легендарный", "chance": 8, "emoji": "🌟", "prompt_prefix": "epic, legendary, masterpiece"},
    {"name": "эпический", "chance": 2, "emoji": "💎", "prompt_prefix": "godly, transcendent, cosmic"},
]

def choose_rarity():
    r = random.randint(1, 100)
    cum = 0
    for rar in RARITIES:
        cum += rar["chance"]
        if r <= cum:
            return rar
    return RARITIES[0]

def generate_artifact_name(rarity):
    themes = ["кристалл", "амулет", "меч", "кольцо", "свиток", "маска", "ключ", "зеркало"]
    theme = random.choice(themes)
    if rarity["name"] == "легендарный":
        return f"Легендарный {theme} судьбы"
    elif rarity["name"] == "эпический":
        return f"Эпический {theme} вселенной"
    else:
        return f"{rarity['name'].capitalize()} {theme}"

# ----- НОВАЯ функция генерации картинки через Pollinations AI (без токена!) -----
async def generate_image_pollinations(prompt):
    # Экранируем промпт для URL
    encoded_prompt = aiohttp.helpers.quote(prompt)
    # Используем параметр для получения обычного изображения, а не SVG
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&nologo=true"
    
    for attempt in range(3): # Делаем 3 попытки на случай временных сбоев
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        # Простая проверка, что мы получили изображение, а не HTML-страницу с ошибкой
                        if image_data and len(image_data) > 1000:
                            return image_data
                        else:
                            logger.warning(f"Pollinations вернул подозрительно маленький ответ ({len(image_data)} байт)")
                    else:
                        logger.error(f"Pollinations error {resp.status}: {await resp.text()}")
        except aiohttp.client_exceptions.ClientConnectorError as e:
            logger.warning(f"Ошибка подключения к Pollinations, попытка {attempt+1}/3: {e}")
        except Exception as e:
            logger.exception(f"Неизвестная ошибка при запросе к Pollinations: {e}")
        
        if attempt < 2:
            await asyncio.sleep(2) # Ждём 2 секунды перед повтором
    return None

# ----- Команды бота (без изменений) -----
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 *Артефакториум (на Pollinations AI)*\n\n"
        "Я создаю уникальные предметы с помощью нейросети.\n"
        "/buy — получить случайный артефакт с картинкой\n"
        "/help — справка",
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("/start — приветствие\n/buy — артефакт\n/help — эта справка")

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    waiting_msg = await message.answer("🎨 Генерирую артефакт, подождите 10–15 секунд...")
    rarity = choose_rarity()
    name = generate_artifact_name(rarity)
    prompt = f"{rarity['prompt_prefix']}, {name}, fantasy artifact, digital art, detailed, beautiful"
    image_data = await generate_image_pollinations(prompt)
    if image_data:
        photo = BytesIO(image_data)
        photo.name = "artifact.png"
        caption = f"{rarity['emoji']} *{name}*\nРедкость: {rarity['name']}"
        await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
        await waiting_msg.delete()
    else:
        await waiting_msg.edit_text("❌ Не удалось создать артефакт. Попробуйте позже.")

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Напишите /start")

# ----- Flask-сервер для Render (без изменений) -----
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

# ----- Запуск (без изменений) -----
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен, генерация изображений через Pollinations AI")
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
