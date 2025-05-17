import os
import argparse
import logging

import telebot
from google.genai import types
from telebot import asyncio_helper


logger = telebot.logger
logger.setLevel(logging.INFO)

# global configs
prompts = {
    'error_info': "⚠️⚠️⚠️\nSomething went wrong !\nplease try to change your prompt or contact the admin !",
    'before_generate_info': "☁️Generating..."
}

models = {
    "model_1": "gemini-2.0-flash-exp",
    "model_2": "gemini-2.5-flash-preview-04-17",
}

# Init args
parser = argparse.ArgumentParser(
    description="Telegram bot args for Google gemini")
parser.add_argument("--token",
                    help="telegram token",
                    default=os.environ.get("BOT_TOKEN"))
parser.add_argument("--key",
                    help="Google Gemini API key",
                    default=os.environ.get("API_KEY"))
parser.add_argument("--botname",
                    help="telegram bot name",
                    default=os.environ.get("BOT_NAME"))
parser.add_argument("--webhook",
                    help="telegram bot deploy webhook. optional",
                    default=os.environ.get("WEB_HOOK"))
args = parser.parse_args()
if not args.token:
    parser.error(
        "--token is required. Please provide it as a command-line argument or set the BOT_TOKEN environment variable. "
    )
BOT_TOKEN = args.token
if not args.key:
    parser.error(
        "--key is required. Please provide it as a command-line argument or set the API_KEY environment variable. "
    )
API_KEY = args.key
if not args.botname:
    logger.warning(
        "--botName is not provided. Using default value '@wygemibot'. You have to set it if you want deploy your own "
        "bot with full features work fine."
    )
BOT_NAME = args.botname or '@wygemibot'
WEB_HOOK = args.webhook or None
WEBHOOK_PORT = 8443
WEBHOOK_LISTEN = '0.0.0.0'
#  no ssl used for koy'eb
WEBHOOK_URL = f"{WEB_HOOK}/{BOT_TOKEN}/"
#  telebot file path
FILE_PATH = "https://api.telegram.org/file/bot{}/{}"
UPLOAD_PHOTO_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

# model instructions
MODEL_INSTRUCTIONS = [
        "你是一个倾向于使用中文回答问题的AI助理",
        "You are a AI assistant who always intend to answer questions in Chinese.",
        "Once you are asked in English, that means you are expected to reply in English."
]
DEFAULT_PROMPT_EN = {
    "photo": "Please describe what you see in this picture. ",
    "document": "Please summarize this document for me. ",
    "video": "Please summarize this video. ",
    "audio": "Please describe this audio clip."
}

DEFAULT_PROMPT_CN = {
    "photo": "请为我描述这张图片。",
    "document": "请为我总结一下这个文档。",
    "video": "请总结这个视频。",
    "audio": "请描述此音频片段的内容"
}

# Gemini model configs
generation_config = types.GenerateContentConfig(
    temperature=0.3,
    top_p=0.5,
    top_k=1,
    max_output_tokens=4096,
    seed=30,
    tools=[types.Tool(google_search=types.GoogleSearch())],
    safety_settings=[
        types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', # type: ignore
                            threshold='BLOCK_NONE'), # type: ignore
        types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', # type: ignore
                            threshold='BLOCK_NONE'), # type: ignore
        types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', # type: ignore
                            threshold='BLOCK_NONE'), # type: ignore
        types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', # type: ignore
                            threshold='BLOCK_NONE'), # type: ignore
    ],
    system_instruction=MODEL_INSTRUCTIONS
)

# model context cache
gemini_chat_dict = {}
gemini_pro_chat_dict = {}
# used model cache
default_chat_dict = {}
# content generate cache
gemini_content_dict = {}
gemini_pro_content_dict = {}
# context cache (for content generation only, to caching file in chat)
# only caching last 1 file content
file_context = {}


# for local debug only
def set_local_proxies():
    asyncio_helper.proxy = 'http://127.0.0.1:7890'
    os.environ['http_proxy'] = "http://127.0.0.1:7890"
    os.environ['https_proxy'] = "http://127.0.0.1:7890"
    os.environ['all_proxy'] = "socks5://127.0.0.1:7890"
    logger.info('Using local proxy.')


logger.info("Arg parse done.")

