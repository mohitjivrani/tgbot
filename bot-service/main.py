import asyncio
import logging
import os
from datetime import datetime

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
        "/start – Show this help message\n"
        "/track <url> [pincode] – Start tracking a product\n"
        "/list – List your tracked products\n"
        "/status <id> – Show detailed product status\n"
        "/remove <id> – Stop tracking a product"
    )


@dp.message(Command("track"))
async def cmd_track(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /track <product_url> [pincode]")
        return

    url = parts[1].strip()
    pincode = parts[2].strip() if len(parts) > 2 else None
    if pincode:
        pincode_digits = "".join(ch for ch in pincode if ch.isdigit())
        if len(pincode_digits) != 6:
            await message.answer("❌ Pincode must be a 6-digit number.")
            return
        pincode = pincode_digits

    telegram_user_id = str(message.from_user.id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{API_GATEWAY_URL}/track",
                json={"url": url, "telegram_user_id": telegram_user_id, "pincode": pincode},
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            pincode_info = f"\nPincode: {data.get('preferred_pincode')}" if data.get("preferred_pincode") else ""
            await message.answer(
                f"✅ Now tracking product (id={data['id']}):\n{url}\nPlatform: {data['platform']}{pincode_info}"
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
                price_str = f"₹{price}" if price is not None else "N/A"
                availability = p.get("last_availability")
                if availability is True:
                    avail = "✅"
                elif availability is False:
                    avail = "❌"
                else:
                    avail = "❓"
                lines.append(
                    f"[{p['id']}] {name}\n"
                    f"  Platform: {p['platform']}\n"
                    f"  Price: {price_str}  {avail}\n"
                    f"  Pincode: {p.get('preferred_pincode') or 'N/A'}\n"
                    f"  Deliverability: {'✅' if p.get('last_deliverable') is True else ('❌' if p.get('last_deliverable') is False else '❓')}\n"
                    f"  Last In-Stock: {_format_last_instock(p)}\n"
                    f"  URL: {p['product_url']}\n"
                )
            await message.answer("\n".join(lines))
        else:
            await message.answer("❌ Failed to fetch products.")
    except httpx.RequestError as exc:
        logger.error("HTTP error listing products: %s", exc)
        await message.answer("❌ Could not reach the API. Please try again later.")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Usage: /status <product_id>")
        return

    product_id = int(parts[1].strip())
    telegram_user_id = str(message.from_user.id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{API_GATEWAY_URL}/products",
                params={"user_id": telegram_user_id},
            )

        if resp.status_code != 200:
            await message.answer("❌ Failed to fetch product status.")
            return

        products = resp.json()
        product = next((p for p in products if p.get("id") == product_id), None)
        if product is None:
            await message.answer(f"❌ Product {product_id} not found.")
            return

        availability = product.get("last_availability")
        availability_text = "✅ In Stock" if availability is True else ("❌ Out of Stock" if availability is False else "❓ Unknown")
        deliverable = product.get("last_deliverable")
        deliverability_text = "✅ Deliverable" if deliverable is True else ("❌ Not deliverable" if deliverable is False else "❓ Unknown")
        price = product.get("last_price")
        price_text = f"₹{price}" if price is not None else "N/A"

        await message.answer(
            f"📌 Status for product [{product['id']}]:\n"
            f"Name: {product.get('product_name') or 'N/A'}\n"
            f"Platform: {product.get('platform')}\n"
            f"Current Price: {price_text}\n"
            f"Availability: {availability_text}\n"
            f"Pincode: {product.get('preferred_pincode') or 'N/A'}\n"
            f"Deliverability: {deliverability_text}\n"
            f"Last In-Stock: {_format_last_instock(product)}\n"
            f"URL: {product.get('product_url')}"
        )
    except httpx.RequestError as exc:
        logger.error("HTTP error fetching status: %s", exc)
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


def _format_last_instock(product: dict) -> str:
    last_available_at = product.get("last_available_at")
    last_available_price = product.get("last_available_price")
    if not last_available_at and last_available_price is None:
        return "N/A"

    time_text = "N/A"
    if last_available_at:
        try:
            parsed = datetime.fromisoformat(last_available_at.replace("Z", "+00:00"))
            time_text = parsed.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            time_text = str(last_available_at)

    price_text = f"₹{last_available_price}" if last_available_price is not None else "N/A"
    return f"{time_text} at {price_text}"


if __name__ == "__main__":
    asyncio.run(main())
