from pprint import pprint
from flask import Flask, render_template, redirect, request, Response
from flask_login import LoginManager, login_user, current_user, login_required, logout_user
from flask_restful import abort
import requests
import json
from data import db_session
from data.paynment import Paynment
from data.dishes import Dish, DishForm
from data.register import LoginForm, RegisterForm, ChangePassForm
from data.users import User, UserForm, BaseUserForm, LkForm
from data.group import Group, GroupForm
from data.menus import Menu, MenuForm
from data.orders import Order, OrdersForm
from data.sheet import Sheet, SheetForm
from data.nutricion_sheet import NutritionSheetForm
from datetime import datetime, date, timedelta, time
from apscheduler.schedulers.background import BackgroundScheduler
import os
import qrcode
import calendar
import locale
import xml.etree.ElementTree as ET


locale.setlocale(locale.LC_ALL, "")
# адреса серверов 1с и учетные данные для доступа к данным
SERVER_1C_B = 'http://localhost/Bufet/odata/standard.odata/'
SERVER_1C_F = 'http://localhost/Food/odata/standard.odata/'
ACCOUNT_1C = ('login', 'pass')
# коды неиспользуемых групп справочника лицевых счетов в 1с
MISS_GROUP = ['100001181 ', '200001596 ', '100000893 ', '200001597 ', '200001732 ']
app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)
app.config['SECRET_KEY'] = 'super_puper_secret_key'
db_session.global_init("db/db.sqlite")
# пул адресов банка, с которых можно принимать запросы на подтверждение онлайн-платежей пополнения счета
VALID_IP = []
for i in range(25):
    VALID_IP.append('194.186.207.'+str(i))
for i in range(25):
    VALID_IP.append('194.54.14.'+str(i))
# добавим возможность использовать функцию len в шаблонах jinja
app.jinja_env.globals.update(len=len)


@login_manager.user_loader
def load_user(user_id):
    session = db_session.create_session()
    return session.query(User).get(user_id)


def get_qr(code):
    # возвращаем адрес(или формируем новый) картинки с QR-кодом для пополнения лицевого счета
    number_card = ('000000000' + str(code))[-9:]
    filename = number_card + '.png'
    fullname = os.path.join('static/qrcodes', filename)
    if not os.path.isfile(fullname):
        data = f'ST00011|Name=[Название ОУ]"|' \
               f'PersonalAcc=[номер счета]|' \
               f'BankName=[наименование банка]"|' \
               f'BIC=[БИК ]|' \
               f'CorrespAcc=[номер счета]|' \
               f'PayeeINN=[идентификатор платежа]|' \
               f'PersAcc={number_card}|' \
               f'CATEGORY=1|'
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(fullname)
    return fullname


def sched_upload_sheets():
    # функция выгрузки заявок на питание в автоматическом режиме
    session = db_session.create_session()
    sheets = session.query(Sheet).filter(Sheet.created_date == date.today())
    for sheet in sheets:
        if sheet.status == 'Не выгружена':
            message = json.dumps(main_upload_sheet(sheet.id))
            sheet.status = message
            session.commit()


def sched_update_dishes():
    # обновление блюд и их стомости из 1с в автоматическом режиме
    session_db = db_session.create_session()
    url = SERVER_1C_B + 'Catalog_Номенклатура?$format=application/json&$filter=IsFolder eq false'
    session = requests.Session()
    session.auth = ACCOUNT_1C
    response = session.get(url, verify=False)
    for elem in json.loads(response.text)['value']:
        if elem['DeletionMark']:
            continue
        id_1c = elem['Ref_Key']
        dish = session_db.query(Dish).filter(Dish.id_1c == id_1c).first()
        if not dish:
            dish = Dish()
        dish.name = elem['Description']
        dish.code = elem['Code']
        dish.cost = 0
        dish.id_1c = elem['Ref_Key']
        session_db.add(dish)
        session_db.commit()


def sched_update_menus():
    # обновление меню из 1с в автоматическом режиме
    session_db = db_session.create_session()
    data = str(date.today() + timedelta(days=1)) + 'T00:00:00'
    url = f"{SERVER_1C_F}Document_Питание_Калькуляция?$format=application/json&$filter=Date ge datetime'{data}'&$expand=ВидКалькуляции"
    session = requests.Session()
    session.auth = ACCOUNT_1C
    response = session.get(url, verify=False)
    menu_json = json.loads(response.text)['value']
    for dok in menu_json:
        menu_name = dok['ВидКалькуляции']['Description']
        date_dok = [int(x) for x in dok['Date'][:10].split('-')]
        menu_date = datetime(date_dok[0], date_dok[1], date_dok[2]).date()
        menu = session_db.query(Menu).filter(Menu.name == menu_name, Menu.date == menu_date).first()
        if not menu:
            menu = Menu()
        menu.name = menu_name
        menu.date = menu_date
        dishes_kod = {}
        for t_dish in dok['Блюда']:
            url = f"{SERVER_1C_F}Catalog_Питание_Блюда?$format=application/json&$filter=Ref_Key eq guid'{t_dish['Блюдо_Key']}'"
            response = session.get(url, verify=False)
            t_json = json.loads(response.text)['value']
            dishes_kod[t_json[0]['Description']] = t_dish['ПродажнаяЦена']
        dishes = []
        for elem in dishes_kod.keys():
            v_dish = session_db.query(Dish).filter(Dish.name == elem).first()
            if v_dish:
                dishes.append(v_dish.id)
                v_dish.cost = dishes_kod[v_dish.name]
        menu.dishes = json.dumps(dishes)
        session_db.add(menu)
        session_db.commit()


