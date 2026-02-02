from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime

from app import db
from app.forms.record_forms import RecordCreateForm, RecordReturnForm
from app.models import Item, Record, Space, User, Reservation

bp = Blueprint('records', __name__)


@bp.route('/my')
@login_required
def my_records():
    """查看当前用户的使用记录（分页）"""
    page = request.args.get('page', 1, type=int)
    per_page = 10  # 每页显示10条

    status = request.args.get('status', '')
    item_name = request.args.get('item_name', '').strip()

    # 基础查询：当前用户的记录
    records_query = current_user.records

    # 筛选：物品名称（模糊查询）
    if item_name:
        records_query = records_query.join(Item).filter(Item.name.ilike(f'%{item_name}%'))

    # 筛选：状态
    if status:
        records_query = records_query.filter(Record.status == status)

    records_query = records_query.order_by(Record._utc_start_time.desc())

    # 使用 paginate 代替 all
    pagination = records_query.paginate(page=page, per_page=per_page, error_out=False)
    records = pagination.items

    return render_template('records/my_records.html', records=records, pagination=pagination)


@bp.route('/all')
@login_required
def all_records():
    """管理员查看所有使用记录（分页）"""
    if not current_user.is_admin():
        flash('没有权限查看所有记录')
        return redirect(url_for('records.my_records'))

    page = request.args.get('page', 1, type=int)
    per_page = 15  # 管理员界面每页显示更多

    # 获取筛选参数
    username = request.args.get('username', '').strip()
    item_name = request.args.get('item_name', '').strip()
    status = request.args.get('status', '')

    records_query = Record.query

    # 联表查询：用户名
    if username:
        records_query = records_query.join(User).filter(User.username.ilike(f'%{username}%'))

    # 联表查询：物品名
    if item_name:
        records_query = records_query.join(Item).filter(Item.name.ilike(f'%{item_name}%'))

    # 筛选：状态
    if status:
        records_query = records_query.filter(Record.status == status)

    records_query = records_query.order_by(Record._utc_start_time.desc())

    # 使用 paginate
    pagination = records_query.paginate(page=page, per_page=per_page, error_out=False)
    records = pagination.items

    return render_template('records/all_records.html', records=records, pagination=pagination)


@bp.route('/item/<int:item_id>')
@login_required
def item_records(item_id):
    """查看特定物品的使用记录（分页）"""
    page = request.args.get('page', 1, type=int)
    per_page = 10

    username = request.args.get('username', '').strip()
    status = request.args.get('status', '')

    item = Item.query.get_or_404(item_id)
    records_query = Record.query.filter_by(item_id=item_id)

    # 筛选：用户名
    if username:
        records_query = records_query.join(User).filter(User.username.ilike(f'%{username}%'))

    # 筛选：状态（虽然通常看物品记录不太需要筛选状态，但保留功能更灵活）
    if status:
        records_query = records_query.filter(Record.status == status)

    records_query = records_query.order_by(Record._utc_start_time.desc())

    pagination = records_query.paginate(page=page, per_page=per_page, error_out=False)
    records = pagination.items

    return render_template('records/item_records.html', records=records, item=item, pagination=pagination)


@bp.route('/create/<int:item_id>', methods=['GET', 'POST'])
@login_required
def create(item_id):
    """创建使用记录（借用物品）"""
    item = Item.query.get_or_404(item_id)
    form = RecordCreateForm()

    # 【新增逻辑】：如果是管理员，加载用户列表供选择
    if current_user.is_admin():
        # 获取所有用户 (id, username)，用于填充下拉框
        users = User.query.with_entities(User.id, User.username).all()
        # 添加 "ALL" 选项，ID设为 -1
        form.target_user.choices = [(-1, '所有用户 (ALL)')] + [(u.id, u.username) for u in users]

        # 默认选中当前管理员自己（如果在 GET 请求中没有指定）
        if request.method == 'GET' and not form.target_user.data:
            form.target_user.data = [current_user.id]

    # 状态检查逻辑优化：
    if not current_user.is_admin():
        user_reservation = Reservation.query.filter_by(
            item_id=item.id,
            user_id=current_user.id
        ).filter(
            Reservation.status.in_(['active', 'scheduled'])
        ).first()

        # 检查物品状态
        if item.status == 'available':
            pass
        elif item.status == 'reserved':
            if not user_reservation or user_reservation.status != 'active':
                flash(f'物品 "{item.name}" 已被其他用户预约，当前不可借用。', 'warning')
                return redirect(url_for('items.view', id=item_id))
        else:
            flash(f'物品 "{item.name}" 当前不可用，状态：{item.status}', 'danger')
            return redirect(url_for('items.view', id=item_id))

    if form.validate_on_submit():
        # 【修改】：确定最终的借用人 ID 列表
        target_user_ids = []

        if current_user.is_admin():
            selected_data = form.target_user.data
            if selected_data:
                # 检查是否选择了 "ALL" (-1)
                if -1 in selected_data:
                    all_users = User.query.with_entities(User.id).all()
                    target_user_ids = [u.id for u in all_users]
                else:
                    target_user_ids = selected_data
            else:
                # 管理员没选任何人，默认自己
                target_user_ids = [current_user.id]
        else:
            # 普通用户只能是自己
            target_user_ids = [current_user.id]

        created_count = 0

        # 遍历用户列表创建记录
        for user_id in target_user_ids:
            # 再次验证用户是否存在
            borrower = User.query.get(user_id)
            if not borrower:
                continue

            # 查找该用户是否有相关预约（为了消耗预约）
            user_res = Reservation.query.filter_by(
                item_id=item.id,
                user_id=user_id
            ).filter(
                Reservation.status.in_(['active', 'scheduled'])
            ).first()

            # 创建使用记录
            record = Record(
                item_id=item_id,
                user_id=user_id,
                space_path=item.space.get_path(),
                usage_location=form.usage_location.data,
                status='using'
            )

            # 消耗预约
            if user_res:
                user_res.status = 'used'

            db.session.add(record)
            created_count += 1

        if created_count > 0:
            # 更新物品状态
            item.status = 'borrowed'
            db.session.add(item)
            db.session.commit()

            if created_count == 1 and target_user_ids[0] == current_user.id:
                flash(f'成功借用物品 "{item.name}"', 'success')
            else:
                flash(f'已成功为 {created_count} 位用户创建借用记录', 'success')
        else:
            flash('未创建任何记录', 'warning')

        return redirect(url_for('items.view', id=item_id))

    return render_template('records/create.html', form=form, item=item)


