import fastapi
import telebot
from telebot.async_telebot import AsyncTeleBot

import bconf

# Init bot
bot = AsyncTeleBot(bconf.BOT_TOKEN)

# used for webhook
app = fastapi.FastAPI(docs_url=None, )
# process webhook calls
@app.post(f'/{bconf.BOT_TOKEN}/')
async def webhook_call(update: dict):
    if update:
        update = telebot.types.Update.de_json(update)
        await bot.process_new_updates([update])
    else:
        return