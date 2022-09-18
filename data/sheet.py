import datetime
import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy import orm
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, SelectMultipleField
from wtforms.validators import DataRequired


class Sheet(SqlAlchemyBase):
    __tablename__ = 'sheets'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    group_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("groups.id"))
    created_date = sqlalchemy.Column(sqlalchemy.DATE, default=datetime.date.today())
    users = sqlalchemy.Column(sqlalchemy.String, default='[]')
    users_privilege = sqlalchemy.Column(sqlalchemy.String, default='[]')
    group = orm.relation('Group')
    status = sqlalchemy.Column(sqlalchemy.String, default='Не выгружена')


class SheetForm(FlaskForm):

    users = SelectMultipleField('Учащиеся класса')
    users_selected = SelectMultipleField('Будут питаться')
    users_privilege = SelectMultipleField('Список льготников')
    users_privilege_selected = SelectMultipleField('Будут питаться (льготники)')
    submit_edit = SubmitField('Сохранить')
