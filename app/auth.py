"""
用户认证系统
包含登录、注册、VIP管理功能
增强安全性：输入验证、限流、事务保护
"""

import sqlite3
import hashlib
import secrets
import os
import re
import logging
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE = os.path.join(BASE_DIR, 'users.db')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoginRateLimiter:
    """登录限流器"""
    def __init__(self, max_attempts=5, window_seconds=300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts = {}
    
    def is_rate_limited(self, identifier):
        """检查是否被限流"""
        now = time.time()
        if identifier in self.attempts:
            attempts = [t for t in self.attempts[identifier] if now - t < self.window_seconds]
            self.attempts[identifier] = attempts
            return len(attempts) >= self.max_attempts
        return False
    
    def record_attempt(self, identifier):
        """记录一次登录尝试"""
        now = time.time()
        if identifier not in self.attempts:
            self.attempts[identifier] = []
        self.attempts[identifier].append(now)
    
    def reset_attempts(self, identifier):
        """重置登录尝试次数"""
        if identifier in self.attempts:
            del self.attempts[identifier]


rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=300)


def get_db():
    """获取数据库连接（使用上下文管理器）"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
    return db


def close_db(e=None):
    """关闭数据库连接"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """初始化数据库"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_vip INTEGER DEFAULT 0,
            vip_expires TIMESTAMP,
            points INTEGER DEFAULT 100,
            use_count INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def validate_username(username):
    """验证用户名格式"""
    if not username or not isinstance(username, str):
        return False, "用户名不能为空"
    
    username = username.strip()
    
    if len(username) < 3:
        return False, "用户名至少3个字符"
    
    if len(username) > 50:
        return False, "用户名最多50个字符"
    
    if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff]+$', username):
        return False, "用户名只能包含字母、数字、下划线和中文"
    
    return True, username


def validate_email(email):
    """验证邮箱格式"""
    if not email or not isinstance(email, str):
        return False, "邮箱不能为空"
    
    email = email.strip()
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "邮箱格式不正确"
    
    if len(email) > 100:
        return False, "邮箱最多100个字符"
    
    return True, email


def validate_password(password):
    """验证密码强度"""
    if not password or not isinstance(password, str):
        return False, "密码不能为空"
    
    if len(password) < 6:
        return False, "密码至少6个字符"
    
    if len(password) > 128:
        return False, "密码最多128个字符"
    
    return True, password


def hash_password(password, salt):
    """哈希密码"""
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()


def create_user(username, email, password):
    """创建用户"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    c = conn.cursor()
    
    try:
        salt = secrets.token_hex(16)
        password_hash = hash_password(password, salt)
        
        c.execute('''
            INSERT INTO users (username, email, password_hash, salt)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, salt))
        conn.commit()
        user_id = c.lastrowid
        logger.info(f"User created: {username}")
        return user_id
    except sqlite3.IntegrityError as e:
        logger.warning(f"Registration failed - duplicate: {username}")
        return None
    finally:
        conn.close()


def verify_user(username, password):
    """验证用户"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute('SELECT id, username, email, password_hash, salt, is_vip, points, use_count FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        
        if not user:
            return None
        
        pwd_hash = hash_password(password, user['salt'])
        
        if user['password_hash'] != pwd_hash:
            return None
        
        return {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'is_vip': user['is_vip'],
            'points': user['points'],
            'use_count': user['use_count']
        }
    finally:
        conn.close()


def log_login_attempt(username, ip_address, success):
    """记录登录尝试"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    c = conn.cursor()
    try:
        c.execute(
            'INSERT INTO login_attempts (username, ip_address, success) VALUES (?, ?, ?)',
            (username, ip_address, 1 if success else 0)
        )
        conn.commit()
    finally:
        conn.close()


def update_last_login(user_id):
    """更新最后登录时间"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    c = conn.cursor()
    try:
        c.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        conn.commit()
    finally:
        conn.close()


