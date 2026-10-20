"""In-app user guide and the 'what's new' walkthrough shown once after an update.

GUIDE is plain data (also exported to USER_GUIDE.md by `py -m ui.guide`), so the
in-app guide and the written guide never drift apart.
"""
import os
import threading
import tkinter as tk
from tkinter import ttk

from salto import config, keystore
from salto.version import APP_NAME, __version__

from . import theme as T
from .widgets import DetailView

# (topic, [(kind, content)]) - kind: "p" paragraph, "h" sub-heading, "steps" numbered list, "list" bullets
GUIDE = [
    ("Getting started", [
        ("p", "SALTO Buddy reads a GOLD order in SALTO for you and shows everything in one place: stage, devices, "
              "people, every tab, every sub-case and every attachment. It can also answer questions about an order "
              "in plain language (Ask Buddy)."),
        ("steps", ["Connect to the Orange network (VPN if you work remotely).",
                   "Open SALTO Buddy from the Start Menu or the desktop shortcut.",
                   "In Order explorer, type a GOLD order number (for example 10-1764901) and press Enter.",
                   "Wait for the green pill 'Connected to SALTO' and the order to appear (a few minutes for a big "
                   "order: every sub-case is opened)."]),
        ("p", "Firefox works hidden in the background. The first time, the Orange sign-in is done for you; if Orange "
              "ever needs your password or MFA, Firefox appears so you can finish it."),
    ]),
    ("Order explorer", [
        ("p", "The top of the page shows the order, its stage bar (green done, blue current, grey to come) and key "
              "numbers. Below, one tab per job:"),
        ("list", ["Summary: the key facts - status, stage, dates, scope of work, people, sub-cases.",
                  "Devices: the TS tab - switch between 'Scope of work' and 'All devices'.",
                  "People: every participant of the case and its sub-cases.",
                  "Case tabs: SALTO's own tabs of the main case (Overview, Site, Information...).",
                  "Sub-cases: pick EQP, CONF, SG, INV... on the left; its tabs appear as buttons.",
                  "Files: attachments (download what you need) and your screenshots."]),
        ("p", "Tables: click a column title to sort, Ctrl+C or right-click to copy rows into Excel."),
    ]),
    ("Downloads", [
        ("steps", ["Open the order, then the Files tab.",
                   "Select the attachments you need (Ctrl+click or Shift+click for several).",
                   "Click 'Download selected' (or 'Download all').",
                   "Double-click a downloaded row to open it."]),
        ("p", "Files keep their format (PDF, Excel, .msg...). E-mails stored in SALTO are saved as PDF."),
    ]),
    ("Screenshots", [
        ("list", ["Screenshot: saves the whole SALTO page that is open, not only the visible part.",
                  "Capture a part: click any section, table or field in Firefox to save just that part "
                  "(needs 'Show the Firefox window' in Settings). Esc cancels."]),
    ]),
    ("Where files are saved", [
        ("p", "Everything for an order goes to <Save folder>\\<GOLD order> - <STC>\\ with Downloads\\ (one folder "
              "per case) and Screenshots\\. Export to Excel saves <order>.xlsx there. Change the save folder in "
              "Settings (default: Documents\\SALTO Buddy). 'Open folder' opens it."),
    ]),
    ("Ask Buddy (chat)", [
        ("p", "Ask questions about an order in your own words, for example 'What is the site address?', "
              "'Serial numbers of the devices in creation', 'Who is the local delivery manager?'."),
        ("steps", ["Open an order in Order explorer (or just name the order in your question).",
                   "Go to the Ask Buddy tab and type your question, then Enter.",
                   "Buddy reads the order and answers, saying which case and tab the answer comes from."]),
        ("p", "Buddy only uses what SALTO shows. If a field does not exist in SALTO (for example a serial number), "
              "it says so and offers the closest fields. Answers come from Claude (Anthropic): your question and the "
              "order data it needs are sent there."),
        ("h", "The team key (nothing to do)"),
        ("p", "Ask Buddy uses the team's shared Claude key. The first time you ask a question, SALTO Buddy gets it "
              "from the team SharePoint folder by itself (about 30 seconds) with your Orange Microsoft account, then "
              "keeps it encrypted on your PC. If Microsoft ever asks you to sign in, Firefox appears: sign in once "
              "and Buddy carries on."),
        ("p", "Have your own key? Settings > Ask Buddy > paste it, Test, Done. Your own key is used first."),
    ]),
    ("Settings", [
        ("list", ["Save folder for orders.",
                  "Show the Firefox window (normally hidden).",
                  "Open every sub-case / download all attachments automatically / screenshot every tab.",
                  "Check for updates at start.",
                  "Ask Buddy: your own Claude key (optional - the team key is used otherwise)."]),
    ]),
    ("Updates", [
        ("p", "SALTO Buddy checks for a new version every time it starts. When there is one, the header button turns "
              "orange ('Update to x.y.z'): click it, read what's new, then 'Download and install'. The app closes, "
              "installs and opens again by itself. After an update, a short walkthrough shows what changed."),
    ]),
    ("Troubleshooting", [
        ("list", ["Red pill 'Offline - waiting for network': connect the VPN; SALTO Buddy carries on by itself.",
                  "Sign-in does not finish: turn on 'Show the Firefox window' in Settings and complete it there.",
                  "Ask Buddy cannot get the team key: check you are on the Orange network and can open the team "
                  "SharePoint folder; or add your own key in Settings.",
                  "'SALTO Buddy is already open': it is running - look in the taskbar.",
                  "Anything else: click 'Show activity' at the bottom and send a screenshot of it."]),
    ]),
]


