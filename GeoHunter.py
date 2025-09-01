# GeoHunter.py
import requests
import time
import traceback
from typing import Dict, Any
import asyncio
import sqlite3
import os
import logging
import json
from dotenv import load_dotenv
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, JobQueue, CallbackQueryHandler

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

# Режим работы (демо/реальный)
DEMO_MODE = os.getenv('DEMO_MODE', 'True').lower() == 'true'

def create_crypto_invoice(user_id: int, amount: float, asset: str = "USDT") -> Dict[str, Any]:
    """Создание инвойса в CryptoBot"""
    if DEMO_MODE:
        logger.info(f"Demo mode: Creating fake invoice for user {user_id}, amount {amount}")
        return {
            'invoice_id': f"demo_{user_id}_{int(time.time())}",
            'pay_url': f"https://t.me/geohunter_bot?start=demo_payment_{user_id}_{amount}",
            'status': 'active'
        }
    
    # Проверяем наличие токена
    if not CRYPTO_BOT_TOKEN or ":" not in CRYPTO_BOT_TOKEN:
        logger.error("CryptoBot token is missing or invalid")
        return {}
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    
    # Генерируем уникальный payload для отслеживания платежа
    payload_data = {
        "user_id": user_id, 
        "type": "deposit",
        "amount": amount,
        "timestamp": int(time.time())
    }
    
    payload_str = json.dumps(payload_data)
    
    payload = {
        "asset": asset,
        "amount": str(amount),
        "description": f"GeoHunter deposit for user {user_id}",
        "paid_btn_name": "viewItem",  # Изменено с "open" на "viewItem"
        "paid_btn_url": f"https://t.me/geohunter_bot?start=payment_{user_id}_{amount}",
        "payload": payload_str,
        "allow_comments": False,
        "allow_anonymous": False
    }
    
    try:
        logger.info(f"Sending request to CryptoBot API: {CRYPTO_BOT_API_URL}api/createInvoice")
        
        response = requests.post(
            f"{CRYPTO_BOT_API_URL}api/createInvoice",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response text: {response.text}")
        
        # Проверяем статус ответа
        if response.status_code == 401:
            logger.error("CryptoBot API returned 401 Unauthorized. Please check your token.")
            return {"error": "Invalid API token"}
        elif response.status_code == 400:
            logger.error("CryptoBot API returned 400 Bad Request. Please check your parameters.")
            return {"error": "Bad request parameters"}
        
        response.raise_for_status()
        result = response.json()
        
        # Проверяем структуру ответа
        if result.get('ok'):
            return result.get('result', {})
        else:
            error = result.get('error', {})
            logger.error(f"CryptoBot API error: {error.get('name', 'Unknown')} - {error.get('code', 'No code')}")
            return {"error": error.get('name', 'Unknown error')}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error creating CryptoBot invoice: {e}")
        return {"error": "Network error"}
    except Exception as e:
        logger.error(f"Unexpected error creating CryptoBot invoice: {e}")
        logger.error(traceback.format_exc())
        return {"error": "Unexpected error"}
        
        
        
def check_crypto_invoice(invoice_id: int) -> Dict[str, Any]:
    """Проверка статуса инвойса в CryptoBot"""
    if DEMO_MODE:
        # В демо-режиме имитируем проверку инвойса
        if invoice_id.startswith("demo_"):
            return {'status': 'paid'}
        return {'status': 'active'}
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN
    }
    
    try:
        response = requests.get(
            f"{CRYPTO_BOT_API_URL}api/invoice?invoice_ids={invoice_id}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        result = response.json().get("result", {}).get("items", [])
        return result[0] if result else {}
    except Exception as e:
        logger.error(f"Error checking CryptoBot invoice: {e}")
        return {}

def check_cryptobot_connection():
    """Проверка подключения к CryptoBot API"""
    if DEMO_MODE:
        logger.info("Demo mode: Skipping CryptoBot connection check")
        return True
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN
    }
    
    try:
        response = requests.get(
            f"{CRYPTO_BOT_API_URL}api/getMe",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        if result.get('ok') and 'result' in result:
            logger.info(f"CryptoBot API connection successful: {result['result']}")
            return True
        else:
            logger.error(f"CryptoBot API connection failed: {result}")
            return False
    except Exception as e:
        logger.error(f"CryptoBot API connection error: {e}")
        return False

async def process_crypto_payment(context: CallbackContext) -> None:
    """Асинхронная обработка платежей через CryptoBot"""
    try:
        logger.info("Starting payment processing job")
        
        # Получаем все ожидающие платежи из базы данных
        conn = sqlite3.connect('geohunter.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM transactions WHERE status = "pending" AND provider = "cryptobot"')
        pending_transactions = cursor.fetchall()
        conn.close()
        
        logger.info(f"Found {len(pending_transactions)} pending transactions")
        
        for transaction in pending_transactions:
            transaction_id, user_id, amount, transaction_type, status, provider, provider_transaction_id, created_at = transaction
            
            logger.info(f"Checking invoice {provider_transaction_id} for user {user_id}")
            
            # Проверяем статус инвойса
            invoice_info = check_crypto_invoice(provider_transaction_id)
            
            logger.info(f"Invoice info: {invoice_info}")
            
            if invoice_info.get('status') == 'paid':
                logger.info(f"Invoice {provider_transaction_id} is paid, updating balance")
                
                # Обновляем статус транзакции и баланс пользователя
                db.update_balance(user_id, amount)
                db.add_transaction(user_id, amount, "deposit", "completed", "cryptobot", provider_transaction_id)
                
                # Уведомляем пользователя
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Ваш платеж на ${amount} успешно обработан! Текущий баланс: ${db.get_balance(user_id)}"
                    )
                    logger.info(f"Notification sent to user {user_id}")
                except Exception as e:
                    logger.error(f"Error sending payment confirmation: {e}")
    except Exception as e:
        logger.error(f"Error in process_crypto_payment: {e}")
        logger.error(traceback.format_exc())

