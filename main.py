import datetime
import json
import sys
import aiosqlite
from fastapi import FastAPI, Depends, HTTPException, Request
import os
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
import aiohttp
from typing import Annotated, Tuple
import asyncio
import sqlite3
from uuid import uuid4
import threading
import time
import requests
from hashlib import md5
from fastapi.middleware.cors import CORSMiddleware


# Note orm will make it harder to split and modify, though make coding easier, so for now we aren't
# + async sqlalchemy is ergh and I don't want to investigate async ORMs right now
def create_tables():
    with sqlite3.connect("spile.db") as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                auth_token TEXT,
                is_admin BOOL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                uid TEXT,
                identifier TEXT,
                title TEXT,
                author TEXT,
                content TEXT,
                summary TEXT,
                link TEXT,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                email TEXT,
                FOREIGN KEY (email) REFERENCES users(email),
                UNIQUE(uid, email)
            );
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                source TEXT,
                type TEXT,
                email TEXT,
                FOREIGN KEY (email) REFERENCES users(email)
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS reading_order (
                item_uid TEXT,
                item_order INT,
                archived BOOLEAN,
                done BOOLEAN,
                email TEXT,
                FOREIGN KEY (item_uid) REFERENCES items(uid),
                FOREIGN KEY (email) REFERENCES users(email)
            )
            """
        )

        con.commit()


async def insert(table: str, values: list[dict]):
    async with aiosqlite.connect("spile.db") as con:
        async with con.cursor() as cur:
            question_marks = ",".join(["?"] * len(values[0]))
            ordered_keys = list(values[0].keys())
            cols = ",".join(ordered_keys)
            fmt_values = tuple(
                tuple(values[i][k] for k in ordered_keys) for i in range(len(values))
            )
            if len(fmt_values) == 1:
                fmt_values = fmt_values[0]
            q = f"INSERT INTO {table} ({cols}) VALUES ({question_marks})"
            print(q, fmt_values)
            await cur.execute(q, fmt_values)
            await con.commit()


async def select(q: str, one: bool = False):
    async with aiosqlite.connect("spile.db") as con:
        con.row_factory = aiosqlite.Row
        async with con.cursor() as cur:
            await cur.execute(q)
            rows = await cur.fetchall()
            res = [dict(x) for x in rows]
            if one:
                if len(rows) > 1:
                    raise Exception(f"Expected only one row, got: {len(rows)}")
                if len(rows) < 1:
                    return None
                return res[0]
            return [x for x in res]


async def mut_query(q: str):
    async with aiosqlite.connect("spile.db") as con:
        async with con.cursor() as cur:
            await cur.execute(q)
            await con.commit()


async def auth(req: Request):
    auth_token = req.headers.get("auth_token", None)
    async with aiosqlite.connect("spile.db") as db:
        if auth_token is None:
            raise HTTPException(status_code=401, detail="No auth provided")

        res = await select(
            f"SELECT email, is_admin FROM users WHERE auth_token='{auth_token}'", True
        )
        if res is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return res["email"], res["is_admin"]


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://read-nine.vercel.app", "https://reader.withmeaning.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def detect_source_type(source: str):
    if "@" in source and "get_feed" in source:
        return "spiel"
    return "rss"


async def consume_source(source: str, source_type: str, email: str):
    if source_type == "spiel":
        async with aiohttp.ClientSession() as session:
            async with session.get(source) as resp:
                all_items = await resp.json()
        for item in all_items:
            reading_item = item["read"]
            res = await select(
                f"SELECT COUNT(*) as c FROM items WHERE email='{email}' and link='{reading_item['link']}'",
                True,
            )
            if res["c"] > 0:
                # @TODO If item already exists merge all the `views` into one
                pass
            else:
                uid = generate_content_uid(
                    reading_item["content"]
                    + reading_item["type"]
                    + email
                    + str(reading_item["link"])
                )
                await insert(
                    "items",
                    [
                        {
                            "author": reading_item["author"],
                            "summary": reading_item["summary"],
                            "title": reading_item["title"],
                            "link": reading_item["link"],
                            "content": reading_item["content"],
                            "type": reading_item["type"],
                            "uid": uid,
                            "email": email,
                        }
                    ],
                )
                if (reading_item["type"] == "do"):
                    do_state = False
                else:
                    do_state = None
                await insert(
                    "reading_order",
                    [
                        {
                            "item_uid": uid,
                            "item_order": None,
                            "archived": False,
                            "done": do_state,
                            "email": email,
                        }
                    ],
                )
    elif source_type == "rss":
        print("RSS not implemented yet!")
    else:
        raise ValueError(f"Unknown source type: `{source_type}` for source `{source}`!")


def generate_auth_token():
    return str(uuid4())


def generate_content_uid(content: str):
    return str(md5(content.encode("utf-8")).hexdigest())



@app.get("/get_items")
async def get_items(auth_data: Annotated[tuple[str], Depends(auth)]):
    async with aiosqlite.connect("spile.db") as db:
        q = f"SELECT * FROM items INNER JOIN reading_order ON items.uid=reading_order.item_uid AND reading_order.email='{auth_data[0]}'  AND reading_order.archived=false WHERE items.email='{auth_data[0]}' and items.type='read' or items.type='do' ORDER BY reading_order.item_order"
        print(q)
        all_consumeable = await select(q)

    return {"updateAt": datetime.datetime.now(), "items": all_consumeable}


class AddItemBody(BaseModel):
    title: Optional[str]
    content: str
    link: str
    type: str
    author: Optional[str]


@app.post("/add_item")
async def add_item(body: AddItemBody, auth_data: Annotated[tuple[str], Depends(auth)]):
    uid = generate_content_uid((body.title or "")  + body.content + body.type + auth_data[0] + str(body.link))
    await insert(
        "items",
        [
            {
                "uid": uid,
                "title": body.title,
                "content": body.content,
                "link": body.link,
                "email": auth_data[0],
                "type": body.type,
                "author": body.author,
            }
        ],
    )
    if body.type == "read":
        await insert(
            "reading_order",
            [
                {
                    "item_uid": uid,
                    "item_order": None,
                    "archived": False,
                    "email": auth_data[0],
                }
            ],
        )
    if body.type == "do":
        await insert(
            "reading_order",
            [
                {
                    "item_uid": uid,
                    "item_order": None,
                    "archived": False,
                    "done": False,
                    "email": auth_data[0],
                }
            ],
        )
    return body

class CreateUserBody(BaseModel):
    email: str
    is_admin: bool


@app.post("/create_user")
async def create_user(
    body: CreateUserBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    if auth_data[1]:
        new_user_auth_token = generate_auth_token()
        await insert(
            "users",
            [
                {
                    "email": body.email,
                    "auth_token": new_user_auth_token,
                    "is_admin": str(body.is_admin).lower(),
                }
            ],
        )
        json = AddItemBody(title="Welcome", content="This is the start of ...", type="read", link="")
        add_item(json, [body.email, new_user_auth_token])
        return {"email": body.email, "auth_token": new_user_auth_token}

""" await insert(
            "items",
            [
                {
                    "uid": "first" + body.email,
                    "title": "Welcome",
                    "content": "This is the start of ...",
                    "link": "",
                    "email": body.email,
                    "type": "read",
                    "author": "",
                }
            ],
        ) """

class ArchiveItemBody(BaseModel):
    archived: bool
    uid: str


@app.post("/archive")
async def archive(
    body: ArchiveItemBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    """ print(
        f"UPDATE reading_order SET archived={str(body.archived).lower()} WHERE item_uid='{body.uid}' AND email='{auth_data[0]}'"
    ) """
    await mut_query(
        f"UPDATE reading_order SET archived={str(body.archived).lower()} WHERE item_uid='{body.uid}' AND email='{auth_data[0]}'"
    )
    return ""

class DoneItemBody(BaseModel):
    done: bool
    uid: str

@app.post("/done")
async def archive(
    body: DoneItemBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    """ print(
        f"UPDATE reading_order SET archived={str(body.archived).lower()} WHERE item_uid='{body.uid}' AND email='{auth_data[0]}'"
    ) """
    await mut_query(
        f"UPDATE reading_order SET done={str(body.done).lower()} WHERE item_uid='{body.uid}' AND email='{auth_data[0]}'"
    )
    return ""

class OrderItemBody(BaseModel):
    order: int
    uid: str
    
class Order(BaseModel):
     items: List[OrderItemBody]

@app.post("/order")
async def order(body: Order, auth_data: Annotated[tuple[str], Depends(auth)]):
    print(body)
    for item in body.items:
        print(item)
        await mut_query(
            f"UPDATE reading_order SET item_order={item.order} WHERE item_uid='{item.uid}' AND email='{auth_data[0]}'"
        )
    return ""


class AddSourceBody(BaseModel):
    source: str


@app.post("/add_source")
async def add_source(
    data: AddSourceBody, auth_data: Annotated[tuple[str], Depends(auth)]
):
    source_type = await detect_source_type(data.source)
    await insert(
        "sources", [{"source": data.source, "type": source_type, "email": auth_data[0]}]
    )
    return {"status": "ok"}


@app.get("/get_feed/{user_email}")
async def get_feed(user_email: str):
    # Rules based on which the user recommends stuff to other people @TODO (this endpoint can accept an optional email, so the user can recommend to specific individuals(?))
    resonance_items = await select(
        f"SELECT content, link FROM items WHERE email='{user_email}' AND type='resonance'"
    )
    send_item_uids = []
    for resonance_item in resonance_items:
        if int(resonance_item["content"]) > 80:
            send_item_uids.append(resonance_item["link"])

    send_item_uids = ",".join([f"'{x}'" for x in send_item_uids])
    reading_items = await select(f"SELECT * FROM items WHERE uid in ({send_item_uids})")
    consumable_objs = []
    for reading_item in reading_items:
        consumable_objs.append(
            {"read": reading_item, "reasons": [{}]}  # e.g. the resonance item
        )
    return consumable_objs


@app.get("/get_feed/{user_email}.rss")
async def get_feed_rss(user_email: str):
    return "Not implemented"


@app.get("/ping")
async def ping():
    return "Pong"


@app.on_event("startup")
async def startup():
    pass


async def refresh_data():
    while True:
        sources = await select("SELECT * FROM sources")
        for source in sources:
            await consume_source(source["source"], source["type"], source["email"])
        time.sleep(2)


class BackgroundTasks(threading.Thread):
    def run(self, *args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(refresh_data())
        loop.close()


if __name__ == "__main__":
    create_tables()
    t = BackgroundTasks()
    t.start()
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 8080
    if os.environ.get("SPILE_ENV", "devitem_uidelopment") == "production":
        uvicorn.run("main:app", port=port, host="0.0.0.0", workers=4)
    else:
        uvicorn.run("main:app", port=port, host="0.0.0.0", reload=True)
