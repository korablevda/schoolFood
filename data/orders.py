import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy import orm
from flask_wtf import FlaskForm
from wtforms import SubmitField, SelectField, StringField
from wtforms.validators import DataRequired
from wtforms.fields.html5 import DateField
import datetime


class Order(SqlAlchemyBase):
    __tablename__ = 'orders'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    date_begin = sqlalchemy.Column(sqlalchemy.Date, default=datetime.datetime.now)
    date_end = sqlalchemy.Column(sqlalchemy.Date, default=datetime.datetime.now)
    user_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"))
    user = orm.relation('User')


class OrdersForm(FlaskForm):

    date_begin = DateField('Начало действия', validators=[DataRequired()])
    date_end = DateField('Окончание действия', validators=[DataRequired()])
    user = StringField('Ученик', validators=[DataRequired()])
    submit_edit = SubmitField('Сохранить')
