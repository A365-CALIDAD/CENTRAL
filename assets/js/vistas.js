// CENTRAL · vistas del portal. Cada vista recibe el contenedor y los parámetros de la ruta.
import {
  S, esc, fmt, fmtN, fmtPct, fmtPeriodo, brecha, filtrar, ultimas, racha, comparar, periodos, opciones,
  unidades, unidad, nombreEmpresa, nombrePais, nombreIndicador, descargar, aCSV, nombreLinea, esConteo, mesPorDefecto,
  esAdmin, bitacoraEnLinea, cargarBitacora, crearAccion, actualizarAccion, eliminarAccion, historialAccion,
  soloIndicadores, urlPerfil,
} from './datos.js';
import {
  badge, kpi, tabla, barraFiltros, filtrosGlobales, graficoLineas, graficoBarrasApiladas, leyenda, css, serie, ETIQUETA_ESTADO, destruirGraficos,
} from './componentes.js';

const nombreUnidad = (e, p) => unidad(e, p)?.nombre ?? `${nombreEmpresa(e)} ${nombrePais(e, p)}`;
const enRiesgo = r => r.s === 'CRITICO' || r.s === 'ALERTA';
const servicio = r => `${nombreUnidad(r.e, r.p)} · ${nombreLinea(r.l)}`;
const servicioDe = l => { const x = S.portal.empresas.flatMap(e => e.paises.flatMap(p => p.dashboards.map(d => ({ d, e, p })))).find(z => z.d.id === l);
  return x ? `${nombreUnidad(x.e.id, x.p.id)} · ${x.d.servicio || x.d.nombre}` : l; };
const brechaRel = r => { const b = brecha(r); return b === null || !r.m ? null : (b / Math.abs(r.m)) * 100; };
const accionesAbiertas = (r) => S.seguimiento.filter(a => a.estado !== 'cerrada' && a.empresa_id === r.e && a.pais_id === r.p && (!a.linea_id || a.linea_id === r.l) && a.cuenta === r.c && (!a.indicador_id || a.indicador_id === r.i)).length;

function avisos() {
  const out = [];
  if (!S.registros.length) out.push('<div class="aviso">Aún no hay mediciones publicadas. Ejecute el ETL (<code>python etl/central_etl.py procesar</code>) para generar <code>data/consolidado.json</code>.</div>');
  if (S.hayDemo) out.push('<div class="aviso"><b>Datos de demostración.</b> Las cifras provienen de archivos ficticios (fuentes <code>demo_*</code>). Reemplácelos por los Excel reales y desactive las fuentes demo en <code>config/fuentes.json</code>.</div>');
  if (S.metasEjemplo) out.push('<div class="aviso">Las metas y umbrales de <code>config/indicadores.json</code> son valores de ejemplo pendientes de validar con cada cliente.</div>');
  return out.join('');
}

const STATUS = () => [
  { id: 'OK', nombre: 'Cumple', color: css('--good') },
  { id: 'ALERTA', nombre: 'Alerta', color: css('--warning') },
  { id: 'CRITICO', nombre: 'Crítico', color: css('--critical') },
  { id: 'SIN_META', nombre: 'Sin meta', color: css('--axis') },
];

export function bloqueKPIs(regs) {
  const ult = ultimas(regs).filter(r => !esConteo(r.i));
  const conMeta = ult.filter(r => r.s !== 'SIN_META');
  const ok = conMeta.filter(r => r.s === 'OK').length;
  const crit = ult.filter(r => r.s === 'CRITICO').length;
  const alert = ult.filter(r => r.s === 'ALERTA').length;
  const cuentas = new Set(ult.map(r => `${r.e}|${r.p}|${r.l}|${r.c}`)).size;
  const per = periodos(regs).at(-1);
  return `<div class="grid g-kpi">
    ${kpi({ etiqueta: 'Plataformas / campañas', valor: fmtN(cuentas), detalle: per ? `Último periodo: ${fmtPeriodo(per)}` : '' })}
    ${kpi({ etiqueta: 'Indicadores vigentes', valor: fmtN(ult.length), detalle: 'Última medición por cuenta e indicador' })}
    ${kpi({ etiqueta: 'Cumplimiento de meta', valor: fmtPct(conMeta.length ? (ok / conMeta.length) * 100 : null), detalle: `${ok} de ${conMeta.length} con meta` })}
    ${kpi({ etiqueta: `${badge('CRITICO')}`, valor: fmtN(crit), detalle: 'Igual o peor que el umbral crítico', clase: crit ? 'critico' : '' })}
    ${kpi({ etiqueta: `${badge('ALERTA')}`, valor: fmtN(alert), detalle: 'Bajo meta, sobre el umbral' })}
  </div>`;
}

export function tarjetasDashboards(lista) {
  if (!lista.length) return '<div class="vacio">No hay dashboards configurados.</div>';
  return `<div class="grid g-dash">${lista.map(({ d: base, u }) => ({ d: { ...base, url: urlPerfil(base.url),
    repo: soloIndicadores() ? '' : base.repo }, u })).map(({ d, u }) => `
    <div class="tarjeta dash">
      <div class="top"><h3>${esc(d.nombre)}</h3>${d.url ? '' : '<span class="pendiente">URL pendiente</span>'}</div>
      <p>${esc(d.descripcion || u.nombre)}</p>
      <div class="acc">
        <a class="btn primario chico ${d.url ? '' : 'deshabilitado'}" ${d.url ? `href="#/ver/${esc(d.id)}"` : 'aria-disabled="true"'}>Ver aquí</a>
        ${d.url ? `<a class="btn chico" href="${esc(d.url)}" target="_blank" rel="noopener">Abrir ↗</a>` : ''}
        ${d.repo ? `<a class="btn chico" href="${esc(d.repo)}" target="_blank" rel="noopener">Repositorio</a>` : soloIndicadores() ? '' : '<span class="pendiente">Repo pendiente</span>'}
      </div>
    </div>`).join('')}</div>`;
}

