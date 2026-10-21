// CENTRAL · Avance equipo: evaluaciones de cada monitor por franja horaria del día y duración de las llamadas.
import { S, esc, fmtN, linea, nombreLinea, descargar, aCSV } from './datos.js';

// Tiempo total en h:mm:ss (o m:ss si es menos de una hora)
const fmtDur = s => {
  if (s == null) return '—';
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
};
const fmtDia = d => new Date(`${d}T00:00`).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
// Suma de las duraciones conocidas; '*' si a alguna evaluación le falta la duración (descargas sin TMO)
const tiempo = evs => {
  const v = evs.map(f => f[4]).filter(x => x != null);
  const txt = v.length ? fmtDur(v.reduce((a, b) => a + b, 0)) : '—';
  return v.length < evs.length ? `<span title="${evs.length - v.length} evaluación(es) aún sin duración">${txt}*</span>` : txt;
};

// Franjas: [corte_i, corte_i+1); lo anterior al primer corte y lo posterior al último va en franjas abiertas.
function franjas(cortes) {
  const f = cortes.slice(0, -1).map((c, i) => ({ id: c, titulo: `${c}–${cortes[i + 1]}`, desde: c, hasta: cortes[i + 1] }));
  return [{ id: 'antes', titulo: `Antes de ${cortes[0]}`, desde: '00:00', hasta: cortes[0] }, ...f,
    { id: 'despues', titulo: `Desde ${cortes[cortes.length - 1]}`, desde: cortes[cortes.length - 1], hasta: '24:00' }];
}

