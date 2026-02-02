from flask_migrate import migrate, upgrade
from app import create_app, db
import sys

# 创建应用上下文
app = create_app()


def update_database():
    print("=== 开始更新数据库结构 ===")
    with app.app_context():
        try:
            # 1. 生成迁移脚本 (相当于 flask db migrate -m "update auth schema")
            print("1. 正在检测模型变更并生成迁移脚本...")
            migrate(message="update auth schema")

            # 2. 应用迁移 (相当于 flask db upgrade)
            print("2. 正在将变更应用到数据库...")
            upgrade()

            print("\n✅ 数据库更新成功！")

        except Exception as e:
            print(f"\n❌ 更新过程中发生错误: {str(e)}")
            print("提示：如果错误提示 'alembic_version' 相关问题，请检查 migrations 文件夹是否完整。")


if __name__ == "__main__":
    update_database()