async def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Создаем или получаем пользователя
    db.create_user(user)
    
    # Обработка платежных callback
    if context.args:
        if context.args[0].startswith('payment_'):
            try:
                parts = context.args[0].split('_')
                if len(parts) >= 3:
                    target_user_id = int(parts[1])
                    amount = float(parts[2])
                    
                    # Проверяем, что это тот же пользователь
                    if user.id == target_user_id:
                        # Показываем сообщение о ожидании платежа
                        await update.message.reply_text(
                            f"✅ Ваш платеж на ${amount} обрабатывается. "
                            f"Баланс будет зачислен в течение нескольких минут после подтверждения платежа."
                        )
            except ValueError:
                logger.error("Invalid payment callback format")
        
        elif context.args[0].startswith('demo_payment_'):
            try:
                parts = context.args[0].split('_')
                if len(parts) >= 4:
                    target_user_id = int(parts[2])
                    amount = float(parts[3])
                    
                    # Проверяем, что это тот же пользователь
                    if user.id == target_user_id:
                        # В демо-режиме сразу зачисляем средства
                        db.update_balance(user.id, amount)
                        db.add_transaction(user.id, amount, "deposit", "completed", "demo", f"demo_{int(time.time())}")
                        
                        await update.message.reply_text(
                            f"✅ Демо-платеж на ${amount} успешно обработан! "
                            f"Текущий баланс: ${db.get_balance(user.id)}"
                        )
            except ValueError:
                logger.error("Invalid demo payment callback format")
    
    welcome_text = (
        "🌟 Welcome to GeoHunter! 🌟\n\n"
        "I'll help you find hidden treasures around you!\n\n"
    )
    
    if DEMO_MODE:
        welcome_text += "🔶 ДЕМО-РЕЖИМ 🔶\n"
        welcome_text += "Все платежи виртуальные, для тестирования.\n\n"
    
    welcome_text += "Click the button below to launch the game interface:"
    
    # Добавляем initData для аутентификации в веб-приложении
    web_app_url = f"{WEB_APP_URL}?user_id={user.id}&demo_mode={DEMO_MODE}"
    
    keyboard = [
        [InlineKeyboardButton("🎮 Launch GeoHunter", web_app=WebAppInfo(url=web_app_url))]
    ]
    
    # Добавляем кнопку для пополнения баланса
    if not DEMO_MODE:
        keyboard.append([InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
async def show_deposit_menu(update: Update, context: CallbackContext) -> None:
    """Показать меню пополнения баланса"""
    query = update.callback_query
    await query.answer()
    
    # Просто вызываем команду пополнения баланса
    await deposit_command(update, context)
    
async def deposit_command(update: Update, context: CallbackContext) -> None:
    """Команда для пополнения баланса"""
    user_id = update.effective_user.id
    
    if DEMO_MODE:
        # В демо-режиме предлагаем виртуальное пополнение
        keyboard = [
            [InlineKeyboardButton("➕ 10$ (Демо)", callback_data="demo_deposit_10")],
            [InlineKeyboardButton("➕ 50$ (Демо)", callback_data="demo_deposit_50")],
            [InlineKeyboardButton("➕ 100$ (Демо)", callback_data="demo_deposit_100")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔶 ДЕМО-РЕЖИМ 🔶\nВыберите сумму для виртуального пополнения:",
            reply_markup=reply_markup
        )
    else:
        # В реальном режиме предлагаем реальное пополнение
        keyboard = [
            [InlineKeyboardButton("5$", callback_data="deposit_5")],
            [InlineKeyboardButton("10$", callback_data="deposit_10")],
            [InlineKeyboardButton("20$", callback_data="deposit_20")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Выберите сумму для пополнения:",
            reply_markup=reply_markup
        )
        
async def handle_deposit_callback(update: Update, context: CallbackContext) -> None:
    """Обработка callback-запросов для пополнения баланса"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Проверяем, что это действительно запрос на пополнение с суммой
    if not callback_data.startswith(('deposit_', 'demo_deposit_')):
        await query.edit_message_text("❌ Неизвестный тип запроса.")
        return
    
    try:
        # Извлекаем сумму из callback_data
        if callback_data.startswith('demo_deposit_'):
            amount_str = callback_data.replace('demo_deposit_', '')
            is_demo = True
        else:
            amount_str = callback_data.replace('deposit_', '')
            is_demo = False
        
        # Проверяем, что amount_str состоит только из цифр
        if not amount_str.isdigit():
            await query.edit_message_text("❌ Неверный формат суммы.")
            return
            
        amount = float(amount_str)
        
        if is_demo:
            # В демо-режиме сразу зачисляем средства
            db.update_balance(user_id, amount)
            db.add_transaction(user_id, amount, "deposit", "completed", "demo", f"demo_{int(time.time())}")
            
            await query.edit_message_text(
                f"✅ Виртуальное пополнение на ${amount} успешно выполнено!\n"
                f"Текущий баланс: ${db.get_balance(user_id)}"
            )
        else:
            # В реальном режиме генерируем ссылку для оплаты
            payment_url = generate_payment_url(user_id, amount)
            
            # Проверяем, что ссылка сгенерирована успешно
            if payment_url.startswith("http"):
                await query.edit_message_text(
                    f"Для пополнения баланса на ${amount} перейдите по ссылке:\n\n{payment_url}\n\n"
                    "После оплаты баланс будет зачислен автоматически в течение нескольких минут."
                )
            else:
                await query.edit_message_text(
                    f"❌ {payment_url}\n\n"
                    "Попробуйте еще раз или обратитесь в поддержку."
                )
                
    except ValueError as e:
        logger.error(f"Error parsing amount from callback data: {callback_data}, error: {e}")
        await query.edit_message_text(
            "❌ Ошибка обработки запроса. Попробуйте еще раз или обратитесь в поддержку."
        )
    except Exception as e:
        logger.error(f"Unexpected error in handle_deposit_callback: {e}")
        logger.error(traceback.format_exc())
        await query.edit_message_text(
            "❌ Произошла непредвиденная ошибка. Попробуйте еще раз или обратитесь в поддержку."
        )

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
            f"💵 Доход: ${total_deposits - total_prizes}\n"
            f"🔶 Режим: {'Демо' if DEMO_MODE else 'Реальный'}"
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

async def admin_toggle_mode(update: Update, context: CallbackContext) -> None:
    """Переключение между демо и реальным режимом"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if str(user_id) not in os.getenv('ADMIN_IDS', '').split(','):
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    global DEMO_MODE
    DEMO_MODE = not DEMO_MODE
    
    # Сохраняем настройку в переменные окружения
    os.environ['DEMO_MODE'] = str(DEMO_MODE)
    
    await update.message.reply_text(
        f"✅ Режим изменен на: {'Демо' if DEMO_MODE else 'Реальный'}"
    )

def generate_payment_url(user_id, amount):
    """Генерация URL для оплаты через CryptoBot"""
    invoice = create_crypto_invoice(user_id, amount)
    
    if invoice and 'pay_url' in invoice:
        # Сохраняем информацию о транзакции в базу данных
        db.add_transaction(user_id, amount, "deposit", "pending", "cryptobot", invoice.get('invoice_id'))
        return invoice['pay_url']
    elif invoice and 'error' in invoice:
        logger.error(f"CryptoBot error: {invoice['error']}")
        return f"Ошибка CryptoBot: {invoice['error']}"
    else:
        logger.error(f"Failed to create invoice for user {user_id}, amount {amount}. Invoice response: {invoice}")
        return "Ошибка при создании платежа. Попробуйте позже."
        
async def handle_successful_payment(update: Update, context: CallbackContext) -> None:
    """Обработка успешного платежа"""
    # Здесь будет обработка успешных платежей
    pass

def main() -> None:
    """Запуск бота"""
    # Проверяем подключение к CryptoBot API (только в реальном режиме)
    if not DEMO_MODE and not check_cryptobot_connection():
        logger.error("Failed to connect to CryptoBot API. Please check your configuration.")
    
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("deposit", deposit_command))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(CommandHandler("toggle_mode", admin_toggle_mode))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    
    # Добавляем обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(show_deposit_menu, pattern="^deposit_menu$"))
    application.add_handler(CallbackQueryHandler(handle_deposit_callback, pattern="^(demo_)?deposit_\\d+$"))
    
    # Добавляем планировщик для проверки платежей (только в реальном режиме)
    if not DEMO_MODE:
        job_queue = application.job_queue
        if job_queue:
            job_queue.run_repeating(
                lambda context: asyncio.create_task(process_crypto_payment(context)),
                interval=300,
                first=10
            )
    
    logger.info(f"Bot started in {'DEMO' if DEMO_MODE else 'REAL'} mode")
    application.run_polling()

if __name__ == '__main__':
    main()
     