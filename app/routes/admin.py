from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User
from app.utils import super_admin_required
from app.forms.auth_forms import AdminEditUserForm

# 此蓝图用于处理“系统级”管理功能
# 普通的物品管理在 items.py，空间管理在 spaces.py
bp = Blueprint('admin', __name__)


@bp.route('/users')
@login_required
@super_admin_required
def user_management():
    """
    【超级管理员专属】用户管理界面
    功能：查看所有用户，任免普通管理员
    """
    page = request.args.get('page', 1, type=int)
    # 按ID排序展示
    users = User.query.order_by(User.id.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template('auth/user_management.html', users=users)


@bp.route('/users/promote/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def promote_admin(user_id):
    """
    将普通用户提升为管理员
    """
    user = User.query.get_or_404(user_id)

    # 安全检查：如果已经是超管，无需操作
    if user.is_super_admin():
        flash('该用户是系统超级管理员，无需提升权限', 'warning')
        return redirect(url_for('admin.user_management'))

    if user.role == 'admin':
        flash(f'用户 {user.username} 已经是管理员了', 'info')
    else:
        user.role = 'admin'
        db.session.commit()
        flash(f'已将用户 {user.username} 提升为管理员 (Admin)', 'success')

    return redirect(url_for('admin.user_management'))


@bp.route('/users/demote/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def demote_admin(user_id):
    """
    撤销管理员权限，降级为普通用户
    """
    user = User.query.get_or_404(user_id)

    # 核心保护：绝对禁止降级超级管理员（即使他在数据库里的role可能被误标为admin）
    # 超级管理员的身份由环境变量决定，数据库role不影响is_super_admin的判断，但为了逻辑清晰，我们阻止对超管的操作
    if user.is_super_admin():
        flash('操作失败：无法对超级管理员 (Root) 执行降级操作', 'danger')
        return redirect(url_for('admin.user_management'))

    if user.role == 'user':
        flash(f'用户 {user.username} 已经是普通用户了', 'info')
    else:
        user.role = 'user'
        db.session.commit()
        flash(f'已撤销用户 {user.username} 的管理员权限', 'warning')

    return redirect(url_for('admin.user_management'))


@bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_user(user_id):
    """
    【新增】超级管理员修改用户信息
    """
    user = User.query.get_or_404(user_id)

    # 禁止修改其他超级管理员的信息（防止误操作，或根据需求自行调整）
    if user.is_super_admin() and user.id != current_user.id:
        flash('无法修改其他超级管理员的信息', 'warning')
        return redirect(url_for('admin.user_management'))

    form = AdminEditUserForm(original_username=user.username, original_email=user.email, obj=user)

    if form.validate_on_submit():
        # 【修改点】：检查邮箱是否发生了变化
        if user.email != form.email.data:
            user.email = form.email.data
            # 如果邮箱变了，强制重置验证状态为 False
            user.email_verified = False
            flash(f'检测到邮箱变更，用户 {user.username} 的邮箱验证状态已重置为“未验证”。', 'warning')

        user.username = form.username.data

        db.session.commit()
        flash(f'用户 {user.username} 的信息已更新', 'success')
        return redirect(url_for('admin.user_management'))

    return render_template('auth/admin_edit_user.html', form=form, user=user)


@bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def delete_user(user_id):
    """
    【新增】超级管理员删除用户
    """
    user = User.query.get_or_404(user_id)

    if user.is_super_admin():
        flash('严重错误：无法删除超级管理员账号', 'danger')
        return redirect(url_for('admin.user_management'))

    if user.id == current_user.id:
        flash('无法删除自己', 'warning')
        return redirect(url_for('admin.user_management'))

    # 记录用户名用于提示
    username = user.username

    # 执行删除 (数据库外键设置为 Set Null 或 SQLAlchemy 默认行为会处理关联)
    db.session.delete(user)
    db.session.commit()

    flash(f'用户 {username} 已被永久删除', 'success')
    return redirect(url_for('admin.user_management'))