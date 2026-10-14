// CENTRAL · arranque, navegación por hash y tema.
import { S, cargar, unidades, lineas, esc } from './datos.js';
import { destruirGraficos } from './componentes.js';
import * as V from './vistas.js';
import * as G from './general.js';

const RUTAS = {
  general: { titulo: 'Vista general', vista: G.general },
  ver: { titulo: 'Dashboards', vista: G.visor },
  kpis: { titulo: 'KPI por cuenta', vista: G.kpis },
  servicio: { titulo: null, vista: G.servicio },
  empresa: { titulo: null, vista: V.empresa },
  seguimiento: { titulo: 'Seguimiento de cuentas', vista: V.seguimiento },
  indicadores: { titulo: 'Tabla consolidada', vista: V.indicadores },
  historico: { titulo: 'Histórico y evolución', vista: V.historico },
  calidad: { titulo: 'Calidad de datos', vista: V.calidad },
};

// Menú por módulos. En "Clientes" cada empresa se despliega con sus cuentas como submódulos.
function menu() {
  const enlace = (href, texto, extra = '', punto = '', clase = '') =>
    `<a href="${href}" data-ruta="${href}" class="${clase}"><span class="item">${punto}${texto}</span>${extra}</a>`;
  const tieneDatos = l => S.totales.some(z => z.l === l);
  const empresa = u => u.proximamente
    ? enlace(`#/empresa/${u.e}/${u.p}`, esc(u.nombre), '<span class="chip-prox">Próximamente</span>', `<span class="punto" style="background:${esc(u.color)}"></span>`)
    : `<details class="nav-emp" data-emp="${u.e}/${u.p}">
        <summary><span class="item"><span class="punto" style="background:${esc(u.color)}"></span>${esc(u.nombre)}</span></summary>
        ${enlace(`#/empresa/${u.e}/${u.p}`, 'Resumen de la empresa', '', '', 'sub')}
        ${lineas().filter(x => x.e === u.e && x.p === u.p).map(x => tieneDatos(x.l)
          ? enlace(`#/servicio/${x.id}`, esc(x.servicio), '', '', 'sub')
          : enlace(`#/ver/${x.id}`, esc(x.servicio), '<span class="chip-prox">Dashboard</span>', '', 'sub')).join('')}
      </details>`;
  document.getElementById('nav').innerHTML = `
    <div class="nav-grupo">Inicio</div>
    ${enlace('#/general', 'Vista general')}
    <div class="nav-grupo">Clientes</div>
    ${unidades().map(empresa).join('')}
    <div class="nav-grupo">Análisis</div>
    ${enlace('#/historico', 'Histórico y evolución')}
    ${enlace('#/indicadores', 'Tabla consolidada')}
    <div class="nav-grupo">Gestión</div>
    ${enlace('#/seguimiento', 'Seguimiento de cuentas')}
    <div class="nav-grupo">Herramientas</div>
    ${enlace('#/ver', 'Dashboards')}
    ${enlace('#/calidad', 'Calidad de datos')}`;
  document.getElementById('pie-sidebar').textContent = S.portal.plataforma.organizacion;
}

function navegar() {
  const [ruta = 'general', ...params] = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const def = RUTAS[ruta] || RUTAS.general;
  const cont = document.getElementById('vista');
  destruirGraficos();
  // Enlace activo: coincidencia exacta de la ruta (o prefijo para el visor de dashboards); la cuenta activa
  // también marca "General" en la barra inferior del celular.
  const hash = location.hash || '#/general';
  document.querySelectorAll('#nav a, #nav-movil a').forEach(a => a.classList.toggle('activo',
    hash === a.dataset.ruta || (a.dataset.ruta === '#/ver' && ruta === 'ver')
    || (ruta === 'kpis' && a.dataset.ruta === '#/general')   // la tabla completa de KPI se abre desde Vista general
    || (a.closest('#nav-movil') && ruta === 'servicio' && a.dataset.ruta === '#/general')));
  // Se despliega la empresa de la cuenta o empresa que se está viendo
  const emp = ruta === 'empresa' ? `${params[0]}/${params[1]}`
    : ['servicio', 'ver'].includes(ruta) && params[0] ? (l => l && `${l.e}/${l.p}`)(lineas().find(x => x.id === params[0])) : null;
  document.querySelectorAll('#nav details.nav-emp').forEach(d => { if (d.dataset.emp === emp) d.open = true; });
  const srv = ruta === 'servicio' ? lineas().find(x => x.id === params[0]) : null;
  const titulo = def.titulo ?? (srv ? `${srv.unidad.nombre.split(' ')[0]} ${srv.servicio}`
    : unidades().find(u => u.e === params[0] && u.p === params[1])?.nombre || 'Empresa');
  document.getElementById('titulo').textContent = titulo;
  document.title = `${titulo} · ${S.portal?.plataforma?.nombre || 'Calidad A365'}`;
  document.getElementById('app').classList.remove('menu-abierto');
  try {
    def.vista(cont, params);
  } catch (e) {
    console.error(e);
    cont.innerHTML = `<div class="aviso error">Error al mostrar la vista: ${esc(e.message)}</div>`;
  }
  window.scrollTo(0, 0);
}

function tema() {
  const btn = document.getElementById('btn-tema');
  let guardado = null;
  try { guardado = localStorage.getItem('central.tema'); } catch { /* sin almacenamiento */ }
  if (guardado) document.documentElement.dataset.theme = guardado;
  btn.addEventListener('click', () => {
    const oscuroActual = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    const nuevo = oscuroActual ? 'light' : 'dark';
    document.documentElement.dataset.theme = nuevo;
    try { localStorage.setItem('central.tema', nuevo); } catch { /* sin almacenamiento */ }
    navegar();   // repinta los gráficos con los colores del tema
  });
}

async function iniciar() {
  tema();
  const app = document.getElementById('app');
  const alternarMenu = ev => { ev.stopPropagation(); app.classList.toggle('menu-abierto'); };
  document.getElementById('btn-menu').addEventListener('click', alternarMenu);
  document.getElementById('btn-menu-movil').addEventListener('click', alternarMenu);
  // Tocar fuera del menú lo cierra
  document.addEventListener('click', ev => {
    if (app.classList.contains('menu-abierto') && !ev.target.closest('#sidebar')) app.classList.remove('menu-abierto');
  });
  try {
    await cargar();
  } catch (e) {
    document.getElementById('vista').innerHTML = `<div class="aviso error"><b>No se pudo cargar la configuración.</b> ${esc(e.message)}<br>
      Si abrió el archivo directamente (file://), sirva la carpeta con <code>python -m http.server 8000</code> y entre a http://localhost:8000.</div>`;
    return;
  }
  menu();
  if (S.generado) document.getElementById('meta-datos').textContent = `Datos actualizados: ${S.generado.replace('T', ' ').slice(0, 16)}`;
  window.addEventListener('hashchange', navegar);
  navegar();
}

iniciar();
