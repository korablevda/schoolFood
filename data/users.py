import datetime
import sqlalchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import orm
from .db_session import SqlAlchemyBase
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField, SelectField
from wtforms.fields.html5 import DateField
from wtforms.validators import DataRequired


class User(SqlAlchemyBase, UserMixin):
    __tablename__ = 'users'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    name = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    kode_1c = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    id_1c = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    card_number = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    login = sqlalchemy.Column(sqlalchemy.String, index=True, unique=True, nullable=True)
    hashed_password = sqlalchemy.Column(sqlalchemy.String, nullable=True)
    created_date = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.now)
    level = sqlalchemy.Column(sqlalchemy.Integer, nullable=True)
    group_id = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("groups.id"))
    will_eat = sqlalchemy.Column(sqlalchemy.Boolean, default=False)
    group = orm.relation('Group')
    orders = orm.relation("Order", back_populates='user')

    def __repr__(self):
        return f'<User> {self.id} {self.name} {self.login}'

    def set_password(self, password):
        self.hashed_password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.hashed_password, password)


class BaseUserForm(FlaskForm):
    name = StringField('Имя пользователя', validators=[DataRequired()])
    card_number = StringField('Номер карты', validators=[DataRequired()])
    group_id = SelectField('Класс', validators=[DataRequired()])
    level = SelectField('Роль', choices=[('0', 'ученик'), ('1', 'Классный руководитель'), ('2', 'администратор')], validators=[DataRequired()])
    submit = SubmitField('Зарегистрировать')
    submit_edit = SubmitField('Сохранить')


class UserForm(BaseUserForm):
    login = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    password_again = PasswordField('Повторите пароль', validators=[DataRequired()])


class LkForm(FlaskForm):
    date_begin = DateField('Начало периода', validators=[DataRequired()])
    date_end = DateField('Конец периода', validators=[DataRequired()])
    submit = SubmitField('Показать')
