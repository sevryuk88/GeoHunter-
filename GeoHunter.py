import os
import random
import math
import logging
import json  # Добавьте этот импорт, если его нет
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from telegram import (
    Update,
    WebAppInfo, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler, 
    MessageHandler, 
    CallbackContext,
    CallbackQueryHandler,
    filters
)
from geopy.distance import geodesic

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID', '0')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ЭКОНОМИЧЕСКАЯ СИСТЕМА ==========
# Параметры режимов
GAME_MODES = {
    'economy': {
        'name': '🟢 Эконом',
        'entry_fee': 5,
        'min_prize': 3,
        'max_prize': 30,
        'win_probability': 0.08,  # 8%
        'prize_distribution': {
            3: 0.75,    # 75% chance
            5: 0.15,    # 15% chance
            10: 0.07,   # 7% chance
            30: 0.03    # 3% chance
        }
    },
    'standard': {
        'name': '🔵 Стандарт',
        'entry_fee': 10,
        'min_prize': 5,
        'max_prize': 50,
        'win_probability': 0.15,  # 15%
        'prize_distribution': {
            5: 0.55,    # 55% chance
            10: 0.25,   # 25% chance
            20: 0.15,   # 15% chance
            50: 0.05    # 5% chance
        }
    },
    'premium': {
        'name': '🟣 Премиум',
        'entry_fee': 15,
        'min_prize': 10,
        'max_prize': 100,
        'win_probability': 0.22,  # 22%
        'prize_distribution': {
            10: 0.50,   # 50% chance
            15: 0.25,   # 25% chance
            25: 0.15,   # 15% chance
            50: 0.07,   # 7% chance
            100: 0.03   # 3% chance
        }
    }
}

# Общие параметры экономики
HOUSE_EDGE = 0.12        # Преимущество казино (12%)
JACKPOT_CONTRIBUTION = 0.02  # Взнос в джекпот (2%)
JACKPOT_PROBABILITY = 0.0005  # Вероятность выигрыша джекпота (0.05%)


WIN_MESSAGES = [
    "🎉 Ура! Ты нашел геометку с призом! 🎉",
    "💰 Вот это удача! Геометка принесла тебе {prize} руб.!",
    "🤑 Нашел клад! Забирай {prize} руб.!",
    "✨ Бинго! Ты нашел {prize} руб. в геометке!",
    "💎 Ого! Геометка оказалась с сюрпризом: {prize} руб.!"
]

EMPTY_MESSAGES = [
    "🔍 Ты нашел геометку, но она пустая.",
    "🤷‍♂️ Ничего страшного, эта метка оказалась пустой. Ищи следующую!",
    "💨 На этот раз не повезло. Метка пустая, но удача уже близко!",
    "🌫️ Эх, эта геометка пустая. Не сдавайся!",
    "❌ Пусто... Но в следующий раз обязательно повезет!"
]

JACKPOT_MESSAGES = [
    "🎰 🎰 🎰 ДЖЕКПОТ! 🎰 🎰 🎰\n\n💎 ВЫ ВЫИГРАЛИ ГЛАВНЫЙ ПРИЗ: {prize} руб.! 💎",
    "🔥 НЕВЕРОЯТНО! ДЖЕКПОТ {prize} руб.! 🔥\n\nЭто настоящая удача!",
    "🏆 ПОБЕДА! Ты сорвал джекпот в {prize} руб.! 🏆\n\nПоздравляем!"
]

# Динамическая экономика
class DynamicEconomy:
    def __init__(self):
        self.total_games = 0
        self.total_profit = 0
        self.win_rate_history = []
        
    def adjust_difficulty(self, base_probability):
        """Автоматическая регулировка сложности на основе статистики"""
        if len(self.win_rate_history) < 10:
            return base_probability
            
        avg_win_rate = sum(self.win_rate_history) / len(self.win_rate_history)
        
        # Регулируем сложность
        if avg_win_rate > base_probability * 1.2:  # Если выигрывают слишком часто
            return max(base_probability * 0.7, base_probability * 0.9)  # Уменьшаем вероятность
        elif avg_win_rate < base_probability * 0.8:  # Если выигрывают слишком редко
            return min(base_probability * 1.3, base_probability * 1.1)  # Увеличиваем вероятность
        return base_probability

# Джекпот система
JACKPOT_POOL = 100  # Начальный джекпот

# Система уровней
USER_LEVELS = {
    1: {"xp_required": 0, "reward": 0, "title": "Новичок"},
    2: {"xp_required": 100, "reward": 5, "title": "Искатель"},
    3: {"xp_required": 300, "reward": 10, "title": "Охотник"},
    4: {"xp_required": 600, "reward": 20, "title": "Мастер"},
    5: {"xp_required": 1000, "reward": 50, "title": "Легенда"}
}

# Опыт за действия
XP_PER_GAME = 5
XP_PER_WIN = 15

# Ограничения ответственной игры
RESPONSIBLE_GAMING_LIMITS = {
    'daily_deposit_limit': 1000,
    'daily_games_limit': 20,
    'cooling_off_period': 24
}

# ========== БАЗЫ ДАННЫХ ==========
games = {}
user_balances = {}
transactions = {}
user_stats = {}
user_achievements = {}
user_referrals = {}
DAILY_STATS = {}
economy = DynamicEconomy()

# Глобальная статистика
global_stats = {
    'total_games': 0,
    'total_deposits': 0,
    'total_prizes': 0,
    'total_revenue': 0,
    'jackpot_wins': 0,
    'active_players': set()
}

