"""A messenger-style conversation: the user's messages on the right (orange bubbles), the bot's on the left next to
its robot avatar. Bot messages fill in as they are written (stream), then get their final formatting (tables...)."""
import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import rich
from . import theme as T
from .robot import Robot
from .widgets import RoundCard, _scale

BOT_BUBBLE, USER_BUBBLE = "#F1F3F7", T.ORANGE


class ChatView(tk.Frame):
    def __init__(self, parent, bot_name="The Friendly SALTO Bot"):
        super().__init__(parent, bg=T.CARD)
        self.bot_name, self.k = bot_name, _scale(parent)
        self.canvas = tk.Canvas(self, bg=T.CARD, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T.CARD)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda e: self.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.unbind_all("<MouseWheel>"))
        self.messages = []

    # ------------------------------------------------------------ layout
    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) * 3, "units")

    def _resize(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        for m in self.messages:
            m.relayout()

    def max_width(self, bot=False):
        """Widest bubble: the bot's use the room next to the avatar, the user's about 3/4 of the chat."""
        w = self.canvas.winfo_width() or 700
        return max(int(240 * self.k), int(w - 90 * self.k) if bot else int(w * 0.74))

    def scroll_end(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.messages = []
        self.canvas.yview_moveto(0)

    # ------------------------------------------------------------ messages
    def add_user(self, text):
        row = tk.Frame(self.inner, bg=T.CARD)
        row.pack(fill="x", padx=12, pady=(10, 2))
        bubble = RoundCard(row, fill=USER_BUBBLE, radius=18, pad=12, fit=True, shadow=False)
        bubble.pack(side="right")
        lbl = tk.Label(bubble.inner, text=text, bg=USER_BUBBLE, fg="white", font=T.F_BODY, justify="left",
                       anchor="w")
        lbl.pack()
        m = _UserMessage(self, bubble, lbl)
        self.messages.append(m)
        m.relayout()
        self.scroll_end()
        return m

    def add_bot(self):
        m = _BotMessage(self)
        self.messages.append(m)
        self.scroll_end()
        return m

    def add_note(self, text):
        tk.Label(self.inner, text=text, bg=T.CARD, fg=T.SUBTLE, font=T.F_SMALL).pack(pady=(10, 0))


class _UserMessage:
    def __init__(self, view, bubble, label):
        self.view, self.bubble, self.label = view, bubble, label

    def relayout(self):
        f = tkfont.Font(font=T.F_BODY)
        longest = max((f.measure(l) for l in self.label.cget("text").splitlines()), default=0)
        width = min(self.view.max_width(), longest + 6)
        self.label.configure(wraplength=width)
        self.bubble.configure(width=width + 2 * self.bubble.pad)


class _BotMessage:
    """One bot message: typing dots, then streamed text, then the formatted answer."""

    def __init__(self, view):
        self.view, self.raw, self.done = view, "", False
        k = view.k
        row = tk.Frame(view.inner, bg=T.CARD)
        row.pack(fill="x", padx=12, pady=(12, 2))
        left = tk.Frame(row, bg=T.CARD)
        left.pack(side="left", anchor="n", padx=(0, 10))
        self.avatar = Robot(left, size=int(38 * k), animate=False, shadow=False, bg=T.CARD)
        self.avatar.pack()
        col = tk.Frame(row, bg=T.CARD)
        col.pack(side="left", fill="x", expand=True, anchor="w")
        tk.Label(col, text=view.bot_name, bg=T.CARD, fg=T.MUTED, font=T.F_SMALL_BOLD, anchor="w").pack(anchor="w")
        self.bubble = RoundCard(col, fill=BOT_BUBBLE, radius=18, pad=12, fit=True, shadow=False)
        self.bubble.pack(anchor="w", pady=(3, 0))
        self.holder = tk.Frame(self.bubble.inner, bg=BOT_BUBBLE)
        self.holder.pack(anchor="w")
        self.holder.pack_propagate(False)
        self.text = tk.Text(self.holder, wrap="word", borderwidth=0, highlightthickness=0, bg=BOT_BUBBLE,
                            fg=T.INK, font=T.F_BODY, padx=0, pady=0, cursor="arrow", spacing1=1, spacing3=2)
        self.text.pack(fill="both", expand=True)
        rich.setup(self.text)
        for tag in ("md_body", "md_h", "md_source", "md_b1", "md_b2"):  # no extra side margins in a bubble
            self.text.tag_configure(tag, lmargin1=0, lmargin2=0, rmargin=0)
        self.text.tag_configure("md_b1", lmargin1=2, lmargin2=18)
        self.text.tag_configure("md_b2", lmargin1=20, lmargin2=36)
        self.text.tag_configure("status", foreground=T.MUTED, font=T.F_SMALL)
        self.text.tag_configure("error", foreground=T.RED)
        self.actions = tk.Frame(col, bg=T.CARD)
        self.actions.pack(anchor="w", pady=(3, 0))
        self.dots, self.status = 0, "Thinking"
        self._typing_job = None
        self.typing("Thinking")

    # typing indicator: "Thinking ●●●" with the dots growing
    def typing(self, status=None):
        if self.done or self.raw:
            return
        if status:
            self.status = status.rstrip(". ")
        self.dots = self.dots % 3 + 1
        self._set_text([(f"{self.status} ", "status"), ("●" * self.dots + "○" * (3 - self.dots), "status")])
        if self._typing_job is None:
            self._typing_job = self.view.after(380, self._typing_tick)

    def _typing_tick(self):
        self._typing_job = None
        if not self.done and not self.raw and self.text.winfo_exists():
            self.typing()

    def stream(self, piece):
        """More text from the bot, shown as it arrives (plain; formatted when finished)."""
        self.raw += piece
        shown = re.sub(r"\*\*", "", self.raw)
        self._set_text([(shown, "md_body")])
        self.view.scroll_end()

    def finish(self, markdown, on_copy=None):
        self.done = True
        self.raw = markdown
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        rich.render(self.text, markdown)
        self.text.delete("end-2c", "end-1c") if self.text.get("end-2c", "end-1c") == "\n" else None
        self.text.configure(state="disabled")
        self.relayout()
        if on_copy:
            link = tk.Label(self.actions, text="Copy", bg=T.CARD, fg=T.ORANGE, font=T.F_SMALL_BOLD,
                            cursor="hand2")
            link.pack(side="left")
            link.bind("<Button-1>", lambda e: (on_copy(markdown), link.configure(text="Copied")))
        self.view.scroll_end()

    def error(self, message):
        self.done = True
        self._set_text([(message, "error")])

    def _set_text(self, parts):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for s, tag in parts:
            self.text.insert("end", s, tag)
        self.text.configure(state="disabled")
        self.relayout()

    def relayout(self):
        """Bubble as wide as its text (up to ~3/4 of the chat), as tall as its content."""
        view = self.view
        maxw = view.max_width(bot=True)
        has_table = bool(self.text.window_names())
        f = tkfont.Font(font=T.F_BODY)
        content = self.text.get("1.0", "end-1c")
        longest = max((f.measure(l) for l in content.splitlines()), default=0)
        width = maxw if has_table else max(int(60 * view.k), min(maxw, longest + int(24 * view.k)))
        self.holder.configure(width=width)
        self.bubble.configure(width=width + 2 * self.bubble.pad)
        self.holder.update_idletasks()
        self.text.update_idletasks()
        try:
            h = self.text.count("1.0", "end", "ypixels")
            h = h[0] if isinstance(h, tuple) else h
        except tk.TclError:
            h = None
        self.holder.configure(height=(h or 20) + int(6 * view.k))
        if not getattr(self, "_again", False):  # once more when Tk has finished wrapping the text
            self._again = True
            view.after(80, lambda: (setattr(self, "_again", False), self.text.winfo_exists() and self._fit_height()))

    def _fit_height(self):
        try:
            h = self.text.count("1.0", "end", "ypixels")
            h = h[0] if isinstance(h, tuple) else h
        except tk.TclError:
            return
        if h:
            self.holder.configure(height=h + int(6 * self.view.k))
            self.view.inner.update_idletasks()
            self.view.canvas.configure(scrollregion=self.view.canvas.bbox("all"))
            if self.view.messages and self.view.messages[-1] is self:
                self.view.canvas.yview_moveto(1.0)
