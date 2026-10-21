"""Avance del equipo: evaluaciones de cada monitor por franja horaria del día (cortes) y duración de las llamadas.

Lee la misma base que usa cada fuente (la copia de Drive o el archivo más reciente de su carpeta) según su clave
"avance" en config/fuentes.json:
    {"fecha": col, "hora": col (opcional si la fecha trae la hora), "duracion": col,
     "monitor": col (opcional), "monitor_fijo": "nombre" (opcional)}
Escribe data/avance.json (solo en este PC; viaja en los paquetes cifrados y en el respaldo):
    {"generado", "cortes", "dias", "fuentes": {linea: {"fuente", "archivo", "ultima"}},
     "filas": [[linea, monitor, "YYYY-MM-DD", "HH:MM", duracion_seg | null], ...]}
Las fuentes cuya base no está en este PC conservan las filas que ya había (p. ej. las que publicó el otro PC).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, time
from pathlib import Path

import pandas as pd

import central_etl as etl

SALIDA = etl.DATA / "avance.json"
DIAS = 35                    # días hacia atrás que se publican
CORTES = ["07:00", "07:30", "08:30", "09:30", "10:30", "11:30", "12:30", "13:30",
          "14:30", "15:30", "16:30", "17:30", "18:30", "19:30", "20:30"]


def a_segundos(v):
    """Duración de la llamada: 407 (segundos), '00:08:27', '04:00' (mm:ss), time(0, 8, 27) o fracción de día."""
    if etl.vacio(v):
        return None
    if isinstance(v, time):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, pd.Timedelta):
        return int(v.total_seconds())
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(round(v * 86400)) if 0 < v < 1 else int(round(v))
    s = str(v).strip()
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.\d+)?", s)
    if m:
        h, mi, se = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
        return h * 3600 + mi * 60 + se
    n = etl.a_numero(s)
    return int(round(n)) if n is not None else None


def a_hora(v):
    """'HH:MM' desde time, datetime o texto ('11:44', '08:21:00')."""
    if etl.vacio(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, time):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, (int, float)) and 0 <= v < 1:                  # fracción de día de Excel
        m = int(round(v * 1440))
        return f"{m // 60:02d}:{m % 60:02d}"
    m = re.search(r"(\d{1,2}):(\d{2})", str(v))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def archivo_fuente(fuente) -> Path | None:
    """La base que leyó el ETL: copia de Drive o el archivo más reciente de la carpeta local."""
    copias = [p for p in (etl.DIR_DRIVE / fuente["id"]).glob("*.xls*") if not p.name.startswith("~$")]
    if copias:
        return max(copias, key=lambda p: (etl.fecha_en_nombre(p.name), p.stat().st_mtime))
    carpeta = etl.ruta_fuente(fuente)
    locales = [p for p in carpeta.glob(fuente.get("patron", "*.xlsx")) if not p.name.startswith("~$")] if carpeta.is_dir() else []
    return max(locales, key=lambda p: (p.stat().st_mtime, p.name)) if locales else None


def leer_fuente(fuente, desde: str) -> tuple[list, Path | None]:
    cfg = fuente["avance"]
    ruta = archivo_fuente(fuente)
    if ruta is None:
        return [], None
    df = pd.read_excel(ruta, sheet_name=fuente.get("hoja", 0), header=fuente.get("fila_encabezado", 0))
    cols = etl.resolver_columnas(df, {k: cfg[k] for k in ("fecha", "hora", "duracion", "monitor") if cfg.get(k)})
    faltan = [k for k in ("fecha", "hora", "duracion", "monitor") if cfg.get(k) and k not in cols]
    if faltan:
        print(f"[avance] {fuente['id']}: faltan las columnas {', '.join(cfg[k] for k in faltan)}; se omite")
        return [], ruta
    for flt in fuente.get("filtros", []):      # p. ej. Qualtrics: solo encuestas terminadas
        real = etl.resolver_columnas(df, {"x": [flt.get("columna", "")]}).get("x") if flt.get("columna") else None
        if real is not None and "incluir" in flt:
            df = df[df[real].map(lambda v, lista=flt["incluir"]: etl.coincide(v, lista))]
        elif real is not None and "excluir" in flt:
            df = df[~df[real].map(lambda v, lista=flt["excluir"]: etl.coincide(v, lista))]
    filas = []
    for _, r in df.iterrows():
        f = etl.a_fecha(r[cols["fecha"]])
        if f is None:
            continue
        dia = f.strftime("%Y-%m-%d")
        if dia < desde:
            continue
        hora = a_hora(r[cols["hora"]]) if "hora" in cols else a_hora(r[cols["fecha"]])
        if not hora:
            continue
        monitor = cfg.get("monitor_fijo") or ("" if "monitor" not in cols or etl.vacio(r[cols["monitor"]])
                                              else " ".join(str(r[cols["monitor"]]).split()).title())
        dur = a_segundos(r[cols["duracion"]])
        dur = dur if dur is not None and 0 < dur <= 4 * 3600 else None     # más de 4 h = error de digitación
        filas.append([fuente["linea_id"], monitor or "Sin identificar", dia, hora, dur])
    return filas, ruta


def generar(fuentes: list) -> int:
    """Actualiza data/avance.json con las fuentes que tienen la clave 'avance'."""
    con_avance = [f for f in fuentes if f.get("activo") and f.get("avance") and f.get("linea_id")]
    if not con_avance:
        return 0
    try:
        previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    except ValueError:
        previo = {}
    desde = (pd.Timestamp.now().normalize() - pd.Timedelta(days=DIAS)).strftime("%Y-%m-%d")
    filas = [f for f in previo.get("filas", []) if f[2] >= desde]
    info = dict(previo.get("fuentes", {}))
    for fuente in con_avance:
        try:
            nuevas, ruta = leer_fuente(fuente, desde)
        except Exception as e:      # el avance nunca debe detener la actualización
            print(f"[avance] {fuente['id']}: no se pudo leer ({e}); se conservan sus datos anteriores")
            continue
        if ruta is None:
            continue                # base no disponible en este PC: se conserva lo anterior
        filas = [f for f in filas if f[0] != fuente["linea_id"]] + nuevas
        info[fuente["linea_id"]] = {"fuente": fuente["id"], "archivo": ruta.name,
                                    "ultima": max((f"{x[2]} {x[3]}" for x in nuevas), default=None)}
    portal = etl.leer_json(etl.CONFIG / "portal.json")
    cortes = (portal.get("avance_equipo") or {}).get("cortes") or CORTES
    filas.sort(key=lambda x: (x[2], x[0], x[1], x[3]))
    etl.escribir_json(SALIDA, {
        "generado": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "cortes": cortes, "dias": DIAS,
        "fuentes": info, "filas": filas,
    }, compacto=True)
    print(f"Avance del equipo: {len(filas)} evaluaciones de los últimos {DIAS} días")
    return len(filas)
