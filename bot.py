import logging
import asyncio
import random
import threading
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from flask import Flask

# ========== ТОКЕНЫ (ЗАМЕНИТЕ НА СВОИ) ==========
TELEGRAM_TOKEN = "8876252162:AAGiBvNqniHXK4emXXeierk1B-n4w1ihBVI"   # например "123456:ABCdef..."
REPLICATE_API_TOKEN = "r8_JKxkgxU1Cj1nfNIQP6VZWTJmwNlcYfx4UyZGM"              # ваш токен от replicate.com
# ===============================================

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# --- Настройка логов ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- База редкостей ---
RARITIES = [
    {"name": "обычный", "chance": 70, "emoji": "⬜", "prompt_prefix": "simple, common"},
    {"name": "редкий", "chance": 20, "emoji": "🟦", "prompt_prefix": "intricate, glowing"},
    {"name": "легендарный", "chance": 8, "emoji": "🌟", "prompt_prefix": "epic, legendary, masterpiece"},
    {"name": "эпический", "chance": 2, "emoji": "💎", "prompt_prefix": "godly, transcendent, cosmic"},
]

def choose_rarity():
    r = random.randint(1, 100)
    cumulative = 0
    for rar in RARITIES:
        cumulative += rar["chance"]
        if r <= cumulative:
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

async def generate_image(prompt):
    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "version": "39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",  # SDXL
        "input": {
            "prompt": prompt,
            "negative_prompt": "blurry, ugly, low quality",
            "width": 768,
            "height": 768,
            "num_outputs": 1
        }
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                if resp.status != 201:
                    logger.error(f"Replicate error {resp.status}: {data}")
                    return None
                pred_id = data["id"]
            # Ждём результат
            for _ in range(30):  # 30 секунд таймаут
                await asyncio.sleep(1)
                async with session.get(f"{url}/{pred_id}", headers=headers) as status_resp:
                    status_data = await status_resp.json()
                    if status_data["status"] == "succeeded":
                        return status_data["output"][0]
                    elif status_data["status"] == "failed":
                        logger.error(f"Replicate failed: {status_data}")
                        return None
            logger.error("Replicate timeout")
            return None
        except Exception as e:
            logger.exception("Replicate exception")
            return None

# --- Команды бота ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 *Артефакториум*\n\n"
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
    # Сообщим, что начали генерацию
    waiting_msg = await message.answer("🎨 Генерирую артефакт, подождите 5–10 секунд...")
    rarity = choose_rarity()
    name = generate_artifact_name(rarity)
    prompt = f"{rarity['prompt_prefix']}, {name}, fantasy artifact, digital art, detailed, beautiful"
    image_url = await generate_image(prompt)
    if image_url:
        caption = f"{rarity['emoji']} *{name}*\nРедкость: {rarity['name']}"
        await message.answer_photo(photo=image_url, caption=caption, parse_mode="Markdown")
        await waiting_msg.delete()
    else:
        await waiting_msg.edit_text("❌ Не удалось создать артефакт. Попробуйте позже.")

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Напишите /start")

# --- Flask-сервер для Render (чтобы открыть порт) ---
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return "Bot is running", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

# --- Запуск бота в отдельном потоке ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и слушает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запускаем Flask в фоновом потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    # Запускаем асинхронного бота
    asyncio.run(main())
