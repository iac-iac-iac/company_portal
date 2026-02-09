@echo off
echo ================================================
echo     Управление миграциями базы данных
echo ================================================
echo.
echo 1. Создать новую миграцию (после изменения моделей)
echo 2. Применить миграции к БД
echo 3. Откатить последнюю миграцию
echo 4. Показать историю миграций
echo.
set /p choice="Выбери действие (1-4): "

if "%choice%"=="1" (
    set /p message="Введи описание изменений: "
    flask db migrate -m "%message%"
    echo.
    echo Миграция создана! Теперь выполни пункт 2 для применения.
    pause
    exit
)

if "%choice%"=="2" (
    flask db upgrade
    echo.
    echo Миграции применены!
    pause
    exit
)

if "%choice%"=="3" (
    flask db downgrade
    echo.
    echo Откат выполнен!
    pause
    exit
)

if "%choice%"=="4" (
    flask db history
    pause
    exit
)

echo Неверный выбор!
pause
