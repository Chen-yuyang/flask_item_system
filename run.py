import os
import click
from app import create_app, db
from app.models import Record
from app.email import send_overdue_reminder

# 核心：读取 FLASK_CONFIG 环境变量，默认值为 'default'
# FLASK_CONFIG 值对应 config.py 的 config 字典键：development/production/testing/docker
config_name = os.environ.get('FLASK_CONFIG', 'default')
app = create_app(config_name)


@app.cli.command("init-db")
def init_db():
    """初始化数据库"""
    with app.app_context():  # 新增：推送上下文（避免db操作无上下文）
        db.drop_all()
        db.create_all()
    click.echo('数据库已初始化')


@app.cli.command("check-overdue")
def manual_check_overdue():
    """手动检查逾期记录（保留手动触发的功能）"""
    with app.app_context():
        from datetime import datetime, timedelta
        overdue_records = Record.query.filter(
            Record.status == 'using',
            Record.start_time < datetime.utcnow() - timedelta(days=10)
        ).all()

        for record in overdue_records:
            send_overdue_reminder(record)
    click.echo('已检查逾期记录并发送提醒')


if __name__ == '__main__':
    # debug 由配置类自动决定（DevelopmentConfig=True，ProductionConfig=False）
    app.run(host="0.0.0.0", port=8080, debug=app.config['DEBUG'])