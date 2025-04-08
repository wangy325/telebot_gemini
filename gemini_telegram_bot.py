# A gemini + telegram bot script.

import argparse
import traceback
import asyncio
import telebot
from google import genai
from google.genai import types
from telebot import TeleBot
from telebot import asyncio_helper
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from md2tgmd import escape
import fastapi
import uvicorn
import os

# proxy
# https://www.pythonanywhere.com/forums/topic/32151/
# asyncio_helper.proxy = 'http://proxy.server:3128'

# for local debug only
asyncio_helper.proxy = 'http://127.0.0.1:7890'
os.environ['http_proxy'] = "http://127.0.0.1:7890"
os.environ['https_proxy'] = "http://127.0.0.1:7890"
os.environ['all_proxy'] = "socks5://127.0.0.1:7890"

# global configs
error_info = "⚠️⚠️⚠️\nSomething went wrong !\nplease try to change your prompt or contact the admin !"
before_generate_info = "☁️Generating..."
download_pic_notify = "☁️Loading picture..."
model_1 = "gemini-2.0-flash-exp"
# model_1 = "gemini-2.0-flash"
model_2 = "gemini-2.5-pro-exp-03-25"

# Init args
# parser = argparse.ArgumentParser()
# parser.add_argument("--botoken", required=True, help="telegram token", default=os.environ.get("BOT_TOKEN"))
# parser.add_argument("--apikey", required=True, help="Google Gemini API key", default=os.environ.get("API_KEY"))
# parser.add_argument("--webhook", help="telegram bot deploy webhook. optional", default=os.environ.get("WEB_HOOK"))
# options = parser.parse_args()
BOT_NAME = '@wygemibot'
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_KEY = os.environ.get("API_KEY")
WEB_HOOK = os.environ.get("WEB_HOOK", None)
print("Arg parse done.")

# gemini configs
generation_config = types.GenerateContentConfig(
    temperature=0.3,
    top_p=0.5,
    top_k=1,
    max_output_tokens=1024,
    seed=30,
    tools=[types.Tool(google_search=types.GoogleSearch())],
    safety_settings=[
        types.SafetySetting(category='HARM_CATEGORY_HARASSMENT',
                            threshold='BLOCK_NONE'),
        types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH',
                            threshold='BLOCK_NONE'),
        types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                            threshold='BLOCK_NONE'),
        types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT',
                            threshold='BLOCK_NONE'),
    ])

# gemini
gemini_chat_dict = {}
gemini_pro_chat_dict = {}
default_chat_dict = {}
# init gemini client
gemini_client = genai.Client(api_key=API_KEY)


# Prevent "model.generate_content" function from blocking the event loop.
async def async_generate_content(model, contents):
    loop = asyncio.get_running_loop()

    def generate():
        return gemini_client.models.generate_content(model, contents=contents)

    response = await loop.run_in_executor(None, generate)
    return response


async def gemini(bot: TeleBot, message: Message, m: str, model_type: str):
    chat = None
    if model_type == model_1:
        chat_dict = gemini_chat_dict
    else:
        chat_dict = gemini_pro_chat_dict
    if str(message.from_user.id) not in chat_dict:
        chat = gemini_client.aio.chats.create(model=model_type,
                                              config=generation_config)
        chat_dict[str(message.from_user.id)] = chat
    else:
        chat = chat_dict[str(message.from_user.id)]
    # new api does not support chat history
    try:
        sent_message = await bot.reply_to(message, before_generate_info)
        response = await chat.send_message(m)
        try:
            await split_and_send(bot,
                                 chat_id=sent_message.chat.id,
                                 text=response.text,
                                 message_id=sent_message.message_id,
                                 parse_mode="MarkdownV2")
        except:
            await split_and_send(bot,
                                 chat_id=sent_message.chat.id,
                                 text=response.text,
                                 message_id=sent_message.message_id)

    except Exception:
        traceback.print_exc()
        await bot.edit_message_text(error_info,
                                    chat_id=sent_message.chat.id,
                                    message_id=sent_message.message_id)