// ===================================================================== EMPRESA / PAÍS

function metaColumna(regs, i) {
  const metas = [...new Set(regs.filter(r => r.i === i && r.m !== null).map(r => r.m))];
  if (!metas.length) return 'sin meta';
  return metas.length === 1 ? `meta ${fmt(metas[0], i)}` : 'meta por cuenta';
}

export function empresa(cont, [e, p]) {
  const u = unidad(e, p);
  if (!u) { cont.innerHTML = '<div class="vacio">Sección no encontrada.</div>'; return; }
  if (u.proximamente) {
    cont.innerHTML = `<div class="tarjeta proximamente"><div class="ico">🚧</div><h2>${esc(u.nombre)} · Próximamente</h2>
      <p class="sub">Esta sección se activará al agregar sus dashboards en <code>config/portal.json</code> y su fuente de datos en <code>config/fuentes.json</code>.</p></div>`;
    return;
  }
  const regs = S.registros.filter(r => r.e === e && r.p === p);
  const pers = periodos(regs);
  let per = mesPorDefecto(pers);
  cont.innerHTML = `${avisos()}
    <div class="tarjeta bloque-dashboards" style="margin-bottom:16px">
      <div class="cabecera"><div><h2>Dashboards de ${esc(u.nombre)}</h2><p class="sub" style="margin:0">Enlaces definidos en config/portal.json</p></div></div>
      ${tarjetasDashboards(u.pais.dashboards.map(d => ({ d, u })))}
    </div>
    ${bloqueKPIs(regs)}
    <div class="tarjeta">
      <div class="cabecera">
        <div><h2>Resultados por plataforma / campaña</h2><p class="sub" style="margin:0">Valor y estado de cada indicador en el periodo seleccionado</p></div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <div class="campo" style="min-width:150px"><label for="sel-per">Periodo</label>
            <select id="sel-per">${pers.map(x => `<option value="${x}" ${x === per ? 'selected' : ''}>${fmtPeriodo(x)}</option>`).join('')}</select></div>
          <a class="btn" href="#/historico" id="lnk-hist" style="align-self:flex-end">Ver evolución</a>
        </div>
      </div>
      <div id="matriz"></div>
    </div>`;

  // Primero los conteos (evaluaciones, encuestas) y luego los indicadores de resultado.
  const inds = Object.keys(S.indicadores).filter(i => regs.some(r => r.i === i)).sort((a, b) => esConteo(b) - esConteo(a));
  const pintar = () => {
    const delPer = regs.filter(r => r.per === per);
    const claves = [...new Set(delPer.map(r => `${r.l}||${r.c}`))];
    const cuentas = claves.map(k => {
      const [l, c] = k.split('||');
      return { l, c, srv: nombreLinea(l), ...Object.fromEntries(delPer.filter(r => r.l === l && r.c === c).map(r => [r.i, r])) };
    });
    tabla(cont.querySelector('#matriz'), {
      filas: cuentas, porPagina: 100, orden: { id: 'srv', dir: 'asc' }, tituloCols: 2,
      columnas: [
        { id: 'srv', titulo: 'Servicio', render: f => esc(f.srv) },
        { id: 'c', titulo: 'Plataforma / campaña', render: f => `<b>${esc(f.c)}</b>` },
        ...inds.map(i => ({
          id: i, titulo: `${esc(nombreIndicador(i))}<br><small style="font-weight:400;text-transform:none">${esConteo(i) ? 'cantidad' : metaColumna(delPer, i)}</small>`, num: true,
          valor: f => f[i]?.v ?? null,
          render: f => f[i] && esConteo(i) ? fmt(f[i].v, i) : f[i] ? `<span class="celda" title="${esc(ETIQUETA_ESTADO[f[i].s])} · meta ${fmt(f[i].m, i)} · ${fmtN(f[i].n)} casos"><span class="p" style="background:${f[i].s === 'OK' ? 'var(--good)' : f[i].s === 'ALERTA' ? 'var(--warning)' : f[i].s === 'CRITICO' ? 'var(--critical)' : 'var(--axis)'}"></span>${fmt(f[i].v, i)}</span>` : '<span style="color:var(--muted)">—</span>',
        })),
      ],
    });
  };
  cont.querySelector('#sel-per').addEventListener('change', ev => { per = ev.target.value; pintar(); });
  cont.querySelector('#lnk-hist').addEventListener('click', () => Object.assign(filtrosGlobales, { e, p, c: '' }));
  pintar();
}

// ===================================================================== TABLA CONSOLIDADA

