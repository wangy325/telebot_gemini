import asyncio
import traceback
import mimetypes
import random

from google import genai
from google.genai.chats import AsyncChat
from google.genai.types import GenerateContentResponse
from markdown_it import MarkdownIt
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from md2tgmd import escape
from google.genai.errors import ServerError
from google.genai import types
from httpx import ConnectError
import bconf
from bconf import logger


model_1 = bconf.models.get('model_1')
model_2 = bconf.models.get('model_2')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')
max_retries = 3
base_delay = 1
slice_size = 2048  # 默认最长消息长度
slice_step = 512  # 默认长度内没有换行符时，向后查询的步长

# init gemini client
gClient = genai.Client(api_key=bconf.API_KEY)


# gen gemini chat model
async def creat_chats(model: str) -> AsyncChat:
    loop = asyncio.get_event_loop()

    def create_chat_model():
        return gClient.aio.chats.create(model=model,
                                        config=bconf.generation_config,
                                        history=[types.Content(
                                            role='user',
                                            parts=[types.Part.from_text(text=bconf.MODEL_INSTRUCTIONS[1]), ],
                                        )])

    return await loop.run_in_executor(None, create_chat_model)


# gemini chat
async def chat(bot: AsyncTeleBot, msg: Message, model: str):
    m_text = msg.text.strip()
    if m_text.startswith('/'):
        # it's a command
        m_text = m_text.split(maxsplit=1)[1].strip()
    if model == model_1:
        chat_dict = bconf.gemini_chat_dict
    else:
        chat_dict = bconf.gemini_pro_chat_dict
    if str(msg.from_user.id) not in chat_dict:
        chat_model = await creat_chats(model)
        chat_dict[str(msg.from_user.id)] = chat_model
    else:
        chat_model = chat_dict[str(msg.from_user.id)]
    sent_message = await bot.reply_to(msg, before_gen_info)
    logger.info(f'Chat prompt: {m_text}, model: {model}')
    try:
        response = await chat_model.send_message(m_text)
        logger.info(f'Chat response: {response.text}')
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
    
    :param url_flag: `bool` value, `True` indicates that message contains YouTube video url,
        and model needs to analyse the video. Default `False`
    
    :param kwargs: Optional. Necessary when param `url_flag` is `True`.
        Available value: `url='https://youtube.com/watch?v=GqybdMKEf5s'`
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

    logger.info(f'Content generation: file type: {content_type}, caption: {caption}, model: {model}')
    response = None
    try:
        # raise ConnectError('debug error')
        # raise ServerError(code=503,
        #                   response_json={'code': 503, 'message': 'Internet Server error message'}
        #                   )
        response = await gClient.aio.models.generate_content(
            model=model, contents=contents, config=bconf.generation_config)
        # record this response to chats history if there is a chat
        logger.info(f'Content generation response: {response.candidates[0].content}')
        await record_response(message, response, model)

    except ServerError as e1:
        # server 503
        logger.error(f"Server error: code:{e1.code}, message: {e1.message}")
        await reply_and_del_err_message(bot, sent_message, e1.message)
    except ConnectError as e2:
        # https error, ignore
        logger.error(f'ConnectError occurred: {e2}\n{traceback.format_exc()}')
        await reply_and_del_err_message(bot, sent_message, 'Internet Error')
    await split_and_send(bot, sent_message, response)


# tele_bot 400 error:   message too long
# '你好！很高兴为你服务。有什么我可以帮你的吗？\n'
# split long response to multiple messages
async def split_and_send(bot: AsyncTeleBot,
                         message: Message,
                         response: GenerateContentResponse,
                         parse_mode='MarkdownV2', ):
    text = response.text
    if text is None:
        logger.error(f'APIError: response is None')
        await reply_and_del_err_message(bot, message, 'API Error: response text is None!')
        return
    elif len(text) > slice_size:
        segments = spit_markdown_new(text)
    else:
        segments = [text]
    logger.info(f'Response segments count: {len(segments)}')

    # retry if network error occurs
    await send_and_retry_message(bot, message, segments[0], parse_mode)

    for segment in segments[1:]:
        await send_and_retry_message(bot, message, segment, parse_mode, 'new')


# using markdown-it to analyse and split markdown text
# without broke markdown's structure
def spit_markdown_new(text) -> list[str]:
    chunks = []
    chunk = ""
    if len(text) < slice_size:
        return [text]
    md = MarkdownIt("commonmark", {"html": False, "typographer": True})
    tokens = md.parse(text)

    for token in tokens:
        last_token_tag = token.tag
        if token.type.endswith("_open"):
            if token.tag == 'ul':
                chunk += "\n"
            elif token.tag == 'li':
                if token.level > 1:
                    chunk += "\t" + token.info + token.markup + " "
                else:
                    chunk += token.info + token.markup + " "
            elif last_token_tag == 'li':
                continue
            else:
                # 判断是否结束token？
                if len(chunk) > slice_size:
                    # 开新的chunk
                    chunks.append(chunk)
                    chunk = ""
        elif token.type == "fence":
            chunk += token.markup + token.info + "\n" + token.content + token.markup + "\n\n"
        elif token.type.endswith("_close"):
            if token.tag == 'ul':
                chunk += "\n"
        else:
            chunk += token.content
            # nested ul li
            if token.level > 1:
                chunk += "\n"
            else:
                chunk += "\n\n"
    else:
        chunks.append(chunk[:-2])
    return chunks


#  split markdown by '\n'
def spit_markdown(text) -> list[str]:
    segments = []
    start = 0
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
    return segments


# record model response content to chat history
async def record_response(message: Message, response: GenerateContentResponse, model: str):
    cached_chat = None
    if model == model_1:
        cached_chat = bconf.gemini_chat_dict.get(str(message.from_user.id))
    elif model == model_2:
        cached_chat = bconf.gemini_pro_chat_dict.get(str(message.from_user.id))
    if cached_chat is None:
        cached_chat = await creat_chats(model)
        if model == model_1:
            bconf.gemini_chat_dict[str(message.from_user.id)] = cached_chat
        elif model == model_2:
            bconf.gemini_pro_chat_dict[str(message.from_user.id)] = cached_chat
    try:
        # ping and no pong
        sent_message: GenerateContentResponse = await cached_chat.send_message('你好')
        curated_history = cached_chat.get_history(True)
        res_content = response.candidates[0].content
        cached_chat.record_history(
            res_content,
            curated_history,
            sent_message.automatic_function_calling_history,
            True)
    except Exception as e:
        logger.error(f'Record response error: {e}\n{traceback.format_exc()}')


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
            logger.error(f'Send message error: {oe}\n{traceback.format_exc()}')
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
