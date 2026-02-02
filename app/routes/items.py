import os
import io
import zipfile
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user
from datetime import datetime

from app import db
from app.models import Item, Space, Record, Reservation
from app.forms.item_forms import ItemForm

from app.utils import generate_and_save_item_qrcode

bp = Blueprint('items', __name__)


@bp.route('/')
@login_required
def all_items():
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    per_page = 15  # 每页显示15条

    query = request.args.get('query', '').strip()
    status = request.args.get('status', '')

    items_query = Item.query

    # 应用搜索条件
    if query:
        items_query = items_query.filter(
            (Item.name.ilike(f'%{query}%') |
             Item.function.ilike(f'%{query}%') |
             Item.serial_number.ilike(f'%{query}%'))
        )

    # 应用状态筛选
    if status:
        items_query = items_query.filter(Item.status == status)

    # 默认按 ID 排序，确保分页顺序稳定
    items_query = items_query.order_by(Item.id.asc())

    # 使用 paginate
    pagination = items_query.paginate(page=page, per_page=per_page, error_out=False)
    # 【修复】：这里不要把 items 赋值为列表，因为模板里 items 既被当做列表迭代，也被当做 pagination 对象使用
    # 为了兼容您的模板 items.pages, items.has_prev 等用法，我们需要传递 pagination 对象给模板的 items 变量
    # 或者修改模板。鉴于您的要求是不改风格，我们传递 pagination 给 items 变量（因为 pagination 对象也是可迭代的）

    return render_template('items/all_items.html', items=pagination, pagination=pagination)


@bp.route('/<int:id>')
@login_required
def view(id):
    item = Item.query.get_or_404(id)

    # 获取当前借用记录（如果有）
    current_record = Record.query.filter_by(
        item_id=id,
        status='using'
    ).first()

    # 获取最近的使用记录
    recent_records = Record.query.filter_by(item_id=id).order_by(Record._utc_start_time.desc()).limit(5).all()

    # 获取当前有效的预约（用于展示给管理员或提示冲突）
    active_reservations = Reservation.query.filter_by(
        item_id=id,
        status='active'
    ).filter(
        Reservation._utc_reservation_start <= datetime.utcnow(),
        Reservation._utc_reservation_end >= datetime.utcnow()
    ).all()

    # 判断当前用户是否有权借用
    user_can_use = False
    if item.status == 'available':
        user_can_use = True
    elif item.status == 'reserved':
        # 检查是否存在属于当前用户的active预约
        my_active_res = Reservation.query.filter_by(
            item_id=id,
            user_id=current_user.id,
            status='active'
        ).first()
        if my_active_res:
            user_can_use = True

    return render_template('items/view.html',
                           item=item,
                           current_record=current_record,
                           recent_records=recent_records,
                           active_reservations=active_reservations,
                           user_can_use=user_can_use)


@bp.route('/create/<int:space_id>', methods=['GET', 'POST'])
@login_required
def create(space_id):
    # 只有管理员可以创建物品
    if not current_user.is_admin():
        flash('没有权限创建物品')
        return redirect(url_for('spaces.view', id=space_id))

    space = Space.query.get_or_404(space_id)
    form = ItemForm()
    form.space_id.data = space_id

    if form.validate_on_submit():
        item = Item(
            name=form.name.data,
            serial_number=form.serial_number.data,
            function=form.function.data,
            status='available',
            space_id=space_id,
            created_by=current_user.id
        )
        db.session.add(item)
        db.session.commit()  # 首次提交：获取item.id

        # 生成并保存二维码（修改：传入item对象）
        qr_path = generate_and_save_item_qrcode(item)
        item.barcode_path = qr_path  # 保存路径到物品记录
        db.session.commit()  # 二次提交：保存二维码路径

        flash(f'物品 "{item.name}" 创建成功，二维码已生成')
        return redirect(url_for('spaces.view', id=space_id))

    return render_template('items/edit.html',
                           title='创建物品',
                           form=form,
                           space=space)


@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    # 只有管理员可以编辑物品
    if not current_user.is_admin():
        flash('没有权限编辑物品')
        return redirect(url_for('items.view', id=id))

    item = Item.query.get_or_404(id)
    form = ItemForm(item_id=id, obj=item)

    if form.validate_on_submit():
        item.name = form.name.data
        item.serial_number = form.serial_number.data
        item.function = form.function.data
        item.status = form.status.data
        item.space_id = form.space_id.data

        db.session.commit()  # 先保存名称更改

        # 补全二维码逻辑 (修改：传入item对象)
        if not item.barcode_path:
            qr_path = generate_and_save_item_qrcode(item)
            item.barcode_path = qr_path
            db.session.commit()  # 保存二维码路径
            flash(f'已自动为物品 "{item.name}" 补全二维码', 'info')

        flash(f'物品 "{item.name}" 更新成功')
        return redirect(url_for('items.view', id=id))

    return render_template('items/edit.html',
                           title='编辑物品',
                           form=form,
                           item=item)


@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    # 只有管理员可以删除物品
    if not current_user.is_admin():
        flash('没有权限删除物品')
        return redirect(url_for('items.view', id=id))

    item = Item.query.get_or_404(id)
    space_id = item.space_id

    db.session.delete(item)
    db.session.commit()
    flash(f'物品 "{item.name}" 已删除')

    return redirect(url_for('spaces.view', id=space_id))


# 二维码批量操作路由
@bp.route('/batch_qr', methods=['POST'])
@login_required
def batch_qr_action():
    if not current_user.is_admin():
        flash('没有权限执行此操作', 'danger')
        return redirect(request.referrer or url_for('items.all_items'))

    action = request.form.get('action')
    item_ids = request.form.getlist('item_ids')

    if not item_ids:
        flash('请先选择需要操作的物品', 'warning')
        return redirect(request.referrer or url_for('items.all_items'))

    items = Item.query.filter(Item.id.in_(item_ids)).all()

    if action == 'generate':
        # 批量生成/重新生成
        count = 0
        for item in items:
            qr_path = generate_and_save_item_qrcode(item)
            item.barcode_path = qr_path
            count += 1
        db.session.commit()
        flash(f'成功为 {count} 个物品生成了二维码', 'success')

    elif action == 'download':
        # 批量打包下载
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in items:
                # 检查二维码是否存在，不存在则生成
                full_path = None
                if item.barcode_path:
                    full_path = os.path.join(current_app.root_path, 'static', item.barcode_path)

                if not full_path or not os.path.exists(full_path):
                    item.barcode_path = generate_and_save_item_qrcode(item)
                    db.session.commit()
                    full_path = os.path.join(current_app.root_path, 'static', item.barcode_path)

                # 获取文件名放入压缩包
                arcname = os.path.basename(item.barcode_path)
                zf.write(full_path, arcname)

        memory_file.seek(0)
        return send_file(
            memory_file,
            download_name=f'qrcodes_{datetime.now().strftime("%Y%m%d%H%M")}.zip',
            as_attachment=True
        )

    return redirect(request.referrer or url_for('items.all_items'))