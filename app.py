import os
import requests
import markdown
from config import Config
from datetime import datetime
from dotenv import load_dotenv
from logger import setup_logger
from flask_migrate import Migrate
from flask_compress import Compress
from flask_basicauth import BasicAuth
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_admin.form import FileUploadField
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask import Flask, render_template, request, flash


# Загружаем переменные окружения
load_dotenv()

# --- КОНФИГУРАЦИЯ ---
app = Flask(__name__)
app.config.from_object(Config)

# Создаем папку для загрузок если её нет
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Получаем настройки Telegram из конфига
TG_BOT_TOKEN = app.config['TG_BOT_TOKEN']
TG_CHAT_ID = app.config['TG_CHAT_ID']

basic_auth = BasicAuth(app)


db = SQLAlchemy(app)
csrf = CSRFProtect(app)
migrate = Migrate(app, db)
# Настройка логирования
setup_logger(app)
# Сжатие ответов (gzip)
compress = Compress(app)
# Отключаем CSRF для feedback (временно для отладки)


# --- ФУНКЦИЯ ОТПРАВКИ В TELEGRAM ---


def send_telegram(message):
    """Отправка уведомления в Telegram"""
    try:
        if TG_BOT_TOKEN and TG_CHAT_ID:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            response = requests.post(url, json={
                "chat_id": TG_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=5)

            if response.status_code == 200:
                app.logger.info(
                    f"Telegram уведомление отправлено: {message[:50]}...")
            else:
                app.logger.error(
                    f"Telegram API вернул код {response.status_code}")
        else:
            app.logger.warning(
                "Telegram не настроен (отсутствует TOKEN или CHAT_ID)")
    except requests.exceptions.Timeout:
        app.logger.error("Timeout при отправке в Telegram")
    except Exception as e:
        app.logger.error(f"Ошибка отправки в Telegram: {e}", exc_info=True)

# --- ОБРАБОТКА ОШИБОК ---


@app.errorhandler(400)
def handle_bad_request(e):
    app.logger.warning(f"Bad Request (400): {e}")
    return render_template('error.html',
                           error_title="Некорректный запрос",
                           error_message="Проверьте правильность введенных данных и попробуйте снова."), 400


@app.errorhandler(404)
def handle_not_found(e):
    app.logger.info(f"Page not found (404): {request.url}")
    return render_template('error.html',
                           error_title="Страница не найдена",
                           error_message="Запрошенная страница не существует."), 404


@app.errorhandler(413)
def handle_large_file(e):
    app.logger.warning(f"File too large (413) from IP: {request.remote_addr}")
    return render_template('error.html',
                           error_title="Файл слишком большой",
                           error_message="Максимальный размер файла: 16 МБ."), 413


@app.errorhandler(500)
def handle_internal_error(e):
    app.logger.error(f"Internal Server Error (500): {e}", exc_info=True)
    db.session.rollback()  # Откатываем транзакцию при ошибке
    return render_template('error.html',
                           error_title="Внутренняя ошибка сервера",
                           error_message="Что-то пошло не так. Попробуйте позже."), 500


@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.critical(f"Unhandled exception: {e}", exc_info=True)
    db.session.rollback()
    return render_template('error.html',
                           error_title="Непредвиденная ошибка",
                           error_message="Произошла ошибка. Администраторы уведомлены."), 500


# --- МОДЕЛИ ---


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False,
                     index=True)  # Индекс для поиска
    position = db.Column(db.String(100), nullable=False,
                         index=True)  # Индекс для поиска
    birthday = db.Column(db.Date, nullable=True)

    manager_id = db.Column(db.Integer, db.ForeignKey(
        'employee.id'), nullable=True, index=True)
    children = db.relationship('Employee', backref=db.backref(
        'parent', remote_side=[id]), lazy='joined')

    def __str__(self):
        return f"{self.name} ({self.position})"


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False,
                      index=True)  # Индекс для поиска
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(200), nullable=True)

    def __str__(self):
        return self.title


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(100), nullable=True, default="Аноним")
    category = db.Column(db.String(50), nullable=False,
                         index=True)  # Индекс для фильтрации
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now,
                           index=True)  # Индекс для сортировки

    def __str__(self):
        return f"{self.category}: {self.message[:20]}..."


# --- БЕЗОПАСНОСТЬ ---


class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return basic_auth.authenticate()

    def inaccessible_callback(self, name, **kwargs):
        return basic_auth.challenge()


class SecureModelView(ModelView):
    def is_accessible(self):
        return basic_auth.authenticate()

    def inaccessible_callback(self, name, **kwargs):
        return basic_auth.challenge()


# --- АДМИНКА ---
admin = Admin(app, name='Панель Управления', index_view=MyAdminIndexView())


