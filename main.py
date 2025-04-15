import asyncio
import bconf
import bot
# import to register handlers
import handlers


if __name__ == '__main__':
    bconf.set_local_proxies()
    asyncio.run(bot.init_bot())
