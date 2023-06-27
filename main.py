import datetime
import json
import sys
import aiosqlite
from fastapi import FastAPI, Depends, HTTPException, Request
import os
import uvicorn
from pydantic import BaseModel
import aiohttp
from typing import Annotated, Tuple
import asyncio
import sqlite3
from uuid import uuid4


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
                uid TEXT PRIMARY KEY,
                type TEXT,
                content TEXT,
                resonance INTEGER,
                feedback TEXT,
                view_date TIMESTAMP,
                received_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                email TEXT,
                FOREIGN KEY (email) REFERENCES users(email)
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


async def auth(req: Request):
    auth_token = req.headers.get("auth_token", None)
    async with aiosqlite.connect("spile.db") as db:
        res = await select(
            f"SELECT email, is_admin FROM users WHERE auth_token='{auth_token}'", True
        )

        if res is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return res["email"], res["is_admin"]


app = FastAPI()


async def detect_source_type(source: str):
    if "@" in source and "get_feed" in source:
        return "spiel"
    return "rss"


async def consume_source(source: str, source_type: str, email: str):
    if source_type == "spiel":
        all_items = await aiohttp.get(source)
        for item in all_items:
            uid = item.uid
            res = await select(
                "SELECT COUNT(*) as c FROM items WHERE email='{email}' and uid='{uid}'",
                True,
            )
            if res["c"] > 0:
                # @TODO If item already exists merge all the `views` into one
                pass
            else:
                await insert(
                    "items",
                    [
                        {
                            "item_content": item.content,
                            "item_type": item.type,
                            "uid": uid,
                            "email": email,
                        }
                    ],
                )
    elif source_type == "rss":
        pass
    else:
        raise ValueError(f"Unknown source type: `{source_type}` for source `{source}`!")


def generate_auth_token():
    return str(uuid4())


class CreateUserBody(BaseModel):
    email: str
    is_admin: bool


@app.post("/create_user")
async def create_user(
    body: CreateUserBody,  # , auth_data: Annotated[tuple[str], Depends(auth)]
):
    # if auth_data[1]:
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
    return {"email": body.email, "auth_token": new_user_auth_token}


@app.post("/rate_item")
async def rate_item(
    uid: str,
    feedback: str,
    resonance: int,
    auth_data: Annotated[tuple[str], Depends(auth)],
):
    async with aiosqlite.connect("spile.db") as db:
        await db.execute(
            f"UPDATE TABLE items SET feedback='{feedback}', resonance={resonance} WHERE uid='{uid}' AND email='{auth_data[0]}'"
        )


@app.get("/get_items")
async def get_items(auth_data: Annotated[tuple[str], Depends(auth)]):
    async with aiosqlite.connect("spile.db") as db:
        all_consumeable = await select(
            f"SELECT * FROM items WHERE email='{auth_data[0]}'"
        )
        print(all_consumeable)
    return {"updateAt": datetime.datetime.now(), "items": all_consumeable}


class CreateItemBody(BaseModel):
    title: str
    content: str
    link: str
    email: str
    type: str


@app.post("/add_item")
async def add_item(
    body: CreateItemBody,
    # auth_data: Annotated[tuple[str], Depends(auth)]
):
    await insert(
        "items",
        [
            {
                "uid": generate_auth_token(),
                "content": json.dumps(
                    {
                        "title": body.title,
                        "content": body.content,
                        "link": body.link,
                    }
                ),
                "email": body.email,
            }
        ],
    )
    return body


@app.post("/add_source")
async def add_source(source: str, auth_data: Annotated[tuple[str], Depends(auth)]):
    source_type = await detect_source_type(source)
    await insert(
        "sources", [{"source": source, "type": source_type, "email": auth_data[0]}]
    )


@app.get("/get_feed/{user_email}")
async def get_feed(user_email: str):
    all_consumeable = await select(
        "SELECT uid, content, type, resonance, feedback FROM items WHERE email='{user_email}' AND view_date is not null"
    )
    consumable_objs = []
    for val in all_consumeable:
        consumable_obj = json.loads(val[1])
        consumable_obj.views.append(
            {
                "viewer": user_email,
                "resonance": val["resonance"],
                "feedback": val["feedback"],
            }
        )
        consumable_objs.append(
            {
                "uid": val["uid"],
                "type": val["type"],
                "content": consumable_obj,
            }
        )
    return all_consumeable


@app.get("/get_feed/{user_email}.rss")
async def get_feed_rss(user_email: str):
    return "Not implemented"


@app.get("/ping")
async def ping():
    return "Pong"


@app.on_event("startup")
async def startup():
    pass


if __name__ == "__main__":
    create_tables()
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    else:
        port = 8080
    if os.environ.get("SPILE_ENV", "development") == "production":
        uvicorn.run("main:app", port=port, host="0.0.0.0", workers=4)
    else:
        uvicorn.run("main:app", port=port, host="0.0.0.0", reload=True)
