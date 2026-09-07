"""Convert docs/USER_GUIDE.md to Word (.docx and .doc)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "docs" / "USER_GUIDE.md"
OUT_DOCX = ROOT / "docs" / "Protection_RCA_User_Guide.docx"
OUT_DOC = ROOT / "docs" / "Protection_RCA_User_Guide.doc"


def inline_runs(paragraph, s: str) -> None:
    pattern = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
    for part in pattern.split(s):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        else:
            paragraph.add_run(part)


def add_code_para(doc: Document, content: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(content)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    p.paragraph_format.left_indent = Inches(0.2)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "F1F5F9")
    shd.set(qn("w:val"), "clear")
    p.paragraph_format.element.get_or_add_pPr().append(shd)


def flush_table(doc: Document, table_rows: list[str]) -> None:
    rows: list[list[str]] = []
    for r in table_rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", c.replace(" ", "") or "-") for c in cells):
            continue
        rows.append(cells)
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for i, r in enumerate(rows):
        for j in range(cols):
            cell_text = r[j] if j < len(r) else ""
            cell_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", cell_text).replace("`", "")
            table.rows[i].cells[j].text = cell_text
            for p in table.rows[i].cells[j].paragraphs:
                for run in p.runs:
                    run.font.size = Pt(9)
                    if i == 0:
                        run.bold = True
    doc.add_paragraph()


def main() -> None:
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.85)
        section.bottom_margin = Inches(0.85)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    in_code = False
    code_buf: list[str] = []
    table_rows: list[str] = []

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                add_code_para(doc, "\n".join(code_buf))
                code_buf = []
                in_code = False
            else:
                if table_rows:
                    flush_table(doc, table_rows)
                    table_rows = []
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        if line.strip().startswith("|"):
            table_rows.append(line)
            continue
        if table_rows:
            flush_table(doc, table_rows)
            table_rows = []

        if line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=0)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=1)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=2)
        elif line.startswith("#### "):
            doc.add_heading(line[5:].strip(), level=3)
        elif line.strip() == "---":
            doc.add_paragraph()
        elif re.match(r"^\d+\.\s+", line.strip()):
            p = doc.add_paragraph(style="List Number")
            inline_runs(p, re.sub(r"^\d+\.\s+", "", line.strip()))
        elif line.strip().startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            inline_runs(p, line.strip()[2:])
        elif line.strip().startswith(">"):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            run = p.add_run(line.strip().lstrip("> ").strip())
            run.italic = True
            run.font.color.rgb = RGBColor(0x33, 0x55, 0x77)
        elif line.strip():
            p = doc.add_paragraph()
            inline_runs(p, line.strip())

    if code_buf:
        add_code_para(doc, "\n".join(code_buf))
    if table_rows:
        flush_table(doc, table_rows)

    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_DOCX)
    # Word opens .docx; also provide .doc filename copy for users who request .doc
    shutil.copyfile(OUT_DOCX, OUT_DOC)
    # Mirror Markdown + Word copies for Help UI and project root
    public_md = ROOT / "frontend" / "public" / "USER_GUIDE.md"
    if public_md.parent.exists():
        shutil.copyfile(MD_PATH, public_md)
    for dest_dir in (ROOT, ROOT.parent):
        try:
            shutil.copyfile(OUT_DOCX, dest_dir / OUT_DOCX.name)
            shutil.copyfile(OUT_DOC, dest_dir / OUT_DOC.name)
        except OSError:
            pass
    print(f"Wrote {OUT_DOCX} ({OUT_DOCX.stat().st_size} bytes)")
    print(f"Wrote {OUT_DOC} ({OUT_DOC.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
