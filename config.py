import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Базовая конфигурация приложения"""

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-only-for-local-testing')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///company.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # File uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(__file__), 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'txt', 'zip', 'jpg', 'png'}

    # Admin
    BASIC_AUTH_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    BASIC_AUTH_PASSWORD = os.getenv('ADMIN_PASSWORD', 'changeme')
    BASIC_AUTH_FORCE = False

    # Telegram
    TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
    TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')

    # Debug mode
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

    # Logging
    LOG_TO_STDOUT = os.getenv('LOG_TO_STDOUT', 'False').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
