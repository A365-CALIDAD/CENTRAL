// CENTRAL · Vista general (todos los servicios en una pantalla) y visor de dashboards embebidos.
import {
  S, esc, fmt, fmtN, fmtPeriodo, periodos, unidades, lineas, linea, esConteo, ponderado,
  nombreIndicador, descargar, aCSV, mayorMejor,
} from './datos.js';
import { kpi, tabla, graficoLineas, leyenda, serie, css, destruirGraficos, ETIQUETA_ESTADO } from './componentes.js';

// Orden de los indicadores en el resumen y en la página de cada cuenta
const ORDEN = ['evaluaciones', 'encuestas', 'calidad', 'epa', 'fcr', 'efectividad', 'pec', 'penc', 'adherencia', 'global'];
const hoyMes = () => new Date().toISOString().slice(0, 7);
const totalDe = (l, i, per) => S.totales.find(z => z.l === l && z.i === i && z.per === per);

// Flecha de tendencia contra el mes anterior: verde si mejora, rojo si empeora (los conteos van en gris).
function tendencia(i, v, vAnt) {
  if (v == null || vAnt == null) return '';
  const d = v - vAnt;
  if (esConteo(i) && mesEnCurso) return '<span class="tend">parcial</span>';
  if (Math.abs(d) < 0.05) return '<span class="tend">= mes ant.</span>';
  const clase = esConteo(i) ? '' : ((mayorMejor(i) ? d > 0 : d < 0) ? 'delta-bien' : 'delta-mal');
  return `<span class="tend ${clase}">${d > 0 ? '▲' : '▼'} ${esConteo(i) ? fmtN(Math.abs(d)) : fmt(Math.abs(d), i).replace('%', ' pts')}</span>`;
}

