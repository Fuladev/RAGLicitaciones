import { SUPABASE_URL, SUPABASE_KEY, FUNCION_CLAUDE, BUCKET } from "./config.js";
import { CATEGORIAS, CATS_EMPRESA, CATS_OBSERVACIONES, estadoCarga, siguientePaso, cobertura } from "./guia.js";
import { extraerTexto, textoConPaginas, esEscaneado, fragmentar, sha1 } from "./extraer.js";

const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const md = (t) => DOMPurify.sanitize(marked.parse(t || ""));

let usuario = null;
let docs = [];
let ultimo = null;

// ---------------- Sesión ----------------
async function iniciar() {
  const { data } = await sb.auth.getSession();
  $("#cargando").hidden = true;
  if (data.session) await entrar(data.session.user);
  else $("#vista-login").hidden = false;
}

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").hidden = true;
  const { data, error } = await sb.auth.signInWithPassword({ email: $("#login-email").value.trim(), password: $("#login-clave").value });
  if (error) {
    $("#login-error").textContent = error.message === "Invalid login credentials" ? "Correo o contraseña incorrectos."
      : /fetch/i.test(error.message) ? "No hay conexión con el servidor. Revisa tu internet." : error.message;
    $("#login-error").hidden = false;
    return;
  }
  await entrar(data.user);
});

$("#btn-salir").addEventListener("click", async () => { await sb.auth.signOut(); location.reload(); });

async function entrar(user) {
  usuario = user;
  $("#vista-login").hidden = true;
  $("#vista-app").hidden = false;
  $("#usuario").textContent = user.email;
  await cargarConfig();
  await refrescarDocs();
  await cargarHistorial();
}

// ---------------- Configuración ----------------
async function cargarConfig() {
  const { data } = await sb.from("rag_config").select("empresa,tipo").maybeSingle();
  if (data) { $("#cfg-empresa").value = data.empresa; $("#cfg-tipo").value = data.tipo; }
  $("#cfg-esfuerzo").value = localStorage.getItem("rag-esfuerzo") || "medium";
  $("#cfg-frag").value = localStorage.getItem("rag-frag") || "50";
}
const guardarConfig = () => sb.from("rag_config").upsert({ user_id: usuario.id, empresa: $("#cfg-empresa").value.trim(), tipo: $("#cfg-tipo").value });
$("#cfg-empresa").addEventListener("change", guardarConfig);
$("#cfg-tipo").addEventListener("change", guardarConfig);
$("#cfg-esfuerzo").addEventListener("change", (e) => localStorage.setItem("rag-esfuerzo", e.target.value));
$("#cfg-frag").addEventListener("change", (e) => localStorage.setItem("rag-frag", e.target.value));
const nombreEmpresa = () => $("#cfg-empresa").value.trim() || "la empresa";

// ---------------- Pestañas ----------------
document.querySelectorAll(".pestanas button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".pestanas button").forEach((x) => x.classList.toggle("activa", x === b));
  document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== `tab-${b.dataset.tab}`));
}));

// ---------------- Base documental ----------------
const selCat = $("#base-categoria");
for (const [k, c] of Object.entries(CATEGORIAS)) selCat.add(new Option(c.nombre, k));
const describirCat = () => {
  const c = CATEGORIAS[selCat.value];
  $("#base-descripcion").innerHTML = `<strong>Qué es:</strong> ${esc(c.descripcion)}<br><strong>Ejemplos:</strong> ${esc(c.ejemplos)}`;
};
selCat.addEventListener("change", describirCat);
describirCat();
$("#base-archivos").addEventListener("change", (e) => ($("#btn-indexar").disabled = !e.target.files.length));

$("#btn-indexar").addEventListener("click", async () => {
  const archivos = [...$("#base-archivos").files];
  const cat = selCat.value;
  const prog = $("#base-progreso");
  prog.innerHTML = "";
  $("#btn-indexar").disabled = true;
  for (const a of archivos) {
    const linea = document.createElement("div");
    linea.className = "aviso info girando";
    linea.textContent = `${a.name}: procesando…`;
    prog.append(linea);
    try {
      linea.className = "aviso " + (await indexar(a, cat, linea));
    } catch (err) {
      linea.className = "aviso mal";
      linea.textContent = `${a.name}: no se pudo procesar (${err.message || err}).`;
    }
  }
  $("#base-archivos").value = "";
  await refrescarDocs();
});

