import logging
import asyncio
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ========== ВСТАВЬТЕ ВАШ ТОКЕН СЮДА ==========
TOKEN = "8876252162:AAGiBvNqniHXK4emXXeierk1B-n4w1ihBVI"   # замените на настоящий токен
# ============================================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# База артефактов (пока простые, без картинок)
ARTIFACTS = [
    {"name": "Кристалл забытых снов", "rarity": "обычный", "desc": "Мерцает фиолетовым. Помогает вспомнить, зачем пришёл на кухню."},
    {"name": "Амулет ленивого солнца", "rarity": "редкий", "desc": "Не греет, зато отгоняет будильники на 2 часа."},
    {"name": "Меч последнего аргумента", "rarity": "легендарный", "desc": "Достаточно показать — собеседник соглашается."},
    {"name": "Шепчущая маска", "rarity": "обычный", "desc": "Надетая задом наперёд, заставляет кота говорить 'мяу' басом."},
    {"name": "Треснувший осколок радуги", "rarity": "редкий", "desc": "Показывает мир в цвете 'grue' (зелёно-синий)."},
    {"name": "Свиток самоисполняющейся шутки", "rarity": "легендарный", "desc": "Рассказывает анекдот, после которого все забывают, о чём спорили."},
]

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🔮 Добро пожаловать в Артефакториум!\n\n"
        "Я создаю магические предметы вслепую.\n"
        "Попробуй команду /buy — получишь случайный артефакт (пока бесплатно).\n"
        "Скоро появятся редкость, аукцион и платные легендарки за Telegram Stars."
    )

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    artifact = random.choice(ARTIFACTS)
    emoji = "⬜" if artifact["rarity"] == "обычный" else "🟦" if artifact["rarity"] == "редкий" else "🌟"
    text = (
        f"{emoji} *Твой артефакт:*\n\n"
        f"📦 *Название:* {artifact['name']}\n"
        f"🔷 *Редкость:* {artifact['rarity']}\n"
        f"📖 *Описание:* {artifact['desc']}\n\n"
        "Скоро здесь появится изображение и возможность продать на аукционе!"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Команды:\n/start — приветствие\n/buy — получить случайный артефакт\n/help — эта справка")

@dp.message()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Напиши /help")

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Бот запущен и слушает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())