import asyncio
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


async def handle_notify(request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        message_text = data.get("message", "")
        if not chat_id or not message_text:
            return web.json_response({"error": "chat_id and message are required"}, status=400)

        bot = request.app["bot"]
        await bot.send_message(chat_id=chat_id, text=message_text)
        logger.info("Notification sent to chat_id=%s", chat_id)
        return web.json_response({"status": "sent"})
    except Exception as exc:
        logger.error("Error sending notification: %s", exc)
        return web.json_response({"error": str(exc)}, status=500)


async def handle_health(request):
    return web.json_response({"status": "ok"})


async def start_notify_server(bot):
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/notify", handle_notify)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Notify server listening on port 8080")

    # Keep running indefinitely
    while True:
        await asyncio.sleep(3600)
