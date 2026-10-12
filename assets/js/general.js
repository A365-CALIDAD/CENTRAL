// CENTRAL · Vista general (todos los servicios en una pantalla) y visor de dashboards embebidos.
import {
  S, esc, fmt, fmtN, fmtPeriodo, periodos, unidades, lineas, linea, esConteo, ponderado,
  nombreIndicador, descargar, aCSV,
} from './datos.js';
import { kpi } from './componentes.js';

const CONTEOS = [['evaluaciones', 'Evaluaciones'], ['encuestas', 'Encuestas']];
const suma = regs => regs.reduce((a, r) => a + r.v, 0);
const colorEstado = s => ({ OK: 'var(--good)', ALERTA: 'var(--warning)', CRITICO: 'var(--critical)' }[s] || 'var(--axis)');

let mesEnCurso = false;   // las variaciones contra el mes anterior no tienen sentido con un mes parcial

function variacion(actual, previo) {
  if (mesEnCurso) return '<span class="det">parcial</span>';
  if (!previo || actual === null) return '';
  const d = ((actual - previo) / previo) * 100;
  if (Math.abs(d) < 0.5) return '<span class="det">= mes anterior</span>';
  return `<span class="det">${d > 0 ? '▲' : '▼'} ${Math.abs(d).toFixed(0)}% vs mes anterior</span>`;
}

function avisos() {
  const out = [];
  if (!S.registros.length) out.push('<div class="aviso">Aún no hay mediciones publicadas. Ejecute <code>python etl/central_etl.py procesar</code>.</div>');
  if (S.hayDemo) out.push('<div class="aviso"><b>Datos de demostración.</b> Hay fuentes <code>demo_*</code> activas.</div>');
  return out.join('');
}

// ===================================================================== VISTA GENERAL

export function general(cont) {
  const pers = periodos();
  const hoy = new Date().toISOString().slice(0, 7);
  // Por defecto el último mes completo: el mes en curso tiene cifras parciales.
  const ultimoCompleto = pers.filter(x => x < hoy).at(-1);
  const estado = { per: ultimoCompleto || pers.at(-1) || '', e: '' };

  const pintar = () => {
    const { per, e } = estado;
    mesEnCurso = per === hoy;
    const iPer = pers.indexOf(per);
    const perAnt = iPer > 0 ? pers[iPer - 1] : null;
    const srv = lineas().filter(x => !e || x.e === e);
    const unis = unidades().filter(u => !e || u.e === e);
    const delPer = S.registros.filter(r => r.per === per && (!e || r.e === e));
    const delAnt = S.registros.filter(r => r.per === perAnt && (!e || r.e === e));
    const evaluaciones = suma(delPer.filter(r => r.i === 'evaluaciones'));
    const encuestas = suma(delPer.filter(r => r.i === 'encuestas'));
    const conDatos = new Set(delPer.map(r => r.l)).size;
    const riesgo = delPer.filter(r => !esConteo(r.i) && (r.s === 'ALERTA' || r.s === 'CRITICO')).length;

    cont.innerHTML = `${avisos()}
      <div class="tarjeta filtros" style="margin-bottom:16px">
        <div class="campo"><label for="g-per">Mes</label><select id="g-per">${pers.slice().reverse().map(x =>
          `<option value="${x}" ${x === per ? 'selected' : ''}>${fmtPeriodo(x)}${x === hoy ? ' (en curso)' : ''}</option>`).join('')}</select></div>
        <div class="campo"><label for="g-emp">Empresa</label><select id="g-emp"><option value="">Todas</option>${S.portal.empresas.map(x =>
          `<option value="${x.id}" ${x.id === e ? 'selected' : ''}>${esc(x.nombre)}</option>`).join('')}</select></div>
        <div class="acciones"><a class="btn" href="#/ver">Ver dashboards</a></div>
      </div>
      <div class="grid g-kpi">
        ${kpi({ etiqueta: 'Evaluaciones de calidad', valor: fmtN(evaluaciones), detalle: `${fmtPeriodo(per)} ${variacion(evaluaciones, suma(delAnt.filter(r => r.i === 'evaluaciones')))}` })}
        ${kpi({ etiqueta: 'Encuestas de clientes', valor: fmtN(encuestas), detalle: `${fmtPeriodo(per)} ${variacion(encuestas, suma(delAnt.filter(r => r.i === 'encuestas')))}` })}
        ${kpi({ etiqueta: 'Servicios con datos', valor: `${conDatos} de ${srv.length}`, detalle: 'Servicios con mediciones en el mes' })}
        ${kpi({ etiqueta: 'Indicadores bajo meta', valor: fmtN(riesgo), detalle: 'Cuenta e indicador en alerta o crítico', clase: riesgo ? 'critico' : '' })}
      </div>
      ${per === hoy ? '<div class="aviso">El mes seleccionado está en curso: las cantidades seguirán aumentando.</div>' : ''}
      <p class="sub">En cada servicio, el punto de color indica el peor estado entre sus cuentas (verde: todas cumplen · amarillo: alguna en alerta · rojo: alguna crítica · gris: sin meta) y "x/y cumplen" cuántas cuentas alcanzan la meta.</p>
      ${unis.map(u => `
        <div class="cabecera" style="margin-top:8px"><div><h2 style="font-size:16px">${esc(u.nombre)}</h2></div>
          ${u.proximamente ? '<span class="pendiente">Próximamente</span>' : `<a class="btn chico" href="#/empresa/${u.e}/${u.p}">Detalle por cuenta</a>`}</div>
        ${u.proximamente ? '' : `<div class="grid g-srv">${srv.filter(x => x.e === u.e && x.p === u.p).map(x => tarjetaServicio(x, delPer, delAnt)).join('')}</div>`}
      `).join('')}
      <div class="tarjeta" style="margin-top:20px">
        <div class="cabecera"><div><h2>Evaluaciones por servicio y mes</h2>
          <p class="sub" style="margin:0">Cantidad de monitoreos de calidad y de encuestas de clientes registrados en cada base</p></div>
          <button class="btn" id="g-csv">Exportar CSV</button></div>
        <div id="g-tabla"></div>
      </div>`;

    pintarTablaEvaluaciones(cont.querySelector('#g-tabla'), srv, hoy);
    cont.querySelector('#g-per').addEventListener('change', ev => { estado.per = ev.target.value; pintar(); });
    cont.querySelector('#g-emp').addEventListener('change', ev => { estado.e = ev.target.value; pintar(); });
    cont.querySelector('#g-csv').addEventListener('click', () => {
      const { filas, meses } = matrizEvaluaciones(srv);
      const cols = [
        { id: 'empresa', titulo: 'Empresa' }, { id: 'servicio', titulo: 'Servicio' }, { id: 'tipo', titulo: 'Tipo' },
        ...meses.map(m => ({ id: m, titulo: m, csv: f => f.meses[m] ?? '' })), { id: 'total', titulo: 'Total' },
      ];
      descargar(`central_evaluaciones_${new Date().toISOString().slice(0, 10)}.csv`, aCSV(filas, cols), 'text/csv;charset=utf-8');
    });
  };
  pintar();
}