const COLS_CONSOLIDADO = [
  { id: 'e', titulo: 'Empresa', render: r => esc(nombreEmpresa(r.e)), csv: r => nombreEmpresa(r.e) },
  { id: 'p', titulo: 'País', render: r => esc(nombrePais(r.e, r.p)), csv: r => nombrePais(r.e, r.p) },
  { id: 'l', titulo: 'Servicio', render: r => esc(nombreLinea(r.l)), csv: r => nombreLinea(r.l) },
  { id: 'c', titulo: 'Cuenta' },
  { id: 'i', titulo: 'Indicador', render: r => esc(nombreIndicador(r.i)), csv: r => nombreIndicador(r.i) },
  { id: 'per', titulo: 'Periodo', render: r => fmtPeriodo(r.per), csv: r => r.per },
  { id: 'v', titulo: 'Valor', num: true, render: r => fmt(r.v, r.i), csv: r => r.v },
  { id: 'm', titulo: 'Meta', num: true, render: r => fmt(r.m, r.i), csv: r => r.m },
  { id: 'b', titulo: 'Brecha', num: true, valor: r => brecha(r), render: r => { const b = brecha(r); return b === null ? '—' : `<span class="${b >= 0 ? 'delta-bien' : 'delta-mal'}">${b >= 0 ? '+' : ''}${fmt(b, r.i)}</span>`; }, csv: r => brecha(r) },
  { id: 'n', titulo: 'Muestras', num: true, render: r => fmtN(r.n) },
  { id: 's', titulo: 'Estado', render: r => badge(r.s), csv: r => ETIQUETA_ESTADO[r.s] },
];

export function indicadores(cont) {
  cont.innerHTML = `${avisos()}<div id="filtros"></div><div class="tarjeta"><div class="cabecera">
    <div><h2>Tabla consolidada de indicadores</h2><p class="sub" style="margin:0" id="res-filas"></p></div>
    <div style="display:flex;gap:8px"><button class="btn" id="btn-csv">Exportar CSV</button></div></div><div id="tabla"></div></div>`;
  let filas = [];
  const t = tabla(cont.querySelector('#tabla'), {
    filas, porPagina: 50, orden: { id: 'per', dir: 'desc' },
    tarjeta: { titulo: r => `${esc(nombreIndicador(r.i))} · ${esc(r.c)}`, sub: r => `${esc(servicio(r))} · ${fmtPeriodo(r.per)}`, omitir: ['e', 'p', 'l', 'c', 'i', 'per'] },
    columnas: [...COLS_CONSOLIDADO, { id: 'acc', titulo: '', sinOrden: true, render: r => enRiesgo(r) && esAdmin() && bitacoraEnLinea() ? `<button class="btn chico" data-seg='${esc(JSON.stringify({ e: r.e, p: r.p, l: r.l, c: r.c, i: r.i, per: r.per }))}'>+ Seguimiento</button>` : '' }],
  });
  const aplicar = () => {
    filas = filtrar(S.registros, filtrosGlobales);
    cont.querySelector('#res-filas').textContent = `${filas.length.toLocaleString('es')} mediciones · ${new Set(filas.map(r => `${r.e}|${r.p}|${r.c}`)).size} cuentas`;
    t.actualizar(filas);
  };
  barraFiltros(cont.querySelector('#filtros'), { alCambiar: aplicar });
  cont.querySelector('#btn-csv').addEventListener('click', () => descargar(`central_indicadores_${new Date().toISOString().slice(0, 10)}.csv`, aCSV(filas, COLS_CONSOLIDADO), 'text/csv;charset=utf-8'));
  cont.querySelector('#tabla').addEventListener('click', ev => {
    const b = ev.target.closest('[data-seg]');
    if (b) abrirSeguimiento(JSON.parse(b.dataset.seg)).then(ok => ok && aplicar());
  });
  aplicar();
}

// ===================================================================== HISTÓRICO Y COMPARACIÓN