def render(d: DetailView, topic):
    blocks = dict(GUIDE)[topic]
    d.clear()
    d.title(topic)
    for kind, content in blocks:
        if kind == "p":
            d.note_body(content)
        elif kind == "h":
            d.section(content)
        elif kind == "steps":
            render_steps(d, content)
        elif kind == "list":
            for s in content:
                d.bullet(s)


def show_guide(root, start="Getting started"):
    w = tk.Toplevel(root)
    w.title(f"{APP_NAME} - Guide")
    w.geometry("900x600")
    w.configure(bg=T.CARD)
    w.transient(root)
    body = ttk.PanedWindow(w, orient="horizontal")
    body.pack(fill="both", expand=True, padx=12, pady=12)
    left = tk.Frame(body, bg=T.ZEBRA, highlightthickness=1, highlightbackground=T.LINE)
    nav = ttk.Treeview(left, show="tree", style="Nav.Treeview", selectmode="browse")
    nav.column("#0", width=200)
    nav.pack(fill="both", expand=True, padx=4, pady=4)
    right = tk.Frame(body, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE)
    d = DetailView(right)
    d.pack(fill="both", expand=True)
    body.add(left, weight=1)
    body.add(right, weight=4)
    for topic, _ in GUIDE:
        nav.insert("", "end", iid=topic, text=topic)
    nav.bind("<<TreeviewSelect>>", lambda e: nav.selection() and render(d, nav.selection()[0]))
    nav.selection_set(start)
    w.bind("<Escape>", lambda e: w.destroy())
    return w


