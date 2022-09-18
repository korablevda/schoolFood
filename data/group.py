import sqlalchemy
from .db_session import SqlAlchemyBase
from sqlalchemy import orm
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired


class Group(SqlAlchemyBase):
    __tablename__ = 'groups'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    id_1c = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    users = orm.relation("User", back_populates='group')
    sheets = orm.relation("Sheet", back_populates='group')


class GroupForm(FlaskForm):

    id_1c = StringField('Код группы в 1с', validators=[DataRequired()])
    name = StringField('Наименование', validators=[DataRequired()])
    submit_edit = SubmitField('Сохранить')