# tele_bot 400 error:   message too long
# '你好！很高兴为你服务。有什么我可以帮你的吗？\n'
async def split_and_send(bot,
                         chat_id,
                         text: str,
                         message_id=None,
                         parse_mode=None):
    slice_size = 3072  #默认最长消息长度
    slice_step = 384  #默认长度内没有换行符时，向后查询的步长
    segments = []
    start = 0
    # print(len(text))

    if len(text) > slice_size:
        while start < len(text):
            end = min(start + slice_size, len(text))
            # (start, end)  ~ 3072
            # find closest empty line
            split_point = text.rfind('\n', start, end)
            # 没找到继续向后查找
            while split_point == -1 and end < len(text):
                i_start = end
                end = min(end + slice_step, len(text))
                split_point = text.rfind('\n', i_start, end)
                # print(f"inner: {end} ")

            # print(f"outer: {split_point} ")
            if split_point - start > slice_size:
                segment = text[start:split_point + 2]
                start = split_point + 2
            elif slice_size > split_point - start > 0:
                segment = text[start:split_point + 1]
                start = split_point + 1
            else:  # split_point = -1
                segment = text[start:end]
                break  # Prevent infinite loop if no split point is found
            segments.append(segment)
    else:
        segments.append(text)
    print(segments)
    for index, segment in enumerate(segments):
        if index == 0 and message_id:
            await bot.edit_message_text(escape(segment),
                                        chat_id=chat_id,
                                        message_id=message_id,
                                        parse_mode=parse_mode)
        else:
            await bot.send_message(chat_id,
                                   escape(segment),
                                   parse_mode=parse_mode)


# Init bot
bot = AsyncTeleBot(BOT_TOKEN)

# used for webhook
app = fastapi.FastAPI(docs_url=None, )
# WEBHOOK_HOST = 'https://accurate-puma.koyeb.app'
WEBHOOK_HOST = WEB_HOOK
WEBHOOK_PORT = 8443
WEBHOOK_LISTEN = '0.0.0.0'
#  no ssl used for koyeb
WEBHOOK_URL = f"{WEBHOOK_HOST}/{BOT_TOKEN}/"


# process webhook calls
@app.post(f'/{BOT_TOKEN}/')
async def handle(update: dict):
    if update:
        update = telebot.types.Update.de_json(update)
        await bot.process_new_updates([update])
    else:
        return


async def set_webhook(url, ssl=False, ssl_cert=None):
    await bot.remove_webhook()
    if ssl:
        await bot.set_webhook(url=url, certificate=open(ssl_cert, 'r'))
    else:
        await bot.set_webhook(url=url)


async def remove_webhook():
    await bot.remove_webhook()

# 以webhook形式运行
def run_webhook():
    asyncio.run(set_webhook(WEBHOOK_URL))
    # start aiohttp server
    print("Starting webhook telegram bot.")
    # loop = asyncio.get_running_loop()
    # def webhook_app(): uvicorn.run(
    #         app,
    #         host=WEBHOOK_LISTEN,
    #         port=WEBHOOK_PORT,
    #     )
    # await loop.run_in_executor(None, webhook_app)
    # 本身开了协程
    uvicorn.run(app, host=WEBHOOK_LISTEN, port=WEBHOOK_PORT)


async def run_polling():
    await remove_webhook()
    print("Starting polling telegram bot.")
    await bot.polling(none_stop=True)


#### bot commands
@bot.message_handler(commands=['start'])
async def start(message: Message) -> None:
    try:
        await bot.reply_to(
            message,
            escape(
                "Welcome, you can ask me questions now. \nFor example: `Who is john lennon?`"
            ),
            parse_mode="MarkdownV2")
    except IndexError:
        await bot.reply_to(message, error_info)


@bot.message_handler(commands=['gemini'])
async def gemini_handler(message: Message) -> None:
    try:
        m = message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(
            message,
            escape(
                "Please add what you want to say after /gemini. \nFor example: `/gemini Who is john lennon?`"
            ),
            parse_mode="MarkdownV2")
        return
    await gemini(bot, message, m, model_1)