function tarjetaServicio(x, delPer, delAnt) {
  const regs = delPer.filter(r => r.l === x.l);
  const ant = delAnt.filter(r => r.l === x.l);
  const conteos = CONTEOS.map(([id, nombre]) => {
    const r = regs.filter(z => z.i === id);
    return r.length ? { id, nombre, v: suma(r), ant: suma(ant.filter(z => z.i === id)) } : null;
  }).filter(Boolean);
  const principal = conteos[0];
  const inds = Object.keys(S.indicadores).filter(i => !esConteo(i) && regs.some(r => r.i === i)).map(i => {
    const r = regs.filter(z => z.i === i);
    const conMeta = r.filter(z => z.s !== 'SIN_META');
    const ok = conMeta.filter(z => z.s === 'OK').length;
    const peor = ['CRITICO', 'ALERTA', 'OK'].find(s => conMeta.some(z => z.s === s)) || 'SIN_META';
    return { i, v: ponderado(r), cuentas: r.length, ok, conMeta: conMeta.length, peor };
  });
  const tieneFuente = S.registros.some(r => r.l === x.l);
  return `<div class="tarjeta srv">
    <div class="srv-top">
      <div><h3>${esc(x.servicio)}</h3><small>${esc(x.unidad.nombre)}</small></div>
      ${!tieneFuente ? '<span class="pendiente">Sin base conectada</span>' : !regs.length ? '<span class="pendiente">Sin datos en el mes</span>' : ''}
    </div>
    ${principal ? `<div class="srv-num"><b>${fmtN(principal.v)}</b> ${principal.nombre.toLowerCase()}
        ${variacion(principal.v, principal.ant)}</div>
      ${conteos.slice(1).map(c => `<div class="srv-sub">${fmtN(c.v)} ${c.nombre.toLowerCase()}</div>`).join('')}` : '<div class="srv-num"><b>—</b></div>'}
    ${inds.length ? `<ul class="srv-inds">${inds.map(d => `<li title="${d.conMeta ? `${d.ok} de ${d.conMeta} cuentas cumplen la meta` : 'Sin meta configurada'}">
        <span class="p" style="background:${colorEstado(d.peor)}"></span><span class="n">${esc(nombreIndicador(d.i))}</span>
        <span class="v">${fmt(d.v, d.i)}</span><span class="c">${d.conMeta ? `${d.ok}/${d.conMeta} cumplen` : `${d.cuentas} cuenta${d.cuentas > 1 ? 's' : ''}`}</span></li>`).join('')}</ul>` : ''}
    <div class="acc">
      ${x.url ? `<a class="btn primario chico" href="#/ver/${esc(x.id)}">Ver dashboard</a><a class="btn chico" href="${esc(x.url)}" target="_blank" rel="noopener">Abrir ↗</a>`
        : '<span class="pendiente">Visualización pendiente</span>'}
    </div>
  </div>`;
}

