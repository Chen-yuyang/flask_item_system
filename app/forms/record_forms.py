from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, Optional


class RecordCreateForm(FlaskForm):
    # 【新增】：管理员代办功能，选择实际使用人
    # coerce=int 确保提交的ID是整数
    # Optional() 允许非管理员提交时此字段为空，validate_choice=False 允许在视图中动态填充选项
    target_user = SelectField('使用用户（仅管理员）', coerce=int, validators=[Optional()], validate_choice=False)

    usage_location = StringField('使用地点', validators=[
        DataRequired(), Length(min=1, max=255)
    ])
    notes = TextAreaField('备注（可选）')
    submit = SubmitField('确认使用')


class RecordReturnForm(FlaskForm):
    notes = TextAreaField('归还备注（可选）')
    submit = SubmitField('确认归还')