async function indexar(archivo, cat, linea) {
  const hash = await sha1(archivo);
  if (docs.some((d) => d.hash === hash)) { linea.textContent = `${archivo.name}: ya estaba cargado.`; return "alerta"; }
  const paginas = await extraerTexto(archivo);
  const frags = fragmentar(paginas);
  const escaneado = esEscaneado(paginas);
  const ruta = `${usuario.id}/${cat}/${hash}-${archivo.name.replace(/[^\w.\-]+/g, "_")}`;
  const subida = await sb.storage.from(BUCKET).upload(ruta, archivo, { upsert: true });
  if (subida.error) throw subida.error;
  const { data: doc, error } = await sb.from("rag_documentos").insert({
    nombre: archivo.name, categoria: cat, hash, ruta_archivo: ruta, fragmentos: frags.length,
    caracteres: paginas.reduce((s, p) => s + p.texto.length, 0), escaneado,
  }).select().single();
  if (error) throw error;
  for (let i = 0; i < frags.length; i += 300) {
    const lote = frags.slice(i, i + 300).map((f) => ({ documento_id: doc.id, categoria: cat, documento: archivo.name, pagina: f.pagina, texto: f.texto }));
    const r = await sb.from("rag_fragmentos").insert(lote);
    if (r.error) { await sb.from("rag_documentos").delete().eq("id", doc.id); throw r.error; }
    linea.textContent = `${archivo.name}: indexando ${Math.min(i + 300, frags.length)}/${frags.length} fragmentos…`;
  }
  if (escaneado) { linea.textContent = `${archivo.name}: parece escaneado (casi sin texto). Pásalo por OCR y vuelve a cargarlo.`; return "alerta"; }
  linea.textContent = `${archivo.name}: ${frags.length} fragmentos indexados.`;
  return "ok";
}

async function refrescarDocs() {
  const { data, error } = await sb.from("rag_documentos").select("*").order("nombre");
  docs = error ? [] : data;
  const cont = $("#lista-docs");
  cont.innerHTML = docs.length ? "" : `<div class="aviso info">Todavía no hay documentos. Empieza por la <strong>Guía de carga</strong>.</div>`;
  for (const [k, c] of Object.entries(CATEGORIAS)) {
    const delCat = docs.filter((d) => d.categoria === k);
    if (!delCat.length) continue;
    const det = document.createElement("details");
    det.innerHTML = `<summary>${esc(c.nombre)} (${delCat.length})</summary>`;
    for (const d of delCat) {
      const fila = document.createElement("div");
      fila.className = "doc";
      fila.innerHTML = `<span><strong>${esc(d.nombre)}</strong> · ${d.fragmentos} fragmentos · ${new Date(d.created_at).toLocaleString("es-CO")}${d.escaneado ? " ⚠️ escaneado" : ""}</span>`;
      const b = document.createElement("button");
      b.textContent = "Eliminar";
      b.addEventListener("click", async () => {
        if (!confirm(`¿Eliminar ${d.nombre} de la base?`)) return;
        if (d.ruta_archivo) await sb.storage.from(BUCKET).remove([d.ruta_archivo]);
        await sb.from("rag_documentos").delete().eq("id", d.id);
        await refrescarDocs();
      });
      fila.append(b);
      det.append(fila);
    }
    cont.append(det);
  }
  actualizarGuia();
}

