import uvicorn
import fastapi
import telebot
from telebot.async_telebot import AsyncTeleBot

import bconf
from bconf import logger


# Init async bot
bot = AsyncTeleBot(bconf.BOT_TOKEN)


async def init_bot():
    try:
        await bot.delete_my_commands()
        await bot.set_my_commands(commands=[
            telebot.types.BotCommand("start", "Start"),
            # telebot.types.BotCommand("gemini20", "Using gemini-2.0-flash"),
            # telebot.types.BotCommand("gemini25", "Using gemini-2.5-flash"),
            telebot.types.BotCommand("clear", "Clear all history"),
            telebot.types.BotCommand("switch", "Switch model"),
            telebot.types.BotCommand("text2image", "Generate image by Gemini 2.0 flash"),
        ], )

        if bconf.WEB_HOOK:
            await bot.remove_webhook()
            await bot.set_webhook(url=bconf.WEBHOOK_URL)
            # start aiohttp server
            logger.info("Starting webhook telegram bot.")
            app = fastapi.FastAPI(docs_url=None, )

            @app.post(f'/{bconf.BOT_TOKEN}/')
            async def register_routes(update: dict):
                if update:
                    update = telebot.types.Update.de_json(update)
                    await bot.process_new_updates([update])
                else:
                    return

            # 本身开了协程, 不能直接在异步上下文中直接运行
            # uvicorn.run(app, host=bconf.WEBHOOK_LISTEN, port=bconf.WEBHOOK_PORT)
            config = uvicorn.Config(app, host=bconf.WEBHOOK_LISTEN, port=bconf.WEBHOOK_PORT)
            server = uvicorn.Server(config)
            await server.serve()
        else:
            # run telegram bot in polling mode
            await bot.remove_webhook()
            logger.info("Starting polling telegram bot.")
            await bot.polling(non_stop=True)
    finally:
        #  close session
        await bot.close_session()
