import asyncio
import bot
import bconf
# import to register handlers
import handlers

import pydevd_pycharm

pydevd_pycharm.settrace('localhost',
                        port=33456,
                        stdoutToServer=True,
                        stderrToServer=True,
                        suspend=False)



if __name__ == '__main__':
    bconf.set_local_proxies()
    asyncio.run(bot.init_bot())
