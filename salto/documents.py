"""Files the user gives The Friendly SALTO Bot: Word (.docx), PDF and plain text.

Word files are read directly from their XML (no Word or extra library needed): headings, paragraphs, lists and
tables (as Markdown tables), in document order. PDFs go to Claude as they are (it reads them natively).
"""
import base64
import os
import re
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_CHARS = 150_000            # about 40 pages of text: enough for any order document
MAX_PDF_BYTES = 20 * 1024 * 1024
TEXT_TYPES = (".txt", ".md", ".csv", ".log", ".json", ".xml", ".eml")
SUPPORTED = (".docx", ".pdf") + TEXT_TYPES
FILETYPES = [("Documents", "*.docx *.pdf *.txt *.md *.csv"), ("Word", "*.docx"), ("PDF", "*.pdf"),
             ("Text", "*.txt *.md *.csv"), ("All files", "*.*")]


class DocumentError(Exception):
    pass


def load(path):
    """{'name', 'kind': 'text'|'pdf', 'text' or 'data' (base64), 'chars'/'size', 'pages'?} for one file."""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    if ext == ".doc":
        raise DocumentError(f"{name} is an old Word file (.doc). Open it in Word and save it as .docx, then attach "
                            "it again.")
    if ext == ".docx":
        text = docx_text(path)
    elif ext == ".pdf":
        size = os.path.getsize(path)
        if size > MAX_PDF_BYTES:
            raise DocumentError(f"{name} is too big ({size // 1_048_576} MB, the limit is 20 MB).")
        with open(path, "rb") as f:
            return {"name": name, "kind": "pdf", "data": base64.standard_b64encode(f.read()).decode("ascii"),
                    "size": size}
    elif ext in TEXT_TYPES:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        raise DocumentError(f"{name}: this kind of file is not supported (Word, PDF or text files only).")
    if not text.strip():
        raise DocumentError(f"{name} has no text to read (is it only pictures or a scan?).")
    cut = len(text) > MAX_CHARS
    return {"name": name, "kind": "text", "text": text[:MAX_CHARS] + ("\n\n[... document cut here: too long]"
                                                                        if cut else ""), "chars": len(text)}


def content_block(doc):
    """The Claude message block for a loaded document."""
    if doc["kind"] == "pdf":
        return {"type": "document", "title": doc["name"],
                "source": {"type": "base64", "media_type": "application/pdf", "data": doc["data"]}}
    return {"type": "document", "title": doc["name"],
            "source": {"type": "text", "media_type": "text/plain", "data": doc["text"]}}


# ---------------------------------------------------------------- Word
def docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
            styles = _heading_styles(z)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise DocumentError(f"{os.path.basename(path)} could not be read as a Word document ({exc}).")
    body = root.find(f"{W}body")
    out = []
    for el in list(body if body is not None else []):
        if el.tag == f"{W}p":
            line = _paragraph(el, styles)
            if line is not None:
                out.append(line)
        elif el.tag == f"{W}tbl":
            out.append(_table(el, styles))
        elif el.tag == f"{W}sdt":  # content controls (forms) wrap paragraphs and tables
            for inner in el.iter():
                if inner.tag == f"{W}p":
                    line = _paragraph(inner, styles)
                    if line is not None:
                        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _heading_styles(z):
    """styleId -> heading level, from styles.xml (Heading 1, Titre 1, Title...)."""
    levels = {}
    try:
        root = ET.fromstring(z.read("word/styles.xml"))
    except (KeyError, ET.ParseError):
        return levels
    for st in root.iter(f"{W}style"):
        sid = st.get(f"{W}styleId", "")
        name = (st.find(f"{W}name").get(f"{W}val", "") if st.find(f"{W}name") is not None else "").lower()
        m = re.search(r"(heading|titre|überschrift|titolo|título)\s*(\d)", name)
        if m:
            levels[sid] = int(m.group(2))
        elif name in ("title", "titre"):
            levels[sid] = 1
    return levels


def _runs_text(el):
    parts = []
    for node in el.iter():
        if node.tag == f"{W}t" and node.text:
            parts.append(node.text)
        elif node.tag in (f"{W}tab",):
            parts.append("\t")
        elif node.tag in (f"{W}br", f"{W}cr"):
            parts.append("\n")
        elif node.tag == f"{W}sym":
            parts.append("•")
    return "".join(parts)


def _paragraph(p, styles):
    text = _runs_text(p).strip()
    ppr = p.find(f"{W}pPr")
    style = ""
    if ppr is not None and ppr.find(f"{W}pStyle") is not None:
        style = ppr.find(f"{W}pStyle").get(f"{W}val", "")
    if not text:
        return ""
    level = styles.get(style)
    if level:
        return "\n" + "#" * min(level, 4) + " " + text
    if ppr is not None and ppr.find(f"{W}numPr") is not None:  # a bulleted / numbered list item
        ilvl = ppr.find(f"{W}numPr/{W}ilvl")
        depth = int(ilvl.get(f"{W}val", "0")) if ilvl is not None else 0
        return "  " * depth + "- " + text
    return text


def _table(tbl, styles):
    rows = []
    for tr in tbl.findall(f"{W}tr"):
        cells = []
        for tc in tr.findall(f"{W}tc"):
            lines = [_runs_text(p).strip() for p in tc.findall(f".//{W}p")]
            cells.append(" / ".join(l for l in lines if l).replace("|", "/"))
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n" + "\n".join(lines) + "\n"
