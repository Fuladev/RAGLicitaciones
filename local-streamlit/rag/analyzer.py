"""Análisis de licitaciones con Claude apoyado en los documentos recuperados."""
from collections.abc import Iterator

import anthropic

from .guia import CATEGORIAS

MODELO_POR_DEFECTO = "claude-opus-5-5"

CATS_OBSERVACIONES = ["banco_observaciones", "respuestas_entidades", "pliegos_referencia", "normativa", "otros"]
CATS_EMPRESA = ["datos_empresa", "equipo", "experiencia"]

SISTEMA = """Eres un analista experto en contratación estatal colombiana (SECOP II, Ley 80 de 1993, Ley 1150 de 2007, \
Decreto 1082 de 2015) especializado en procesos de intermediación de seguros y licitaciones públicas. Ayudas a {empresa} \
({tipo}) a preparar observaciones a pliegos de condiciones.

Trabajas SOLO con dos fuentes:
1. El PLIEGO que el usuario envía (con marcas [pág. N]).
2. Los FRAGMENTOS DE REFERENCIA recuperados de la base documental de la empresa, numerados [F1], [F2], ...

Reglas:
- Cita siempre numeral y página del pliego ("pág. 15, num. 3.2") y el fragmento de referencia que respalda cada observación ([F3]).
- No inventes respaldo: si una observación no tiene precedente en los fragmentos, márcala con 🟡 y descríbela como punto a estudiar, sin redacción definitiva.
- Distingue observaciones propias de la empresa de observaciones de terceros (otros oferentes) que aparezcan en las respuestas de entidades.
- Si un fragmento incluye la respuesta de una entidad a una observación parecida, inclúyela: indica si fue acogida o rechazada.
- No cites normas que no estén en el pliego ni en los fragmentos sin aclarar "(norma no verificada en la base documental)".
- Los incumplimientos de la empresa son información interna: nunca los incluyas dentro del texto de las observaciones.
- Si un requisito favorece a la empresa, no propongas observarlo; avísalo.
- Si el pliego parece escaneado o incompleto, dilo. Si falta la fecha límite de observaciones, pídela; no la inventes.
- Responde en español, en Markdown, con tono profesional y directo."""

INSTRUCCIONES = """Analiza el pliego y entrega, en este orden y con estos títulos:

## 1. Resumen del proceso
Entidad, número de proceso, objeto, modalidad, valor o presupuesto, plazo, cronograma y fecha límite para observaciones (si no aparece, dilo).

## 2. Alertas críticas para {empresa}
Requisitos que la empresa NO cumpliría o podría no cumplir según los documentos de la empresa recuperados (domicilio, indicadores financieros, experiencia, equipo, documentos exigidos). Si no hay documentos de la empresa suficientes para verificar algo, dilo explícitamente.

## 3. Observaciones propuestas
Una tabla con columnas: N.° | Apartado (num./pág.) | Problema | Observación propuesta | Respaldo en la base ([F#]) | Respuesta de entidades en casos similares | Similitud (IGUAL / SIMILAR / 🟡 SIN PRECEDENTE).
Después de la tabla, redacta el texto completo de cada observación con respaldo, con el formato:
### OBSERVACIÓN No. X – <título>
**El pliego establece (pág. N):** "<cita breve>"
**Argumento:** ...
**Solicitud:** ...

## 4. Equipo de trabajo y experiencia
Tabla: Perfil o requisito | Exigencia del pliego (pág.) | Documento disponible en la base | Brecha.

## 5. Puntos 🟡 para estudio
Ambigüedades o requisitos sin precedente en la base que requieren decisión del usuario.

## 6. Observaciones que NO conviene hacer
Las que el pliego ya resolvió o que favorecen a la empresa.

## 7. Guía: información que conviene cargar
Lista concreta de documentos que faltaron en la base para hacer este análisis más sólido (por ejemplo: "certificado de experiencia con primas del ramo X", "respuestas de la entidad Y a observaciones de procesos anteriores"), indicando en qué categoría cargarlos: {categorias}."""


