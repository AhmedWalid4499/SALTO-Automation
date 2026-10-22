"""Home: a dashboard of the orders read on this PC (key figures, charts, recent orders)."""
import time
import tkinter as tk

from salto import history
from ui import theme as T
from ui.widgets import BarChart, GradientTile, RoundButton, RoundCard, RoundEntry, Table

from .base import Feature

# tile caption -> gradient (left, right)
TILES = [("Orders", ("#1D5FD1", "#3B8BFF")), ("In progress", ("#0B8F8C", "#1EC2B0")),
         ("Completed", ("#2F7D4F", "#45B26B")), ("New devices", ("#D9416E", "#F2719A")),
         ("Serial numbers", ("#6D36D9", "#9C6BFF")), ("Open sub-cases", ("#E06A00", "#FF9433"))]
BARS = ["#3B8BFF", "#1EC2B0", "#F2719A", "#9C6BFF", "#FF9433", "#45B26B", "#2E3B3B"]
COLS = ["Order", "STC", "Customer", "Site", "Stage", "Status", "Devices in creation", "Serial numbers",
        "Open sub-cases", "Read"]


class Home(Feature):
    title = "Home"
    icon = ""
    subtitle = "Your orders at a glance"

    def build(self, parent):
        self.parent = parent
        bar = tk.Frame(parent, bg=T.CARD)
        bar.pack(fill="x")
        self.order = tk.StringVar()
        e = RoundEntry(bar, textvariable=self.order, width=220)
        e.pack(side="left")
        e.bind("<Return>", lambda _e: self.open_order())
        RoundButton(bar, "Open order", self.open_order).pack(side="left", padx=(10, 0))
        self.when = tk.Label(bar, text="", bg=T.CARD, fg=T.MUTED, font=T.F_SMALL)
        self.when.pack(side="right")

        tiles = tk.Frame(parent, bg=T.CARD)
        tiles.pack(fill="x", pady=(16, 0))
        self.tiles = {}
        for i, (name, colors) in enumerate(TILES):
            t = GradientTile(tiles, name, colors)
            t.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            tiles.grid_columnconfigure(i, weight=1, uniform="tiles")
            self.tiles[name] = t

        charts = tk.Frame(parent, bg=T.CARD)
        charts.pack(fill="x", pady=(16, 0))
        self.charts = {}
        for i, name in enumerate(["Orders by stage", "New devices by type"]):
            card = RoundCard(charts, fill=T.STATUS_CARD, radius=18, pad=14, fit=True, shadow=False)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 14, 0))
            charts.grid_columnconfigure(i, weight=1, uniform="charts")
            tk.Label(card.inner, text=name, bg=T.STATUS_CARD, fg=T.INK, font=T.F_SECTION, anchor="w").pack(fill="x")
            chart = BarChart(card.inner, height=130)
            chart.pack(fill="x", pady=(6, 0))
            self.charts[name] = chart

        head = tk.Frame(parent, bg=T.CARD)
        head.pack(fill="x", pady=(16, 6))
        tk.Label(head, text="Recent orders", bg=T.CARD, fg=T.INK, font=T.F_SECTION).pack(side="left")
        tk.Label(head, text="Double-click an order to open it", bg=T.CARD, fg=T.SUBTLE,
                 font=T.F_SMALL).pack(side="left", padx=10)
        self.table_box = tk.Frame(parent, bg=T.CARD)
        self.table_box.pack(fill="both", expand=True)
        self.seeded = False
        parent.bind("<Map>", lambda e: self.refresh())

    def order_updated(self, rep):
        self.refresh()

    def open_order(self, ref=None):
        ref = (ref or self.order.get()).strip()
        ex = self.app.explorer
        if not ref or not ex:
            return
        self.app.select(self.app.features.index(ex))
        ex.order.set(ref)
        ex.go()

    def refresh(self):
        if not self.seeded:  # first time: orders read before this version (saved copies)
            self.seeded = True
            try:
                history.seed_from_cache()
            except Exception:
                pass
        rows = history.orders()
        done = [r for r in rows if (r.get("stage") or "").lower() == "completed" or
                (r.get("status") or "").lower().startswith("resolved")]
        found = sum(r.get("serials_found", 0) for r in rows)
        total = sum(r.get("serials_total", 0) for r in rows)
        self.tiles["Orders"].set(str(len(rows)), f"{len({r.get('customer') for r in rows if r.get('customer')})}"
                                 " customer(s)")
        self.tiles["In progress"].set(str(len(rows) - len(done)), "open orders")
        self.tiles["Completed"].set(str(len(done)), "resolved")
        self.tiles["New devices"].set(str(sum(r.get("creation", 0) for r in rows)),
                                      f"{sum(r.get('cessation', 0) for r in rows)} ceased")
        self.tiles["Serial numbers"].set(f"{found}/{total}" if total else "0",
                                         f"{round(100 * found / total)} % found" if total else "from FLIP")
        self.tiles["Open sub-cases"].set(str(sum(r.get("open_subcases", 0) for r in rows)),
                                         f"of {sum(r.get('subcases', 0) for r in rows)}")
        stages = {}
        for r in rows:
            s = r.get("stage") or r.get("status") or "Unknown"
            stages[s] = stages.get(s, 0) + 1
        self.charts["Orders by stage"].set(
            [(s, n, "#45B26B" if s == "Completed" else BARS[i % len(BARS)])
             for i, (s, n) in enumerate(sorted(stages.items(), key=lambda kv: -kv[1])[:7])])
        types = {}
        for r in rows:
            for t, n in (r.get("types") or {}).items():
                types[t] = types.get(t, 0) + n
        self.charts["New devices by type"].set(
            [(t, n, BARS[i % len(BARS)]) for i, (t, n) in enumerate(sorted(types.items(), key=lambda kv: -kv[1])[:7])])
        if rows:
            self.when.configure(text="Last read " + time.strftime("%d %b %Y %H:%M",
                                                                         time.localtime(rows[0].get("read", 0))))
        for w in self.table_box.winfo_children():
            w.destroy()
        table_rows = [{"Order": r["order"], "STC": r.get("stc", ""), "Customer": r.get("customer", ""),
                       "Site": ", ".join(x for x in (r.get("city"), r.get("country")) if x),
                       "Stage": r.get("stage", ""), "Status": r.get("status", ""),
                       "Devices in creation": r.get("creation", 0),
                       "Serial numbers": f"{r.get('serials_found', 0)} / {r.get('serials_total', 0)}",
                       "Open sub-cases": f"{r.get('open_subcases', 0)} / {r.get('subcases', 0)}",
                       "Read": time.strftime("%d %b %H:%M", time.localtime(r.get("read", 0)))} for r in rows]
        if not table_rows:
            tk.Label(self.table_box, text="No order read yet. Type a GOLD order number above to start.", bg=T.CARD,
                     fg=T.MUTED, font=T.F_BODY).pack(anchor="w", pady=10)
            return
        t = Table(self.table_box, COLS, table_rows, height=6)
        t.pack(fill="both", expand=True)
        t.tv.bind("<Double-1>", lambda e: self._open_row(t), add="+")

    def _open_row(self, t):
        sel = t.tv.selection()
        if sel:
            self.open_order(str(t.tv.item(sel[0], "values")[0]))
