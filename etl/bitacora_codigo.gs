/**
 * Calidad A365 · Bitácora de acciones en línea (Google Apps Script).
 *
 * Se pega en una hoja de Google (Extensiones › Apps Script) y se implementa como "Aplicación web"
 * (Ejecutar como: Yo · Quién tiene acceso: Cualquier usuario). La protección la da la clave de cada
 * perfil: este código solo guarda su huella SHA-256 (CONFIG), nunca la clave.
 *
 * Hojas que crea solas: "Acciones" (una fila por acción) e "Historial" (cada cambio).
 * Permisos: el administrador crea, edita y elimina; cada perfil solo ve las acciones de sus cuentas
 * y puede cambiar el estado y dejar un comentario de avance.
 *
 * NO editar CONFIG a mano: se regenera con  python etl/perfiles.py bitacora
 */
const CONFIG = /*CONFIG*/{}/*FIN_CONFIG*/;

const HOJA_ACCIONES = 'Acciones';
const HOJA_HISTORIAL = 'Historial';
const COLUMNAS = ['id', 'empresa_id', 'pais_id', 'linea_id', 'cuenta', 'indicador_id', 'periodo', 'observacion', 'accion',
  'responsable', 'fecha_compromiso', 'prioridad', 'estado', 'avance', 'creado', 'creado_por', 'actualizado', 'actualizado_por'];
const COLUMNAS_HISTORIAL = ['fecha', 'id', 'perfil', 'cambio', 'comentario'];
const SISTEMA = ['id', 'creado', 'creado_por', 'actualizado', 'actualizado_por'];
const ESTADOS = ['abierta', 'en_curso', 'cerrada'];
const EDITABLES_PERFIL = ['estado', 'avance'];

function doGet() {
  return responder({ ok: true, servicio: 'Bitácora Calidad A365' });
}

function doPost(e) {
  let r;
  try {
    r = manejar(JSON.parse(e.postData.contents));
  } catch (err) {
    r = { ok: false, error: String(err && err.message || err) };
  }
  return responder(r);
}

function responder(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function sha256(texto) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(texto), Utilities.Charset.UTF_8)
    .map(b => ('0' + (b & 255).toString(16)).slice(-2)).join('');
}

function autenticar(p) {
  const c = (CONFIG.perfiles || {})[p.perfil];
  if (!c || !p.token || sha256(p.token) !== c.hash) throw new Error('No autorizado');
  return { id: p.perfil, admin: !!c.admin, lineas: c.lineas || [] };
}

function hoja(nombre, columnas) {
  const ss = SpreadsheetApp.getActive();
  let h = ss.getSheetByName(nombre);
  if (!h) {
    h = ss.insertSheet(nombre);
    h.getRange(1, 1, 1, columnas.length).setValues([columnas]).setFontWeight('bold');
    h.setFrozenRows(1);
    h.getRange(1, 1, h.getMaxRows(), columnas.length).setNumberFormat('@');   // todo como texto
  }
  return h;
}

function leerAcciones() {
  const h = hoja(HOJA_ACCIONES, COLUMNAS);
  const v = h.getDataRange().getDisplayValues();
  const cab = v.shift() || COLUMNAS;
  return v.map((f, i) => ({ fila: i + 2, a: Object.fromEntries(cab.map((c, j) => [c, f[j]])) })).filter(x => x.a.id);
}

// Evita que un texto se interprete como fórmula en la hoja.
function texto(v) {
  const s = String(v == null ? '' : v).slice(0, 2000).trim();
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

function limpiar(obj, permitidos) {
  const out = {};
  (permitidos || COLUMNAS.filter(c => !SISTEMA.includes(c))).forEach(c => {
    if (obj && Object.prototype.hasOwnProperty.call(obj, c)) out[c] = texto(obj[c]);
  });
  if (out.estado && !ESTADOS.includes(out.estado)) throw new Error('Estado no válido');
  return out;
}

function registrar(id, perfil, cambio, comentario) {
  hoja(HOJA_HISTORIAL, COLUMNAS_HISTORIAL).appendRow([ahora(), id, perfil, texto(cambio), texto(comentario || '')]);
}

function ahora() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ss");
}

function manejar(p) {
  const u = autenticar(p);
  const permitida = a => u.admin || u.lineas.indexOf(a.linea_id) >= 0;
  if (p.op === 'listar') {
    return { ok: true, perfil: u.id, acciones: leerAcciones().map(x => x.a).filter(permitida) };
  }
  if (p.op === 'historial') {
    const accion = leerAcciones().find(x => x.a.id === p.id);
    if (!accion || !permitida(accion.a)) throw new Error('Acción no encontrada');
    const v = hoja(HOJA_HISTORIAL, COLUMNAS_HISTORIAL).getDataRange().getDisplayValues();
    v.shift();
    return { ok: true, historial: v.filter(f => f[1] === p.id).map(f => ({ fecha: f[0], perfil: f[2], cambio: f[3], comentario: f[4] })) };
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const h = hoja(HOJA_ACCIONES, COLUMNAS);
    if (p.op === 'crear') {
      if (!u.admin) throw new Error('Solo el administrador crea acciones');
      const a = limpiar(p.accion);
      if (!a.linea_id || !a.cuenta) throw new Error('Falta la cuenta de la acción');
      a.id = 'seg-' + Utilities.getUuid().slice(0, 8);
      a.estado = a.estado || 'abierta';
      a.creado = a.actualizado = ahora();
      a.creado_por = a.actualizado_por = u.id;
      h.appendRow(COLUMNAS.map(c => a[c] == null ? '' : a[c]));
      registrar(a.id, u.id, 'Acción creada', a.accion || a.observacion);
      return { ok: true, accion: a };
    }
    const f = leerAcciones().find(x => x.a.id === p.id);
    if (!f || !permitida(f.a)) throw new Error('Acción no encontrada');
    if (p.op === 'actualizar') {
      const cambios = limpiar(p.cambios, u.admin ? null : EDITABLES_PERFIL);
      const nuevo = Object.assign({}, f.a, cambios, { actualizado: ahora(), actualizado_por: u.id });
      h.getRange(f.fila, 1, 1, COLUMNAS.length).setValues([COLUMNAS.map(c => nuevo[c] == null ? '' : nuevo[c])]);
      const resumen = Object.keys(cambios).filter(c => c !== 'avance' && cambios[c] !== f.a[c])
        .map(c => c === 'estado' ? 'Estado: ' + f.a.estado + ' → ' + cambios.estado : 'Editado: ' + c).join(' · ') || 'Avance';
      registrar(f.a.id, u.id, resumen, cambios.avance);
      return { ok: true, accion: nuevo };
    }
    if (p.op === 'eliminar') {
      if (!u.admin) throw new Error('Solo el administrador elimina acciones');
      h.deleteRow(f.fila);
      registrar(f.a.id, u.id, 'Acción eliminada', f.a.accion);
      return { ok: true };
    }
    throw new Error('Operación no válida');
  } finally {
    lock.releaseLock();
  }
}
