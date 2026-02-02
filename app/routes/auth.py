from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.urls import urlsplit
from app import db, mail
from app.models import User
from app.forms.auth_forms import (
    LoginForm, RegistrationForm, ResetPasswordRequestForm,
    ResetPasswordForm, ChangeUsernameForm, AddEmailForm, ChangePasswordEmailForm
)
from app.email import send_password_reset_email
from flask_mail import Message

bp = Blueprint('auth', __name__)


# 辅助函数：发送验证邮件
def send_verification_email(user):
    token = user.get_email_verification_token()

    # 【修复】：根据 config.py 获取正确的发件人配置
    # config.py 中定义了 FLASKY_MAIL_SENDER 作为发件人
    sender = current_app.config.get('FLASKY_MAIL_SENDER')

    # 保底逻辑：如果没有配置 FLASKY_MAIL_SENDER，尝试使用 MAIL_USERNAME
    if not sender:
        sender = current_app.config.get('MAIL_USERNAME')

    # 最后的默认值
    if not sender:
        sender = 'no-reply@localhost'

    msg = Message('[物品管理系统] 请验证您的邮箱',
                  sender=sender,
                  recipients=[user.email])
    msg.body = f'''请点击以下链接验证您的邮箱地址：
{url_for('auth.verify_email', token=token, _external=True)}

如果您没有发出此请求，请忽略本邮件。
'''
    mail.send(msg)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('无效的用户名或密码')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.index')
        return redirect(next_page)

    return render_template('auth/login.html', title='登录', form=form)


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data if form.email.data else None

        # --- 获取配置中的管理员列表 ---
        # config.py 中定义了 FLASKY_ADMIN
        admin_emails_config = current_app.config.get('FLASKY_ADMIN')
        admin_list = []
        if admin_emails_config:
            if isinstance(admin_emails_config, str):
                admin_list = [e.strip() for e in admin_emails_config.split(',')]
            else:
                admin_list = admin_emails_config
        # -----------------------------

        if email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash(f'邮箱「{email}」已被注册，请直接登录', 'warning')
                return redirect(url_for('auth.login'))

        is_config_admin = email in admin_list if email else False

        user = User(
            username=form.username.data,
            email=email,
            role='admin' if is_config_admin else 'user'
        )
        user.email_verified = False

        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
            if is_config_admin:
                flash(f'🎉 超级管理员账号注册成功！', 'success')
            else:
                flash(f'✅ 注册成功！', 'success')

            login_user(user)
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            flash(f'❌ 注册失败：{str(e)}', 'danger')

    return render_template('auth/register.html', title='注册', form=form)


@bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('请检查您的邮箱，获取密码重置链接')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_request.html',
                           title='重置密码', form=form)


@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('main.index'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('您的密码已重置')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)


@bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', title='个人中心')


@bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if not current_user.email:
        flash('您必须先绑定邮箱才能修改密码。', 'warning')
        return redirect(url_for('auth.manage_email'))

    if not current_user.email_verified:
        flash('请先验证您的邮箱地址。', 'warning')
        return redirect(url_for('auth.manage_email'))

    # 【修复】：实例化表单用于CSRF验证
    form = ChangePasswordEmailForm()
    if form.validate_on_submit():
        send_password_reset_email(current_user)
        flash(f'重置密码链接已发送至 {current_user.email}，请查收。', 'success')
        return redirect(url_for('auth.profile'))

    # 【修复】：传入form变量
    return render_template('auth/change_password.html', title='修改密码', form=form)


@bp.route('/change_username', methods=['GET', 'POST'])
@login_required
def change_username():
    form = ChangeUsernameForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        db.session.commit()
        flash('您的用户名已更新。', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/change_username.html', title='修改用户名', form=form)


@bp.route('/manage_email', methods=['GET', 'POST'])
@login_required
def manage_email():
    form = AddEmailForm()
    if request.method == 'GET' and current_user.email:
        form.email.data = current_user.email

    if form.validate_on_submit():
        if current_user.email != form.email.data:
            current_user.email = form.email.data
            current_user.email_verified = False
            db.session.commit()

        send_verification_email(current_user)
        flash('验证邮件已发送！请检查您的收件箱。', 'success')
        return redirect(url_for('main.index'))

    return render_template('auth/manage_email.html', form=form, title='验证邮箱')


@bp.route('/verify_email/<token>')
def verify_email(token):
    if current_user.is_authenticated and current_user.email_verified:
        flash('您的邮箱已验证。', 'info')
        return redirect(url_for('main.index'))

    user = User.verify_email_token(token)
    if not user:
        flash('验证链接无效或已过期。', 'danger')
        return redirect(url_for('main.index'))

    user.email_verified = True
    db.session.commit()
    flash('谢谢！您的邮箱验证成功。', 'success')
    return redirect(url_for('main.index'))