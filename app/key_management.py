"""
密钥管理系统 - Key Management System
支持密钥生成、验证、绑定、查询

密钥格式: STEGO-{DAYS}-{随机码}
例如: STEGO-365-A7B3C9D4
"""

import sqlite3
import secrets
import string
import hashlib
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from functools import wraps

key_bp = Blueprint('key', __name__, url_prefix='/api/key')

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE = os.environ.get('KEYS_DB_PATH', os.path.join(DATA_DIR, 'keys.db'))

ADMIN_TOKEN = os.environ.get('KMS_ADMIN_TOKEN', 'kms_admin_secret_2024')

init_key_db()

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_key_db():
    """初始化密钥数据库"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE NOT NULL,
            vip_days INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_at TIMESTAMP,
            bound_username TEXT,
            bound_user_id TEXT,
            is_bound INTEGER DEFAULT 0,
            is_revoked INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            mac_address TEXT,
            machine_id TEXT,
            bind_count INTEGER DEFAULT 0,
            use_type TEXT DEFAULT 'fixed',
            bound_expires_at TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS activation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT NOT NULL,
            action TEXT NOT NULL,
            username TEXT,
            machine_id TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def generate_key_code(vip_days: int) -> str:
    """生成密钥码"""
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"STEGO-{vip_days}-{random_part}"

def verify_admin_token(f):
    """验证管理员Token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Admin-Token')
        if not token or token != ADMIN_TOKEN:
            return jsonify({'success': False, 'message': '未授权'}), 401
        return f(*args, **kwargs)
    return decorated

@key_bp.route('/generate', methods=['POST'])
@verify_admin_token
def generate_keys():
    """批量生成密钥"""
    data = request.get_json()

    count = data.get('count', 1)
    vip_days = data.get('days', 365)
    custom_expires_at = data.get('expires_at')
    custom_seconds = data.get('seconds')
    use_type = data.get('use_type', 'fixed')

    if count < 1 or count > 1000:
        return jsonify({'success': False, 'message': '数量必须在1-1000之间'}), 400

    if vip_days < 1 or vip_days > 3650:
        return jsonify({'success': False, 'message': '天数必须在1-3650之间'}), 400

    conn = get_db()
    c = conn.cursor()

    generated_keys = []
    for _ in range(count):
        key_code = generate_key_code(vip_days)

        if use_type == 'usage_days':
            expires_at = None
            vip_days_display = vip_days
        elif custom_expires_at:
            expires_at = custom_expires_at
            vip_days_display = 0
        elif custom_seconds:
            expires_at = datetime.fromtimestamp(custom_seconds).isoformat()
            vip_days_display = int(custom_seconds / 86400)
        else:
            expires_at = (datetime.now() + timedelta(days=vip_days)).isoformat()
            vip_days_display = vip_days

        try:
            c.execute('''
                INSERT INTO keys (key_code, vip_days, expires_at, use_type)
                VALUES (?, ?, ?, ?)
            ''', (key_code, vip_days_display, expires_at, use_type))
            generated_keys.append({
                'key': key_code,
                'days': vip_days_display,
                'expires_at': expires_at if expires_at else f"激活后{vip_days_display}天到期",
                'use_type': use_type
            })
        except sqlite3.IntegrityError:
            continue

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'成功生成{len(generated_keys)}个密钥',
        'keys': generated_keys
    })

