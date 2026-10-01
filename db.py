"""Stores settings per (bot, chat) in SQLite."""
import json
import sqlite3

DEFAULTS = {"title": None, "emoji": "🟢", "step": 10, "min_buy": 0, "whale": 0,
            "media": None, "links": {}, "paused": False, "sells": False}

chats: dict[tuple[int, int], dict] = {}
_con: sqlite3.Connection | None = None


def init(path: str):
    global _con
    _con = sqlite3.connect(path)
    _con.execute("CREATE TABLE IF NOT EXISTS chats (bot INTEGER, chat INTEGER, cfg TEXT, PRIMARY KEY (bot, chat))")
    chats.update({(b, c): {**DEFAULTS, **json.loads(j)} for b, c, j in _con.execute("SELECT * FROM chats")})


def get(key) -> dict:
    return chats.get(key) or dict(DEFAULTS)


def save(key, cfg: dict):
    chats[key] = cfg
    _con.execute("REPLACE INTO chats VALUES (?, ?, ?)", (*key, json.dumps(cfg)))
    _con.commit()


def delete(key):
    chats.pop(key, None)
    _con.execute("DELETE FROM chats WHERE bot = ? AND chat = ?", key)
    _con.commit()
