// CENTRAL · carga de configuración y datos, más utilidades de consulta.

export const S = {
  portal: null,
  indicadores: {},
  registros: [],
  resumen: { cargas: [], errores: [] },
  seguimiento: [],
  generado: null,
  hayDemo: false,
  metasEjemplo: false,
};

async function json(url, defecto) {
  try {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    if (defecto !== undefined) return defecto;
    throw e;
  }
}

// ---------- sesión por perfil
// Los datos se publican cifrados por perfil (data/seguro/<perfil>.json, PBKDF2-SHA256 + AES-256-GCM).
// Se descifran aquí con la contraseña del perfil; sin ella el archivo no se puede leer.
const CLAVE_SESION = 'central.sesion.v1';

async function descifrar(sobre, clave) {
  const b = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(clave), 'PBKDF2', false, ['deriveKey']);
  const k = await crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: b(sobre.salt), iterations: sobre.iter },
    base, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  const plano = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: b(sobre.iv) }, k, b(sobre.ct));
  return JSON.parse(new TextDecoder().decode(plano));
}

// Configuración pública (sin datos): portal, indicadores y lista de perfiles.
export async function cargarBase() {
  const [portal, ind, perfiles] = await Promise.all([
    json('config/portal.json'), json('config/indicadores.json'), json('config/perfiles.json', { perfiles: [] }),
  ]);
  S.portalCompleto = portal;
  S.portal = portal;
  S.indicadores = Object.fromEntries(ind.indicadores.map(i => [i.id, i]));
  S.perfiles = perfiles.perfiles || [];
}

// Devuelve true si la contraseña es correcta y los datos quedaron cargados.
export async function iniciarSesion(perfilId, clave, recordar = true) {
  let sobre;
  try { sobre = await json(`data/seguro/${encodeURIComponent(perfilId)}.json`); } catch { throw new Error('No se encontraron los datos del perfil.'); }
  let paquete;
  try { paquete = await descifrar(sobre, clave); } catch { return false; }
  aplicarPaquete(paquete);
  if (recordar) { try { sessionStorage.setItem(CLAVE_SESION, JSON.stringify({ perfil: perfilId, clave })); } catch { /* sin almacenamiento */ } }
  return true;
}

// Reabre la sesión de esta pestaña (se borra al cerrar el navegador).
export async function restaurarSesion() {
  let ses = null;
  try { ses = JSON.parse(sessionStorage.getItem(CLAVE_SESION) || 'null'); } catch { /* sin almacenamiento */ }
  if (!ses) return false;
  try { return await iniciarSesion(ses.perfil, ses.clave); } catch { return false; }
}

export function cerrarSesion() {
  try { sessionStorage.removeItem(CLAVE_SESION); } catch { /* sin almacenamiento */ }
}

export const esAdmin = () => !!S.perfil?.admin;
const lineaPermitida = l => esAdmin() || (S.perfil?.lineas || []).includes(l);

function aplicarPaquete(paquete) {
  S.perfil = paquete.perfil;
  const cons = paquete.consolidado || { registros: [] };
  const resumen = paquete.resumen || { cargas: [], errores: [] };
  const seg = paquete.seguimiento || { acciones: [] };
  const validacion = paquete.validacion || null;
  // Las filas "(TOTAL)" resumen cada servicio como lo calcula su dashboard; se separan de las cuentas.
  S.totales = (cons.registros || []).filter(r => r.t);
  S.registros = (cons.registros || []).filter(r => !r.t);
  S.validacion = validacion;
  S.generado = cons.generado || null;
  S.hayDemo = !!cons.hay_datos_demo;
  S.metasEjemplo = !!cons.metas_son_ejemplo;
  S.resumen = resumen;
  S.seguimientoBase = seg.acciones || [];
  S.seguimiento = combinarSeguimiento(S.seguimientoBase, borradoresLocales());
}

// ---------- catálogo

