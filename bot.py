import os
import logging
import asyncio
import random
import aiohttp
from io import BytesIO
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ========== ТОКЕНЫ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")          # опционально, если не задан – HF не будет использован

if not TELEGRAM_TOKEN:
    raise RuntimeError("Не задана переменная окружения TELEGRAM_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----- Редкости и генерация имен -----
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

# ----- Генерация изображения с резервными источниками -----
async def generate_image_pollinations(prompt):
    """Пытается получить картинку через Pollinations (без ключа)"""
    encoded_prompt = aiohttp.helpers.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&nologo=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    if data and len(data) > 1000:
                        return data
                    else:
                        logger.warning(f"Pollinations вернул маленький ответ ({len(data)} байт)")
                else:
                    logger.error(f"Pollinations error {resp.status}: {await resp.text()}")
    except Exception as e:
        logger.warning(f"Pollinations исключение: {e}")
    return None

async def generate_image_huggingface(prompt):
    """Пытается получить картинку через Hugging Face (требуется HF_TOKEN)"""
    if not HF_TOKEN:
        logger.warning("HF_TOKEN не задан, пропускаем Hugging Face")
        return None
    api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {"negative_prompt": "blurry, ugly, low quality"}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    error_text = await resp.text()
                    logger.error(f"Hugging Face error {resp.status}: {error_text}")
    except Exception as e:
        logger.warning(f"Hugging Face исключение: {e}")
    return None

async def generate_image_with_fallback(prompt):
    """
    Последовательно пробует провайдеров:
    1. Pollinations (бесплатно, без ключа)
    2. Hugging Face (если есть HF_TOKEN)
    При первом успехе возвращает байты изображения.
    """
    # 1. Pollinations
    logger.info("Пробуем Pollinations...")
    image = await generate_image_pollinations(prompt)
    if image:
        logger.info("Pollinations успешно сгенерировал изображение")
        return image
    
    # 2. Hugging Face
    if HF_TOKEN:
        logger.info("Пробуем Hugging Face...")
        image = await generate_image_huggingface(prompt)
        if image:
            logger.info("Hugging Face успешно сгенерировал изображение")
            return image
    
    logger.error("Все провайдеры не смогли сгенерировать изображение")
    return None

# ----- Команды бота -----
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 *Артефакториум*\n\n"
        "Я создаю уникальные предметы с помощью нейросетей.\n"
        "/buy — получить случайный артефакт с картинкой\n"
        "/help — справка",
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("/start — приветствие\n/buy — артефакт\n/help — эта справка")

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    waiting_msg = await message.answer("🎨 Генерирую артефакт, подождите 10–20 секунд...")
    rarity = choose_rarity()
    name = generate_artifact_name(rarity)
    prompt = f"{rarity['prompt_prefix']}, {name}, fantasy artifact, digital art, detailed, beautiful"
    
    image_data = await generate_image_with_fallback(prompt)
    
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

# ----- Запуск -----
async def main():
    # Сбрасываем вебхук на случай старых соединений
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен, генерация с резервными провайдерами")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
