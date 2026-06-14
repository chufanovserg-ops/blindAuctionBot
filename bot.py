import logging
import asyncio
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ========== ТОКЕНЫ ==========
TELEGRAM_TOKEN = "8876252162:AAGiBvNqniHXK4emXXeierk1B-n4w1ihBVI"    # вставьте сюда
REPLICATE_API_TOKEN = "r8_VkjWmJGLRvdmzbKFeEvKWt7XNg2I7IZ4Ys6Mh"               # вставьте сюда
# ===========================

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Словарь редкостей с вероятностями
RARITIES = [
    {"name": "обычный", "chance": 70, "emoji": "⬜", "prompt_prefix": "simple, common, everyday object, low detail"},
    {"name": "редкий", "chance": 20, "emoji": "🟦", "prompt_prefix": "intricate, mysterious, glowing, fantasy art"},
    {"name": "легендарный", "chance": 8, "emoji": "🌟", "prompt_prefix": "epic, legendary, divine, masterpiece, cinematic lighting"},
    {"name": "эпический", "chance": 2, "emoji": "💎", "prompt_prefix": "godly, transcendent, otherworldly, cosmic, sacred geometry"},
]

# База для генерации описаний (можно расширить)
ARTIFACT_THEMES = [
    "кристалл", "амулет", "меч", "кольцо", "свиток", "маска", "ключ", "зеркало", "чаша", "статуэтка"
]

def choose_rarity():
    r = random.randint(1, 100)
    cumulative = 0
    for rarity in RARITIES:
        cumulative += rarity["chance"]
        if r <= cumulative:
            return rarity
    return RARITIES[0]

def generate_description(rarity, theme):
    # Генерируем имя и описание (пока шаблонно, потом можно через DeepSeek)
    name = f"{rarity['name'].capitalize()} {random.choice(ARTIFACT_THEMES)}"
    desc = f"Таинственный предмет, найденный в древних руинах. {rarity['emoji']}"
    if rarity["name"] == "легендарный":
        name = f"Легендарный {name}"
        desc = "В нём чувствуется сила древних богов. Говорят, он исполняет желания."
    elif rarity["name"] == "эпический":
        name = f"Эпический {name}"
        desc = "Этот артефакт меняет реальность вокруг себя. Берегитесь!"
    return name, desc

async def generate_image(prompt):
    """Отправляет запрос к Replicate API и возвращает URL картинки"""
    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Token {REPLICATE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "version": "db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",  # SDXL
        "input": {
            "prompt": prompt,
            "negative_prompt": "low quality, blurry, ugly, deformed",
            "width": 768,
            "height": 768,
            "num_outputs": 1,
            "scheduler": "DPMSolverMultistep",
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json()
            prediction_id = data["id"]
        # Ждём завершения
        while True:
            await asyncio.sleep(1)
            async with session.get(f"{url}/{prediction_id}", headers=headers) as status_resp:
                status_data = await status_resp.json()
                if status_data["status"] == "succeeded":
                    return status_data["output"][0]
                elif status_data["status"] == "failed":
                    return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 *Артефакториум* — бот, который создаёт уникальные предметы с картинками!\n\n"
        "Команды:\n/buy — получить случайный артефакт (бесплатно)\n/help — справка",
        parse_mode="Markdown"
    )

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    # Отправляем "печатает", чтобы пользователь ждал
    await bot.send_chat_action(message.chat.id, "upload_photo")
    
    rarity = choose_rarity()
    theme = random.choice(ARTIFACT_THEMES)
    name, desc = generate_description(rarity, theme)
    
    # Создаём промпт для картинки
    prompt = f"{rarity['prompt_prefix']}, {name}, {desc}, fantasy, digital art, high quality"
    
    # Генерируем картинку
    image_url = await generate_image(prompt)
    
    if image_url:
        caption = f"{rarity['emoji']} *{name}*\n\n📖 {desc}\n\nРедкость: {rarity['name']}"
        await message.answer_photo(photo=image_url, caption=caption, parse_mode="Markdown")
    else:
        await message.answer("❌ Не удалось создать изображение. Попробуй ещё раз.")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("/start — приветствие\n/buy — получить артефакт с картинкой")

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Используй /buy для получения артефакта")

async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен, генерация картинок через Replicate")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())