export function unidades() {
  // Cada combinación empresa+país es una "unidad" navegable (Entel, Claro Ecuador, Claro México…).
  const out = [];
  for (const e of S.portal.empresas) {
    for (const p of e.paises) {
      // Un perfil de cuenta solo ve las empresas y dashboards que le corresponden.
      const dashboards = (p.dashboards || []).filter(d => lineaPermitida(d.id));
      if (!esAdmin() && !dashboards.length) continue;
      out.push({
        e: e.id, p: p.id, empresa: e, pais: { ...p, dashboards }, color: e.color,
        nombre: `${e.nombre} ${p.nombre}`,
        proximamente: p.estado === 'proximamente' || e.estado === 'proximamente',
      });
    }
  }
  return out;
}

// Servicios = dashboards de cada empresa/país (Inbound, Outbound...). Su id es el linea_id de los datos.
export function lineas() {
  return unidades().flatMap(u => u.pais.dashboards.map((d, k) => ({
    ...d, l: d.id, e: u.e, p: u.p, unidad: u, orden: k, servicio: d.servicio || d.nombre,
  })));
}
export const linea = l => lineas().find(x => x.l === l);
export const nombreLinea = l => linea(l)?.servicio ?? (l || '—');
export const esConteo = i => !!S.indicadores[i]?.conteo;

export const unidad = (e, p) => unidades().find(u => u.e === e && u.p === p);
export const empresasVisibles = () => S.portal.empresas.filter(e => unidades().some(u => u.e === e.id));
export const nombreEmpresa = e => S.portal.empresas.find(x => x.id === e)?.nombre ?? e;
export const nombrePais = (e, p) => S.portal.empresas.find(x => x.id === e)?.paises.find(x => x.id === p)?.nombre ?? p;
export const nombreIndicador = i => S.indicadores[i]?.nombre ?? i;
export const mayorMejor = i => (S.indicadores[i]?.sentido ?? 'mayor_mejor') === 'mayor_mejor';

// ---------- formato

