"""Extracción de texto de documentos y división en fragmentos."""
import io
import re

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

EXTENSIONES = ["pdf", "docx", "xlsx", "txt", "md"]


def extraer_texto(nombre: str, datos: bytes) -> list[tuple[int | None, str]]:
    """Devuelve una lista de (página, texto). Página es None si el formato no tiene páginas."""
    ext = nombre.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        lector = PdfReader(io.BytesIO(datos))
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(lector.pages)]
    if ext == "docx":
        doc = Document(io.BytesIO(datos))
        partes = [p.text for p in doc.paragraphs if p.text.strip()]
        for tabla in doc.tables:
            for fila in tabla.rows:
                celdas = [c.text.strip() for c in fila.cells]
                if any(celdas):
                    partes.append(" | ".join(celdas))
        return [(None, "\n".join(partes))]
    if ext == "xlsx":
        libro = load_workbook(io.BytesIO(datos), read_only=True, data_only=True)
        partes = []
        for hoja in libro.worksheets:
            partes.append(f"## Hoja: {hoja.title}")
            for fila in hoja.iter_rows(values_only=True):
                valores = [str(v) for v in fila if v is not None and str(v).strip()]
                if valores:
                    partes.append(" | ".join(valores))
        return [(None, "\n".join(partes))]
    if ext in ("txt", "md"):
        return [(None, datos.decode("utf-8", errors="replace"))]
    raise ValueError(f"Formato no soportado: .{ext}")


def texto_con_paginas(paginas: list[tuple[int | None, str]]) -> str:
    return "\n\n".join(f"[pág. {p}]\n{t}" if p else t for p, t in paginas)


def es_probablemente_escaneado(paginas: list[tuple[int | None, str]]) -> bool:
    con_texto = sum(1 for _, t in paginas if len(t.strip()) > 50)
    return len(paginas) > 0 and con_texto / len(paginas) < 0.3


def fragmentar(paginas: list[tuple[int | None, str]], tam: int = 1500, solape: int = 200) -> list[dict]:
    """Divide en fragmentos de ~tam caracteres, respetando párrafos y guardando la página de inicio."""
    fragmentos = []
    for pagina, texto in paginas:
        texto = re.sub(r"[ \t]+", " ", texto)
        parrafos = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-ZÁÉÍÓÚÑ0-9]{2,}[\.\)]?\s)", texto) if p.strip()]
        actual = ""
        for par in parrafos:
            if len(actual) + len(par) + 1 > tam and actual:
                fragmentos.append({"pagina": pagina, "texto": actual})
                actual = actual[-solape:] + "\n" + par
            else:
                actual = f"{actual}\n{par}" if actual else par
            while len(actual) > tam * 1.5:
                fragmentos.append({"pagina": pagina, "texto": actual[:tam]})
                actual = actual[tam - solape:]
        if actual.strip():
            fragmentos.append({"pagina": pagina, "texto": actual})
    return fragmentos
