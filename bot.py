import os
import asyncio
import random
import logging
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from huggingface_hub import InferenceClient

# Загружаем переменные из .env
load_dotenv()

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Токены ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

# --- Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Редкости и генерация имени артефакта ---
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

# --- Провайдер 1: Replicate (основной) ---
async def generate_with_replicate(prompt: str) -> str | None:
    if not REPLICATE_API_KEY:
        logger.warning("Replicate API ключ отсутствует")
        return None
    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Bearer {REPLICATE_API_KEY}",
        "Content-Type": "application/json"
    }
    # Последняя стабильная версия SDXL
    payload = {
        "version": "39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
        "input": {
            "prompt": prompt,
            "negative_prompt": "blurry, ugly, low quality",
            "width": 768,
            "height": 768,
            "num_outputs": 1,
            "scheduler": "DPMSolverMultistep",
            "num_inference_steps": 25,
            "guidance_scale": 7.5
        }
    }
    async with aiohttp.ClientSession() as session:
        try:
            # Создаём задание
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 201:
                    logger.error(f"Replicate create error {resp.status}")
                    return None
                data = await resp.json()
                pred_id = data["id"]
            # Ждём результат (до 30 секунд)
            for _ in range(30):
                await asyncio.sleep(1)
                async with session.get(f"{url}/{pred_id}", headers=headers) as status_resp:
                    if status_resp.status != 200:
                        continue
                    status_data = await status_resp.json()
                    if status_data["status"] == "succeeded":
                        return status_data["output"][0]
                    elif status_data["status"] == "failed":
                        logger.error(f"Replicate failed: {status_data.get('error')}")
                        return None
            logger.error("Replicate timeout")
            return None
        except Exception as e:
            logger.error(f"Replicate exception: {e}")
            return None

# --- Провайдер 2: Pollinations (бесплатный, без ключа) ---
async def generate_with_pollinations(prompt: str) -> str | None:
    encoded_prompt = aiohttp.helpers.quote(prompt)
    # Используем модель flux для качества
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=768&height=768&model=flux"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.head(image_url) as resp:
                if resp.status == 200:
                    return image_url
                else:
                    logger.error(f"Pollinations head error {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Pollinations exception: {e}")
            return None

# --- Провайдер 3: Hugging Face (резервный) ---
async def generate_with_huggingface(prompt: str) -> str | None:
    if not HF_TOKEN:
        logger.warning("HF_TOKEN отсутствует")
        return None
    try:
        client = InferenceClient(token=HF_TOKEN)
        image = await asyncio.to_thread(
            client.text_to_image,
            prompt,
            model="black-forest-labs/FLUX.1-dev"
        )
        if not image:
            return None
        temp_filename = f"temp_{random.randint(1, 100000)}.png"
        image.save(temp_filename)
        return temp_filename
    except Exception as e:
        logger.error(f"HuggingFace exception: {e}")
        return None

# --- Команда /buy ---
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    waiting_msg = await message.answer("🎨 Генерирую артефакт (10–20 секунд)...")
    rarity = choose_rarity()
    name = generate_artifact_name(rarity)
    prompt = f"{rarity['prompt_prefix']}, {name}, fantasy artifact, digital art, detailed, beautiful, 8k"

    image_result = None
    used_provider = None

    # 1. Replicate
    image_result = await generate_with_replicate(prompt)
    if image_result:
        used_provider = "Replicate"

    # 2. Pollinations
    if not image_result:
        logger.info("Replicate не сработал, пробуем Pollinations...")
        image_result = await generate_with_pollinations(prompt)
        if image_result:
            used_provider = "Pollinations"

    # 3. Hugging Face
    if not image_result:
        logger.info("Pollinations не сработал, пробуем Hugging Face...")
        image_result = await generate_with_huggingface(prompt)
        if image_result:
            used_provider = "Hugging Face"

    # Ответ пользователю
    if image_result:
        caption = f"{rarity['emoji']} *{name}*\nРедкость: {rarity['name']}\n\n✨ *Сгенерировано через:* {used_provider}"
        if image_result.startswith("http"):
            await message.answer_photo(photo=image_result, caption=caption, parse_mode="Markdown")
        else:
            # временный файл от Hugging Face
            with open(image_result, "rb") as photo:
                await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
            os.remove(image_result)
        await waiting_msg.delete()
    else:
        await waiting_msg.edit_text(
            "❌ *Не удалось создать артефакт.*\n\n"
            "Все сервисы генерации временно недоступны.\n"
            "Попробуйте позже.",
            parse_mode="Markdown"
        )
        logger.error("Все провайдеры не сработали")

# --- Команды /start и /help ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 *Артефакториум*\n\n"
        "Я генерирую уникальные предметы с помощью нейросетей!\n"
        "Используй `/buy` — получишь артефакт с картинкой.\n\n"
        "✨ *Поддерживаемые сервисы:* Replicate, Pollinations, Hugging Face.\n"
        "Если один занят, автоматически включается другой.",
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "🕹️ *Доступные команды:*\n"
        "/start — приветствие\n"
        "/buy — получить артефакт\n"
        "/help — эта справка\n\n"
        "Генерация может занимать до 20 секунд."
    )

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Напишите /start")

# --- Запуск бота ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и слушает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