const nf1 = new Intl.NumberFormat('es', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat('es', { maximumFractionDigits: 0 });

export function fmt(v, i) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const u = S.indicadores[i]?.unidad;
  if (u === '%') return `${nf1.format(v)}%`;
  if (u === 'seg') return `${nf0.format(v)} s`;
  if (u === 'n') return nf0.format(v);
  if (u === 'indice') return nf1.format(v);
  if (u === 'pts') return new Intl.NumberFormat('es', { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(v);
  return nf1.format(v);
}
export const fmtN = v => (v === null || v === undefined ? '—' : nf0.format(v));
export const fmtPct = v => (v === null || v === undefined || Number.isNaN(v) ? '—' : `${nf0.format(v)}%`);

const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
export function fmtPeriodo(per) {
  if (!per) return '—';
  const [a, m] = per.split('-');
  return `${MESES[+m - 1]} ${a}`;
}

// Brecha frente a la meta, con signo "positivo = mejor" sin importar el sentido del indicador.
export function brecha(r) {
  if (r.m === null || r.m === undefined) return null;
  return mayorMejor(r.i) ? r.v - r.m : r.m - r.v;
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------- consultas

// Mes que muestran por defecto los filtros: el mes en curso; si aún no tiene datos, el último mes disponible.
export function mesPorDefecto(pers) {
  const hoy = new Date().toISOString().slice(0, 7);
  if (pers.includes(hoy)) return hoy;
  return pers.filter(p => p < hoy).at(-1) || pers.at(-1) || '';
}

export function periodos(regs = S.registros) {
  return [...new Set(regs.map(r => r.per))].sort();
}

export function filtrar(regs, f = {}) {
  return regs.filter(r =>
    (!f.e || r.e === f.e) &&
    (!f.p || r.p === f.p) &&
    (!f.l || r.l === f.l) &&
    (!f.c || r.c === f.c) &&
    (!f.i || r.i === f.i) &&
    (!f.desde || r.per >= f.desde) &&
    (!f.hasta || r.per <= f.hasta) &&
    (!f.s || r.s === f.s));
}

// Última medición de cada empresa+país+cuenta+indicador.
export function ultimas(regs) {
  const m = new Map();
  for (const r of regs) {
    const k = `${r.e}|${r.p}|${r.l}|${r.c}|${r.i}`;
    if (!m.has(k) || m.get(k).per < r.per) m.set(k, r);
  }
  return [...m.values()];
}

// Cuántos periodos seguidos (hasta el último) lleva una serie sin cumplir la meta.
export function racha(regs, r) {
  const serie = regs.filter(x => x.e === r.e && x.p === r.p && x.l === r.l && x.c === r.c && x.i === r.i).sort((a, b) => b.per.localeCompare(a.per));
  let n = 0;
  for (const x of serie) { if (x.s === 'ALERTA' || x.s === 'CRITICO') n++; else break; }
  return n;
}

export function comparar(regs, perA, perB) {
  const idx = new Map();
  for (const r of regs) if (r.per === perA || r.per === perB) {
    const k = `${r.e}|${r.p}|${r.l}|${r.c}|${r.i}`;
    if (!idx.has(k)) idx.set(k, { e: r.e, p: r.p, l: r.l, c: r.c, i: r.i, a: null, b: null });
    idx.get(k)[r.per === perA ? 'a' : 'b'] = r;
  }
  return [...idx.values()].map(x => {
    const d = x.a && x.b ? x.b.v - x.a.v : null;
    return { ...x, delta: d, mejora: d === null ? null : (mayorMejor(x.i) ? d > 0 : d < 0) };
  });
}

// Promedio ponderado por muestras de un indicador (para resumir un servicio con varias cuentas).
export function ponderado(regs) {
  const conN = regs.filter(r => r.n);
  if (!conN.length) return regs.length ? regs.reduce((a, r) => a + r.v, 0) / regs.length : null;
  const n = conN.reduce((a, r) => a + r.n, 0);
  return conN.reduce((a, r) => a + r.v * r.n, 0) / n;
}

export function opciones(regs, campo) {
  return [...new Set(regs.map(r => r[campo]))].sort((a, b) => String(a).localeCompare(String(b), 'es'));
}

// ---------- seguimiento (observaciones y acciones)
// El archivo data/seguimiento.json es la fuente oficial (versionada en Git).
// Lo que se registra en el navegador queda como borrador local hasta exportarlo y subirlo al repositorio.

const claveBorradores = () => `central.seguimiento.borradores.v1.${S.perfil?.id || 'sin-perfil'}`;

export function borradoresLocales() {
  try { return JSON.parse(localStorage.getItem(claveBorradores()) || '[]'); } catch { return []; }
}

function guardarBorradores(lista) {
  try { localStorage.setItem(claveBorradores(), JSON.stringify(lista)); return true; } catch { return false; }
}

function combinarSeguimiento(base, locales) {
  const m = new Map(base.map(a => [a.id, { ...a, local: false }]));
  for (const a of locales) m.set(a.id, { ...a, local: true });
  return [...m.values()].sort((a, b) => (b.actualizado || '').localeCompare(a.actualizado || ''));
}

export function guardarAccion(accion) {
  const locales = borradoresLocales().filter(a => a.id !== accion.id);
  const ahora = new Date().toISOString().slice(0, 19);
  const a = { ...accion, id: accion.id || `seg-${Date.now().toString(36)}`, creado: accion.creado || ahora, actualizado: ahora };
  delete a.local;
  locales.push(a);
  const ok = guardarBorradores(locales);
  S.seguimiento = combinarSeguimiento(S.seguimientoBase, locales);
  return ok;
}

export function descartarBorradores() {
  guardarBorradores([]);
  S.seguimiento = combinarSeguimiento(S.seguimientoBase, []);
}

export function exportarSeguimiento() {
  const acciones = S.seguimiento.map(({ local, ...a }) => a);
  descargar(`seguimiento_${S.perfil?.id || 'perfil'}_${new Date().toISOString().slice(0, 10)}.json`,
    JSON.stringify({ version: 1, perfil: S.perfil?.id, acciones }, null, 2), 'application/json');
}

export function descargar(nombre, contenido, tipo) {
  const url = URL.createObjectURL(new Blob([contenido], { type: tipo }));
  const a = Object.assign(document.createElement('a'), { href: url, download: nombre });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function aCSV(filas, columnas) {
  const q = v => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return '﻿' + [columnas.map(c => q(c.titulo)).join(';'), ...filas.map(f => columnas.map(c => q(c.csv ? c.csv(f) : f[c.id])).join(';'))].join('\n');
}
