// CENTRAL · componentes reutilizables: KPI, estado, tabla, filtros y gráficos.
import { S, esc, fmtPeriodo, nombreEmpresa, nombrePais, nombreIndicador, opciones, periodos, unidades, lineas } from './datos.js';

export const ETIQUETA_ESTADO = { OK: 'Cumple', ALERTA: 'Alerta', CRITICO: 'Crítico', SIN_META: 'Sin meta', abierta: 'Abierta', en_curso: 'En curso', cerrada: 'Cerrada' };

export const badge = s => `<span class="estado ${esc(s)}">${esc(ETIQUETA_ESTADO[s] ?? s)}</span>`;

export function kpi({ etiqueta, valor, detalle = '', clase = '' }) {
  return `<div class="tarjeta kpi ${clase}"><div class="etq">${etiqueta}</div><div class="valor">${valor}</div><div class="det">${detalle}</div></div>`;
}

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ---------- tabla con orden y paginación

export function tabla(cont, { columnas, filas, porPagina = 50, orden = null, vacio = 'Sin datos para los filtros seleccionados.' }) {
  let pagina = 0;
  let ord = orden ? { ...orden } : null;

  function valorOrden(col, f) {
    return col.valor ? col.valor(f) : f[col.id];
  }

  function pintar() {
    let datos = filas;
    if (ord) {
      const col = columnas.find(c => c.id === ord.id);
      datos = [...filas].sort((a, b) => {
        const x = valorOrden(col, a), y = valorOrden(col, b);
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        const r = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es');
        return ord.dir === 'desc' ? -r : r;
      });
    }
    const total = datos.length;
    const paginas = Math.max(1, Math.ceil(total / porPagina));
    pagina = Math.min(pagina, paginas - 1);
    const vista = datos.slice(pagina * porPagina, (pagina + 1) * porPagina);
    const flecha = c => (ord?.id === c.id ? (ord.dir === 'asc' ? ' ▲' : ' ▼') : '');
    cont.innerHTML = total === 0 ? `<div class="tabla-wrap"><div class="vacio">${vacio}</div></div>` : `
      <div class="tabla-wrap"><table>
        <thead><tr>${columnas.map(c => `<th class="${c.num ? 'num' : ''} ${c.sinOrden ? '' : 'ordenable'}" data-col="${c.id}" scope="col">${c.titulo}${flecha(c)}</th>`).join('')}</tr></thead>
        <tbody>${vista.map(f => `<tr>${columnas.map(c => `<td class="${c.num ? 'num' : ''} ${c.clase ?? ''}">${c.render ? c.render(f) : esc(f[c.id])}</td>`).join('')}</tr>`).join('')}</tbody>
      </table></div>
      ${paginas > 1 || total > 10 ? `<div class="paginacion"><span>${total.toLocaleString('es')} filas · página ${pagina + 1} de ${paginas}</span>
        <span><button class="btn chico" data-pag="-1" ${pagina === 0 ? 'disabled' : ''}>‹ Anterior</button>
        <button class="btn chico" data-pag="1" ${pagina >= paginas - 1 ? 'disabled' : ''}>Siguiente ›</button></span></div>` : ''}`;
    cont.querySelectorAll('th.ordenable').forEach(th => th.addEventListener('click', () => {
      const id = th.dataset.col;
      ord = ord?.id === id ? { id, dir: ord.dir === 'asc' ? 'desc' : 'asc' } : { id, dir: 'asc' };
      pintar();
    }));
    cont.querySelectorAll('[data-pag]').forEach(b => b.addEventListener('click', () => { pagina += +b.dataset.pag; pintar(); }));
  }
  pintar();
  return { actualizar(nuevas) { filas = nuevas; pagina = 0; pintar(); } };
}

// ---------- barra de filtros (estado compartido entre vistas)

export const filtrosGlobales = { e: '', p: '', l: '', c: '', i: '', desde: '', hasta: '', s: '' };

const CAMPOS = {
  e: 'Empresa', p: 'País', l: 'Servicio', c: 'Cuenta', i: 'Indicador', desde: 'Desde', hasta: 'Hasta', s: 'Estado',
};

