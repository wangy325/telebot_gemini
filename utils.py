import io
import uuid
import requests

import bconf
from bconf import logger

SUFFIX = '.png'
model_1 = bconf.models.get('model_1')
model_2 = bconf.models.get('model_2')
error_info = bconf.prompts.get('error_info')
before_gen_info = bconf.prompts.get('before_generate_info')


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
