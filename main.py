import asyncio
import bconf
import pydevd_pycharm
import bot
# import to register handlers
import handlers

logger = bconf.logger

# local debug
pydevd_pycharm.settrace('localhost', port=12345, suspend=False, stdoutToServer=True, stderrToServer=True)


if __name__ == '__main__':
    bconf.set_local_proxies()
    asyncio.run(bot.init_bot())
