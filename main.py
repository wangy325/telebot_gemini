import asyncio
import uvicorn
import telebot

import bconf
from bot import bot, app
# import to register handlers
import handlers

logger = bconf.logger
logger.name = __name__


async def init_bot():
    try:
        await bot.delete_my_commands(scope=None, language_code=None)
        await bot.set_my_commands(commands=[
            telebot.types.BotCommand("start", "Start"),
            telebot.types.BotCommand("gemini", "Using gemini-2.0-flash-exp"),
            telebot.types.BotCommand("gemini_pro", "Using gemini-2.5-pro-exp"),
            telebot.types.BotCommand("clear", "Clear all history"),
            telebot.types.BotCommand("switch", "Switch to default model(2.0-flash-exp)"),
        ], )

        if bconf.WEB_HOOK:
            await bot.remove_webhook()
            await bot.set_webhook(url=bconf.WEBHOOK_URL)
            # start aiohttp server
            logger.info("Starting webhook telegram bot.")
            # asyncio.run() cannot be called from a running event loop
            # 本身开了协程, 不能直接在异步上下文中直接运行
            # uvicorn.run(app, host=bconf.WEBHOOK_LISTEN, port=bconf.WEBHOOK_PORT)
            config = uvicorn.Config(app, host=bconf.WEBHOOK_LISTEN, port=bconf.WEBHOOK_PORT)
            server = uvicorn.Server(config)
            await server.serve()
        else:
            # run telegram bot in polling mode
            await bot.remove_webhook()
            logger.info("Starting polling telegram bot.")
            await bot.polling(none_stop=True)
    finally:
        #  close session
        await bot.close_session()


if __name__ == '__main__':
    bconf.set_local_proxies()
    asyncio.run(init_bot())

# test cmd:
# python .\main.py --key AIzaSyDIn00nCYnxnJVip2J39BGyrcvKRVBwpcE
# --token 7684873575:AAEO5_2kWfOvXFeaTU2S1irqTKRtKMU9A4E --botname '@wyDevBot'