@bot.message_handler(commands=['gemini_pro'])
async def gemini_pro_handler(message: Message) -> None:
    try:
        m = message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(
            message,
            escape(
                "Please add what you want to say after /gemini_pro. \nFor example: `/gemini_pro Who is john lennon?`"
            ),
            parse_mode="MarkdownV2")
        return
    await gemini(bot, message, m, model_2)


@bot.message_handler(commands=['clear'])
async def clear(message: Message) -> None:
    # Check if the player is already in gemini_player_dict.
    if (str(message.from_user.id) in gemini_chat_dict):
        del gemini_chat_dict[str(message.from_user.id)]
    if (str(message.from_user.id) in gemini_pro_chat_dict):
        del gemini_pro_chat_dict[str(message.from_user.id)]
    await bot.reply_to(message, "Your history has been cleared")


@bot.message_handler(commands=['switch'])
async def switch(message: Message) -> None:
    if message.chat.type != "private":
        await bot.reply_to(message, "This command is only for private chat !")
        return
    # Check if the player is already in default_chat_dict.
    if str(message.from_user.id) not in default_chat_dict:
        default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Now you are using " + model_2)
        return
    if default_chat_dict[str(message.from_user.id)] == True:
        default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Now you are using " + model_2)
    else:
        default_chat_dict[str(message.from_user.id)] = True
        await bot.reply_to(message, "Now you are using " + model_1)

#  handle all other text messages in private chat
@bot.message_handler(func=lambda message: message.chat.type == "private", content_types=['text'])
async def gemini_private_handler(message: Message) -> None:
    m = message.text.strip()
    from_who = message.from_user.id
    if str(from_who) not in default_chat_dict:
        default_chat_dict[str(from_who)] = True
        await gemini(bot, message, m, model_1)
    else:
        if default_chat_dict[str(from_who)]:
            await gemini(bot, message, m, model_1)
        else:
            await gemini(bot, message, m, model_2)

# handle group/channel '@' text chat
@bot.message_handler(regexp=BOT_NAME, chat_types=['group','supergroup','channel'], content_types=['text'])
async def handle_group_chat(message:Message) -> None:
    print(f'group message: {message.text.strip()}')
    await gemini_private_handler(message)

# image2text
@bot.message_handler(commands=['photo'])
async def gemini_photo_handler(message: Message) -> None:
    if message.chat.type != "private":
        caption = message.caption
        if not caption or not (caption.startswith("/gemini")):
            return
        prompt = message.caption.strip().split(maxsplit=1)[1].strip() if len(message.caption.strip().split(maxsplit=1)) > 1 else ""
        await gen_image(message, prompt)
    else:
        s = message.caption if message.caption else ""
        gen_image(message, s.strip())

async def gen_image(message:Message, caption:str):
    try:
        file_path = await bot.get_file(message.photo[-1].file_id)
        sent_message = await bot.reply_to(message, download_pic_notify)
        downloaded_file = await bot.download_file(file_path.file_path)
    except Exception:
        traceback.print_exc()
        await bot.reply_to(message, error_info)
    contents = {
            "parts": [{
                "mime_type": "image/jpeg",
                "data": downloaded_file
            }, {
                "text": caption
            }]
        }
    try:
        await bot.edit_message_text(before_generate_info,
                                        chat_id=sent_message.chat.id,
                                        message_id=sent_message.message_id)
        response = await async_generate_content(model_1, contents)
        await bot.edit_message_text(response.text,
                                        chat_id=sent_message.chat.id,
                                        message_id=sent_message.message_id)
    except Exception:
        traceback.print_exc()
        await bot.edit_message_text(error_info,
                                        chat_id=sent_message.chat.id,
                                        message_id=sent_message.message_id)


if __name__ == '__main__':
   # Start the bot
    if WEB_HOOK:
        run_webhook()
    else:
        asyncio.run(run_polling())