class EmployeeView(SecureModelView):
    column_labels = {
        'name': 'ФИО',
        'position': 'Должность',
        'birthday': 'День Рождения'
    }
    column_list = ('name', 'position', 'birthday', 'manager_id')
    form_columns = ('name', 'position', 'manager_id', 'birthday')

    # Красивое отображение руководителя
    column_formatters = {
        'manager_id': lambda v, c, m, p: f'{m.parent.name} ({m.parent.position})' if m.parent else 'Нет руководителя'
    }

    # Переименовываем колонку в интерфейсе
    column_labels['manager_id'] = 'Руководитель'


class ArticleView(SecureModelView):
    column_labels = {'title': 'Заголовок', 'content': 'Текст',
                     'file_upload': 'Файл', 'file_path': 'Имя файла'}
    form_extra_fields = {
        'file_upload': FileUploadField('Загрузить файл',
                                       base_path=lambda: app.config['UPLOAD_FOLDER'],
                                       allowed_extensions=list(app.config['ALLOWED_EXTENSIONS']))
    }

    def on_model_change(self, form, model, is_created):
        if form.file_upload.data:
            model.file_path = form.file_upload.data.filename
        super().on_model_change(form, model, is_created)

    column_list = ('title', 'file_path')
    form_columns = ('title', 'content', 'file_upload')


class FeedbackView(SecureModelView):
    can_create = False
    can_edit = False
    column_searchable_list = ['message', 'sender']
    column_filters = ['category']
    column_list = ('created_at', 'category', 'sender', 'message')
    column_default_sort = ('created_at', True)


admin.add_view(EmployeeView(Employee, db.session, name="Сотрудники"))
admin.add_view(ArticleView(Article, db.session, name="База знаний"))
admin.add_view(FeedbackView(Feedback, db.session, name="Сообщения"))


@app.template_filter('markdown')
def render_markdown(text):
    return markdown.markdown(text) if text else ""

# --- МАРШРУТЫ ---


@app.route('/')
def home():
    roots = Employee.query.filter_by(manager_id=None).all()

    # --- ЛОГИКА ДНЕЙ РОЖДЕНИЙ ---
    from datetime import datetime
    today = datetime.today()
    current_month = today.month

    # Находим всех, у кого есть дата рождения
    all_employees = Employee.query.filter(Employee.birthday.is_not(None)).all()

    # Фильтруем тех, у кого ДР в этом месяце
    birthdays_this_month = []
    for emp in all_employees:
        if emp.birthday.month == current_month:
            birthdays_this_month.append(emp)

    # Сортируем по дню (кто раньше)
    birthdays_this_month.sort(key=lambda x: x.birthday.day)

    return render_template('index.html', roots=roots, birthdays=birthdays_this_month)


@app.route('/wiki')
def wiki():
    articles = Article.query.all()
    return render_template('wiki.html', articles=articles)


@app.route('/search')
def search():
    q = request.args.get('q', '').strip()  # Убираем пробелы

    if q:
        found_employees = Employee.query.filter(
            (Employee.name.ilike(f'%{q}%')) | (
                Employee.position.ilike(f'%{q}%'))
        ).all()
        found_articles = Article.query.filter(
            (Article.title.ilike(f'%{q}%')) | (Article.content.ilike(f'%{q}%'))
        ).all()
    else:
        found_employees = []
        found_articles = []

    return render_template('search.html', q=q, employees=found_employees, articles=found_articles)

# ОБРАТНАЯ СВЯЗЬ + TELEGRAM


@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    success = False
    if request.method == 'POST':
        try:
            sender = request.form.get('sender') or "Аноним"
            category = request.form.get('category')
            message = request.form.get('message')

            app.logger.info(f"Новое обращение от {sender}: {category}")

            new_feedback = Feedback(
                sender=sender, category=category, message=message)
            db.session.add(new_feedback)
            db.session.commit()

            # Формируем текст для Telegram
            tg_text = (
                f"🔔 *Новое обращение на портале!*\n\n"
                f"📌 *Тема:* {category}\n"
                f"👤 *От:* {sender}\n"
                f"📝 *Текст:* {message}"
            )

            send_telegram(tg_text)
            success = True

        except Exception as e:
            app.logger.error(
                f"Ошибка при обработке обратной связи: {e}", exc_info=True)
            db.session.rollback()
            flash('Произошла ошибка при отправке сообщения. Попробуйте позже.', 'error')

    return render_template('feedback.html', success=success)


# ОБРАТНАЯ СВЯЗЬ + TELEGRAM


if __name__ == '__main__':
    # Миграции теперь управляются через flask db команды
    # db.create_all() больше не нужен

    app.run(debug=app.config['DEBUG'], host='127.0.0.1', port=5000)
