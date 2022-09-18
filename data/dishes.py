import sqlalchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

from .db_session import SqlAlchemyBase


class Dish(SqlAlchemyBase):
    __tablename__ = 'dishes'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    code = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    cost = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    id_1c = sqlalchemy.Column(sqlalchemy.String, nullable=True)


class DishForm(FlaskForm):

    code = StringField('Код', validators=[DataRequired()])
    name = StringField('Наименование', validators=[DataRequired()])
    cost = StringField("Стоимость", validators=[DataRequired()])
    submit_edit = SubmitField('Сохранить')