# ---------------------------------------------------------------- what's new walkthrough
def show_whats_new(app):
    """Step-by-step window shown once after installing or updating to this version."""
    root = app.root
    w = tk.Toplevel(root)
    w.title(f"{APP_NAME} {__version__} - What's new")
    w.geometry("760x520")
    w.configure(bg=T.CARD)
    w.transient(root)
    w.grab_set()
    top = tk.Frame(w, bg=T.HEADER, height=48)
    top.pack(fill="x")
    tk.Label(top, text=f"Welcome to {APP_NAME} {__version__}", bg=T.HEADER, fg="white", font=T.F_APP).pack(
        side="left", padx=16, pady=10)
    dots = tk.Label(top, text="", bg=T.HEADER, fg=T.SUBTLE, font=T.F_SMALL)
    dots.pack(side="right", padx=16)
    tk.Frame(w, bg=T.ORANGE, height=3).pack(fill="x")
    foot = tk.Frame(w, bg=T.CARD)  # buttons pinned to the bottom, the page takes the rest
    foot.pack(side="bottom", fill="x", padx=16, pady=12)
    content = tk.Frame(w, bg=T.CARD)
    content.pack(fill="both", expand=True)

    def key_ready():
        return bool(keystore.unprotect(app.cfg.get("claude_key", "")) or config.read_team_key(app.cfg)
                    or keystore.unprotect(app.cfg.get("team_key_cache", "")))

    def page_new(d):
        d.title("What's new")
        for s in ["Ask Buddy: a chat that answers questions about an order in plain language.",
                  "No setup: Ask Buddy gets the team's key from SharePoint by itself.",
                  "A built-in guide: the Guide button in the header, at any time."]:
            d.bullet(s)
        d.note_body("The next steps take one minute and get you ready.")

    def page_order(d):
        d.title("Step 1 - Open an order")
        render_steps(d, ["Go to the Order explorer tab.", "Type a GOLD order number and press Enter.",
                         "Wait for the order to load (Firefox works hidden in the background)."])

    def page_key(d):
        d.title("Step 2 - Ask Buddy is ready for you")
        if key_ready():
            d.section("Ready")
            d.note_body("Ask Buddy already has its key. Nothing to do here.")
            return
        d.section("Nothing to set up")
        d.note_body("The first time you ask Buddy a question, SALTO Buddy gets the team's key from SharePoint by "
                    "itself (about 30 seconds), using your Orange Microsoft account. If Microsoft asks you to sign "
                    "in, Firefox appears: sign in once and Buddy carries on.")

    def page_ask(d):
        d.title("Step 3 - Ask Buddy")
        render_steps(d, ["With an order open, go to the Ask Buddy tab.",
                         "Type a question, e.g. 'What is the site address?' or 'Devices in creation', then Enter.",
                         "Buddy answers from SALTO and tells you which tab the answer comes from."])
        d.note_body("Buddy never invents data: if SALTO does not have it, Buddy says so.")

    def page_done(d):
        d.title("You're all set")
        d.note_body("Open the Guide (header, top right) any time for the full user guide: downloads, screenshots, "
                    "where files are saved, troubleshooting.")

    pages = [page_new, page_order, page_key, page_ask, page_done]
    state = {"i": 0}
    detail = DetailView(content)
    detail.pack(fill="both", expand=True, padx=8, pady=8)
    back = ttk.Button(foot, text="Back")
    nxt = ttk.Button(foot, text="Next", style="Accent.TButton")
    check = ttk.Button(foot, text="Check again")
    settings = ttk.Button(foot, text="Open Settings", command=lambda: (w.destroy(), app.show_settings()))
    guide = ttk.Button(foot, text="Open the guide", command=lambda: (w.destroy(), show_guide(root)))

    def draw():
        i = state["i"]
        detail.clear()
        pages[i](detail)
        dots.configure(text=f"{i + 1} / {len(pages)}")
        for b in (back, nxt, check, settings, guide):
            b.pack_forget()
        nxt.configure(text="Finish" if i == len(pages) - 1 else "Next")
        nxt.pack(side="right")
        if i:
            back.pack(side="right", padx=6)
        if pages[i] is page_done:
            guide.pack(side="left")

    def go(step):
        if state["i"] + step >= len(pages):
            w.destroy()
            return
        state["i"] = max(0, state["i"] + step)
        draw()

    def check_again():
        check.configure(state="disabled", text="Looking...")

        def work():
            folder = config.find_team_key()
            def done():
                if folder:
                    app.cfg["team_key_dir"] = config.portable(folder)
                    config.save(app.cfg)
                    for feat in app.features:
                        getattr(feat, "key_changed", lambda: None)()
                check.configure(state="normal", text="Check again")
                draw()
            app.ui(done)
        threading.Thread(target=work, daemon=True).start()

    back.configure(command=lambda: go(-1))
    nxt.configure(command=lambda: go(1))
    check.configure(command=check_again)
    draw()
    return w


def render_steps(d, steps):
    for i, s in enumerate(steps, 1):
        d.step(i, s)


# ---------------------------------------------------------------- USER_GUIDE.md export
def to_markdown():
    out = [f"# {APP_NAME} - User guide", ""]
    for topic, blocks in GUIDE:
        out += [f"## {topic}", ""]
        for kind, content in blocks:
            if kind == "p":
                out += [content, ""]
            elif kind == "h":
                out += [f"### {content}", ""]
            elif kind == "steps":
                out += [f"{i}. {s}" for i, s in enumerate(content, 1)] + [""]
            elif kind == "list":
                out += [f"- {s}" for s in content] + [""]
    return "\n".join(out)


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "USER_GUIDE.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_markdown())
    print(path)
