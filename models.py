from datetime import datetime
from sqlalchemy import (
    orm,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    PrimaryKeyConstraint,
    Identity,
    JSON,
    func,
    UniqueConstraint,
    Column,
    create_engine,
)
import os


class Base(orm.DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    email: orm.Mapped[str] = orm.mapped_column(Text, primary_key=True)
    auth_token: orm.Mapped[str] = orm.mapped_column(Text)
    is_admin: orm.Mapped[bool] = orm.mapped_column(Boolean)
    email: orm.Mapped[str] = orm.mapped_column(Text)

    created_at = Column(DateTime, default=func.now())


class Item(Base):
    __tablename__ = "items"

    uid: orm.Mapped[str] = orm.mapped_column(Text, primary_key=True)
    identifier: orm.Mapped[str] = orm.mapped_column(Text)
    title: orm.Mapped[str] = orm.mapped_column(Text)
    author: orm.Mapped[str] = orm.mapped_column(Text)
    content: orm.Mapped[str] = orm.mapped_column(Text)
    summary: orm.Mapped[str] = orm.mapped_column(Text)
    link: orm.Mapped[str] = orm.mapped_column(Text)
    type: orm.Mapped[str] = orm.mapped_column(Text)
    email: orm.Mapped[str] = orm.mapped_column(Text)

    user_email = Column(Integer, ForeignKey("users.email"))
    user = orm.relationship("User")

    created_at = Column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint("link", "email", name="uix_uid_email"),)


class Source(Base):
    __tablename__ = "sources"

    source: orm.Mapped[str] = orm.mapped_column(Text)
    type: orm.Mapped[str] = orm.mapped_column(Text)
    email: orm.Mapped[str] = orm.mapped_column(Text)
    uid: orm.Mapped[str] = orm.mapped_column(Text)

    user_email = Column(Integer, ForeignKey("users.email"))
    user = orm.relationship("User")

    created_at = Column(DateTime, default=func.now())


class ItemReadingOrder(Base):
    __tablename__ = "item_reading_orders"

    item_uid: orm.Mapped[str] = orm.mapped_column(Text)
    item_order: orm.Mapped[int] = orm.mapped_column(Integer)
    archived: orm.Mapped[bool] = orm.mapped_column(Boolean)
    done: orm.Mapped[bool] = orm.mapped_column(Boolean)

    user_email = Column(Integer, ForeignKey("users.email"))
    user = orm.relationship("User")

    item_uid = Column(Integer, ForeignKey("items.uid"))
    item = orm.relationship("Item")


db_url = os.environ.get(
    "WM_DB_URL", "sqlite:///" + str(os.path.join(os.getcwd(), "spiel.db"))
)
print(f"Running on db url: {db_url}")
engine = create_engine(db_url, echo=False)
Base.metadata.create_all(engine)
