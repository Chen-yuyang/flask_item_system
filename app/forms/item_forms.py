from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError, Optional
from app.models import Item, Space


class ItemForm(FlaskForm):
    # 显式添加 csrf_token 类型提示（不影响实际功能，仅用于 IDE 识别）
    csrf_token: StringField  # 关键：告诉 IDE 该字段存在

    name = StringField('物品名称', validators=[
        DataRequired(), Length(min=1, max=100)
    ])
    serial_number = StringField('物品编号', validators=[
        DataRequired(), Length(min=1, max=50)
    ])
    function = TextAreaField('功能描述',validators=[DataRequired()])
    status = SelectField('状态', choices=[
        ('available', '可用'),
        ('borrowed', '正在使用'),
        ('reserved', '已预约')
    ], validators=[Optional()])
    space_id = SelectField('所属空间', coerce=int, validators=[DataRequired()])
    submit = SubmitField('保存')

    def __init__(self, item_id=None, *args, **kwargs):
        super(ItemForm, self).__init__(*args, **kwargs)
        self.space_id.choices = [(space.id, space.get_path()) for space in Space.query.all()]
        self.item_id = item_id

    def validate_serial_number(self, serial_number):
        item = Item.query.filter_by(serial_number=serial_number.data).first()
        if item is not None and item.id != self.item_id:
            raise ValidationError('该编号已被使用，请使用其他编号')