@key_bp.route('/validate', methods=['POST'])
def validate_key():
    """
    验证密钥（用于绑定）
    用户激活时调用，需要联网
    """
    data = request.get_json()
    key_code = data.get('key', '').strip().upper()
    username = data.get('username', '').strip()
    machine_id = data.get('machine_id', '')

    if not key_code:
        return jsonify({'success': False, 'message': '密钥不能为空', 'code': 'KEY_EMPTY'}), 400

    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空', 'code': 'USERNAME_EMPTY'}), 400

    conn = get_db()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('SELECT * FROM keys WHERE key_code = ?', (key_code,))
    key_row = c.fetchone()

    if not key_row:
        conn.close()
        return jsonify({'success': False, 'message': '密钥不存在', 'code': 'KEY_NOT_FOUND'}), 404

    if key_row['is_revoked']:
        conn.close()
        return jsonify({'success': False, 'message': '密钥已被撤销', 'code': 'KEY_REVOKED'}), 403

    use_type = key_row['use_type'] or 'fixed'

    if key_row['is_bound'] and key_row['bind_count'] >= 1:
        if key_row['machine_id'] and key_row['machine_id'] != machine_id:
            conn.close()
            return jsonify({
                'success': False,
                'message': '密钥已被其他设备绑定',
                'code': 'KEY_ALREADY_BOUND'
            }), 403

        expires = datetime.fromisoformat(key_row['bound_expires_at'] or key_row['expires_at'])
        if datetime.now() > expires:
            conn.close()
            return jsonify({
                'success': False,
                'message': '密钥已过期',
                'code': 'KEY_EXPIRED',
                'expired_at': key_row['bound_expires_at'] or key_row['expires_at']
            }), 403

        time_left = expires - datetime.now()
        days_left = time_left.days
        seconds_left = int(time_left.total_seconds())
        conn.close()
        return jsonify({
            'success': True,
            'message': f'密钥有效，剩余{days_left}天{time_left.seconds//3600}小时',
            'days': days_left,
            'seconds': seconds_left,
            'expires_at': key_row['bound_expires_at'] or key_row['expires_at'],
            'already_bound': True,
            'bound_username': key_row['bound_username']
        })

    if use_type == 'usage_days':
        expires_at = (datetime.now() + timedelta(days=key_row['vip_days'])).isoformat()
        bound_expires_at = expires_at
    else:
        expires_at = key_row['expires_at'] if key_row['expires_at'] else (datetime.now() + timedelta(days=key_row['vip_days'])).isoformat()
        bound_expires_at = expires_at

    c.execute('''
        UPDATE keys SET
            is_bound = 1,
            used_at = ?,
            bound_username = ?,
            bind_count = bind_count + 1,
            machine_id = ?,
            expires_at = ?,
            bound_expires_at = ?
        WHERE key_code = ?
    ''', (datetime.now().isoformat(), username, machine_id, expires_at, bound_expires_at, key_code))

    c.execute('''
        INSERT INTO activation_logs (key_code, action, username, machine_id, details)
        VALUES (?, ?, ?, ?, ?)
    ''', (key_code, 'BIND', username, machine_id, f'密钥绑定成功，有效期{key_row["vip_days"]}天'))

    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'密钥绑定成功，获得{key_row["vip_days"]}天VIP',
        'days': key_row['vip_days'],
        'expires_at': bound_expires_at,
        'already_bound': False
    })