export function historico(cont) {
  const pers = periodos();
  if (!filtrosGlobales.i) filtrosGlobales.i = Object.keys(S.indicadores).find(i => S.registros.some(r => r.i === i)) || '';
  const actual = mesPorDefecto(pers);
  const cmp = { a: pers[pers.indexOf(actual) - 1] || actual, b: actual };   // mes en curso contra el anterior
  cont.innerHTML = `${avisos()}<div id="filtros"></div>
    <div class="tarjeta" style="margin-bottom:16px">
      <h2 id="h-titulo">Evolución</h2><p class="sub" id="h-sub"></p>
      <div class="grafico" style="height:340px"><canvas id="g-hist" aria-label="Evolución del indicador"></canvas></div>
      <div id="h-leyenda"></div>
    </div>
    <div class="tarjeta">
      <div class="cabecera"><div><h2>Comparación entre periodos</h2><p class="sub" style="margin:0">Variación por cuenta e indicador (aplica los filtros superiores)</p></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <div class="campo"><label for="cmp-a">Periodo base</label><select id="cmp-a">${pers.map(x => `<option value="${x}" ${x === cmp.a ? 'selected' : ''}>${fmtPeriodo(x)}</option>`).join('')}</select></div>
          <div class="campo"><label for="cmp-b">Periodo comparado</label><select id="cmp-b">${pers.map(x => `<option value="${x}" ${x === cmp.b ? 'selected' : ''}>${fmtPeriodo(x)}</option>`).join('')}</select></div>
        </div></div>
      <div id="t-cmp"></div>
    </div>`;

  const tCmp = tabla(cont.querySelector('#t-cmp'), {
    filas: [], porPagina: 25, orden: { id: 'delta', dir: 'asc' },
    columnas: [
      { id: 'u', titulo: 'Servicio', valor: x => servicio(x), render: x => esc(servicio(x)) },
      { id: 'c', titulo: 'Cuenta' },
      { id: 'i', titulo: 'Indicador', render: x => esc(nombreIndicador(x.i)) },
      { id: 'a', titulo: 'Base', num: true, valor: x => x.a?.v ?? null, render: x => fmt(x.a?.v, x.i) },
      { id: 'b', titulo: 'Comparado', num: true, valor: x => x.b?.v ?? null, render: x => fmt(x.b?.v, x.i) },
      { id: 'delta', titulo: 'Variación', num: true, valor: x => x.delta === null ? null : (x.mejora ? 1 : -1) * Math.abs(x.delta), render: x => x.delta === null ? '—' : `<span class="${x.mejora ? 'delta-bien' : x.delta === 0 ? '' : 'delta-mal'}">${x.delta > 0 ? '▲ +' : x.delta < 0 ? '▼ ' : ''}${fmt(x.delta, x.i)}</span>` },
      { id: 's', titulo: 'Estado actual', render: x => x.b ? badge(x.b.s) : '—' },
    ],
  });

  const pintar = () => {
    const f = { ...filtrosGlobales };
    const ind = f.i;
    const base = filtrar(S.registros, { ...f, s: '' });
    const etiquetas = periodos(base);
    const formato = v => fmt(v, ind);
    let series = [];
    let metaUnica = null;
    let nota = '';
    if (f.c) {
      const r = base.filter(x => x.c === f.c);
      if (new Set(r.map(x => x.l)).size > 1) nota = 'La cuenta existe en varios servicios: seleccione el servicio.';
      series = [{ nombre: f.c, color: serie(0), datos: etiquetas.map(per => r.find(x => x.per === per)?.v ?? null) }];
      const metas = [...new Set(r.map(x => x.m))];
      metaUnica = metas.length === 1 ? metas[0] : null;
    } else if (f.e && f.p) {
      const clave = x => `${nombreLinea(x.l)} · ${x.c}`;
      const todas = [...new Set(S.registros.filter(x => x.e === f.e && x.p === f.p).map(clave))].sort();   // color fijo por cuenta
      const presentes = [...new Set(base.map(clave))].sort();
      if (presentes.length > 8) nota = `Se muestran 8 de ${presentes.length} cuentas; filtre por cuenta para ver otras.`;
      series = presentes.slice(0, 8).map(c => ({ nombre: c, color: serie(todas.indexOf(c)), datos: etiquetas.map(per => base.find(x => clave(x) === c && x.per === per)?.v ?? null) }));
      const metas = [...new Set(base.map(x => x.m))];
      metaUnica = metas.length === 1 ? metas[0] : null;
    } else {
      const unis = unidades().filter(u => !u.proximamente);
      series = unis.map((u, k) => {
        const r = base.filter(x => x.e === u.e && x.p === u.p);
        return { nombre: `${u.nombre} (promedio)`, color: serie(k), datos: etiquetas.map(per => { const v = r.filter(x => x.per === per).map(x => x.v); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }) };
      }).filter(s => (!f.e || s.nombre.startsWith(nombreEmpresa(f.e))) && s.datos.some(v => v !== null));
      nota = 'Promedio simple de las cuentas de cada empresa. Seleccione empresa y país para ver cada cuenta.';
    }
    cont.querySelector('#h-titulo').textContent = `Evolución de ${nombreIndicador(ind)}`;
    cont.querySelector('#h-sub').textContent = [S.indicadores[ind]?.descripcion, nota].filter(Boolean).join(' · ');
    const lienzo = cont.querySelector('#g-hist');
    const nuevo = document.createElement('canvas');
    nuevo.id = 'g-hist';
    lienzo.replaceWith(nuevo);
    destruirGraficos();
    if (series.length) graficoLineas(nuevo, { etiquetas: etiquetas.map(fmtPeriodo), series, formato, meta: metaUnica });
    else nuevo.replaceWith(Object.assign(document.createElement('div'), { id: 'g-hist', className: 'vacio', textContent: 'Sin datos para los filtros seleccionados.' }));
    cont.querySelector('#h-leyenda').innerHTML = series.length ? leyenda([...series, ...(metaUnica !== null ? [{ nombre: `Meta ${formato(metaUnica)}`, color: css('--muted'), dash: true }] : [])]) : '';
    tCmp.actualizar(comparar(filtrar(S.registros, { ...f, desde: '', hasta: '', s: '' }), cont.querySelector('#cmp-a').value, cont.querySelector('#cmp-b').value)
      .filter(x => !f.s || x.b?.s === f.s));
  };
  barraFiltros(cont.querySelector('#filtros'), { campos: ['e', 'p', 'l', 'c', 'i', 'desde', 'hasta', 's'], alCambiar: () => { if (!filtrosGlobales.i) filtrosGlobales.i = Object.keys(S.indicadores)[0]; pintar(); } });
  cont.querySelectorAll('#cmp-a, #cmp-b').forEach(s => s.addEventListener('change', pintar));
  pintar();
}

// ===================================================================== SEGUIMIENTO (bitácora de acciones)

const hoyISO = () => new Date().toISOString().slice(0, 10);
const vencida = a => a.estado !== 'cerrada' && a.fecha_compromiso && a.fecha_compromiso < hoyISO();
const ESTADOS_ACCION = [['abierta', 'Abierta'], ['en_curso', 'En curso'], ['cerrada', 'Cerrada']];
// Perfiles de cuenta que verán una acción (además del administrador).
const perfilesQueVen = l => S.perfiles.filter(p => !p.admin && (p.lineas || []).includes(l)).map(p => p.nombre);
const contextoAccion = a => [nombreUnidad(a.empresa_id, a.pais_id), a.linea_id && nombreLinea(a.linea_id), a.cuenta,
  a.indicador_id && nombreIndicador(a.indicador_id), a.periodo && fmtPeriodo(a.periodo)].filter(Boolean).join(' · ');

