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
from flask_admin.actions import action
from flask_sqlalchemy import SQLAlchemy
from flask_admin.form import FileUploadField
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user


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
# --- FLASK-LOGIN ---
login_manager = LoginManager(app)
login_manager.login_view = 'user_login'  # Куда редиректить неавторизованных
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Загружает пользователя по ID"""
    return User.query.get(int(user_id))


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
class User(UserMixin, db.Model):
    """Пользователь системы с авторизацией"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True,
                         nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey(
        'employee.id'), nullable=True, unique=True)
    # employee, manager, admin
    role = db.Column(db.String(20), default='employee')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime, nullable=True)

    # НОВОЕ: Флаг принудительной смены пароля
    must_change_password = db.Column(db.Boolean, default=True)

    # НОВОЕ: Дата последней смены пароля
    password_changed_at = db.Column(db.DateTime, nullable=True)

    # Связь с сотрудником
    employee = db.relationship('Employee', backref=db.backref(
        'user', uselist=False), lazy='joined')

    def set_password(self, password):
        """Хэширует и сохраняет пароль"""
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.now()

    def check_password(self, password):
        """Проверяет пароль"""
        return check_password_hash(self.password_hash, password)

    def __str__(self):
        return self.username


class LoginHistory(db.Model):
    """История входов пользователей"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False, index=True)
    login_time = db.Column(db.DateTime, default=datetime.now, index=True)
    logout_time = db.Column(db.DateTime, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 поддержка
    user_agent = db.Column(db.String(200), nullable=True)
    session_duration = db.Column(db.Integer, nullable=True)  # в секундах

    # Связь с пользователем
    user = db.relationship('User', backref=db.backref(
        'login_history', lazy='dynamic', order_by='LoginHistory.login_time.desc()'))

    def __str__(self):
        return f"{self.user.username} - {self.login_time.strftime('%d.%m.%Y %H:%M')}"

    def get_duration_str(self):
        """Возвращает длительность сеанса в читаемом виде"""
        if not self.session_duration:
            return "Активен"

        minutes = self.session_duration // 60
        if minutes < 60:
            return f"{minutes} мин"

        hours = minutes // 60
        remaining_minutes = minutes % 60
        return f"{hours}ч {remaining_minutes}м"
# --- ГЕЙМИФИКАЦИЯ: ПРОДАЖИ ---


class SalesTask(db.Model):
    """Задачи для отдела продаж"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Тип задачи
    # calls, sales, meetings, deals
    task_type = db.Column(db.String(50), nullable=False)

    # Период
    period = db.Column(db.String(20), nullable=False)  # daily, weekly, monthly

    # Целевое значение
    target_value = db.Column(db.Integer, nullable=False)

    # Очки за выполнение
    reward_points = db.Column(db.Integer, default=10)

    # Активность
    is_active = db.Column(db.Boolean, default=True)

    # Даты
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now)

    def __str__(self):
        return f"{self.title} ({self.get_period_display()})"

    def get_period_display(self):
        periods = {
            'daily': 'Ежедневно',
            'weekly': 'Еженедельно',
            'monthly': 'Ежемесячно'
        }
        return periods.get(self.period, self.period)

    def get_type_display(self):
        types = {
            'calls': '☎️ Звонки',
            'sales': '💰 Продажи',
            'meetings': '🤝 Встречи',
            'deals': '📝 Сделки'
        }
        return types.get(self.task_type, self.task_type)


class SalesProgress(db.Model):
    """Прогресс сотрудника по задаче"""
    id = db.Column(db.Integer, primary_key=True)

    # Связи
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey(
        'sales_task.id'), nullable=False, index=True)

    # Прогресс
    current_value = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Период (для повторяющихся задач)
    period_start = db.Column(db.Date, nullable=False, index=True)
    period_end = db.Column(db.Date, nullable=False)

    # Кто обновил
    updated_by_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=True)
    last_updated = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Связи
    user = db.relationship('User', foreign_keys=[
                           user_id], backref='sales_progress')
    task = db.relationship('SalesTask', backref='progress_records')
    updated_by = db.relationship('User', foreign_keys=[updated_by_id])

    def __str__(self):
        return f"{self.user.username} - {self.task.title}: {self.current_value}/{self.task.target_value}"

    def get_progress_percent(self):
        """Возвращает процент выполнения"""
        if self.task.target_value == 0:
            return 0
        return min(100, int((self.current_value / self.task.target_value) * 100))


