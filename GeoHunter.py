# GeoHunter.py
import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters

from database import Database

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

# Инициализация базы данных
db = Database()

async def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Создаем или получаем пользователя
    db.create_user(user)
    
    welcome_text = (
        "🌟 Welcome to GeoHunter! 🌟\n\n"
        "I'll help you find hidden treasures around you!\n\n"
        "Click the button below to launch the game interface:"
    )
    
    # Добавляем initData для аутентификации в веб-приложении
    web_app_url = f"{WEB_APP_URL}?user_id={user.id}"
    
    keyboard = [
        [InlineKeyboardButton("🎮 Launch GeoHunter", web_app=WebAppInfo(url=web_app_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def handle_web_app_data(update: Update, context: CallbackContext) -> None:
    """Обработка данных из веб-приложения"""
    try:
        data = json.loads(update.message.web_app_data.data)
        user_id = update.effective_user.id
        
        logger.info(f"Received data from web app: {data}")
        
        # Обработка разных типов данных из веб-приложения
        if data.get('type') == 'game_result':
            # Обработка результатов игры
            game_id = db.create_game(user_id, data['mode'], data['entry_fee'])
            
            # Добавляем найденные геоточки
            for geospot in data.get('found_geospots', []):
                db.add_found_geospot(
                    game_id, 
                    user_id, 
                    geospot['has_prize'], 
                    geospot.get('prize_amount', 0)
                )
            
            # Обновляем баланс пользователя
            prize_won = data.get('prize_won', 0)
            if prize_won > 0:
                db.update_balance(user_id, prize_won)
                db.update_game_result(game_id, prize_won)
                
                await update.message.reply_text(
                    f"🎉 Congratulations! You won ${prize_won}!\n"
                    f"Your current balance: ${db.get_balance(user_id)}"
                )
            else:
                db.update_game_result(game_id, 0)
                await update.message.reply_text(
                    "Thanks for playing! Better luck next time!\n"
                    f"Your current balance: ${db.get_balance(user_id)}"
                )
                
        elif data.get('type') == 'payment_request':
            # Обработка запроса на пополнение счета
            amount = data.get('amount', 0)
            payment_url = generate_payment_url(user_id, amount)
            
            await update.message.reply_text(
                f"Please complete your payment of ${amount}:\n{payment_url}"
            )
            
    except Exception as e:
        logger.error(f"Error processing web app data: {e}")
        await update.message.reply_text("Sorry, there was an error processing your request.")

def generate_payment_url(user_id, amount):
    """Генерация URL для оплаты через CryptoBot"""
    # Здесь будет реализация генерации платежной ссылки
    # Пока заглушка
    base_url = "https://t.me/CryptoBot"
    return f"{base_url}?start=invoice_{user_id}_{amount}"

async def handle_successful_payment(update: Update, context: CallbackContext) -> None:
    """Обработка успешного платежа"""
    # Здесь будет обработка успешных платежей
    # Пока заглушка
    pass

def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    logger.info("Bot started with database and web app support")
    application.run_polling()

if __name__ == '__main__':
    main()