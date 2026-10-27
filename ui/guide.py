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
from .dialogs import shell
from .widgets import DetailView

# (topic, [(kind, content)]) - kind: "p" paragraph, "h" sub-heading, "steps" numbered list, "list" bullets
GUIDE = [
    ("Getting started", [
        ("p", "SALTO Buddy reads a GOLD order in SALTO for you and shows everything in one place: stage, devices, "
              "people, every tab, every sub-case and every attachment. It can also answer questions about an order "
              "in plain language (The Friendly SALTO Bot)."),
        ("steps", ["Connect to the Orange network (VPN if you work remotely).",
                   "Open SALTO Buddy from the Start Menu or the desktop shortcut.",
                   "In Order explorer, type a GOLD order number (for example 10-1764901) and press Enter.",
                   "The order appears in about 20 seconds. Sub-cases and FLIP serial numbers fill in by themselves "
                   "afterwards (about a minute) - you can already work with what is shown."]),
        ("p", "SALTO Buddy signs in to SALTO in the background as soon as it opens. An order you have read before "
              "appears at once (saved copy) and is refreshed behind it."),
        ("p", "Firefox works hidden in the background. When Orange asks you to sign in, SALTO Buddy asks you in its "
              "own window how to sign in (Orange PKI, Orange GroupIdentity or Microsoft Professional Account) and "
              "does the rest:"),
        ("list", ["Orange PKI: Firefox's own password window appears for a moment - type your PKI PIN there, as "
                  "usual. Firefox then goes back out of sight.",
                  "Orange GroupIdentity: type your account and password in the SALTO Buddy window.",
                  "Microsoft Professional Account: type what Microsoft asks in the SALTO Buddy window; if it asks "
                  "for a phone approval, SALTO Buddy shows the number to tap in Authenticator."]),
        ("p", "Tick 'Remember my choice' to skip the question next time (change it in Settings > General). Your "
              "password and PIN are never saved by SALTO Buddy."),
    ]),
    ("Home dashboard", [
        ("p", "Home shows the orders read on this PC at a glance: how many, in progress or completed, new devices, "
              "serial numbers found and open sub-cases, two charts (orders by stage, new devices by type) and the "
              "recent orders."),
        ("list", ["Type an order number at the top and press Enter to open it.",
                  "Double-click a recent order to open it again (instantly, from the saved copy).",
                  "It fills in by itself every time an order has been read."]),
    ]),
    ("Notifications", [
        ("p", "When a task is done - an order fully read (sub-cases and serial numbers included), a SALTO Bot "
              "answer, downloads - a SALTO Buddy card appears at the bottom right of the screen and the taskbar "
              "button flashes if you are in another window. Click Open to go straight to it."),
        ("list", ["Settings > General: 'Notify me when a task is done' turns them on or off.",
                  "'Play a sound with notifications' adds a short sound."]),
    ]),
    ("Order explorer", [
        ("p", "The top of the page shows the order, its stage bar (green done, blue current, grey to come) and key "
              "numbers. Below, one tab per job:"),
        ("list", ["Summary: the key facts - status, stage, dates, scope of work, people, sub-cases.",
                  "Devices: the TS tab - switch between 'Scope of work' and 'All devices'.",
                  "FLIP serial numbers: the serial number of every EQP device, read from FLIP.",
                  "People: every participant of the case and its sub-cases, with their email, job title, manager and "
                  "manager's email from the Org Chart ('Copy emails' copies them all).",
                  "Case tabs: SALTO's own tabs of the main case (Overview, Site, Information...).",
                  "Sub-cases: pick EQP, CONF, SG, INV... on the left; its tabs appear as buttons.",
                  "Files: attachments (download what you need) and your screenshots."]),
        ("p", "Tables: click a column title to sort, Ctrl+C or right-click to copy rows into Excel."),
    ]),
    ("FLIP serial numbers", [
        ("p", "For every EQP of the order, SALTO Buddy follows the same path you would: EQP > Information > rocket > "
              "Intervention Id > FLIP > Work Flow Action Items > Open Part Request > Export. It then matches each SALTO "
              "device to its FLIP part with the same OBS name and the device model, so you get the serial number of "
              "the device itself (not its power supplies or SFPs)."),
        ("list", ["FLIP serial numbers tab: one row per device with its serial number, and below it every FLIP part.",
                  "Check column: OK when exactly one part matched; otherwise it tells you what to look at.",
                  "The FLIP export (Excel) is saved in the order folder, Downloads\\FLIP.",
                  "The Friendly SALTO Bot can answer it too: 'serial numbers of the devices in creation'.",
                  "Nothing is ever changed in FLIP: only 'Open Part Request' and 'Export' are used."]),
    ]),
    ("HOTO preparation", [
        ("p", "The HOTO sheet of a LAN project, filled from the order open in Order explorer: one row per device in "
              "creation (devices being ceased or modified are left out)."),
        ("steps", ["Open the order in Order explorer.",
                   "Go to the HOTO preparation tab: the rows are already filled. Serial numbers fill in as soon as FLIP "
                   "has been read.",
                   "Click 'Save HOTO Excel' (saved in the order folder by default), or 'Copy all rows' and paste them "
                   "into your HOTO document."]),
        ("p", "The Excel has two sheets. 'HOTO': a ready-to-share template - title, an order block (GOLD ref, "
              "customer, site, go-live, project manager, STC case, date), the devices grouped by type with counts, "
              "yellow columns to fill in by hand (admin / customer IP), amber serial numbers to check, and a total. "
              "'Plain list': the same rows without layout, to paste anywhere."),
        ("list", ["Go Live Date: the case's target delivery date. Change it in Excel if the go-live is planned "
                  "differently.",
                  "Project Manager: the case's Project Manager participant, empty when there is none.",
                  "City, Country, Site address, Site ID and the local contact come from the Site tab (Primary Contact).",
                  "Device Name is the customer device name; Switch number comes from it (skf-sw-itvil-01_02 -> 01_02). "
                  "In a stack, member 01 is the Master; the others show their master's name.",
                  "Device Type: SW, AP, WLC, RTR or FW, from the device type.",
                  "Device SN#: from FLIP. A highlighted cell means it is missing, or FLIP lists several serial "
                  "numbers for the device: check it in the FLIP serial numbers tab.",
                  "Admin and customer IP addresses are not in SALTO: fill them in Excel."]),
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
    ("Org Chart (emails and managers)", [
        ("p", "SALTO Buddy reads the Orange Business Org Chart for you: a person's email, job title, department, "
              "phone and who they report to, with every manager's email."),
        ("list", ["People tab of an order: filled by itself once the order is read (a few seconds). Customer contacts "
                  "are not in the Org Chart: their emails are in the Site and Commercial Content tabs.",
                  "Org Chart tab: type a last name, a first name or an email (partial names work) and press Enter. "
                  "Select a person to see their management chain: manager, 2nd-level manager and so on, with emails.",
                  "The Friendly SALTO Bot: 'What is the email of Ahmed Khairy's manager?' works too.",
                  "Results are kept for a week; 'Refresh' in the People tab reads them again."]),
    ]),
    ("The Friendly SALTO Bot (chat)", [
        ("p", "Ask questions about an order in your own words, for example 'What is the site address?', "
              "'Serial numbers of the devices in creation', 'Who is the local delivery manager?'."),
        ("steps", ["Open an order in Order explorer (or just name the order in your question).",
                   "Click SALTO Bot in the menu, type your question and press Enter.",
                   "The bot reads the order and answers as it writes, saying which case and tab the answer comes from."]),
        ("h", "Documents"),
        ("p", "Click the paperclip next to the message box to attach Word (.docx), PDF or text files - a customer "
              "request, a HOTO or handover form, an email saved as text. Add a question, or just press Send: the bot "
              "reads the document and does what it asks when it can."),
        ("list", ["It looks up the orders the document names (and opens them in SALTO if needed), checks the "
                  "document against SALTO and FLIP (devices, models, serial numbers, sites, contacts) and tells you "
                  "what matches and what differs.",
                  "It finds people in the Org Chart, prepares the HOTO Excel sheet or exports an order to Excel when "
                  "the document asks for it. Files it creates appear as 'Open ...' buttons under its answer.",
                  "It never changes anything in SALTO and never sends emails: if the document asks for that, it "
                  "tells you what to do.",
                  "Old Word files (.doc): open them in Word and save them as .docx first. Attached documents are "
                  "sent to Claude (Anthropic) with your question."]),
        ("p", "Chats are saved on this PC and listed on the left, grouped by order number: click one to read it "
              "again or to continue it (Buddy remembers the conversation). '+ New chat' starts a fresh one; "
              "right-click a chat to delete it."),
        ("p", "Your chats stay confidential: they are kept only on this PC (never in OneDrive or any cloud), "
              "encrypted so that only you, signed in to Windows on this PC, can open them. To answer, the "
              "question and the SALTO details it needs are sent to Claude (Anthropic); SALTO Buddy stores no chat "
              "there."),
        ("p", "Answers start with the short answer, then the details: bullets for a few facts, a table for lists "
              "(devices, serial numbers, sub-cases...). Click a table's column title to sort it. 'Copy answer' under "
              "each answer copies it as clean text: tables paste as columns in Excel and as text in Outlook."),
        ("p", "The bot only uses what SALTO shows. If a field does not exist in SALTO (for example a serial number), "
              "it says so and offers the closest fields. Answers come from Claude (Anthropic): your question and the "
              "order data it needs are sent there."),
        ("h", "The team key (nothing to do)"),
        ("p", "The bot uses the team's shared Claude key. The first time you ask a question, SALTO Buddy gets it "
              "from the team SharePoint folder by itself (about 30 seconds) with your Orange Microsoft account, then "
              "keeps it encrypted on your PC. If Microsoft ever asks you to sign in, Firefox appears: sign in once "
              "and Buddy carries on."),
        ("p", "Have your own key? Settings > SALTO Bot > paste it, Test, Done. Your own key is used first."),
    ]),
    ("Settings", [
        ("list", ["Save folder for orders.",
                  "Show the Firefox window (normally hidden).",
                  "Sign in to SALTO with: Ask me, or always the same way (Orange PKI, GroupIdentity, Microsoft).",
                  "Open every sub-case / download all attachments automatically / screenshot every tab.",
                  "Read the full audit history (slower): by default only the latest audit page is read.",
                  "Check for updates at start.",
                  "SALTO Bot: your own Claude key (optional - the team key is used otherwise)."]),
    ]),
    ("Updates", [
        ("p", "SALTO Buddy checks for a new version every time it starts. When there is one, the header button turns "
              "orange ('Update to x.y.z'): click it, read what's new, then 'Download and install'. The app closes, "
              "installs and opens again by itself. After an update, a short walkthrough shows what changed."),
    ]),
    ("Troubleshooting", [
        ("list", ["Red pill 'Offline - waiting for network': connect the VPN; SALTO Buddy carries on by itself.",
                  "Sign-in does not finish: click 'Show Firefox instead' in the sign-in window (or turn on 'Show "
                  "the Firefox window' in Settings) and complete it there.",
                  "No PKI password window: make sure your Orange smart card or PKI certificate is ready, then open "
                  "the order again.",
                  "The SALTO Bot cannot get the team key: check you are on the Orange network and can open the team "
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
    w, inner, _foot = shell(root, "Guide", "How to use SALTO Buddy", width=960, height=640, modal=False,
                            resizable=True)
    body = ttk.PanedWindow(inner, orient="horizontal")
    body.pack(fill="both", expand=True)
    left = tk.Frame(body, bg=T.ZEBRA)
    nav = ttk.Treeview(left, show="tree", style="Nav.Treeview", selectmode="browse")
    nav.column("#0", width=200)
    nav.pack(fill="both", expand=True, padx=4, pady=4)
    right = tk.Frame(body, bg=T.CARD)
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
    w, content, foot = shell(root, f"Welcome to {APP_NAME} {__version__}", "What's new, and one minute to get "
                             "you ready", width=780, height=560)
    dots = tk.Label(foot, text="", bg=T.CANVAS, fg=T.MUTED, font=T.F_SMALL)
    dots.pack(side="left")

    def key_ready():
        return bool(keystore.unprotect(app.cfg.get("claude_key", "")) or config.read_team_key(app.cfg)
                    or keystore.unprotect(app.cfg.get("team_key_cache", "")))

    def page_new(d):
        d.title("What's new")
        for s in ["Confidential chats: saved chats are encrypted and kept only on this PC - never in a cloud.",
                  "Sign in from SALTO Buddy: when Orange asks you to sign in, choose Orange PKI, GroupIdentity or "
                  "Microsoft in a SALTO Buddy window. With PKI, just type your PIN in the password window - no "
                  "Firefox page to deal with.",
                  "The Friendly SALTO Bot reads documents: attach a Word, PDF or text file and it understands "
                  "it and acts on it - looks up orders, checks them, prepares the HOTO or an Excel export.",
                  "Meet The Friendly SALTO Bot: a real chat with our robot - your messages and its answers in "
                  "bubbles, and answers written live as it thinks, in a friendly tone.",
                  "New Home dashboard: your orders at a glance - key figures, charts and recent orders.",
                  "The Friendly SALTO Bot keeps your chats, grouped by order number: reopen one for quick info or continue it.",
                  "Notifications when a task is done (order read, answer ready, downloads), in SALTO Buddy style.",
                  "HOTO Excel in a template layout: order block, devices grouped by type, totals, fields to fill.",
                  "Rounder design, and every window and message now in SALTO Buddy style.",
                  "A new look: a new logo, a menu on the left, rounded cards and clearer key figures. Everything is "
                  "where it was, just easier to read.",
                  "Nothing is left behind: every sub-case and every page of every table is read, plus the Pulse "
                  "messages and any information on a tab that is not a field or a table.",
                  "New: Org Chart - emails, job titles and managers (with their emails) of everyone on an order, and "
                  "an Org Chart tab to find anyone at Orange Business with their management chain.",
                  "Chat answers are clearer: the answer first, then short sections, tables for devices and serial "
                  "numbers, and where it comes from. 'Copy answer' pastes cleanly into Outlook or Excel.",
                  "New: HOTO preparation - the HOTO sheet of a LAN order, filled for you (devices in creation), "
                  "ready to save as Excel or paste into your HOTO document.",
                  "FLIP: every part of an intervention is read now (large orders used to miss some serial numbers).",
                  "Much faster: the order appears in about 20 seconds; sub-cases and serial numbers fill in after.",
                  "Orders you read before open instantly, and SALTO is signed in as soon as the app starts.",
                  "FLIP serial numbers: for every EQP, SALTO Buddy goes to FLIP and gets each device's serial number.",
                  "A chat that answers questions about an order in plain language (serial numbers too).",
                  "No setup: the chat gets the team's key from SharePoint by itself.",
                  "A built-in guide: the Guide button in the header, at any time."]:
            d.bullet(s)
        d.note_body("The next steps take one minute and get you ready.")

    def page_order(d):
        d.title("Step 1 - Open an order")
        render_steps(d, ["Go to the Order explorer tab.", "Type a GOLD order number and press Enter.",
                         "Wait for the order to load (Firefox works hidden in the background)."])

    def page_key(d):
        d.title("Step 2 - The Friendly SALTO Bot is ready for you")
        if key_ready():
            d.section("Ready")
            d.note_body("The bot already has its key. Nothing to do here.")
            return
        d.section("Nothing to set up")
        d.note_body("The first time you ask Buddy a question, SALTO Buddy gets the team's key from SharePoint by "
                    "itself (about 30 seconds), using your Orange Microsoft account. If Microsoft asks you to sign "
                    "in, Firefox appears: sign in once and Buddy carries on.")

    def page_ask(d):
        d.title("Step 3 - The Friendly SALTO Bot")
        render_steps(d, ["With an order open, click SALTO Bot in the menu.",
                         "Type a question, e.g. 'What is the site address?' or 'Devices in creation', then Enter.",
                         "The bot answers from SALTO, live as it writes, and tells you where the answer comes from."])
        d.note_body("The bot never invents data: if SALTO does not have it, it says so.")

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
