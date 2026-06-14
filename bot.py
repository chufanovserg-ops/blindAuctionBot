import asyncio
import logging
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import os

# --- Настройки ---
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Логика для /buy (упрощённая, для примера) ---
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    await message.answer("🎲 Генерируем артефакт...")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Бот запущен и работает на Railway!")

# --- Запуск ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