def _formatear_fragmentos(fragmentos: list[dict]) -> str:
    bloques = []
    for i, f in enumerate(fragmentos, 1):
        cat = CATEGORIAS.get(f["categoria"], {}).get("nombre", f["categoria"])
        pag = f", pág. {f['pagina']}" if f.get("pagina") else ""
        bloques.append(f"[F{i}] Documento: {f['documento']}{pag} | Categoría: {cat}\n{f['texto']}")
    return "\n\n---\n\n".join(bloques) if bloques else "(La base documental no devolvió fragmentos relevantes.)"


def construir_mensajes_analisis(pliego: str, fragmentos: list[dict], empresa: str, notas: str = "") -> list[dict]:
    lista_cats = ", ".join(c["nombre"] for c in CATEGORIAS.values())
    contenido = [
        {"type": "text", "text": f"<fragmentos_de_referencia>\n{_formatear_fragmentos(fragmentos)}\n</fragmentos_de_referencia>"},
        {"type": "text", "text": f"<pliego>\n{pliego}\n</pliego>"},
    ]
    texto = INSTRUCCIONES.format(empresa=empresa, categorias=lista_cats)
    if notas.strip():
        texto += f"\n\nIndicaciones adicionales del usuario: {notas.strip()}"
    contenido.append({"type": "text", "text": texto})
    return [{"role": "user", "content": contenido}]


def construir_mensajes_consulta(pregunta: str, fragmentos: list[dict]) -> list[dict]:
    return [{"role": "user", "content": [
        {"type": "text", "text": f"<fragmentos_de_referencia>\n{_formatear_fragmentos(fragmentos)}\n</fragmentos_de_referencia>"},
        {"type": "text", "text": f"Responde la pregunta usando solo los fragmentos y citándolos con [F#]. "
                                 f"Si no alcanzan, dilo y sugiere qué documento cargar.\n\nPregunta: {pregunta}"},
    ]}]


def transmitir(api_key: str, mensajes: list[dict], empresa: str, tipo: str,
               modelo: str = MODELO_POR_DEFECTO, esfuerzo: str = "high") -> Iterator[str]:
    """Llama a Claude en streaming y va devolviendo el texto. Lanza RuntimeError con un mensaje legible si falla."""
    cliente = anthropic.Anthropic(api_key=api_key or None, timeout=1800, max_retries=3)
    parametros = dict(
        model=modelo,
        max_tokens=64000,
        system=SISTEMA.format(empresa=empresa, tipo=tipo),
        messages=mensajes,
        thinking={"type": "adaptive"},
        output_config={"effort": esfuerzo},
    )
    try:
        # Si el modelo rechaza por política de seguridad, el servidor reintenta con un modelo alterno.
        with cliente.beta.messages.stream(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **parametros
        ) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\n> ⚠️ El modelo declinó completar la respuesta. Revisa el documento o reformula la solicitud."
        elif final.stop_reason == "max_tokens":
            yield "\n\n> ⚠️ La respuesta se cortó por longitud. Prueba con un pliego más corto o por capítulos."
    except anthropic.AuthenticationError:
        raise RuntimeError("La clave de API de Anthropic no es válida. Revísala en la barra lateral.")
    except anthropic.PermissionDeniedError:
        raise RuntimeError("La clave de API no tiene permiso para usar este modelo.")
    except anthropic.RateLimitError:
        raise RuntimeError("Se alcanzó el límite de uso de la API. Espera un momento y vuelve a intentar.")
    except anthropic.BadRequestError as e:
        raise RuntimeError(f"Solicitud rechazada por la API: {e.message}")
    except anthropic.APIConnectionError:
        raise RuntimeError("No hay conexión con la API de Anthropic. Revisa tu internet.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Error de la API ({e.status_code}): {e.message}")
