from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from app import db, models
import inspect
from datetime import datetime

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
    model_list = {}
    # 自动扫描 app.models 中的所有 SQLAlchemy 模型类
    for name, obj in inspect.getmembers(models):
        if inspect.isclass(obj) and hasattr(obj, '__tablename__'):
            model_list[name] = obj
    return model_list


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

    # 使用独立的 layout，防止 base.html 报错
    return render_template('engineer/login.html')


@bp.route('/logout')
def logout():
    session.pop('is_engineer', None)
    flash('已退出工程师模式', 'info')
    return redirect(url_for('main.index'))


@bp.route('/dashboard')
@engineer_required
def dashboard():
    models_map = get_all_models()
    tables = sorted(models_map.keys())
    return render_template('engineer/dashboard.html', tables=tables)


@bp.route('/table/<model_name>')
@engineer_required
def view_table(model_name):
    models_map = get_all_models()
    model = models_map.get(model_name)

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
                           model_name=model_name,
                           columns=columns,
                           items=items,
                           pagination=pagination)


@bp.route('/table/<model_name>/edit/<int:id>', methods=['GET', 'POST'])
@engineer_required
def edit_record(model_name, id):
    models_map = get_all_models()
    model = models_map.get(model_name)

    if not model:
        flash(f'模型 {model_name} 不存在', 'danger')
        return redirect(url_for('engineer.dashboard'))

    item = model.query.get_or_404(id)
    columns = model.__table__.columns

    if request.method == 'POST':
        try:
            for column in columns:
                # 1. 跳过主键修改
                if column.primary_key:
                    continue

                # 2. 获取表单数据
                value = request.form.get(column.key)

                # 3. 处理空值 (空字符串且列允许为空)
                if value == '' and column.nullable:
                    value = None

                # 4. 类型转换逻辑
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
                                        # 如果日期格式都不匹配，保持原样，可能会在commit时报错
                                        pass
                    except (ValueError, TypeError):
                        # 如果类型转换失败，打印日志并跳过，防止整个请求崩溃
                        print(f"转换字段 {column.key} 失败: {value}")
                        continue

                # 5. 安全赋值 (修复 property has no setter 错误)
                try:
                    setattr(item, column.key, value)
                except AttributeError:
                    # 如果该属性是只读的（比如定义了 @property 但没有 setter），则跳过
                    print(f"跳过只读属性: {column.key}")
                    continue

            db.session.commit()
            flash(f'{model_name} [ID:{id}] 更新成功', 'success')
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
    models_map = get_all_models()
    model = models_map.get(model_name)

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

    return redirect(url_for('engineer.view_table', model_name=model_name))