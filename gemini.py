import asyncio
import traceback
from google import genai
from telebot import TeleBot
from telebot.types import Message
from md2tgmd import escape
import bconf

logger = bconf.logger
logger.name = __name__

model_1 = bconf.models.get('model_1')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')

gClient = genai.Client(api_key=bconf.API_KEY)

# Prevent "model.generate_content" function from blocking the event loop.
async def async_generate_content(model, contents):
    loop = asyncio.get_running_loop()

    def generate():
        return gClient.models.generate_content(model=model, contents=contents)

    response = await loop.run_in_executor(None, generate)
    return response


async def chat(bot: TeleBot, message: Message, m: str, model_type: str):
    chat = None
    if model_type == model_1:
        chat_dict = bconf.gemini_chat_dict
    else:
        chat_dict = bconf.gemini_pro_chat_dict
    if str(message.from_user.id) not in chat_dict:
        chat = gClient.aio.chats.create(model=model_type,
                                              config=bconf.generation_config)
        chat_dict[str(message.from_user.id)] = chat
    else:
        chat = chat_dict[str(message.from_user.id)]
    # new api does not support chat history
    try:
        sent_message = await bot.reply_to(message, before_gen_info)
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
# split long response to multiple messages
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
    logger.info(segments)
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

