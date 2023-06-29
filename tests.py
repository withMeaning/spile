import requests
import sqlite3
import json
import os
import time


# A server runs on 8080 using spile.db with and admin account
base = "http://localhost:8080"


# We make the admin account
db = sqlite3.connect("spile.db")

db.execute(
    "INSERT INTO users (email, auth_token, is_admin) VALUES ('test@test.com', 'abcdefg', true)"
)
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

print(user1_auth)
print(user2_auth)
# Both users should have no items
for auth_token in [user1_auth, user2_auth]:
    items = requests.get(
        base + "/get_items", headers={"auth_token": auth_token}
    ).json()["items"]
    assert len(items) == 0


# Artificially add items
for auth, email in [(user1_auth, user1_email), (user2_auth, user2_email)]:
    res = requests.post(
        base + "/add_item",
        headers={"auth_token": auth},
        json={
            "title": f"Hello from {email}",
            "content": "This is a long string of text",
            "link": f"Link.de/subscriber_email={email}",
            "type": "read",
        },
    )

# Now both users should get 1 item
for auth_token in [user1_auth, user2_auth]:
    items = requests.get(
        base + "/get_items", headers={"auth_token": auth_token}
    ).json()["items"]
    assert len(items) == 1


# Now subscribe them to each other
resp = requests.post(
    base + "/add_source",
    headers={"auth_token": user1_auth},
    json={"source": base + f"/get_feed/{user2_email}"},
)
assert resp.status_code == 200
resp = requests.post(
    base + "/add_source",
    headers={"auth_token": user2_auth},
    json={"source": base + f"/get_feed/{user1_email}"},
)
assert resp.status_code == 200


time.sleep(1.5)
# They should still have 1 item each
for auth_token in [user1_auth, user2_auth]:
    items = requests.get(
        base + "/get_items", headers={"auth_token": auth_token}
    ).json()["items"]
    assert len(items) == 1

# user1 reads and rates an item
res = requests.get(
    base + "/get_items",
    headers={"auth_token": user1_auth},
)
assert res.status_code == 200
read_item = res.json()["items"][0]
res = requests.post(
    base + "/add_item",
    headers={"auth_token": user1_auth},
    json={
        "content": "95",
        "link": read_item["uid"],
        "type": "resonance",
    },
)
time.sleep(2)
items = requests.get(base + "/get_items", headers={"auth_token": user2_auth}).json()[
    "items"
]

assert len(items) == 2

# User 2 reads and rates, it has low resonance
res = requests.get(
    base + "/get_items",
    headers={"auth_token": user2_auth},
)
assert res.status_code == 200
read_item = res.json()["items"][0]
res = requests.post(
    base + "/add_item",
    headers={"auth_token": user2_auth},
    json={
        "content": "10",
        "link": read_item["uid"],
        "type": "resonance",
    },
)
time.sleep(1.5)
items = requests.get(base + "/get_items", headers={"auth_token": user1_auth}).json()[
    "items"
]
assert len(items) == 1

# Test Item Archive and Order
items = requests.get(base + "/get_items", headers={"auth_token": user2_auth}).json()[
    "items"
]

resp = requests.post(
    base + "/archive",
    headers={"auth_token": user2_auth},
    json={
        "uid": items[0]["uid"],
        "archived": True,
    },
)
assert resp.status_code == 200

items = requests.get(base + "/get_items", headers={"auth_token": user2_auth}).json()[
    "items"
]
assert len(items) == 1

resp = requests.post(
    base + "/done",
    headers={"auth_token": user2_auth},
    json={
        "uid": items[0]["uid"],
        "done": True,
    },
)
assert resp.status_code == 200

print("All tests passed")

# Subscribe user1 to nintil's RSS
# https://nintil.com/rss.xml
