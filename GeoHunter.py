# GeoHunter.py
import requests
import time
from typing import Dict, Any
import asyncio
import sqlite3
import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, JobQueue

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

# CryptoBot API configuration
CRYPTO_BOT_TOKEN = os.getenv('CRYPTO_BOT_TOKEN')
CRYPTO_BOT_TESTNET = os.getenv('CRYPTO_BOT_TESTNET', 'True').lower() == 'true'
CRYPTO_BOT_API_URL = "https://testnet-pay.crypt.bot/" if CRYPTO_BOT_TESTNET else "https://pay.crypt.bot/"

def create_crypto_invoice(user_id: int, amount: float, asset: str = "USDT") -> Dict[str, Any]:
    """Создание инвойса в CryptoBot"""
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    
    payload = {
        "asset": asset,
        "amount": str(amount),
        "description": f"Пополнение счета для пользователя {user_id}",
        "paid_btn_name": "open",
        "paid_btn_url": f"https://t.me/geohunter_bot?start=payment_success_{user_id}",
        "payload": json.dumps({"user_id": user_id, "type": "deposit"}),
        "allow_comments": False,
        "allow_anonymous": False
    }
    
    try:
        response = requests.post(
            f"{CRYPTO_BOT_API_URL}api/invoice",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        return response.json().get("result", {})
    except Exception as e:
        logger.error(f"Error creating CryptoBot invoice: {e}")
        return {}

def check_crypto_invoice(invoice_id: int) -> Dict[str, Any]:
    """Проверка статуса инвойса в CryptoBot"""
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN
    }
    
    try:
        response = requests.get(
            f"{CRYPTO_BOT_API_URL}api/invoice/{invoice_id}",
            headers=headers
        )
        response.raise_for_status()
        return response.json().get("result", {})
    except Exception as e:
        logger.error(f"Error checking CryptoBot invoice: {e}")
        return {}

# Замените функцию process_crypto_payment в GeoHunter.py

async def process_crypto_payment(context: CallbackContext) -> None:
    """Асинхронная обработка платежей через CryptoBot"""
    try:
        # Получаем все ожидающие платежи из базы данных
        conn = sqlite3.connect('geohunter.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transactions WHERE status = "pending" AND provider = "cryptobot"')
        pending_transactions = cursor.fetchall()
        conn.close()
        
        for transaction in pending_transactions:
            transaction_id, user_id, amount, transaction_type, status, provider, provider_transaction_id, created_at = transaction
            
            # Проверяем статус инвойса
            invoice_info = check_crypto_invoice(provider_transaction_id)
            
            if invoice_info.get('status') == 'paid':
                # Обновляем статус транзакции и баланс пользователя
                db.update_balance(user_id, amount)
                db.add_transaction(user_id, amount, "deposit", "completed", "cryptobot", provider_transaction_id)
                
                # Уведомляем пользователя
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Ваш платеж на ${amount} успешно обработан! Текущий баланс: ${db.get_balance(user_id)}"
                    )
                except Exception as e:
                    logger.error(f"Error sending payment confirmation: {e}")
    except Exception as e:
        logger.error(f"Error in process_crypto_payment: {e}")
                

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
        
        
async def admin_stats(update: Update, context: CallbackContext) -> None:
    """Показать статистику для администратора"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if str(user_id) not in os.getenv('ADMIN_IDS', '').split(','):
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    # Используем методы базы данных вместо прямых SQL-запросов
    try:
        # Получаем статистику через методы базы данных
        conn = sqlite3.connect('geohunter.db')
        cursor = conn.cursor()
        
        # Общая статистика
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM games')
        total_games = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(prize_won) FROM games')
        total_prizes = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(amount) FROM transactions WHERE type = "deposit" AND status = "completed"')
        total_deposits = cursor.fetchone()[0] or 0
        
        conn.close()
        
        # Формируем сообщение со статистикой
        stats_message = (
            "📊 Статистика бота:\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🎮 Всего игр: {total_games}\n"
            f"🏆 Всего выигрышей: ${total_prizes}\n"
            f"💰 Всего пополнений: ${total_deposits}\n"
            f"💵 Доход: ${total_deposits - total_prizes}"
        )
        
        await update.message.reply_text(stats_message)
        
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении статистики.")
        
        
        
async def admin_broadcast(update: Update, context: CallbackContext) -> None:
    """Рассылка сообщения всем пользователям"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if str(user_id) not in os.getenv('ADMIN_IDS', '').split(','):
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    # Проверяем, есть ли текст для рассылки
    if not context.args:
        await update.message.reply_text("❌ Укажите сообщение для рассылки: /broadcast Ваше сообщение")
        return
    
    message = ' '.join(context.args)
    
    # Получаем всех пользователей
    conn = sqlite3.connect('geohunter.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    # Отправляем сообщение всем пользователям
    success = 0
    fail = 0
    
    for user in users:
        try:
            await context.bot.send_message(chat_id=user[0], text=message)
            success += 1
        except Exception as e:
            logger.error(f"Error sending message to {user[0]}: {e}")
            fail += 1
    
    await update.message.reply_text(
        f"✅ Рассылка завершена:\n"
        f"✅ Успешно: {success}\n"
        f"❌ Не удалось: {fail}"
    )

def generate_payment_url(user_id, amount):
    """Генерация URL для оплаты через CryptoBot"""
    invoice = create_crypto_invoice(user_id, amount)
    
    if invoice and 'pay_url' in invoice:
        # Сохраняем информацию о транзакции в базу данных
        db.add_transaction(user_id, amount, "deposit", "pending", "cryptobot", invoice.get('invoice_id'))
        return invoice['pay_url']
    
    return "https://t.me/CryptoBot?start=invoice_error"
    

async def handle_successful_payment(update: Update, context: CallbackContext) -> None:
    """Обработка успешного платежа"""
    # Здесь будет обработка успешных платежей
    # Пока заглушка
    pass

# В функции main() после создания application
def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    # Добавляем обработчики команд администратора
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    
    # Добавляем планировщик для проверки платежей каждые 5 минут
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            lambda context: asyncio.create_task(process_crypto_payment(context)),
            interval=300,
            first=10
        )
    
    logger.info("Bot started with database and web app support")
    application.run_polling()

if __name__ == '__main__':
    main()