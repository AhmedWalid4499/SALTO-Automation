"""Export an OrderReport to a formatted Excel workbook (one sheet per area and per case)."""
import re
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

HEAD_FILL = PatternFill("solid", fgColor="FF7900")
HEAD_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
SECTION_FONT = Font(bold=True, size=11, color="FF7900")
NOTE_FONT = Font(italic=True, color="6B7280")
LABEL_FONT = Font(bold=True, color="6B7280")


class _Sheet:
    def __init__(self, wb, title, heading, note):
        title = re.sub(r"[\[\]:*?/\\]", "-", title)[:31] or "Sheet"
        base, n = title, 2
        while title in wb.sheetnames:
            title = f"{base[:28]}~{n}"
            n += 1
        self.ws = wb.create_sheet(title)
        self.ws.sheet_view.showGridLines = False
        self.ws.cell(row=1, column=1, value=heading).font = TITLE_FONT
        self.ws.cell(row=2, column=1, value=note).font = NOTE_FONT
        self.row = 4
        self.tables = 0

    def section(self, text):
        self.ws.cell(row=self.row, column=1, value=text).font = SECTION_FONT
        self.row += 1

    def fields(self, pairs):
        for k, v in pairs:
            self.ws.cell(row=self.row, column=1, value=k).font = LABEL_FONT
            c = self.ws.cell(row=self.row, column=2, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            self.row += 1
        self.row += 1

    def table(self, headers, rows, freeze=False):
        if not headers:
            return
        start = self.row
        for j, h in enumerate(headers, 1):
            c = self.ws.cell(row=start, column=j, value=h)
            c.fill, c.font = HEAD_FILL, HEAD_FONT
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for r in rows:
            self.row += 1
            for j, h in enumerate(headers, 1):
                v = r.get(h, "") if isinstance(r, dict) else (r[j - 1] if j - 1 < len(r) else "")
                self.ws.cell(row=self.row, column=j, value=_num(v))
        if rows:  # filterable Excel table (header names must be unique and non-empty)
            names = _unique_headers(headers)
            for j, h in enumerate(names, 1):
                self.ws.cell(row=start, column=j, value=h)
            self.tables += 1
            ref = f"A{start}:{get_column_letter(len(headers))}{self.row}"
            t = Table(displayName=f"T{abs(hash((self.ws.title, start))) % 10**8}_{self.tables}", ref=ref)
            t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
            self.ws.add_table(t)
        if freeze:
            self.ws.freeze_panes = f"A{start + 1}"
        self.row += 2

    def finish(self):
        widths = {}
        for row in self.ws.iter_rows(min_row=3):
            for c in row:
                if c.value is not None:
                    widths[c.column] = max(widths.get(c.column, 0), min(60, len(str(c.value))))
        for col, w in widths.items():
            self.ws.column_dimensions[get_column_letter(col)].width = max(10, w + 2)


def _num(v):
    if isinstance(v, str) and re.fullmatch(r"-?\d{1,12}(\.\d+)?", v.strip()) and not v.startswith("0"):
        return float(v) if "." in v else int(v)
    return v


def _unique_headers(headers):
    out, seen = [], {}
    for h in headers:
        h = str(h) or "Column"
        seen[h] = seen.get(h, 0) + 1
        out.append(h if seen[h] == 1 else f"{h} {seen[h]}")
    return out


def export_report(rep, path):
    wb = Workbook()
    wb.remove(wb.active)
    now = datetime.now().strftime("%d-%b-%Y %H:%M")
    note = f"GOLD order {rep.order_ref} · STC {rep.stc_id} · generated {now} by SALTO Buddy"
    case = rep.case

    s = _Sheet(wb, "Summary", f"{rep.order_ref} · {rep.stc_id}", note)
    s.section("Order")
    s.fields([("STC", rep.stc_id), ("Status", rep.status), ("Current stage", rep.current_stage),
              ("Stages", " > ".join(f"{x.name} ({x.state})" for x in rep.stages)),
              ("EQPs", ", ".join(rep.eqps)), ("Folder", rep.folder)])
    if case:
        s.fields(case.header)
        s.section("Sub-cases")
        s.table(["Case", "Type", "Stages"],
                [[c.stc_id, c.title, " > ".join(f"{x.name} ({x.state})" for x in c.stages)] for c in case.subcases])
    s.finish()

    if case:
        for scope in (True, False):
            s = _Sheet(wb, "Scope of work" if scope else "All devices",
                       "Scope of work devices" if scope else "All devices", note)
            for n in case.scope:
                g = n.devices if scope else n.all_devices
                s.section(f"{n.product} > {n.node}")
                if scope:
                    s.fields(n.counts)
                if g:
                    s.table(g.headers, g.rows)
            s.finish()

        eqps = [c for c in case.walk() if c.stc_id.startswith("EQP-")]
        serials = [r for c in eqps for r in c.flip.get("serials", [])]
        if serials:
            s = _Sheet(wb, "FLIP serial numbers", "FLIP serial numbers", note)
            s.table(["Device (OBS name)", "Serial number", "Model", "FLIP part number", "CDC", "USID", "FLIP status",
                     "Condition", "EQP", "Intervention", "Part request", "Check"], serials, freeze=True)
            s.section("All FLIP parts")
            s.table(["EQP", "Device", "Part number", "Serial number", "Description", "Status", "Condition", "Request",
                     "Type", "Revision", "Created"], [dict(p, EQP=c.stc_id) for c in eqps for p in c.flip.get("parts", [])])
            s.finish()

        s = _Sheet(wb, "Participants", "Participants", note)
        s.table(["Case", "Name", "Role", "Party"],
                [[c.stc_id, p.name, p.role, p.party] for c in case.walk() for p in c.participants], freeze=True)
        s.finish()

        s = _Sheet(wb, "Downloads", "Attachments and downloads", note)
        s.table(["Case", "Title", "Category", "Added by", "Date", "Saved as"],
                [{"Case": c.stc_id, **a} for c in case.walk() for a in c.attachments], freeze=True)
        s.finish()

        for c in case.walk():
            s = _Sheet(wb, c.stc_id, f"{c.stc_id} · {c.title}", note)
            if c.stages:
                s.section("Stages")
                s.fields([(x.name, x.state) for x in c.stages])
            if c.participants:
                s.section("Participants")
                s.fields([(p.role or p.party, p.name) for p in c.participants])
            for name, td in c.tabs.items():
                for sec, fs in td.sections:
                    s.section(f"{name} · {sec}")
                    s.fields(fs)
                for g in td.grids:
                    s.section(f"{name} · {g.name}")
                    s.table(g.headers, g.rows)
            s.finish()

    s = _Sheet(wb, "Search results", "STC Search results", note)
    width = max((len(r.cells) for r in rep.rows), default=0)
    s.table(["STC ID", "Sub-case ID"] + [f"Col {i + 1}" for i in range(2, width)],
            [[r.stc_id, r.sub_case_id] + r.cells[2:] for r in rep.rows], freeze=True)
    s.finish()
    wb.save(path)
    return path
