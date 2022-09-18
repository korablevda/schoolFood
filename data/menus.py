import sqlalchemy
from .db_session import SqlAlchemyBase
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from wtforms.fields.html5 import DateField


class Menu(SqlAlchemyBase):
    __tablename__ = 'menus'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    date = sqlalchemy.Column(sqlalchemy.Date, nullable=True)
    dishes = sqlalchemy.Column(sqlalchemy.String, nullable=False, default='[]')


class MenuForm(FlaskForm):

    name = StringField('Наименование', validators=[DataRequired()])
    date = DateField('Дата', validators=[DataRequired()])
    submit_edit = SubmitField('Сохранить')