// ---------------- Guía ----------------
function actualizarGuia() {
  const conteo = {};
  for (const d of docs) conteo[d.categoria] = (conteo[d.categoria] || 0) + 1;
  $("#cobertura").textContent = `${cobertura(conteo)} %`;
  const sig = siguientePaso(conteo);
  $("#siguiente").className = "aviso " + (sig ? "info" : "ok");
  $("#siguiente").innerHTML = sig ? `<strong>Siguiente a cargar:</strong> ${esc(sig.categoria)} (${sig.cargados}/${sig.recomendado})`
    : "La base tiene lo mínimo recomendado en todas las categorías.";
  $("#guia-tabla").innerHTML = estadoCarga(conteo).map((f) => `<tr><td>${f.recomendado === 0 ? "Opcional" : f.completo ? "✅" : "⬜"}</td>
    <td>${esc(f.categoria)}</td><td>${f.prioridad}</td><td>${f.cargados}</td><td>${f.recomendado}</td></tr>`).join("");
  $("#guia-detalle").innerHTML = Object.values(CATEGORIAS).map((c) => `<details><summary>${esc(c.nombre)} · prioridad ${c.prioridad}</summary>
    <p><strong>Qué cargar:</strong> ${esc(c.descripcion)}</p><p><strong>Ejemplos:</strong> ${esc(c.ejemplos)}</p><p><strong>Para qué sirve:</strong> ${esc(c.por_que)}</p></details>`).join("");
  $("#aviso-base-vacia").hidden = docs.length > 0;
}

// ---------------- Llamada a Claude (Edge Function) ----------------
async function llamarClaude(cuerpo, destino) {
  const { data: { session } } = await sb.auth.getSession();
  const r = await fetch(FUNCION_CLAUDE, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.access_token}`, apikey: SUPABASE_KEY },
    body: JSON.stringify({ ...cuerpo, empresa: nombreEmpresa(), tipo: $("#cfg-tipo").value, esfuerzo: $("#cfg-esfuerzo").value }),
  });
  if (!r.ok) throw new Error((await r.text()) || `Error ${r.status}`);
  const lector = r.body.getReader();
  const dec = new TextDecoder();
  let texto = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    texto += dec.decode(value, { stream: true });
    destino.innerHTML = md(texto);
  }
  return texto;
}

function mostrarRefs(det, refs) {
  det.hidden = !refs.length;
  det.querySelector(".refs").innerHTML = refs.map((f, i) =>
    `<p><strong>[F${i + 1}] ${esc(f.documento)}${f.pagina ? `, pág. ${f.pagina}` : ""}</strong> · <em>${esc(CATEGORIAS[f.categoria]?.nombre ?? f.categoria)}</em></p><pre>${esc(f.texto.slice(0, 600))}</pre>`).join("");
}

// ---------------- Analizar ----------------
$("#pliego").addEventListener("change", (e) => ($("#btn-analizar").disabled = !e.target.files.length));

$("#btn-analizar").addEventListener("click", async () => {
  const archivo = $("#pliego").files[0];
  const estado = $("#estado-analisis");
  $("#btn-analizar").disabled = true;
  $("#descargas").hidden = true;
  $("#resultado").innerHTML = "";
  try {
    estado.className = "sutil girando";
    estado.textContent = "Leyendo el pliego…";
    const paginas = await extraerTexto(archivo);
    const avisoOcr = esEscaneado(paginas) ? " ⚠️ El pliego parece escaneado: pásalo por OCR para un análisis confiable." : "";
    const consultas = fragmentar(paginas).map((f) => f.texto);
    estado.textContent = "Buscando respaldo en la base documental…";
    const maxFrag = Math.max(10, Math.min(120, +$("#cfg-frag").value || 50));
    const nEmp = Math.max(8, Math.floor(maxFrag / 3));
    const [obs, emp] = await Promise.all([
      sb.rpc("rag_buscar", { consultas, categorias: CATS_OBSERVACIONES, k_por_consulta: 3, maximo: maxFrag - nEmp }),
      sb.rpc("rag_buscar", { consultas, categorias: CATS_EMPRESA, k_por_consulta: 3, maximo: nEmp }),
    ]);
    if (obs.error || emp.error) throw obs.error || emp.error;
    const refs = [...obs.data, ...emp.data];
    mostrarRefs($("#refs-analisis"), refs);
    estado.textContent = `Pliego: ${paginas.length} páginas · ${refs.length} fragmentos de referencia. Analizando con Claude (puede tardar unos minutos)…${avisoOcr}`;
    const resultado = await llamarClaude({ modo: "analisis", pliego: textoConPaginas(paginas), notas: $("#notas").value, fragmentos: refs }, $("#resultado"));
    estado.className = "sutil";
    estado.textContent = `Pliego: ${paginas.length} páginas · ${refs.length} fragmentos de referencia.${avisoOcr}`;
    const fuentes = refs.map((f, i) => ({ n: i + 1, documento: f.documento, pagina: f.pagina }));
    await sb.from("rag_analisis").insert({ pliego: archivo.name, resultado, fuentes });
    ultimo = { pliego: archivo.name, resultado };
    $("#descargas").hidden = false;
    await cargarHistorial();
  } catch (err) {
    estado.className = "aviso mal";
    estado.textContent = `No se pudo completar el análisis: ${err.message || err}`;
  } finally {
    $("#btn-analizar").disabled = false;
  }
});

function descargar(nombre, contenido, tipo) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([contenido], { type: tipo }));
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(a.href);
}
const base = (n) => n.replace(/\.[^.]+$/, "");
function descargarWord(pliego, resultado) {
  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8">
    <style>body{font-family:Arial;font-size:10pt} table{border-collapse:collapse} td,th{border:1px solid #999;padding:4px;vertical-align:top} th{background:#eee}</style></head>
    <body><h1>Observaciones – ${esc(pliego)}</h1>${md(resultado).replace(/(<(p|li|td)[^>]*>)([^<]*🟡)/g, '$1<span style="background:yellow">$3</span>')}</body></html>`;
  descargar(`Observaciones_${base(pliego)}.doc`, "﻿" + html, "application/msword");
}
$("#btn-word").addEventListener("click", () => descargarWord(ultimo.pliego, ultimo.resultado));
$("#btn-md").addEventListener("click", () => descargar(`Observaciones_${base(ultimo.pliego)}.md`, ultimo.resultado, "text/markdown"));

