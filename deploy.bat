@echo off
echo ================================================
echo     Production Deployment Script
echo ================================================
echo.

echo [1/5] Устанавливаем зависимости...
pip install -r requirements.txt

echo.
echo [2/5] Применяем миграции базы данных...
flask db upgrade

echo.
echo [3/5] Проверяем конфигурацию...
if not exist .env (
    echo ОШИБКА: Файл .env не найден!
    echo Создайте .env на основе .env.example
    pause
    exit /b 1
)

echo.
echo [4/5] Создаем резервную копию БД...
if not exist backups mkdir backups
copy instance\company.db backups\company_backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%.db

echo.
echo [5/5] Готово к запуску!
echo.
echo Для production используйте:
echo   gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
echo.
echo Для разработки:
echo   python app.py
echo.
pause
