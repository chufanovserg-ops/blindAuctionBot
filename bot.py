import os
import asyncio
import random
import logging
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from huggingface_hub import InferenceClient

# Загружаем переменные из .env
load_dotenv()

# Настройка детального логирования в файл и консоль
LOG_FILE = f"bot_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"=== БОТ ЗАПУЩЕН {datetime.now()} ===")
logger.info(f"Логи сохраняются в файл: {LOG_FILE}")

# --- Токены ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REPLICATE_API_KEY = os.getenv("REPLICATE_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")
logger.info(f"Токен Telegram найден: {BOT_TOKEN[:10]}...")
if REPLICATE_API_KEY:
    logger.info(f"Replicate API ключ найден: {REPLICATE_API_KEY[:10]}...")
else:
    logger.warning("Replicate API ключ отсутствует!")
if HF_TOKEN:
    logger.info(f"HuggingFace API ключ найден: {HF_TOKEN[:10]}...")
else:
    logger.warning("HuggingFace API ключ отсутствует!")

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

# --- Функция с повторными попытками для любых запросов ---
async def request_with_retry(func, *args, max_retries=3, **kwargs):
    """Выполняет функцию с повторными попытками при ошибках"""
    for attempt in range(max_retries):
        try:
            result = await func(*args, **kwargs)
            if result:
                logger.info(f"Функция {func.__name__} успешно выполнилась с попытки {attempt + 1}")
                return result
            else:
                logger.warning(f"Функция {func.__name__} вернула None на попытке {attempt + 1}")
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__} на попытке {attempt + 1}: {e}")
        
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # экспоненциальная задержка: 1, 2, 4 секунды
            logger.info(f"Повторная попытка через {wait_time} секунд...")
            await asyncio.sleep(wait_time)
    logger.error(f"Функция {func.__name__} не сработала после {max_retries} попыток")
    return None

# --- Провайдер 1: Replicate (основной) ---
async def _generate_with_replicate(prompt: str) -> str | None:
    if not REPLICATE_API_KEY:
        logger.warning("Replicate API ключ отсутствует")
        return None
    
    logger.info(f"[Replicate] Начинаем генерацию с промптом: {prompt[:100]}...")
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
            logger.info("[Replicate] Отправляем запрос на создание предсказания...")
            async with session.post(url, json=payload, headers=headers) as resp:
                response_text = await resp.text()
                logger.info(f"[Replicate] Статус создания: {resp.status}")
                if resp.status != 201:
                    logger.error(f"[Replicate] Ошибка создания: {resp.status}, {response_text}")
                    return None
                data = await resp.json()
                pred_id = data["id"]
                logger.info(f"[Replicate] Предсказание создано: {pred_id}")
            
            # Ждём результат (до 30 секунд)
            for i in range(30):
                await asyncio.sleep(1)
                async with session.get(f"{url}/{pred_id}", headers=headers) as status_resp:
                    if status_resp.status != 200:
                        logger.warning(f"[Replicate] Статус {status_resp.status} при проверке, повторяем...")
                        continue
                    status_data = await status_resp.json()
                    status = status_data.get("status")
                    logger.debug(f"[Replicate] Статус выполнения: {status} (прошло {i+1} сек)")
                    
                    if status == "succeeded":
                        image_url = status_data["output"][0] if status_data.get("output") else None
                        if image_url:
                            logger.info(f"[Replicate] ✅ Успешно! Получен URL: {image_url[:100]}...")
                            return image_url
                        else:
                            logger.error(f"[Replicate] Нет output в ответе: {status_data}")
                            return None
                    elif status == "failed":
                        error_msg = status_data.get("error", "Неизвестная ошибка")
                        logger.error(f"[Replicate] ❌ Генерация не удалась: {error_msg}")
                        return None
            
            logger.error("[Replicate] Таймаут 30 секунд")
            return None
        except Exception as e:
            logger.exception(f"[Replicate] Исключение: {e}")
            return None

# Провайдер 1 с обёрткой повторных попыток
async def generate_with_replicate(prompt: str) -> str | None:
    return await request_with_retry(_generate_with_replicate, prompt, max_retries=2)

# --- Провайдер 2: Pollinations (бесплатный, без ключа) ---
async def _generate_with_pollinations(prompt: str) -> str | None:
    encoded_prompt = aiohttp.helpers.quote(prompt)
    # Пробуем несколько моделей по очереди
    models = ["flux", "turbo", "gptimage"]
    base_url = "https://image.pollinations.ai/prompt/{prompt}?width=768&height=768&model={model}&nologo=true"
    
    for model in models:
        image_url = base_url.format(prompt=encoded_prompt, model=model)
        logger.info(f"[Pollinations] Пробуем модель {model}: {image_url[:100]}...")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(image_url) as resp:
                    logger.info(f"[Pollinations] Статус {resp.status} для модели {model}")
                    if resp.status == 200:
                        content_type = resp.headers.get('Content-Type', '')
                        if 'image' in content_type:
                            logger.info(f"[Pollinations] ✅ Успешно! Получено изображение с моделью {model}")
                            return image_url
                        else:
                            logger.warning(f"[Pollinations] Ответ не является изображением: {content_type}")
                    elif resp.status == 402:
                        error_text = await resp.text()
                        logger.warning(f"[Pollinations] Ошибка 402 (лимит/очередь): {error_text[:200]}")
                    else:
                        logger.warning(f"[Pollinations] Ошибка {resp.status} для модели {model}")
            except Exception as e:
                logger.error(f"[Pollinations] Исключение для модели {model}: {e}")
    
    logger.error("[Pollinations] Все модели не сработали")
    return None

