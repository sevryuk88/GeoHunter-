import os
import logging
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://sevryuk88.github.io/GeoHunter-/geohtml.html')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: CallbackContext) -> None:
    """Отправляет сообщение с кнопкой для открытия WebApp"""
    user = update.effective_user
    
    welcome_text = (
        "🌟 Welcome to GeoHunter! 🌟\n\n"
        "I'll help you find hidden treasures around you!\n\n"
        "Click the button below to launch the game interface:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎮 Launch GeoHunter", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    logger.info("Bot started in WebApp-only mode")
    application.run_polling()

if __name__ == '__main__':
    main()