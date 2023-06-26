import requests
import sqlite3
import json
import os


# A server runs on 8080 using spile.db with and admin account
base = "http://localhost:8080"


# We make the admin account
db = sqlite3.connect("spile.db")

#resets the DB for now
cur = db.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cur.fetchall()
for table in tables:
    table_name = table[0]
    drop_query = f"DROP TABLE {table_name};"
    cur.execute(drop_query)
db.commit()

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



db.execute("INSERT INTO users (email, auth_token, is_admin) VALUES ('test@test.com', 'abcdefg', true)")
db.commit()

## And create two users
user1_email = "user1@test.com"
user2_email = "user2@test.com"
user1_auth = requests.post(
    base + "/create_user",
    headers={"auth_token": "abcdefg"},
    json={"email": user1_email, "is_admin": False},
).json()["auth_token"]
user2_auth = requests.post(
    base + "/create_user",
    headers={"auth_token": "abcdefg"},
    json={"email": user2_email, "is_admin": True},
).json()["auth_token"]

# Both users should have no items
for auth_token in [user1_auth, user2_auth]:
    items = requests.get(
        base + "/get_items", headers={"auth_token": auth_token}
    ).json()["items"]
    assert len(items) == 0


# Artificially add items
for email in [user1_email, user2_email]:
    res = requests.post(base + "/add_item", 
                        headers={"auth_token": "abcdefg"},
                        json={"title": "Hello", "content": "Blob", "link": "Link.de", "email": email, "type": "read"})

# Now both users should get 1 item
for auth_token in [user1_auth, user2_auth]:
    items = requests.get(
        base + "/get_items", headers={"auth_token": auth_token}
    ).json()["items"]
    assert len(items) == 1


# Now subscribe them to each other


# They should still have 1 item each


# user1 reads and rates an item


# user2 should have 2x items now


# user2 rates his original item


# Both now have 1x item, but with the meaningdata from the other on top and the uids reversed


# Adding an rss feed to user1 results in him getting more items from that


# And user1 is also able to generate a valid rss feed with the same amount of items as the source + 1 (the one he rated already)