# Провайдер 2 с обёрткой повторных попыток
async def generate_with_pollinations(prompt: str) -> str | None:
    return await request_with_retry(_generate_with_pollinations, prompt, max_retries=2)

# --- Провайдер 3: Hugging Face (резервный) ---
async def _generate_with_huggingface(prompt: str) -> str | None:
    if not HF_TOKEN:
        logger.warning("HF_TOKEN отсутствует")
        return None
    
    logger.info(f"[HuggingFace] Начинаем генерацию с промптом: {prompt[:100]}...")
    
    # Список моделей для перебора
    models = [
        "black-forest-labs/FLUX.1-dev",
        "stabilityai/stable-diffusion-xl-base-1.0",
        "prompthero/openjourney-v4"
    ]
    
    for model in models:
        logger.info(f"[HuggingFace] Пробуем модель {model}")
        try:
            client = InferenceClient(token=HF_TOKEN)
            image = await asyncio.to_thread(
                client.text_to_image,
                prompt,
                model=model
            )
            if image:
                temp_filename = f"temp_{random.randint(1, 100000)}.png"
                image.save(temp_filename)
                logger.info(f"[HuggingFace] ✅ Успешно! Изображение сохранено: {temp_filename}")
                return temp_filename
            else:
                logger.warning(f"[HuggingFace] Модель {model} вернула None")
        except Exception as e:
            logger.error(f"[HuggingFace] Ошибка с моделью {model}: {e}")
    
    logger.error("[HuggingFace] Все модели не сработали")
    return None

# Провайдер 3 с обёрткой повторных попыток
async def generate_with_huggingface(prompt: str) -> str | None:
    return await request_with_retry(_generate_with_huggingface, prompt, max_retries=2)

# --- ОСНОВНАЯ ФУНКЦИЯ С FALLBACK ---
async def generate_artifact_image(rarity, name):
    """Пытается сгенерировать изображение последовательно через все провайдеры"""
    prompt = f"{rarity['prompt_prefix']}, {name}, fantasy artifact, digital art, detailed, beautiful, 8k"
    logger.info(f"=== НАЧАЛО ГЕНЕРАЦИИ ДЛЯ АРТЕФАКТА: {name} ===")
    logger.info(f"Промпт: {prompt}")
    
    # 1. Replicate
    logger.info("1️⃣ Пытаемся через Replicate...")
    image_result = await generate_with_replicate(prompt)
    if image_result:
        return image_result, "Replicate"
    
    # 2. Pollinations
    logger.info("2️⃣ Replicate не сработал, пытаемся через Pollinations...")
    image_result = await generate_with_pollinations(prompt)
    if image_result:
        return image_result, "Pollinations"
    
    # 3. Hugging Face
    logger.info("3️⃣ Pollinations не сработал, пытаемся через Hugging Face...")
    image_result = await generate_with_huggingface(prompt)
    if image_result:
        return image_result, "Hugging Face"
    
    logger.error("❌ ВСЕ ПРОВАЙДЕРЫ НЕ СМОГЛИ СГЕНЕРИРОВАТЬ ИЗОБРАЖЕНИЕ")
    return None, None

# --- Команда /buy ---
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    logger.info(f"=== ПОЛУЧЕНА КОМАНДА /buy ОТ {message.from_user.id} ===")
    waiting_msg = await message.answer("🎨 Генерирую артефакт (это может занять 20-30 секунд)...")
    
    rarity = choose_rarity()
    name = generate_artifact_name(rarity)
    logger.info(f"Выбрана редкость: {rarity['name']}, имя: {name}")
    
    image_result, used_provider = await generate_artifact_image(rarity, name)
    
    if image_result:
        caption = f"{rarity['emoji']} *{name}*\nРедкость: {rarity['name']}\n\n✨ *Сгенерировано через:* {used_provider}"
        
        if image_result.startswith("http"):
            logger.info(f"Отправляем фото по URL: {image_result}")
            await message.answer_photo(photo=image_result, caption=caption, parse_mode="Markdown")
        else:
            logger.info(f"Отправляем фото из файла: {image_result}")
            with open(image_result, "rb") as photo:
                await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
            os.remove(image_result)
            logger.info(f"Временный файл {image_result} удалён")
        
        await waiting_msg.delete()
        logger.info(f"✅ Успешно отправлен артефакт {name} пользователю {message.from_user.id}")
    else:
        error_text = (
            "❌ *Не удалось создать артефакт.*\n\n"
            "Все сервисы генерации временно недоступны.\n"
            "Попробуйте позже.\n\n"
            "Возможные причины:\n"
            "• Закончились бесплатные лимиты в Replicate\n"
            "• Очередь запросов в Pollinations переполнена\n"
            "• Технические проблемы на стороне сервисов"
        )
        logger.error(f"❌ Не удалось отправить артефакт пользователю {message.from_user.id}")
        await waiting_msg.edit_text(error_text, parse_mode="Markdown")

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
        "Генерация может занимать до 20 секунд.\n\n"
        "📋 *Логирование:* Все ошибки записываются в файл bot_debug_*.log"
    )

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Напишите /start")

# --- Запуск бота ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("=== БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ ===")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
