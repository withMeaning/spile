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
import requests
import sqlite3
from uuid import uuid4
import threading
import time
from hashlib import md5
from fastapi.middleware.cors import CORSMiddleware
from rss_parser import Parser
import markdownify


def link_to_md(link: str):
    obj = requests.get(
        f"https://api.diffbot.com/v3/article?url={link}&token=6165e93d46dfa342d862a975c813a296"
    ).json()
    html = obj["objects"][0]["html"]
    md = markdownify.markdownify(html, heading_style="ATX")
    return md


def detect_source_type(source: str):
    if "@" in source and "get_feed" in source:
        return "spile"
    return "rss"


def generate_auth_token():
    return str(uuid4())


def generate_content_uid(content: str | list[object]):
    if isinstance(content, list):
        content = " --- ".join([str(x) for x in content])
    return str(md5(content.encode("utf-8")).hexdigest())