export async function seguimiento(cont) {
  const admin = esAdmin();
  if (!bitacoraEnLinea()) {
    cont.innerHTML = `${avisos()}<div class="tarjeta"><h2>Bitácora de acciones</h2>
      <p class="sub">La bitácora en línea todavía no está configurada. ${admin ? 'Sigue los pasos de "Bitácora en línea" en el README y publica de nuevo.' : 'Avísale al administrador.'}</p></div>`;
    return;
  }
  cont.innerHTML = `${avisos()}<div class="vacio">Cargando la bitácora…</div>`;
  try {
    await cargarBitacora();
  } catch (e) {
    cont.innerHTML = `<div class="aviso error"><b>No se pudo cargar la bitácora.</b> ${esc(e.message)}</div>`;
    return;
  }
  if (!cont.isConnected) return;
  let tab = admin ? 'cuentas' : 'mias';
  let estadoFiltro = 'pendientes';
  cont.innerHTML = `${avisos()}${admin ? '<div id="filtros"></div>' : ''}
    <div class="tarjeta">
      ${admin ? `<div class="tabs" role="tablist"><button data-tab="cuentas">Cuentas a seguir</button><button data-tab="bitacora">Bitácora de acciones</button></div>` : ''}
      <div id="panel"></div>
    </div>`;
  const panel = cont.querySelector('#panel');

  const filtrarAcciones = () => {
    const f = filtrosGlobales;
    return S.seguimiento.filter(a => (!admin || ((!f.e || a.empresa_id === f.e) && (!f.p || a.pais_id === f.p) && (!f.l || a.linea_id === f.l)
      && (!f.c || a.cuenta === f.c) && (!f.i || a.indicador_id === f.i)))
      && (estadoFiltro === 'todas' || (estadoFiltro === 'pendientes' ? a.estado !== 'cerrada' : estadoFiltro === 'vencidas' ? vencida(a) : a.estado === estadoFiltro)));
  };

  const pintar = () => {
    cont.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('activo', b.dataset.tab === tab));
    if (tab === 'cuentas') {
      const f = filtrosGlobales;
      const filas = ultimas(filtrar(S.registros, { ...f, s: '' })).filter(r => enRiesgo(r) && (!f.s || r.s === f.s))
        .map(r => ({ ...r, racha: racha(S.registros, r), acciones: accionesAbiertas(r), rel: brechaRel(r) }));
      panel.innerHTML = `<p class="sub">Última medición en estado Alerta o Crítico. "Periodos seguidos" indica cuántos meses consecutivos lleva sin cumplir la meta. Usa "+ Crear acción" para asignar un plan.</p><div id="t"></div>`;
      tabla(panel.querySelector('#t'), {
        filas, porPagina: 50, orden: { id: 'rel', dir: 'asc' }, vacio: 'No hay cuentas que requieran seguimiento con estos filtros.',
        tarjeta: { titulo: r => `${esc(r.c)} · ${esc(nombreIndicador(r.i))}`, sub: r => esc(servicio(r)), omitir: ['u', 'c', 'i'] },
        columnas: [
          { id: 'u', titulo: 'Servicio', valor: r => servicio(r), render: r => esc(servicio(r)) },
          { id: 'c', titulo: 'Plataforma', render: r => `<b>${esc(r.c)}</b>` },
          { id: 'i', titulo: 'Indicador', render: r => esc(nombreIndicador(r.i)) },
          { id: 'per', titulo: 'Periodo', render: r => fmtPeriodo(r.per) },
          { id: 'v', titulo: 'Valor', num: true, render: r => fmt(r.v, r.i) },
          { id: 'm', titulo: 'Meta', num: true, render: r => fmt(r.m, r.i) },
          { id: 'rel', titulo: 'Brecha %', num: true, render: r => r.rel === null ? '—' : `<span class="delta-mal">${r.rel.toFixed(1)}%</span>` },
          { id: 'racha', titulo: 'Periodos seguidos', num: true, render: r => `${r.racha}${r.racha >= 3 ? ' ⚠' : ''}` },
          { id: 's', titulo: 'Estado', render: r => badge(r.s) },
          { id: 'acciones', titulo: 'Acciones abiertas', num: true },
          { id: 'x', titulo: '', sinOrden: true, render: r => `<button class="btn chico" data-seg='${esc(JSON.stringify({ e: r.e, p: r.p, l: r.l, c: r.c, i: r.i, per: r.per }))}'>+ Crear acción</button>` },
        ],
      });
      return;
    }
    const filas = filtrarAcciones();
    const cuenta = (est) => S.seguimiento.filter(a => est === 'vencidas' ? vencida(a) : est === 'pendientes' ? a.estado !== 'cerrada' : est === 'todas' || a.estado === est).length;
    panel.innerHTML = `<div class="cabecera">
        <div><h2 style="margin:0">${admin ? 'Bitácora de acciones' : 'Mis acciones'}</h2>
          <p class="sub" style="margin:4px 0 0">${admin ? 'Acciones de todas las cuentas, guardadas en línea.' : 'Acciones asignadas a tus cuentas. Usa "Actualizar avance" para cambiar el estado o contar cómo va.'}</p></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
          <div class="campo" style="min-width:170px"><label for="b-estado">Mostrar</label><select id="b-estado">
            ${[['pendientes', 'Pendientes'], ['vencidas', 'Vencidas'], ['abierta', 'Abiertas'], ['en_curso', 'En curso'], ['cerrada', 'Cerradas'], ['todas', 'Todas']]
              .map(([v, t]) => `<option value="${v}" ${v === estadoFiltro ? 'selected' : ''}>${t} (${cuenta(v)})</option>`).join('')}</select></div>
          <button class="btn" id="b-recargar" title="Traer los últimos cambios">↻ Actualizar</button>
          ${admin ? '<button class="btn primario" id="b-nueva">+ Nueva acción</button>' : ''}
        </div></div><div id="t"></div>`;
    tabla(panel.querySelector('#t'), {
      filas, porPagina: 50, orden: { id: 'fecha_compromiso', dir: 'asc' },
      vacio: admin ? 'No hay acciones con estos filtros.' : 'No tienes acciones en esta vista.',
      tarjeta: { titulo: a => esc(a.accion || a.observacion || 'Acción'), sub: a => esc(contextoAccion(a)), omitir: ['u', 'accion'] },
      columnas: [
        { id: 'u', titulo: 'Cuenta', valor: a => contextoAccion(a), render: a => `${esc(nombreLinea(a.linea_id))}<br><small style="color:var(--muted)">${esc(a.cuenta)}${a.indicador_id ? ' · ' + esc(nombreIndicador(a.indicador_id)) : ''}${a.periodo ? ' · ' + fmtPeriodo(a.periodo) : ''}</small>` },
        { id: 'observacion', titulo: 'Observación', clase: 'texto' },
        { id: 'accion', titulo: 'Acción', clase: 'texto' },
        { id: 'responsable', titulo: 'Responsable' },
        { id: 'fecha_compromiso', titulo: 'Compromiso', render: a => esc(a.fecha_compromiso || '—') + (vencida(a) ? ' <span class="delta-mal">vencida</span>' : '') },
        { id: 'estado', titulo: 'Estado', render: a => badge(a.estado) },
        { id: 'avance', titulo: 'Último avance', clase: 'texto', render: a => esc(a.avance || '—') },
        { id: 'actualizado', titulo: 'Actualizado', render: a => esc((a.actualizado || '').replace('T', ' ').slice(0, 16)) },
        ...(admin ? [{ id: 'visible', titulo: 'Visible para', clase: 'texto', valor: a => perfilesQueVen(a.linea_id).join(', '),
          render: a => esc(perfilesQueVen(a.linea_id).join(', ') || 'Solo administrador') }] : []),
        { id: 'x', titulo: '', sinOrden: true, render: a => `<div style="display:flex;gap:6px;flex-wrap:wrap">
            <button class="btn chico ${admin ? '' : 'primario'}" data-avance="${esc(a.id)}">Actualizar avance</button>
            ${admin ? `<button class="btn chico" data-editar="${esc(a.id)}">Editar</button>` : ''}
            <button class="btn chico" data-historial="${esc(a.id)}">Historial</button>
            ${admin ? `<button class="btn chico" data-eliminar="${esc(a.id)}">Eliminar</button>` : ''}</div>` },
      ],
    });
    panel.querySelector('#b-estado').addEventListener('change', ev => { estadoFiltro = ev.target.value; pintar(); });
    panel.querySelector('#b-recargar').addEventListener('click', recargar);
    panel.querySelector('#b-nueva')?.addEventListener('click', () => {
      const f = filtrosGlobales;
      abrirSeguimiento({ e: f.e, p: f.p, l: f.l, c: f.c, i: f.i }).then(ok => ok && pintar());
    });
  };

  async function recargar() {
    panel.innerHTML = '<div class="vacio">Actualizando…</div>';
    try { await cargarBitacora(); } catch (e) { alert(e.message); }
    pintar();
  }

  panel.addEventListener('click', async ev => {
    const btn = ev.target.closest('[data-seg],[data-editar],[data-avance],[data-historial],[data-eliminar]');
    if (!btn) return;
    const buscar = id => S.seguimiento.find(a => a.id === id);
    if (btn.dataset.seg) { if (await abrirSeguimiento(JSON.parse(btn.dataset.seg))) { tab = 'bitacora'; pintar(); } }
    else if (btn.dataset.editar) { if (await abrirSeguimiento(null, buscar(btn.dataset.editar))) pintar(); }
    else if (btn.dataset.avance) { if (await abrirSeguimiento(null, buscar(btn.dataset.avance), 'avance')) pintar(); }
    else if (btn.dataset.historial) { verHistorial(buscar(btn.dataset.historial)); }
    else if (btn.dataset.eliminar) {
      const a = buscar(btn.dataset.eliminar);
      if (!confirm(`¿Eliminar la acción "${a.accion || a.observacion}"? Queda registrada en el historial.`)) return;
      btn.disabled = true;
      try { await eliminarAccion(a.id); S.seguimiento = S.seguimiento.filter(x => x.id !== a.id); pintar(); } catch (e) { alert(e.message); btn.disabled = false; }
    }
  });
  cont.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { tab = b.dataset.tab; pintar(); }));
  if (admin) barraFiltros(cont.querySelector('#filtros'), { campos: ['e', 'p', 'l', 'c', 'i', 's'], alCambiar: pintar });
  pintar();
}

