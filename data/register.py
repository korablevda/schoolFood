from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired


class RegisterForm(FlaskForm):

    login = StringField('Логин', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    password_again = PasswordField('Повторите пароль', validators=[DataRequired()])
    name = StringField('Имя пользователя', validators=[DataRequired()])
    card_number = StringField('Номер карты', validators=[DataRequired()])
    group_id = SelectField('Класс', validators=[DataRequired()])
    level = SelectField('Роль', choices=[('0', 'ученик'), ('1', 'Классный руководитель'), ('2', 'администратор')], validators=[DataRequired()])
    submit = SubmitField('Зарегистрировать')
    submit_edit = SubmitField('Сохранить')


class LoginForm(FlaskForm):

    login = StringField('Логин(номер карты без нулей)', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')


class ChangePassForm(FlaskForm):

    password = PasswordField('Пароль', validators=[DataRequired()])
    password_again = PasswordField('Повторите пароль', validators=[DataRequired()])
    submit = SubmitField('Сохранить')
