from flask import render_template, current_app  # 导入current_app
from flask_mail import Message
from threading import Thread
from app import mail  # 只导入mail实例


def send_async_email(app, msg):
    """异步发送邮件"""
    with app.app_context():
        mail.send(msg)


def send_email(to, subject, template, **kwargs):
    """发送邮件的通用函数"""
    # 使用current_app获取配置，避免直接引用app实例
    msg = Message(
        subject=current_app.config['MAIL_SUBJECT_PREFIX'] + subject,
        sender=current_app.config['MAIL_SENDER'],
        recipients=[to]
    )
    msg.html = render_template(template, **kwargs)

    # 获取当前应用实例
    app = current_app._get_current_object()
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr


def send_password_reset_email(user):
    """发送密码重置邮件"""
    token = user.get_reset_password_token()
    send_email(
        user.email,
        '密码重置',
        'auth/email/reset_password.html',
        user=user,
        token=token
    )


def send_overdue_reminder(record, recipient_type='user'):
    """发送逾期提醒邮件"""
    from app.models import User
    from datetime import datetime
    import pytz

    if recipient_type == 'user':
        recipient = record.user.email
        subject = '物品逾期提醒'
    else:
        admin = User.query.filter_by(is_admin=True).first()
        if not admin:
            return
        recipient = admin.email
        subject = f'用户 {record.user.username} 的物品已逾期'

    # 计算逾期天数（使用UTC时间进行计算，避免时区问题）
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    start_time_utc = record._utc_start_time.replace(tzinfo=pytz.utc)
    overdue_days = (now_utc - start_time_utc).days - 10

    send_email(
        recipient,
        subject,
        'records/email/overdue_reminder.html',
        record=record,
        recipient_type=recipient_type,
        overdue_days=overdue_days
    )
