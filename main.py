import json
import aiosqlite
from fastapi import FastAPI, Depends, HTTPException, Request
import os
import uvicorn
from pydantic import BaseModel
import aiohttp


async def create_tables():
    async with aiosqlite.connect("spile.db") as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                auth_token TEXT,
                is_admin BOOL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            );
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                uid TEXT PRIMARY KEY,
                type TEXT,
                content TEXT,
                resonance INTEGER,
                feedback TEXT,
                view_date TIMESTAMP,
                received_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (email) REFERENCES users(email)
            );
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                source TEXT,
                type TEXT,
                FOREIGN KEY (email) REFERENCES users(email)
            )
            """
        )

        await db.commit()

async def auth(req: Request):
    auth_token = req.headers.get("auth_token", None)
    async with aiosqlite.connect("spile.db") as db:
        res = await db.execute(f"SELECT email, is_admin FROM users WHERE auth_token='{auth_token}'")
        
        if len(res) == 0:
            raise HTTPException(status_code=401, detail="Unauthorized")
        email = res[0][0], res[0][1]
        return email

app = FastAPI()


async def detect_source_type(source: str):
    if "@" in source and "get_feed" in source:
        return  "spiel"
    return "rss"

async def consume_source(source: str, source_type: str, email: str):
    if source_type == "spiel":
        all_items = await aiothttp.get(source)
        async with aiosqlite.connect("spile.db") as db:
            for item in all_items:
                uid = item.uid
                res = await db.execute("SELECT COUNT(*) as c FROM items WHERE email='{email}' and uid='{uid}'")
                if res[0][0] > 0:
                    # @TODO If item already exists merge all the `views` into one
                    pass
                else:
                    await db.execute("INSERT INTO items(item_content, item_type, uid, email) VALUES (?, ?, ?, ?)", (item.content, item.type, uid, email))
            await db.commit()
    elif source_type == "rss":
        pass
    else:
        raise ValueError(f"Unknown source type: `{source_type}` for source `{source}`!")


@app.post("/create_user")
async def create_user(email: str, is_admin: bool):
    if is_admin:
        new_user_auth_token = generate_auth_token()
        async with aiosqlite.connect("spile.db") as db:
            await db.execute(f"INSERT INTO users VALUES ('{email}', '{new_user_auth_token}', {str(is_admin).lower()})")
            await db.commit()
    return {
        "email": email,
        "auth_token": new_user_auth_token
    }

@app.post("/rate_item")
async def rate_item(uid: str, feedback: str, resonance: int):
    async with aiosqlite.connect("spile.db") as db:
        await db.execute(f"UPDATE TABLE items SET feedback='{feedback}', resonance={resonance} WHERE uid='{uid}' AND email='{auth_email}'")

@app.post("/get_items")
async def get_items():
    async with aiosqlite.connect("spile.db") as db:
        all_consumeable = await db.execute(f"SELECT * FROM items WHERE email='{auth_email}'")
    return all_consumeable

@app.post("/add_source")
async def add_source(source: str):
    source_type = await detect_source_type(source)
    async with aiosqlite.connect("spile.db") as db:
        await db.execute(f"INSERT INTO sources VALUES ('{source}', '{source_type}', '{auth_email}')")
        await db.commit()

@app.get("/get_feed/{user_email}")
async def get_feed():
    async with aiosqlite.connect("spile.db") as db:
        all_consumeable = await db.execute(f"SELECT uid, content, type, resonance, feedback FROM items WHERE email='{user_email}' AND view_date is not null")
        consumable_objs = {"updateAt": datetime.datetime.now(), "items": []}
        for val in all_consumeable:
            consumable_obj = json.loads(val[1])
            consumable_obj.views.append({
                "viewer": user_email,
                "resonance": val[3],
                "feedback": val[4],

            })
            consumable_objs.append({
                "uid": val[0],
                "type": val[2],
                "content": consumable_obj,
            })
    return all_consumeable

@app.get("/get_feed/{user_email}.rss")
async def get_feed_rss(user_email: str):
    return 'Not implemented'

@app.on_event("startup")
async def startup():
    pass

if __name__ == "__main__":
    import asyncio
    asyncio.run(create_tables())
    if os.environ.get("APP_ENV", "development") == "production":
        uvicorn.run("api:app", host="0.0.0.0", port=8080, workers=4)
    else:
        uvicorn.run("api:app", host="0.0.0.0", port=8080, workers=1)