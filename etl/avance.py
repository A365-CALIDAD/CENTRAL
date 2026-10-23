"""Avance del equipo: evaluaciones de cada monitor por franja horaria del día (cortes) y duración de las llamadas.

Lee la base que usa cada fuente (la copia de Drive o el archivo más reciente de su carpeta) y, en Entel, además
las descargas de adherencias de esa cuenta ("Reporte Pauta ..."), que se bajan varias veces al día: si una
evaluación (ID Pauta) está en varios archivos, gana la descarga más reciente. Clave "avance" en config/fuentes.json:
    {"fecha": col, "hora": col (opcional si la fecha trae la hora), "duracion": col,
     "monitor": col (opcional), "monitor_fijo": "nombre" (opcional),
     "descargas": [{"carpeta", "patron"}] (opcional; por defecto, los complementos de la fuente),
     "zona": zona horaria de la base (ej. "America/Santiago"); se pasa a avance_equipo.zona de portal.json (Perú),
     "id": col que identifica cada evaluación (opcional; por defecto id_unico; Qualtrics: ResponseId),
     "qualtrics": true (Claro: además trae las respuestas del día por la API, ver etl/qualtrics.py)}
o, para las fuentes que llegan por aplicación web (Movistar, BN):
    {"api_json": url, "clave": "filas"|"avance", "posiciones": {"fecha": 0, "hora": 1, "monitor": 2, "duracion": 3},
     "nombre": texto que se muestra como origen}
Escribe data/avance.json (solo en este PC; viaja en los paquetes cifrados y en el respaldo):
    {"generado", "cortes", "dias", "fuentes": {linea: {"fuente", "archivo", "ultima"}},
     "filas": [[linea, monitor, "YYYY-MM-DD", "HH:MM", duracion_seg | null, id_evaluacion | ""], ...]}
Las fuentes cuya base no está en este PC conservan las filas que ya había (p. ej. las que publicó el otro PC).
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, time
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd

import central_etl as etl

SALIDA = etl.DATA / "avance.json"
DIAS = 35                    # días hacia atrás que se publican
CORTES = [f"{h:02d}:00" for h in range(7, 22)]
ZONA = "America/Lima"       # todas las horas se pasan a la hora de Perú (la del equipo y de la extracción)     # 07:00-08:00, 08:00-09:00... (se extrae a la media hora)


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


def zona_destino() -> str:
    portal = etl.leer_json(etl.CONFIG / "portal.json")
    return (portal.get("avance_equipo") or {}).get("zona") or ZONA


def a_zona(dia: str, hora: str, origen: str | None, destino: str) -> tuple[str, str]:
    """Pasa día y hora de la zona de la base (ej. Entel: hora de Chile) a la del equipo (Perú)."""
    if not origen or origen == destino:
        return dia, hora
    try:
        local = datetime.strptime(f"{dia} {hora}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(origen))
    except ValueError:
        return dia, hora
    convertida = local.astimezone(ZoneInfo(destino))
    return convertida.strftime("%Y-%m-%d"), convertida.strftime("%H:%M")


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


def descargas(fuente) -> list:
    """Descargas de la plataforma ('Reporte Pauta ...') de esa cuenta: clave 'descargas' del avance o sus complementos."""
    out = []
    for c in fuente["avance"].get("descargas") or fuente.get("complementos", []):
        carpeta = etl.ruta_fuente({"carpeta": c["carpeta"]})
        if carpeta.is_dir():
            out += [p for p in carpeta.glob(c.get("patron", "*.xlsx")) if not p.name.startswith("~$")]
    if fuente["avance"].get("qualtrics"):        # respuestas traídas por la API de Qualtrics (las más recientes)
        import qualtrics
        out += list(qualtrics.DESTINO.glob(f"{fuente['id']}_*.csv"))
    return sorted(set(out), key=lambda p: (p.stat().st_mtime, p.name))


def leer_descarga(ruta: Path, clave: str) -> pd.DataFrame | None:
    """Las descargas traen títulos arriba: el encabezado es la fila que contiene la columna id (ej. 'ID Pauta')."""
    if ruta.suffix.lower() == ".csv":
        crudo = pd.read_csv(ruta, header=None, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    else:
        hojas = pd.read_excel(ruta, sheet_name=None, header=None)
        crudo = hojas.get("Matriz", next(iter(hojas.values())))
    fila = next((i for i in range(min(15, len(crudo))) if clave in {etl.normalizar(x) for x in crudo.iloc[i]}), None)
    if fila is None:
        return None
    df = crudo.iloc[fila + 1:].copy()
    # Nombres repetidos se numeran como en la base consolidada de Excel: el segundo "TMO" (duración de la llamada;
    # el primero viene vacío) queda como "TMO2".
    nombres, vistos = [], {}
    for j, x in enumerate(crudo.iloc[fila]):
        n = f"_{j}" if etl.vacio(x) else str(x).strip()
        vistos[n] = vistos.get(n, 0) + 1
        nombres.append(n if vistos[n] == 1 else f"{n}{vistos[n]}")
    df.columns = nombres
    return df


def extraer(df: pd.DataFrame, fuente, desde: str, origen: str, sin_duracion_ok=False) -> dict | None:
    """{id: [linea, monitor, dia, hora, duracion]}. Las descargas de Outbound/E-commerce no traen la duración
    (sin_duracion_ok): igual cuentan en Q y la duración llega con la base consolidada."""
    cfg = fuente["avance"]
    cols = etl.resolver_columnas(df, {k: cfg[k] for k in ("fecha", "hora", "duracion", "monitor") if cfg.get(k)})
    faltan = [k for k in ("fecha", "hora", "duracion", "monitor") if cfg.get(k) and k not in cols
              and not (k == "duracion" and sin_duracion_ok)]
    if faltan:
        print(f"[avance] {fuente['id']} · {origen}: faltan las columnas {', '.join(cfg[k] for k in faltan)}; se omite")
        return None
    id_col = cfg.get("id") or fuente.get("id_unico")
    cid = etl.resolver_columnas(df, {"x": [id_col]}).get("x") if id_col else None
    for flt in fuente.get("filtros", []):      # p. ej. Qualtrics: solo encuestas terminadas
        real = etl.resolver_columnas(df, {"x": [flt.get("columna", "")]}).get("x") if flt.get("columna") else None
        if real is not None and "incluir" in flt:
            df = df[df[real].map(lambda v, lista=flt["incluir"]: etl.coincide(v, lista))]
        elif real is not None and "excluir" in flt:
            df = df[~df[real].map(lambda v, lista=flt["excluir"]: etl.coincide(v, lista))]
    out = {}
    origen, destino = cfg.get("zona"), zona_destino()
    for k, (_, r) in enumerate(df.iterrows()):
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
        dur = a_segundos(r[cols["duracion"]]) if "duracion" in cols else None
        dur = dur if dur is not None and 0 < dur <= 4 * 3600 else None     # más de 4 h = error de digitación
        ident = etl.norm_id(r[cid]) if cid is not None and not etl.vacio(r[cid]) else f"{origen}#{k}"
        dia, hora = a_zona(dia, hora, origen, destino)
        # 6.º dato: identificador de la evaluación (ID Pauta, ResponseId) para ubicarla en su plataforma
        id_original = " ".join(str(r[cid]).split()).removesuffix(".0") if cid is not None and not etl.vacio(r[cid]) else ""
        out[ident] = [fuente["linea_id"], monitor or "Sin identificar", dia, hora, dur, id_original]
    return out


def leer_api(fuente, desde: str) -> tuple[list, list]:
    """Aplicación web de Apps Script (Movistar, BN): {ok, <clave>: [[...], ...]} con las posiciones de 'posiciones'."""
    cfg = fuente["avance"]
    pedido = urllib.request.Request(cfg["api_json"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(pedido, timeout=180) as r:
        datos = json.loads(r.read().decode("utf-8"))
    lista = datos.get(cfg.get("clave", "filas")) if datos.get("ok") else None
    if lista is None:
        print(f"[avance] {fuente['id']}: la aplicación web todavía no entrega el avance; se conservan los datos anteriores")
        return [], []
    pos = cfg["posiciones"]
    origen, destino = cfg.get("zona"), zona_destino()
    filas = []
    for x in lista:
        dia, hora = str(x[pos["fecha"]])[:10], a_hora(x[pos["hora"]])
        if not hora or dia < desde:
            continue
        monitor = cfg.get("monitor_fijo") or ("" if "monitor" not in pos or etl.vacio(x[pos["monitor"]])
                                              else " ".join(str(x[pos["monitor"]]).split()).title())
        dur = a_segundos(x[pos["duracion"]]) if "duracion" in pos else None
        dur = dur if dur is not None and 0 < dur <= 4 * 3600 else None
        dia, hora = a_zona(dia, hora, origen, destino)
        filas.append([fuente["linea_id"], monitor or "Sin identificar", dia, hora, dur, ""])
    return filas, [Path(cfg.get("nombre", "aplicacion_web"))]


# Pasos que AvanceEquipo.exe hace antes y en su orden (Qualtrics → Entel → BN → Movistar); generar() usa lo ya traído.
PRECARGA: dict = {}          # id de fuente -> (filas, usados) leídos de su aplicación web
QUALTRICS_LISTO = False      # las respuestas de hoy ya se trajeron de Qualtrics


def desde_periodo() -> str:
    return (pd.Timestamp.now().normalize() - pd.Timedelta(days=DIAS)).strftime("%Y-%m-%d")


def descargar_qualtrics(fuentes: list) -> int:
    """Trae de Qualtrics las respuestas de hoy de las fuentes que lo usan (Claro). Devuelve cuántas se trajeron."""
    global QUALTRICS_LISTO
    import qualtrics
    if not (qualtrics.leer_config().get("token")):
        print("Qualtrics sin conectar (AvanceEquipo.exe › Q): se usan las exportaciones de la carpeta filtrado.")
        QUALTRICS_LISTO = True
        return 0
    n = 0
    for f in fuentes:
        if f.get("activo") and (f.get("avance") or {}).get("qualtrics"):
            n += qualtrics.descargar(f) is not None
    QUALTRICS_LISTO = True
    return n


def precargar(fuentes: list, fuente_id: str) -> int:
    """Lee ya la aplicación web de una fuente (BN, Movistar) y la deja lista para generar(). Devuelve evaluaciones."""
    f = next((x for x in fuentes if x["id"] == fuente_id and x.get("activo") and x.get("avance")), None)
    if f is None:
        return 0
    try:
        PRECARGA[fuente_id] = leer_api(f, desde_periodo())
    except Exception as e:
        print(f"[avance] {fuente_id}: no se pudo leer ({e}); se conservan sus datos anteriores")
        PRECARGA[fuente_id] = ([], [])
    filas = PRECARGA[fuente_id][0]
    hoy = datetime.now(ZoneInfo(zona_destino())).strftime("%Y-%m-%d")
    print(f"{len(filas)} evaluaciones de los últimos {DIAS} días · {sum(1 for x in filas if x[2] == hoy)} de hoy")
    return len(filas)


def leer_fuente(fuente, desde: str) -> tuple[list, list]:
    if fuente["id"] in PRECARGA:
        return PRECARGA.pop(fuente["id"])
    if fuente["avance"].get("api_json"):
        return leer_api(fuente, desde)
    """Base principal + descargas de la cuenta; si una evaluación está en varias, gana la descarga más reciente."""
    if fuente["avance"].get("qualtrics") and not QUALTRICS_LISTO:
        import qualtrics
        qualtrics.descargar(fuente)
    principal = archivo_fuente(fuente)
    usados, filas = [], {}
    if principal is not None:
        df = pd.read_excel(principal, sheet_name=fuente.get("hoja", 0), header=fuente.get("fila_encabezado", 0))
        parte = extraer(df, fuente, desde, principal.name)
        if parte is not None:
            filas.update(parte)
            usados.append(principal)
    clave = etl.normalizar(fuente["avance"].get("id") or fuente.get("id_unico", ""))
    for ruta in descargas(fuente) if clave else []:
        if datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%Y-%m-%d") < desde:
            continue        # descargas anteriores al periodo publicado
        try:
            df = leer_descarga(ruta, clave)
        except Exception as e:
            print(f"[avance] {fuente['id']} · {ruta.name}: no se pudo leer ({e})")
            continue
        parte = extraer(df, fuente, desde, ruta.name, sin_duracion_ok=True) if df is not None else None
        if parte:
            for k, fila in parte.items():
                if fila[4] is None and k in filas:      # sin duración en la descarga: se conserva la conocida
                    fila[4] = filas[k][4]
                filas[k] = fila
            usados.append(ruta)
    return list(filas.values()), usados


def generar(fuentes: list) -> int:
    """Actualiza data/avance.json con las fuentes que tienen la clave 'avance'."""
    con_avance = [f for f in fuentes if f.get("activo") and f.get("avance") and f.get("linea_id")]
    if not con_avance:
        return 0
    try:
        previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {}
    except ValueError:
        previo = {}
    desde = desde_periodo()
    filas = [f for f in previo.get("filas", []) if f[2] >= desde]
    info = dict(previo.get("fuentes", {}))
    for fuente in con_avance:
        try:
            nuevas, usados = leer_fuente(fuente, desde)
        except Exception as e:      # el avance nunca debe detener la actualización
            print(f"[avance] {fuente['id']}: no se pudo leer ({e}); se conservan sus datos anteriores")
            continue
        if not usados:
            continue                # base no disponible en este PC: se conserva lo anterior
        # Se reemplazan solo los días que trae la lectura nueva: si una descarga trae únicamente hoy,
        # los días anteriores de esa cuenta se conservan.
        dias_nuevos = {f[2] for f in nuevas}
        filas = [f for f in filas if f[0] != fuente["linea_id"] or f[2] not in dias_nuevos] + nuevas
        reciente = max(usados, key=lambda p: p.stat().st_mtime if p.exists() else 0)
        info[fuente["linea_id"]] = {"fuente": fuente["id"], "archivo": reciente.name, "archivos": len(usados),
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
