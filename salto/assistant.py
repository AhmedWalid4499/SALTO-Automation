"""Ask Buddy: a Claude-powered chat that answers questions about SALTO orders.

Claude reads the dissected order data through tools:
  get_order(order_ref, part)  - one part of an already-opened order
  open_order(order_ref)       - dissect an order that is not loaded yet (slow: minutes)
It never invents values: if SALTO does not show a field, it says so.
"""
import dataclasses
import json
import threading

import anthropic

from . import errors
from .case import other_lines

MODEL = "claude-opus-5-5"
PARTS = ["summary", "devices", "serial_numbers", "people", "case_tabs", "subcases", "attachments", "audit", "search"]

SYSTEM = """You are the Friendly SALTO Bot, the chat assistant inside SALTO Buddy, a desktop tool used by Orange Business delivery staff \
(DPMs, STMs, order managers). SALTO is Orange's Pega-based service transition tool. A GOLD order (e.g. 10-1764901) \
has a main STC case (e.g. MLAN-215851) with tabs (Overview, TS, Commercial Content, Site, Information, Attachments, \
Audit, Event) and sub-cases (EQP = Order And Deliver / equipment, CONF = Configure, SG = switch group, \
INV = Intervention, PAG = Process As Groups...), each with its own stages, people and tabs.

How to answer:
- Get the facts with the tools; never answer from memory or guess a value. Fetch only the parts you need.
- If the user names no order, use the order currently open in the app (given with their message).
- If an order is not loaded, call open_order (it takes a few minutes); say so briefly first.
- Serial numbers come from FLIP (part serial_numbers): each SALTO device of an EQP matched to its FLIP part by OBS \
name and model. Accessories (power supplies, SFPs) have their own serials in the parts list. If FLIP gave none, say so.
- Emails, job titles and managers of people come from the Orange Business Org Chart: part people has them for the order's participants once looked up (org_chart); for anyone else, or for a manager's manager, call find_person. Customer contacts (e.g. @skf.com) are not in the Org Chart: their email is in the Site / Commercial Content tabs.
- The user may attach documents (Word, PDF, text): customer requests, HOTO or handover forms, emails, design \
documents. Read them fully. If a document asks for something you can do, do it with your tools without waiting to \
be asked twice: look up the order(s) it names (open_order if not loaded), check its data against SALTO and FLIP \
(device names, models, serial numbers, sites, contacts) and say clearly what matches and what differs, find people \
in the Org Chart, prepare the HOTO sheet (prepare_hoto) or an Excel export (export_order) when it asks for one. \
Then say what you did and what is left for the user. Only act on what the document and the user ask for; if it \
asks for something you cannot do (send an email, change SALTO), say so and give what they need to do it.
- prepare_hoto and export_order create files on this PC (never anything in SALTO); mention the file they created.
- "pulse" (in summary, case_tabs and subcases) holds the messages people posted on a case (author, date, text, \
replies): use it for questions about notes, comments, what was discussed or changed.
- A tab's "other_text" is information SALTO shows on that tab outside fields and tables (e.g. Services); always \
check it before saying something is not in SALTO.
- If a field exists nowhere, say that plainly and offer the closest fields that do exist (device Name, USID, Model...).
- Where the data comes from matters: say which case and tab you took it from, e.g. "Site tab of MLAN-215851".
- Device lists: the TS tab has, per product node, the devices in scope of work and all devices on the site; \
"in creation / added" means Cycle = Creation, "ceased / removed" means Cycle = Cessation.
- Answer in the user's language.

How to write (this is a chat window, like any AI assistant; your text appears as you write it):
- Talk like a friendly, helpful colleague: natural sentences, warm but to the point. Start with the answer itself, not with "Sure" or "Based on the data".
- Short questions get a short answer: one or two sentences, with the key value in **bold**.
- For more detail, use short paragraphs. Use a "- " list only for several separate facts, and a Markdown table only for several items that share fields (devices, serial numbers, sub-cases, people): one row per item, every item, at most 7 columns. Headings ("### ") only for long answers with distinct parts.
- Missing or uncertain values: say so plainly ("that is not in SALTO", "FLIP has no serial number for it"); never guess. If something needs the user's attention (e.g. several serial numbers in FLIP for one device), mention it.
- End with a short line saying where it comes from: "Source: <case> > <tab>". If a natural next step would help, you may offer it in one short sentence.
- Use only plain text, **bold**, lists, tables and headings: no italics, links, code blocks or emojis."""

