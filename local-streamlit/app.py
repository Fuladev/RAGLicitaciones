"""RAG de licitaciones (beta): carga de documentos de referencia, análisis de pliegos y guía de carga."""
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from rag.analyzer import (CATS_EMPRESA, CATS_OBSERVACIONES, MODELO_POR_DEFECTO,
                          construir_mensajes_analisis, construir_mensajes_consulta, transmitir)
from rag.exportar import markdown_a_docx
from rag.guia import CATEGORIAS, estado_carga, porcentaje_cobertura, siguiente_paso
from rag.ingest import EXTENSIONES, es_probablemente_escaneado, extraer_texto, fragmentar, texto_con_paginas
from rag.store import Almacen

RAIZ = Path(__file__).resolve().parent.parent          # carpeta del proyecto (contiene data/)


def _cargar_env():
    """Lee ANTHROPIC_API_KEY y otras variables desde app/.env o la raíz del proyecto, si existen."""
    for ruta in (Path(__file__).parent / ".env", RAIZ / ".env"):
        if ruta.exists():
            for linea in ruta.read_text(encoding="utf-8").splitlines():
                if "=" in linea and not linea.lstrip().startswith("#"):
                    k, v = linea.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_cargar_env()
DIR_DATOS = Path(os.environ.get("RAG_DATA_DIR", RAIZ / "data"))
DIR_ANALISIS = DIR_DATOS / "processed" / "analisis"
RUTA_CONFIG = DIR_DATOS / "processed" / "config.json"

st.set_page_config(page_title="RAG Licitaciones (beta)", page_icon="📑", layout="wide")


@st.cache_resource
def obtener_almacen() -> Almacen:
    return Almacen(DIR_DATOS)


def leer_config() -> dict:
    if RUTA_CONFIG.exists():
        return json.loads(RUTA_CONFIG.read_text(encoding="utf-8"))
    return {"empresa": "", "tipo": "Agencia de seguros"}


def guardar_config(cfg: dict):
    RUTA_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    RUTA_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


almacen = obtener_almacen()
cfg = leer_config()

# ---------------- Barra lateral ----------------
with st.sidebar:
    st.title("📑 RAG Licitaciones")
    st.caption("Versión beta")
    st.subheader("Configuración")
    api_key = st.text_input("Clave de API de Anthropic", type="password",
                            value=os.environ.get("ANTHROPIC_API_KEY", ""),
                            help="Se lee de la variable ANTHROPIC_API_KEY o del archivo .env. No se guarda en disco.")
    empresa = st.text_input("Nombre de tu empresa", value=cfg.get("empresa", ""))
    tipo = st.selectbox("Tipo de oferente", ["Agencia de seguros", "Corredor de seguros", "Otro oferente"],
                        index=["Agencia de seguros", "Corredor de seguros", "Otro oferente"].index(cfg.get("tipo", "Agencia de seguros")))
    if empresa != cfg.get("empresa") or tipo != cfg.get("tipo"):
        guardar_config({"empresa": empresa, "tipo": tipo})
    with st.expander("Opciones avanzadas"):
        modelo = st.text_input("Modelo", value=MODELO_POR_DEFECTO)
        esfuerzo = st.select_slider("Profundidad del análisis", ["low", "medium", "high", "xhigh"], value="high")
        max_frag = st.slider("Fragmentos de referencia por análisis", 10, 120, 50)

    conteo = almacen.conteo_por_categoria()
    st.divider()
    st.metric("Cobertura de la base documental", f"{porcentaje_cobertura(conteo)} %")
    paso = siguiente_paso(conteo)
    if paso:
        st.info(f"**Siguiente a cargar:** {paso['categoria']} ({paso['cargados']}/{paso['recomendado']})")
    else:
        st.success("La base tiene lo mínimo recomendado en todas las categorías.")

nombre_empresa = empresa.strip() or "la empresa"

tab_analizar, tab_base, tab_guia, tab_consultar, tab_historial = st.tabs(
    ["🔍 Analizar licitación", "📚 Base documental", "🧭 Guía de carga", "💬 Consultar la base", "🗂️ Historial"])

