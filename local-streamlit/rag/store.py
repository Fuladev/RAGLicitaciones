"""Almacén local de documentos y fragmentos, con búsqueda BM25."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from rank_bm25 import BM25Plus

from .ingest import es_probablemente_escaneado, extraer_texto, fragmentar

STOPWORDS = set("""
a al algo ante antes como con contra cual cuando de del desde donde dos el ella ellas ellos en entre era es esa ese eso esta
este esto estos estas fue ha han hasta la las le les lo los mas me mi muy no nos o otra otro para pero por que quien se
ser si sin sobre su sus tambien te tiene todo tu un una uno unos unas y ya son sea sera seran debe deben dicho dicha cada
""".split())


def tokenizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9]+", texto) if len(t) > 2 and t not in STOPWORDS]


class Almacen:
    def __init__(self, raiz: Path):
        self.dir_raw = raiz / "raw"
        self.dir_proc = raiz / "processed"
        self.dir_raw.mkdir(parents=True, exist_ok=True)
        self.dir_proc.mkdir(parents=True, exist_ok=True)
        self.ruta_indice = self.dir_proc / "indice.json"
        self.docs: dict[str, dict] = {}
        self.fragmentos: list[dict] = []
        self._bm25 = None
        self._cargar()

    # ---------- persistencia ----------
    def _cargar(self):
        if self.ruta_indice.exists():
            datos = json.loads(self.ruta_indice.read_text(encoding="utf-8"))
            self.docs = datos.get("docs", {})
            self.fragmentos = datos.get("fragmentos", [])
        self._bm25 = None

    def _guardar(self):
        datos = {"docs": self.docs, "fragmentos": self.fragmentos}
        self.ruta_indice.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        self._bm25 = None

    # ---------- documentos ----------
    def agregar(self, nombre: str, datos: bytes, categoria: str) -> dict:
        doc_id = hashlib.sha1(datos).hexdigest()[:12]
        if doc_id in self.docs:
            return {"estado": "duplicado", "doc": self.docs[doc_id]}
        paginas = extraer_texto(nombre, datos)
        frags = fragmentar(paginas)
        carpeta = self.dir_raw / categoria
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / nombre).write_bytes(datos)
        doc = {
            "id": doc_id,
            "nombre": nombre,
            "categoria": categoria,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fragmentos": len(frags),
            "caracteres": sum(len(t) for _, t in paginas),
            "escaneado": es_probablemente_escaneado(paginas),
        }
        self.docs[doc_id] = doc
        for i, f in enumerate(frags):
            self.fragmentos.append({
                "id": f"{doc_id}-{i}",
                "doc_id": doc_id,
                "documento": nombre,
                "categoria": categoria,
                "pagina": f["pagina"],
                "texto": f["texto"],
            })
        self._guardar()
        return {"estado": "ok", "doc": doc}

    def eliminar(self, doc_id: str):
        doc = self.docs.pop(doc_id, None)
        if not doc:
            return
        self.fragmentos = [f for f in self.fragmentos if f["doc_id"] != doc_id]
        archivo = self.dir_raw / doc["categoria"] / doc["nombre"]
        if archivo.exists():
            archivo.unlink()
        self._guardar()

    def conteo_por_categoria(self) -> dict:
        conteo = {}
        for d in self.docs.values():
            conteo[d["categoria"]] = conteo.get(d["categoria"], 0) + 1
        return conteo

    # ---------- búsqueda ----------
    def _indice(self):
        if self._bm25 is None and self.fragmentos:
            tokens = [tokenizar(f["texto"]) for f in self.fragmentos]
            self._conjuntos = [set(t) for t in tokens]
            self._bm25 = BM25Plus(tokens)
        return self._bm25

    def buscar(self, consulta: str, k: int = 8, categorias: list[str] | None = None) -> list[tuple[float, dict]]:
        bm25 = self._indice()
        if bm25 is None:
            return []
        tokens = tokenizar(consulta)
        if not tokens:
            return []
        puntajes = bm25.get_scores(tokens)
        consulta_set = set(tokens)
        pares = [
            (float(s), f) for s, f, conj in zip(puntajes, self.fragmentos, self._conjuntos)
            if (categorias is None or f["categoria"] in categorias) and conj & consulta_set
        ]
        pares.sort(key=lambda p: p[0], reverse=True)
        return pares[:k]

    def buscar_para_documento(self, fragmentos_consulta: list[str], categorias: list[str],
                              k_por_consulta: int = 3, maximo: int = 40) -> list[dict]:
        """Recupera los fragmentos más relevantes para un documento completo (p. ej. un pliego):
        busca con cada fragmento del pliego y acumula puntajes."""
        acumulado: dict[str, float] = {}
        por_id: dict[str, dict] = {}
        for q in fragmentos_consulta:
            for s, f in self.buscar(q, k=k_por_consulta, categorias=categorias):
                acumulado[f["id"]] = acumulado.get(f["id"], 0) + s
                por_id[f["id"]] = f
        mejores = sorted(acumulado, key=acumulado.get, reverse=True)[:maximo]
        return [por_id[i] for i in mejores]
