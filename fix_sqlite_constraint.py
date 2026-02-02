from app import create_app, db
from sqlalchemy import text

# 创建应用上下文
app = create_app()


def fix_database():
    """
    专门用于修复 SQLite 无法通过常规迁移删除 UNIQUE 约束的问题。
    原理：
    1. 将现有的 item 表重命名为备份表。
    2. 根据最新的 models.py (已移除 unique=True) 创建全新的 item 表。
    3. 将数据从备份表导回新表。
    4. 删除备份表。
    """
    print("=== 开始修复 SQLite 数据库结构 ===")

    with app.app_context():
        try:
            # 1. 检查是否存在残留的备份表，如果有则清理
            db.session.execute(text("DROP TABLE IF EXISTS _item_backup"))

            # 2. 将现有 item 表重命名为 _item_backup
            print("1. 正在备份旧表数据...")
            db.session.execute(text("ALTER TABLE item RENAME TO _item_backup"))

            # 3. 创建新表
            # db.create_all() 会检测并创建不存在的表。
            # 因为 item 表刚才被改名了，所以这里会根据 models.py 的新定义（无 unique 约束）创建新 item 表。
            print("2. 正在创建新表结构（已移除唯一约束）...")
            db.create_all()

            # 4. 迁移数据
            # 必须列出所有列名以确保对应正确
            columns = "id, name, function, serial_number, status, barcode_path, space_id, created_by, created_at, updated_at"
            print("3. 正在恢复数据...")
            db.session.execute(text(f"INSERT INTO item ({columns}) SELECT {columns} FROM _item_backup"))

            # 5. 删除备份表
            print("4. 正在清理临时文件...")
            db.session.execute(text("DROP TABLE _item_backup"))

            db.session.commit()
            print("\n✅ 修复成功！现在你可以添加重复的 '-' 编号了。")

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 修复失败: {str(e)}")
            print("尝试回滚中...")
            try:
                # 尝试恢复原状
                db.session.execute(text("ALTER TABLE _item_backup RENAME TO item"))
                db.session.commit()
                print("已回滚到初始状态。")
            except:
                print("回滚失败，请手动检查数据库。")


if __name__ == "__main__":
    fix_database()