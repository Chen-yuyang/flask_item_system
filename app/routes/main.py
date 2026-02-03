from datetime import datetime

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
# 【修改】：导入 User 模型以支持联表查询
from app.models import Item, Record, Reservation, Space, User
from app.routes.spaces import get_space_hierarchy

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    if current_user.is_authenticated:
        # 正确代码：使用原始数据库字段_utc_start_time
        recent_records = current_user.records.order_by(Record._utc_start_time.desc()).limit(5).all()

        # 获取当前用户的有效预约
        my_reservations = current_user.reservations.filter(
            Reservation.status == 'active',
            Reservation._utc_reservation_end >= datetime.utcnow()
        ).order_by(Reservation._utc_reservation_start).limit(5).all()

        return render_template('main/index.html',
                               recent_records=recent_records,
                               my_reservations=my_reservations)
    return render_template('main/index.html')


@bp.route('/search')
@login_required
def global_search():
    query = request.args.get('query', '')
    results = {
        'items': [],
        'records': [],
        'spaces': []
    }

    if query:
        # 搜索物品
        results['items'] = Item.query.filter(
            (Item.name.ilike(f'%{query}%') |
             Item.function.ilike(f'%{query}%') |
             Item.serial_number.ilike(f'%{query}%'))
        ).all()

        # 搜索记录
        # 【修改】：联表查询 User，增加按用户名搜索的条件
        results['records'] = Record.query.join(User).filter(
            (Record.usage_location.ilike(f'%{query}%') |
             Record.space_path.ilike(f'%{query}%') |
             User.username.ilike(f'%{query}%'))
        ).all()

        # 搜索空间
        results['spaces'] = Space.query.filter(
            Space.name.ilike(f'%{query}%')
        ).all()

    total_results = len(results['items']) + len(results['records']) + len(results['spaces'])

    return render_template('main/search_results.html',
                           query=query,
                           results=results,
                           total_results=total_results)