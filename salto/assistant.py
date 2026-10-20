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

MODEL = "claude-opus-5-5"
PARTS = ["summary", "devices", "serial_numbers", "people", "case_tabs", "subcases", "attachments", "audit", "search"]

SYSTEM = """You are Buddy, the assistant inside SALTO Buddy, a desktop tool used by Orange Business delivery staff \
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
- If a field exists nowhere, say that plainly and offer the closest fields that do exist (device Name, USID, Model...).
- Where the data comes from matters: say which case and tab you took it from, e.g. "Site tab of MLAN-215851".
- Device lists: the TS tab has, per product node, the devices in scope of work and all devices on the site; \
"in creation / added" means Cycle = Creation, "ceased / removed" means Cycle = Cessation.
- Answer in the user's language. Be short. Plain text only (no Markdown headings or bold); for lists, one item per \
line starting with "- ", fields separated by " | "."""

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
]


# ---------------------------------------------------------------- order data -> JSON
def _tab_dict(td):
    return {"sections": {s: dict(f) for s, f in td.sections},
            "tables": [{"name": g.name, "rows": g.rows} for g in td.grids]}


def _case_dict(c, with_tabs=True, skip=("Audit",)):
    d = {"case": c.stc_id, "type": c.title,
         "stages": [f"{s.name}: {s.state}" for s in c.stages],
         "header": dict(c.header),
         "people": [{"name": p.name, "role": p.role or p.party} for p in c.participants]}
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
        return [{"case": c.stc_id, "type": c.title,
                 "people": [{"name": p.name, "role": p.role or p.party} for p in c.participants]} for c in case.walk()]
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

    def __init__(self, api_key, reports, open_order, log=print):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=180)
        self.reports = reports
        self.open_order = open_order
        self.log = log
        self.messages = []
        self.stop = threading.Event()

    def reset(self):
        self.messages = []

    def _tool(self, name, args, status):
        ref = (args.get("order_ref") or "").strip()
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
        return _json({"error": f"unknown tool {name}"}), True

    def ask(self, text, current_order="", status=lambda s: None):
        """Send one user message; runs tools until Claude answers. Returns the answer text."""
        note = f"(Order open in the app: {current_order})" if current_order else "(No order is open in the app.)"
        self.messages.append({"role": "user", "content": f"{text}\n\n{note}"})
        for _ in range(12):  # tool rounds per question
            status("Thinking...")
            response = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM,
                tools=TOOLS,
                messages=self.messages,
                output_config={"effort": "medium"},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            # keep the assistant turn exactly as returned (thinking blocks must be passed back unchanged)
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return "Sorry, I can't help with that request."
            if response.stop_reason != "tool_use":
                return "".join(b.text for b in response.content if b.type == "text").strip() or "(no answer)"
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    content, is_error = self._tool(block.name, block.input, status)
                except Exception as exc:  # a SALTO problem becomes a tool error Claude can explain
                    content, is_error = _json({"error": str(exc).splitlines()[0][:300]}), True
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content,
                                "is_error": is_error})
            self.messages.append({"role": "user", "content": results})
        return "I stopped after too many steps. Try a more specific question."


def check_key(api_key):
    """Raises on a bad key / no network; returns None when the key works."""
    anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=20).models.retrieve(MODEL)
