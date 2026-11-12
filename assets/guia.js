export const CATEGORIAS = {
  banco_observaciones: { nombre: "Banco de observaciones propias", prioridad: "Alta", minimo: 3,
    descripcion: "Observaciones que tu empresa ya radicó a otros pliegos, prepliegos e informes de evaluación.",
    ejemplos: "Recopilaciones de observaciones, cartas radicadas en SECOP II, observaciones a informes de evaluación.",
    por_que: "Es la base principal: el sistema propone observaciones apoyándose en argumentos que ya usaste." },
  respuestas_entidades: { nombre: "Respuestas de entidades y observaciones de terceros", prioridad: "Alta", minimo: 3,
    descripcion: "Documentos de respuesta a observaciones publicados por las entidades, incluidas las de otros oferentes.",
    ejemplos: "Respuestas a observaciones de SECOP II, adendas que acogieron observaciones.",
    por_que: "Muestra qué argumentos aceptan o rechazan las entidades y cómo responden." },
  pliegos_referencia: { nombre: "Pliegos anteriores y adendas", prioridad: "Media", minimo: 3,
    descripcion: "Pliegos definitivos, proyectos de pliego y adendas de procesos similares.",
    ejemplos: "Pliegos de intermediación de seguros de otras entidades, estudios previos.",
    por_que: "Permite comparar requisitos y detectar exigencias fuera de lo usual o desproporcionadas." },
  datos_empresa: { nombre: "Datos de la empresa", prioridad: "Alta", minimo: 2,
    descripcion: "Documentos que prueban la capacidad jurídica, financiera y organizacional de tu empresa.",
    ejemplos: "RUP vigente, Certificado de Cámara de Comercio, estados financieros, ficha de información de la empresa.",
    por_que: "Con ellos el sistema alerta qué requisitos del pliego tu empresa NO cumpliría hoy." },
  equipo: { nombre: "Equipo de trabajo", prioridad: "Alta", minimo: 2,
    descripcion: "Hojas de vida y certificaciones laborales y académicas del personal que propondrías.",
    ejemplos: "Hojas de vida, diplomas, tarjetas profesionales, certificaciones laborales.",
    por_que: "El equipo suele ser lo más exigente del pliego; se cruza perfil por perfil." },
  experiencia: { nombre: "Experiencia y certificados", prioridad: "Media", minimo: 2,
    descripcion: "Certificados de experiencia, contratos ejecutados y certificados de siniestros atendidos.",
    ejemplos: "Certificaciones de clientes con primas, ramos y fechas; actas de liquidación.",
    por_que: "Permite verificar si la experiencia exigida (primas, ramos, número de contratos) se puede acreditar." },
  normativa: { nombre: "Normativa y guías", prioridad: "Baja", minimo: 1,
    descripcion: "Normas y guías de contratación estatal que quieras que el sistema use como sustento.",
    ejemplos: "Ley 80 de 1993, Ley 1150 de 2007, Decreto 1082 de 2015, guías de Colombia Compra Eficiente.",
    por_que: "Da sustento normativo; sin estos documentos el sistema no cita normas como verificadas." },
  otros: { nombre: "Otros documentos", prioridad: "Baja", minimo: 0,
    descripcion: "Cualquier otro documento útil (plantillas de carta, notas internas, conceptos jurídicos).",
    ejemplos: "Plantilla de carta de observaciones, conceptos del área jurídica.",
    por_que: "Contexto adicional." },
};

export const CATS_OBSERVACIONES = ["banco_observaciones", "respuestas_entidades", "pliegos_referencia", "normativa", "otros"];
export const CATS_EMPRESA = ["datos_empresa", "equipo", "experiencia"];
const ORDEN = { Alta: 0, Media: 1, Baja: 2 };
const PESO = { Alta: 3, Media: 2, Baja: 1 };

export function estadoCarga(conteo) {
  return Object.entries(CATEGORIAS).map(([clave, c]) => {
    const n = conteo[clave] || 0;
    return { clave, categoria: c.nombre, prioridad: c.prioridad, cargados: n, recomendado: c.minimo, completo: n >= c.minimo };
  });
}

export function siguientePaso(conteo) {
  const p = estadoCarga(conteo).filter((f) => !f.completo);
  p.sort((a, b) => ORDEN[a.prioridad] - ORDEN[b.prioridad] || (a.cargados - a.recomendado) - (b.cargados - b.recomendado));
  return p[0] || null;
}

export function cobertura(conteo) {
  const filas = estadoCarga(conteo).filter((f) => f.recomendado > 0);
  const total = filas.reduce((s, f) => s + PESO[f.prioridad], 0);
  const logrado = filas.reduce((s, f) => s + PESO[f.prioridad] * Math.min(1, f.cargados / f.recomendado), 0);
  return total ? Math.round((100 * logrado) / total) : 0;
}
