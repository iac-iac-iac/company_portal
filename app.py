import os
import requests # Библиотека для связи с Telegram
from flask import Flask, render_template, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_admin.form import FileUploadField
from flask_basicauth import BasicAuth 
import markdown
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///company.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- НАСТРОЙКИ TELEGRAM (ВСТАВЬ СВОИ ДАННЫЕ!) ---
TG_BOT_TOKEN = ''  # Например: '54321:AAFx...'
TG_CHAT_ID = ''              # Например: '123456' или '-100...'

# НАСТРОЙКИ ПАРОЛЯ АДМИНКИ
app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = '2232' 
app.config['BASIC_AUTH_FORCE'] = False

basic_auth = BasicAuth(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

# --- ФУНКЦИЯ ОТПРАВКИ В TELEGRAM ---
def send_telegram(message):
    try:
        if TG_BOT_TOKEN and TG_CHAT_ID:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": TG_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown" # Чтобы работало жирное выделение
            })
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

# --- МОДЕЛИ ---
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    # НОВОЕ ПОЛЕ:
    birthday = db.Column(db.Date, nullable=True) 

    manager_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    children = db.relationship('Employee', backref=db.backref('parent', remote_side=[id]), lazy='joined')

    def __str__(self):
        return f"{self.name} ({self.position})"

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(200), nullable=True)

    def __str__(self):
        return self.title

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(100), nullable=True, default="Аноним")
    category = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

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
    column_labels = {'name': 'ФИО', 'position': 'Должность', 'parent': 'Руководитель', 'birthday': 'День Рождения'}
    column_list = ('name', 'position', 'parent', 'birthday')
    form_columns = ('name', 'position', 'parent', 'birthday')

class ArticleView(SecureModelView):
    column_labels = {'title': 'Заголовок', 'content': 'Текст', 'file_upload': 'Файл', 'file_path': 'Имя файла'}
    form_extra_fields = {
        'file_upload': FileUploadField('Загрузить файл', base_path=UPLOAD_FOLDER, allowed_extensions=['pdf', 'docx', 'xlsx', 'txt', 'zip', 'jpg', 'png'])
    }
    def on_model_change(self, form, model, is_created):
        if form.file_upload.data:
            model.file_path = form.file_upload.data.filename
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
    all_employees = Employee.query.filter(Employee.birthday != None).all()

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
    q = request.args.get('q')
    if q:
        found_employees = Employee.query.filter((Employee.name.contains(q)) | (Employee.position.contains(q))).all()
        found_articles = Article.query.filter((Article.title.contains(q)) | (Article.content.contains(q))).all()
    else:
        found_employees = []
        found_articles = []
    return render_template('search.html', q=q, employees=found_employees, articles=found_articles)

# ОБРАТНАЯ СВЯЗЬ + TELEGRAM
@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    success = False
    if request.method == 'POST':
        sender = request.form.get('sender') or "Аноним"
        category = request.form.get('category')
        message = request.form.get('message')
        
        # 1. Сохраняем в базу (как и раньше)
        new_feedback = Feedback(sender=sender, category=category, message=message)
        db.session.add(new_feedback)
        db.session.commit()
        
        # 2. Формируем текст для Telegram
        tg_text = (
            f"🔔 *Новое обращение на портале!*\n\n"
            f"📌 *Тема:* {category}\n"
            f"👤 *От:* {sender}\n"
            f"📝 *Текст:* {message}"
        )
        
        # 3. Отправляем
        send_telegram(tg_text)
        
        success = True
        
    return render_template('feedback.html', success=success)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True, host='0.0.0.0', port=5000)
