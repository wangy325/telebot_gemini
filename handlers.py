
import traceback
from telebot.types import Message
from md2tgmd import escape
from google.genai import types

import bconf
from gemini import chat as gChat
from gemini import async_generate_content as gContent
from bot import bot

logger = bconf.logger
logger.name = __name__

model_1 = bconf.models.get('model_1')
model_2 = bconf.models.get('model_2')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')
download_pic_notify = bconf.prompts.get('download_pic_notify')


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
    await gChat(bot, message, m, model_1)


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
    await gChat(bot, message, m, model_2)


@bot.message_handler(commands=['clear'])
async def clear(message: Message) -> None:
    # Check if the player is already in gemini_player_dict.
    if (str(message.from_user.id) in bconf.gemini_chat_dict):
        del bconf.gemini_chat_dict[str(message.from_user.id)]
    if (str(message.from_user.id) in bconf.gemini_pro_chat_dict):
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
    if bconf.default_chat_dict[str(message.from_user.id)] == True:
        bconf.default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Now you are using " + model_2)
    else:
        bconf.default_chat_dict[str(message.from_user.id)] = True
        await bot.reply_to(message, "Now you are using " + model_1)

#  handle all other text messages in private chat
@bot.message_handler(func=lambda message: message.chat.type == "private", content_types=['text'])
async def private_text_handler(message: Message) -> None:
    m = message.text.strip()
    from_who = message.from_user.id
    if str(from_who) not in bconf.default_chat_dict:
        bconf.default_chat_dict[str(from_who)] = True
        await gChat(bot, message, m, model_1)
    else:
        if bconf.default_chat_dict[str(from_who)]:
            await gChat(bot, message, m, model_1)
        else:
            await gChat(bot, message, m, model_2)

# handle group/channel '@' text chat
@bot.message_handler(regexp=bconf.BOT_NAME, chat_types=['group','supergroup','channel'], content_types=['text'])
async def group_at_text_handler(message:Message) -> None:
    logger.info(f'group chat @ed message received: {message.text.strip()}')
    await private_text_handler(message)

# image2text
@bot.message_handler(content_types=['photo'])
async def image2text_handler(message: Message) -> None:
    logger.info(f'image message received: chat_type: {message.chat.type}, caption: {message.caption}')
    caption = message.caption
    if not caption or caption == "":
        await bot.reply_to(message=message, text='Please add caption to the image, so that I can know what to do~')
        return 
    try:
        file_path = await bot.get_file(message.photo[-1].file_id)
        sent_message = await bot.reply_to(message, download_pic_notify)
        #  base64 encoded str
        downloaded_file = await bot.download_file(file_path.file_path)
    except Exception:
        traceback.print_exc()
        await bot.reply_to(message, error_info)
    contents = [
        types.Part.from_text(text=caption),
        types.Part.from_bytes(data=downloaded_file, mime_type="image/jpeg")
    ]
    try:
        await bot.edit_message_text(before_gen_info,
                                        chat_id=sent_message.chat.id,
                                        message_id=sent_message.message_id)
        response = await gContent(model_1, contents)
        # logger.info(f'image2text gemini response: {response.text}')
        await bot.edit_message_text(escape(response.text),
                                        chat_id=sent_message.chat.id,
                                        message_id=sent_message.message_id,
                                        parse_mode='MarkdownV2')
    except Exception:
        traceback.print_exc()
        await bot.edit_message_text(error_info,
                                        chat_id=sent_message.chat.id,
                                        message_id=sent_message.message_id)   
 