function matrizEvaluaciones(srv) {
  const meses = periodos(S.registros.filter(r => esConteo(r.i))).slice(-12);
  const filas = [];
  for (const x of srv) {
    for (const [id, nombre] of CONTEOS) {
      const r = S.registros.filter(z => z.l === x.l && z.i === id);
      if (!r.length) continue;
      const porMes = Object.fromEntries(meses.map(m => [m, suma(r.filter(z => z.per === m)) || null]));
      filas.push({ empresa: x.unidad.nombre, servicio: x.servicio, tipo: nombre, l: x.l, meses: porMes,
        total: Object.values(porMes).reduce((a, v) => a + (v || 0), 0) });
    }
  }
  return { filas, meses };
}

function pintarTablaEvaluaciones(cont, srv, hoy) {
  const { filas, meses } = matrizEvaluaciones(srv);
  if (!filas.length) { cont.innerHTML = '<div class="vacio">Sin conteos de evaluaciones.</div>'; return; }
  const totales = CONTEOS.map(([, nombre]) => {
    const f = filas.filter(x => x.tipo === nombre);
    return f.length ? { tipo: nombre, meses: Object.fromEntries(meses.map(m => [m, f.reduce((a, x) => a + (x.meses[m] || 0), 0)])), total: f.reduce((a, x) => a + x.total, 0) } : null;
  }).filter(Boolean);
  const celda = v => `<td class="num">${v ? fmtN(v) : '<span style="color:var(--muted)">—</span>'}</td>`;
  cont.innerHTML = `<div class="tabla-wrap"><table class="tabla-eval">
    <thead><tr><th>Empresa</th><th>Servicio</th><th>Tipo</th>${meses.map(m => `<th class="num">${fmtPeriodo(m)}${m === hoy ? '*' : ''}</th>`).join('')}<th class="num">Total</th></tr></thead>
    <tbody>${filas.map(f => `<tr><td>${esc(f.empresa)}</td><td><b>${esc(f.servicio)}</b></td><td>${esc(f.tipo)}</td>
      ${meses.map(m => celda(f.meses[m])).join('')}<td class="num"><b>${fmtN(f.total)}</b></td></tr>`).join('')}</tbody>
    <tfoot>${totales.map(t => `<tr><td colspan="3"><b>Total ${t.tipo.toLowerCase()}</b></td>${meses.map(m => `<td class="num"><b>${fmtN(t.meses[m])}</b></td>`).join('')}<td class="num"><b>${fmtN(t.total)}</b></td></tr>`).join('')}</tfoot>
  </table></div>
  ${meses.includes(hoy) ? '<p class="sub" style="margin-top:8px">* Mes en curso.</p>' : ''}`;
}

// ===================================================================== VISOR DE DASHBOARDS

export function visor(cont, [id]) {
  const todos = lineas();
  const actual = linea(id) || todos.find(x => x.url);
  cont.innerHTML = `
    <div class="tarjeta visor-tabs">
      ${unidades().filter(u => !u.proximamente).map(u => `<div class="grupo"><span class="g">${esc(u.nombre)}</span>
        ${todos.filter(x => x.e === u.e && x.p === u.p).map(x => x.url
          ? `<a class="tab ${x.l === actual?.l ? 'activo' : ''}" href="#/ver/${esc(x.id)}">${esc(x.servicio)}</a>`
          : `<span class="tab deshabilitado" title="Visualización pendiente en config/portal.json">${esc(x.servicio)}</span>`).join('')}</div>`).join('')}
    </div>
    ${actual?.url ? `
      <div class="visor-barra"><b>${esc(actual.unidad.nombre)} · ${esc(actual.servicio)}</b>
        <span style="flex:1"></span>
        <a class="btn chico" href="${esc(actual.url)}" target="_blank" rel="noopener">Abrir en pestaña nueva ↗</a>
        ${actual.repo ? `<a class="btn chico" href="${esc(actual.repo)}" target="_blank" rel="noopener">Repositorio</a>` : ''}</div>
      <iframe class="visor" src="${esc(actual.url)}" title="Dashboard ${esc(actual.servicio)}" loading="lazy" referrerpolicy="no-referrer"></iframe>
      <p class="sub">Si el dashboard no se muestra, ábrelo en una pestaña nueva (algunos sitios no permiten mostrarse dentro de otra página o requieren iniciar sesión).</p>`
      : '<div class="vacio">Ningún dashboard tiene URL de visualización configurada.</div>'}`;
}