# ---------------- Base documental ----------------
with tab_base:
    st.header("Documentos de referencia")
    st.write("Carga aquí los documentos que el sistema usará como respaldo. Se indexan para búsqueda; "
             "no se entrena ningún modelo. Formatos: " + ", ".join(EXTENSIONES))
    col1, col2 = st.columns([1, 2])
    with col1:
        cat_clave = st.selectbox("Categoría", list(CATEGORIAS), format_func=lambda k: CATEGORIAS[k]["nombre"])
        c = CATEGORIAS[cat_clave]
        st.caption(f"**Qué es:** {c['descripcion']}\n\n**Ejemplos:** {c['ejemplos']}")
    with col2:
        archivos = st.file_uploader("Archivos", type=EXTENSIONES, accept_multiple_files=True, key="carga_base")
        if st.button("Indexar archivos", type="primary", disabled=not archivos):
            barra = st.progress(0.0)
            for n, a in enumerate(archivos, 1):
                try:
                    r = almacen.agregar(a.name, a.getvalue(), cat_clave)
                    if r["estado"] == "duplicado":
                        st.warning(f"{a.name}: ya estaba cargado.")
                    elif r["doc"]["escaneado"]:
                        st.warning(f"{a.name}: parece escaneado (casi sin texto). Pásalo por OCR y vuelve a cargarlo.")
                    else:
                        st.success(f"{a.name}: {r['doc']['fragmentos']} fragmentos indexados.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"{a.name}: no se pudo leer ({e}).")
                barra.progress(n / len(archivos))
            st.rerun()

    st.subheader("Documentos cargados")
    if not almacen.docs:
        st.info("Todavía no hay documentos. Empieza por la **Guía de carga**.")
    for cat, info in CATEGORIAS.items():
        docs = [d for d in almacen.docs.values() if d["categoria"] == cat]
        if not docs:
            continue
        with st.expander(f"{info['nombre']} ({len(docs)})"):
            for d in sorted(docs, key=lambda d: d["nombre"]):
                a, b = st.columns([5, 1])
                aviso = " ⚠️ escaneado" if d.get("escaneado") else ""
                a.write(f"**{d['nombre']}** · {d['fragmentos']} fragmentos · {d['fecha']}{aviso}")
                if b.button("Eliminar", key=f"del-{d['id']}"):
                    almacen.eliminar(d["id"])
                    st.rerun()

# ---------------- Guía ----------------
with tab_guia:
    st.header("Guía: qué información cargar")
    st.write("Mientras más completa la base, mejores observaciones. Carga primero lo de prioridad **Alta**.")
    filas = estado_carga(conteo)
    df = pd.DataFrame([{
        "Estado": "Opcional" if f["recomendado"] == 0 else ("✅" if f["completo"] else "⬜"),
        "Categoría": f["categoria"],
        "Prioridad": f["prioridad"],
        "Cargados": f["cargados"],
        "Recomendado": f["recomendado"],
    } for f in filas])
    st.dataframe(df, hide_index=True, use_container_width=True)
    for clave, c in CATEGORIAS.items():
        with st.expander(f"{c['nombre']} · prioridad {c['prioridad']}"):
            st.markdown(f"**Qué cargar:** {c['descripcion']}\n\n**Ejemplos:** {c['ejemplos']}\n\n**Para qué sirve:** {c['por_que']}")
    st.subheader("Recomendaciones de los últimos análisis")
    guias = []
    if DIR_ANALISIS.exists():
        for ruta in sorted(DIR_ANALISIS.glob("*.json"), reverse=True)[:3]:
            a = json.loads(ruta.read_text(encoding="utf-8"))
            sec = a["resultado"].split("## 7.", 1)
            if len(sec) == 2:
                guias.append((a["pliego"], "## 7." + sec[1]))
    if guias:
        for nombre, texto in guias:
            with st.expander(f"Según el análisis de {nombre}"):
                st.markdown(texto)
    else:
        st.caption("Cuando analices una licitación, aquí aparecerá lo que faltó en la base para ese análisis.")
    st.subheader("Buenas prácticas")
    st.markdown("""
- Usa PDF con texto seleccionable; los escaneados deben pasar antes por OCR.
- Nombra los archivos con entidad, proceso y año (ej. `Alcaldia_Jamundi_CM-003-2025_observaciones.pdf`).
- Actualiza el RUP y los estados financieros cada vez que se renueven: las alertas dependen de ellos.
- Carga las respuestas de las entidades junto con tus observaciones: así el sistema sabe qué argumentos funcionaron.
""")

# ---------------- Analizar ----------------
with tab_analizar:
    st.header("Analizar una licitación")
    if not almacen.docs:
        st.warning("La base documental está vacía: el análisis no tendrá respaldo. Carga documentos primero.")
    pliego_archivo = st.file_uploader("Pliego de condiciones (y anexos en un solo archivo)", type=EXTENSIONES, key="pliego")
    notas = st.text_area("Indicaciones adicionales (opcional)",
                         placeholder="Ej.: enfócate en el equipo de trabajo; la fecha límite de observaciones es el 20 de noviembre.")
    if st.button("Analizar", type="primary", disabled=pliego_archivo is None):
        if not api_key:
            st.error("Falta la clave de API de Anthropic (barra lateral).")
            st.stop()
        paginas = extraer_texto(pliego_archivo.name, pliego_archivo.getvalue())
        if es_probablemente_escaneado(paginas):
            st.warning("El pliego parece escaneado y casi no tiene texto. Pásalo por OCR para un análisis confiable.")
        pliego_txt = texto_con_paginas(paginas)
        consultas = [f["texto"] for f in fragmentar(paginas)]
        n_emp = max(8, max_frag // 3)
        refs = (almacen.buscar_para_documento(consultas, CATS_OBSERVACIONES, maximo=max_frag - n_emp)
                + almacen.buscar_para_documento(consultas, CATS_EMPRESA, maximo=n_emp))
        st.caption(f"Pliego: {len(paginas)} páginas · {len(refs)} fragmentos de referencia recuperados.")
        with st.expander("Ver fragmentos de referencia usados"):
            for i, f in enumerate(refs, 1):
                pag = f", pág. {f['pagina']}" if f.get("pagina") else ""
                st.markdown(f"**[F{i}] {f['documento']}{pag}** · _{CATEGORIAS[f['categoria']]['nombre']}_")
                st.text(f["texto"][:600])
        mensajes = construir_mensajes_analisis(pliego_txt, refs, nombre_empresa, notas)
        try:
            with st.spinner("Analizando el pliego (puede tardar varios minutos)..."):
                resultado = st.write_stream(transmitir(api_key, mensajes, nombre_empresa, tipo, modelo, esfuerzo))
        except RuntimeError as e:
            st.error(str(e))
            st.stop()
        DIR_ANALISIS.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        registro = {"fecha": marca, "pliego": pliego_archivo.name, "resultado": resultado,
                    "fuentes": [{"n": i, "documento": f["documento"], "pagina": f.get("pagina")} for i, f in enumerate(refs, 1)]}
        (DIR_ANALISIS / f"{marca}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        st.session_state["ultimo"] = registro

    if "ultimo" in st.session_state:
        r = st.session_state["ultimo"]
        base = Path(r["pliego"]).stem
        c1, c2 = st.columns(2)
        c1.download_button("Descargar en Word", markdown_a_docx(r["resultado"], f"Observaciones – {r['pliego']}"),
                           file_name=f"Observaciones_{base}.docx")
        c2.download_button("Descargar en Markdown", r["resultado"], file_name=f"Observaciones_{base}.md")
        st.caption("Las observaciones deben revisarse por el área jurídica antes de radicarlas.")

# ---------------- Consultar ----------------
with tab_consultar:
    st.header("Consultar la base documental")
    pregunta = st.text_input("Pregunta", placeholder="¿Qué hemos observado antes sobre la experiencia del director de cuenta?")
    if st.button("Preguntar", disabled=not pregunta):
        if not api_key:
            st.error("Falta la clave de API de Anthropic (barra lateral).")
            st.stop()
        refs = [f for _, f in almacen.buscar(pregunta, k=15)]
        if not refs:
            st.info("No encontré nada relacionado en la base. Prueba otras palabras o carga más documentos.")
        else:
            try:
                st.write_stream(transmitir(api_key, construir_mensajes_consulta(pregunta, refs),
                                           nombre_empresa, tipo, modelo, "medium"))
            except RuntimeError as e:
                st.error(str(e))
            with st.expander("Fragmentos usados"):
                for i, f in enumerate(refs, 1):
                    st.markdown(f"**[F{i}] {f['documento']}**")
                    st.text(f["texto"][:500])

# ---------------- Historial ----------------
with tab_historial:
    st.header("Análisis anteriores")
    rutas = sorted(DIR_ANALISIS.glob("*.json"), reverse=True) if DIR_ANALISIS.exists() else []
    if not rutas:
        st.info("Aún no hay análisis guardados.")
    for ruta in rutas:
        a = json.loads(ruta.read_text(encoding="utf-8"))
        with st.expander(f"{a['fecha']} · {a['pliego']}"):
            st.markdown(a["resultado"])
            st.download_button("Descargar en Word", markdown_a_docx(a["resultado"], f"Observaciones – {a['pliego']}"),
                               file_name=f"Observaciones_{Path(a['pliego']).stem}.docx", key=f"dl-{ruta.stem}")
