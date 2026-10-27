"""Saved Ask Buddy conversations: confidential, so they never leave this PC.

One file per chat in %LOCALAPPDATA%\\SaltoBuddy\\chats - the local part of the Windows profile, which is never
roamed or synced - encrypted with Windows DPAPI (keystore): only this Windows user on this PC can read them.

A chat belongs to the GOLD order it is about (named in the first question, or the order open in Order explorer),
so the chat list can group them by order.
"""
import json
import os
import re
import time
import uuid
from contextlib import suppress

from . import keystore
from .config import CONFIG_DIR

CHAT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SaltoBuddy", "chats")
EXT = ".chat"
_OLD_DIR = os.path.join(CONFIG_DIR, "chats")  # before 1.15.1: plain JSON in the roaming profile
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


def _path(chat_id):
    return os.path.join(CHAT_DIR, chat_id + EXT)


def save(chat):
    os.makedirs(CHAT_DIR, exist_ok=True)
    path = _path(chat["id"])
    with open(path + ".tmp", "w", encoding="ascii") as f:
        f.write(keystore.protect(json.dumps(chat, ensure_ascii=False)))
    os.replace(path + ".tmp", path)


def load(chat_id):
    with suppress(OSError, ValueError):
        with open(_path(chat_id), encoding="ascii") as f:
            text = keystore.unprotect(f.read().strip())
        return json.loads(text) if text else None  # "": another user or PC, or a damaged file
    return None


def delete(chat_id):
    with suppress(OSError):
        os.remove(_path(chat_id))


def _move_old_chats():
    """Chats saved by older versions (plain files in the roaming profile): encrypt them here, then remove them."""
    with suppress(OSError):
        names = [n for n in os.listdir(_OLD_DIR) if n.endswith(".json")]
        for name in names:
            old = os.path.join(_OLD_DIR, name)
            try:
                with open(old, encoding="utf-8") as f:
                    chat = json.load(f)
                if not isinstance(chat, dict):
                    continue
                chat["id"] = name[:-5]
                save(chat)
                if load(chat["id"]) == chat:  # safely in the new place: only then remove the plain copy
                    os.remove(old)
            except (OSError, ValueError):
                continue
        with suppress(OSError):
            os.rmdir(_OLD_DIR)  # only if it is empty now


def all_chats():
    """Every saved chat, newest first."""
    _move_old_chats()
    out = []
    with suppress(OSError):
        for name in os.listdir(CHAT_DIR):
            if name.endswith(EXT):
                c = load(name[:-len(EXT)])
                if isinstance(c, dict) and c.get("turns"):  # skip damaged files
                    c["id"] = name[:-len(EXT)]  # the file name is what load() and delete() use
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
