import io
import uuid
import requests
import traceback
import asyncio
import random
from md2tgmd import escape
from markdown_it import MarkdownIt
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

import bconf
from bconf import logger

SUFFIX = '.png'
model_1 = bconf.models.get('model_1')
model_2 = bconf.models.get('model_2')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')

slice_size = 2048  # 默认最长消息长度
slice_step = 512  # 默认长度内没有换行符时，向后查询的步长
max_retries = 3
base_delay = 1


# using markdown-it to analyse and split Markdown text
# without broke markdown's structure
def spit_markdown_new(text) -> list[str]:
    chunks = []
    chunk = ""
    if len(text) < slice_size:
        return [text]
    md = MarkdownIt("commonmark", {"html": False, "typographer": True})
    tokens = md.parse(text)

    #
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


async def choose_model(user_id: int) -> str:
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


async def upload_photo(image_bytes, chat_id, caption='', mime_type='image/png'):
    image_file = None
    try:
        # Create an in-memory file-like object from the bytes
        image_file = io.BytesIO(image_bytes)

        files = {
            "photo": (random_file_name(), image_file, mime_type)
        }
        data = {
            "chat_id": chat_id,
            "caption": caption
        }

        response = requests.post(bconf.UPLOAD_PHOTO_URL, data=data, files=files)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        logger.info(f'Photo uploaded: {response}')
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending image: {e}")
    finally:
        if 'image_file' in locals():
            image_file.close()


def random_file_name():
    return str(uuid.uuid4()) + SUFFIX


# split markdown by '\n'
def spit_markdown(text) -> list[str]:
    """
    Deprecated.
    """
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


async def send_message(bot: AsyncTeleBot, message: Message, text: str, parse_mode='MarkdownV2', mode='reply'):
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
                await err_message(bot, message)


async def err_message(bot: AsyncTeleBot, message: Message, err_info: str = error_info):
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