class UserPoints(db.Model):
    """Очки и статистика пользователя"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False, unique=True, index=True)

    # Очки
    total_points = db.Column(db.Integer, default=0)
    current_level = db.Column(db.Integer, default=1)

    # Статистика
    tasks_completed = db.Column(db.Integer, default=0)
    achievements_earned = db.Column(db.Integer, default=0)

    # Даты
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_activity = db.Column(db.DateTime, default=datetime.now)

    # Связь
    user = db.relationship('User', backref=db.backref('points', uselist=False))

    def __str__(self):
        return f"{self.user.username}: {self.total_points} pts (Lvl {self.current_level})"

    def add_points(self, points, reason=""):
        """Добавляет очки и проверяет повышение уровня"""
        self.total_points += points
        self.last_activity = datetime.now()

        # Простая формула уровня: каждые 100 очков = +1 уровень
        new_level = (self.total_points // 100) + 1

        if new_level > self.current_level:
            self.current_level = new_level
            return True  # Повышение уровня!

        return False

    def get_progress_to_next_level(self):
        """Прогресс до следующего уровня в процентах"""
        points_in_current_level = self.total_points % 100
        return points_in_current_level


class SalesAchievement(db.Model):
    """Достижения в продажах"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(50), default='🏆')

    # Условие получения
    # tasks_completed, points_earned, streak_days
    condition_type = db.Column(db.String(50), nullable=False)
    condition_value = db.Column(db.Integer, nullable=False)

    # Награда
    reward_points = db.Column(db.Integer, default=50)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __str__(self):
        return f"{self.icon} {self.title}"