function celdaTotal(t, tAnt) {
  if (!t) return '<span style="color:var(--muted)">—</span>';
  const punto = esConteo(t.i) ? '' : `<span class="p" style="background:${colorEstado(t.s)}" title="${esc(ETIQUETA_ESTADO[t.s] || '')}${t.m != null ? ' · meta ' + fmt(t.m, t.i) : ''}"></span>`;
  return `<span class="celda-res"><b>${punto}${fmt(t.v, t.i)}</b>${tendencia(t.i, t.v, tAnt?.v)}</span>`;
}

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
      <div class="tarjeta" style="margin-bottom:16px">
        <div class="cabecera"><div><h2>KPI por cuenta · ${fmtPeriodo(per)}</h2>
          <p class="sub" style="margin:0">Total del mes de cada cuenta, calculado como en su dashboard. Flecha: comparación con el mes anterior (verde mejora, rojo empeora). Toca una cuenta para ver su detalle.</p></div>
          <a class="btn chico" href="#/kpis">Ver tabla completa</a></div>
        <div id="g-resumen"></div>
      </div>
      <div class="grid g-kpi">
        ${kpi({ etiqueta: 'Evaluaciones de calidad', valor: fmtN(evaluaciones), detalle: `${fmtPeriodo(per)} ${variacion(evaluaciones, suma(delAnt.filter(r => r.i === 'evaluaciones')))}` })}
        ${kpi({ etiqueta: 'Encuestas de clientes', valor: fmtN(encuestas), detalle: `${fmtPeriodo(per)} ${variacion(encuestas, suma(delAnt.filter(r => r.i === 'encuestas')))}` })}
        ${kpi({ etiqueta: 'Servicios con datos', valor: `${conDatos} de ${srv.length}`, detalle: 'Servicios con mediciones en el mes' })}
        ${kpi({ etiqueta: 'Indicadores bajo meta', valor: fmtN(riesgo), detalle: 'Cuenta e indicador en alerta o crítico', clase: riesgo ? 'critico' : '' })}
      </div>
      ${per === hoy ? '<div class="aviso">El mes seleccionado está en curso: las cantidades seguirán aumentando.</div>' : ''}
      <details class="ayuda"><summary>¿Cómo leer esta vista?</summary><p class="sub">Los valores de cada servicio son el total del mes calculado con la misma fórmula de su dashboard. El punto indica si ese total cumple la meta (verde), está bajo meta (amarillo/rojo) o el dashboard no define meta (gris); "x/y cuentas cumplen" detalla las cuentas.</p></details>
      ${unis.map(u => `
        <div class="cabecera" style="margin-top:8px"><div><h2 style="font-size:16px">${esc(u.nombre)}</h2></div>
          ${u.proximamente ? '<span class="pendiente">Próximamente</span>' : `<a class="btn chico" href="#/empresa/${u.e}/${u.p}">Detalle por plataforma</a>`}</div>
        ${u.proximamente ? '' : `<div class="grid g-srv">${srv.filter(x => x.e === u.e && x.p === u.p).map(x => tarjetaServicio(x, delPer, delAnt, per, perAnt)).join('')}</div>`}
      `).join('')}
      <div class="tarjeta" style="margin-top:20px">
        <div class="cabecera"><div><h2>Evaluaciones por servicio y mes</h2>
          <p class="sub" style="margin:0">Cantidad de monitoreos de calidad y de encuestas de clientes registrados en cada base</p></div>
          <button class="btn" id="g-csv">Exportar CSV</button></div>
        <div id="g-tabla"></div>
      </div>`;

    pintarResumen(cont.querySelector('#g-resumen'), srv, per, perAnt);
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

function tarjetaServicio(x, delPer, delAnt, per, perAnt) {
  const regs = delPer.filter(r => r.l === x.l);
  const ant = delAnt.filter(r => r.l === x.l);
  const total = i => S.totales.find(z => z.l === x.l && z.i === i && z.per === per);
  const totalAnt = i => S.totales.find(z => z.l === x.l && z.i === i && z.per === perAnt);
  const conteos = CONTEOS.map(([id, nombre]) => {
    const t = total(id);
    const r = regs.filter(z => z.i === id);
    if (!t && !r.length) return null;
    return { id, nombre, v: t ? t.v : suma(r), ant: totalAnt(id)?.v ?? suma(ant.filter(z => z.i === id)) };
  }).filter(Boolean);
  const principal = conteos[0];
  const inds = Object.keys(S.indicadores).filter(i => !esConteo(i) && (total(i) || regs.some(r => r.i === i))).map(i => {
    const r = regs.filter(z => z.i === i);
    const t = total(i);
    const conMeta = r.filter(z => z.s !== 'SIN_META');
    const ok = conMeta.filter(z => z.s === 'OK').length;
    // Valor y estado del servicio = fila (TOTAL), calculada como en el dashboard.
    return { i, v: t ? t.v : ponderado(r), cuentas: r.length, ok, conMeta: conMeta.length, peor: t ? t.s : 'SIN_META', meta: t?.m };
  });
  // Primero los indicadores con meta y los principales; el resto queda en "Ver más".
  const PRIORIDAD = ['calidad', 'epa', 'fcr', 'efectividad', 'pec', 'penc', 'adherencia', 'global'];
  inds.sort((a, b) => (b.meta != null) - (a.meta != null) || PRIORIDAD.indexOf(a.i) - PRIORIDAD.indexOf(b.i));
  const fila = d => `<li title="${d.meta != null ? `Meta ${fmt(d.meta, d.i)} · ` : ''}${d.conMeta ? `${d.ok} de ${d.conMeta} cuentas cumplen la meta` : 'Sin meta definida en el dashboard'}">
        <span class="p" style="background:${colorEstado(d.peor)}"></span><span class="n">${esc(nombreIndicador(d.i))}</span>
        <span class="v">${fmt(d.v, d.i)}</span><span class="c">${d.meta != null ? `meta ${fmt(d.meta, d.i)} · ` : ''}${d.conMeta ? `${d.ok}/${d.conMeta} cuentas cumplen` : d.cuentas ? `${d.cuentas} cuenta${d.cuentas > 1 ? 's' : ''} · sin meta` : 'sin meta'}</span></li>`;
  const tieneFuente = S.registros.some(r => r.l === x.l) || S.totales.some(r => r.l === x.l);
  return `<div class="tarjeta srv">
    <div class="srv-top">
      <div><h3><a class="srv-link" href="#/servicio/${esc(x.id)}">${esc(x.servicio)} ›</a></h3><small>${esc(x.unidad.nombre)}</small></div>
      ${!tieneFuente ? '<span class="pendiente">Sin base conectada</span>' : !regs.length ? '<span class="pendiente">Sin datos en el mes</span>' : ''}
    </div>
    ${principal ? `<div class="srv-num"><b>${fmtN(principal.v)}</b> ${principal.nombre.toLowerCase()}
        ${variacion(principal.v, principal.ant)}</div>
      ${conteos.slice(1).map(c => `<div class="srv-sub">${fmtN(c.v)} ${c.nombre.toLowerCase()}</div>`).join('')}` : '<div class="srv-num"><b>—</b></div>'}
    ${inds.length ? `<ul class="srv-inds">${inds.slice(0, 3).map(fila).join('')}</ul>` : ''}
    ${inds.length > 3 ? `<details class="srv-mas"><summary>Ver ${inds.length - 3} indicador${inds.length - 3 > 1 ? 'es' : ''} más</summary><ul class="srv-inds">${inds.slice(3).map(fila).join('')}</ul></details>` : ''}
    <div class="acc">
      ${x.url ? `<a class="btn primario chico" href="#/ver/${esc(x.id)}">Ver dashboard</a><a class="btn chico" href="${esc(x.url)}" target="_blank" rel="noopener">Abrir ↗</a>`
        : '<span class="pendiente">Visualización pendiente</span>'}
    </div>
  </div>`;
}

function pintarResumen(cont, srv, per, perAnt) {
  const conDatos = srv.filter(x => S.totales.some(z => z.l === x.l));
  const inds = ORDEN.filter(i => conDatos.some(x => totalDe(x.l, i, per)));
  pintarResumen.ultimo = { conDatos, inds, per, perAnt };
  tabla(cont, {
    filas: conDatos.map(x => ({ x, srv: `${x.unidad.nombre} · ${x.servicio}` })), porPagina: 50,
    vacio: 'Sin datos para el mes seleccionado.',
    tarjeta: { titulo: f => `<a class="srv-link" href="#/servicio/${esc(f.x.id)}">${esc(f.x.servicio)} ›</a>`, sub: f => esc(f.x.unidad.nombre), omitir: ['srv'] },
    columnas: [
      { id: 'srv', titulo: 'Cuenta', render: f => `<a class="srv-link" href="#/servicio/${esc(f.x.id)}"><b>${esc(f.x.servicio)}</b> ›</a><br><small style="color:var(--muted)">${esc(f.x.unidad.nombre)}</small>` },
      ...inds.map(i => ({
        id: i, titulo: esc(nombreIndicador(i)), num: true,
        valor: f => totalDe(f.x.l, i, per)?.v ?? null,
        render: f => celdaTotal(totalDe(f.x.l, i, per), totalDe(f.x.l, i, perAnt)),
      })),
    ],
  });
}

// ===================================================================== TABLA DE KPI POR CUENTA

export function kpis(cont) {
  const pers = periodos(S.totales);
  const hoy = hoyMes();
  const estado = { per: pers.filter(p => p < hoy).at(-1) || pers.at(-1) || '', e: '' };
  const pintar = () => {
    mesEnCurso = estado.per === hoy;
    const perAnt = pers[pers.indexOf(estado.per) - 1] || null;
    const srv = lineas().filter(x => !estado.e || x.e === estado.e);
    cont.innerHTML = `
      <div class="tarjeta filtros" style="margin-bottom:16px">
        <div class="campo"><label for="k-per">Mes</label><select id="k-per">${pers.slice().reverse().map(p =>
          `<option value="${p}" ${p === estado.per ? 'selected' : ''}>${fmtPeriodo(p)}${p === hoy ? ' (en curso)' : ''}</option>`).join('')}</select></div>
        <div class="campo"><label for="k-emp">Empresa</label><select id="k-emp"><option value="">Todas</option>${S.portal.empresas.map(x =>
          `<option value="${x.id}" ${x.id === estado.e ? 'selected' : ''}>${esc(x.nombre)}</option>`).join('')}</select></div>
        <div class="acciones"><button class="btn" id="k-csv">Exportar CSV</button></div>
      </div>
      ${mesEnCurso ? '<div class="aviso">Mes en curso: las cantidades seguirán aumentando.</div>' : ''}
      <div class="tarjeta">
        <h2>KPI por cuenta · ${fmtPeriodo(estado.per)}</h2>
        <p class="sub">Una fila por cuenta y una columna por KPI. Toca un encabezado para ordenar y una cuenta para ver su detalle.
          Punto: verde cumple la meta, amarillo/rojo bajo meta, gris sin meta definida. Flecha: comparación con ${perAnt ? fmtPeriodo(perAnt) : 'el mes anterior'}.</p>
        <div id="k-tabla"></div>
      </div>`;
    pintarResumen(cont.querySelector('#k-tabla'), srv, estado.per, perAnt);
    cont.querySelector('#k-per').addEventListener('change', ev => { estado.per = ev.target.value; pintar(); });
    cont.querySelector('#k-emp').addEventListener('change', ev => { estado.e = ev.target.value; pintar(); });
    cont.querySelector('#k-csv').addEventListener('click', () => {
      const { conDatos, inds, per, perAnt: pa } = pintarResumen.ultimo;
      const filas = conDatos.map(x => ({ x }));
      const cols = [
        { id: 'empresa', titulo: 'Empresa', csv: f => f.x.unidad.nombre },
        { id: 'cuenta', titulo: 'Cuenta', csv: f => f.x.servicio },
        ...inds.flatMap(i => [
          { id: i, titulo: `${nombreIndicador(i)} ${per}`, csv: f => totalDe(f.x.l, i, per)?.v?.toFixed(2) ?? '' },
          { id: i + '_ant', titulo: `${nombreIndicador(i)} ${pa || 'mes anterior'}`, csv: f => totalDe(f.x.l, i, pa)?.v?.toFixed(2) ?? '' },
          ...(esConteo(i) ? [] : [{ id: i + '_m', titulo: `${nombreIndicador(i)} meta`, csv: f => totalDe(f.x.l, i, per)?.m ?? '' }]),
        ]),
      ];
      descargar(`central_kpi_por_cuenta_${per}.csv`, aCSV(filas, cols), 'text/csv;charset=utf-8');
    });
  };
  pintar();
}

// ===================================================================== PÁGINA DE UNA CUENTA (servicio)

export function servicio(cont, [id]) {
  const x = linea(id);
  if (!x) { cont.innerHTML = '<div class="vacio">Cuenta no encontrada.</div>'; return; }
  const tots = S.totales.filter(z => z.l === x.l);
  const pers = periodos(tots);
  const hoy = hoyMes();
  let per = pers.filter(p => p < hoy).at(-1) || pers.at(-1);

  const pintar = () => {
    destruirGraficos();
    mesEnCurso = per === hoy;
    const perAnt = pers[pers.indexOf(per) - 1] || null;
    const inds = ORDEN.filter(i => tots.some(z => z.i === i && z.per === per));
    const regsMes = S.registros.filter(r => r.l === x.l && r.per === per);
    const plataformas = [...new Set(regsMes.map(r => r.c))].sort();
    cont.innerHTML = `
      <div class="tarjeta" style="margin-bottom:16px">
        <div class="cabecera">
          <div><h2 style="font-size:18px">${esc(x.unidad.nombre)} · ${esc(x.servicio)}</h2>
            <p class="sub" style="margin:0">${plataformas.length} plataforma${plataformas.length === 1 ? '' : 's'} / campaña${plataformas.length === 1 ? '' : 's'} con datos en ${fmtPeriodo(per)}</p></div>
          <div class="acc-srv">
            <div class="campo" style="min-width:150px"><label for="s-per">Mes</label><select id="s-per">${pers.slice().reverse().map(p =>
              `<option value="${p}" ${p === per ? 'selected' : ''}>${fmtPeriodo(p)}${p === hoy ? ' (en curso)' : ''}</option>`).join('')}</select></div>
            ${x.url ? `<a class="btn primario" href="#/ver/${esc(x.id)}">Ver dashboard</a>` : ''}
          </div>
        </div>
      </div>
      ${!tots.length ? '<div class="vacio">Esta cuenta todavía no tiene una base conectada.</div>' : `
      ${mesEnCurso ? '<div class="aviso">Mes en curso: las cantidades seguirán aumentando.</div>' : ''}
      <div class="grid g-kpi">${inds.map(i => {
        const t = totalDe(x.l, i, per), a = totalDe(x.l, i, perAnt);
        return kpi({
          etiqueta: `${esConteo(i) ? '' : `<span class="p-kpi" style="background:${colorEstado(t.s)}"></span>`}${esc(nombreIndicador(i))}`,
          valor: fmt(t.v, i),
          detalle: [t.m != null ? `Meta ${fmt(t.m, i)}` : (esConteo(i) ? '' : 'Sin meta'), tendencia(i, t.v, a?.v), esConteo(i) ? '' : `${fmtN(t.n)} casos`].filter(Boolean).join(' · '),
        });
      }).join('')}</div>
      <div class="grid g-2">
        <div class="tarjeta"><h2>Evolución de indicadores</h2><p class="sub">Total mensual de la cuenta (últimos 12 meses)</p>
          <div class="grafico"><canvas id="s-g1" aria-label="Evolución de indicadores"></canvas></div><div id="s-l1"></div></div>
        <div class="tarjeta"><h2>Evaluaciones y encuestas</h2><p class="sub">Cantidad por mes</p>
          <div class="grafico"><canvas id="s-g2" aria-label="Evaluaciones por mes"></canvas></div><div id="s-l2"></div></div>
      </div>
      <div class="tarjeta"><h2>Por plataforma / campaña · ${fmtPeriodo(per)}</h2><p class="sub">Detalle del mes dentro de la cuenta</p><div id="s-tabla"></div></div>`}`;

    cont.querySelector('#s-per').addEventListener('change', ev => { per = ev.target.value; pintar(); });
    if (!tots.length) return;

    const meses = pers.slice(-12);
    const serieDe = i => meses.map(m => tots.find(z => z.i === i && z.per === m)?.v ?? null);
    // Un solo eje: indicadores en % o índice (escala hasta 100); los conteos y la escala 1-5 van aparte.
    const res = ORDEN.filter(i => !esConteo(i) && i !== 'global' && tots.some(z => z.i === i));
    const s1 = res.map(i => ({ nombre: nombreIndicador(i), color: serie(ORDEN.indexOf(i) - 2), datos: serieDe(i) }));
    const s2 = ['evaluaciones', 'encuestas'].filter(i => tots.some(z => z.i === i))
      .map((i, k) => ({ nombre: nombreIndicador(i), color: serie(k), datos: serieDe(i) }));
    const etiquetas = meses.map(fmtPeriodo);
    if (s1.length) {
      graficoLineas(cont.querySelector('#s-g1'), { etiquetas, series: s1, formato: v => fmt(v, res[0]).replace('%', '') });
      cont.querySelector('#s-l1').innerHTML = leyenda(s1);
    } else cont.querySelector('#s-g1').replaceWith(Object.assign(document.createElement('div'), { className: 'vacio', textContent: 'Sin indicadores de resultado.' }));
    graficoLineas(cont.querySelector('#s-g2'), { etiquetas, series: s2, formato: v => fmtN(v) });
    cont.querySelector('#s-l2').innerHTML = s2.length > 1 ? leyenda(s2) : '';

    const indsPlat = ORDEN.filter(i => regsMes.some(r => r.i === i));
    tabla(cont.querySelector('#s-tabla'), {
      filas: plataformas.map(c => ({ c, ...Object.fromEntries(regsMes.filter(r => r.c === c).map(r => [r.i, r])) })),
      porPagina: 50, orden: { id: 'c', dir: 'asc' },
      columnas: [
        { id: 'c', titulo: 'Plataforma / campaña', render: f => `<b>${esc(f.c)}</b>` },
        ...indsPlat.map(i => ({
          id: i, titulo: esc(nombreIndicador(i)), num: true, valor: f => f[i]?.v ?? null,
          render: f => !f[i] ? '<span style="color:var(--muted)">—</span>' : esConteo(i) ? fmt(f[i].v, i)
            : `<span class="celda"><span class="p" style="background:${colorEstado(f[i].s)}"></span>${fmt(f[i].v, i)}</span>`,
        })),
      ],
    });
  };
  pintar();
}

function matrizEvaluaciones(srv) {
  // En el celular se muestran los últimos 6 meses para que la tabla se lea sin desplazarse tanto.
  const meses = periodos(S.registros.filter(r => esConteo(r.i))).slice(matchMedia('(max-width: 600px)').matches ? -6 : -12);
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
    <thead><tr><th>Servicio</th><th>Tipo</th>${meses.map(m => `<th class="num">${fmtPeriodo(m)}${m === hoy ? '*' : ''}</th>`).join('')}<th class="num">Total</th></tr></thead>
    <tbody>${filas.map(f => `<tr><td><b>${esc(f.servicio)}</b><small>${esc(f.empresa)}</small></td><td>${esc(f.tipo)}</td>
      ${meses.map(m => celda(f.meses[m])).join('')}<td class="num"><b>${fmtN(f.total)}</b></td></tr>`).join('')}</tbody>
    <tfoot>${totales.map(t => `<tr><td><b>Total ${t.tipo.toLowerCase()}</b></td><td></td>${meses.map(m => `<td class="num"><b>${fmtN(t.meses[m])}</b></td>`).join('')}<td class="num"><b>${fmtN(t.total)}</b></td></tr>`).join('')}</tfoot>
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
      <p class="sub solo-movil">En el celular el dashboard se ve mejor en una pestaña nueva.</p>
      <div class="visor-wrap"><iframe class="visor" src="${esc(actual.url)}" title="Dashboard ${esc(actual.servicio)}" referrerpolicy="no-referrer"></iframe></div>
      <p class="sub">Si el dashboard no se muestra, ábrelo en una pestaña nueva (algunos sitios no permiten mostrarse dentro de otra página o requieren iniciar sesión).</p>`
      : '<div class="vacio">Ningún dashboard tiene URL de visualización configurada.</div>'}`;
}
