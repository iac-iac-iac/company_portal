import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logger(app):
    """Настройка логирования для приложения"""

    # Создаем папку для логов
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Уровень логирования
    log_level = logging.DEBUG if app.config['DEBUG'] else logging.INFO

    # Формат логов
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )

    # Файловый обработчик (ротация при достижении 10MB, храним 10 файлов)
    file_handler = RotatingFileHandler(
        'logs/company_portal.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Добавляем обработчики к приложению
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)

    # Логируем старт приложения
    app.logger.info('='*50)
    app.logger.info(
        f'Company Portal запущен в {"DEBUG" if app.config["DEBUG"] else "PRODUCTION"} режиме')
    app.logger.info('='*50)
