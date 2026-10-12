// CENTRAL · arranque, navegación por hash y tema.
import { S, cargar, unidades, esc } from './datos.js';
import { destruirGraficos } from './componentes.js';
import * as V from './vistas.js';
import * as G from './general.js';

const RUTAS = {
  general: { titulo: 'Vista general', vista: G.general },
  ver: { titulo: 'Dashboards', vista: G.visor },
  empresa: { titulo: null, vista: V.empresa },
  seguimiento: { titulo: 'Seguimiento de cuentas', vista: V.seguimiento },
  indicadores: { titulo: 'Tabla consolidada', vista: V.indicadores },
  historico: { titulo: 'Histórico y evolución', vista: V.historico },
  calidad: { titulo: 'Calidad de datos', vista: V.calidad },
};

function menu() {
  const enlace = (href, texto, extra = '', punto = '') =>
    `<a href="${href}" data-ruta="${href}"><span class="item">${punto}${texto}</span>${extra}</a>`;
  document.getElementById('nav').innerHTML = `
    ${enlace('#/general', 'Vista general')}
    ${enlace('#/ver', 'Dashboards')}
    <div class="nav-grupo">Empresas</div>
    ${unidades().map(u => enlace(`#/empresa/${u.e}/${u.p}`, esc(u.nombre), u.proximamente ? '<span class="chip-prox">Próximamente</span>' : '',
      `<span class="punto" style="background:${esc(u.color)}"></span>`)).join('')}
    <div class="nav-grupo">Análisis</div>
    ${enlace('#/seguimiento', 'Seguimiento de cuentas')}
    ${enlace('#/indicadores', 'Tabla consolidada')}
    ${enlace('#/historico', 'Histórico y evolución')}
    <div class="nav-grupo">Operación</div>
    ${enlace('#/calidad', 'Calidad de datos')}`;
  document.getElementById('pie-sidebar').textContent = S.portal.plataforma.organizacion;
}

function navegar() {
  const [ruta = 'general', ...params] = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  const def = RUTAS[ruta] || RUTAS.general;
  const cont = document.getElementById('vista');
  destruirGraficos();
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('activo', location.hash.startsWith(a.dataset.ruta) || (!location.hash && a.dataset.ruta === '#/general')));
  const titulo = def.titulo ?? (unidades().find(u => u.e === params[0] && u.p === params[1])?.nombre || 'Empresa');
  document.getElementById('titulo').textContent = titulo;
  document.title = `${titulo} · CENTRAL`;
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
  document.getElementById('btn-menu').addEventListener('click', () => document.getElementById('app').classList.toggle('menu-abierto'));
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
