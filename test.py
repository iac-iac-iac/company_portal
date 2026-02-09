from app import app, db, User

with app.app_context():
    admin = User(username='admin', role='admin')
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()
    print("✅ Администратор создан! Логин: admin, Пароль: admin123")