@key_bp.route('/check', methods=['POST'])
def check_key():
    """
    检查密钥状态（离线验证用）
    返回密钥信息用于本地缓存
    """
    data = request.get_json()
    key_code = data.get('key', '').strip().upper()
    
    if not key_code:
        return jsonify({'success': False, 'message': '密钥不能为空'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM keys WHERE key_code = ?', (key_code,))
    key_row = c.fetchone()
    
    if not key_row:
        conn.close()
        return jsonify({'success': False, 'message': '密钥不存在', 'code': 'KEY_NOT_FOUND'}), 404
    
    conn.close()
    
    is_valid = not key_row['is_revoked']
    is_expired = False
    seconds_left = 0

    try:
        if key_row['expires_at']:
            expires = datetime.fromisoformat(key_row['expires_at'])
            is_expired = datetime.now() > expires
            if is_expired:
                is_valid = False
            else:
                seconds_left = int((expires - datetime.now()).total_seconds())
    except ValueError:
        pass

    return jsonify({
        'success': True,
        'data': {
            'key': key_row['key_code'],
            'days': key_row['vip_days'],
            'seconds': seconds_left,
            'is_bound': bool(key_row['is_bound']),
            'bound_username': key_row['bound_username'],
            'bound_at': key_row['used_at'],
            'expires_at': key_row['expires_at'],
            'is_valid': is_valid and not is_expired,
            'is_revoked': bool(key_row['is_revoked']),
            'is_expired': is_expired
        }
    })

@key_bp.route('/list', methods=['GET'])
@verify_admin_token
def list_keys():
    """列出所有密钥（管理员）"""
    conn = get_db()
    c = conn.cursor()
    
    status = request.args.get('status', 'all')
    
    if status == 'unused':
        c.execute('SELECT * FROM keys WHERE is_bound = 0 AND is_revoked = 0 ORDER BY created_at DESC')
    elif status == 'used':
        c.execute('SELECT * FROM keys WHERE is_bound = 1 ORDER BY used_at DESC')
    elif status == 'revoked':
        c.execute('SELECT * FROM keys WHERE is_revoked = 1 ORDER BY created_at DESC')
    else:
        c.execute('SELECT * FROM keys ORDER BY created_at DESC')
    
    rows = c.fetchall()
    conn.close()
    
    keys = []
    for row in rows:
        keys.append({
            'id': row['id'],
            'key': row['key_code'],
            'days': row['vip_days'],
            'created_at': row['created_at'],
            'is_bound': bool(row['is_bound']),
            'bound_username': row['bound_username'],
            'used_at': row['used_at'],
            'expires_at': row['expires_at'],
            'is_revoked': bool(row['is_revoked'])
        })
    
    return jsonify({
        'success': True,
        'keys': keys,
        'total': len(keys),
        'unused': sum(1 for k in keys if not k['is_bound'] and not k['is_revoked']),
        'used': sum(1 for k in keys if k['is_bound']),
        'revoked': sum(1 for k in keys if k['is_revoked'])
    })

@key_bp.route('/revoke', methods=['POST'])
@verify_admin_token
def revoke_key():
    """撤销密钥"""
    data = request.get_json()
    key_code = data.get('key', '').strip().upper()
    
    if not key_code:
        return jsonify({'success': False, 'message': '密钥不能为空'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('UPDATE keys SET is_revoked = 1 WHERE key_code = ?', (key_code,))
    
    if c.rowcount == 0:
        conn.close()
        return jsonify({'success': False, 'message': '密钥不存在'}), 404
    
    c.execute('''
        INSERT INTO activation_logs (key_code, action, details)
        VALUES (?, ?, ?)
    ''', (key_code, 'REVOKE', '密钥被撤销'))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': '密钥已撤销'})

@key_bp.route('/logs', methods=['GET'])
@verify_admin_token
def get_logs():
    """获取激活日志"""
    conn = get_db()
    c = conn.cursor()
    
    limit = request.args.get('limit', 100, type=int)
    
    c.execute('''
        SELECT * FROM activation_logs
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    rows = c.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append({
            'id': row['id'],
            'key': row['key_code'],
            'action': row['action'],
            'username': row['username'],
            'machine_id': row['machine_id'],
            'timestamp': row['timestamp'],
            'details': row['details']
        })
    
    return jsonify({
        'success': True,
        'logs': logs
    })

@key_bp.route('/stats', methods=['GET'])
@verify_admin_token
def get_stats():
    """获取统计信息"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) as total FROM keys')
    total = c.fetchone()['total']
    
    c.execute('SELECT COUNT(*) as unused FROM keys WHERE is_bound = 0 AND is_revoked = 0')
    unused = c.fetchone()['unused']
    
    c.execute('SELECT COUNT(*) as used FROM keys WHERE is_bound = 1')
    used = c.fetchone()['used']
    
    c.execute('SELECT COUNT(*) as revoked FROM keys WHERE is_revoked = 1')
    revoked = c.fetchone()['revoked']
    
    c.execute('SELECT SUM(vip_days) as total_days FROM keys WHERE is_bound = 1')
    total_days = c.fetchone()['total_days'] or 0
    
    conn.close()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_keys': total,
            'unused_keys': unused,
            'used_keys': used,
            'revoked_keys': revoked,
            'total_vip_days_sold': total_days
        }
    })

init_key_db()
