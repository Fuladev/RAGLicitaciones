"""Exporta el análisis en Markdown a un documento Word sencillo."""
import io
import re

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt


def _agregar_texto(parrafo, texto: str):
    # Soporta **negrita**; resalta en amarillo las líneas con 🟡
    partes = re.split(r"(\*\*[^*]+\*\*)", texto)
    for p in partes:
        if not p:
            continue
        run = parrafo.add_run(p[2:-2] if p.startswith("**") and p.endswith("**") else p)
        run.bold = p.startswith("**") and p.endswith("**")
        if "🟡" in texto:
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW


def markdown_a_docx(md: str, titulo: str) -> bytes:
    doc = Document()
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(10)
    doc.add_heading(titulo, level=0)
    lineas = md.splitlines()
    i = 0
    while i < len(lineas):
        linea = lineas[i].rstrip()
        if linea.startswith("|"):
            filas = []
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                celdas = [c.strip() for c in lineas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas if c):
                    filas.append(celdas)
                i += 1
            if filas:
                ncol = max(len(f) for f in filas)
                tabla = doc.add_table(rows=0, cols=ncol)
                tabla.style = "Table Grid"
                for j, fila in enumerate(filas):
                    celdas = tabla.add_row().cells
                    for k in range(ncol):
                        texto = fila[k] if k < len(fila) else ""
                        par = celdas[k].paragraphs[0]
                        _agregar_texto(par, texto.replace("**", "") if j == 0 else texto)
                        if j == 0:
                            for r in par.runs:
                                r.bold = True
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", linea)
        if m:
            doc.add_heading(m.group(2), level=min(len(m.group(1)), 3))
        elif re.match(r"^\s*[-*]\s+", linea):
            _agregar_texto(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*]\s+", "", linea))
        elif re.match(r"^\s*\d+\.\s+", linea):
            _agregar_texto(doc.add_paragraph(style="List Number"), re.sub(r"^\s*\d+\.\s+", "", linea))
        elif linea.startswith(">"):
            _agregar_texto(doc.add_paragraph(style="Intense Quote"), linea.lstrip("> "))
        elif linea.strip() and not re.fullmatch(r"-{3,}", linea.strip()):
            _agregar_texto(doc.add_paragraph(), linea)
        i += 1
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
