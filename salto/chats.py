"""Saved Ask Buddy conversations, one JSON file each in %APPDATA%\\SALTO Buddy\\chats (per Windows user).

A chat belongs to the GOLD order it is about (named in the first question, or the order open in Order explorer),
so the chat list can group them by order.
"""
import json
import os
import re
import time
import uuid
from contextlib import suppress

from .config import CONFIG_DIR

CHAT_DIR = os.path.join(CONFIG_DIR, "chats")
ORDER_RE = re.compile(r"\b\d{2}-\d{6,8}\b")  # GOLD order, e.g. 10-1764901


def order_of(question, current=""):
    m = ORDER_RE.search(question or "")
    return m.group(0) if m else (current or "")


def new(question, current=""):
    now = time.time()
    return {"id": uuid.uuid4().hex[:12], "order": order_of(question, current),
            "title": re.sub(r"\s+", " ", question).strip()[:70], "created": now, "updated": now, "turns": []}


def add_turn(chat, question, answer, documents=(), created=()):
    """documents: files attached to the question (their text is kept so the chat can be continued; a PDF keeps
    only its name). created: files the bot's actions made."""
    docs = [{"name": d["name"], "kind": d["kind"], "text": d.get("text", "")} for d in documents]
    chat["turns"].append({"q": question, "a": answer, "time": time.time(), "docs": docs, "created": list(created)})
    chat["updated"] = time.time()
    save(chat)


def save(chat):
    os.makedirs(CHAT_DIR, exist_ok=True)
    path = os.path.join(CHAT_DIR, chat["id"] + ".json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(chat, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def load(chat_id):
    with suppress(OSError, ValueError):
        with open(os.path.join(CHAT_DIR, chat_id + ".json"), encoding="utf-8") as f:
            return json.load(f)
    return None


def delete(chat_id):
    with suppress(OSError):
        os.remove(os.path.join(CHAT_DIR, chat_id + ".json"))


def all_chats():
    """Every saved chat (without its turns' text loaded lazily: they are small), newest first."""
    out = []
    with suppress(OSError):
        for name in os.listdir(CHAT_DIR):
            if name.endswith(".json"):
                c = load(name[:-5])
                if isinstance(c, dict) and c.get("turns"):  # skip damaged files
                    c["id"] = name[:-5]  # the file name is what load() and delete() use
                    out.append(c)
    return sorted(out, key=lambda c: c.get("updated") or 0, reverse=True)


def grouped():
    """[(order or '', [chats newest first])], the order with the latest chat first."""
    groups = {}
    for c in all_chats():
        groups.setdefault(c.get("order", ""), []).append(c)
    return sorted(groups.items(), key=lambda kv: kv[1][0].get("updated") or 0, reverse=True)


def history_messages(chat):
    """The conversation as plain user/assistant turns, so a reopened chat can be continued."""
    msgs = []
    for t in chat.get("turns", []):
        docs = [{"type": "document", "title": d.get("name") or "Document",
                 "source": {"type": "text", "media_type": "text/plain", "data": d["text"]}}
                for d in t.get("docs", []) if d.get("text")]
        q = t.get("q") or ("Here is a document." if docs else "(no question)")  # the API refuses empty text
        user = docs + [{"type": "text", "text": q}] if docs else q
        msgs += [{"role": "user", "content": user}, {"role": "assistant", "content": t.get("a") or "(no answer)"}]
    return msgs
