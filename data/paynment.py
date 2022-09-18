import sqlalchemy
from .db_session import SqlAlchemyBase


class Paynment(SqlAlchemyBase):
    __tablename__ = 'paynment'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True, autoincrement=True)
    user = sqlalchemy.Column(sqlalchemy.Integer, sqlalchemy.ForeignKey("users.id"))
    pay_id = sqlalchemy.Column(sqlalchemy.String)
    pay_date = sqlalchemy.Column(sqlalchemy.String)
    amount = sqlalchemy.Column(sqlalchemy.Float)




