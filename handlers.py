import asyncio
import re
from telebot.types import Message
from md2tgmd import escape

import bconf
from gemini import chat as gemini_chat
from gemini import gen_text as gemini_gen_text
from gemini import gen_image as gemini_gen_image
from bot import bot
import utils


error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')


#  message handlers
@bot.message_handler(commands=['start'])
async def cmd_start(message: Message) -> None:
    try:
        await bot.reply_to(
            message,
            escape(
                "Welcome, you can ask me questions now. \nFor example: `Who is john lennon?`"
            ),
            parse_mode="MarkdownV2")
    except IndexError:
        await utils.err_message(bot, message)


@bot.message_handler(commands=['gemini20'])
async def cmd_gemini(message: Message) -> None:
    try:
        # validating message
        message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(
            message,
            escape(
                "Please add what you want to say after /gemini. \nFor example: `/gemini Who is john lennon?`"
            ),
            parse_mode="MarkdownV2")
        return
    await gemini_chat(bot, message, utils.model_1)


@bot.message_handler(commands=['gemini25'])
async def cmd_gemini_pro(message: Message) -> None:
    try:
        message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(
            message,
            escape(
                "Please add what you want to say after /gemini_pro. \nFor example: `/gemini_pro Who is john lennon?`"
            ),
            parse_mode="MarkdownV2")
        return
    await gemini_chat(bot, message, utils.model_2)


@bot.message_handler(commands=['text2image'])
async def cmd_image(message: Message) -> None:
    try:
        message.text.strip().split(maxsplit=1)[1].strip()
    except IndexError:
        await bot.reply_to(
            message,
            escape(
                "Please add what image you want. \n"
                "For example: `/text2image Generate an image of the Eiffel Tower with a fireworks background.`"
            ),
            parse_mode="MarkdownV2")
        return
    await gemini_gen_image(bot, message, utils.model_1)


@bot.message_handler(commands=['clear'])
async def cmd_clear(message: Message) -> None:
    # Check if the player is already in gemini_player_dict.
    if str(message.from_user.id) in bconf.gemini_chat_dict:
        del bconf.gemini_chat_dict[str(message.from_user.id)]
    if str(message.from_user.id) in bconf.gemini_pro_chat_dict:
        del bconf.gemini_pro_chat_dict[str(message.from_user.id)]
    await bot.reply_to(message, "Your history has been cleared")


@bot.message_handler(commands=['switch'])
async def cmd_switch(message: Message) -> None:
    if message.chat.type != "private":
        await bot.reply_to(message, "This command is only for private chat !")
        return
    # Check if the player is already in default_chat_dict.
    if str(message.from_user.id) not in bconf.default_chat_dict:
        bconf.default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Switch to " + utils.model_2)
        return
    if bconf.default_chat_dict[str(message.from_user.id)]:
        bconf.default_chat_dict[str(message.from_user.id)] = False
        await bot.reply_to(message, "Switch to" + utils.model_2)
    else:
        bconf.default_chat_dict[str(message.from_user.id)] = True
        await bot.reply_to(message, "Switch to " + utils.model_1)


#  handle all other text messages in private chat
@bot.message_handler(func=lambda message: message.chat.type == "private", content_types=['text'])
@bot.message_handler(regexp=bconf.BOT_NAME, chat_types=['group', 'supergroup', 'channel'], content_types=['text'])
async def handle_text_message(message: Message) -> None:
    """
       Handle text messages sent to bot. In group/channel chats, use `@bot` to start a chat.

       If group user does not start a private chat with bot, and use /switch to switch model first,
       this handler will always use default model.

       :param message: Instance of :class:`telebot.types.Message`
       """
    model = await utils.choose_model(message.from_user.id)
    await gemini_chat(bot, message, model)


# content_types=['audio', 'photo', 'voice', 'video', 'document','text', 'location', 'contact', 'sticker']
@bot.message_handler(func=lambda message: True, content_types=['photo', 'document', 'video', 'audio'])
async def handle_file(message: Message) -> None:
    """
        Handle file messages for bot
        
        :param message: Instance of :class:`telebot.types.Message`
    """
    content_type = message.content_type
    chat_type = message.chat.type
    caption = message.caption
    # you must add caption and start with '@bot' to invoke this function in group chat
    if chat_type != 'private':
        if caption is None or not caption.startswith(bconf.BOT_NAME):
            return
        else:
            caption = caption.strip().split(maxsplit=1)[1].strip() if len(caption.strip().split(maxsplit=1)) > 1 else ""
    else:
        # if caption is not set in private chat...
        if not caption:
            caption = bconf.DEFAULT_PROMPT_CN.get(content_type)
    # choose a model?
    model = await utils.choose_model(message.from_user.id)
    await gemini_gen_text(bot, message, caption, model)