async function verHistorial(a) {
  const dlg = document.getElementById('dlg-historial');
  dlg.querySelector('#h-contexto').textContent = `${a.accion || a.observacion} · ${contextoAccion(a)}`;
  const lista = dlg.querySelector('#h-lista');
  lista.innerHTML = '<p class="sub">Cargando…</p>';
  dlg.showModal();
  try {
    const h = await historialAccion(a.id);
    lista.innerHTML = h.length ? `<ul class="historial">${h.slice().reverse().map(x => `<li><b>${esc(x.cambio)}</b>${x.comentario ? `<br>${esc(x.comentario)}` : ''}
      <br><small>${esc((x.fecha || '').replace('T', ' ').slice(0, 16))} · ${esc(S.perfiles.find(p => p.id === x.perfil)?.nombre || x.perfil)}</small></li>`).join('')}</ul>` : '<p class="sub">Sin cambios registrados.</p>';
  } catch (e) { lista.innerHTML = `<div class="aviso error">${esc(e.message)}</div>`; }
}

// Diálogo de acciones. modo: 'crear' / 'editar' (administrador) o 'avance' (cualquier perfil: estado + comentario).
export function abrirSeguimiento(ctx, existente = null, modo = null) {
  modo = modo || (existente ? 'editar' : 'crear');
  const dlg = document.getElementById('dlg-seguimiento');
  const a = existente || { empresa_id: ctx.e, pais_id: ctx.p, linea_id: ctx.l || '', cuenta: ctx.c, indicador_id: ctx.i, periodo: ctx.per, estado: 'abierta' };
  if (modo === 'crear' && (!a.linea_id || !a.cuenta)) {
    alert('Elige primero un servicio y una cuenta en los filtros, o usa "+ Crear acción" en una cuenta de "Cuentas a seguir".');
    return Promise.resolve(false);
  }
  const avance = modo === 'avance';
  dlg.querySelector('#dlg-titulo').textContent = avance ? 'Actualizar avance' : modo === 'crear' ? 'Nueva acción' : 'Editar acción';
  const ven = perfilesQueVen(a.linea_id);
  dlg.querySelector('#dlg-contexto').textContent = contextoAccion(a)
    + (esAdmin() ? ` — La verá: ${ven.length ? ven.join(', ') : 'solo el administrador (ningún perfil tiene esta cuenta)'}` : '');
  const campos = { obs: 'observacion', acc: 'accion', resp: 'responsable', fecha: 'fecha_compromiso', estado: 'estado' };
  for (const [k, c] of Object.entries(campos)) {
    const el = dlg.querySelector(`#f-${k}`);
    el.value = a[c] || (k === 'estado' ? 'abierta' : '');
    const bloquear = avance && k !== 'estado';
    el.disabled = bloquear;
    el.closest('.campo').classList.toggle('solo-lectura', bloquear);
  }
  dlg.querySelector('#f-obs').required = !avance;
  const avanceCampo = dlg.querySelector('#f-avance');
  avanceCampo.value = '';
  avanceCampo.closest('.campo').hidden = modo === 'crear';
  const error = dlg.querySelector('#dlg-error');
  error.hidden = true;
  dlg.returnValue = '';
  dlg.showModal();
  return new Promise(res => {
    const form = dlg.querySelector('#form-seguimiento');
    const alEnviar = async ev => {
      if (ev.submitter?.value !== 'guardar') return;          // "Cancelar" cierra normal
      ev.preventDefault();
      const btn = ev.submitter;
      btn.disabled = true; btn.textContent = 'Guardando…';
      const valor = id => dlg.querySelector(id).value.trim();
      try {
        if (modo === 'crear') {
          const nueva = await crearAccion({ ...a, observacion: valor('#f-obs'), accion: valor('#f-acc'), responsable: valor('#f-resp'),
            fecha_compromiso: valor('#f-fecha'), estado: valor('#f-estado') });
          S.seguimiento.unshift(nueva);
        } else {
          const cambios = avance ? { estado: valor('#f-estado'), avance: valor('#f-avance') }
            : { observacion: valor('#f-obs'), accion: valor('#f-acc'), responsable: valor('#f-resp'), fecha_compromiso: valor('#f-fecha'),
              estado: valor('#f-estado'), ...(valor('#f-avance') ? { avance: valor('#f-avance') } : {}) };
          const nueva = await actualizarAccion(a.id, cambios);
          S.seguimiento = S.seguimiento.map(x => x.id === a.id ? nueva : x);
        }
        form.removeEventListener('submit', alEnviar);
        dlg.close('guardado');
        res(true);
      } catch (e) {
        error.textContent = e.message; error.hidden = false;
      } finally {
        btn.disabled = false; btn.textContent = 'Guardar';
      }
    };
    form.addEventListener('submit', alEnviar);
    dlg.addEventListener('close', () => { form.removeEventListener('submit', alEnviar); if (dlg.returnValue !== 'guardado') res(false); }, { once: true });
  });
}