@bp.route('/return/<int:record_id>', methods=['GET', 'POST'])
@login_required
def return_item(record_id):
    """归还物品"""
    record = Record.query.get_or_404(record_id)

    # 检查权限
    if not current_user.is_admin() and record.user_id != current_user.id:
        flash('没有权限执行此操作')
        return redirect(url_for('items.view', id=record.item_id))

    # 检查记录状态
    if record.status != 'using':
        flash('该物品已归还')
        return redirect(url_for('items.view', id=record.item_id))

    form = RecordReturnForm()
    if form.validate_on_submit() or request.method == 'POST':
        # 更新记录状态
        record.status = 'returned'
        record._utc_return_time = datetime.utcnow()
        # record.notes ... (同上，Record 没有 notes 字段，不更新)

        # 【修改逻辑】：只有当该物品没有其他正在进行的借用记录时，才将物品状态设为 available
        # 查询该物品其他 'using' 状态的记录（排除当前这条）
        other_active_count = Record.query.filter(
            Record.item_id == record.item_id,
            Record.status == 'using',
            Record.id != record.id
        ).count()

        if other_active_count == 0:
            # 只有没有其他人使用时，才释放物品
            item = record.item
            item.status = 'available'
        else:
            # 否则保持 borrowed 状态
            pass

        db.session.commit()

        if other_active_count == 0:
            flash(f'成功归还物品 "{record.item.name}"，物品已变更为可用状态。')
        else:
            flash(f'已结束您的使用记录，但物品 "{record.item.name}" 仍被其他 {other_active_count} 人使用中。')

        return redirect(url_for('items.view', id=record.item.id))

    return render_template('records/return.html', form=form, record=record)


@bp.route('/delete/<int:record_id>', methods=['POST'])
@login_required
def delete(record_id):
    """删除使用记录（仅管理员），删除后返回“所有记录”页面并保留筛选状态"""
    # 1. 权限检查：仅管理员可执行
    if not current_user.is_admin():
        flash('没有权限删除使用记录', 'danger')
        return redirect(
            url_for('records.all_records', status=request.args.get('status'), page=request.args.get('page')))

    # 2. 查询要删除的记录
    record = Record.query.get_or_404(record_id)

    # 3. 记录删除信息（用于日志或提示，可选）
    item_name = record.item.name

    # 【修改】：如果该记录是“使用中”，则在删除前检查是否释放物品
    reset_msg = ""
    if record.status == 'using':
        # 核心修复：查询同一物品下，状态为 using 且不是当前这条记录的数量
        other_active_count = Record.query.filter(
            Record.item_id == record.item_id,
            Record.status == 'using',
            Record.id != record.id
        ).count()

        if other_active_count == 0:
            # 没有其他人在用，可以释放
            record.item.status = 'available'
            reset_msg = "，同时物品状态已重置为“可用”"
        else:
            # 还有其他人在用，不改变物品状态
            reset_msg = f"，但物品仍被其他 {other_active_count} 人使用中，状态保持为“正在使用”"

    # 4. 执行删除操作
    db.session.delete(record)
    db.session.commit()

    flash(f'成功删除物品「{item_name}」的使用记录{reset_msg}', 'success')

    # 关键改动：重定向到“所有记录”页面，并将当前的筛选状态传递回去
    return redirect(url_for(
        'records.all_records',
        status=request.args.get('status'),
        username=request.args.get('username'),
        item_name=request.args.get('item_name'),
        page=request.args.get('page')
    ))