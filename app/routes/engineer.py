from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from app import db, models
import inspect
from datetime import datetime
import os
from sqlalchemy import text
# 导入任务函数
from app.tasks import update_reservation_status, check_overdue_records

bp = Blueprint('engineer', __name__, url_prefix='/engineer')


# --- 装饰器：验证 Session 标记 ---
def engineer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查 session 中是否有 is_engineer 标记
        if not session.get('is_engineer'):
            flash('会话已过期或未授权，请验证身份', 'warning')
            return redirect(url_for('engineer.login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


# --- 辅助函数：获取所有模型 ---
def get_all_models():
    """获取所有模型类，返回字典 {'Item': class Item, ...}"""
    model_list = {}
    for name, obj in inspect.getmembers(models):
        if inspect.isclass(obj) and hasattr(obj, '__tablename__'):
            model_list[name] = obj
    return model_list


def get_model_by_name(name):
    """
    【核心修复】根据 URL 中的名称查找对应的 Model 类
    解决 'items' 找不到 'Item' 模型的问题
    """
    # 1. 尝试直接通过映射表查找 (匹配前端硬编码的链接)
    mapping = {
        'items': models.Item,
        'reservations': models.Reservation,
        'records': models.Record,
        'users': models.User,
        'spaces': models.Space  # 【新增】添加空间表映射
    }
    if name in mapping:
        return mapping[name]

    # 2. 如果没找到，尝试通过类名查找 (兼容旧逻辑)
    all_models = get_all_models()
    return all_models.get(name)


# --- 路由 ---

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('is_engineer'):
        return redirect(url_for('engineer.dashboard'))

    if request.method == 'POST':
        password = request.form.get('password')
        # 获取 Config 中的 ENGINEER_ACCESS_KEY
        access_key = current_app.config.get('ENGINEER_ACCESS_KEY')

        if password and password == access_key:
            session['is_engineer'] = True
            session.permanent = True  # 保持会话
            flash('权限验证成功 - 工程师模式已激活', 'success')

            next_page = request.args.get('next')
            return redirect(next_page or url_for('engineer.dashboard'))
        else:
            flash('无效的访问密钥', 'danger')

    return render_template('engineer/login.html')


@bp.route('/logout')
def logout():
    session.pop('is_engineer', None)
    flash('已退出工程师模式', 'info')
    return redirect(url_for('main.index'))


@bp.route('/dashboard')
@engineer_required
def dashboard():
    # 获取所有模型用于可能的动态展示
    models_map = get_all_models()
    tables = sorted(models_map.keys())
    return render_template('engineer/dashboard.html', tables=tables)


# --- 【补回功能】SQL 控制台 ---
@bp.route('/sql', methods=['POST'])
@engineer_required
def sql_console():
    """只读 SQL 控制台"""
    sql = request.form.get('sql', '').strip()
    result = None
    error = None

    if sql:
        # 安全检查：仅允许 SELECT 语句
        if not sql.lower().startswith('select'):
            error = "安全警告：工程模式仅允许执行 SELECT 查询语句！"
        else:
            try:
                # 使用 SQLAlchemy 执行原生 SQL
                with db.engine.connect() as conn:
                    result_proxy = conn.execute(text(sql))
                    keys = result_proxy.keys()
                    data = result_proxy.fetchall()
                    result = {'keys': keys, 'data': data}
            except Exception as e:
                error = f"SQL 执行错误: {str(e)}"

    return render_template('engineer/dashboard.html', active_tab='sql', sql=sql, result=result, error=error)


# --- 【补回功能】查看日志 ---
@bp.route('/logs')
@engineer_required
def view_logs():
    """实时日志查看器"""
    log_path = current_app.config.get('LOG_FILE_PATH')
    # 如果配置中没写，尝试默认路径
    if not log_path:
        log_path = os.path.join(os.getcwd(), 'logs', 'app.log')

    lines = []

    if log_path and os.path.exists(log_path):
        try:
            # 使用 utf-8 读取，并忽略错误
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            lines = all_lines[-200:]  # 读取最后 200 行
            lines.reverse()
        except Exception as e:
            lines = [f"读取日志失败: {str(e)}"]
    else:
        lines = [f"日志文件不存在: {log_path or '未配置路径'}"]

    return render_template('engineer/dashboard.html', active_tab='logs', logs=lines)


# --- 【补回功能】手动触发任务 ---
@bp.route('/trigger/<task_name>', methods=['POST'])
@engineer_required
def trigger_task(task_name):
    """手动触发后台任务"""
    try:
        if task_name == 'update_reservation_status':
            update_reservation_status()
            flash('任务 [预约状态流转] 已手动触发执行', 'success')
        elif task_name == 'check_overdue':
            check_overdue_records()
            flash('任务 [逾期检查] 已手动触发执行', 'success')
        else:
            flash(f'未知任务: {task_name}', 'warning')
    except Exception as e:
        flash(f'任务执行异常: {str(e)}', 'danger')
        current_app.logger.error(f"手动触发任务失败: {e}")

    return redirect(url_for('engineer.dashboard'))


# --- 数据表管理 ---

# 【修复】函数名改回 view_table，参数改为 model_name 以匹配 table_view.html
@bp.route('/table/<model_name>')
@engineer_required
def view_table(model_name):
    # 【修复】使用 get_model_by_name 处理 'items' -> Item 的映射
    model = get_model_by_name(model_name)

    if not model:
        flash(f'模型 {model_name} 不存在', 'danger')
        return redirect(url_for('engineer.dashboard'))

    page = request.args.get('page', 1, type=int)
    try:
        pagination = model.query.paginate(page=page, per_page=20, error_out=False)
        items = pagination.items
    except Exception as e:
        flash(f'查询错误: {str(e)}', 'danger')
        items = []
        pagination = None

    columns = [c.key for c in model.__table__.columns]

    return render_template('engineer/table_view.html',
                           model_name=model_name,  # 传回 model_name 给模板用
                           columns=columns,
                           items=items,
                           pagination=pagination)


@bp.route('/table/<model_name>/edit/<int:id>', methods=['GET', 'POST'])
@engineer_required
def edit_record(model_name, id):
    # 【修复】使用 get_model_by_name
    model = get_model_by_name(model_name)

    if not model:
        flash(f'模型 {model_name} 不存在', 'danger')
        return redirect(url_for('engineer.dashboard'))

    item = model.query.get_or_404(id)
    columns = model.__table__.columns

    if request.method == 'POST':
        try:
            for column in columns:
                if column.primary_key:
                    continue

                value = request.form.get(column.key)

                if value == '' and column.nullable:
                    value = None

                if value is not None:
                    python_type = column.type.python_type
                    try:
                        if python_type is bool:
                            if isinstance(value, str):
                                value = value.lower() in ('true', '1', 'on', 'yes')
                        elif python_type is int:
                            value = int(value)
                        elif python_type is float:
                            value = float(value)
                        elif python_type is datetime:
                            try:
                                value = datetime.strptime(value, '%Y-%m-%dT%H:%M')
                            except ValueError:
                                try:
                                    value = datetime.strptime(value, '%Y-%m-%d')
                                except ValueError:
                                    try:
                                        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                                    except ValueError:
                                        pass
                    except (ValueError, TypeError):
                        print(f"转换字段 {column.key} 失败: {value}")
                        continue

                try:
                    setattr(item, column.key, value)
                except AttributeError:
                    continue

            db.session.commit()
            flash(f'{model_name} [ID:{id}] 更新成功', 'success')
            # 【修复】重定向使用 model_name 和 view_table
            return redirect(url_for('engineer.view_table', model_name=model_name))
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败: {str(e)}', 'danger')

    return render_template('engineer/record_edit.html',
                           model_name=model_name,
                           item=item,
                           columns=columns)


@bp.route('/table/<model_name>/delete/<int:id>', methods=['POST'])
@engineer_required
def delete_record(model_name, id):
    # 【修复】使用 get_model_by_name
    model = get_model_by_name(model_name)

    if not model:
        flash(f'模型 {model_name} 不存在', 'danger')
        return redirect(url_for('engineer.dashboard'))

    item = model.query.get_or_404(id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash(f'记录 [ID:{id}] 已被永久删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败: {str(e)}', 'danger')

    # 【修复】重定向使用 model_name 和 view_table
    return redirect(url_for('engineer.view_table', model_name=model_name))