class UserAchievement(db.Model):
    """Полученные достижения пользователей"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(
        'user.id'), nullable=False, index=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey(
        'sales_achievement.id'), nullable=False)

    earned_at = db.Column(db.DateTime, default=datetime.now)

    # Связи
    user = db.relationship('User', backref='achievements')
    achievement = db.relationship('SalesAchievement', backref='earned_by')

    def __str__(self):
        return f"{self.user.username} - {self.achievement.title}"


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    position = db.Column(db.String(100), nullable=False, index=True)
    birthday = db.Column(db.Date, nullable=True)
    email = db.Column(db.String(120), nullable=True)  # Если добавили
    telegram = db.Column(db.String(50), nullable=True)  # Если добавили

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
        'birthday': 'День Рождения',
        'email': 'Email',
        'telegram': 'Telegram'
    }
    column_list = ['name', 'position', 'email',
                   'telegram', 'birthday', 'manager_id']
    form_columns = ['name', 'position', 'email',
                    'telegram', 'manager_id', 'birthday']

    column_formatters = {
        'manager_id': lambda v, c, m, p: f'{m.parent.name} ({m.parent.position})' if m.parent else 'Нет руководителя'
    }
    column_labels['manager_id'] = 'Руководитель'


class ArticleView(SecureModelView):
    column_labels = {
        'title': 'Заголовок',
        'content': 'Текст',
        'file_path': 'Имя файла'
    }
    column_list = ['title', 'file_path']
    form_columns = ['title', 'content']


class FeedbackView(SecureModelView):
    can_create = False
    can_edit = False
    column_searchable_list = ['message', 'sender']
    column_filters = ['category']
    column_list = ['created_at', 'category', 'sender', 'message']
    column_default_sort = ('created_at', True)


class UserView(SecureModelView):
    """Управление пользователями"""
    column_labels = {
        'username': 'Логин',
        'employee': 'Сотрудник',
        'role': 'Роль',
        'is_active': 'Активен',
        'last_login': 'Последний вход',
        'must_change_password': 'Требует смены',
        'password_changed_at': 'Пароль изменен'
    }

    column_list = ['username', 'employee', 'role',
                   'is_active', 'must_change_password', 'last_login']
    form_columns = ['username', 'employee', 'role', 'is_active']
    column_searchable_list = ['username']
    column_filters = ['role', 'is_active', 'must_change_password']
    column_default_sort = ('created_at', True)

    column_descriptions = {
        'must_change_password': 'Пользователь будет обязан сменить пароль при следующем входе'
    }

    def on_model_change(self, form, model, is_created):
        """При создании устанавливаем дефолтный пароль = логин"""
        if is_created:
            model.set_password(model.username)
            model.must_change_password = True
            app.logger.info(f"Создан новый пользователь: {model.username}")

            # Уведомление в Telegram
            if model.employee:
                send_telegram(
                    f"🆕 *Новый пользователь создан*\n\n"
                    f"👤 Логин: `{model.username}`\n"
                    f"🔑 Пароль: `{model.username}` _(временный)_\n"
                    f"👨‍💼 Сотрудник: {model.employee.name}\n"
                    f"📋 Роль: {model.role}\n\n"
                    f"⚠️ Пользователь должен сменить пароль при первом входе!"
                )

        super().on_model_change(form, model, is_created)

    # НОВОЕ: Массовое действие "Сбросить пароль"
    @action('reset_password', '🔄 Сбросить пароль',
            'Вы уверены? Пароль будет сброшен на логин пользователя.')
    def action_reset_password(self, ids):
        """Сбрасывает пароль для выбранных пользователей"""
        try:
            query = User.query.filter(User.id.in_(ids))
            count = 0
            reset_users = []

            for user in query.all():
                old_must_change = user.must_change_password

                # Сбрасываем пароль на логин
                user.set_password(user.username)
                user.must_change_password = True

                reset_users.append({
                    'username': user.username,
                    'employee': user.employee.name if user.employee else None
                })
                count += 1

                app.logger.warning(
                    f"Пароль сброшен админом для: {user.username}")

            db.session.commit()

            # Уведомление в Telegram
            if reset_users:
                user_list = "\n".join([
                    f"• `{u['username']}` ({u['employee'] or 'без сотрудника'})"
                    for u in reset_users
                ])

                send_telegram(
                    f"🔐 *Сброс паролей*\n\n"
                    f"👥 Пользователи ({count}):\n{user_list}\n\n"
                    f"🔑 Новые пароли = логины _(временные)_\n"
                    f"⚠️ Требуется смена при следующем входе!"
                )

            flash(
                f'✅ Пароль сброшен для {count} пользователей. Новый пароль = логин.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'❌ Ошибка при сбросе пароля: {str(e)}', 'error')
            app.logger.error(f"Ошибка сброса пароля: {e}", exc_info=True)


class SalesTaskView(SecureModelView):
    """Управление задачами для продаж"""
    column_labels = {
        'title': 'Название',
        'description': 'Описание',
        'task_type': 'Тип',
        'period': 'Период',
        'target_value': 'Цель',
        'reward_points': 'Очки',
        'is_active': 'Активна',
        'start_date': 'Начало',
        'end_date': 'Конец'
    }

    column_list = ['title', 'task_type', 'period',
                   'target_value', 'reward_points', 'is_active']
    form_columns = ['title', 'description', 'task_type', 'period',
                    'target_value', 'reward_points', 'is_active', 'start_date', 'end_date']

    column_filters = ['task_type', 'period', 'is_active']
    column_searchable_list = ['title']

    form_choices = {
        'task_type': [
            ('calls', '☎️ Звонки'),
            ('sales', '💰 Продажи'),
            ('meetings', '🤝 Встречи'),
            ('deals', '📝 Сделки')
        ],
        'period': [
            ('daily', 'Ежедневно'),
            ('weekly', 'Еженедельно'),
            ('monthly', 'Ежемесячно')
        ]
    }


class SalesProgressView(SecureModelView):
    """Прогресс по задачам (только для manager/admin)"""
    can_create = False
    can_delete = False

    column_labels = {
        'user': 'Сотрудник',
        'task': 'Задача',
        'current_value': 'Текущий результат',
        'is_completed': 'Выполнено',
        'period_start': 'Начало периода',
        'period_end': 'Конец периода',
        'updated_by': 'Обновил',
        'last_updated': 'Последнее обновление'
    }

    column_list = ['user', 'task', 'current_value',
                   'is_completed', 'period_start', 'last_updated']
    form_columns = ['user', 'task', 'current_value',
                    'period_start', 'period_end']

    column_filters = ['is_completed', 'period_start', 'user']
    column_searchable_list = ['user.username']

    def on_model_change(self, form, model, is_created):
        """При обновлении прогресса"""
        # Записываем кто обновил
        from flask_login import current_user
        model.updated_by_id = current_user.id
        model.last_updated = datetime.now()

        # Проверяем выполнение
        if model.current_value >= model.task.target_value and not model.is_completed:
            model.is_completed = True
            model.completed_at = datetime.now()

            # Начисляем очки
            user_points = UserPoints.query.filter_by(
                user_id=model.user_id).first()
            if not user_points:
                user_points = UserPoints(user_id=model.user_id)
                db.session.add(user_points)

            leveled_up = user_points.add_points(model.task.reward_points)
            user_points.tasks_completed += 1

            # Уведомление в Telegram
            employee_name = model.user.employee.name if model.user.employee else model.user.username
            send_telegram(
                f"🎉 *Задача выполнена!*\n\n"
                f"👤 Сотрудник: {employee_name}\n"
                f"📋 Задача: {model.task.title}\n"
                f"✅ Результат: {model.current_value}/{model.task.target_value}\n"
                f"⭐ Получено очков: +{model.task.reward_points}\n"
                + (f"🎊 **НОВЫЙ УРОВЕНЬ: {user_points.current_level}!**" if leveled_up else "")
            )

        super().on_model_change(form, model, is_created)


class UserPointsView(SecureModelView):
    """Статистика очков (только просмотр)"""
    can_create = False
    can_edit = False
    can_delete = False

    column_labels = {
        'user': 'Сотрудник',
        'total_points': 'Всего очков',
        'current_level': 'Уровень',
        'tasks_completed': 'Задач выполнено',
        'achievements_earned': 'Достижений',
        'last_activity': 'Последняя активность'
    }

    column_list = ['user', 'total_points', 'current_level',
                   'tasks_completed', 'achievements_earned', 'last_activity']
    column_default_sort = ('total_points', True)
    column_filters = ['current_level']


class AchievementView(SecureModelView):
    """Управление достижениями"""
    column_labels = {
        'title': 'Название',
        'description': 'Описание',
        'icon': 'Иконка',
        'condition_type': 'Условие',
        'condition_value': 'Значение',
        'reward_points': 'Очки',
        'is_active': 'Активно'
    }

    column_list = ['icon', 'title', 'condition_type',
                   'condition_value', 'reward_points', 'is_active']
    form_columns = ['title', 'description', 'icon', 'condition_type',
                    'condition_value', 'reward_points', 'is_active']

    form_choices = {
        'condition_type': [
            ('tasks_completed', 'Количество выполненных задач'),
            ('points_earned', 'Набрано очков'),
            ('streak_days', 'Дней активности подряд'),
            ('level_reached', 'Достигнут уровень')
        ]
    }

    column_descriptions = {
        'icon': 'Эмодзи для отображения (🏆, 🎖️, ⭐, 🥇, 💎 и т.д.)',
        'condition_type': 'Тип условия для получения',
        'condition_value': 'Целевое значение (например, 10 задач или 500 очков)'
    }


# Регистрация
admin.add_view(EmployeeView(Employee, db.session, name="Сотрудники"))
admin.add_view(ArticleView(Article, db.session, name="База знаний"))
admin.add_view(FeedbackView(Feedback, db.session, name="Сообщения"))
admin.add_view(UserView(User, db.session, name="Пользователи"))

# Геймификация
admin.add_view(SalesTaskView(SalesTask, db.session, name="📋 Задачи продаж"))
admin.add_view(SalesProgressView(SalesProgress, db.session, name="📊 Прогресс"))
admin.add_view(UserPointsView(UserPoints, db.session, name="⭐ Рейтинг"))
admin.add_view(AchievementView(SalesAchievement,
               db.session, name="🎖️ Достижения"))  # НОВОЕ


@app.template_filter('markdown')
def render_markdown(text):
    return markdown.markdown(text) if text else ""

# --- МАРШРУТЫ ---


@app.route('/')
def home():
    roots = Employee.query.filter_by(manager_id=None).all()

    # --- СТАТИСТИКА ---
    from datetime import timedelta

    stats = {
        'total_employees': Employee.query.count(),
        'total_articles': Article.query.count(),
        'recent_feedback': Feedback.query.filter(
            Feedback.created_at >= datetime.now() - timedelta(days=7)
        ).count()
    }

    # --- ЛОГИКА ДНЕЙ РОЖДЕНИЙ ---
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

    return render_template('index.html', roots=roots, birthdays=birthdays_this_month, stats=stats)


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


@app.route('/api/employee')
def api_employee():
    """API для получения детальной информации о сотруднике"""
    employee_id = request.args.get('id', type=int)

    if not employee_id:
        return {'error': 'ID не указан'}, 400

    emp = Employee.query.get_or_404(employee_id)

    return {
        'id': emp.id,
        'name': emp.name,
        'position': emp.position,
        'email': emp.email,
        'telegram': emp.telegram,  # ИЗМЕНИЛИ
        # БЕЗ ГОДА!
        'birthday': emp.birthday.strftime('%d.%m') if emp.birthday else None,
        'manager': emp.parent.name if emp.parent else None,
        'manager_position': emp.parent.position if emp.parent else None
    }


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

# --- АВТОРИЗАЦИЯ ---


@app.route('/login', methods=['GET', 'POST'])
def user_login():  # ИЗМЕНИЛИ название функции на user_login
    """Страница входа"""
    if current_user.is_authenticated:
        return redirect(url_for('profile'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        if not username or not password:
            flash('Заполните все поля', 'error')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Ваш аккаунт заблокирован. Обратитесь к администратору.', 'error')
                return render_template('login.html')

            login_user(user, remember=remember)
            user.last_login = datetime.now()

            # НОВОЕ: Записываем вход в историю
            login_record = LoginHistory(
                user_id=user.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')[:200]
            )
            db.session.add(login_record)
            db.session.commit()

            app.logger.info(
                f"Успешный вход: {username} (IP: {request.remote_addr})")

            # Проверяем принудительную смену пароля
            if user.must_change_password:
                flash(
                    'Вы используете временный пароль. Пожалуйста, смените его.', 'warning')
                return redirect(url_for('change_password'))

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('profile'))

        else:
            app.logger.warning(f"Неудачная попытка входа: {username}")
            flash('Неверный логин или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    username = current_user.username
    user_id = current_user.id

    # НОВОЕ: Закрываем последний сеанс
    last_session = LoginHistory.query.filter_by(
        user_id=user_id,
        logout_time=None
    ).order_by(LoginHistory.login_time.desc()).first()

    if last_session:
        last_session.logout_time = datetime.now()
        duration = (last_session.logout_time -
                    last_session.login_time).total_seconds()
        last_session.session_duration = int(duration)
        db.session.commit()

    logout_user()
    app.logger.info(f"Выход: {username}")
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('home'))


@app.route('/profile')
@login_required
def profile():
    """Личный кабинет пользователя"""
    return render_template('profile.html', user=current_user)

# --- СМЕНА ПАРОЛЯ ---


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Страница смены пароля"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Валидация
        if not current_password or not new_password or not confirm_password:
            flash('Заполните все поля', 'error')
            return render_template('change_password.html', must_change=current_user.must_change_password)

        # Проверяем текущий пароль
        if not current_user.check_password(current_password):
            flash('Неверный текущий пароль', 'error')
            return render_template('change_password.html', must_change=current_user.must_change_password)

        # Проверяем совпадение нового пароля
        if new_password != confirm_password:
            flash('Новые пароли не совпадают', 'error')
            return render_template('change_password.html', must_change=current_user.must_change_password)

        # Проверяем длину
        if len(new_password) < 6:
            flash('Пароль должен быть минимум 6 символов', 'error')
            return render_template('change_password.html', must_change=current_user.must_change_password)

        # Проверяем что новый пароль отличается от старого
        if new_password == current_password:
            flash('Новый пароль должен отличаться от текущего', 'error')
            return render_template('change_password.html', must_change=current_user.must_change_password)

        # Меняем пароль
        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()

        app.logger.info(f"Пароль изменен: {current_user.username}")
        flash('Пароль успешно изменен!', 'success')
        return redirect(url_for('profile'))

    return render_template('change_password.html', must_change=current_user.must_change_password)

# --- ГЕЙМИФИКАЦИЯ: МАРШРУТЫ ---


@app.route('/sales-dashboard')
@login_required
def sales_dashboard():
    """Дашборд продаж для сотрудника"""
    from datetime import date, timedelta

    # Получаем или создаем статистику очков
    user_points = UserPoints.query.filter_by(user_id=current_user.id).first()
    if not user_points:
        user_points = UserPoints(user_id=current_user.id)
        db.session.add(user_points)
        db.session.commit()

    # Текущие активные задачи
    today = date.today()

    # Определяем периоды
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)

    # Получаем активные задачи
    active_tasks = SalesTask.query.filter_by(is_active=True).all()

    # Получаем прогресс пользователя
    user_progress = {}
    for task in active_tasks:
        # Определяем период для задачи
        if task.period == 'daily':
            period_start = today
            period_end = today
        elif task.period == 'weekly':
            period_start = week_start
            period_end = week_end
        elif task.period == 'monthly':
            period_start = month_start
            period_end = today + timedelta(days=31)

        # Ищем или создаем прогресс
        progress = SalesProgress.query.filter_by(
            user_id=current_user.id,
            task_id=task.id,
            period_start=period_start
        ).first()

        if not progress:
            progress = SalesProgress(
                user_id=current_user.id,
                task_id=task.id,
                period_start=period_start,
                period_end=period_end
            )
            db.session.add(progress)

        user_progress[task.id] = progress

    db.session.commit()

    # Топ-5 сотрудников
    top_users = UserPoints.query.order_by(
        UserPoints.total_points.desc()).limit(5).all()

    # Мои достижения
    my_achievements = UserAchievement.query.filter_by(
        user_id=current_user.id).order_by(UserAchievement.earned_at.desc()).limit(5).all()

    return render_template('sales_dashboard.html',
                           user_points=user_points,
                           active_tasks=active_tasks,
                           user_progress=user_progress,
                           top_users=top_users,
                           my_achievements=my_achievements)


@app.route('/leaderboard')
@login_required
def leaderboard():
    """Доска лидеров"""
    # Все пользователи с очками
    all_users = UserPoints.query.order_by(UserPoints.total_points.desc()).all()

    # Моя позиция
    my_points = UserPoints.query.filter_by(user_id=current_user.id).first()
    my_rank = None

    if my_points:
        my_rank = UserPoints.query.filter(
            UserPoints.total_points > my_points.total_points).count() + 1

    return render_template('leaderboard.html',
                           all_users=all_users,
                           my_points=my_points,
                           my_rank=my_rank)


@app.route('/achievements')
@login_required
def achievements():
    """Страница достижений"""
    # Все доступные достижения
    all_achievements = SalesAchievement.query.filter_by(is_active=True).all()

    # Полученные достижения
    earned_ids = [ua.achievement_id for ua in UserAchievement.query.filter_by(
        user_id=current_user.id).all()]

    # Моя статистика
    my_points = UserPoints.query.filter_by(user_id=current_user.id).first()

    return render_template('achievements.html',
                           all_achievements=all_achievements,
                           earned_ids=earned_ids,
                           my_points=my_points)


if __name__ == '__main__':
    # Миграции теперь управляются через flask db команды
    # db.create_all() больше не нужен

    app.run(debug=app.config['DEBUG'], host='127.0.0.1', port=5000)
