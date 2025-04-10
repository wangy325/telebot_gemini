import asyncio
import traceback
import mimetypes
from google import genai
from telebot import TeleBot
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

# init gemini client
gClient = genai.Client(api_key=bconf.API_KEY)


# # gemini content generation
# async def generate_content(model:str, contents, config):
#     loop = asyncio.get_running_loop()

#     def generate():
#         return gClient.models.generate_content(model=model, contents=contents)

#     response = await loop.run_in_executor(None, generate)
#     return response


# gemini chat
async def chat(bot: TeleBot, msg: Message, model: str):
    chats = None
    m_text = msg.text.strip()
    if m_text.startswith('/'):
        # its a command
        m_text = m_text.split(maxsplit=1)[1].strip()
    if model == model_1:
        chat_dict = bconf.gemini_chat_dict
    else:
        chat_dict = bconf.gemini_pro_chat_dict
    if str(msg.from_user.id) not in chat_dict:
        chats = gClient.aio.chats.create(model=model,
                                         config=bconf.generation_config)
        chat_dict[str(msg.from_user.id)] = chats
    else:
        chats = chat_dict[str(msg.from_user.id)]
    # new api does not support chat history
    try:
        sent_message = await bot.reply_to(msg, before_gen_info)
        logger.info(f'chatting prompt: {m_text}, model: {model}')
        response = await chats.send_message(m_text)
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
        await reply_and_del_err_message(bot, sent_message)

# gemini generate content
async def gen_text(bot: TeleBot, message: Message, caption: str, model: str, url_flag: bool = False, **kwargs) -> None:
    """
    Gemini content generation model.
    
    :param bot: Instance of :class:`telebot.TeleBot`
    
    :param message: Instance of :class:`telebot.types.Message`
    
    :param caption: `str` type file/image caption,  set while sending message
    
    :param model: gemini model name :class:`str`
    
    :param url_flag: `bool` value for online youtube video, default false
    
    :kwargs: Other necessary params like url='https://youtube.com'
    """
    file_info =None
    sent_message =''
    file_bytes = None
    url = ''
    mime_type = ''
    content_type = message.content_type

    # logger.info(f'content_type is : {content_type} ')
    contents = {}
    # load file
    try:
        if content_type != 'text':
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
            file_bytes = await bot.download_file(file_info.file_path)
        else:
            # its a url hard coded
            url = kwargs.get('url')
        sent_message = await bot.reply_to(message=message, text=before_gen_info)
    except Exception:
        traceback.print_exc()
        await reply_and_del_err_message(bot, sent_message)

    # await file_path = bconf.FILE_PATH.format(bconf.BOT_TOKEN, file.file_path)
    types.FileData()
    if url_flag:
        contents = [
            types.Part.from_text(text=caption),
            types.Part.from_uri(file_uri=url, mime_type=mime_type)      #empty mime_type?
        ]
    else:
        contents = [
            types.Part.from_text(text=caption),
            types.Part.from_bytes(data=file_bytes, mime_type=mime_type ),
        ]

    logger.info(f'content generating: file: {content_type}, caption: {caption}, model: {model}')
    try:
        # raise ServerError(code=503, response_json={'code': 503, 'message': 'Internet Server error message'})
        # raise ConnectError('debug error')
        response = gClient.models.generate_content(
            model=model, contents=contents, config=bconf.generation_config)
        try:
            # logger.info(f'generated: {response.text}')
            await split_and_send(bot,
                                chat_id=sent_message.chat.id,
                                text=response.text,
                                message_id=sent_message.message_id,
                                parse_mode='MarkdownV2')
        except Exception as e:
            traceback.print_exc()
            await reply_and_del_err_message(bot, sent_message)
    except ServerError as e1:
        # server 503
        logger.error(f"Server error: code:{e1.code}, message: {e1.message}")
        await reply_and_del_err_message(bot, sent_message, e1.message)
    except ConnectError as e2:
        # https error, ignore
        logger.error('Internet Error')
        await reply_and_del_err_message(bot, sent_message, 'Internet Error')

# tele_bot 400 error:   message too long
# '你好！很高兴为你服务。有什么我可以帮你的吗？\n'
# split long response to multiple messages
async def split_and_send(bot,
                         chat_id,
                         text: str,
                         message_id=None,
                         parse_mode=None):
    slice_size = 3072  # 默认最长消息长度
    slice_step = 384  # 默认长度内没有换行符时，向后查询的步长
    segments = []
    start = 0
    # print(len(text))

    if len(text) > slice_size:
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


async def reply_and_del_err_message(bot: TeleBot, message: Message, err_info:str = error_info):
    await bot.edit_message_text(
            err_info,
            chat_id=message.chat.id,
            message_id=message.message_id
        )
    await asyncio.sleep(30)
    await bot.delete_message(message.chat.id, message.message_id)
