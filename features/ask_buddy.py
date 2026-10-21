"""Ask Buddy: chat with Claude about the orders SALTO Buddy has read."""
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from salto import config, errors, keystore
from ui import rich
from ui import theme as T

from .base import Feature

EXAMPLES = ["What is the site address?", "Serial numbers in creation", "Who is the delivery manager?",
            "Which sub-cases are open?"]


class AskBuddy(Feature):
    title = "Ask Buddy"
    icon = "\uE8BD"
    subtitle = "Ask anything about an order, in your own words"

    def build(self, parent):
        self.bot = None
        self.bot_key = ""
        self.busy = False
        head = tk.Frame(parent, bg=T.CARD)
        head.pack(fill="x")
        self.ctx = tk.Label(head, text="", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL)
        self.ctx.pack(side="left", padx=12)
        ttk.Button(head, text="New chat", command=self.new_chat).pack(side="right")
        tk.Label(parent, text="Answers come from Claude (Anthropic) and only use what SALTO shows.", bg=T.CARD,
                 fg=T.MUTED, font=T.F_SMALL, anchor="w").pack(fill="x", pady=(2, 8))

        # input row and example chips are pinned to the bottom; the conversation takes the rest
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(side="bottom", fill="x", pady=(4, 0))
        self.entry = ttk.Entry(row, font=(T.FONT, 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        self.send_btn = ttk.Button(row, text="Send", style="Accent.TButton", command=self.send)
        self.send_btn.pack(side="left", padx=(8, 0))
        chips = tk.Frame(parent, bg=T.CARD)
        chips.pack(side="bottom", fill="x", pady=(8, 4))
        for ex in EXAMPLES:
            c = tk.Label(chips, text=ex, bg=T.FIELD, fg=T.INK, font=T.F_SMALL, padx=12, pady=5, cursor="hand2")
            c.pack(side="left", padx=(0, 6))
            c.bind("<Button-1>", lambda e, t=ex: (self.entry.delete(0, "end"), self.entry.insert(0, t), self.send()))

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
        if self.bot:
            self.bot.reset()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._welcome()

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
            self.app.ui(lambda: self._answer(answer, tag))

        threading.Thread(target=work, daemon=True).start()

    def _answer(self, answer, tag):
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
