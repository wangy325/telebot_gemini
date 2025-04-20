import asyncio
import bconf
import bot
# import to register handlers
import handlers

import pydevd_pycharm

pydevd_pycharm.settrace('localhost',
                        port=33456,
                        suspend=False,
                        stdoutToServer=True,
                        stderrToServer=True)

if __name__ == '__main__':
    # bconf.set_local_proxies()
    asyncio.run(bot.init_bot())
