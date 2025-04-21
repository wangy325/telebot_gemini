import asyncio
import re
import traceback
import mimetypes

from google import genai
from google.genai.chats import AsyncChat
from google.genai.types import GenerateContentResponse
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message
from google.genai.errors import ServerError
from google.genai import types
from httpx import ConnectError
import bconf
from bconf import logger
import utils


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
    if m_text.startswith('/') or re.compile(bconf.BOT_NAME).match(m_text):
        # it's a command
        m_text = m_text.split(maxsplit=1)[1].strip()
    if model == utils.model_1:
        chat_dict = bconf.gemini_chat_dict
    else:
        chat_dict = bconf.gemini_pro_chat_dict
    if str(msg.from_user.id) not in chat_dict:
        chat_model = await creat_chats(model)
        chat_dict[str(msg.from_user.id)] = chat_model
    else:
        chat_model = chat_dict[str(msg.from_user.id)]
    sent_message = await bot.reply_to(msg, utils.before_gen_info)
    logger.info(f'Chat prompt: {m_text}, model: {model}')
    try:
        response = await chat_model.send_message(m_text)
        # logger.info(f'Chat response: {response.text}')
    except Exception as e:
        logger.error(f'APIError: response error. {e}\n{traceback.format_exc()}')
        await utils.err_message(bot, sent_message, 'API response error')
        return
    await split_and_send(bot, sent_message, response)


# gemini content generation
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
            content_type = 'url'
        sent_message = await bot.reply_to(message=message, text=utils.before_gen_info)
    except Exception as e:
        logger.error(f'File Error: {e}\n{traceback.format_exc()}')
        await utils.err_message(bot, sent_message)
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
        # logger.info(f'Content generation response: {response.candidates[0].content}')
        await record_response(message, response, model)

    except ServerError as e1:
        # server 503
        logger.error(f"Server error: code:{e1.code}, message: {e1.message}")
        await utils.err_message(bot, sent_message, e1.message)
    except ConnectError as e2:
        # https error, ignore
        logger.error(f'ConnectError occurred: {e2}\n{traceback.format_exc()}')
        await utils.err_message(bot, sent_message, 'Internet Error')
    await split_and_send(bot, sent_message, response)


# Gemini image generation
async def gen_image(bot: AsyncTeleBot, message: Message,  model: str):
    # TODO: text2image and image2image
    caption = message.text.strip().split(maxsplit=1)[1].strip()
    try:
        response = await gClient.aio.models.generate_content(
            model=model,
            contents=[types.Part.from_text(text=caption)],
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE']
            )
        )
    except Exception as e:
        logger.error(f'Image Error: {e}\n{traceback.format_exc()}')
        await utils.err_message(bot, message, "API response error")
        return
    response_part = response.candidates[0].content.parts
    i_bytes, r_text, mime_type = None, '', ''
    if response_part:
        for part in response_part:
            if part.text is not None:
                r_text = part.text
            if part.inline_data is not None:
                logger.info('Image generation success.')
                i_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type
    if i_bytes:
        await utils.upload_photo(i_bytes, message.chat.id, r_text, mime_type)
    else:
        await utils.err_message(bot, message, "Can't not get generated image info. Please try again later.")


# tele_bot 400 error:   message too long
# split long response to multiple messages
async def split_and_send(bot: AsyncTeleBot,
                         message: Message,
                         response: GenerateContentResponse,
                         parse_mode='MarkdownV2', ):
    text = response.text
    if text is None:
        logger.error(f'APIError: response is None')
        await utils.err_message(bot, message, 'API Error: response text is None!')
        return
    elif len(text) > utils.slice_size:
        segments = utils.spit_markdown_new(text)
    else:
        segments = [text]
    logger.info(f'Response segments count: {len(segments)}')

    # retry if network error occurs
    await utils.send_message(bot, message, segments[0], parse_mode)

    for segment in segments[1:]:
        await utils.send_message(bot, message, segment, parse_mode, 'new')


# record model response content to chat history
async def record_response(message: Message, response: GenerateContentResponse, model: str):
    cached_chat = None
    if model == utils.model_1:
        cached_chat = bconf.gemini_chat_dict.get(str(message.from_user.id))
    elif model == utils.model_2:
        cached_chat = bconf.gemini_pro_chat_dict.get(str(message.from_user.id))
    if cached_chat is None:
        cached_chat = await creat_chats(model)
        if model == utils.model_1:
            bconf.gemini_chat_dict[str(message.from_user.id)] = cached_chat
        elif model == utils.model_2:
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

