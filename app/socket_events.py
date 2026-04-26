from flask_socketio import emit, join_room, leave_room
from app import socketio

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected', {'status': 'ok', 'message': 'Connected to StegoShield WebSocket'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('join_admin')
def handle_join_admin(data):
    print(f'Admin joined: {data}')
    join_room('admin')
    emit('joined', {'room': 'admin', 'status': 'ok'})

@socketio.on('leave_admin')
def handle_leave_admin(data):
    leave_room('admin')
    emit('left', {'room': 'admin', 'status': 'ok'})

def broadcast_key_generated(keys):
    """广播密钥生成事件"""
    socketio.emit('key_generated', {
        'keys': keys,
        'action': 'generate'
    }, room='admin')

def broadcast_key_activated(key, username, days):
    """广播密钥激活事件"""
    socketio.emit('key_activated', {
        'key': key,
        'username': username,
        'days': days,
        'action': 'activate'
    }, room='admin')

def broadcast_stats_update(stats):
    """广播统计更新"""
    socketio.emit('stats_updated', stats, room='admin')
