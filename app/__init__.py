from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
import os

from app.config import Config
from app.errors import StegoError

socketio = SocketIO()

def create_app():
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(Config)

    cors_origins = Config.CORS_ORIGINS if hasattr(Config, 'CORS_ORIGINS') else '*'

    if cors_origins == '*':
        allowed_origins = ['http://127.0.0.1:5001', 'http://localhost:5001', 'http://127.0.0.1:*', 'http://localhost:*']
    else:
        allowed_origins = [origin.strip() for origin in cors_origins.split(',') if origin.strip()]

    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-User-ID"],
            "expose_headers": ["Content-Length", "Content-Type"],
            "supports_credentials": True,
            "max_age": 3600
        }
    })

    Config.init_app()

    from app.routes.stego import stego_bp
    from app.auth import auth_bp
    from app.key_management import key_bp
    app.register_blueprint(stego_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(key_bp)

    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'frontend')

    @app.route('/')
    def index():
        if os.path.exists(frontend_dir):
            frontend_path = os.path.join(frontend_dir, 'index.html')
            if os.path.exists(frontend_path):
                return send_from_directory(frontend_dir, 'index.html')
        return jsonify({
            'status': 'running',
            'service': 'StegoShield Backend',
            'version': '1.1.0',
            'endpoints': {
                'api': '/api/health',
                'auth': '/api/auth',
                'stego': '/api/stego',
                'keys': '/api/key'
            },
            'websocket': '/socket.io'
        })

    @app.route('/test')
    def test():
        return jsonify({
            'status': 'ok',
            'service': 'StegoShield Backend'
        })

    @app.route('/<path:filename>.html')
    def serve_html(filename):
        if '..' in filename or filename.startswith('/'):
            return '<h1>403 Forbidden</h1>', 403
        html_path = os.path.join(frontend_dir, filename + '.html')
        if os.path.exists(html_path):
            return send_from_directory(frontend_dir, filename + '.html')
        return '<h1>404 Not Found</h1>', 404

    @app.route('/simple.html')
    def simple():
        simple_path = os.path.join(frontend_dir, 'simple.html')
        if os.path.exists(simple_path):
            return send_from_directory(frontend_dir, 'simple.html')
        return '<h1>StegoShield</h1>'

    @app.route('/css/<path:filename>')
    def serve_css(filename):
        if '..' in filename or filename.startswith('/'):
            return '<h1>403 Forbidden</h1>', 403
        return send_from_directory(os.path.join(frontend_dir, 'css'), filename)

    @app.errorhandler(StegoError)
    def handle_stego_error(e):
        return jsonify(e.to_dict()), e.status_code

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'NOT_FOUND',
                'message': '资源不存在'
            }
        }), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': '服务器内部错误'
            }
        }), 500

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({
            'success': False,
            'error': {
                'code': 'FORBIDDEN',
                'message': '禁止访问'
            }
        }), 403

    socketio.init_app(app, cors_allowed_origins="*")

    return app
