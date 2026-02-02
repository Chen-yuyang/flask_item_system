from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from flask_login import current_user
from app.models import User


class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')


class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[
        DataRequired(), Length(min=2, max=32)
    ])
    # 修改：邮箱改为可选，只有填写时才验证格式
    email = StringField('邮箱', validators=[
        Optional(), Email()
    ])
    password = PasswordField('密码', validators=[
        DataRequired(), Length(min=3)
    ])
    password2 = PasswordField('确认密码', validators=[
        DataRequired(), EqualTo('password')
    ])
    submit = SubmitField('注册')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('请使用其他用户名')

    def validate_email(self, email):
        # 修改：只有当用户填写了邮箱时才验证唯一性
        if email.data:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('请使用其他邮箱地址')


class ResetPasswordRequestForm(FlaskForm):
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    submit = SubmitField('请求密码重置')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('新密码', validators=[
        DataRequired(), Length(min=3)
    ])
    password2 = PasswordField('确认新密码', validators=[
        DataRequired(), EqualTo('password')
    ])
    submit = SubmitField('重置密码')


# 新增：修改用户名表单
class ChangeUsernameForm(FlaskForm):
    username = StringField('新用户名', validators=[
        DataRequired(), Length(min=2, max=32)
    ])
    submit = SubmitField('更新用户名')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('该用户名已被占用，请选择其他用户名')


# 新增：添加/管理邮箱表单
class AddEmailForm(FlaskForm):
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    submit = SubmitField('发送验证邮件')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        # 如果邮箱存在且不是当前用户的，则报错
        if user and user.id != current_user.id:
            raise ValidationError('该邮箱地址已被其他账户使用')


# 【新增】: 用于修改密码页面（发送邮件）的简单表单，主要用于CSRF保护
class ChangePasswordEmailForm(FlaskForm):
    submit = SubmitField('发送重置密码邮件')


# 【新增】：管理员编辑用户信息表单
class AdminEditUserForm(FlaskForm):
    username = StringField('用户名', validators=[
        DataRequired(), Length(min=2, max=32)
    ])
    email = StringField('邮箱', validators=[
        Optional(), Email()
    ])
    submit = SubmitField('保存更改')

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(AdminEditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user is not None:
                raise ValidationError('该用户名已被占用')

    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('该邮箱已被占用')