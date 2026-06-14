import logging
import asyncio
import random
import threading
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from flask import Flask

# ========== ТОКЕНЫ ==========
TELEGRAM_TOKEN = "8876252162:AAGiBvNqniHXK4emXXeierk1B-n4w1ihBVI"  # Токен от BotFather
HF_TOKEN = "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"                    # Новый токен от Hugging Face
# ============================

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RARITIES = [
    {"name": "обычный", "chance": 70, "emoji": "⬜", "prompt_prefix": "simple, common"},
    {"name": "редкий", "chance": 20, "emoji": "🟦", "prompt_prefix": "intricate, glowing"},
    {"name": "легендарный", "chance": 8, "emoji": "🌟", "prompt_prefix": "epic, legendary, masterpiece"},
    {"name": "эпический", "chance": 2, "emoji": "💎", "prompt_prefix": "godly, transcendent"},
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

async def generate_image_hf(prompt, retries=3):
    """Генерация изображения через бесплатный Hugging Face API с повторными попытками."""
    api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {"negative_prompt": "blurry, ugly, low quality"}
    }

    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        return image_data
                    else:
                        error_text = await resp.text()
                        logging.error(f"Hugging Face error {resp.status}: {error_text}")
                        return None

        except aiohttp.client_exceptions.ClientConnectorDNSError as e:
            logging.warning(f"DNS ошибка при попытке {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Ожидание 1, 2, 4 секунды
            else:
                logging.error(f"Не удалось подключиться после {retries} попыток.")
                return None

        except Exception as e:
            logging.exception(f"Неизвестная ошибка при генерации: {e}")
            return None
    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 *Артефакториум (на Hugging Face)*\n\n"
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
    waiting_msg = await message.answer("🎨 Генерирую артефакт, подождите 5–10 секунд...")
    rarity = choose_rarity()
    name = generate_artifact_name(rarity)
    prompt = f"{rarity['prompt_prefix']}, {name}, fantasy artifact, digital art, detailed, beautiful"
    image_data = await generate_image_hf(prompt)
    if image_data:
        from io import BytesIO
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

# Flask для Render
flask_app = Flask(__name__)
@flask_app.route('/')
def health():
    return "Bot is running", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=10000)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен (Hugging Face)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
