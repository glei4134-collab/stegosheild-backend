import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    
    if not SECRET_KEY:
        if os.getenv('FLASK_ENV') == 'production':
            raise ValueError("SECRET_KEY environment variable must be set in production")
        SECRET_KEY = secrets.token_hex(32)
        print(f"WARNING: Using generated SECRET_KEY for development: {SECRET_KEY[:8]}...")

    SALT_ROUNDS = int(os.getenv('SALT_ROUNDS', '100000'))

    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')

    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')
    
    if CORS_ORIGINS == '*' and not DEBUG:
        CORS_ORIGINS = ''

    @staticmethod
    def init_app():
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '')
    
    _SECRET_KEY = os.getenv('SECRET_KEY')
    
    @property
    def SECRET_KEY(self):
        if not self._SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable must be set in production")
        return self._SECRET_KEY
    
    @SECRET_KEY.setter
    def SECRET_KEY(self, value):
        self._SECRET_KEY = value


class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