def sched_update_users():
    # обновление пользователей из 1с в автоматическом режиме
    session_db = db_session.create_session()
    url = f'{SERVER_1C_B}Catalog_ЛС?$format=application/json&$filter=IsFolder eq false&$expand=Parent'
    session = requests.Session()
    session.auth = ACCOUNT_1C
    response = session.get(url, verify=False)
    for elem in json.loads(response.text)['value']:
        if elem['Code'] == '000000000':
            continue
        if elem['DeletionMark']:
            continue
        if elem['Parent']['Code'] in MISS_GROUP:
            continue
        login_t = str(int(elem['Коды'][0]['Код']))
        user_login = session_db.query(User).filter(User.login == login_t).first()
        ref_key = elem['Ref_Key']
        user = session_db.query(User).filter(User.id_1c == ref_key).first()
        if user:
            if user.login[0] in '1234567890':
                if user.login != login_t:
                    if user_login:
                        user_login.login = login_t + 'del' + str(datetime.today())
                        session_db.commit()
                    user.login = login_t
                user.name = elem['Description'].strip()
                user.card_number = ('000000000' + str(int(elem['Коды'][0]['Код'])))[-9:]
                session_db.commit()
        else:
            group_admin = session_db.query(Group).filter(Group.id_1c == elem['Parent']['Code']).first()
            user = User()
            user.name = elem['Description'].strip()
            user.login = login_t
            user.level = 0
            user.group = group_admin
            user.set_password(str(int(elem['Коды'][0]['Код'])))
            user.card_number = ('000000000' + str(int(elem['Коды'][0]['Код'])))[-9:]
            user.kode_1c = elem['Code']
            user.id_1c = elem['Ref_Key']
            group_admin.users.append(user)
            session_db.merge(group_admin)
            session_db.commit()


def get_balance(guid):
    # получение баланса лицевого счета из 1С
    session_1с = requests.Session()
    session_1с.auth = ACCOUNT_1C
    url = f"{SERVER_1C_B}AccumulationRegister_ОстаткиЛС/Balance(" \
          f"Dimensions='ЛС', " \
          f"Condition=ЛС_Key eq guid'{guid}'" \
          f")" \
          f"?$format=application/json"
    response = json.loads(session_1с.get(url, verify=False).text)
    balance = '0.0'
    if len(response['value']) > 0:
        balance = response['value'][0]['СуммаBalance']
    return balance


def main_upload_sheet(id):
    # выгрузка заявки на организованное питание от класса в 1С
    answer = ''
    session = db_session.create_session()
    sheet = session.query(Sheet).filter(Sheet.id == id).first()
    group = session.query(Group).filter(Group.id == sheet.group.id).first()
    data = dict()
    session_1c = requests.Session()
    session_1c.auth = ACCOUNT_1C
    url = f"{SERVER_1C_B}Catalog_Подразделения?$format=application/json&$filter=Description eq '{group.name}'"
    response = session_1c.get(url, verify=False)
    json_resp = json.loads(response.text)
    '''Сформируем json с данными по организованному питанию'''
    data['Date'] = str(sheet.created_date) + 'T09:30:00'
    data['Подразделение_Key'] = json_resp['value'][0]['Ref_Key']
    data['Номенклатура_Key'] = '660c6ab4-a801-11e6-8488-bcaec528c105'
    data['МестоХранения_Key'] = json_resp['value'][0]['МестоХранения_Key']
    data['Смена_Key'] = '00000000-0000-0000-0000-000000000000'
    data['Оператор_Key'] = '506a0afa-b5fa-11e5-b4c9-bcaec528c105'
    data['ГруппаНоменклатуры_Key'] = '7d6c3dac-7051-11e6-9b64-bcaec528c105'
    data['Состав'] = []
    count = 0
    for kod in json.loads(sheet.users):
        temp = dict()
        count += 1
        user = session.query(User).filter(User.id == int(kod)).first()
        temp['ЛС_Key'] = user.id_1c
        temp['LineNumber'] = str(count)
        if float(get_balance(user.id_1c)) >= 50.0:
            temp['ОтметкаОПолучении'] = True
        else:
            temp['ОтметкаОПолучении'] = False
        temp['ИсточникФинансирования_Key'] = '769fdb0c-c2ec-470b-92a5-692cdde3471f'
        data['Состав'].append(temp)
    if len(data['Состав']) > 0:
        url_post = f"{SERVER_1C_B}Document_РаздаточныйЛист?$format=application/json"
        response = session_1c.post(url_post, json=data)
        if response.status_code == 201:
            answer = 'OK'
        else:
            answer = str(response.status_code)
    '''Сформируем json с данными по льготному питанию, изменится несколько полей'''
    data['ГруппаНоменклатуры_Key'] = '7d6c3ddb-7051-11e6-9b64-bcaec528c105'
    data['Состав'] = []
    count = 0
    for kod in json.loads(sheet.users_privilege):
        temp = dict()
        count += 1
        user = session.query(User).filter(User.id == int(kod)).first()
        temp['ЛС_Key'] = user.id_1c
        temp['LineNumber'] = str(count)
        temp['ОтметкаОПолучении'] = True
        temp['ИсточникФинансирования_Key'] = 'c489b6e7-2271-4a17-9d90-f56e9e6d0d33'
        data['Состав'].append(temp)
    if len(data['Состав']) > 0:
        url_post = f"{SERVER_1C_B}Document_РаздаточныйЛист?$format=application/json"
        response = session_1c.post(url_post, json=data)
        if response.status_code == 201:
            answer += ';OK'
        else:
            answer += ';' + str(response.status_code)
    return answer


