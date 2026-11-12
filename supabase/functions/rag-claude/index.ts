// Edge Function: recibe el pliego (o una pregunta) y los fragmentos recuperados, llama a Claude
// y devuelve la respuesta como texto en streaming. La clave ANTHROPIC_API_KEY vive como secreto
// de Supabase y nunca llega al navegador.
import Anthropic from "npm:@anthropic-ai/sdk@^1.8";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const CATEGORIAS: Record<string, string> = {
  banco_observaciones: "Banco de observaciones propias",
  respuestas_entidades: "Respuestas de entidades y observaciones de terceros",
  pliegos_referencia: "Pliegos anteriores y adendas",
  datos_empresa: "Datos de la empresa",
  equipo: "Equipo de trabajo",
  experiencia: "Experiencia y certificados",
  normativa: "Normativa y guías",
  otros: "Otros documentos",
};

const SISTEMA = (empresa: string, tipo: string) => `Eres un analista experto en contratación estatal colombiana (SECOP II, Ley 80 de 1993, Ley 1150 de 2007, Decreto 1082 de 2015) especializado en procesos de intermediación de seguros y licitaciones públicas. Ayudas a ${empresa} (${tipo}) a preparar observaciones a pliegos de condiciones.

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
- Responde en español, en Markdown, con tono profesional y directo.`;

const INSTRUCCIONES = (empresa: string) => `Analiza el pliego y entrega, en este orden y con estos títulos:

## 1. Resumen del proceso
Entidad, número de proceso, objeto, modalidad, valor o presupuesto, plazo, cronograma y fecha límite para observaciones (si no aparece, dilo).

## 2. Alertas críticas para ${empresa}
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
Lista concreta de documentos que faltaron en la base para hacer este análisis más sólido, indicando en qué categoría cargarlos: ${Object.values(CATEGORIAS).join(", ")}.`;

type Fragmento = { documento: string; categoria: string; pagina: number | null; texto: string };

function formatearFragmentos(frags: Fragmento[]): string {
  if (!frags.length) return "(La base documental no devolvió fragmentos relevantes.)";
  return frags
    .map((f, i) => `[F${i + 1}] Documento: ${f.documento}${f.pagina ? `, pág. ${f.pagina}` : ""} | Categoría: ${CATEGORIAS[f.categoria] ?? f.categoria}\n${f.texto}`)
    .join("\n\n---\n\n");
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return new Response("Método no permitido", { status: 405, headers: CORS });

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  if (!apiKey) {
    return new Response("Falta el secreto ANTHROPIC_API_KEY en Supabase (Edge Functions > Secrets).", { status: 500, headers: CORS });
  }

  let body: {
    modo: "analisis" | "consulta"; pliego?: string; pregunta?: string; notas?: string;
    fragmentos: Fragmento[]; empresa?: string; tipo?: string; esfuerzo?: string; modelo?: string;
  };
  try {
    body = await req.json();
  } catch {
    return new Response("Cuerpo JSON inválido", { status: 400, headers: CORS });
  }

  const empresa = body.empresa?.trim() || "la empresa";
  const tipo = body.tipo || "Agencia de seguros";
  const esfuerzo = ["low", "medium", "high", "xhigh"].includes(body.esfuerzo ?? "") ? body.esfuerzo! : "medium";
  const refs = { type: "text" as const, text: `<fragmentos_de_referencia>\n${formatearFragmentos(body.fragmentos ?? [])}\n</fragmentos_de_referencia>` };

  let contenido;
  if (body.modo === "consulta") {
    contenido = [refs, { type: "text" as const, text: `Responde la pregunta usando solo los fragmentos y citándolos con [F#]. Si no alcanzan, dilo y sugiere qué documento cargar.\n\nPregunta: ${body.pregunta ?? ""}` }];
  } else {
    let instr = INSTRUCCIONES(empresa);
    if (body.notas?.trim()) instr += `\n\nIndicaciones adicionales del usuario: ${body.notas.trim()}`;
    contenido = [refs, { type: "text" as const, text: `<pliego>\n${body.pliego ?? ""}\n</pliego>` }, { type: "text" as const, text: instr }];
  }

  const client = new Anthropic({ apiKey, maxRetries: 2 });
  const encoder = new TextEncoder();

  const salida = new ReadableStream({
    async start(controller) {
      try {
        // Si el modelo declina por política de seguridad, el servidor reintenta con un modelo alterno.
        const stream = client.beta.messages.stream({
          model: body.modelo || "claude-opus-5-5",
          max_tokens: 32000,
          betas: ["server-side-fallback-2026-07-01"],
          fallbacks: "default",
          thinking: { type: "adaptive" },
          output_config: { effort: esfuerzo },
          system: SISTEMA(empresa, tipo),
          messages: [{ role: "user", content: contenido }],
        } as any);
        for await (const ev of stream) {
          if (ev.type === "content_block_delta" && ev.delta.type === "text_delta") {
            controller.enqueue(encoder.encode(ev.delta.text));
          }
        }
        const final = await stream.finalMessage();
        if (final.stop_reason === "refusal") {
          controller.enqueue(encoder.encode("\n\n> ⚠️ El modelo declinó completar la respuesta. Revisa el documento o reformula la solicitud."));
        } else if (final.stop_reason === "max_tokens") {
          controller.enqueue(encoder.encode("\n\n> ⚠️ La respuesta se cortó por longitud. Prueba con el pliego por capítulos."));
        }
      } catch (e) {
        let msg = "Error desconocido";
        if (e instanceof Anthropic.AuthenticationError) msg = "La clave ANTHROPIC_API_KEY guardada en Supabase no es válida.";
        else if (e instanceof Anthropic.RateLimitError) msg = "Se alcanzó el límite de uso de la API de Anthropic. Espera un momento.";
        else if (e instanceof Anthropic.APIError) msg = `Error de la API de Anthropic (${e.status}): ${e.message}`;
        else if (e instanceof Error) msg = e.message;
        controller.enqueue(encoder.encode(`\n\n> ❌ ${msg}`));
      } finally {
        controller.close();
      }
    },
  });

  return new Response(salida, { headers: { ...CORS, "Content-Type": "text/plain; charset=utf-8" } });
});