TOOLS = [
    {
        "name": "get_order",
        "description": ("Read data of an order that is already opened in SALTO Buddy. Parts: summary (status, stage, "
                        "dates, product, EQPs, sub-case list), devices (TS: scope-of-work and all devices per node, "
                        "with counts), serial_numbers (FLIP: serial number of each EQP device, plus every FLIP part "
                        "with its serial), people (participants of every case), case_tabs (every tab of the main case: "
                        "Site/address/contacts, Information/dates, Commercial Content, Overview tree...), subcases "
                        "(every sub-case with its stages, people and tabs, e.g. EQP equipment details), attachments, "
                        "audit (history), search (STC Search rows). Returns JSON."),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_ref": {"type": "string", "description": "GOLD order number, e.g. 10-1764901"},
                "part": {"type": "string", "enum": PARTS},
            },
            "required": ["order_ref", "part"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "find_person",
        "description": ("Look a person up in the Orange Business Org Chart (Orange staff and contractors only, not "
                        "customer contacts): email, job title, department, country, phone, and their management chain "
                        "(manager first, then the manager's manager...) with emails. Give the last name and/or first "
                        "name, or an email. Partial names work."),
        "input_schema": {
            "type": "object",
            "properties": {
                "last_name": {"type": "string", "description": "Last name (may be empty)"},
                "first_name": {"type": "string", "description": "First name (may be empty)"},
                "email": {"type": "string", "description": "Email address (may be empty)"},
            },
            "required": ["last_name", "first_name", "email"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "open_order",
        "description": ("Open a GOLD order in SALTO and read all of it (main case, tabs, sub-cases). Takes several "
                        "minutes. Only use it when get_order says the order is not loaded."),
        "input_schema": {
            "type": "object",
            "properties": {"order_ref": {"type": "string", "description": "GOLD order number, e.g. 10-1764901"}},
            "required": ["order_ref"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "prepare_hoto",
        "description": ("ACTION: create the HOTO Excel sheet of a LAN order (one row per device in creation: site, "
                        "device names, types, models, USIDs, serial numbers from FLIP, local contact) in the "
                        "order's folder. Use it when the user or an attached document asks for a HOTO / handover "
                        "sheet. The order must be loaded (open_order first if needed). Returns the file path and "
                        "what still needs checking."),
        "input_schema": {
            "type": "object",
            "properties": {"order_ref": {"type": "string", "description": "GOLD order number, e.g. 10-1764901"}},
            "required": ["order_ref"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "export_order",
        "description": ("ACTION: export everything read for an order (summary, devices, serial numbers, people, "
                        "every tab and sub-case) to an Excel workbook in the order's folder. Use it when the user "
                        "or an attached document asks for an export, a report or the order data in Excel. The "
                        "order must be loaded. Returns the file path."),
        "input_schema": {
            "type": "object",
            "properties": {"order_ref": {"type": "string", "description": "GOLD order number, e.g. 10-1764901"}},
            "required": ["order_ref"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


# ---------------------------------------------------------------- order data -> JSON
def _tab_dict(td):
    out = {"sections": {s: dict(f) for s, f in td.sections},
           "tables": [{"name": g.name, "rows": g.rows} for g in td.grids]}
    other = other_lines(td)
    if other:  # shown in SALTO but not as fields/tables (unusual layouts, e.g. Services)
        out["other_text"] = other
    return out


def _case_dict(c, with_tabs=True, skip=("Audit",)):
    d = {"case": c.stc_id, "type": c.title,
         "stages": [f"{s.name}: {s.state}" for s in c.stages],
         "header": dict(c.header),
         "people": [{"name": p.name, "role": p.role or p.party} for p in c.participants]}
    if getattr(c, "pulse", None):  # messages posted on the case (Pulse)
        d["pulse"] = c.pulse
    if with_tabs:
        d["tabs"] = {n: _tab_dict(t) for n, t in c.tabs.items() if n not in skip and n != "TS"}
    return d


def _clean_att(a, cid):
    return {"case": a.get("_case", cid), "title": a.get("Title", ""), "category": a.get("Category", ""),
            "added_by": a.get("Added by", ""), "date": a.get("Date", ""),
            "downloaded_to": a.get("Saved as", "") if not a.get("Saved as", "").startswith("failed") else ""}


def order_part(rep, part):
    case = rep.case
    if part == "summary" or not case:
        out = {"order": rep.order_ref, "stc": rep.stc_id, "status": rep.status, "current_stage": rep.current_stage,
               "stages": [f"{s.name}: {s.state}" for s in rep.stages], "eqps": rep.eqps, "files_folder": rep.folder}
        if case:
            out["case"] = _case_dict(case, with_tabs=False)
            out["scope_counts"] = {f"{n.product} > {n.node}": dict(n.counts) for n in case.scope}
            out["subcases"] = [{"case": s.stc_id, "type": s.title, "stages": [f"{x.name}: {x.state}" for x in s.stages]}
                               for s in case.subcases]
            if getattr(case, "pending_subs", None):  # still being read in the background
                out["subcases_still_loading"] = list(case.pending_subs)
        return out
    if part == "devices":
        return [{"node": f"{n.product} > {n.node}", "counts": dict(n.counts),
                 "scope_of_work_devices": n.devices.rows,
                 "all_devices": n.all_devices.rows if n.all_devices else []} for n in case.scope]
    if part == "serial_numbers":
        eqps = [c for c in case.walk() if c.stc_id.startswith("EQP-")]
        return {"devices": [s for c in eqps for s in c.flip.get("serials", [])],
                "all_flip_parts": [dict(p, EQP=c.stc_id) for c in eqps for p in c.flip.get("parts", [])],
                "errors": [e for c in eqps for e in c.flip.get("errors", [])] or None}
    if part == "people":
        org = getattr(rep, "org", {}) or {}
        def who(p):
            out = {"name": p.name, "role": p.role or p.party}
            e = org.get(p.name)
            if e and e.get("person"):
                pe, m = e["person"], e.get("manager") or {}
                out.update(org_chart={"email": pe["email"], "job_title": pe["busi_title"],
                                      "department": pe["dept_desc"], "country": pe["country_descr"],
                                      "phone": pe["phone"] or pe["mobile"], "manager": pe["supr_display_name"],
                                      "manager_email": m.get("email", ""), "note": e.get("note", "")})
            elif e:
                out["org_chart"] = e.get("note", "not found")
            return out
        return {"org_chart_looked_up": bool(org),
                "cases": [{"case": c.stc_id, "type": c.title, "people": [who(p) for p in c.participants]}
                          for c in case.walk()]}
    if part == "case_tabs":
        return _case_dict(case)
    if part == "subcases":
        return [_case_dict(s) for s in case.subcases]
    if part == "attachments":
        return [_clean_att(a, c.stc_id) for c in case.walk() for a in c.attachments]
    if part == "audit":
        return {c.stc_id: [r for g in c.tabs.get("Audit", None).grids for r in g.rows] if c.tabs.get("Audit") else []
                for c in case.walk()}
    if part == "search":
        return [{"stc": r.stc_id, "sub_case": r.sub_case_id, "cells": r.cells} for r in rep.rows]
    return {"error": f"unknown part {part}"}


def _json(obj):
    def default(o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return str(o)
    return json.dumps(obj, ensure_ascii=False, default=default, separators=(",", ":"))


# ---------------------------------------------------------------- the chat
class Assistant:
    """Conversation state + the tool loop. `reports` is shared with the Order explorer: {order_ref: OrderReport}.
    open_order(order_ref) must dissect the order (blocking) and return the OrderReport."""

    def __init__(self, api_key, reports, open_order, log=print, find_person=None):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=180)
        self.reports = reports
        self.open_order = open_order
        self.find_person = find_person
        self.created = []  # files the last answer's actions created (prepare_hoto, export_order)
        self.log = log
        self.messages = []
        self.stop = threading.Event()

    def reset(self):
        self.messages = []

    def _tool(self, name, args, status):
        ref = (args.get("order_ref") or "").strip()
        if name == "find_person":
            if not self.find_person:
                return _json({"error": "The Org Chart is not available here."}), True
            who = " ".join(x for x in (args.get("first_name"), args.get("last_name"), args.get("email")) if x)
            status(f"Looking up {who} in the Org Chart...")
            people = self.find_person(args.get("last_name", ""), args.get("first_name", ""), args.get("email", ""))
            return _json({"matches": people[:10], "count": len(people)} if people else
                         {"matches": [], "note": "Nobody with this name in the Org Chart (customer contacts are "
                                                 "not in it)."}), False
        if name == "get_order":
            rep = self.reports.get(ref)
            if not rep:
                return _json({"error": f"Order {ref} is not loaded. Loaded orders: {list(self.reports) or 'none'}. "
                                       "Call open_order to read it from SALTO."}), False
            status(f"Reading {args['part'].replace('_', ' ')} of {ref}...")
            return _json(order_part(rep, args["part"])), False
        if name == "open_order":
            status(f"Opening {ref} in SALTO (this takes a few minutes)...")
            rep = self.open_order(ref)
            if not rep or not rep.stc_id:
                return _json({"error": f"No STC found in SALTO for order {ref}."}), True
            return _json({"loaded": ref, "summary": order_part(rep, "summary")}), False
        if name in ("prepare_hoto", "export_order"):
            rep = self.reports.get(ref)
            if not rep or not rep.case:
                return _json({"error": f"Order {ref} is not loaded. Call open_order first."}), True
            return self._action(name, rep, status)
        return _json({"error": f"unknown tool {name}"}), True

    def _action(self, name, rep, status):
        """The actions the bot can take: files in the order's folder (never anything sent or changed in SALTO)."""
        import os
        from datetime import datetime
        from . import export, files, hoto
        folder = rep.folder or os.path.join(os.path.expanduser("~"), "Documents", "SALTO Buddy",
                                            files.safe(f"{rep.order_ref} - {rep.stc_id}"))
        os.makedirs(folder, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H%M")
        if name == "prepare_hoto":
            if not hoto.is_lan(rep):
                return _json({"error": f"{rep.order_ref} is not a LAN order: the HOTO sheet is for Managed LAN."}), True
            status(f"Preparing the HOTO sheet of {rep.order_ref}...")
            rows = hoto.build(rep)
            if not rows:
                return _json({"error": "No device in creation in the scope of work: nothing for a HOTO sheet."}), True
            path = files.unique(os.path.join(folder, files.safe(f"HOTO {rep.order_ref} - {rep.stc_id} {stamp}")
                                             + ".xlsx"))
            hoto.save(rows, path, rep=rep)
            self.created.append(path)
            check = [r["Device Name"] for r in rows if hoto.needs_check(r)]
            return _json({"saved": path, "devices": len(rows), "serial_numbers_to_check": check,
                          "note": "Admin and customer IP addresses are not in SALTO: to fill in by hand."}), False
        status(f"Exporting {rep.order_ref} to Excel...")
        path = files.unique(os.path.join(folder, files.safe(f"{rep.order_ref} - {rep.stc_id} {stamp}") + ".xlsx"))
        export.export_report(rep, path)
        self.created.append(path)
        return _json({"saved": path}), False

    def ask(self, text, current_order="", status=lambda s: None, on_text=None, documents=()):
        """Send one user message; runs tools until Claude answers. The answer streams in as it is written:
        on_text(piece) gets each piece of text. documents: files from salto.documents.load(), sent with the
        message. Returns the whole answer text; files the bot created are in self.created."""
        from .documents import content_block
        self.created = []
        note = f"(Order open in the app: {current_order})" if current_order else "(No order is open in the app.)"
        if documents:
            names = ", ".join(d["name"] for d in documents)
            content = [content_block(d) for d in documents] + [
                {"type": "text", "text": f"{text or 'Here is a document.'}\n\n(Attached: {names})\n{note}"}]
        else:
            content = f"{text}\n\n{note}"
        self.messages.append({"role": "user", "content": content})
        written = []  # the text of every round (a sentence before a lookup, then the answer)
        for _ in range(12):  # tool rounds per question
            status("Thinking...")
            if written and on_text:
                on_text("\n\n")  # a new round continues the same message on a new paragraph
            parts = []
            with self.client.beta.messages.stream(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM,
                tools=TOOLS,
                messages=self.messages,
                output_config={"effort": "medium"},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        parts.append(event.text)
                        if on_text:
                            on_text(event.text)
                response = stream.get_final_message()
            # keep the assistant turn exactly as returned (thinking blocks must be passed back unchanged)
            self.messages.append({"role": "assistant", "content": response.content})
            if "".join(parts).strip():
                written.append("".join(parts).strip())
            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that request."
            if response.stop_reason != "tool_use":
                return "\n\n".join(written) or "(no answer)"
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    content, is_error = self._tool(block.name, block.input, status)
                except Exception as exc:  # a SALTO problem becomes a tool error Claude can explain
                    content, is_error = _json({"error": errors.note(exc)[:300]}), True
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content,
                                "is_error": is_error})
            self.messages.append({"role": "user", "content": results})
        return "I stopped after too many steps. Try a more specific question."


def check_key(api_key):
    """Raises on a bad key / no network; returns None when the key works."""
    anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=20).models.retrieve(MODEL)
