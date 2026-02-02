from datetime import datetime, timedelta
import pytz
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
# 使用 itsdangerous 2.2.0+ 推荐的 URLSafeTimedSerializer
from itsdangerous import URLSafeTimedSerializer as Serializer

# 全局定义本地时区（东八区，北京时间）
LOCAL_TIMEZONE = pytz.timezone('Asia/Shanghai')


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    # 修改：邮箱设为可为空，支持无邮箱注册
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(10), default='user')  # 数据库角色：'user' 或 'admin'
    # 新增：邮箱验证状态
    email_verified = db.Column(db.Boolean, default=False)

    # 数据库存储UTC时间（字段名加前缀_utc，实际数据库列名仍为created_at）
    _utc_created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)

    # 定义property，前端调用user.created_at时自动返回本地时间
    @property
    def created_at(self):
        return self._convert_utc_to_local(self._utc_created_at)

    # 时间转换通用方法（UTC→本地时区）
    def _convert_utc_to_local(self, utc_time):
        if not utc_time:
            return None
        # 给UTC时间添加时区标识，再转换为本地时区
        utc_aware = pytz.utc.localize(utc_time)  # 标记为UTC时间
        return utc_aware.astimezone(LOCAL_TIMEZONE)  # 转换为本地时间

    def get_reset_password_token(self, expires_in=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @classmethod
    def verify_reset_password_token(cls, token, max_age=3600):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=max_age)
        except:
            return None
        return cls.query.get(data['user_id'])

    # 新增：生成邮箱验证 Token (保持与重置密码一致的风格)
    def get_email_verification_token(self, expires_in=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    # 新增：验证邮箱 Token
    @classmethod
    def verify_email_token(cls, token, max_age=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=max_age)
        except:
            return None
        return cls.query.get(data['user_id'])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- 权限核心逻辑修改 ---

    def is_super_admin(self):
        """
        判断是否为超级管理员 (Root)
        依据：邮箱是否包含在 FLASKY_ADMIN 配置列表中
        """
        # 如果用户没有邮箱，自然不可能是超级管理员
        if not self.email:
            return False

        admin_emails_config = current_app.config.get('FLASKY_ADMIN')

        if not admin_emails_config:
            return False

        # 兼容处理：支持字符串（逗号分隔）或 列表格式
        if isinstance(admin_emails_config, str):
            # 将 "a@a.com, b@b.com" 分割并去空格 -> ['a@a.com', 'b@b.com']
            admin_list = [email.strip() for email in admin_emails_config.split(',')]
        else:
            admin_list = admin_emails_config

        return self.email in admin_list

    def is_admin(self):
        """
        判断是否为普通管理员 (Admin)
        依据：数据库角色为 'admin' 或 自身是超级管理员
        """
        return self.role == 'admin' or self.is_super_admin()

    # -----------------------

    # 关系
    spaces = db.relationship('Space', backref='creator', lazy='dynamic')
    items = db.relationship('Item', backref='creator', lazy='dynamic')
    records = db.relationship('Record', backref='user', lazy='dynamic')
    reservations = db.relationship('Reservation', backref='user', lazy='dynamic')


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


class Space(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('space.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    _utc_created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)

    @property
    def created_at(self):
        if not self._utc_created_at:
            return None
        utc_aware = pytz.utc.localize(self._utc_created_at)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    def get_path(self):
        path = [self.name]
        current = self.parent
        while current:
            path.insert(0, current.name)
            current = current.parent
        return '/'.join(path)

    def get_level(self):
        level = 0
        current = self.parent
        while current:
            level += 1
            current = current.parent
        return level

    children = db.relationship('Space', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    items = db.relationship('Item', backref='space', lazy='dynamic', cascade="all, delete-orphan")


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    function = db.Column(db.Text)
    serial_number = db.Column(db.String(50), unique=True)
    status = db.Column(db.String(20), default='available')  # available, borrowed, reserved
    barcode_path = db.Column(db.String(255))
    space_id = db.Column(db.Integer, db.ForeignKey('space.id'), nullable=False)
    # 【允许创建者为空（用户删除后保留物品）】
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # 数据库存储UTC时间
    _utc_created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    _utc_updated_at = db.Column('updated_at', db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 前端调用item.created_at / item.updated_at时返回本地时间
    @property
    def created_at(self):
        if not self._utc_created_at:
            return None
        utc_aware = pytz.utc.localize(self._utc_created_at)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    @property
    def updated_at(self):
        if not self._utc_updated_at:
            return None
        utc_aware = pytz.utc.localize(self._utc_updated_at)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    # 关系
    records = db.relationship('Record', backref='item', lazy='dynamic', cascade="all, delete-orphan")
    reservations = db.relationship('Reservation', backref='item', lazy='dynamic', cascade="all, delete-orphan")


class Record(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    # 【允许用户ID为空（用户删除后保留记录）】
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    space_path = db.Column(db.String(255))
    usage_location = db.Column(db.String(255))

    # 数据库存储UTC时间
    _utc_start_time = db.Column('start_time', db.DateTime, default=datetime.utcnow)
    _utc_return_time = db.Column('return_time', db.DateTime)
    _utc_created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='using')  # using, returned

    # 前端调用record.start_time / return_time / created_at时返回本地时间
    @property
    def start_time(self):
        if not self._utc_start_time:
            return None
        utc_aware = pytz.utc.localize(self._utc_start_time)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    @property
    def return_time(self):
        if not self._utc_return_time:
            return None
        utc_aware = pytz.utc.localize(self._utc_return_time)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    @property
    def created_at(self):
        if not self._utc_created_at:
            return None
        utc_aware = pytz.utc.localize(self._utc_created_at)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    # 逾期判断基于UTC时间
    def is_overdue(self):
        if self.status == 'using' and self._utc_start_time:  # 使用数据库原始UTC时间判断
            return datetime.utcnow() - self._utc_start_time > timedelta(days=10)
        return False


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    # 【允许用户ID为空（用户删除后保留预约）】
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # 数据库存储UTC时间
    _utc_reservation_start = db.Column('reservation_start', db.DateTime, nullable=False)
    _utc_reservation_end = db.Column('reservation_end', db.DateTime, nullable=False)
    _utc_created_at = db.Column('created_at', db.DateTime, default=datetime.utcnow)
    # scheduled/active/expired/cancelled/used/conflicted
    status = db.Column(db.String(20), default='scheduled')
    notes = db.Column(db.Text, nullable=True)

    # 前端调用时返回东八区本地时间
    @property
    def reservation_start(self):
        if not self._utc_reservation_start:
            return None
        utc_aware = pytz.utc.localize(self._utc_reservation_start)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    @property
    def reservation_end(self):
        if not self._utc_reservation_end:
            return None
        utc_aware = pytz.utc.localize(self._utc_reservation_end)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    @property
    def created_at(self):
        if not self._utc_created_at:
            return None
        utc_aware = pytz.utc.localize(self._utc_created_at)
        return utc_aware.astimezone(LOCAL_TIMEZONE)

    def is_scheduled(self):
        """判断是否处于“待开始”状态"""
        return self.status == 'scheduled'

    def is_active(self):
        """
        判断是否处于“有效可使用”状态
        【关键修改】：在新逻辑中，预约生效(active)时，物品会被自动锁定(reserved)。
        因此不再要求 item.status == 'available'。
        只要预约状态是 active，就代表当前用户拥有该物品的独占使用权。
        """
        return self.status == 'active'

    def is_expired(self):
        """判断是否“超期作废”"""
        return self.status == 'expired'

    def is_conflicted(self):
        """判断是否因物品未归还导致冲突"""
        return self.status == 'conflicted'