# ========== ГЕО-КОНФИГУРАЦИЯ ==========
SEARCH_RADIUS = 30  # Радиус поиска в метрах 100
MAX_DISTANCE = 10    # Расстояние для реакции 50
FIND_DISTANCE = 10   # Дистанция находки 10
GPS_TOLERANCE = 20   # Погрешность GPS в метрах 20
LIVE_LOCATION_DURATION = 600  # 10 минут в секундах

class GeoGame:
    def __init__(self, user_id, center_lat, center_lon, game_mode):
        self.user_id = user_id
        self.center = (center_lat, center_lon)
        self.game_mode = game_mode
        self.mode_config = GAME_MODES[game_mode]
        self.geospots = self.generate_geospots()
        self.found_spots = []
        self.start_time = datetime.now()
        self.last_update = datetime.now()
        self.live_location_active = False
        self.last_proximity_check = {}
        logger.info(f"Created new {game_mode} game for user {user_id}")
        
    def generate_geospots(self, count=5):
        """Генерация случайных геометок в радиусе"""
        spots = []
        current_win_probability = economy.adjust_difficulty(self.mode_config['win_probability'])
        
        logger.info(f"Generating spots with win probability: {current_win_probability}")
        
        
        for _ in range(count):
            # Генерация координат
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, SEARCH_RADIUS)
            
            earth_radius = 6371000
            dx = distance * math.cos(angle)
            dy = distance * math.sin(angle)
            
            delta_lat = dy / earth_radius * (180 / math.pi)
            delta_lon = dx / (earth_radius * math.cos(math.radians(self.center[0]))) * (180 / math.pi)
            
            new_lat = self.center[0] + delta_lat
            new_lon = self.center[1] + delta_lon
            
            # Определяем, будет ли приз
            has_prize = random.random() < current_win_probability
            prize_amount = self.generate_prize_amount() if has_prize else 0
            
            spots.append({
                'coords': (new_lat, new_lon),
                'has_prize': has_prize,
                'prize_amount': prize_amount,
                'found': False,
                'type': 'money' if has_prize else 'empty'
            })
            logger.info(f"Spot {_}: has_prize={has_prize}, amount={prize_amount}")
    
        
        return spots
    
    def generate_prize_amount(self):
        """Генерация суммы приза на основе распределения"""
        rand = random.random()
        cumulative = 0
        
        for prize, probability in self.mode_config['prize_distribution'].items():
            cumulative += probability
            if rand <= cumulative:
                return prize
        
        return self.mode_config['min_prize']  # Минимальный приз по умолчанию
    
    def check_proximity(self, user_location):
        """Проверка близости к геометкам"""
        results = []
        user_lat, user_lon = user_location
        
        for i, spot in enumerate(self.geospots):
            if spot['found']:
                continue
                
            spot_lat, spot_lon = spot['coords']
            
            # Горизонтальное расстояние
            horizontal_dist = geodesic(user_location, (spot_lat, spot_lon)).meters
            
            # Учет погрешности GPS
            effective_dist = max(0, horizontal_dist - GPS_TOLERANCE)
            
            if effective_dist <= MAX_DISTANCE:
                progress = int((1 - effective_dist / MAX_DISTANCE) * 100)
                results.append({
                    'distance': effective_dist,
                    'progress': progress,
                    'spot': spot,
                    'is_close': effective_dist <= FIND_DISTANCE
                })
        
        return results

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def log_transaction(user_id: int, amount: int, transaction_type: str):
    """Логирование транзакции"""
    if user_id not in transactions:
        transactions[user_id] = []
    
    transactions[user_id].append({
        'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'amount': amount,
        'type': transaction_type
    })
    
    # Обновляем глобальную статистику
    if amount > 0:
        global_stats['total_deposits'] += amount
    else:
        global_stats['total_prizes'] += abs(amount)
    
    global_stats['total_revenue'] = global_stats['total_deposits'] - global_stats['total_prizes']

def can_play_game(user_id: int) -> bool:
    """Проверка, может ли пользователь играть сегодня"""
    today = date.today()
    if today not in DAILY_STATS:
        DAILY_STATS[today] = {}
    
    if user_id not in DAILY_STATS[today]:
        DAILY_STATS[today][user_id] = {'games_played': 0, 'amount_deposited': 0}
    
    return DAILY_STATS[today][user_id]['games_played'] < RESPONSIBLE_GAMING_LIMITS['daily_games_limit']

def log_game_played(user_id: int):
    """Логирование сыгранной игры"""
    today = date.today()
    if today not in DAILY_STATS:
        DAILY_STATS[today] = {}
    
    if user_id not in DAILY_STATS[today]:
        DAILY_STATS[today][user_id] = {'games_played': 0, 'amount_deposited': 0}
    
    DAILY_STATS[today][user_id]['games_played'] += 1

async def check_achievements(update: Update, context: CallbackContext, user_id: int, achievement_type: str):
    """Проверка и выдача достижений"""
    if user_id not in user_achievements:
        user_achievements[user_id] = {}
    
    # Проверяем достижения
    if achievement_type == "first_win" and "first_win" not in user_achievements[user_id]:
        user_achievements[user_id]["first_win"] = True
        reward = 5
        
        user_balances[user_id] += reward
        log_transaction(user_id, reward, "achievement_reward")
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎖 Получено достижение: Первый выигрыш!\n💰 Награда: {reward} руб."
        )

