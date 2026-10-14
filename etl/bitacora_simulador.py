"""
Simulador local de la bitácora en línea (mismo protocolo y permisos que etl/bitacora_codigo.gs).
Sirve para probar la página sin publicar el script de Google:

    python etl/bitacora_simulador.py                 # escucha en http://localhost:8791
    python etl/perfiles.py bitacora-url http://localhost:8791

Guarda las acciones en bitacora/simulada.json (solo en este PC).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CODIGO = RAIZ / "bitacora" / "Codigo.gs"
ALMACEN = RAIZ / "bitacora" / "simulada.json"
COLUMNAS = ["id", "empresa_id", "pais_id", "linea_id", "cuenta", "indicador_id", "periodo", "observacion", "accion",
            "responsable", "fecha_compromiso", "prioridad", "estado", "avance", "creado", "creado_por", "actualizado", "actualizado_por"]
SISTEMA = {"id", "creado", "creado_por", "actualizado", "actualizado_por"}
ESTADOS = {"abierta", "en_curso", "cerrada"}
EDITABLES_PERFIL = ["estado", "avance"]


def config():
    m = re.search(r"/\*CONFIG\*/(.*?)/\*FIN_CONFIG\*/", CODIGO.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))


def leer():
    return json.loads(ALMACEN.read_text(encoding="utf-8")) if ALMACEN.exists() else {"acciones": [], "historial": []}


def guardar(d):
    ALMACEN.parent.mkdir(parents=True, exist_ok=True)
    ALMACEN.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def ahora():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def limpiar(obj, permitidos=None):
    permitidos = permitidos or [c for c in COLUMNAS if c not in SISTEMA]
    out = {c: str(obj[c])[:2000].strip() for c in permitidos if obj and c in obj and obj[c] is not None}
    if out.get("estado") and out["estado"] not in ESTADOS:
        raise ValueError("Estado no válido")
    return out


def manejar(p):
    c = config()["perfiles"].get(p.get("perfil"))
    if not c or not p.get("token") or hashlib.sha256(p["token"].encode()).hexdigest() != c["hash"]:
        raise PermissionError("No autorizado")
    admin, lineas, pid = c.get("admin"), c.get("lineas", []), p["perfil"]
    permitida = lambda a: admin or a.get("linea_id") in lineas
    d = leer()
    op = p.get("op")
    if op == "listar":
        return {"ok": True, "perfil": pid, "acciones": [a for a in d["acciones"] if permitida(a)]}
    if op == "historial":
        a = next((x for x in d["acciones"] if x["id"] == p.get("id")), None)
        if not a or not permitida(a):
            raise LookupError("Acción no encontrada")
        return {"ok": True, "historial": [h for h in d["historial"] if h["id"] == a["id"]]}
    if op == "crear":
        if not admin:
            raise PermissionError("Solo el administrador crea acciones")
        a = limpiar(p.get("accion"))
        if not a.get("linea_id") or not a.get("cuenta"):
            raise ValueError("Falta la cuenta de la acción")
        a.update(id="seg-" + uuid.uuid4().hex[:8], estado=a.get("estado") or "abierta",
                 creado=ahora(), actualizado=ahora(), creado_por=pid, actualizado_por=pid)
        d["acciones"].append(a)
        d["historial"].append({"fecha": ahora(), "id": a["id"], "perfil": pid, "cambio": "Acción creada", "comentario": a.get("accion", "")})
        guardar(d)
        return {"ok": True, "accion": a}
    a = next((x for x in d["acciones"] if x["id"] == p.get("id")), None)
    if not a or not permitida(a):
        raise LookupError("Acción no encontrada")
    if op == "actualizar":
        cambios = limpiar(p.get("cambios"), None if admin else EDITABLES_PERFIL)
        resumen = " · ".join(f"Estado: {a.get('estado')} → {cambios['estado']}" if k == "estado" else f"Editado: {k}"
                             for k in cambios if k != "avance" and cambios[k] != a.get(k)) or "Avance"
        a.update(cambios, actualizado=ahora(), actualizado_por=pid)
        d["historial"].append({"fecha": ahora(), "id": a["id"], "perfil": pid, "cambio": resumen, "comentario": cambios.get("avance", "")})
        guardar(d)
        return {"ok": True, "accion": a}
    if op == "eliminar":
        if not admin:
            raise PermissionError("Solo el administrador elimina acciones")
        d["acciones"] = [x for x in d["acciones"] if x["id"] != a["id"]]
        d["historial"].append({"fecha": ahora(), "id": a["id"], "perfil": pid, "cambio": "Acción eliminada", "comentario": ""})
        guardar(d)
        return {"ok": True}
    raise ValueError("Operación no válida")


class Manejador(BaseHTTPRequestHandler):
    def _responder(self, obj):
        cuerpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._responder({"ok": True, "servicio": "Bitácora Calidad A365 (simulador)"})

    def do_POST(self):
        try:
            p = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
            r = manejar(p)
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        self._responder(r)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    print(f"Simulador de la bitácora en http://localhost:{puerto}")
    ThreadingHTTPServer(("127.0.0.1", puerto), Manejador).serve_forever()
