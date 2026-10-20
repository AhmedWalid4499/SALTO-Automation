"""Ask Buddy: chat with Claude about the orders SALTO Buddy has read."""
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from salto import config, keystore
from ui import theme as T

from .base import Feature

EXAMPLES = ["What is the site address?", "Serial numbers of the devices in creation",
            "Who is the local delivery manager?", "Which sub-cases are still open, and at what stage?"]


class AskBuddy(Feature):
    title = "Ask Buddy"

    def build(self, parent):
        self.bot = None
        self.busy = False
        head = tk.Frame(parent, bg=T.CARD)
        head.pack(fill="x")
        tk.Label(head, text="Ask Buddy", bg=T.CARD, fg=T.INK, font=T.F_TITLE).pack(side="left")
        self.ctx = tk.Label(head, text="", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL)
        self.ctx.pack(side="left", padx=12)
        ttk.Button(head, text="New chat", command=self.new_chat).pack(side="right")
        tk.Label(parent, text="Ask anything about an order: Buddy reads it from SALTO for you. Answers come from Claude "
                              "(Anthropic) and only use what SALTO shows.", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL,
                 anchor="w").pack(fill="x", pady=(2, 8))

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
            c = tk.Label(chips, text=ex, bg=T.BUTTON, fg=T.INK, font=T.F_SMALL, padx=10, pady=4, cursor="hand2",
                         highlightthickness=1, highlightbackground=T.BUTTON_BORDER)
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
        if self.bot:
            return True
        # own key first, then the team key file, then the environment
        key = (keystore.unprotect(self.app.cfg.get("claude_key", "")) or config.read_team_key(self.app.cfg)
               or os.environ.get("ANTHROPIC_API_KEY", ""))
        if not key:
            if messagebox.askyesno("SALTO Buddy", "Ask Buddy needs a Claude API key: your own, or the team key "
                                                  "(Settings > Ask Buddy > Team key folder).\n\nOpen Settings now?"):
                self.app.show_settings()
            return False
        from salto.assistant import Assistant
        self.bot = Assistant(key, self.app.reports, self._open_order, log=self.app.log)
        return True

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
            try:
                answer, tag = self.bot.ask(text, cur, status), "bot"
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
        self._put(answer + "\n", tag)
        self.busy = False
        self.send_btn.configure(state="normal")
        self._update_ctx()


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
    return f"Something went wrong: {str(exc).splitlines()[0][:200]}"
