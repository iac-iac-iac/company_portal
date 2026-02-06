import sqlite3

# Подключаемся к базе
conn = sqlite3.connect('company.db')
cursor = conn.cursor()

print("Начинаю обновление базы...")

try:
    # Команда SQL, которая добавляет колонку в таблицу
    cursor.execute("ALTER TABLE employee ADD COLUMN birthday DATE")
    print("✅ УСПЕШНО! Колонка 'birthday' добавлена.")
except sqlite3.OperationalError as e:
    # Если ошибка "duplicate column name", значит колонка уже есть
    print(f"⚠️ Колонка уже существует или другая ошибка: {e}")

conn.commit()
conn.close()
input("Нажми Enter, чтобы выйти...")