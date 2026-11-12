"""Categorías de documentos de referencia y guía de carga."""

CATEGORIAS = {
    "banco_observaciones": {
        "nombre": "Banco de observaciones propias",
        "prioridad": "Alta",
        "minimo": 3,
        "descripcion": "Observaciones que tu empresa ya radicó a otros pliegos, prepliegos e informes de evaluación.",
        "ejemplos": "Recopilaciones de observaciones, cartas radicadas en SECOP II, observaciones a informes de evaluación.",
        "por_que": "Es la base principal: el sistema propone observaciones apoyándose en argumentos que ya usaste.",
    },
    "respuestas_entidades": {
        "nombre": "Respuestas de entidades y observaciones de terceros",
        "prioridad": "Alta",
        "minimo": 3,
        "descripcion": "Documentos de respuesta a observaciones publicados por las entidades, incluidas las de otros oferentes.",
        "ejemplos": "Respuestas a observaciones de SECOP II, adendas que acogieron observaciones.",
        "por_que": "Muestra qué argumentos aceptan o rechazan las entidades y cómo responden.",
    },
    "pliegos_referencia": {
        "nombre": "Pliegos anteriores y adendas",
        "prioridad": "Media",
        "minimo": 3,
        "descripcion": "Pliegos definitivos, proyectos de pliego y adendas de procesos similares.",
        "ejemplos": "Pliegos de intermediación de seguros de otras entidades, estudios previos.",
        "por_que": "Permite comparar requisitos y detectar exigencias fuera de lo usual o desproporcionadas.",
    },
    "datos_empresa": {
        "nombre": "Datos de la empresa",
        "prioridad": "Alta",
        "minimo": 2,
        "descripcion": "Documentos que prueban la capacidad jurídica, financiera y organizacional de tu empresa.",
        "ejemplos": "RUP vigente, Certificado de Cámara de Comercio, estados financieros, ficha de información de la empresa.",
        "por_que": "Con ellos el sistema alerta qué requisitos del pliego tu empresa NO cumpliría hoy.",
    },
    "equipo": {
        "nombre": "Equipo de trabajo",
        "prioridad": "Alta",
        "minimo": 2,
        "descripcion": "Hojas de vida y certificaciones laborales y académicas del personal que propondrías.",
        "ejemplos": "Hojas de vida, diplomas, tarjetas profesionales, certificaciones laborales.",
        "por_que": "El equipo suele ser lo más exigente del pliego; se cruza perfil por perfil.",
    },
    "experiencia": {
        "nombre": "Experiencia y certificados",
        "prioridad": "Media",
        "minimo": 2,
        "descripcion": "Certificados de experiencia, contratos ejecutados y certificados de siniestros atendidos.",
        "ejemplos": "Certificaciones de clientes con primas, ramos y fechas; actas de liquidación.",
        "por_que": "Permite verificar si la experiencia exigida (primas, ramos, número de contratos) se puede acreditar.",
    },
    "normativa": {
        "nombre": "Normativa y guías",
        "prioridad": "Baja",
        "minimo": 1,
        "descripcion": "Normas y guías de contratación estatal que quieras que el sistema use como sustento.",
        "ejemplos": "Ley 80 de 1993, Ley 1150 de 2007, Decreto 1082 de 2015, guías de Colombia Compra Eficiente.",
        "por_que": "Da sustento normativo a las observaciones; sin estos documentos el sistema no cita normas como verificadas.",
    },
    "otros": {
        "nombre": "Otros documentos",
        "prioridad": "Baja",
        "minimo": 0,
        "descripcion": "Cualquier otro documento útil (plantillas de carta, notas internas, conceptos jurídicos).",
        "ejemplos": "Plantilla de carta de observaciones, conceptos del área jurídica.",
        "por_que": "Contexto adicional.",
    },
}

ORDEN_PRIORIDAD = {"Alta": 0, "Media": 1, "Baja": 2}


def estado_carga(conteo_por_categoria: dict) -> list[dict]:
    """Devuelve, por categoría, cuántos documentos hay y si se alcanza el mínimo recomendado."""
    filas = []
    for clave, cat in CATEGORIAS.items():
        n = conteo_por_categoria.get(clave, 0)
        filas.append({
            "clave": clave,
            "categoria": cat["nombre"],
            "prioridad": cat["prioridad"],
            "cargados": n,
            "recomendado": cat["minimo"],
            "completo": n >= cat["minimo"],
        })
    return filas


def siguiente_paso(conteo_por_categoria: dict) -> dict | None:
    """La categoría incompleta de mayor prioridad: lo próximo que conviene cargar."""
    pendientes = [f for f in estado_carga(conteo_por_categoria) if not f["completo"]]
    if not pendientes:
        return None
    pendientes.sort(key=lambda f: (ORDEN_PRIORIDAD[f["prioridad"]], f["cargados"] - f["recomendado"]))
    return pendientes[0]


def porcentaje_cobertura(conteo_por_categoria: dict) -> int:
    filas = [f for f in estado_carga(conteo_por_categoria) if f["recomendado"] > 0]
    peso = {"Alta": 3, "Media": 2, "Baja": 1}
    total = sum(peso[f["prioridad"]] for f in filas)
    logrado = sum(peso[f["prioridad"]] * min(1, f["cargados"] / f["recomendado"]) for f in filas)
    return round(100 * logrado / total) if total else 0
