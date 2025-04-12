import asyncio
import traceback
import mimetypes
import re
import random

from google import genai
from google.genai.types import GenerateContentResponse
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from md2tgmd import escape
from google.genai.errors import ServerError
from google.genai import types
from httpx import ConnectError
import bconf

logger = bconf.logger
logger.name = __name__

model_1 = bconf.models.get('model_1')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')
pattern = r"[?.!？。！]"
max_retries = 3
base_delay = 1

# init gemini client
gClient = genai.Client(api_key=bconf.API_KEY)


# gemini chat
async def chat(bot: AsyncTeleBot, msg: Message, model: str):
    chats = None
    m_text = msg.text.strip()
    if m_text.startswith('/'):
        # it's a command
        m_text = m_text.split(maxsplit=1)[1].strip()
    if model == model_1:
        chat_dict = bconf.gemini_chat_dict
    else:
        chat_dict = bconf.gemini_pro_chat_dict
    if str(msg.from_user.id) not in chat_dict:
        chats = gClient.aio.chats.create(model=model, config=bconf.generation_config)
        chat_dict[str(msg.from_user.id)] = chats
    else:
        chats = chat_dict[str(msg.from_user.id)]
    sent_message = await bot.reply_to(msg, before_gen_info)
    logger.info(f'Chat prompt: {m_text}, model: {model}')
    try:
        response = await chats.send_message(m_text)
    except Exception as e:
        logger.error(f'APIError: response error. {e}\n{traceback.format_exc()}')
        await reply_and_del_err_message(bot, sent_message, 'API response error')
        return
    await split_and_send(bot, sent_message, response)


# gemini generate content
async def gen_text(bot: AsyncTeleBot, message: Message, caption: str, model: str, url_flag: bool = False,
                   **kwargs) -> None:
    """
    Gemini content generation model.
    
    :param bot: Instance of :class:`telebot.async_telebot.AsyncTeleBot`
    
    :param message: Instance of :class:`telebot.types.Message`
    
    :param caption: `str` type file/image caption,  set while sending message
    
    :param model: gemini model name :class:`str`
    
    :param url_flag: `bool` value for online YouTube video, default false
    
    :kwargs: Other necessary params like url='https://youtube.com/watch?v=GqybdMKEf5s'
    """
    file_info = None
    sent_message = ''
    file_bytes = None
    url = ''
    mime_type = ''
    content_type = message.content_type

    # load file
    try:
        if content_type != 'text':
            if content_type == 'document':
                file_info = await bot.get_file(message.document.file_id)
                mime_type = message.document.mime_type
            elif content_type == 'photo':
                file_info = await bot.get_file(message.photo[-1].file_id)
                mime_type = mimetypes.guess_type(file_info.file_path)[0]
            elif content_type == 'video':
                file_info = await bot.get_file(message.video.file_id)
                mime_type = message.video.mime_type
            elif content_type == 'audio':
                file_info = await bot.get_file(message.audio.file_id)
                mime_type = message.audio.mime_type
            file_bytes = await bot.download_file(file_info.file_path)
        else:
            # it's an url hard coded
            url = kwargs.get('url')
        sent_message = await bot.reply_to(message=message, text=before_gen_info)
    except Exception as e:
        logger.error(f'File Error: {e}\n{traceback.format_exc()}')
        await reply_and_del_err_message(bot, sent_message)
        return

    # TODO: url content part has empty mime type
    if url_flag:
        contents = [
            types.Part.from_text(text=caption),
            types.Part.from_uri(file_uri=url, mime_type=mime_type)  # empty mime_type?
        ]
    else:
        contents = [
            types.Part.from_text(text=caption),
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
        ]

    logger.info(f'content generating: file: {content_type}, caption: {caption}, model: {model}')
    response = None
    try:
        # raise ServerError(code=503, response_json={'code': 503, 'message': 'Internet Server error message'})
        # raise ConnectError('debug error')
        response = await gClient.aio.models.generate_content(
            model=model, contents=contents, config=bconf.generation_config)
    except ServerError as e1:
        # server 503
        logger.error(f"Server error: code:{e1.code}, message: {e1.message}")
        await reply_and_del_err_message(bot, sent_message, e1.message)
    except ConnectError as e2:
        # https error, ignore
        logger.error(f'ConnectError occurred: {e2}\n{traceback.format_exc()}')
        await reply_and_del_err_message(bot, sent_message, 'Internet Error')
    # logger.info(f'generated: {response.text}')
    await split_and_send(bot, sent_message, response)


# tele_bot 400 error:   message too long
# '你好！很高兴为你服务。有什么我可以帮你的吗？\n'
# split long response to multiple messages
async def split_and_send(bot: AsyncTeleBot,
                         message: Message,
                         response: GenerateContentResponse,
                         parse_mode='MarkdownV2', ):
    slice_size = 3072  # 默认最长消息长度
    slice_step = 512  # 默认长度内没有换行符时，向后查询的步长
    segments = []
    start = 0
    text = response.text
    # logger.info(f'response content: {response}')
    if text is None:
        logger.error(f'APIError: response is None')
        await reply_and_del_err_message(bot, message, 'API Error: response text is None!')
        return
    elif len(text) > slice_size:
        while start < len(text):
            end = min(start + slice_size, len(text))
            # (start, end)  ~ 3072
            # find the closest empty line
            split_point = text.rfind('\n', start, end)
            # 没找到继续向后查找
            while split_point == -1 and end < len(text):
                i_start = end
                end = min(end + slice_step, len(text))
                split_point = text.rfind('\n', i_start, end)

            if split_point == -1:
                # find last end of sentence may be a better way
                # fixed_end = end
                # for i in range(end - 1, start - 1, -1):
                #     if re.match(pattern, text[i]):
                #         fixed_end = i
                #         break
                segment = text[start:end]
                start = end
            else:
                segment = text[start:split_point + 1]
                start = split_point + 1
            segments.append(segment)
    else:
        segments.append(text)
    logger.info(f'Response segments count: {len(segments)}')

    # retry if network error occurs
    await send_and_retry_message(bot, message, segments[0], parse_mode)

    for segment in segments[1:]:
        await send_and_retry_message(bot, message, segment, parse_mode, 'new')


async def send_and_retry_message(bot: AsyncTeleBot, message: Message, text: str, parse_mode='MarkdownV2', mode='reply'):
    """
    send/reply message(s) with retry mach

    param: mode: str of message mode, default 'reply'
    """
    for attempt in range(max_retries):
        try:
            if mode == 'reply':
                await bot.edit_message_text(escape(text),
                                            chat_id=message.chat.id,
                                            message_id=message.message_id,
                                            parse_mode=parse_mode)
            else:
                await bot.send_message(message.chat.id, escape(text), parse_mode=parse_mode)
            break
        except Exception as oe:
            # (reply)edit message error, maybe (parse_mode error)? or network error
            logger.error(f'Send message error, will retry: {oe}\n{traceback.format_exc()}')
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.info(f'Send message error, will retry in {delay} seconds')
                await asyncio.sleep(delay)
            else:
                logger.error(f'Maximum retries reached, Send message ERROR')
                await reply_and_del_err_message(bot, message)


async def reply_and_del_err_message(bot: AsyncTeleBot, message: Message, err_info: str = error_info):
    try:
        await bot.edit_message_text(
            err_info,
            chat_id=message.chat.id,
            message_id=message.message_id
        )
        await asyncio.sleep(30)
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logger.error(f'Error on deleting message: {e}\n{traceback.format_exc()}')
