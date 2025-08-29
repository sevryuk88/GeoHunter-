# database.py
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name='geohunter.db'):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Инициализация таблиц базы данных"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance REAL DEFAULT 0.0,
                language TEXT DEFAULT 'en',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица игр
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                mode TEXT,
                entry_fee REAL,
                prize_won REAL,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица транзакций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                type TEXT,
                status TEXT,
                provider TEXT,
                provider_transaction_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица найденных геоточек
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS found_geospots (
                geospot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER,
                user_id INTEGER,
                has_prize BOOLEAN,
                prize_amount REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games (game_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def get_user(self, user_id):
        """Получить пользователя по ID"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'user_id': user[0],
                'username': user[1],
                'first_name': user[2],
                'last_name': user[3],
                'balance': user[4],
                'language': user[5],
                'created_at': user[6]
            }
        return None
        
    def create_user(self, user_data):
        """Создать нового пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_data.id, user_data.username, user_data.first_name, user_data.last_name))
        conn.commit()
        conn.close()
        
    def update_balance(self, user_id, amount):
        """Обновить баланс пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        
    def get_balance(self, user_id):
        """Получить баланс пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        balance = cursor.fetchone()
        conn.close()
        return balance[0] if balance else 0.0
        
    def create_game(self, user_id, mode, entry_fee):
        """Создать запись об игре"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO games (user_id, mode, entry_fee)
            VALUES (?, ?, ?)
        ''', (user_id, mode, entry_fee))
        game_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return game_id
        
    def update_game_result(self, game_id, prize_won, status='completed'):
        """Обновить результат игры"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE games SET prize_won = ?, status = ? WHERE game_id = ?
        ''', (prize_won, status, game_id))
        conn.commit()
        conn.close()
        
    def add_transaction(self, user_id, amount, transaction_type, status, provider, provider_transaction_id=None):
        """Добавить транзакцию"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, status, provider, provider_transaction_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, transaction_type, status, provider, provider_transaction_id))
        conn.commit()
        conn.close()
        
    def add_found_geospot(self, game_id, user_id, has_prize, prize_amount):
        """Добавить найденную геотоку"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO found_geospots (game_id, user_id, has_prize, prize_amount)
            VALUES (?, ?, ?, ?)
        ''', (game_id, user_id, has_prize, prize_amount))
        conn.commit()
        conn.close()