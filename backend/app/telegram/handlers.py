from telegram import Update
from telegram.ext import ContextTypes


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    await update.message.reply_text(
        f"You said: {user_message}"
    )