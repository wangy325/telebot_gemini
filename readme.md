<!-- TOC -->
  * [A Simple Telegram Chat Bot with Gemini Inside](#a-simple-telegram-chat-bot-with-gemini-inside)
  * [Usage](#usage)
    * [Install requirements](#install-requirements)
    * [Run Locally](#run-locally)
      * [Parameters:](#parameters)
      * [Additional](#additional-)
    * [Run with Docker](#run-with-docker)
      * [Build image](#build-image)
      * [Run Image](#run-image)
  * [Deploy](#deploy)
    * [Deploy on pythonanywhere](#deploy-on-pythonanywhere)
    * [Deploy on koyeb](#deploy-on-koyeb)
  * [Supported Models](#supported-models)
  * [What can this bot do](#what-can-this-bot-do)
  * [TODO](#todo)
<!-- TOC -->>


## A Simple Telegram Chat Bot with Gemini Inside

Demo: [@wygemibot](https://t.me/wygemibot)

## Usage

### Install requirements

```cmd
pip install -r ./requirements.txt
```

### Run Locally

```cmd
python main.py --key {your google api key} --token {bot token} --botname {botname} --webhook {webhook url}
```

#### Parameters:

1. `--key`: Required. Google gemini api key, can apply from https://aistudio.google.com/app/apikey
2. `--token`: Required. Telegram bot token, get it from [BotFather](https://t.me/BotFather)
3. `--botname`: Required. Your botname, get it from **BotFather** or bot info page <username>, 
   start with`@`, `@mybot` for example. 
4. `--webhook`: Optional. Set it to run telegram bot in webhook mode, or in polling mode.

#### Additional 

1. You need set proxy to make telegram and gemini connect to server successfully. You can find a 
   named `set_local_proxy` method in `bconf.py`, run it before start bot in `main.py`

    ```python
    if __name__ == '__main__':
        bconf.set_local_proxies()
        asyncio.run(init_bot())
    ```

2. If you want to run bot in webhook mode locally, you may need extra tools like [ngrok](https://ngrok.com/) 
   to proxy your `localhost:port` to a public https link.

### Run with Docker

#### Build image

```cmd
docker build -t image:tag .
```

#### Run Image

```cmd
docker run -d --network host \
-e API_KEY=gemini_api_key \
-e BOT_TOKEN=bot_token \
-e BOT_NAME=bot_name \
-e WEB_HOOK=web_hook_url \
image:tag
```

## Deploy

### Deploy on pythonanywhere

[pythonanywhere](https://www.pythonanywhere.com/) is a provider offers free cloud resources to host and your python codes.

Using pythonanywhere, your bot can run in polling mode. And it's simple to deploy.

Upload all project files, install requirements and run `python main.py` -h for help.

Just same as run in local machine.

### Deploy on koyeb

[koyeb](https://app.koyeb.com/) offers free limited resource to host your web app, which is enough to host this bot.

By using koyeb, bot must run in webhook mode.

1. build your own docker image and push it to docker hub
2. config your server
   1. source: your image docker hub path
   2. environment variables:
      - API_KEY=gemini_api_key 
      - BOT_TOKEN=bot_token 
      - BOT_NAME=bot_name 
      - WEB_HOOK=web_hook_url 
   3. configue ports: 8443

Your webhook url in koyeb is like `https://beauty-girl-7xhd16532.koyeb.app`, which is auto generated once 
service created.

## Supported Models

1. gemini-2.0-flash-exp
2. gemini-2.5-pro-exp-03-25

## What can this bot do

1. Chat, both in private and group mode.
2. Content Generating
   1. Read documents(pdf/txt/code .etc) and answer questions.
   2. Analyse photos. 
   3. Analyse audio clips.
   4. Analyse video clips
   5. ~~Analyse YouTube video by link (unstable)~~


## TODO

- [x] context of content generation
- [x] split long markdown reply 
- [x] text to image by gemini 2.0 flash
- [ ] handle reply messages~