def check_vip(user_id):
    """检查VIP状态"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute('SELECT is_vip, vip_expires FROM users WHERE id = ?', (user_id,))
        row = c.fetchone()
        
        if not row or not row['is_vip']:
            return False
        
        if not row['vip_expires']:
            return False
        
        try:
            expires = datetime.fromisoformat(row['vip_expires'])
            return datetime.now() < expires
        except ValueError as e:
            logger.error(f"Invalid VIP expiry format for user {user_id}: {e}")
            return False
    finally:
        conn.close()


def use_points(user_id, points):
    """使用积分（带事务保护）"""
    if points <= 0:
        return False
    
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        conn.execute('BEGIN IMMEDIATE')
        
        c.execute('SELECT points FROM users WHERE id = ?', (user_id,))
        row = c.fetchone()
        
        if not row:
            conn.rollback()
            return False
        
        current_points = row['points']
        
        if current_points < points:
            conn.rollback()
            logger.warning(f"Insufficient points for user {user_id}: have {current_points}, need {points}")
            return False
        
        c.execute('UPDATE users SET points = points - ?, use_count = use_count + 1 WHERE id = ?', 
                 (points, user_id))
        
        conn.commit()
        logger.info(f"Points deducted for user {user_id}: -{points}")
        return True
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error using points for user {user_id}: {e}")
        return False
    finally:
        conn.close()


def add_points(user_id, points):
    """增加积分"""
    if points <= 0:
        return False
    
    conn = sqlite3.connect(DATABASE, timeout=10)
    c = conn.cursor()
    
    try:
        c.execute('UPDATE users SET points = points + ? WHERE id = ?', (points, user_id))
        conn.commit()
        logger.info(f"Points added for user {user_id}: +{points}")
        return True
    except Exception as e:
        logger.error(f"Error adding points for user {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_client_ip():
    """获取客户端IP"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'message': '请求数据无效'}), 400
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    valid_username, username_msg = validate_username(username)
    if not valid_username:
        return jsonify({'success': False, 'message': username_msg}), 400
    
    valid_email, email_msg = validate_email(email)
    if not valid_email:
        return jsonify({'success': False, 'message': email_msg}), 400
    
    valid_password, password_msg = validate_password(password)
    if not valid_password:
        return jsonify({'success': False, 'message': password_msg}), 400
    
    user_id = create_user(username, email_msg, password)
    
    if user_id:
        return jsonify({
            'success': True,
            'message': '注册成功',
            'data': {
                'user_id': user_id,
                'username': username,
                'points': 100
            }
        }), 201
    else:
        return jsonify({'success': False, 'message': '用户名或邮箱已存在'}), 400


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    client_ip = get_client_ip()
    
    if rate_limiter.is_rate_limited(client_ip):
        logger.warning(f"Rate limited IP: {client_ip}")
        return jsonify({
            'success': False, 
            'message': '登录尝试过于频繁，请5分钟后再试'
        }), 429
    
    data = request.get_json()
    
    if not data:
        rate_limiter.record_attempt(client_ip)
        return jsonify({'success': False, 'message': '请求数据无效'}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        rate_limiter.record_attempt(client_ip)
        return jsonify({'success': False, 'message': '请填写用户名和密码'}), 400
    
    valid_username, _ = validate_username(username)
    if not valid_username:
        rate_limiter.record_attempt(client_ip)
        return jsonify({'success': False, 'message': '用户名格式不正确'}), 400
    
    user = verify_user(username, password)
    
    if user:
        rate_limiter.reset_attempts(client_ip)
        update_last_login(user['id'])
        log_login_attempt(username, client_ip, True)
        is_vip = check_vip(user['id'])
        
        logger.info(f"User logged in: {username}")
        
        return jsonify({
            'success': True,
            'message': '登录成功',
            'data': {
                'user_id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'is_vip': is_vip,
                'points': user['points'],
                'use_count': user['use_count']
            }
        }), 200
    else:
        rate_limiter.record_attempt(client_ip)
        log_login_attempt(username, client_ip, False)
        remaining = rate_limiter.max_attempts - len([t for t in rate_limiter.attempts.get(client_ip, []) 
                                                     if time.time() - t < rate_limiter.window_seconds])
        
        logger.warning(f"Failed login attempt for: {username} from {client_ip}")
        
        return jsonify({
            'success': False, 
            'message': f'用户名或密码错误（剩余尝试次数: {remaining}）'
        }), 401


@auth_bp.route('/profile', methods=['GET'])
def get_profile():
    """获取用户信息"""
    user_id = request.headers.get('X-User-ID')
    
    if not user_id:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({'success': False, 'message': '无效的用户ID'}), 400
    
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        c.execute('SELECT id, username, email, is_vip, points, use_count, created_at FROM users WHERE id = ?', (user_id,))
        user = c.fetchone()
        
        if not user:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'is_vip': user['is_vip'],
                'points': user['points'],
                'use_count': user['use_count'],
                'created_at': user['created_at']
            }
        })
    finally:
        conn.close()


@auth_bp.route('/upgrade-vip', methods=['POST'])
def upgrade_vip():
    """升级VIP"""
    user_id = request.headers.get('X-User-ID')
    
    if not user_id:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({'success': False, 'message': '无效的用户ID'}), 400
    
    data = request.get_json() or {}
    days = data.get('days', 30)
    price = data.get('price', 0)
    
    if days <= 0 or days > 365:
        return jsonify({'success': False, 'message': 'VIP天数必须在1-365之间'}), 400
    
    if price > 0:
        if not use_points(user_id, price):
            return jsonify({'success': False, 'message': '积分不足或扣减失败'}), 400
    
    conn = sqlite3.connect(DATABASE, timeout=10)
    c = conn.cursor()
    
    try:
        expires = (datetime.now() + timedelta(days=days)).isoformat()
        c.execute('UPDATE users SET is_vip = 1, vip_expires = ? WHERE id = ?', (expires, user_id))
        conn.commit()
        
        logger.info(f"VIP upgraded for user {user_id}: {days} days")
        
        return jsonify({
            'success': True,
            'message': f'VIP已开通，有效期{days}天'
        })
    except Exception as e:
        logger.error(f"VIP upgrade failed for user {user_id}: {e}")
        return jsonify({'success': False, 'message': 'VIP升级失败'}), 500
    finally:
        conn.close()


@auth_bp.route('/add-points', methods=['POST'])
def add_user_points():
    """增加积分"""
    user_id = request.headers.get('X-User-ID')
    
    if not user_id:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    try:
        user_id = int(user_id)
    except ValueError:
        return jsonify({'success': False, 'message': '无效的用户ID'}), 400
    
    data = request.get_json() or {}
    points = data.get('points', 50)
    
    if points <= 0 or points > 10000:
        return jsonify({'success': False, 'message': '积分数量必须在1-10000之间'}), 400
    
    if add_points(user_id, points):
        return jsonify({
            'success': True,
            'message': f'已获得{points}积分'
        })
    else:
        return jsonify({'success': False, 'message': '增加积分失败'}), 500


@auth_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'success': True,
        'message': 'Auth service is running',
        'data': {
            'rate_limited_ips': len(rate_limiter.attempts),
            'timestamp': datetime.now().isoformat()
        }
    })


init_db()
