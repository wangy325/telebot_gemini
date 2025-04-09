import asyncio
import io
import mimetypes
import traceback
from httpx import ConnectError
from telebot.types import Message
from md2tgmd import escape
from google.genai import types
from google.genai.errors import ServerError

import bconf
from gemini import chat as gemini_chat
from gemini import generate_content as gemini_content
from gemini import split_and_send
from bot import bot

logger = bconf.logger
logger.name = __name__

model_1 = bconf.models.get('model_1')
model_2 = bconf.models.get('model_2')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')


#  message handlers
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
async def gemini(message: Message) -> None:
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
    await gemini_chat(bot, message, model_1)


@bot.message_handler(commands=['gemini_pro'])
async def gemini_pro(message: Message) -> None:
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
    await gemini_chat(bot, message, model_2)


@bot.message_handler(commands=['clear'])
async def clear(message: Message) -> None:
    # Check if the player is already in gemini_player_dict.
    if str(message.from_user.id) in bconf.gemini_chat_dict:
        del bconf.gemini_chat_dict[str(message.from_user.id)]
    if str(message.from_user.id) in bconf.gemini_pro_chat_dict:
        del bconf.gemini_pro_chat_dict[str(message.from_user.id)]
    await bot.reply_to(message, "Your history has been cleared")


@bot.message_handler(commands=['switch'])
async def switch(message: Message) -> None:
    if message.chat.type != "private":
        await bot.reply_to(message, "This command is only for private chat !")
        return
    # Check if the player is already in default_chat_dict.
    if str(message.from_user.id) not in bconf.default_chat_dict:
        bconf.default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Now you are using " + model_2)
        return
    if bconf.default_chat_dict[str(message.from_user.id)]:
        bconf.default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Now you are using " + model_2)
    else:
        bconf.default_chat_dict[str(message.from_user.id)] = True
        await bot.reply_to(message, "Now you are using " + model_1)


#  handle all other text messages in private chat
@bot.message_handler(func=lambda message: message.chat.type == "private", content_types=['text'])
async def private_text_handler(message: Message) -> None:
    model = await choose_model(message.from_user.id)
    await gemini_chat(bot, message, model)




# handle group/channel '@' text chat
@bot.message_handler(regexp=bconf.BOT_NAME, chat_types=['group', 'supergroup', 'channel'], content_types=['text'])
async def group_at_text_handler(message: Message) -> None:
    logger.info(f'group chat @ed message received: {message.text.strip()}')
    # if group user does not start a private chat with bot,
    # this handler will always use default model(model_1)
    model = await choose_model(message.from_user.id)
    await gemini_chat(bot, message, model)

# content_types=['audio', 'photo', 'voice', 'video', 'document','text', 'location', 'contact', 'sticker']
# image2text
@bot.message_handler(func=lambda message: True, content_types=['photo', 'document', 'video', 'audio'])
async def file_handler(message: Message) -> None:
    return await handle_file(message)

#  handle files
async def handle_file(message: Message):
    content_type = message.content_type
    chat_type = message.chat.type
    caption = message.caption
    model = model_1
    # you must add caption and start with '@bot' to invoke this function in group chat
    if chat_type != 'private':
        if not caption or not caption.startswith(bconf.BOT_NAME):
            return
        else: 
            caption = caption.strip().split(maxsplit=1)[1].strip() if len(caption.strip().split(maxsplit=1)) > 1 else ""
    else:
        # if caption is not set in private chat...
        if not caption or caption == '':
            caption = bconf.DEFAULT_PROMPT_CN.get(content_type)
    # choose a model?
    model = await choose_model(message.from_user.id)
    # load file
    file_info =None
    sent_message =''
    file_bytes = None
    mime_type = ''
    try:
        if content_type == 'document':
            file_info = await bot.get_file(message.document.file_id)
            mime_type = message.document.mime_type
        elif content_type == 'photo':
            file_info = await bot.get_file(message.photo[-1].file_id)
            mime_type= mimetypes.guess_type(file_info.file_path)[0]
        elif content_type == 'video':
            file_info = await bot.get_file(message.video.file_id)
            mime_type = message.video.mime_type
        elif content_type == 'audio':
            file_info = await bot.get_file(message.audio.file_id)
            mime_type = message.audio.mime_type
        sent_message = await bot.reply_to(message=message, text=before_gen_info)
        file_bytes = await bot.download_file(file_info.file_path)
    except Exception:
        traceback.print_exc()
        await del_err_message(sent_message, error_info)
    
    contents = [
        types.Part.from_text(text=caption),
        types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        bconf.MODEL_INSTRUCTIONS
    ]
    logger.info(f'content generating: file: {file_info.file_path}, caption: {caption}, model: {model}')
    try:
        response = await gemini_content(model, contents)
        try:
            await split_and_send(bot,
                                chat_id=sent_message.chat.id,
                                text=response.text,
                                message_id=sent_message.message_id,
                                parse_mode='MarkdownV2')
        except Exception as e:
            traceback.print_exc()
            await del_err_message(sent_message, error_info)
    except ServerError as e1:
        # server 503
        logger.error(f"Server error: code:{e1.code}, message: {e1.message}")
        await del_err_message(sent_message, e1.message)
    except ConnectError as e2:
        # https error, ignore
        logger.error('Internet Error')
        await del_err_message(sent_message, 'Internet Error')
        
async def choose_model(user_id:int) -> str:
    # choose model to chat, based on content in bconf.default_chat_dict
    if str(user_id) not in bconf.default_chat_dict:
        # use model_1 by default
        bconf.default_chat_dict[str(user_id)] = True
        return model_1
    else:
        if bconf.default_chat_dict[str(user_id)]:
            return model_1
        else:
            return model_2

async def del_err_message(message: Message, err_info:str):
    await bot.edit_message_text(
            err_info,
            chat_id=message.chat.id,
            message_id=message.message_id
        )
    await asyncio.sleep(30)
    await bot.delete_message(message.chat.id, message.message_id)