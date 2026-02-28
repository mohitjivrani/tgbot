import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import httpx
from dotenv import load_dotenv

from notify_server import start_notify_server

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway:7500")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Welcome to the Price & Offer Tracker Bot!\n\n"
        "Commands:\n"
        "/track <url> – Start tracking a product\n"
        "/list – List your tracked products\n"
        "/remove <id> – Stop tracking a product"
    )


@dp.message(Command("track"))
async def cmd_track(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /track <product_url>")
        return

    url = parts[1].strip()
    telegram_user_id = str(message.from_user.id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{API_GATEWAY_URL}/track",
                json={"url": url, "telegram_user_id": telegram_user_id},
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            await message.answer(
                f"✅ Now tracking product (id={data['id']}):\n{url}\nPlatform: {data['platform']}"
            )
        elif resp.status_code == 400:
            detail = resp.json().get("detail", "Invalid URL")
            await message.answer(f"❌ {detail}")
        else:
            logger.error("Track error: %s %s", resp.status_code, resp.text)
            await message.answer("❌ Failed to track product. Please try again later.")
    except httpx.RequestError as exc:
        logger.error("HTTP error tracking product: %s", exc)
        await message.answer("❌ Could not reach the API. Please try again later.")


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    telegram_user_id = str(message.from_user.id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{API_GATEWAY_URL}/products",
                params={"user_id": telegram_user_id},
            )
        if resp.status_code == 200:
            products = resp.json()
            if not products:
                await message.answer("📭 You have no tracked products.")
                return
            lines = ["📋 Your tracked products:\n"]
            for p in products:
                name = p.get("product_name") or "N/A"
                price = p.get("last_price")
                price_str = f"₹{price}" if price else "N/A"
                avail = "✅" if p.get("last_availability") else "❓"
                lines.append(
                    f"[{p['id']}] {name}\n"
                    f"  Platform: {p['platform']}\n"
                    f"  Price: {price_str}  {avail}\n"
                    f"  URL: {p['product_url']}\n"
                )
            await message.answer("\n".join(lines))
        else:
            await message.answer("❌ Failed to fetch products.")
    except httpx.RequestError as exc:
        logger.error("HTTP error listing products: %s", exc)
        await message.answer("❌ Could not reach the API. Please try again later.")


@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Usage: /remove <product_id>")
        return

    product_id = parts[1].strip()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(f"{API_GATEWAY_URL}/products/{product_id}")
        if resp.status_code == 204:
            await message.answer(f"🗑️ Product {product_id} removed from tracking.")
        elif resp.status_code == 404:
            await message.answer(f"❌ Product {product_id} not found.")
        else:
            await message.answer("❌ Failed to remove product.")
    except httpx.RequestError as exc:
        logger.error("HTTP error removing product: %s", exc)
        await message.answer("❌ Could not reach the API. Please try again later.")


async def main():
    logger.info("Starting bot-service...")
    notify_task = asyncio.create_task(start_notify_server(bot))
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    await asyncio.gather(notify_task, polling_task)


if __name__ == "__main__":
    asyncio.run(main())
