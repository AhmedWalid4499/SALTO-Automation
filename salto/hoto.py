"""HOTO preparation: the hand-over sheet of a LAN project, one row per device in creation."""
import re
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .flip import norm

COLUMNS = ["Gold Ref", "Go Live Date", "Project Manager", "City", "Country", "Site address", "Site ID",
           "Device Name", "OBS Device name", "Device Type", "Switch number", "Stack Master Name", "Device Model",
           "USID", "Admin ip address", "Customer ip address", "Device SN#", "Local site contact",
           "Telephone / mobile number of local site person", "Email Address of local contact"]

# SALTO device type -> HOTO short type
TYPES = {"lan switch": "SW", "switch": "SW", "wireless access point": "AP", "access point": "AP",
         "wireless lan controller": "WLC", "router": "RTR", "firewall": "FW"}
# device name code (skf-<code>-site-nn) -> HOTO short type
CODES = {"sw": "SW", "ap": "AP", "wlc": "WLC", "rt": "RTR", "rtr": "RTR", "fw": "FW"}


def is_lan(rep):
    case = rep.case
    product = dict(case.header).get("Product", "") if case else ""
    return bool(case) and (rep.stc_id.startswith("MLAN-") or "lan" in product.lower())


def _fields(case, tab, section=None):
    t = case.tabs.get(tab)
    if not t:
        return {}
    out = {}
    for name, pairs in t.sections:
        if section is None or name.lower() == section.lower():
            for k, v in pairs:
                out.setdefault(k, v)
    return out


def _date(text):
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            d = datetime.strptime(text.strip(), fmt)
            return f"{d.month}/{d.day}/{d.year}"
        except ValueError:
            pass
    return text


def creation_devices(case):
    """Scope-of-work devices being created (not ceased or modified)."""
    devs = case.scope_devices
    if any(d.get("Cycle") for d in devs):
        return [d for d in devs if (d.get("Cycle") or "").lower() == "creation"]
    return [d for d in devs if (d.get("Cycle") or "").lower() != "cessation"]


def device_type(dev):
    t = TYPES.get((dev.get("Type") or "").strip().lower())
    if t:
        return t
    parts = (dev.get("Customer Defined Code") or "").lower().split("-")
    return CODES.get(parts[1], parts[1].upper()) if len(parts) > 2 else dev.get("Type", "")


def device_number(name):
    """skf-sw-itvil-01_01 -> 01_01, skf-sw-itvil-02_01-a14 -> 02_01, skf-ap-semol-03 -> 03."""
    name = (name or "").strip()
    m = re.search(r"-(\d+_\d+)(?=-|$)", name) or re.search(r"-(\d+)(?=-|$)", name)
    return m.group(1) if m else ""


def build(rep):
    """HOTO rows for the order's devices in creation (Admin / Customer IP are not in SALTO: left empty)."""
    case = rep.case
    info = _fields(case, "Information", "MAIN DATES")
    go_live = info.get("Revised Target Delivery Date") or info.get("Initial Target Delivery Date") or \
        dict(case.header).get("Target Delivery Date", "")
    pm = next((p.name for p in case.participants if p.role.lower() == "project manager"), "")
    site, addr = _fields(case, "Site", "SITE"), _fields(case, "Site", "Address")
    contact = _fields(case, "Site", "Primary Contact")
    person = " ".join(x for x in (contact.get("First Name", ""), contact.get("Last Name", "")) if x)
    phone = contact.get("Mobile") or contact.get("Phone", "")
    serials = {norm(s["Device (OBS name)"]): s["Serial number"]
               for c in case.walk() for s in (c.flip or {}).get("serials", []) if s["Serial number"]}

    devs = creation_devices(case)
    rows = []
    for dev in devs:
        name = dev.get("Customer Defined Code", "")
        parts = name.split("-")
        site_id = (site.get("Customer Site Name") or (parts[2] if len(parts) > 3 else "")).upper()
        kind = device_type(dev)
        number = device_number(name) if kind == "SW" else ""
        master = ""
        if "_" in number:  # stack: <stack>_<member>, member 01 is the master
            stack, member = number.split("_", 1)
            if int(member) == 1:
                master = "Master"
            else:
                head = name.replace(f"-{number}", f"-{stack}_{'1'.zfill(len(member))}", 1)
                master = head if any(d.get("Customer Defined Code") == head for d in devs) else "Member"
        rows.append({
            "Gold Ref": rep.order_ref, "Go Live Date": _date(go_live), "Project Manager": pm,
            "City": addr.get("City", ""), "Country": addr.get("Country", "").upper(),
            "Site address": addr.get("Address", ""), "Site ID": site_id,
            "Device Name": name, "OBS Device name": dev.get("Name", ""), "Device Type": kind,
            "Switch number": number, "Stack Master Name": master, "Device Model": dev.get("Model", ""),
            "USID": dev.get("USID", ""), "Admin ip address": "", "Customer ip address": "",
            "Device SN#": serials.get(norm(dev.get("Name", "")), ""),
            "Local site contact": person, "Telephone / mobile number of local site person": phone,
            "Email Address of local contact": contact.get("Email", ""),
        })
    return sorted(rows, key=lambda r: (r["Device Type"] != "SW", r["Device Name"]))


def needs_check(row):
    return not row["Device SN#"] or " / " in row["Device SN#"]


def save(rows, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "HOTO"
    fill, font = PatternFill("solid", fgColor="FF7900"), Font(bold=True, color="FFFFFF")
    for j, h in enumerate(COLUMNS, 1):
        c = ws.cell(row=1, column=j, value=h)
        c.fill, c.font = fill, font
        c.alignment = Alignment(wrap_text=True, vertical="top")
        width = max([len(h) * 0.6] + [len(str(r.get(h, ""))) for r in rows])
        ws.column_dimensions[c.column_letter].width = min(max(10, width + 2), 45)
    check = PatternFill("solid", fgColor="FFF3C4")  # serial number to check: missing, or several in FLIP
    for i, r in enumerate(rows, 2):
        for j, h in enumerate(COLUMNS, 1):
            c = ws.cell(row=i, column=j, value=r.get(h, ""))
            if h == "Device SN#" and needs_check(r):
                c.fill = check
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)
    return path