// ---------------- Consultar ----------------
$("#btn-preguntar").addEventListener("click", async () => {
  const pregunta = $("#pregunta").value.trim();
  if (!pregunta) return;
  const salida = $("#respuesta");
  salida.innerHTML = `<p class="sutil girando">Buscando…</p>`;
  try {
    const { data, error } = await sb.rpc("rag_buscar", { consultas: [pregunta], categorias: null, k_por_consulta: 15, maximo: 15 });
    if (error) throw error;
    mostrarRefs($("#refs-consulta"), data);
    if (!data.length) { salida.innerHTML = `<div class="aviso info">No encontré nada relacionado en la base. Prueba otras palabras o carga más documentos.</div>`; return; }
    await llamarClaude({ modo: "consulta", pregunta, fragmentos: data }, salida);
  } catch (err) {
    salida.innerHTML = `<div class="aviso mal">${esc(err.message || err)}</div>`;
  }
});
$("#pregunta").addEventListener("keydown", (e) => e.key === "Enter" && $("#btn-preguntar").click());

// ---------------- Historial ----------------
async function cargarHistorial() {
  const { data } = await sb.from("rag_analisis").select("id,pliego,resultado,created_at").order("created_at", { ascending: false }).limit(50);
  const lista = data || [];
  const cont = $("#lista-historial");
  cont.innerHTML = lista.length ? "" : `<div class="aviso info">Aún no hay análisis guardados.</div>`;
  for (const a of lista) {
    const det = document.createElement("details");
    det.innerHTML = `<summary>${new Date(a.created_at).toLocaleString("es-CO")} · ${esc(a.pliego)}</summary><div class="markdown">${md(a.resultado)}</div>`;
    const b = document.createElement("button");
    b.className = "secundario";
    b.textContent = "Descargar en Word";
    b.addEventListener("click", () => descargarWord(a.pliego, a.resultado));
    det.append(b);
    cont.append(det);
  }
  const guias = lista.slice(0, 3).map((a) => [a.pliego, a.resultado.split("## 7.")[1]]).filter(([, g]) => g);
  if (guias.length) $("#guia-analisis").innerHTML = guias.map(([p, g]) => `<details><summary>Según el análisis de ${esc(p)}</summary><div class="markdown">${md("## 7." + g)}</div></details>`).join("");
}

iniciar();
