"""The Friendly SALTO Bot: a chat with Claude about the orders SALTO Buddy has read."""
import os
import threading
import time
import tkinter as tk
from tkinter import ttk

from salto import chats, config, errors, keystore
from ui import dialogs as messagebox
from ui import rich
from ui import theme as T
from ui.bot_kit import AIBanner, Bot
from ui.chatview import ChatView
from ui.widgets import IconButton, RoundButton, RoundCard, RoundEntry

from .base import Feature

BOT_NAME = "The Friendly SALTO Bot"
HINT = "Reads SALTO and the Org Chart for you. It never changes anything in SALTO."
# suggestion label -> the question it asks
EXAMPLES = {"Site address": "What is the site address and who is the local contact?",
            "Serial numbers": "Serial numbers of the devices in creation",
            "Delivery manager": "Who is the local delivery manager, and what is their email?",
            "Open sub-cases": "Which sub-cases are still open, and at what stage?"}


class AskBuddy(Feature):
    title = BOT_NAME
    icon = "\uE99A"  # robot
    subtitle = "Chat about any order, in your own words"
    nav_title = "SALTO Bot"

    def build(self, parent):
        self.bot = None
        self.bot_key = ""
        self.busy = False
        self.chat_rec = None   # the saved chat on screen (None: a new chat, saved after its first answer)
        self._history = None   # turns of a reopened chat, given to the bot before the next question
        self._history_panel(parent)
        parent = tk.Frame(parent, bg=T.CARD)
        parent.pack(side="left", fill="both", expand=True)

        # header: the flowing banner with the bot, its name, what it does, the order in view and New chat
        k = max(1.0, parent.winfo_fpixels("1i") / 96)
        self.banner = AIBanner(parent, BOT_NAME, HINT, on_new=self.new_chat, height=int(62 * k))
        self.banner.pack(fill="x", pady=(0, 6))

        # the message box is pinned to the bottom; the conversation takes the rest
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(side="bottom", fill="x", pady=(8, 0))
        IconButton(row, "\uE723", "Attach a Word, PDF or text document", self.attach, size=38).pack(side="left",
                                                                                            padx=(0, 8))
        self.entry = RoundEntry(row, width=300, placeholder="Ask about an order...")
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        self.send_btn = RoundButton(row, "Send", self.send, kind="ai", icon="\uE724", height=38)
        self.send_btn.pack(side="left", padx=(8, 0))
        # documents attached to the next message: one chip each, x to remove
        self.docs = []
        self.doc_row = tk.Frame(parent, bg=T.CARD)
        self.doc_row.pack(side="bottom", fill="x")
        note = tk.Label(parent, text="Answers come from Claude (Anthropic) and only use what SALTO shows. Attached "
                                     "documents are sent to Claude too.", bg=T.CARD, fg=T.SUBTLE, font=T.F_SMALL,
                        anchor="w", justify="left")
        note.pack(side="bottom", fill="x", pady=(6, 0))
        note.bind("<Configure>", lambda e: note.configure(wraplength=max(200, e.width - 4)))

        self.area = tk.Frame(parent, bg=T.CARD)
        self.area.pack(fill="both", expand=True)
        self.view = ChatView(self.area, BOT_NAME)
        self.welcome = self._welcome_screen(self.area)
        self._show_welcome(True)
        parent.bind("<Map>", lambda e: self._update_ctx())

    # ------------------------------------------------------------ welcome screen
    def _welcome_screen(self, parent):
        w = tk.Frame(parent, bg=T.CARD)
        box = tk.Frame(w, bg=T.CARD)
        box.place(relx=0.5, rely=0.45, anchor="center")
        k = max(1.0, parent.winfo_fpixels("1i") / 96)
        Bot(box, size=int(130 * k), bg=T.CARD).pack()
        tk.Label(box, text=f"Hi! I'm {BOT_NAME}", bg=T.CARD, fg=T.INK, font=T.F_TITLE).pack(pady=(4, 2))
        tk.Label(box, text="Ask me anything about an order: its site, devices, serial numbers, people or sub-cases.",
                 bg=T.CARD, fg=T.MUTED, font=T.F_SMALL, wraplength=int(360 * k), justify="center").pack()
        chips = tk.Frame(box, bg=T.CARD)
        chips.pack(pady=(14, 0))
        for i, (label, question) in enumerate(EXAMPLES.items()):
            RoundButton(chips, label, lambda q=question: self._ask_example(q), kind="ai_soft", padx=14, height=32,
                        font=T.F_SMALL).grid(row=i // 2, column=i % 2, padx=4, pady=4)
        return w

    def _show_welcome(self, on):
        if on:
            self.view.pack_forget()
            self.welcome.pack(fill="both", expand=True)
        else:
            self.welcome.pack_forget()
            self.view.pack(fill="both", expand=True)

    def _ask_example(self, question):
        self.entry.delete(0, "end")
        self.entry.insert(0, question)
        self.send()

    # ------------------------------------------------------------ helpers
    def _current(self):
        ex = self.app.explorer
        return ex.rep.order_ref if ex and ex.rep and ex.rep.stc_id else ""

    def _update_ctx(self):
        cur = self._current()
        self.banner.set(hint="Working on it..." if self.busy else HINT, chip=f"Order {cur}" if cur else "")

    def new_chat(self):
        if self.busy:
            return
        if self.bot:
            self.bot.reset()
        self.chat_rec, self._history = None, None
        self.view.clear()
        self._show_welcome(True)
        self.tree.selection_remove(self.tree.selection())
        self.entry.focus_set()

    # ------------------------------------------------------------ saved chats, grouped by order
    def _history_panel(self, parent):
        side = tk.Frame(parent, bg=T.CARD)
        side.pack(side="left", fill="y", padx=(0, 16))
        top = tk.Frame(side, bg=T.CARD)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Chats", bg=T.CARD, fg=T.INK, font=T.F_SECTION).pack(side="left")
        k = max(1.0, parent.winfo_fpixels("1i") / 96)
        card = RoundCard(side, fill=T.FIELD, radius=12, pad=4, shadow=False, width=int(216 * k))
        card.pack(fill="both", expand=True)
        box = card.inner
        self.tree = ttk.Treeview(box, show="tree", style="Nav.Treeview", selectmode="browse")
        self.tree.column("#0", width=int(185 * k))
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("order", font=T.F_SMALL_BOLD, foreground=T.MUTED)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._open_selected())
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(label="Delete this chat", command=self._delete_selected)
        self.tree.bind("<Button-3>", lambda e: (self.tree.identify_row(e.y).startswith("chat:")
                                                 and (self.tree.selection_set(self.tree.identify_row(e.y)),
                                                      menu.tk_popup(e.x_root, e.y_root))))
        tk.Label(side, text="Encrypted, on this PC only.\nRight-click a chat to delete it.", bg=T.CARD, fg=T.SUBTLE,
                 font=T.F_SMALL, anchor="w", justify="left").pack(fill="x", pady=(6, 0))
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
                if not c.get("id") or t.exists(f"chat:{c['id']}"):
                    continue  # a damaged or duplicated chat file
                when = time.strftime("%d %b", time.localtime(c.get("updated", 0) or 0))
                t.insert(gid, "end", iid=f"chat:{c['id']}", text=f"{str(c.get('title') or 'Chat')[:34]}  · {when}")
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
        self._history = chats.history_messages(c)  # the bot continues this conversation
        self._show_welcome(False)
        self.view.clear()
        self.view.add_note(f"{c.get('order') or 'No order'} · started "
                           f"{time.strftime('%d %b %Y %H:%M', time.localtime(c.get('created', 0)))}")
        for turn in c.get("turns", []):
            self.view.add_user(turn.get("q", ""), files=[d.get("name", "") for d in turn.get("docs", [])])
            self.view.add_bot().finish(turn.get("a", ""), on_copy=self._copy, files=turn.get("created", []))
        self.view.scroll_end()

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

    # ------------------------------------------------------------ Claude key
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
        status("Getting the team key from SharePoint (first time only)")
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
            old = self.bot or getattr(self, "_old_bot", None)
            self.bot = Assistant(key, self.app.reports, self._open_order, log=self.app.log,
                                 find_person=self._find_person)
            if old is not None:  # a new key: the conversation goes on
                self.bot.messages = list(old.messages)
            self.bot_key, self._old_bot = key, None
        return source

    def key_changed(self):
        if self.bot is not None:  # rebuilt with the new key on the next question, keeping the conversation
            self._old_bot, self.bot = self.bot, None

    # ------------------------------------------------------------ tools that need the browser (chat thread, blocking)
    def _open_order(self, ref):
        """open_order tool: blocks until the Order explorer has read the order."""
        done, box = threading.Event(), {}
        self.app.ui(lambda: self.app.explorer.open_for_chat(ref, lambda rep, err: (box.update(rep=rep, err=err), done.set())))
        if not done.wait(45 * 60):  # a big order takes minutes, never this long
            raise TimeoutError(f"{ref} took too long to read")
        if box.get("err"):
            raise box["err"]
        return box.get("rep")

    def _find_person(self, last, first, email):
        """find_person tool: Org Chart search through the browser worker."""
        from salto import orgchart
        done, box = threading.Event(), {}
        self.app.worker.submit(lambda b: orgchart.find(b, last, first, email, log=self.app.log),
                               lambda r: (box.update(r=r), done.set()),
                               lambda exc: (box.update(err=exc), done.set()))
        done.wait()
        if box.get("err"):
            raise box["err"]
        return box["r"]

    # ------------------------------------------------------------ documents
    def attach(self):
        from tkinter import filedialog
        from salto import documents
        paths = filedialog.askopenfilenames(title="Attach documents", filetypes=documents.FILETYPES,
                                            parent=self.entry)
        problems = []
        for p in paths:
            try:
                doc = documents.load(p)
            except (documents.DocumentError, OSError) as exc:
                problems.append(str(exc))
                continue
            if all(d["name"] != doc["name"] for d in self.docs):
                self.docs.append(doc)
        self._show_docs()
        if problems:
            messagebox.showwarning("Attach documents", "\n\n".join(problems), parent=self.entry)
        self.entry.focus_set()

    def _show_docs(self):
        for w in self.doc_row.winfo_children():
            w.destroy()
        for doc in self.docs:
            chip = tk.Frame(self.doc_row, bg=T.ORANGE_TINT)
            chip.pack(side="left", padx=(0, 6), pady=(8, 0))
            tk.Label(chip, text="\uE8A5", font=(T.ICONS, 11), bg=T.ORANGE_TINT, fg=T.ORANGE).pack(side="left",
                                                                                              padx=(8, 4), pady=4)
            size = f"{doc['chars'] // 1000 + 1}k characters" if doc["kind"] == "text" else \
                f"PDF, {doc['size'] // 1024 + 1} KB"
            tk.Label(chip, text=f"{doc['name']}  ·  {size}", font=T.F_SMALL, bg=T.ORANGE_TINT,
                     fg=T.INK).pack(side="left")
            x = tk.Label(chip, text="✕", font=T.F_SMALL, bg=T.ORANGE_TINT, fg=T.MUTED, cursor="hand2")
            x.pack(side="left", padx=(6, 8))
            x.bind("<Button-1>", lambda e, d=doc: (self.docs.remove(d), self._show_docs()))

    # ------------------------------------------------------------ send
    def send(self):
        text = self.entry.get().strip()
        docs, self.docs = list(self.docs), []
        if (not text and not docs) or self.busy:
            self.docs = docs
            return
        if not text:
            text = "Please read this document and do what it asks, if you can."
        self.entry.delete(0, "end")
        self._show_docs()
        self._show_welcome(False)
        self.view.add_user(text, files=[d["name"] for d in docs])
        msg = self.view.add_bot()
        self.busy = True
        self.send_btn.configure(state="disabled")
        self._update_ctx()
        cur = self._current()

        def status(s):
            self.app.ui(lambda: msg.typing(s))

        def piece(s):
            self.app.ui(lambda: msg.stream(s))

        def work():
            import anthropic
            try:
                source = self._get_bot(status)
                if self._history is not None:  # a reopened chat: the bot continues it
                    self.bot.messages = list(self._history)
                    self._history = None
                elif self.chat_rec is None:
                    self.bot.reset()
                try:
                    answer = self.bot.ask(text, cur, status, on_text=piece, documents=docs)
                except anthropic.AuthenticationError:
                    if source != "cache":
                        raise
                    # the team key was replaced on SharePoint: fetch the new one and ask again
                    self.bot.messages.pop()  # drop the unanswered question; it is asked again below
                    self._get_bot(status, refresh=True)
                    answer = self.bot.ask(text, cur, status, on_text=piece, documents=docs)
                ok = True
            except Exception as exc:
                answer, ok = _friendly(exc), False
            created = list(getattr(self.bot, "created", []) or [])
            self.app.ui(lambda: self._answer(msg, answer, ok, text, cur, docs, created))

        threading.Thread(target=work, daemon=True).start()

    def _answer(self, msg, answer, ok, question, cur, docs=(), created=()):
        self.busy = False
        self.send_btn.configure(state="normal")
        self._update_ctx()
        if not ok:
            msg.error(answer)
            return
        msg.finish(answer, on_copy=self._copy, files=created)
        if self.chat_rec is None:  # keep it: saved chats, grouped by order (also an order named in a document)
            named = next((chats.order_of(d.get("text", "")) for d in docs if chats.order_of(d.get("text", ""))), "")
            self.chat_rec = chats.new(question, named or cur)
        chats.add_turn(self.chat_rec, question, answer, documents=docs, created=created)
        self._fill_tree(select=self.chat_rec["id"])
        first = next((l for l in answer.splitlines() if l.strip()), "").replace("**", "")
        self.app.notify(f"{BOT_NAME} answered", first[:140], page=self, only_if_away=True)

    def _copy(self, answer):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(rich.plain(answer))
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
