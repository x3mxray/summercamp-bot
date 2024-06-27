import logging
import logging.config
import os
import subprocess
import time
import telegram
import openai
import sys
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater
from pydantic_settings import BaseSettings
from pydantic.types import SecretStr
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.database import *


class BotSettings(BaseSettings):
    API_TELEGRAM: str
    OPENAI_TOKEN: str
    CHATGPT_MODEL: str
    PGDATABASE: str
    PGHOST:str
    PGPASSWORD:str
    PGPORT:str
    PGUSER: str
    PORT: int
    MODE: str


bot_settings = BotSettings(_env_file="app/.env")

openai.api_key = bot_settings.OPENAI_TOKEN
CHATGPT_MODEL = bot_settings.CHATGPT_MODEL


def help_command_handler(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text("Type /start to register to the service")


def start_command_handler(update, context):
    """Send a message when the command /start is issued."""
    add_new_user(str(update.message.chat.id))

    start_text = """
This bot allows you to query OpenAI from Telegram with voice messages!
It keeps track of your past messages, remember to select /reset from the command menu to cancel the history.
    """
    
    update.message.reply_text(start_text)


def echo(update, context):
    """Echo the user message."""
    telegram_id = str(update.message.chat.id)
    message = update.message.text
    answer = generate_response(message, telegram_id)
    update.message.reply_text(answer)


def transcribe_voice_message(voice_message: str) -> str:
    """Transcribe voice message using Wishper model."""
    # Use the Whisper AI API to transcribe the voice message
    audio_file= open(voice_message, "rb")
    result = openai.audio.transcriptions.create(
  model="whisper-1", 
  file=audio_file
)

    return result.text


def handle_voice_message(update, context):
    """ Handle telegram voice message. """
    # Get the voice message from the update
    voice_message = context.bot.get_file(update.message.voice.file_id)
    print(voice_message)
    voice_message.download("tmp/audio.oga")
    subprocess.run(["ffmpeg", "-y", "-i", 'tmp/audio.oga', 'tmp/audio.mp3'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Transcribe the voice message
    text = transcribe_voice_message("tmp/audio.mp3")

    # Answer
    telegram_id = str(update.message.chat.id)
    answer = generate_response(text, telegram_id)
    # Send the transcribed text back to the user
    update.message.reply_text(answer)
    answer_mp3 = text_to_voice(answer, "tmp/answer.mp3")
    audio_file= open(answer_mp3, "rb")
    update.message.reply_audio(audio=audio_file)

def text_to_voice(text: str, speech_file_path: str) -> str:
    response = openai.audio.speech.create(
  model="tts-1",
  voice="alloy",
  input=text
)
    response.stream_to_file(speech_file_path)
    return speech_file_path

def generate_response(question: str, telegram_id: str) -> str:
    """Generate answer using OpenAI."""

    row = retrieve_history(telegram_id)
    prompt = create_question_prompt(row, question)

    response = openai.chat.completions.create(model="gpt-3.5-turbo", messages=prompt)
    answer = response.choices[0].message.content

    logging.info("Question: %s", question)
    logging.info("Got answer: %s", answer)
    update_history_user(telegram_id, question, answer)

    return answer


def error(update, context):
    """Log Errors caused by Updates."""

    logging.warning('Update "%s" ', update)
    logging.exception(context.error)


def reset(update, context):
    """ Reset history """

    telegram_id = str(update.message.chat.id)
    reset_history_user(telegram_id)


def main():
    updater = Updater(DefaultConfig.TELEGRAM_TOKEN, use_context=True)

    dp = updater.dispatcher

    # command handlers
    dp.add_handler(CommandHandler("help", help_command_handler))
    dp.add_handler(CommandHandler("start", start_command_handler))
    dp.add_handler(CommandHandler("reset", reset))

    # message handler
    dp.add_handler(MessageHandler(Filters.text, echo))
    dp.add_handler(MessageHandler(Filters.voice, handle_voice_message))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    if DefaultConfig.MODE == "webhook":
        updater.start_webhook(
            listen="0.0.0.0",
            port=int(DefaultConfig.PORT),
            url_path=DefaultConfig.TELEGRAM_TOKEN,
            webhook_url=DefaultConfig.WEBHOOK_URL + DefaultConfig.TELEGRAM_TOKEN
        )

        logging.info(f"Start webhook mode on port {DefaultConfig.PORT}")
    else:
        updater.start_polling()
        logging.info(f"Start polling mode")

    updater.idle()


class DefaultConfig:
    PORT = bot_settings.PORT
    TELEGRAM_TOKEN = bot_settings.API_TELEGRAM
    MODE = bot_settings.MODE
    WEBHOOK_URL = ""
    LOG_LEVEL = "INFO"

    @staticmethod
    def init_logging():
        logging.basicConfig(
            format="%(asctime)s - %(levelname)s - %(message)s",
            level=DefaultConfig.LOG_LEVEL,
        )
        


if __name__ == "__main__":
    # Enable logging
    DefaultConfig.init_logging()
    logging.info(f"PORT: {DefaultConfig.PORT}")
    main()