@app.route('/register', methods=['GET', 'POST'])
def register():
    # обработчик регистрации пользователей, почти не используется - пользователи переносятся из 1С автоматически
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = RegisterForm()
    session = db_session.create_session()
    group_list = list()
    for elem in session.query(Group).all():
        group_list.append((str(elem.id), elem.name))
    form.group_id.choices = group_list
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Пароли не совпадают")
        if session.query(User).filter(User.login == form.login.data).first():
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Такой пользователь уже есть")
        if session.query(User).filter(User.card_number == int(form.card_number.data)).first():
            return render_template('register.html', title='Регистрация',
                                   form=form,
                                   message="Такой номер карты уже есть")
        user = User()
        user.name = form.name.data
        user.login = form.login.data
        user.card_number = int(form.card_number.data)
        group_user = session.query(Group).filter(Group.id == int(form.group_id.data)).first()
        user.group = group_user
        user.group_id = group_user.id
        user.level = int(form.level.data)
        user.set_password(form.password.data)
        session.add(user)
        session.commit()
        return redirect('/users')
    return render_template('register.html', title='Регистрация', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    # обработчик страница авторизации
    form = LoginForm()
    if form.validate_on_submit():
        session = db_session.create_session()
        user = session.query(User).filter(User.login == form.login.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            return redirect("/")
        return render_template('login.html',
                               message="Неправильный логин или пароль",
                               form=form)
    return render_template('login.html', title='Авторизация', form=form)


@app.route('/change_pass/<int:id>', methods=['GET', 'POST'])
@login_required
def change_pass(id):
    # обработчик страницы смены пароля
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.id != id:
        return redirect('/')
    session = db_session.create_session()
    user = session.query(User).filter(User.id == id).first()
    if user:
        form = ChangePassForm()
        form.login = user.login
        if form.validate_on_submit():
            if form.password.data != form.password_again.data:
                return render_template('change_pass.html', title='Изменение пароля',
                                       form=form,
                                       message="Пароли не совпадают", user=user)
            user.set_password(form.password.data)
            session.add(user)
            session.commit()
            return redirect('/lk')
        return render_template('change_pass.html', title='Изменение пароля',
                               form=form, user=user,
                               message="")
    else:
        abort(404)


@app.route("/")
@app.route("/index")
def index():
    # обработчик главной страницы, отображаются меню за последние 3 дня
    if current_user.is_authenticated:
        session = db_session.create_session()
        menus = session.query(Menu).filter(Menu.date > (datetime.today() - timedelta(days=3)))
        menus = menus.order_by(Menu.date.desc())
        return render_template("index.html", menus=menus)
    else:
        return redirect('/login')


@app.route("/admin")
def admin():
    # обработчик панели управления приложением
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        return render_template("admin.html")
    else:
        return redirect('/login')


@app.route("/lk", methods=['GET', 'POST'])
def lk():
    # обработчик страницы личного кабинета пользователя
    session = db_session.create_session()
    session_1с = requests.Session()
    session_1с.auth = ACCOUNT_1C
    if current_user.is_authenticated:
        form = LkForm()
        balance = get_balance(current_user.id_1c)
        rec_list = []
        if request.method == 'POST':
            date_begin = str(form.date_begin.data) + 'T00:00:00'
            date_end = str(form.date_end.data) + 'T23:59:59'
            url = f"{SERVER_1C_B}AccumulationRegister_ОстаткиЛС_RecordType?" \
                  f"$format=application/json&" \
                  f"$filter=Period ge datetime'{date_begin}' and Period le datetime'{date_end}' and ЛС_Key eq guid'{current_user.id_1c}'&" \
                  f"$expand=Recorder"
            response = json.loads(session_1с.get(url, verify=False).text)
            if 'value' in response:
                for rec in response['value']:
                    row = dict()
                    if 'Товар' in rec['Recorder_Expanded']:
                        row['period'] = rec['Period'][:10]
                        row['dok'] = 'Чек №' + rec['Recorder_Expanded']['Number']
                        row['dishes'] = []
                        for elem in rec['Recorder_Expanded']['Товар']:
                            dish_id = elem['Номенклатура_Key']
                            dish = session.query(Dish).filter(Dish.id_1c == dish_id).first()
                            if dish:
                                row['dishes'].append([dish.name, elem['Количество'], elem['Сумма']])
                            else:
                                row['dishes'].append(('<неизвестно>', elem['Количество'], elem['Сумма']))
                        row['sum'] = '-' + str(rec['Сумма'])
                        row['len'] = len(row['dishes'])
                        row['color'] = '#DC143C'
                    else:
                        row['period'] = rec['Period'][:10]
                        row['dok'] = 'Сбор денег №' + rec['Recorder_Expanded']['Number']
                        row['dishes'] = []
                        row['sum'] = '+' + str(rec['Сумма'])
                        row['len'] = len(row['dishes'])
                        row['color'] = '#228B22'
                    rec_list.append(row)
        return render_template("lk.html", balance=balance, form=form, rec_list=rec_list, qr=get_qr(current_user.card_number))
    else:
        return redirect('/login')


@app.route('/will_eat/<int:id>', methods=['GET', 'POST'])
@login_required
def will_eat(id):
    # обработчик кнопки согласия на участие в организованном питании
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.id != id:
        return redirect('/')
    session = db_session.create_session()
    user = session.query(User).filter(User.id == id).first()
    if user:
        user.will_eat = True
        session.commit()
        return redirect('/')
    else:
        abort(404)


@app.route('/not_will_eat/<int:id>', methods=['GET', 'POST'])
@login_required
def not_will_eat(id):
    # обработчик кнопки отказа от участия в организованном питании
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.id != id:
        return redirect('/')
    session = db_session.create_session()
    user = session.query(User).filter(User.id == id).first()
    if user:
        user.will_eat = False
        session.commit()
        return redirect('/')
    else:
        abort(404)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect("/")


@app.route("/users")
@login_required
def users():
    # обработчик страницы со списком пользователей
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        users = session.query(User)
        users = users.order_by(User.name)
        return render_template("users.html", users=users)
    else:
        return redirect('/login')


@app.route('/user/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    # обработчик страницы редактирования пользователя, открывается со страницы класса, меняются не все поля
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = BaseUserForm()
    session = db_session.create_session()
    group_list = list()
    for elem in session.query(Group).all():
        group_list.append((str(elem.id), elem.name))
    form.group_id.choices = sorted(group_list, key=lambda x: x[1])
    if request.method == "GET":
        user = session.query(User).filter(User.id == id).first()
        if user:
            form.name.data = user.name
            form.group_id.data = str(user.group_id)
            form.level.data = str(user.level)
            form.card_number.data = str(user.card_number)
        else:
            abort(404)
    if form.validate_on_submit():
        t_user = session.query(User).filter(User.card_number == int(form.card_number.data)).first()
        if t_user and t_user.id != id:
            return render_template('register.html', title='Редактирование пользователя',
                                   form=form,
                                   message="Такой номер карты уже используется")
        user = session.query(User).filter(User.id == id).first()
        if user:
            user.name = form.name.data
            user.card_number = int(form.card_number.data)
            group_user = session.query(Group).filter(Group.id == int(form.group_id.data)).first()
            user.group = group_user
            user.group_id = group_user.id
            user.level = int(form.level.data)
            session.commit()
            return redirect('/users')
        else:
            abort(404)
    return render_template('user.html', title='Редактирование пользователя', form=form)


@app.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
def full_edit_user(id):
    # обработчик страницы редактирования всех свойств пользователя
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = UserForm()
    session = db_session.create_session()
    group_list = list()
    for elem in session.query(Group).all():
        group_list.append((str(elem.id), elem.name))
    form.group_id.choices = group_list
    if request.method == "GET":
        user = session.query(User).filter(User.id == id).first()
        if user:
            form.name.data = user.name
            form.login.data = user.login
            form.group_id.data = str(user.group_id)
            form.level.data = str(user.level)
            form.card_number.data = str(user.card_number)
        else:
            abort(404)
    if form.validate_on_submit():
        if form.password.data != form.password_again.data:
            return render_template('user.html', title='Ошибка!',
                                   form=form,
                                   message="Пароли не совпадают")
        t_user = session.query(User).filter(User.card_number == int(form.card_number.data)).first()
        if t_user and t_user.id != id:
            return render_template('register.html', title='Редактирование пользователя',
                                   form=form,
                                   message="Такой номер карты уже используется")
        user = session.query(User).filter(User.id == id).first()
        if user:
            user.name = form.name.data
            user.login = form.login.data
            user.card_number = int(form.card_number.data)
            group_user = session.query(Group).filter(Group.id == int(form.group_id.data)).first()
            user.group = group_user
            user.group_id = group_user.id
            user.level = int(form.level.data)
            user.set_password(form.password.data)
            session.commit()
            return redirect('/users')
        else:
            abort(404)
    return render_template('edit_user.html', title='Редактирование пользователя', form=form)


@app.route('/user_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def user_delete(id):
    # обработчик удаления пользователя
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    user = session.query(User).filter(User.id == id).first()
    if user:
        session.delete(user)
        session.commit()
    else:
        abort(404)
    return redirect('/users')


@app.route("/dishes")
@login_required
def dishes():
    # обработчик страницы со списком блюд
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        dishes = session.query(Dish)
        dishes = dishes.order_by(Dish.name)
        return render_template("dishes.html", dishes=dishes)
    else:
        return redirect('/login')


@app.route('/dish_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def dish_delete(id):
    # обработчик страницы удаления блюда
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    dish = session.query(Dish).filter(Dish.id == id).first()
    if dish:
        session.delete(dish)
        session.commit()
    else:
        abort(404)
    return redirect('/dishes')


@app.route('/dish/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_dish(id):
    # обработчик страницы редактирования блюд
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = DishForm()
    session = db_session.create_session()
    if request.method == "GET":
        dish = session.query(Dish).filter(Dish.id == id).first()
        if dish:
            form.code.data = dish.code
            form.name.data = dish.name
            form.cost.data = dish.cost
        else:
            abort(404)
    if form.validate_on_submit():
        t_dish = session.query(Dish).filter(Dish.code == form.code.data).first()
        if t_dish and t_dish.id != id:
            return render_template('dish.html', title='Редактирование блюда',
                                   form=form,
                                   message="Такой код блюда уже используется")
        dish = session.query(Dish).filter(Dish.id == id).first()
        if dish:
            dish.name = form.name.data
            dish.code = form.code.data
            dish.cost = form.cost.data
            session.commit()
            return redirect('/dishes')
        else:
            abort(404)
    return render_template('dish.html', title='Редактирование блюда', form=form)


@app.route("/groups")
@login_required
def groups():
    # обработчик страницы со списком групп (классов)
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        groups = session.query(Group)
        groups = groups.order_by(Group.name)
        return render_template("groups.html", groups=groups)
    else:
        return redirect('/login')


@app.route('/group_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def group_delete(id):
    # обработчик страницы удаления группы (класса)
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    group = session.query(Group).filter(Group.id == id).first()
    if group:
        if len(group.users) == 0:
            session.delete(group)
            session.commit()
        else:
            return render_template('groups.html', message="Список учащихся группы не пуст, удаление невозможно!")
    else:
        abort(404)
    return redirect('/groups')


@app.route('/group/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_group(id):
    # обработчик страницы редактирования группы (класса)
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = GroupForm()
    session = db_session.create_session()
    if request.method == "GET":
        group = session.query(Group).filter(Group.id == id).first()
        if group:
            form.id_1c.data = group.id_1c
            form.name.data = group.name
            users = sorted(list(group.users), key=lambda x: x.name)
        else:
            abort(404)
    if form.validate_on_submit():
        t_group = session.query(Group).filter(Group.id_1c == form.id_1c.data).first()
        if t_group and t_group.id != id:
            return render_template('register.html', title='Редактирование группы',
                                   form=form,
                                   message="Такой код группы уже используется")
        group = session.query(Group).filter(Group.id == id).first()
        if group:
            group.name = form.name.data
            group.id_1c = form.id_1c.data
            session.commit()
            return redirect('/groups')
        else:
            abort(404)
    return render_template('group.html', title='Редактирование группы', form=form, users=users)


@app.route("/menus")
@login_required
def menus():
    # обработчик страницы со списком меню
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        menus = session.query(Menu)
        menus = menus.order_by(Menu.date.desc())
        return render_template("menus.html", menus=menus)
    else:
        return redirect('/login')


@app.route('/menu_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def menu_delete(id):
    # обработчик страницы удаления меню
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    menu = session.query(Menu).filter(Menu.id == id).first()
    if menu:
        session.delete(menu)
        session.commit()
    else:
        abort(404)
    return redirect('/menus')


@app.route('/menu/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_menu(id):
    # обработчик страницы редактирования меню
    if not current_user.is_authenticated:
        return redirect('/login')
    form = MenuForm()
    session = db_session.create_session()
    if request.method == "GET":
        menu = session.query(Menu).filter(Menu.id == id).first()
        if menu:
            form.date.data = menu.date
            form.name.data = menu.name
            dishes_cods = json.loads(menu.dishes)
            dishes = []
            for kod in dishes_cods:
                dish = session.query(Dish).filter(Dish.id == int(kod)).first()
                if dish:
                    dishes.append(dish)
            dishes.sort(key=lambda x: x.name)
        else:
            abort(404)
    if form.validate_on_submit():
        menu = session.query(Menu).filter(Menu.id == id).first()
        if menu:
            menu.name = form.name.data
            menu.date = form.date.data
            session.commit()
            return redirect('/menus')
        else:
            abort(404)
    return render_template('menu.html', title='Редактирование меню', form=form, dishes=dishes, menu=menu)


@app.route("/orders")
@login_required
def orders():
    # обработчик страницы со списком приказов на льготное (бесплатное) питание
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        orders = session.query(Order)
        orders = orders.order_by(Order.date_begin.desc())
        return render_template("orders.html", orders=orders)
    else:
        return redirect('/login')


@app.route('/register_order', methods=['GET', 'POST'])
def register_order():
    # обработчик страницы создания приказа на льготное (бесплатное) питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = OrdersForm()
    session = db_session.create_session()
    user_list = []
    for elem in session.query(User).all():
        user_list.append(elem.name)
    user_list.sort()
    if form.validate_on_submit():
        order = Order()
        order.date_begin = form.date_begin.data
        order.date_end = form.date_end.data
        t_user = session.query(User).filter(User.name == str(form.user.data)).first()
        if t_user:
            order.user = t_user
            order.user_id = t_user.id
            session.add(order)
            session.commit()
            return redirect('/orders')
        else:
            abort(404)
    return render_template('register_order.html', title='Новый приказ', form=form, users=user_list)


@app.route('/edit_order/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_order(id):
    # обработчик страницы редактирования приказа на льготное (бесплатное) питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = OrdersForm()
    session = db_session.create_session()
    user_list = []
    for elem in session.query(User).all():
        user_list.append(elem.name)
    user_list.sort()
    if request.method == "GET":
        order = session.query(Order).filter(Order.id == id).first()
        if order:
            form.date_begin.data = order.date_begin
            form.date_end.data = order.date_end
            form.user.data = order.user.name
        else:
            abort(404)
    if form.validate_on_submit():
        order = session.query(Order).filter(Order.id == id).first()
        if order:
            order.date_begin = form.date_begin.data
            order.date_end = form.date_end.data
            t_user = session.query(User).filter(User.name == str(form.user.data)).first()
            if t_user:
                order.user = t_user
                order.user_id = t_user.id
                session.add(order)
                session.commit()
                return redirect('/orders')
            else:
                abort(404)
        else:
            abort(404)
    return render_template('register_order.html', title='Редактирование приказа', form=form, users=user_list)


@app.route('/order_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def order_delete(id):
    # обработчик страницы удаления приказа на льготное (бесплатное) питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    order = session.query(Order).filter(Order.id == id).first()
    if order:
        session.delete(order)
        session.commit()
    else:
        abort(404)
    return redirect('/orders')


@app.route("/sheets")
@login_required
def sheets():
    # обработчик страницы со списком заявок на организованное питание
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        sheets = session.query(Sheet)
        sheets = sheets.order_by(Sheet.created_date.desc())
        return render_template("sheets.html", sheets=sheets, message='')
    else:
        return redirect('/login')


@app.route('/register_sheet', methods=['GET', 'POST'])
def register_sheet():
    # обработчик страницы создания заявки на организованное питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 1:
        return redirect('/')
    session = db_session.create_session()
    # если есть заявка от класса на этот день - открываем ее на редактирование, иначе создаем новую
    t_sheet = session.query(Sheet).filter(Sheet.group_id == current_user.group.id, Sheet.created_date == date.today()).first()
    if t_sheet:
        return redirect(f'/edit_sheet/{t_sheet.id}')
    form = SheetForm()
    user_privilege_list = []
    user_privilege_selected_list = []
    all_users = session.query(User).filter(User.group == current_user.group, User.level == 0)
    user_list = []
    user_selected_list = []
    for elem in all_users:
        if session.query(Order).filter(Order.user_id == elem.id, Order.date_end >= datetime.today()).first():
            if elem.will_eat:
                user_privilege_selected_list.append((str(elem.id), elem.name))
            else:
                user_privilege_list.append((str(elem.id), elem.name))
        else:
            if elem.will_eat:
                user_selected_list.append((str(elem.id), elem.name))
            else:
                user_list.append((str(elem.id), elem.name))
    user_list.sort(key=lambda x: x[1])
    user_selected_list.sort(key=lambda x: x[1])
    user_privilege_list.sort(key=lambda x: x[1])
    user_privilege_selected_list.sort(key=lambda x: x[1])
    if form.validate_on_submit():
        sheet = Sheet()
        sheet.created_date = datetime.today()
        sheet.group = current_user.group
        sheet.group_id = current_user.group.id
        sheet.users = json.dumps(request.form.getlist('users_to'))
        sheet.users_privilege = json.dumps(request.form.getlist('users_to_p'))
        session.add(sheet)
        session.commit()
        return redirect('/sheets')
    return render_template('register_sheet.html',
                           title='Заявка на питание',
                           form=form,
                           users=user_list,
                           size=str(len(user_list) + len(user_selected_list)),
                           users_selected=user_selected_list,
                           user_privilege=user_privilege_list,
                           user_privilege_selected=user_privilege_selected_list,
                           size_p=str(len(user_privilege_list) + len(user_privilege_selected_list))
                           )


@app.route('/sheet_delete/<int:id>', methods=['GET', 'POST'])
@login_required
def sheet_delete(id):
    # обработчик страницы удаления заявки на организованное питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    sheet = session.query(Sheet).filter(Sheet.id == id).first()
    if sheet:
        session.delete(sheet)
        session.commit()
    else:
        abort(404)
    return redirect('/sheets')


@app.route('/edit_sheet/<int:id>', methods=['GET', 'POST'])
def edit_sheet(id):
    # обработчик страницы редактирования заявки на организованное питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 1:
        return redirect('/')
    session = db_session.create_session()
    sheet = session.query(Sheet).filter(Sheet.id == id).first()
    if not sheet:
        abort(404)
    form = SheetForm()
    user_privilege_list = []
    user_privilege_selected_list = []
    all_users = session.query(User).filter(User.group == sheet.group, User.level == 0)
    user_list = []
    user_selected_list = []
    if request.method == "GET":
        user_sp = json.loads(sheet.users_privilege)
        user_s = json.loads(sheet.users)
        for elem in all_users:
            if session.query(Order).filter(Order.user_id == elem.id, Order.date_end >= datetime.today()).first():
                if str(elem.id) in user_sp:
                    user_privilege_selected_list.append((str(elem.id), elem.name))
                else:
                    user_privilege_list.append((str(elem.id), elem.name))
            else:
                if str(elem.id) in user_s:
                    user_selected_list.append((str(elem.id), elem.name))
                else:
                    user_list.append((str(elem.id), elem.name))
        user_list.sort(key=lambda x: x[1])
        user_selected_list.sort(key=lambda x: x[1])
        user_privilege_list.sort(key=lambda x: x[1])
        user_privilege_selected_list.sort(key=lambda x: x[1])
    if form.validate_on_submit():
        sheet = session.query(Sheet).filter(Sheet.id == id).first()
        sheet.users = json.dumps(request.form.getlist('users_to'))
        sheet.users_privilege = json.dumps(request.form.getlist('users_to_p'))
        session.add(sheet)
        session.commit()
        return redirect('/sheets')
    return render_template('register_sheet.html',
                           title='Заявка на питание',
                           form=form,
                           users=user_list,
                           size=str(len(user_list) + len(user_selected_list)),
                           users_selected=user_selected_list,
                           user_privilege=user_privilege_list,
                           user_privilege_selected=user_privilege_selected_list,
                           size_p=str(len(user_privilege_list) + len(user_privilege_selected_list))
                           )


@app.route("/users_in_orders")
@login_required
def users_in_orders():
    # обработчик страницы со списком льготно питающихся учащихся
    if current_user.is_authenticated:
        if current_user.level < 2:
            return redirect('/')
        session = db_session.create_session()
        users_id = []
        for elem in session.query(Order).filter(Order.date_end >= datetime.today().date()):
            users_id.append(elem.user_id)
        users = dict()
        for user in session.query(User).filter(User.id.in_(users_id)):
            if user.group.name in users:
                users[user.group.name].append(user.name)
            else:
                users[user.group.name] = []
                users[user.group.name].append(user.name)
        keys = sorted(users.keys())
        return render_template("users_in_orders.html", users=users, keys=keys)
    else:
        return redirect('/login')


@app.route('/upload_sheet/<int:id>', methods=['GET', 'POST'])
@login_required
def upload_sheet(id):
    # обработчик "ручной" выгрузки заявки на питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    sheet = session.query(Sheet).filter(Sheet.id == id).first()
    if sheet:
        message = json.dumps(main_upload_sheet(sheet.id))
        sheet.status = message
        session.commit()
    return redirect('/sheets')


@app.route('/upload_sheets')
@login_required
def upload_sheets():
    # обработчик "ручной" выгрузки заявок на питание
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session = db_session.create_session()
    sheets = session.query(Sheet).filter(Sheet.created_date == date.today())
    for sheet in sheets:
        if sheet.status == 'Не выгружена':
            message = json.dumps(main_upload_sheet(sheet.id))
            sheet.status = message
            session.commit()
    return redirect('/sheets')


@app.route('/debtors', methods=['GET'])
@login_required
def debtors():
    # обработчик страницы со списком должников - учащихся с отрицательным балансом лицевого счета
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 1:
        return redirect('/')
    users = list(current_user.group.users)
    debtors = dict()
    for user in users:
        balance = get_balance(user.id_1c)
        if float(balance) < 0:
            debtors[user.name] = balance
    names = sorted(debtors.keys())
    return render_template('debtors.html', title='Должники', debtors=debtors, names=names)


@app.route('/group_balance', methods=['GET'])
@login_required
def group_balance():
    # обработчик страницы со списком учащихся класса с указанием баланса лицевого счета
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 1:
        return redirect('/')
    users = dict()
    for user in list(current_user.group.users):
        if user.level < 1:
            users[user.name] = get_balance(user.id_1c)
    names = sorted(users.keys())
    return render_template('group_balance.html', title='Состояние лицевых счетов класса', users=users, names=names)


@app.route('/update_users')
def update_users():
    # обработчик "ручного" обновления пользователей из 1С
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    sched_update_users()
    return redirect('/admin')


@app.route('/update_dishes')
def update_dishes():
    # обработчик "ручного" обновления блюд из 1С
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session_db = db_session.create_session()
    url = f'{SERVER_1C_B}Catalog_Номенклатура?$format=application/json&$filter=IsFolder eq false'
    session = requests.Session()
    session.auth = ACCOUNT_1C
    response = session.get(url, verify=False)
    for elem in json.loads(response.text)['value']:
        if elem['DeletionMark']:
            continue
        id_1c = elem['Ref_Key']
        dish = session_db.query(Dish).filter(Dish.id_1c == id_1c).first()
        if not dish:
            dish = Dish()
        dish.name = elem['Description']
        dish.code = elem['Code']
        dish.cost = 0
        dish.id_1c = elem['Ref_Key']
        session_db.add(dish)
        session_db.commit()
    return redirect('/admin')


@app.route('/update_menus')
def update_menus():
    # обработчик "ручного" обновления меню из 1С
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    session_db = db_session.create_session()
    data = str(date.today() + timedelta(days=1)) + 'T00:00:00'
    url = f"{SERVER_1C_F}Document_Питание_Калькуляция?$format=application/json&$filter=Date ge datetime'{data}'&$expand=ВидКалькуляции"
    session = requests.Session()
    session.auth = ACCOUNT_1C
    response = session.get(url, verify=False)
    menu_json = json.loads(response.text)['value']
    for dok in menu_json:
        menu_name = dok['ВидКалькуляции']['Description']
        date_dok = [int(x) for x in dok['Date'][:10].split('-')]
        menu_date = datetime(date_dok[0], date_dok[1], date_dok[2]).date()
        menu = session_db.query(Menu).filter(Menu.name == menu_name, Menu.date == menu_date).first()
        if not menu:
            menu = Menu()
        menu.name = menu_name
        menu.date = menu_date
        dishes_kod = {}
        for t_dish in dok['Блюда']:
            url = f"{SERVER_1C_F}Catalog_Питание_Блюда?$format=application/json&$filter=Ref_Key eq guid'{t_dish['Блюдо_Key']}'"
            response = session.get(url, verify=False)
            t_json = json.loads(response.text)['value']
            dishes_kod[t_json[0]['Description']] = t_dish['ПродажнаяЦена']
        dishes = []
        for elem in dishes_kod.keys():
            v_dish = session_db.query(Dish).filter(Dish.name == elem).first()
            if v_dish:
                dishes.append(v_dish.id)
                v_dish.cost = dishes_kod[v_dish.name]
        menu.dishes = json.dumps(dishes)
        session_db.add(menu)
        session_db.commit()
    return redirect('/admin')


@app.route('/nutrition_sheet', methods=['GET', 'POST'])
def nutrition_sheet():
    # обработчик страницы с табелем питания учащихся-льготников
    if not current_user.is_authenticated:
        return redirect('/login')
    if current_user.level < 2:
        return redirect('/')
    form = NutritionSheetForm()
    date_list = []
    header_date = ''
    users_dict = dict()
    if form.validate_on_submit():
        select_date = form.date.data
        cldr = calendar.Calendar()
        date_list = [day for day in filter(lambda x: x != 0, cldr.itermonthdays(select_date.year, select_date.month))]
        header_date = 'за ' + select_date.strftime('%B %Y') + ' года'
        session_db = db_session.create_session()
        if select_date.month == 12:
            end_month = select_date.replace(day=31)
        else:
            end_month = select_date.replace(month=select_date.month+1, day=1) - timedelta(days=1)
        begin_month = select_date.replace(day=1)
        sheets = session_db.query(Sheet).filter(Sheet.created_date >= begin_month, Sheet.created_date <= end_month).all()
        for sheet in sheets:
            for id in json.loads(sheet.users_privilege):
                user = session_db.query(User).filter(User.id == int(id)).first()
                if user.name in users_dict:
                    users_dict[user.name]['dates'][sheet.created_date.day] = '+'
                    users_dict[user.name]['all'] += 1
                else:
                    users_dict[user.name] = dict()
                    users_dict[user.name]['name'] = user.name
                    users_dict[user.name]['dates'] = dict()
                    for day in date_list:
                        users_dict[user.name]['dates'][day] = ''
                    users_dict[user.name]['all'] = 0
    sort_name = sorted(users_dict.keys())
    return render_template('nutrition_sheet.html', title='Табель питания', form=form, date_list=date_list, header_date=header_date, users_dict=users_dict, sort_name=sort_name)


@app.route("/payment_app.cgi", methods=['POST', 'GET'])
def payment():
    # обработчик запросов от банковской системы для проведения онлайн-платежа по пополнению лицевого счета
    root = ET.Element('response')
    action = request.args.get('ACTION', None)
    ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
    if ip not in VALID_IP:
        abort(404)
    if not action:
        abort(404)
    if action == 'check':
        account = request.args.get('ACCOUNT', None)
        if account and account.isdigit():
            session_db = db_session.create_session()
            card_number = ('0' * 8 + account)[-8:]
            user = session_db.query(User).filter(User.card_number == card_number).first()
            if user:
                code = ET.SubElement(root, "CODE")
                code.text = "0"
                message = ET.SubElement(root, "MESSAGE")
                message.text = "Карта найдена"
                fio = ET.SubElement(root, "FIO")
                fio.text = user.name
                info = ET.SubElement(root, "INFO")
                info.text = 'Пополнение карты питания'
            else:
                code = ET.SubElement(root, "CODE")
                code.text = "3"
                message = ET.SubElement(root, "MESSAGE")
                message.text = "Карта не найдена"
                fio = ET.SubElement(root, "FIO")
                fio.text = ''
                info = ET.SubElement(root, "INFO")
                info.text = 'Пополнение карты питания'
        else:
            code = ET.SubElement(root, "CODE")
            code.text = "4"
            message = ET.SubElement(root, "MESSAGE")
            message.text = "Неверный формат номера карты питания"
            fio = ET.SubElement(root, "FIO")
            fio.text = ''
            info = ET.SubElement(root, "INFO")
            info.text = 'Пополнение карты питания'
    elif action == 'payment':
        account = request.args.get('ACCOUNT', None)
        pay_id = request.args.get('PAY_ID', None)
        pay_date = request.args.get('PAY_DATE', None)
        amount = request.args.get('AMOUNT', None)
        if account and account.isdigit():
            session_db = db_session.create_session()
            card_number = ('0' * 8 + account)[-8:]
            user = session_db.query(User).filter(User.card_number == card_number).first()
            if user:
                try:
                    amount = float(amount)
                    paynment = session_db.query(Paynment).filter(Paynment.pay_id == pay_id).first()
                    if paynment:
                        code = ET.SubElement(root, "CODE")
                        code.text = "8"
                        message = ET.SubElement(root, "MESSAGE")
                        message.text = "Дублирование транзакции"
                    else:
                        '''Содание документа в 1с'''
                        data = dict()
                        session_1c = requests.Session()
                        session_1c.auth = ACCOUNT_1C
                        '''Пример значения pay_date=20180619120133'''
                        data['Date'] = f'{pay_date[:4]}-{pay_date[4:6]}-{pay_date[6:8]}T{pay_date[8:10]}:{pay_date[10:12]}:{pay_date[12:]}'
                        data['Posted'] = True
                        data['Состав'] = []
                        temp = dict()
                        temp['ЛС_Key'] = user.id_1c
                        temp['LineNumber'] = '1'
                        temp['СуммаДоп'] = amount
                        temp['СуммаОсн'] = 0
                        data['Состав'].append(temp)
                        data['Сумма'] = amount
                        url_post = f"{SERVER_1C_B}Document_СборДенег?$format=application/json"
                        response = session_1c.post(url_post, json=data, verify=False)
                        if response.status_code == 201:
                            code = ET.SubElement(root, "CODE")
                            code.text = "0"
                            message = ET.SubElement(root, "MESSAGE")
                            message.text = "payment successful"
                            '''Запишем платеж в базу для быстрой проверки на дублирование'''
                            paynment = Paynment()
                            paynment.user = user.id
                            paynment.pay_id = pay_id
                            paynment.pay_date = pay_date
                            paynment.amount = amount
                            session_db.add(paynment)
                            session_db.commit()
                        else:
                            code = ET.SubElement(root, "CODE")
                            code.text = "1"
                            message = ET.SubElement(root, "MESSAGE")
                            message.text = "Временная ошибка.Повторите запрос позже"
                except Exception:
                    code = ET.SubElement(root, "CODE")
                    code.text = "4"
                    message = ET.SubElement(root, "MESSAGE")
                    message.text = "Неверная сумма платежа"
            else:
                code = ET.SubElement(root, "CODE")
                code.text = "3"
                message = ET.SubElement(root, "MESSAGE")
                message.text = "Карта не найдена"
        else:
            code = ET.SubElement(root, "CODE")
            code.text = "4"
            message = ET.SubElement(root, "MESSAGE")
            message.text = "Неверный формат номера карты питания"
    xmlstr = ET.tostring(root, encoding='utf-8', method='xml')
    r = Response(response=xmlstr, status=200, mimetype="application/xml")
    r.headers["Content-Type"] = "text/xml; charset=utf-8"
    return r


if __name__ == '__main__':
    # формироваание задач для автоматического выполнения по расписанию
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(sched_update_dishes, trigger='cron', minute='45', hour='17')
    sched.add_job(sched_update_menus, trigger='cron', minute='55', hour='17')
    sched.add_job(sched_upload_sheets, trigger='cron', minute='30', hour='09')
    sched.add_job(sched_update_users, trigger='cron', minute='00', hour='17')
    sched.start()
    app.run(host='0.0.0.0', port='2021')

