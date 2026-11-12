// Extracción de texto en el navegador: PDF (pdf.js), Word (mammoth), Excel (SheetJS) y texto.
// Las librerías están copiadas en assets/vendor para no depender de CDNs.
import * as pdfjs from "./vendor/pdf.min.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", import.meta.url).href;
const XLSX = window.XLSX;

export const EXTENSIONES = [".pdf", ".docx", ".xlsx", ".txt", ".md"];

/** Devuelve [{pagina, texto}] (pagina = null si el formato no tiene páginas). */
export async function extraerTexto(archivo) {
  const ext = archivo.name.toLowerCase().split(".").pop();
  const datos = await archivo.arrayBuffer();
  if (ext === "pdf") {
    const pdf = await pdfjs.getDocument({ data: datos }).promise;
    const paginas = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const p = await pdf.getPage(i);
      const c = await p.getTextContent();
      let texto = "";
      for (const it of c.items) texto += it.str + (it.hasEOL ? "\n" : " ");
      paginas.push({ pagina: i, texto });
    }
    return paginas;
  }
  if (ext === "docx") {
    const r = await window.mammoth.extractRawText({ arrayBuffer: datos });
    return [{ pagina: null, texto: r.value }];
  }
  if (ext === "xlsx") {
    const libro = XLSX.read(datos);
    const partes = libro.SheetNames.map((n) => `## Hoja: ${n}\n` + XLSX.utils.sheet_to_csv(libro.Sheets[n], { FS: " | ", blankrows: false }));
    return [{ pagina: null, texto: partes.join("\n") }];
  }
  if (ext === "txt" || ext === "md") return [{ pagina: null, texto: new TextDecoder().decode(datos) }];
  throw new Error(`Formato no soportado: .${ext}`);
}

export const textoConPaginas = (paginas) =>
  paginas.map((p) => (p.pagina ? `[pág. ${p.pagina}]\n${p.texto}` : p.texto)).join("\n\n");

export function esEscaneado(paginas) {
  const conTexto = paginas.filter((p) => p.texto.trim().length > 50).length;
  return paginas.length > 0 && conTexto / paginas.length < 0.3;
}

/** Divide en fragmentos de ~tam caracteres respetando párrafos. */
export function fragmentar(paginas, tam = 1500, solape = 200) {
  const out = [];
  for (const { pagina, texto: bruto } of paginas) {
    const texto = bruto.replace(/[ \t]+/g, " ");
    const parrafos = texto.split(/\n\s*\n|\n(?=[A-ZÁÉÍÓÚÑ0-9]{2,}[.)]?\s)/).map((s) => s.trim()).filter(Boolean);
    let actual = "";
    for (const par of parrafos) {
      if (actual && actual.length + par.length + 1 > tam) {
        out.push({ pagina, texto: actual });
        actual = actual.slice(-solape) + "\n" + par;
      } else {
        actual = actual ? `${actual}\n${par}` : par;
      }
      while (actual.length > tam * 1.5) {
        out.push({ pagina, texto: actual.slice(0, tam) });
        actual = actual.slice(tam - solape);
      }
    }
    if (actual.trim()) out.push({ pagina, texto: actual });
  }
  return out;
}

export async function sha1(archivo) {
  const h = await crypto.subtle.digest("SHA-1", await archivo.arrayBuffer());
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}
