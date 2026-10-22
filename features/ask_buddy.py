"""Ask Buddy: chat with Claude about the orders SALTO Buddy has read."""
import os
import threading
import tkinter as tk
from tkinter import ttk

import time

from salto import chats, config, errors, keystore
from ui import dialogs as messagebox
from ui import rich
from ui import theme as T
from ui.widgets import RoundButton, RoundEntry

from .base import Feature

# chip label -> the question it asks
EXAMPLES = {"Site address": "What is the site address and who is the local contact?",
            "Serial numbers": "Serial numbers of the devices in creation",
            "Delivery manager": "Who is the local delivery manager, and what is their email?",
            "Open sub-cases": "Which sub-cases are still open, and at what stage?"}


class AskBuddy(Feature):
    title = "Ask Buddy"
    icon = "\uE8BD"
    subtitle = "Ask anything about an order, in your own words"

    def build(self, parent):
        self.bot = None
        self.bot_key = ""
        self.busy = False
        self.chat_rec = None   # the saved chat on screen (None: a new chat, saved after its first answer)
        self._history = None   # turns of a reopened chat, given to Buddy before the next question
        self._history_panel(parent)
        parent = tk.Frame(parent, bg=T.CARD)
        parent.pack(side="left", fill="both", expand=True)
        head = tk.Frame(parent, bg=T.CARD)
        head.pack(fill="x")
        self.ctx = tk.Label(head, text="", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL)
        self.ctx.pack(side="left", padx=12)
        tk.Label(parent, text="Answers come from Claude (Anthropic) and only use what SALTO shows.", bg=T.CARD,
                 fg=T.MUTED, font=T.F_SMALL, anchor="w").pack(fill="x", pady=(2, 8))

        # input row and example chips are pinned to the bottom; the conversation takes the rest
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(side="bottom", fill="x", pady=(4, 0))
        self.entry = RoundEntry(row, width=300)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        self.send_btn = RoundButton(row, "Send", self.send)
        self.send_btn.pack(side="left", padx=(8, 0))
        chips = tk.Frame(parent, bg=T.CARD)
        chips.pack(side="bottom", fill="x", pady=(8, 4))
        for label, question in EXAMPLES.items():
            c = RoundButton(chips, label, lambda q=question: (self.entry.delete(0, "end"), self.entry.insert(0, q),
                                                              self.send()), kind="soft", padx=12, height=30,
                            font=T.F_SMALL)
            c.pack(side="left", padx=(0, 6))

        box = tk.Frame(parent, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE)
        box.pack(fill="both", expand=True)
        self.chat = tk.Text(box, wrap="word", borderwidth=0, highlightthickness=0, bg=T.CARD, fg=T.INK, font=T.F_BODY,
                            padx=16, pady=12, state="disabled", spacing1=2, spacing3=2, cursor="arrow")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.chat.pack(fill="both", expand=True)
        self.chat.tag_configure("you_name", font=T.F_SMALL_BOLD, foreground=T.ORANGE, spacing1=10)
        self.chat.tag_configure("you", background=T.ORANGE_TINT, lmargin1=8, lmargin2=8, rmargin=60, spacing3=6)
        self.chat.tag_configure("bot_name", font=T.F_SMALL_BOLD, foreground=T.MUTED, spacing1=10)
        self.chat.tag_configure("bot", lmargin1=8, lmargin2=8, rmargin=20, spacing3=6)
        self.chat.tag_configure("status", font=T.F_SMALL, foreground=T.MUTED, lmargin1=8)
        self.chat.tag_configure("error", foreground=T.RED, lmargin1=8, lmargin2=8)
        self.chat.tag_configure("copy", font=T.F_SMALL, foreground=T.ORANGE, lmargin1=8, spacing1=2, spacing3=8)
        rich.setup(self.chat)
        self.answers = 0

        self._welcome()
        parent.bind("<Map>", lambda e: self._update_ctx())

    # ------------------------------------------------------------ helpers
    def _put(self, text, *tags):
        self.chat.configure(state="normal")
        self.chat.insert("end", text, tags)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _welcome(self):
        self._put("Buddy\n", "bot_name")
        self._put("Hi! Open an order in Order explorer, or just name one here, and ask me about it.\n", "bot")

    def _current(self):
        ex = self.app.explorer
        return ex.rep.order_ref if ex and ex.rep and ex.rep.stc_id else ""

    def _update_ctx(self):
        cur = self._current()
        loaded = list(self.app.reports)
        self.ctx.configure(text=(f"Current order: {cur}" if cur else "No order open")
                           + (f"   ·   loaded: {', '.join(loaded)}" if loaded else ""))

    def new_chat(self):
        if self.busy:
            return
        if self.bot:
            self.bot.reset()
        self.chat_rec, self._history = None, None
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._welcome()
        self.tree.selection_remove(self.tree.selection())
        self.entry.focus_set()

    # ------------------------------------------------------------ saved chats, grouped by order
    def _history_panel(self, parent):
        side = tk.Frame(parent, bg=T.CARD)
        side.pack(side="left", fill="y", padx=(0, 16))
        top = tk.Frame(side, bg=T.CARD)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Chats", bg=T.CARD, fg=T.INK, font=T.F_SECTION).pack(side="left")
        RoundButton(top, "+ New chat", self.new_chat, kind="dark", padx=14, height=32).pack(side="right")
        box = tk.Frame(side, bg=T.FIELD)
        box.pack(fill="both", expand=True)
        k = max(1.0, parent.winfo_fpixels("1i") / 96)
        self.tree = ttk.Treeview(box, show="tree", style="Nav.Treeview", selectmode="browse")
        self.tree.column("#0", width=int(215 * k))
        self.tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        self.tree.tag_configure("order", font=T.F_SMALL_BOLD, foreground=T.MUTED)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._open_selected())
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(label="Delete this chat", command=self._delete_selected)
        self.tree.bind("<Button-3>", lambda e: (self.tree.identify_row(e.y).startswith("chat:")
                                                 and (self.tree.selection_set(self.tree.identify_row(e.y)),
                                                      menu.tk_popup(e.x_root, e.y_root))))
        tk.Label(side, text="Saved on this PC. Right-click a chat to delete it.", bg=T.CARD, fg=T.SUBTLE,
                 font=T.F_SMALL, anchor="w").pack(fill="x", pady=(6, 0))
        self._fill_tree()

    def _fill_tree(self, select=None):
        t = self.tree
        t.delete(*t.get_children())
        groups = chats.grouped()
        if not groups:
            t.insert("", "end", iid="empty", text="No saved chats yet", tags=("order",))
        for order, items in groups:
            gid = f"order:{order or '-'}"
            t.insert("", "end", iid=gid, text=f"{order or 'No order'}  ({len(items)})", open=True, tags=("order",))
            for c in items:
                when = time.strftime("%d %b", time.localtime(c.get("updated", 0)))
                t.insert(gid, "end", iid=f"chat:{c['id']}", text=f"{c['title'][:34]}  · {when}")
        if select and t.exists(f"chat:{select}"):
            t.selection_set(f"chat:{select}")
            t.see(f"chat:{select}")

    def _open_selected(self):
        sel = self.tree.selection()
        if not sel or not sel[0].startswith("chat:") or self.busy:
            return
        cid = sel[0][5:]
        if self.chat_rec and self.chat_rec["id"] == cid:
            return
        c = chats.load(cid)
        if not c:
            return
        self.chat_rec = c
        self._history = chats.history_messages(c)  # Buddy continues this conversation
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._put(f"{c.get('order') or 'No order'} · started "
                  f"{time.strftime('%d %b %Y %H:%M', time.localtime(c.get('created', 0)))}\n", "status")
        for turn in c.get("turns", []):
            self._put("You\n", "you_name")
            self._put(turn["q"] + "\n", "you")
            self._put("Buddy\n", "bot_name")
            self._show_answer(turn["a"])
        self.chat.see("end")

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel or not sel[0].startswith("chat:"):
            return
        if not messagebox.askyesno("Delete chat", "Delete this saved chat? This cannot be undone.",
                                   parent=self.tree):
            return
        cid = sel[0][5:]
        chats.delete(cid)
        if self.chat_rec and self.chat_rec["id"] == cid:
            self.new_chat()
        self._fill_tree()

    def _ensure_bot(self):
        return True  # the key is resolved on the chat thread (it may need SharePoint): see _get_bot

    def _local_key(self):
        """(key, source) from: own key, synced team file, team key cached from SharePoint, environment."""
        cfg = self.app.cfg
        for source, key in (("own", keystore.unprotect(cfg.get("claude_key", ""))),
                            ("team file", config.read_team_key(cfg)),
                            ("cache", keystore.unprotect(cfg.get("team_key_cache", ""))),
                            ("env", os.environ.get("ANTHROPIC_API_KEY", ""))):
            if key:
                return key, source
        return "", ""

    def _fetch_team_key(self, status):
        """Blocking (chat thread): read the team key from the SharePoint link through the browser worker."""
        from salto import teamkey
        status("Getting the team key from SharePoint (first time only)...")
        done, box = threading.Event(), {}
        self.app.worker.submit(lambda b: teamkey.fetch(b, log=self.app.log),
                               lambda key: (box.update(key=key), done.set()),
                               lambda exc: (box.update(err=exc), done.set()))
        done.wait()
        if box.get("err"):
            raise RuntimeError(f"Could not get the team key from SharePoint: {box['err']}")
        key = box["key"]

        def save():
            self.app.cfg["team_key_cache"] = keystore.protect(key)
            config.save(self.app.cfg)
        self.app.ui(save)
        return key

    def _get_bot(self, status, refresh=False):
        key, source = ("", "") if refresh else self._local_key()
        if not key:
            key, source = self._fetch_team_key(status), "cache"
        if not self.bot or self.bot_key != key:
            from salto.assistant import Assistant
            self.bot = Assistant(key, self.app.reports, self._open_order, log=self.app.log,
                                 find_person=self._find_person)
            self.bot_key = key
        return source

    def key_changed(self):
        self.bot = None  # rebuilt with the new key on the next question

    # ------------------------------------------------------------ open_order tool: dissect through the browser worker
    def _open_order(self, ref):
        """Called from the chat thread; blocks until the Order explorer has read the order."""
        done, box = threading.Event(), {}
        self.app.ui(lambda: self.app.explorer.open_for_chat(ref, lambda rep, err: (box.update(rep=rep, err=err), done.set())))
        done.wait()
        if box.get("err"):
            raise box["err"]
        return box.get("rep")

    def _find_person(self, last, first, email):
        """find_person tool (chat thread): Org Chart search through the browser worker, blocking."""
        from salto import orgchart
        done, box = threading.Event(), {}
        self.app.worker.submit(lambda b: orgchart.find(b, last, first, email, log=self.app.log),
                               lambda r: (box.update(r=r), done.set()),
                               lambda exc: (box.update(err=exc), done.set()))
        done.wait()
        if box.get("err"):
            raise box["err"]
        return box["r"]

    # ------------------------------------------------------------ send
    def send(self):
        text = self.entry.get().strip()
        if not text or self.busy or not self._ensure_bot():
            return
        self.entry.delete(0, "end")
        self._put("You\n", "you_name")
        self._put(f"{text}\n", "you")
        self._put("Buddy\n", "bot_name")
        self.chat.configure(state="normal")
        self.chat.insert("end", "Thinking...\n", ("status", "pending"))
        self.chat.configure(state="disabled")
        self.busy = True
        self.send_btn.configure(state="disabled")
        cur = self._current()

        def status(msg):
            def upd():
                self.chat.configure(state="normal")
                r = self.chat.tag_ranges("pending")
                if r:
                    self.chat.delete(r[0], r[1])
                    self.chat.insert(r[0], msg + "\n", ("status", "pending"))
                self.chat.configure(state="disabled")
            self.app.ui(upd)

        def work():
            import anthropic
            try:
                source = self._get_bot(status)
                if self._history is not None:  # a reopened chat: Buddy continues it
                    self.bot.messages = list(self._history)
                    self._history = None
                elif self.chat_rec is None:
                    self.bot.reset()
                try:
                    answer = self.bot.ask(text, cur, status)
                except anthropic.AuthenticationError:
                    if source != "cache":
                        raise
                    # the team key was replaced on SharePoint: fetch the new one and ask again
                    self.bot.messages.pop()  # drop the unanswered question; it is asked again below
                    self._get_bot(status, refresh=True)
                    answer = self.bot.ask(text, cur, status)
                tag = "bot"
            except Exception as exc:
                answer, tag = _friendly(exc), "error"
            self.app.ui(lambda: self._answer(answer, tag, text, cur))

        threading.Thread(target=work, daemon=True).start()

    def _answer(self, answer, tag, question="", cur=""):
        self.chat.configure(state="normal")
        r = self.chat.tag_ranges("pending")
        if r:
            self.chat.delete(r[0], r[1])
        self.chat.configure(state="disabled")
        if tag == "bot":
            self._show_answer(answer)
        else:
            self._put(answer + "\n", tag)
        self.busy = False
        self.send_btn.configure(state="normal")
        self._update_ctx()
        if tag == "bot" and question:  # keep it: saved chats, grouped by order
            if self.chat_rec is None:
                self.chat_rec = chats.new(question, cur)
            chats.add_turn(self.chat_rec, question, answer)
            self._fill_tree(select=self.chat_rec["id"])
            first = next((l for l in answer.splitlines() if l.strip()), "").replace("**", "")
            self.app.notify("Buddy answered", first[:140], page=self, only_if_away=True)

    def _show_answer(self, answer):
        """Formatted answer (headings, bullets, bold, tables) and a Copy link under it."""
        self.answers += 1
        link = f"copy{self.answers}"
        self.chat.configure(state="normal")
        rich.render(self.chat, answer)
        self.chat.insert("end", "Copy answer\n", ("copy", link))
        self.chat.tag_bind(link, "<Button-1>", lambda e, t=answer: self._copy(t))
        self.chat.tag_bind(link, "<Enter>", lambda e: self.chat.configure(cursor="hand2"))
        self.chat.tag_bind(link, "<Leave>", lambda e: self.chat.configure(cursor="arrow"))
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _copy(self, answer):
        self.chat.clipboard_clear()
        self.chat.clipboard_append(rich.plain(answer))
        self.app.log("Answer copied.")


def _friendly(exc):
    import anthropic
    if isinstance(exc, anthropic.AuthenticationError):
        return "The Claude API key was refused. Check it in Settings."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This API key is not allowed to use the model. Check your Anthropic account."
    if isinstance(exc, anthropic.RateLimitError):
        return "Claude is rate-limited right now. Wait a minute and try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach Claude (api.anthropic.com). Check the network / VPN."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Claude returned an error ({exc.status_code}). Try again."
    return f"Something went wrong: {errors.note(exc)}"
