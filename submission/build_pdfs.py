"""Renders the submission Markdown documents to PDF (pip install markdown xhtml2pdf).

Run from the repository root:  python submission/build_pdfs.py
"""

from pathlib import Path

import markdown
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa
from xhtml2pdf.default import DEFAULT_FONT

HERE = Path(__file__).resolve().parent
DOCS = [
    HERE / "01-technical-documentation" / "TECHNICAL_DOCUMENTATION.md",
    HERE / "05-security-self-assessment" / "SECURITY_SELF_ASSESSMENT.md",
]
FONTS = Path("C:/Windows/Fonts")
# xhtml2pdf ignores @font-face with absolute Windows paths, so register the TTFs with reportlab directly.
for name, regular, bold in (("CalibriEmb", "calibri.ttf", "calibrib.ttf"), ("ConsolasEmb", "consola.ttf", "consolab.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(FONTS / regular)))
    pdfmetrics.registerFont(TTFont(name + "-Bold", str(FONTS / bold)))
    for b, face in ((0, name), (1, name + "-Bold")):
        for i in (0, 1):
            addMapping(name, b, i, face)
    DEFAULT_FONT[name.lower()] = name

CSS = f"""
@page {{ size: A4; margin: 1.8cm 1.6cm 1.8cm 1.6cm;
  @frame footer {{ -pdf-frame-content: footer; bottom: 0.8cm; margin-left: 1.6cm; margin-right: 1.6cm; height: 0.6cm; }} }}
body {{ font-family: CalibriEmb; font-size: 10pt; line-height: 1.4; color: #1f2937; }}
h1 {{ font-size: 20pt; color: #0b1220; margin: 0 0 6pt 0; }}
h2 {{ font-size: 14pt; color: #0f766e; margin: 16pt 0 4pt 0; -pdf-keep-with-next: true; }}
h3 {{ font-size: 11.5pt; color: #0b1220; margin: 10pt 0 3pt 0; -pdf-keep-with-next: true; }}
p, li {{ margin: 0 0 4pt 0; }}
pre code, code {{ font-family: ConsolasEmb; font-size: 8.5pt; color: #0f3d3a; }}
pre {{ font-family: ConsolasEmb; font-size: 7.2pt; line-height: 1.2; background-color: #f3f6f8; border: 0.5pt solid #d6dde3;
  padding: 6pt; margin: 4pt 0 8pt 0; }}
table {{ border-collapse: collapse; margin: 4pt 0 8pt 0; }}
th {{ background-color: #0b1220; color: #ffffff; font-weight: bold; padding: 3pt 4pt; font-size: 8.5pt; text-align: left; }}
td {{ border-bottom: 0.5pt solid #d6dde3; padding: 3pt 4pt; font-size: 8.5pt; vertical-align: top; }}
hr {{ color: #d6dde3; }}
"""


def render(md_path: Path) -> Path:
    html_body = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    html = (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html_body}"
            f"<div id='footer' style='font-size:8pt;color:#6b7280;text-align:right'>CashPilot · FinTechathon 2026 · "
            f"page <pdf:pagenumber/> of <pdf:pagecount/></div></body></html>")
    out = md_path.with_suffix(".pdf")
    with open(out, "wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")
    if result.err:
        raise SystemExit(f"PDF render failed for {md_path.name}")
    return out


if __name__ == "__main__":
    for doc in DOCS:
        print("wrote", render(doc))