export function barraFiltros(cont, { campos = ['e', 'p', 'l', 'c', 'i', 'desde', 'hasta', 's'], fijos = {}, valores = filtrosGlobales, alCambiar, extra = '' }) {
  function pintar() {
    Object.assign(valores, fijos);
    const base = S.registros;
    const porEmpresa = base.filter(r => !valores.e || r.e === valores.e);
    const porPais = porEmpresa.filter(r => (!valores.p || r.p === valores.p) && (!valores.l || r.l === valores.l));
    const pers = periodos();
    const op = {
      e: [...new Set(unidades().map(u => u.e))].map(v => [v, nombreEmpresa(v)]),
      p: [...new Set(unidades().filter(u => !valores.e || u.e === valores.e).map(u => `${u.p}`))].map(v => [v, nombrePais(valores.e || unidades().find(u => u.p === v).e, v)]),
      l: lineas().filter(x => (!valores.e || x.e === valores.e) && (!valores.p || x.p === valores.p))
        .map(x => [x.l, unidades().filter(u => u.e === x.e).length > 1 || !valores.e ? `${x.unidad.nombre} · ${x.servicio}` : x.servicio]),
      c: opciones(porPais, 'c').map(v => [v, v]),
      i: Object.keys(S.indicadores).map(v => [v, nombreIndicador(v)]),
      desde: pers.map(v => [v, fmtPeriodo(v)]),
      hasta: pers.map(v => [v, fmtPeriodo(v)]),
      s: ['OK', 'ALERTA', 'CRITICO', 'SIN_META'].map(v => [v, ETIQUETA_ESTADO[v]]),
    };
    for (const k of ['p', 'l', 'c']) if (valores[k] && !op[k].some(([v]) => v === valores[k])) valores[k] = '';
    cont.innerHTML = `<div class="tarjeta filtros">
      ${campos.filter(k => !(k in fijos)).map(k => `<div class="campo"><label for="flt-${k}">${CAMPOS[k]}</label>
        <select id="flt-${k}" data-k="${k}"><option value="">${k === 'desde' || k === 'hasta' ? '—' : 'Todos'}</option>
        ${op[k].map(([v, t]) => `<option value="${esc(v)}" ${valores[k] === v ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></div>`).join('')}
      <div class="acciones"><button class="btn" data-limpiar>Limpiar</button>${extra}</div>
    </div>`;
    cont.querySelectorAll('select').forEach(sel => sel.addEventListener('change', () => {
      valores[sel.dataset.k] = sel.value;
      if (sel.dataset.k === 'e') { valores.p = ''; valores.l = ''; valores.c = ''; }
      if (sel.dataset.k === 'p') { valores.l = ''; valores.c = ''; }
      if (sel.dataset.k === 'l') valores.c = '';
      pintar();
      alCambiar();
    }));
    cont.querySelector('[data-limpiar]').addEventListener('click', () => {
      for (const k of campos) if (!(k in fijos)) valores[k] = '';
      pintar();
      alCambiar();
    });
  }
  pintar();
}

// ---------- gráficos (Chart.js)

const graficos = [];
export function destruirGraficos() { while (graficos.length) graficos.pop().destroy(); }

export const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
export const serie = n => css(`--s${(n % 8) + 1}`);

function baseOpciones() {
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink-2'),
        borderColor: css('--axis'), borderWidth: 1, padding: 10, boxPadding: 4, usePointStyle: true,
      },
    },
    scales: {
      x: { grid: { display: false }, border: { color: css('--axis') }, ticks: { color: css('--muted') } },
      y: { grid: { color: css('--grid') }, border: { display: false }, ticks: { color: css('--muted') } },
    },
  };
}

export function graficoLineas(canvas, { etiquetas, series, formato, meta = null }) {
  if (!window.Chart) return sinLibreria(canvas);
  const op = baseOpciones();
  op.plugins.tooltip.callbacks = { label: c => ` ${c.dataset.label}: ${formato(c.parsed.y)}` };
  op.scales.y.ticks.callback = v => formato(v);
  const datasets = series.map(s => ({
    label: s.nombre, data: s.datos, borderColor: s.color, backgroundColor: s.color,
    borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, pointBorderColor: css('--surface'), pointBorderWidth: 2,
    tension: 0, spanGaps: true,
  }));
  if (meta !== null) datasets.push({ label: 'Meta', data: etiquetas.map(() => meta), borderColor: css('--muted'), borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 0 });
  graficos.push(new Chart(canvas, { type: 'line', data: { labels: etiquetas, datasets }, options: op }));
}

export function graficoBarrasApiladas(canvas, { etiquetas, series }) {
  if (!window.Chart) return sinLibreria(canvas);
  const op = baseOpciones();
  op.indexAxis = 'y';
  op.interaction = { mode: 'nearest', intersect: true };
  op.scales.x = { stacked: true, max: 100, grid: { color: css('--grid') }, border: { display: false }, ticks: { color: css('--muted'), callback: v => `${v}%` } };
  op.scales.y = { stacked: true, grid: { display: false }, border: { color: css('--axis') }, ticks: { color: css('--ink-2') } };
  op.plugins.tooltip.callbacks = { label: c => ` ${c.dataset.label}: ${Math.round(c.parsed.x)}% (${c.dataset.conteos[c.dataIndex]} mediciones)` };
  const datasets = series.map(s => ({
    label: s.nombre, data: s.datos, conteos: s.conteos, backgroundColor: s.color,
    borderColor: css('--surface'), borderWidth: { left: 1, right: 1 }, borderSkipped: false, borderRadius: 3, barThickness: 22,
  }));
  graficos.push(new Chart(canvas, { type: 'bar', data: { labels: etiquetas, datasets }, options: op }));
}

function sinLibreria(canvas) {
  canvas.replaceWith(h('<div class="vacio">No se pudo cargar la librería de gráficos (sin conexión al CDN). Use la vista de tabla.</div>'));
}

export function leyenda(items, cuadro = false) {
  return `<div class="leyenda">${items.map(x => `<span><i class="${cuadro ? 'cuadro' : ''}" style="background:${x.color}${x.dash ? ';background:repeating-linear-gradient(90deg,' + x.color + ' 0 4px,transparent 4px 7px)' : ''}"></i>${esc(x.nombre)}</span>`).join('')}</div>`;
}
