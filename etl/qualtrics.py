"""Respuestas de Qualtrics (Claro Ecuador) directo por la API, para el módulo Avance equipo.

config/qualtrics.local.json (solo en el PC que hace la extracción; está en .gitignore):
    {"centro": "iad1" | "empresa.qualtrics.com", "token": "...", "zona": "America/Guayaquil",
     "encuestas": {"claro_ec_in_monitoreo": "SV_...", "claro_ec_out_monitoreo": "SV_..."}}
Se configura desde CalidadA365.exe › "Conectar Qualtrics (Claro)": el token se escribe en la consola y no se muestra.
Cada extracción baja en CSV las respuestas desde el inicio del periodo del avance a etl/entrada/qualtrics/<fuente>.csv,
con las mismas columnas que la exportación manual (etiquetas de las opciones y hora local de Ecuador).
"""
from __future__ import annotations

import getpass
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import central_etl as etl

CONFIG = etl.CONFIG / "qualtrics.local.json"
DESTINO = etl.RAIZ / "etl" / "entrada" / "qualtrics"


def leer_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    except ValueError:
        return {}


def _base(centro: str) -> str:
    centro = centro.strip().replace("https://", "").rstrip("/")
    return f"https://{centro if '.' in centro else centro + '.qualtrics.com'}/API/v3"


def _api(cfg: dict, ruta: str, cuerpo: dict | None = None, crudo=False):
    pedido = urllib.request.Request(_base(cfg["centro"]) + ruta, method="POST" if cuerpo is not None else "GET",
                                    data=json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None,
                                    headers={"X-API-TOKEN": cfg["token"], "Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=180) as r:
        datos = r.read()
    return datos if crudo else json.loads(datos.decode("utf-8"))


def exportar(cfg: dict, encuesta: str, desde: str, destino: Path) -> Path:
    """Exporta las respuestas desde 'desde' (YYYY-MM-DD) en CSV y las deja en 'destino'."""
    inicio = _api(cfg, f"/surveys/{encuesta}/export-responses", {
        "format": "csv", "useLabels": True, "breakoutSets": False,
        "startDate": f"{desde}T00:00:00Z", "timeZone": cfg.get("zona", "America/Guayaquil"),
    })
    progreso = inicio["result"]["progressId"]
    for _ in range(120):                         # hasta ~4 minutos
        estado = _api(cfg, f"/surveys/{encuesta}/export-responses/{progreso}")["result"]
        if estado.get("status") == "complete":
            break
        if estado.get("status") == "failed":
            raise RuntimeError("Qualtrics no pudo generar la exportación")
        time.sleep(2)
    else:
        raise RuntimeError("Qualtrics tardó demasiado en generar la exportación")
    archivo = _api(cfg, f"/surveys/{encuesta}/export-responses/{estado['fileId']}/file", crudo=True)
    with zipfile.ZipFile(io.BytesIO(archivo)) as z:
        nombre = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        contenido = z.read(nombre)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(contenido)
    tmp.replace(destino)
    return destino


def descargar(fuente: dict, desde: str) -> Path | None:
    """Respuestas de la encuesta de esa fuente; None si Qualtrics no está configurado o falla (se sigue sin ella)."""
    cfg = leer_config()
    encuesta = (cfg.get("encuestas") or {}).get(fuente["id"])
    if not (cfg.get("token") and cfg.get("centro") and encuesta):
        return None
    try:
        ruta = exportar(cfg, encuesta, desde, DESTINO / f"{fuente['id']}.csv")
        print(f"[avance] {fuente['id']}: respuestas traídas de Qualtrics")
        return ruta
    except (urllib.error.URLError, RuntimeError, KeyError, StopIteration, ValueError, OSError) as e:
        detalle = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else str(e)
        print(f"[avance] {fuente['id']}: no se pudo consultar Qualtrics ({detalle}); se usan las exportaciones guardadas")
        return None


def configurar():
    """Pide centro de datos y token, muestra las encuestas de la cuenta y guarda las de Claro Inbound y Outbound."""
    cfg = leer_config()
    print("Datos en Qualtrics › Configuración de la cuenta › Qualtrics IDs:")
    print("  - 'Centro de datos' (ej. iad1, o el dominio de la empresa como empresa.qualtrics.com)")
    print("  - 'Token de API' (botón Generar token si no hay uno)\n")
    centro = input(f"Centro de datos [{cfg.get('centro', '')}]: ").strip() or cfg.get("centro", "")
    token = getpass.getpass("Token de API (no se muestra; Enter = mantener el actual): ").strip() or cfg.get("token", "")
    if not centro or not token:
        print("Faltan el centro de datos o el token; no se guardó nada.")
        return
    prueba = {**cfg, "centro": centro, "token": token}
    try:
        encuestas, ruta = [], "/surveys"
        while ruta:
            r = _api(prueba, ruta)["result"]
            encuestas += r.get("elements", [])
            siguiente = r.get("nextPage")
            ruta = siguiente.split("/API/v3", 1)[1] if siguiente else None
    except urllib.error.HTTPError as e:
        print(f"Qualtrics rechazó el acceso (HTTP {e.code}). Revisa el centro de datos y el token.")
        return
    except urllib.error.URLError as e:
        print(f"No se pudo conectar con Qualtrics ({e.reason}). Revisa el centro de datos.")
        return
    encuestas.sort(key=lambda x: x.get("name", ""))
    print("\nEncuestas de la cuenta:")
    for i, e in enumerate(encuestas, 1):
        print(f"  {i:>3}. {e.get('name')}  ({e.get('id')}){'' if e.get('isActive') else '  · inactiva'}")
    elegidas = dict(cfg.get("encuestas") or {})
    for fid, texto in (("claro_ec_in_monitoreo", "Claro Ecuador · Inbound"), ("claro_ec_out_monitoreo", "Claro Ecuador · Outbound")):
        actual = elegidas.get(fid, "")
        op = input(f"\nNúmero de la encuesta de monitoreo de {texto} [{actual or 'ninguna'}]: ").strip()
        if op.isdigit() and 1 <= int(op) <= len(encuestas):
            elegidas[fid] = encuestas[int(op) - 1]["id"]
    CONFIG.write_text(json.dumps({
        "_comentario": "Acceso a Qualtrics para el módulo Avance equipo. NO subir a GitHub (está en .gitignore).",
        "centro": centro, "token": token, "zona": cfg.get("zona", "America/Guayaquil"), "encuestas": elegidas,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nGuardado en config/qualtrics.local.json. Desde la próxima actualización, Claro llega directo de Qualtrics.")