// ===================================================================== CALIDAD DE DATOS

export function calidad(cont) {
  const { cargas = [], errores = [] } = S.resumen;
  const procesadas = cargas.filter(c => c.estado !== 'OMITIDO_YA_PROCESADO');
  const suma = k => procesadas.reduce((a, c) => a + (+c[k] || 0), 0);
  cont.innerHTML = `<div class="grid g-kpi">
      ${kpi({ etiqueta: 'Cargas procesadas', valor: fmtN(procesadas.length), detalle: `${cargas.length - procesadas.length} archivos omitidos por ya procesados` })}
      ${kpi({ etiqueta: 'Mediciones en histórico', valor: fmtN(S.resumen.total_historico), detalle: `${fmtN(S.resumen.total_vigentes)} vigentes (resto: versiones anteriores)` })}
      ${kpi({ etiqueta: 'Registros con error', valor: fmtN(suma('errores')), detalle: 'En las últimas cargas', clase: suma('errores') ? 'critico' : '' })}
      ${kpi({ etiqueta: 'Conflictos con histórico', valor: fmtN(suma('conflictos')), detalle: 'Periodos cerrados no sobrescritos' })}
    </div>
    <div class="tarjeta" style="margin-bottom:16px"><h2>Registro de cargas</h2><p class="sub">Resultado de cada archivo procesado por el ETL (data/cargas/registro_cargas.csv)</p><div id="t-cargas"></div></div>
    <div class="tarjeta" style="margin-bottom:16px"><div class="cabecera"><div><h2>Validación contra los dashboards</h2>
      <p class="sub" style="margin:0">${S.validacion ? `Cada indicador mensual recalculado con la fórmula de su dashboard (index.html local) y comparado con Calidad A365 · ${esc(S.validacion.generado.replace('T', ' ').slice(0, 16))}` : 'Ejecute <code>python etl/validar_dashboards.py</code> para generar la validación.'}</p></div></div>
      <div id="t-val-res"></div><div id="t-val" style="margin-top:12px"></div></div>
    <div class="tarjeta"><div class="cabecera"><div><h2>Errores detectados</h2><p class="sub" style="margin:0">Detalle por fila de Excel (data/cargas/errores/)</p></div>
      <button class="btn" id="btn-err">Exportar CSV</button></div><div id="t-err"></div></div>`;
  const ESTADO_CARGA = { OK: 'OK', OK_CON_ERRORES: 'ALERTA', ERROR: 'CRITICO', OMITIDO_YA_PROCESADO: 'SIN_META' };
  tabla(cont.querySelector('#t-cargas'), {
    filas: cargas, porPagina: 20,
    columnas: [
      { id: 'fecha_carga', titulo: 'Fecha', render: c => esc(c.fecha_carga.replace('T', ' ')) },
      { id: 'fuente_id', titulo: 'Fuente' },
      { id: 'archivo', titulo: 'Archivo', render: c => esc(c.archivo.split('/').pop()) },
      { id: 'estado', titulo: 'Estado', render: c => `<span class="estado ${ESTADO_CARGA[c.estado] || ''}">${esc(c.estado.replaceAll('_', ' ').toLowerCase())}</span>` },
      ...['filas_leidas', 'mediciones_validas', 'nuevas', 'versionadas', 'duplicadas', 'conflictos', 'errores'].map(k => ({ id: k, titulo: k.replace('_', ' '), num: true, valor: c => +c[k] || 0 })),
    ],
  });
  if (S.validacion) {
    tabla(cont.querySelector('#t-val-res'), {
      filas: S.validacion.resumen.filter(r => !r.error), porPagina: 20,
      columnas: [
        { id: 'linea', titulo: 'Servicio', render: r => esc(servicioDe(r.linea)) },
        { id: 'index_html', titulo: 'index.html del dashboard', render: r => esc((r.index_html || '').replace('T', ' ')) },
        { id: 'coinciden', titulo: 'Coinciden', num: true },
        { id: 'difieren', titulo: 'Difieren', num: true, render: r => r.difieren ? `<span class="delta-mal">${r.difieren}</span>` : '0' },
      ],
    });
    tabla(cont.querySelector('#t-val'), {
      filas: S.validacion.comparaciones.filter(c => c.estado !== 'OK'), porPagina: 15, vacio: 'Todos los indicadores coinciden.',
      columnas: [
        { id: 'linea', titulo: 'Servicio', render: c => esc(servicioDe(c.linea)) },
        { id: 'periodo', titulo: 'Periodo', render: c => fmtPeriodo(c.periodo) },
        { id: 'indicador', titulo: 'Indicador', render: c => esc(nombreIndicador(c.indicador)) },
        { id: 'dashboard', titulo: 'Dashboard', num: true, render: c => fmt(c.dashboard, c.indicador) },
        { id: 'central', titulo: 'Calidad A365', num: true, render: c => fmt(c.central, c.indicador) },
        { id: 'estado', titulo: 'Estado', render: c => c.estado === 'SOLO_DASHBOARD' ? '<span class="pendiente">solo en el dashboard</span>' : '<span class="estado ALERTA">diferente</span>' },
      ],
    });
  }
  const colsErr = ['fuente_id', 'archivo', 'fila_excel', 'campo', 'tipo_error', 'valor', 'detalle'].map(k => ({ id: k, titulo: k.replace('_', ' '), clase: k === 'detalle' ? 'texto' : '', render: k === 'archivo' ? e => esc(e.archivo.split('/').pop()) : undefined }));
  tabla(cont.querySelector('#t-err'), { filas: errores, porPagina: 25, columnas: colsErr, vacio: 'Sin errores en las últimas cargas.' });
  cont.querySelector('#btn-err').addEventListener('click', () => descargar('central_errores.csv', aCSV(errores, colsErr.map(c => ({ ...c, render: undefined }))), 'text/csv;charset=utf-8'));
}
