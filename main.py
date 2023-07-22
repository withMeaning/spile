import datetime
import multiprocessing
import sys
from fastapi import FastAPI, Depends, HTTPException, Request
import os
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
import aiohttp
from typing import Annotated, Tuple
import asyncio
import threading
import time
from fastapi.middleware.cors import CORSMiddleware
from cron_consumer import refresh_data
from utils import generate_auth_token, generate_content_uid, link_to_md
from models import Item, ReadingItemData, Source, User, engine
from sqlalchemy import desc, orm, select
from utils import detect_source_type, link_to_md
import os


async def auth(req: Request):
    auth_token = req.headers.get("auth_token", None)
    with orm.Session(engine) as session:
        if auth_token is None:
            raise HTTPException(status_code=401, detail="No auth provided")
        if os.environ.get("GLOBAL_AUTH_TOKEN") == auth_token:
            return None, True

        user = (
            session.execute(select(User).where(User.auth_token == auth_token))
            .scalars()
            .first()
        )
        if user is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        return user.email, user.is_admin


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://read-nine.vercel.app",
        "https://reader.withmeaning.io",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/get_items")
async def get_items(auth_data: Annotated[tuple[str], Depends(auth)]):
    with orm.Session(engine) as session:
        reading_item_Data = (
            session.execute(
                select(ReadingItemData)
                .where(
                    ReadingItemData.user_email == auth_data[0],
                    ReadingItemData.archived == False,
                    ReadingItemData.item.any(Item.type.in_("read", "do")),
                )
                .order_by(desc(ReadingItemData.item_order))
            )
            .scalars()
            .all()
        )
        items = [x.item for x in reading_item_Data]

    return {"items": [x.to_dict() for x in items]}


class AddItemBody(BaseModel):
    title: Optional[str]
    content: Optional[str]
    link: str
    type: str
    author: Optional[str]


@app.post("/add_item")
async def add_item(body: AddItemBody, auth_data: Annotated[tuple[str], Depends(auth)]):
    if not body.content:
        body.content = await link_to_md(body.link)
        uid = generate_content_uid(
            (body.title or ""), body.content, body.type, auth_data[0], body.link
        )
    with orm.Session(engine) as session:
        session.add(
            Item(
                uid=uid,
                title=body.title,
                content=body.content,
                link=body.link,
                email=auth_data[0],
                type=body.type,
                author=body.author,
            )
        )
        if body.type == "read":
            session.add(
                ReadingItemData(
                    item_uid=uid, item_order=None, archived=False, email=auth_data[0]
                )
            )
        if body.type == "do":
            session.add(
                ReadingItemData(
                    item_uid=uid,
                    item_order=None,
                    archived=False,
                    done=False,
                    email=auth_data[0],
                )
            )
        session.commit()
    return body


class CreateUserBody(BaseModel):
    email: str
    is_admin: bool


@app.post("/create_user")
async def create_user(
    body: CreateUserBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    with orm.Session(engine) as session:
        new_user_auth_token = generate_auth_token()
        if auth_data[1]:
            session.add(
                User(
                    email=body.email,
                    auth_token=new_user_auth_token,
                    is_admin=body.is_admin,
                )
            )
            session.commit()
            return {"email": body.email, "auth_token": new_user_auth_token}


class ArchiveItemBody(BaseModel):
    archived: bool
    uid: str


@app.post("/archive")
async def archive(
    body: ArchiveItemBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    with orm.Session(engine) as session:
        reading_item_data = (
            session.execute(
                select(ReadingItemData).where(
                    ReadingItemData.item_uid == body.uid,
                    ReadingItemData.user_email == auth_data[0],
                )
            )
            .scalars()
            .first()
        )
        reading_item_data.archived = body.archived
        session.commit()
    return {}


class DoneItemBody(BaseModel):
    done: bool
    uid: str


@app.post("/done")
async def done(body: DoneItemBody, auth_data: Annotated[tuple[str], Depends(auth)]):
    with orm.Session(engine) as session:
        reading_item_data = (
            session.execute(
                select(ReadingItemData).where(
                    ReadingItemData.item_uid == body.uid,
                    ReadingItemData.user_email == auth_data[0],
                )
            )
            .scalars()
            .first()
        )
        reading_item_data.done = body.done
        session.commit()
    return {}


class OrderItemBody(BaseModel):
    order: int
    uid: str


class Order(BaseModel):
    items: List[OrderItemBody]


@app.post("/order")
async def order(body: Order, auth_data: Annotated[tuple[str], Depends(auth)]):
    print(body)
    for item in body.items:
        with orm.Session(engine) as session:
            reading_item_data = (
                session.execute(
                    select(ReadingItemData).where(
                        ReadingItemData.item_uid == item.uid,
                        ReadingItemData.user_email == auth_data[0],
                    )
                )
                .scalars()
                .first()
            )
            reading_item_data.item_order = item.order
            session.commit()
        return {}


class AddSourceBody(BaseModel):
    source: str


@app.post("/add_source")
async def add_source(
    data: AddSourceBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    source_type = detect_source_type(data.source)
    with orm.Session(engine) as session:
        session.add(
            Source(source=data.source, type=source_type, user_email=auth_data[0])
        )
    return {"status": "ok"}


class DeleteSourceBody(BaseModel):
    source: str


@app.post("/delete_source")
async def delete_source(
    data: DeleteSourceBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    with orm.Session(engine) as session:
        source = (
            session.execute(
                select(Source).where(
                    Source.source == data.source, Source.user_email == auth_data[0]
                )
            )
            .scalars()
            .first()
        )
        source.delete()
        session.commit()
    return {"status": "ok"}


@app.get("/get_sources")
async def get_sources(auth_data: Annotated[tuple[str], Depends(auth)]):
    with orm.Session(engine) as session:
        sources = (
            session.execute(select(Source).where(Source.user_email == auth_data[0]))
            .scalars()
            .all()
        )
    return {"sources": [x.to_dict() for x in sources]}


@app.get("/get_feed/{user_email}")
async def get_feed(user_email: str):
    # Rules based on which the user recommends stuff to other people @TODO (this endpoint can accept an optional email, so the user can recommend to specific individuals(?))
    with orm.Session(engine) as session:
        resonance_items = session.execute(
            select(Item).where(Item.user_email == user_email, Item.type == "resonance")
        )
        send_item_uids = []
        for resonance_item in resonance_items:
            if int(resonance_item.content) > 80:
                send_item_uids.append(resonance_item.link)

        reading_items = session.execute(
            select(Item).where(Item.uid.in_(send_item_uids))
        )
    return [{"read": x, "reasons": [{}]} for x in reading_items]


@app.get("/ping")
async def ping():
    return "Pong"


@app.on_event("startup")
async def startup():
    pass


if __name__ == "__main__":
    p = multiprocessing.Process(target=refresh_data)
    p.start()
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 8080
    try:
        if os.environ.get("SPILE_ENV", "development") == "production":
            uvicorn.run("main:app", port=port, host="0.0.0.0", workers=4)
        else:
            uvicorn.run("main:app", port=port, host="0.0.0.0", reload=True)
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        # Ensure the background process is terminated when the server is stopped
        p.terminate()
        p.join()
