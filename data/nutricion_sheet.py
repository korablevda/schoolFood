from flask_wtf import FlaskForm
from wtforms import SubmitField, StringField
from wtforms.validators import DataRequired
from wtforms.fields.html5 import DateField


class NutritionSheetForm(FlaskForm):

    date = DateField('Выбор даты ', validators=[DataRequired()])
    submit_edit = SubmitField('Сформировать')
