# Production Deployment Checklist

## Перед деплоем

### Безопасность

- [ ] `.env` файл создан и заполнен реальными значениями
- [ ] `SECRET_KEY` - случайная строка минимум 32 символа
- [ ] `DEBUG=False` в `.env`
- [ ] `ADMIN_PASSWORD` изменен на сложный пароль
- [ ] `.env` добавлен в `.gitignore`
- [ ] Telegram токены настроены (если используется)

### База данных

- [ ] Все миграции применены (`flask db upgrade`)
- [ ] Создана резервная копия БД
- [ ] Настроено автоматическое резервное копирование

### Файлы

- [ ] Папка `static/uploads/` существует
- [ ] Права на запись для папки `logs/`
- [ ] Права на запись для папки `instance/`

### Зависимости

- [ ] Все пакеты установлены (`pip install -r requirements.txt`)
- [ ] Версии Python совместимы (3.8+)

### Тестирование

- [ ] Проверена авторизация в админке
- [ ] Протестирована форма обратной связи
- [ ] Проверена отправка в Telegram
- [ ] Протестирован поиск
- [ ] Проверена загрузка файлов

## Запуск Production

### Вариант 1: Gunicorn (Linux/Mac)

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app --access-logfile logs/access.log --error-logfile logs/error.log

### Вариант 2: Waitress (Windows)
bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 wsgi:app

### Вариант 3: Docker
bash
docker build -t company-portal .
docker run -d -p 5000:5000 --env-file .env company-portal
Мониторинг
 Логи пишутся в logs/company_portal.log

 Настроен мониторинг свободного места на диске

 Настроены алерты при ошибках 500

 Telegram уведомления работают

### Обслуживание

## Резервное копирование (запускать ежедневно)
bash
python -c "from app import app, db; import shutil; from datetime import datetime; shutil.copy('instance/company.db', f'backups/db_{datetime.now():%Y%m%d_%H%M%S}.db')"
Обновление приложения
bash
git pull
pip install -r requirements.txt
flask db upgrade
# Перезапустить сервер

## Очистка старых логов (раз в месяц)
bash
find logs/ -name "*.log.*" -mtime +30 -delete

### Рекомендации
Nginx/Apache - используйте reverse proxy

SSL/HTTPS - обязательно для production

Firewall - ограничьте доступ к порту 5000

Systemd/Supervisor - автозапуск при перезагрузке

PostgreSQL - для production вместо SQLite

### Создаем Dockerfile (опционально)

**Создаем `Dockerfile`:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Копируем приложение
COPY . .

# Создаем необходимые папки
RUN mkdir -p logs instance static/uploads backups

# Порт приложения
EXPOSE 5000

# Запуск через gunicorn
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "wsgi:app"]