export function avance(cont) {
  const A = S.avance;
  if (!A || !A.filas?.length) {
    cont.innerHTML = '<div class="vacio">Aún no hay datos de avance del equipo. Se generan al actualizar CENTRAL con las bases que traen la hora de cada evaluación.</div>';
    return;
  }
  const dias = [...new Set(A.filas.map(f => f[2]))].sort().reverse();
  const lineasCon = [...new Set(A.filas.map(f => f[0]))].sort((a, b) => nombreCompleto(a).localeCompare(nombreCompleto(b), 'es'));
  let dia = dias[0], lin = '', acumulado = false;

  cont.innerHTML = `
    <div class="tarjeta filtros">
      <div class="campo"><label for="av-dia">Día</label><select id="av-dia">${dias.map(d => `<option value="${d}">${esc(fmtDia(d))}</option>`).join('')}</select></div>
      <div class="campo"><label for="av-lin">Cuenta</label><select id="av-lin"><option value="">Todas</option>
        ${lineasCon.map(l => `<option value="${esc(l)}">${esc(nombreCompleto(l))}</option>`).join('')}</select></div>
      <div class="campo"><label for="av-modo">Conteo</label><select id="av-modo"><option value="">Por franja</option><option value="1">Acumulado al corte</option></select></div>
      <div class="acciones"><button class="btn" id="av-csv">Exportar CSV</button></div>
    </div>
    <div class="tarjeta"><div class="cabecera"><div><h2>Avance por monitor</h2><p class="sub" style="margin:0" id="av-res"></p></div></div>
      <div id="av-faltan"></div>
      <div id="av-tabla"></div>
      <p class="sub" style="margin-top:8px">Q = evaluaciones enviadas en la franja · Tiempo = suma de la duración de las llamadas evaluadas (h:mm:ss); * = alguna evaluación aún sin duración. Hora local de cada base.
      Las bases se actualizan cuando llega su archivo (Drive o carpetas): el día en curso se completa a medida que llegan.</p>
      <div id="av-fuentes"></div>
    </div>`;

  const pintar = () => {
    const F = franjas(A.cortes);
    // Franjas que seguían abiertas al momento de la extracción (solo el día de la extracción): conteo parcial
    const [diaExt, horaExt] = (A.generado || '').split('T');
    const enCurso = fr => dia === diaExt && fr.desde <= (horaExt || '').slice(0, 5) && fr.hasta > (horaExt || '').slice(0, 5);
    const filasDia = A.filas.filter(f => f[2] === dia && (!lin || f[0] === lin));
    const usadas = F.filter(fr => fr.id !== 'antes' && fr.id !== 'despues' || filasDia.some(f => f[3] >= fr.desde && f[3] < fr.hasta));
    const grupos = {};
    for (const f of filasDia) (grupos[`${f[0]}|${f[1]}`] ||= { l: f[0], monitor: f[1], evs: [] }).evs.push(f);
    const filas = Object.values(grupos).sort((a, b) => nombreCompleto(a.l).localeCompare(nombreCompleto(b.l), 'es') || a.monitor.localeCompare(b.monitor, 'es'));
    const celdas = evs => usadas.map(fr => {
      const sel = evs.filter(f => (acumulado ? f[3] < fr.hasta : f[3] >= fr.desde && f[3] < fr.hasta));
      return `<td class="num">${sel.length ? fmtN(sel.length) : '<span style="color:var(--muted)">—</span>'}</td><td class="num">${sel.length ? tiempo(sel) : ''}</td>`;
    }).join('');
    const total = evs => `<td class="num"><b>${fmtN(evs.length)}</b></td><td class="num"><b>${tiempo(evs)}</b></td>`;
    cont.querySelector('#av-res').textContent = `${fmtN(filasDia.length)} evaluaciones · ${filas.length} monitor${filas.length === 1 ? '' : 'es'} · ${fmtDia(dia)}`
      + (dia === diaExt ? ` · extracción de las ${horaExt.slice(0, 5)}` : '');
    cont.querySelector('#av-tabla').innerHTML = !filas.length ? '<div class="vacio">Sin evaluaciones ese día.</div>' : `
      <div class="tabla-wrap"><table class="tabla-eval tabla-avance">
        <thead><tr><th rowspan="2">Monitor</th>${usadas.map(fr => `<th colspan="2" class="franja ${enCurso(fr) ? 'en-curso' : ''}" ${enCurso(fr) ? `title="Extracción de las ${esc(horaExt.slice(0, 5))}: la franja aún no termina"` : ''}>${acumulado ? `Hasta ${fr.hasta === '24:00' ? 'fin del día' : fr.hasta}` : esc(fr.titulo)}${enCurso(fr) ? '<small>en curso</small>' : ''}</th>`).join('')}<th colspan="2" class="franja">Total del día</th></tr>
          <tr>${[...usadas, 0].map(() => '<th class="num">Q</th><th class="num">Tiempo</th>').join('')}</tr></thead>
        <tbody>${filas.map(g => `<tr><td><b>${esc(g.monitor)}</b><small>${esc(nombreCompleto(g.l))}</small></td>${celdas(g.evs)}${total(g.evs)}</tr>`).join('')}</tbody>
        ${filas.length > 1 ? `<tfoot><tr><td><b>Total</b></td>${celdas(filasDia)}${total(filasDia)}</tr></tfoot>` : ''}
      </table></div>`;
    // Cuentas sin evaluaciones ese día: casi siempre porque su base todavía no llega hasta esa fecha
    const conDatos = new Set(filasDia.map(f => f[0]));
    const faltan = lineasCon.filter(l => (!lin || l === lin) && !conDatos.has(l)).map(l => {
      const ult = (A.fuentes?.[l]?.ultima || '').slice(0, 10);
      return `${esc(nombreCompleto(l))}${ult && ult < dia ? ` (base hasta el ${esc(ult.slice(8, 10) + '/' + ult.slice(5, 7))})` : ''}`;
    });
    cont.querySelector('#av-faltan').innerHTML = faltan.length
      ? `<div class="aviso" style="margin-bottom:10px">Sin evaluaciones este día: ${faltan.join(' · ')}. Se completan cuando llegan sus bases.</div>` : '';
    const fuentes = Object.entries(A.fuentes || {}).filter(([l]) => !lin || l === lin);
    cont.querySelector('#av-fuentes').innerHTML = fuentes.length ? `<details class="sub" style="margin-top:8px"><summary>Bases usadas</summary><ul>
      ${fuentes.map(([l, x]) => `<li>${esc(nombreCompleto(l))}: ${esc(x.archivo)}${x.ultima ? ` · última evaluación ${esc(x.ultima)}` : ''}</li>`).join('')}</ul></details>` : '';
  };

  cont.querySelector('#av-dia').addEventListener('change', e => { dia = e.target.value; pintar(); });
  cont.querySelector('#av-lin').addEventListener('change', e => { lin = e.target.value; pintar(); });
  cont.querySelector('#av-modo').addEventListener('change', e => { acumulado = !!e.target.value; pintar(); });
  cont.querySelector('#av-csv').addEventListener('click', () => {
    const filas = A.filas.filter(f => f[2] === dia && (!lin || f[0] === lin))
      .map(f => ({ cuenta: nombreCompleto(f[0]), monitor: f[1], fecha: f[2], hora: f[3], duracion_seg: f[4] }));
    descargar(`avance_equipo_${dia}.csv`, aCSV(filas, ['cuenta', 'monitor', 'fecha', 'hora', 'duracion_seg'].map(id => ({ id, titulo: id }))), 'text/csv;charset=utf-8');
  });
  pintar();
}

function nombreCompleto(l) {
  const x = linea(l);
  return x ? `${x.unidad.nombre} · ${x.servicio}` : nombreLinea(l);
}
