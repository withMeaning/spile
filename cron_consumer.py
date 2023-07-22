from models import Item, Source, User, ReadingItemData, engine
import requests
from sqlalchemy import orm, select
from utils import generate_content_uid, link_to_md
from rss_parser import Parser
import time


def check_dup_and_stack(email: str, link: str) -> bool:
    with orm.Session(engine) as session:
        res = session.execute(
            select(Item).where(Item.user_email == email, link == link)
        ).first()
    if res:
        # @TODO If item already exists merge all the `views` into one
        return True
    return False


def consume_source(source: str, source_type: str, email: str):
    if source_type == "spiel":
        all_items = requests.get(source).json()
        for item in all_items:
            reading_item = item["read"]
            if not check_dup_and_stack(email, reading_item["link"]):
                uid = generate_content_uid(
                    [
                        reading_item["content"],
                        reading_item["type"],
                        email,
                        reading_item["link"],
                    ]
                )
                with orm.Session(engine) as session:
                    session.add(
                        Item(
                            author=reading_item["author"],
                            summary=reading_item["summary"],
                            title=reading_item["title"],
                            link=reading_item["link"],
                            content=reading_item["content"],
                            type=reading_item["type"],
                            uid=uid,
                            user_email=email,
                        )
                    )

                    if reading_item["type"] == "do":
                        do_state = False
                    else:
                        do_state = None
                    session.add(
                        ReadingItemData(
                            item_uid=uid,
                            item_order=None,
                            archived=False,
                            done=do_state,
                            user_email=email,
                        )
                    )
                    session.commit()
    elif source_type == "rss":
        rss_text = requests.get(source).json()
        rss = Parser.parse(rss_text)
        for reading_item in rss.channel.items:
            uid = generate_content_uid(
                [
                    reading_item.content.description.content,
                    "read",
                    email,
                    reading_item.link,
                ]
            )
            link = reading_item.content.link.content
            if not check_dup_and_stack(email, link):
                md = link_to_md(link)
                with orm.Session(engine) as session:
                    session.add(
                        Item(
                            author=reading_item.content.author.content
                            if reading_item.content.author
                            else None,
                            summary=reading_item.content.description.content
                            if reading_item.content.description
                            else "",
                            title=reading_item.content.title.content
                            if reading_item.content.title
                            else "",
                            link=link,
                            content=md,  # @TODO USE THE API!
                            type="read",
                            uid=uid,
                            email=email,
                        )
                    )
                    session.add(
                        ReadingItemData(
                            item_uid=uid,
                            item_order=None,
                            archived=False,
                            done=None,
                            email=email,
                        )
                    )
                    session.commit()
    else:
        raise ValueError(f"Unknown source type: `{source_type}` for source `{source}`!")


async def refresh_data():
    while True:
        with orm.Session(engine) as session:
            sources = session.execute(select(Source)).scalars().all()
            for source in sources:
                consume_source(source.source, source.type, source.user_email)
        time.sleep(2)
