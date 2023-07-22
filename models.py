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
    __abstract__ = True

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in self.__table__.c}


class User(Base):
    __tablename__ = "users"

    email: orm.Mapped[str] = orm.mapped_column(Text, primary_key=True)
    auth_token: orm.Mapped[str] = orm.mapped_column(Text)
    is_admin: orm.Mapped[bool] = orm.mapped_column(Boolean)

    created_at = Column(DateTime, default=func.now())


class Item(Base):
    __tablename__ = "items"

    uid: orm.Mapped[str] = orm.mapped_column(Text, primary_key=True)
    uiuid: orm.Mapped[str] = orm.mapped_column(Text)
    title: orm.Mapped[str] = orm.mapped_column(Text, nullable=True)
    author: orm.Mapped[str] = orm.mapped_column(Text, nullable=True)
    content: orm.Mapped[str] = orm.mapped_column(Text, nullable=True)
    summary: orm.Mapped[str] = orm.mapped_column(Text, nullable=True)
    link: orm.Mapped[str] = orm.mapped_column(Text)
    type: orm.Mapped[str] = orm.mapped_column(Text)

    user_email = Column(Integer, ForeignKey("users.email"))
    user = orm.relationship("User")

    created_at = Column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint("link", "user_email"),)


class Source(Base):
    __tablename__ = "sources"

    source: orm.Mapped[str] = orm.mapped_column(Text)
    type: orm.Mapped[str] = orm.mapped_column(Text)
    uid: orm.Mapped[str] = orm.mapped_column(Text, primary_key=True)

    user_email = Column(Integer, ForeignKey("users.email"))
    user = orm.relationship("User")

    created_at = Column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint("source", "user_email"),)


class ReadingItemData(Base):
    __tablename__ = "reading_item_data"

    item_uid: orm.Mapped[str] = orm.mapped_column(Text)
    item_order: orm.Mapped[int] = orm.mapped_column(Integer, nullable=True)
    archived: orm.Mapped[bool] = orm.mapped_column(Boolean)
    done: orm.Mapped[bool] = orm.mapped_column(Boolean)

    user_email = Column(Integer, ForeignKey("users.email"))
    user = orm.relationship("User")

    item_uid = Column(Integer, ForeignKey("items.uid"))
    item = orm.relationship("Item")

    __table_args__ = (PrimaryKeyConstraint("item_uid", "user_email"),)


db_url = os.environ.get(
    "WM_DB_URL", "sqlite:///" + str(os.path.join(os.getcwd(), "spile.db"))
)
print(f"Running on db url: {db_url}")
engine = create_engine(db_url, echo=False)
Base.metadata.create_all(engine)