def generate_near_miss():
    """Создание ситуации 'почти выигрыша'"""
    if random.random() < 0.15:  # 15% шанс near miss
        messages = [
            "Ой! Вы были так близки к выигрышу! Попробуйте еще раз!",
            "Почти получилось! Следующая метка точно будет удачной!",
            "Удача уже на вашей стороне! Продолжайте поиски!"
        ]
        return random.choice(messages)
    return None

# ========== КНОПКИ ==========
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎮 Начать игру", callback_data='choose_mode')],
        [InlineKeyboardButton("🌎 Открыть карту", web_app=WebAppInfo(url="https://sevryuk88.github.io/GeoHunter-/geohtml.html"))],
   
        [InlineKeyboardButton("💰 Мой баланс", callback_data='check_balance')],
        [InlineKeyboardButton("💳 Пополнить счет", callback_data='make_deposit')],
        [InlineKeyboardButton("👥 Пригласить друзей", callback_data='invite_friends')],
        [InlineKeyboardButton("❓ Правила", callback_data='show_rules')],
        [InlineKeyboardButton("📊 Статистика", callback_data='user_stats')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_mode_selection_keyboard():
    keyboard = [
        [InlineKeyboardButton("🟢 Эконом (5 руб.)", callback_data='mode_economy')],
        [InlineKeyboardButton("🔵 Стандарт (10 руб.)", callback_data='mode_standard')],
        [InlineKeyboardButton("🟣 Премиум (15 руб.)", callback_data='mode_premium')],
        [InlineKeyboardButton("🔙 Назад", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_keyboard():
    keyboard = [
        [InlineKeyboardButton("📍 Включить трансляцию", callback_data='start_live_location')],
        [InlineKeyboardButton("📊 Моя статистика", callback_data='user_stats')],
        [InlineKeyboardButton("❌ Завершить игру", callback_data='cancel_game')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_live_location_keyboard():
    keyboard = [
        [InlineKeyboardButton("📍 Остановить трансляцию", callback_data='stop_live_location')],
        [InlineKeyboardButton("📊 Моя статистика", callback_data='user_stats')],
        [InlineKeyboardButton("❌ Завершить игру", callback_data='cancel_game')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_deposit_keyboard():
    keyboard = [
        [InlineKeyboardButton("15 руб.", callback_data='deposit_15')],
        [InlineKeyboardButton("50 руб. (+5 руб. бонус)", callback_data='deposit_50')],
        [InlineKeyboardButton("100 руб. (+15 руб. бонус)", callback_data='deposit_100')],
        [InlineKeyboardButton("🔙 Назад", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ОБРАБОТЧИКИ ==========
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Инициализация пользователя
    if user.id not in user_balances:
        user_balances[user.id] = 0
        user_stats[user.id] = {'level': 1, 'xp': 0, 'games_played': 0, 'prizes_won': 0}
    
    welcome_text = (
        "🌟 Добро пожаловать в GeoHunter! 🌟\n\n"
        "Я помогу тебе найти скрытые сокровища вокруг тебя!\n\n"
        "Доступные режимы игры:\n"
        f"🟢 Эконом: 5 руб. - призы 3-30 руб.\n"
        f"🔵 Стандарт: 10 руб. - призы 5-50 руб.\n"
        f"🟣 Премиум: 15 руб. - призы 10-100 руб.\n\n"
        f"💎 Джекпот: {JACKPOT_POOL} руб. (шанс {JACKPOT_PROBABILITY*100}%)\n\n"
        "Выбери действие:"
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_text,
        reply_markup=get_main_menu_keyboard()
    )

async def rules(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    rules_text = (
        "📜 Правила GeoHunter:\n\n"
        "1. Выбери режим игры и внеси депозит\n"
        "2. Запусти игру, отправив свою геопозицию\n"
        "3. Я создам 5 скрытых геометок в радиусе 100 м\n"
        "4. Перемещайся по местности и ищи метки\n"
        "5. Когда приблизишься к метке:\n"
        "   - 📱 Телефон начнет вибрировать\n"
        "   - 🔔 Появится звуковой сигнал\n"
        "   - 📊 Шкала будет показывать близость\n"
        "6. Найди все метки и собери призы!\n\n"
        "🔥 Советы:\n"
        "- Используйте 'Трансляцию геопозиции' для автоматического отслеживания\n"
        "- Приближайтесь к меткам медленно, чтобы не пропустить их\n\n"
        "Удачи в охоте! 🗺️"
    )
    
    await query.edit_message_text(rules_text, reply_markup=get_back_keyboard())

async def choose_mode(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    mode_text = (
        "🎮 Выбери режим игры:\n\n"
        "🟢 Эконом (5 руб.)\n"
        "   - Призы: 3-30 руб.\n\n"   
        "🔵 Стандарт (10 руб.)\n"
        "   - Призы: 5-50 руб.\n\n"   
        "🟣 Премиум (15 руб.)\n"
        "   - Призы: 10-100 руб.\n\n"   
        "💎 Во всех режимах есть шанс выиграть джекпот!"
    )
    
    await query.edit_message_text(mode_text, reply_markup=get_mode_selection_keyboard())

async def start_game(update: Update, context: CallbackContext, game_mode: str) -> None:
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    mode_config = GAME_MODES[game_mode]
    
    # Проверяем баланс
    if user.id not in user_balances or user_balances[user.id] < mode_config['entry_fee']:
        payment_text = (
            f"Для игры в режиме {mode_config['name']} требуется {mode_config['entry_fee']} руб.\n\n"
            f"Что вы можете найти:\n"
            f"• Призы: {mode_config['min_prize']}-{mode_config['max_prize']} руб.\n"
            f"• Шанс выигрыша: {int(mode_config['win_probability'] * 100)}%\n"
            f"• Джекпот: {JACKPOT_POOL} руб.\n"
            f"• 5 геометок в радиусе 100 м\n\n"
            "Хотите попробовать удачу?"
        )
        
        keyboard = [
            [InlineKeyboardButton("💳 Внести депозит", callback_data='make_deposit')],
            [InlineKeyboardButton("💰 Мой баланс", callback_data='check_balance')],
            [InlineKeyboardButton("🔙 Назад", callback_data='choose_mode')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(payment_text, reply_markup=reply_markup)
        return
    
    # Проверяем лимит игр
    if not can_play_game(user.id):
        limit_text = (
            f"❌ Вы исчерпали лимит игр на сегодня ({RESPONSIBLE_GAMING_LIMITS['daily_games_limit']} игр/день).\n\n"
            "Попробуйте завтра или пригласите друзей,\n"
            "чтобы получить дополнительные игры!"
        )
        await query.edit_message_text(limit_text, reply_markup=get_back_keyboard())
        return
    
    # Списание средств и начало игры
    user_balances[user.id] -= mode_config['entry_fee']
    log_transaction(user.id, -mode_config['entry_fee'], f"game_entry_{game_mode}")
    log_game_played(user.id)
    
    # Обновляем глобальную статистику
    global_stats['total_games'] += 1
    global_stats['active_players'].add(user.id)
    
    start_game_text = (
        f"Отлично! Выбран режим {mode_config['name']}\n"
        f"С вашего счета списано {mode_config['entry_fee']} руб.\n"
        "Для начала игры мне нужна твоя текущая геопозиция. "
        "Выбери способ передачи геопозиции:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📍 Включить трансляцию", callback_data='start_live_location')],
        [InlineKeyboardButton("📎 Отправить вручную", callback_data='send_location')],
        [InlineKeyboardButton("🔙 Назад", callback_data='choose_mode')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(start_game_text, reply_markup=reply_markup)
    
    # Сохраняем выбранный режим в контексте
    context.user_data['selected_mode'] = game_mode

async def handle_deposit(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    deposit_text = (
        "Выберите сумму депозита:\n\n"
        "💎 При пополнении от 50 руб. - бонус 5 руб.! \n"
        "💎 При пополнении от 100 руб. - бонус 15 руб.!"
    )
    
    await query.edit_message_text(
        deposit_text,
        reply_markup=get_deposit_keyboard()
    )

async def process_deposit(update: Update, context: CallbackContext, amount: int) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    bonus = 0
    if amount == 50:
        bonus = 5
    elif amount == 100:
        bonus = 15
    
    user_balances[user.id] = user_balances.get(user.id, 0) + amount + bonus
    log_transaction(user.id, amount + bonus, "deposit")
    
    deposit_text = (
        f"✅ Счет успешно пополнен на {amount} руб.\n"
    )
    
    if bonus > 0:
        deposit_text += f"🎁 Получен бонус: {bonus} руб.\n"
    
    deposit_text += (
        f"💰 Текущий баланс: {user_balances[user.id]} руб.\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎮 Начать игру", callback_data='choose_mode')],
        [InlineKeyboardButton("💰 Мой баланс", callback_data='check_balance')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')],
    ]
    
    await query.edit_message_text(
        deposit_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_balance(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    balance = user_balances.get(user.id, 0)
    games_today = DAILY_STATS.get(date.today(), {}).get(user.id, {}).get('games_played', 0) if date.today() in DAILY_STATS and user.id in DAILY_STATS[date.today()] else 0
    
    balance_text = (
        f"💰 Ваш баланс: {balance} руб.\n"
        f"📅 Игр сегодня: {games_today}/{RESPONSIBLE_GAMING_LIMITS['daily_games_limit']}\n\n"
        "Доступные режимы:\n"
    )
    
    # Показываем, сколько игр доступно в каждом режиме
    for mode, config in GAME_MODES.items():
        games_available = balance // config['entry_fee']
        balance_text += f"{config['name']}: {games_available} игр\n"
    
    balance_text += "\nИстория транзакций:\n"
    
    # Добавляем историю транзакций
    user_transactions = transactions.get(user.id, [])
    if user_transactions:
        for transaction in user_transactions[-5:]:
            sign = "+" if transaction['amount'] > 0 else ""
            balance_text += f"• {transaction['date']}: {sign}{transaction['amount']} руб. ({transaction['type']})\n"
    else:
        balance_text += "История транзакций пуста\n"
    
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='make_deposit')],
        [InlineKeyboardButton("🎮 Начать игру", callback_data='choose_mode')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')],
    ]
    
    await query.edit_message_text(
        balance_text,
        reply_mup=InlineKeyboardMarkup(keyboard)
    )

async def invite_friends(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    referral_link = f"https://t.me/{(await context.bot.get_me()).username}?start=ref{user.id}"
    
    referral_text = (
        "👥 Пригласи друзей и получай бонусы!\n\n"
        f"Твоя реферальная ссылка: {referral_link}\n\n"
        "За каждого приглашенного друга:\n"
        "• Ты получаешь 5 руб.\n"
        "• Друг получает +1 бесплатную игру\n"
        "• Растем вместе! 🚀"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')],
    ]
    
    await query.edit_message_text(
        referral_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_live_location(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    instructions = (
        "📡 Как включить трансляцию геопозиции:\n\n"
        "1. Откройте меню вложения (кнопка 📎)\n"
        "2. Выберите 'Геопозиция'\n"
        "3. Нажмите 'Транслировать мою геопозицию'\n"
        "4. Выберите время трансляции\n"
        "5. Нажмите 'Поделиться'\n\n"
        "Я буду автоматически отслеживать ваше перемещение!"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Я включил трансляцию", callback_data='confirm_live')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_game')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(instructions, reply_markup=reply_markup)

async def confirm_live_location(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    # Если игра уже начата, просто обновляем статус
    if user.id in games:
        game = games[user.id]
        game.live_location_active = True
        response = "✅ Трансляция геопозиции активирована! Начинайте поиск!"
        logger.info(f"Live location activated for user {user.id}")
    else:
        # Создаем временную игру
        response = "⚠️ Сначала начните игру, отправив геопозицию!"
        await query.edit_message_text(response, reply_markup=get_main_menu_keyboard())
        return
    
    await query.edit_message_text(response, reply_markup=get_live_location_keyboard())

async def stop_live_location(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    if user.id in games:
        games[user.id].live_location_active = False
        response = "⏹ Трансляция геопозиции остановлена."
        logger.info(f"Live location stopped for user {user.id}")
    else:
        response = "❌ У вас нет активной игры."
    
    await query.edit_message_text(response, reply_markup=get_game_keyboard())

async def handle_location(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    message = update.effective_message
    
    if not message or not message.location:
        logger.warning("Location update without valid message or location data")
        return
        
    location = message.location
    user_coords = (location.latitude, location.longitude)
    logger.info(f"Received location update from user {user.id}: {user_coords}")
    
    # Получаем выбранный режим из контекста
    selected_mode = context.user_data.get('selected_mode', 'standard')
    mode_config = GAME_MODES[selected_mode]
    
    # Сохраняем последнее местоположение
    context.user_data['last_location'] = user_coords
    
    # Если это первое сообщение с геопозицией - начинаем игру
    if user.id not in games:
        game = GeoGame(user.id, location.latitude, location.longitude, selected_mode)
        games[user.id] = game
        action = "начата"
    else:
        game = games[user.id]
        action = "обновлена"
        game.last_update = datetime.now()
    
    # Формирование ссылки на карту
    yandex_map_url = (
        f"https://static-maps.yandex.ru/1.x/?ll={location.longitude},{location.latitude}"
        f"&size=650,450"
        f"&z=17"
        f"&l=map"
        f"&pt={location.longitude},{location.latitude},pm2rdl"
    )
    
    # Добавляем метки геометок
    for i, spot in enumerate(game.geospots):
        lat, lon = spot['coords']
        color = "pm2gnl" if not spot['found'] else "pm2bll"
        yandex_map_url += f"~{lon},{lat},{color}{i+1}"
    
    response_text = (
        f"🎉 Игра {action}! 🎉\n\n"
        f"Режим: {mode_config['name']}\n"
        f"В радиусе {SEARCH_RADIUS} м от тебя спрятаны {len(game.geospots)} геометок.\n"
        f"Из них {sum(1 for s in game.geospots if s['has_prize'])} содержат призы!\n\n"
        f"<a href='{yandex_map_url}'>🗺️ Посмотреть карту с метками</a>\n\n"
        "Начинай поиск! Я буду сообщать, когда ты приблизишься к метке."
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=response_text,
        parse_mode='HTML',
        reply_markup=get_game_keyboard()
    )
    
    # Если включена трансляция, сразу проверяем позицию
    if game.live_location_active:
        logger.info("Checking proximity immediately after location update")
        await check_proximity_and_respond(update, context, user_coords, game)

async def handle_live_location(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    message = update.effective_message

    if not message or not message.location:
        logger.warning("Live location update without valid message or location data")
        return

    location = message.location
    user_coords = (location.latitude, location.longitude)
    
    # Сохраняем последнее местоположение
    context.user_data['last_location'] = user_coords
    
    logger.info(f"Received live location from user {user.id}: {user_coords}")

    if user.id not in games:
        logger.warning(f"No active game for user: {user.id}")
        return

    game = games[user.id]
    
    # АКТИВИРУЕМ трансляцию автоматически при получении live location!
    if not game.live_location_active:
        game.live_location_active = True
        logger.info(f"Auto-activated live location for user {user.id}")
    
    logger.info(f"Game found for user: {user.id}, live status: {game.live_location_active}")

    # Проверяем близость к геометкам
    logger.info("Checking proximity for live location...")
    await check_proximity_and_respond(update, context, user_coords, game)
    
    

async def check_proximity_and_respond(update: Update, context: CallbackContext, 
                                     user_coords: tuple, game: GeoGame) -> None:
    """Проверка близости и отправка уведомления"""
    proximity_results = game.check_proximity(user_coords)
    
    if not proximity_results:
        logger.info("No proximity results")
        return
    
    for result in proximity_results:
        spot = result['spot']
        distance = result['distance']
        progress = result['progress']
        
        spot_id = id(spot)
        last_progress = game.last_proximity_check.get(spot_id, 0)
        
        if abs(progress - last_progress) < 10 and not result['is_close']:
            logger.info(f"Progress for spot didn't change significantly ({progress} vs {last_progress})")
            continue
            
        game.last_proximity_check[spot_id] = progress
        
        if result['is_close']:
            # Удаляем сообщение о прогрессе, если оно есть
            if 'progress_message_id' in context.user_data:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['progress_message_id']
                    )
                except Exception as e:
                    logger.error(f"Error deleting progress message: {e}")
                del context.user_data['progress_message_id']
            
            # Проверяем, не найдена ли уже эта метка
            if spot['found']:
                continue
                
            spot['found'] = True
            game.found_spots.append(spot)
            
            prize = 0
            message_text = ""
            jackpot_won = False

            # Проверяем джекпот
            if random.random() < JACKPOT_PROBABILITY:
                jackpot_won = True
                prize = JACKPOT_POOL
                JACKPOT_POOL = 100
                global_stats['jackpot_wins'] += 1
                logger.info(f"JACKPOT WON! User {game.user_id} won {prize} rubles!")
                user_balances[game.user_id] += prize
                log_transaction(game.user_id, prize, "jackpot_won")
                message_text = random.choice(JACKPOT_MESSAGES).format(prize=prize)
                message_text += f"\n\n💰 Твой баланс: {user_balances[game.user_id]} руб.!"
                message_text += "\n\n🎆 Это невероятная удача! 🎆"

            elif spot['has_prize']:
                prize = spot['prize_amount']
                user_balances[game.user_id] += prize
                log_transaction(game.user_id, prize, "prize_won")
                message_text = random.choice(WIN_MESSAGES).format(prize=prize)
                message_text += f"\n\n💰 Твой баланс: {user_balances[game.user_id]} руб.!"
                message_text += "\n\n🎯 Продолжай в том же духе!"

                # Обновляем статистику пользователя
                if game.user_id in user_stats:
                    user_stats[game.user_id]['prizes_won'] = user_stats[game.user_id].get('prizes_won', 0) + 1
                    user_stats[game.user_id]['xp'] = user_stats[game.user_id].get('xp', 0) + XP_PER_WIN

            else:
                prize = 0
                message_text = random.choice(EMPTY_MESSAGES)
                near_miss = generate_near_miss()
                if near_miss:
                    message_text += f"\n\n💫 {near_miss}"

            if jackpot_won and game.user_id in user_stats:
                user_stats[game.user_id]['prizes_won'] = user_stats[game.user_id].get('prizes_won', 0) + 1
                user_stats[game.user_id]['xp'] = user_stats[game.user_id].get('xp', 0) + XP_PER_WIN

            # Отправляем эффектное сообщение о находке
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message_text,
                    parse_mode='HTML',
                    reply_markup=get_live_location_keyboard()
                )
                logger.info(f"Message sent to user {game.user_id}: {message_text}")
            except Exception as e:
                logger.error(f"Failed to send message to user {game.user_id}: {e}")

            if prize > 0:
                await check_achievements(update, context, game.user_id, "prize_won")
                
            # После обработки находки прерываем цикл, чтобы избежать множественных сообщений
            break
            
        else:
            # Код для отображения прогресса
            progress_bar = "🟩" * (progress // 10) + "⬜️" * (10 - progress // 10)
            
            progress_text = (
                f"🔔 Ты близко к геометке! 🔔\n"
                f"Расстояние: {distance:.1f} м\n"
                f"Прогресс: {progress_bar} {progress}%"
            )
            
            if 'progress_message_id' in context.user_data:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['progress_message_id'],
                        text=progress_text,
                        reply_markup=get_live_location_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Error editing progress message: {e}")
                    msg = await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=progress_text,
                        reply_markup=get_live_location_keyboard()
                    )
                    context.user_data['progress_message_id'] = msg.message_id
            else:
                msg = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=progress_text,
                    reply_markup=get_live_location_keyboard()
                )
                context.user_data['progress_message_id'] = msg.message_id
    
    # Проверка завершения игры
    if len(game.found_spots) == len(game.geospots):
        prize_count = len([s for s in game.found_spots if s['has_prize']])
        total_prize = sum(s['prize_amount'] for s in game.found_spots if s['has_prize'])
        game_time = datetime.now() - game.start_time
        
        completion_text = (
            "🏆 ТЫ НАШЕЛ ВСЕ ГЕОМЕТКИ! 🏆\n\n"
            f"Режим: {game.mode_config['name']}\n"
            f"Общее время: {game_time.seconds // 60} мин {game_time.seconds % 60} сек\n"
            f"Найденные призы: {prize_count}\n"
            f"Сумма выигрыша: {total_prize} руб.\n\n"
            "Хочешь сыграть еще раз?"
        )
        
        if 'progress_message_id' in context.user_data:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['progress_message_id']
                )
            except Exception as e:
                logger.error(f"Error deleting progress message: {e}")
            del context.user_data['progress_message_id']
        
        user_id = game.user_id
        del games[user_id]
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=completion_text,
            reply_markup=get_main_menu_keyboard()
        )
        
        
        
async def handle_text(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    if user.id in games:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Используйте кнопки для управления игрой:",
            reply_markup=get_game_keyboard()
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Привет! Я бот для поиска геометок. Начни игру с помощью /start",
            reply_markup=get_main_menu_keyboard()
        )
        
# ========== ОБРАБОТЧИКИ ==========
# ... другие обработчики ...

async def web_app_data(update: Update, context: CallbackContext) -> None:
    """Обработка данных из Web App"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        user = update.effective_user
        action = data.get('action')
        
        if action == 'start_game':
            # Обработка начала игры из Web App
            game_mode = data.get('mode', 'standard')
            lat = data.get('lat')
            lon = data.get('lon')
            
            # Проверяем баланс
            mode_config = GAME_MODES[game_mode]
            if user.id not in user_balances or user_balances[user.id] < mode_config['entry_fee']:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Недостаточно средств для игры в режиме {mode_config['name']}",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Создаем игру
            game = GeoGame(user.id, lat, lon, game_mode)
            games[user.id] = game
            
            # Подготавливаем данные для отправки в Web App
            geospots_data = []
            for i, spot in enumerate(game.geospots):
                geospots_data.append({
                    'id': i,
                    'lat': spot['coords'][0],
                    'lon': spot['coords'][1],
                    'has_prize': spot['has_prize'],
                    'prize_amount': spot['prize_amount']
                })
            
            # Отправляем данные обратно в Web App
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=json.dumps({
                    'status': 'success',
                    'game_data': {
                        'geospots': geospots_data,
                        'center': [lat, lon],
                        'radius': SEARCH_RADIUS
                    }
                }),
                parse_mode='HTML'
            )
            
        elif action == 'found_spot':
            # Обработка найденной геометки
            spot_id = data.get('spot_id')
            if user.id in games:
                game = games[user.id]
                if 0 <= spot_id < len(game.geospots) and not game.geospots[spot_id]['found']:
                    game.geospots[spot_id]['found'] = True
                    game.found_spots.append(game.geospots[spot_id])
                    
                    # Начисляем приз, если есть
                    if game.geospots[spot_id]['has_prize']:
                        prize = game.geospots[spot_id]['prize_amount']
                        user_balances[user.id] += prize
                        log_transaction(user.id, prize, "prize_won")
                        
                        # Отправляем уведомление о выигрыше
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"🎉 Поздравляем! Вы нашли геометку с призом {prize} руб.!",
                            reply_markup=get_main_menu_keyboard()
                        )
    
    except Exception as e:
        logger.error(f"Error processing web app data: {e}")
# ... остальные обработчики ...

async def user_stats(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    if user.id not in games:
        stats_text = "У тебя нет активной игры. Начни новую игру!"
        await query.edit_message_text(stats_text, reply_markup=get_back_keyboard())
        return
    
    game = games[user.id]
    found = len(game.found_spots)
    total = len(game.geospots)
    time_elapsed = datetime.now() - game.start_time
    prize_count = len([s for s in game.found_spots if s['has_prize']])
    total_prize = sum(s['prize_amount'] for s in game.found_spots if s['has_prize'])
    
    stats_text = (
        "📊 Твоя статистика:\n\n"
        f"Режим: {game.mode_config['name']}\n"
        f"🔍 Найдено геометок: {found}/{total}\n"
        f"🎁 Найдено призов: {prize_count}\n"
        f"💰 Сумма выигрыша: {total_prize} руб.\n"
        f"⏱ Время игры: {time_elapsed.seconds // 60} мин {time_elapsed.seconds % 60} сек\n\n"
        f"📍 Центр поиска: {game.center[0]:.5f}, {game.center[1]:.5f}"
    )
    
    await query.edit_message_text(stats_text, reply_markup=get_back_keyboard())

async def cancel_game(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    if user.id in games:
        game = games[user.id]
        found = len(game.found_spots)
        total = len(game.geospots)
        prize_count = len([s for s in game.found_spots if s['has_prize']])
        total_prize = sum(s['prize_amount'] for s in game.found_spots if s['has_prize'])
        
        del games[user.id]
        response = (
            "❌ Игра завершена досрочно!\n\n"
            f"Режим: {game.mode_config['name']}\n"
            f"🔍 Ты нашел {found} из {total} геометок\n"
            f"🎁 Призов найдено: {prize_count}\n"
            f"💰 Сумма выигрыша: {total_prize} руб.\n\n"
            "Можешь начать новую игру в любое время!"
        )
        logger.info(f"Game canceled for user {user.id}")
    else:
        response = "У тебя нет активной игры."
    
    await query.edit_message_text(response, reply_markup=get_main_menu_keyboard())


async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    
    if data == 'choose_mode':
        await choose_mode(update, context)
    elif data.startswith('mode_'):
        mode = data.split('_')[1]
        await start_game(update, context, mode)
    elif data == 'show_rules':
        await rules(update, context)
    elif data == 'user_stats':
        await user_stats(update, context)
    elif data == 'make_deposit':
        await handle_deposit(update, context)
    elif data == 'check_balance':
        await handle_balance(update, context)
    elif data == 'invite_friends':
        await invite_friends(update, context)
    elif data == 'deposit_15':
        await process_deposit(update, context, 15)
    elif data == 'deposit_50':
        await process_deposit(update, context, 50)
    elif data == 'deposit_100':
        await process_deposit(update, context, 100)
    elif data == 'cancel_game':
        await cancel_game(update, context)
    elif data == 'main_menu':
        await main_menu(update, context)
    elif data == 'send_location':
        await send_location_prompt(update, context)
    elif data == 'start_live_location':
        await start_live_location(update, context)
    elif data == 'stop_live_location':
        await stop_live_location(update, context)
    elif data == 'confirm_live':
        await confirm_live_location(update, context)
    elif data == 'back_to_game':
        # Возврат к игре после выбора режима
        if 'selected_mode' in context.user_data:
            mode = context.user_data['selected_mode']
            await start_game(update, context, mode)
        else:
            await choose_mode(update, context)

async def main_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Выбери действие:", reply_markup=get_main_menu_keyboard())

async def send_location_prompt(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Пожалуйста, отправь свою текущую геопозицию через меню Telegram:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_game')]
        ])
    )

async def admin_stats(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) != ADMIN_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Эта команда только для администратора"
        )
        return
    
    # Рассчитываем фактическое преимущество казино
    if global_stats['total_deposits'] > 0:
        house_edge_actual = (global_stats['total_deposits'] - global_stats['total_prizes']) / global_stats['total_deposits']
    else:
        house_edge_actual = 0
    
    stats_text = (
        f"📊 Админ-статистика GeoHunter:\n\n"
        f"• Активных игр: {len(games)}\n"
        f"• Уникальных игроков: {len(global_stats['active_players'])}\n"
        f"• Всего игр: {global_stats['total_games']}\n"
        f"• Общие депозиты: {global_stats['total_deposits']} руб.\n"
        f"• Общие выигрыши: {global_stats['total_prizes']} руб.\n"
        f"• Доход: {global_stats['total_revenue']} руб.\n"
        f"• Фактическое преимущество: {house_edge_actual:.2%}\n"
        f"• Размер джекпота: {JACKPOT_POOL} руб.\n"
        f"• Выигрышей джекпота: {global_stats['jackpot_wins']}\n\n"
        f"Текущие игры:\n"
    )
    
    for user_id, game in games.items():
        found = len(game.found_spots)
        total = len(game.geospots)
        time_elapsed = datetime.now() - game.start_time
        live_status = "✅" if game.live_location_active else "❌"
        stats_text += (
            f"👤 Пользователь: {user_id}\n"
            f"🎮 Режим: {game.mode_config['name']}\n"
            f"🔍 Найдено: {found}/{total}\n"
            f"⏱ Время: {time_elapsed.seconds // 60} мин\n"
            f"📍 Трансляция: {live_status}\n"
            f"📍 Центр: {game.center[0]:.5f}, {game.center[1]:.5f}\n\n"
        )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=stats_text
    )

async def force_check(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    if user.id not in games:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="У вас нет активной игры"
        )
        return
        
    game = games[user.id]
    
    # Получаем последнее известное местоположение
    if not hasattr(context, 'user_data') or 'last_location' not in context.user_data:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Нет информации о вашем местоположении"
        )
        return
        
    user_coords = context.user_data['last_location']
    logger.info(f"Force check for user at {user_coords}")
    
    await check_proximity_and_respond(update, context, user_coords, game)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Проверка расстояния выполнена"
    )

async def check_jackpot(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    jackpot_text = (
        f"🎰 ТЕКУЩИЙ ДЖЕКПОТ: {JACKPOT_POOL} руб.! 🎰\n\n"
        f"Шанс выигрыша: {JACKPOT_PROBABILITY*100}%\n"
        "Джекпот растет с каждой игрой!\n\n"
        "Для участия в розыгрыше джекпота\n"
        "просто играйте в любом режиме!"
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=jackpot_text
    )

async def handle_withdraw(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    balance = user_balances.get(user.id, 0)
    
    if balance < 50:
        withdraw_text = (
            f"❌ Минимальная сумма для вывода: 50 руб.\n"
            f"💰 Ваш текущий баланс: {balance} руб.\n\n"
            "Продолжайте играть, чтобы накопить нужную сумму!"
        )
        
        await query.edit_message_text(withdraw_text, reply_markup=get_back_keyboard())
        return
    
    # Здесь должна быть интеграция с платежной системой
    # Для демо-режима просто обнуляем баланс
    
    user_balances[user.id] = 0
    log_transaction(user.id, -balance, "withdrawal")
    
    withdraw_text = (
        f"✅ Запрос на вывод {balance} руб. принят!\n\n"
        "Обычно обработка занимает до 24 часов.\n"
        "Средства поступят на ваш счет в течение\n"
        "рабочего дня после подтверждения."
    )
    
    await query.edit_message_text(withdraw_text, reply_markup=get_main_menu_keyboard())

async def daily_bonus(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    
    # Инициализация статистики пользователя, если не существует
    if user.id not in user_stats:
        user_stats[user.id] = {'level': 1, 'xp': 0, 'games_played': 0, 'prizes_won': 0, 'last_bonus_date': None}
    
    # Инициализация баланса, если не существует
    if user.id not in user_balances:
        user_balances[user.id] = 0
    
    # Проверяем, получал ли пользователь бонус сегодня
    today = date.today()
    last_bonus_date = user_stats[user.id].get('last_bonus_date')
    
    if last_bonus_date == today:
        bonus_text = "❌ Вы уже получали ежедневный бонус сегодня. Приходите завтра!"
    else:
        # Начисляем бонус
        bonus_amount = random.randint(3, 10)
        user_balances[user.id] += bonus_amount
        log_transaction(user.id, bonus_amount, "daily_bonus")
        
        user_stats[user.id]['last_bonus_date'] = today
        
        bonus_text = (
            f"🎁 Ежедневный бонус: {bonus_amount} руб.! 🎁\n\n"
            f"💰 Ваш баланс: {user_balances[user.id]} руб.\n"
            "Возвращайтесь завтра за новым бонусом!"
        )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=bonus_text
    )

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("check", force_check))
    application.add_handler(CommandHandler("jackpot", check_jackpot))
    application.add_handler(CommandHandler("withdraw", handle_withdraw))
    application.add_handler(CommandHandler("bonus", daily_bonus))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Обработка геопозиции
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    # Обработка живой геопозиции
    application.add_handler(MessageHandler(filters.LOCATION, handle_live_location))
    
    # Обработка данных из Web App - ДОБАВЬТЕ ЭТУ СТРОЧКУ
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    

    # Запуск бота
    logger.info("Бот запущен и работает...")
    application.run_polling()

if __name__ == '__main__':
    main()