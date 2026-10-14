"""
CENTRAL · Validación cruzada contra los dashboards.

Recalcula los indicadores mensuales de cada servicio con la MISMA fórmula que usa su dashboard
(a partir de los datos embebidos en el index.html local de cada uno) y los compara con el total
del servicio publicado por CENTRAL (cuenta "(TOTAL)" de data/consolidado.json).

    python etl/validar_dashboards.py            # imprime el resumen y escribe data/cargas/validacion.json

Diferencias esperables: si el index.html local se generó con archivos distintos a los que leyó el
ETL (por ejemplo, un dashboard actualizado antes de la última descarga), el último mes no coincide.
Por eso se informa la fecha del index.html de cada dashboard.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import re
import sys
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# En el .exe (PyInstaller) la raíz es la carpeta donde está el ejecutable, junto a config/ y data/.
RAIZ = Path(os.environ.get("CALIDAD_A365_RAIZ") or (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent))
A365 = RAIZ.parent
TOLERANCIA = 0.15          # puntos de diferencia aceptados por redondeos
TOTAL = "(TOTAL)"


# ---------------------------------------------------------------- lectura de los index.html

def _b64(html, nombre):
    m = re.search(r'const %s = "([^"]*)";' % re.escape(nombre), html)
    if not m or not m.group(1):
        return None
    raw = base64.b64decode(m.group(1))
    for f in (lambda b: b, gzip.decompress, zlib.decompress):
        try:
            return json.loads(f(raw).decode("utf-8"))
        except Exception:
            continue
    return None


def _literal(html, patron):
    m = re.search(patron, html)
    return json.JSONDecoder().raw_decode(html[m.end():])[0] if m else None


def _html(rel):
    ruta = A365 / rel
    return ruta.read_text(encoding="utf-8"), datetime.fromtimestamp(ruta.stat().st_mtime)


def media(vals):
    v = [x for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return sum(v) / len(v) if v else None


def por_mes(filas, mes, campos):
    """{mes: {indicador: valor}} aplicando funciones de agregación sobre las filas de cada mes."""
    grupos = defaultdict(list)
    for f in filas:
        m = mes(f)
        if m:
            grupos[m].append(f)
    return {m: {k: fn(g) for k, fn in campos.items()} for m, g in grupos.items()}


# ---------------------------------------------------------------- réplica de cada dashboard

def entel_in():
    html, fecha = _html("ENTEL/ENTEL_BI_IN/BI/index.html")
    d = _b64(html, "__PAYLOAD_B64")
    adh = por_mes(d["RECORDS"], lambda r: (r.get("fecha") or "")[:7], {
        "evaluaciones": len,
        "calidad": lambda g: media(r["resultadoFinal"] for r in g),
        "pec": lambda g: media(r["pec"] for r in g),
        "penc": lambda g: media(r["penc"] for r in g),
        "adherencia": lambda g: media(r["adherencia"] for r in g)})
    epa = por_mes(d["EPA_RECORDS"], lambda r: (r.get("fechaAtencion") or "")[:7], {
        "encuestas": len,
        "epa": lambda g: media(r["epa"] for r in g),
        "fcr": lambda g: media(r["resolucion"] for r in g),
        "global": lambda g: media(r["global"] for r in g)})
    return "entel-in", fecha, _unir(adh, epa)


def _evol_adh(rel):
    html, fecha = _html(rel)
    d = _b64(html, "ADH_B64")
    out = {}
    for e in d["evolMensual"]:
        k = d["byMonth"].get(e["key"], {}).get("kpis", {})
        out[e["key"]] = {"evaluaciones": e["q"], "calidad": e["adherencia"], "penc": k.get("penc"), "pec": k.get("pec")}
    return html, fecha, out


def entel_mt():
    html, fecha, adh = _evol_adh("ENTEL/ENTEL_BI_MT/BI/index.html")
    for v in adh.values():
        v.pop("pec", None)      # el PEC de MT combina bloques distintos; CENTRAL no lo publica
    e = _b64(html, "EPA_B64") or {}
    epa = {x["key"]: {"encuestas": x["q"], "epa": x["epa"]} for x in e.get("evolMensual", [])}
    return "entel-mt", fecha, _unir(adh, epa)


def entel_c2c():
    _, fecha, adh = _evol_adh("ENTEL/ENTEL_BI_CZC/BI/index.html")
    return "entel-c2c", fecha, adh


def _out_ec(canal, linea):
    html, fecha = _html(f"ENTEL/ENTEL_BI_{canal}/BI/index.html")
    d = _literal(html, r"const DATA\s*=\s*")
    c = d["adh"]["campos"]
    i_f, i_penc, i_pec = c.index("fecha"), c.index("penc"), c.index("pec")
    adh = por_mes(d["adh"]["filas"], lambda r: (r[i_f] or "")[:7], {
        "evaluaciones": len,
        "penc": lambda g: media(r[i_penc] for r in g),
        "pec": lambda g: media(r[i_pec] for r in g)})
    epa = {}
    if d["movil"]["filas"]:
        cm = d["movil"]["campos"]
        i_fm, i_g = cm.index("fecha"), cm.index("global")
        rec = lambda g: None if g is None else (100 if g >= 4 else 0 if g == 3 else -100)
        epa = por_mes(d["movil"]["filas"], lambda r: (r[i_fm] or "")[:7], {
            "encuestas": len,
            "epa": lambda g: media(rec(r[i_g]) for r in g),
            "global": lambda g: media(r[i_g] for r in g)})
    return linea, fecha, _unir(adh, epa)


def entel_emp():
    html, fecha = _html("ENTEL/ENTEL_BI_EMP/index.html")
    d = _literal(html, r"const DATA\s*=\s*")
    anio = d.get("anio", datetime.now().year)
    return "entel-emp", fecha, por_mes(d["registros"], lambda r: f"{anio}-{int(r['mes']):02d}", {
        "evaluaciones": len, "calidad": lambda g: media(r["nota"] for r in g)})


def claro_in():
    html, fecha = _html("CLARO/ECUADOR/CLARO_IN/BI/index.html")
    d = _literal(html, r"const D\s*=\s*")
    items, bw = d["items"], d["bw"]

    def copc(r):
        got = cap = 0
        for b, peso in bw.items():
            its = [i for i in items if i["b"] == b and r["it"].get(i["k"]) is not None]
            if not its:
                continue
            w = sum(i["w"] for i in its)
            got += peso * sum(i["w"] * r["it"][i["k"]] for i in its) / w
            cap += peso
        if not cap:
            return None
        return 0 if any(i["c"] and r["it"].get(i["k"]) == 0 for i in items) else got / cap * 100

    def fcr(g):
        f = [r for r in g if r.get("fcr")]
        return sum(r["fcr"] == "SI" for r in f) / len(f) * 100 if f else None

    return "claro-ec-in", fecha, por_mes(d["rows"], lambda r: (r.get("fecha") or "")[:7], {
        "evaluaciones": len, "calidad": lambda g: media(copc(r) for r in g), "fcr": fcr})


def claro_out():
    html, fecha = _html("CLARO/ECUADOR/CLARO_OUT/BI/index.html")
    d = _literal(html, r"const DATA=")
    items = _literal(html, r"const ITEMS=")

    def copc(e):
        if e.get("ecs") is None:
            return None
        return 0 if any(it[3] and e["it"][i] == 0 for i, it in enumerate(items)) else e["ecs"]

    def efe(g):
        si, no = sum(e.get("efe") == "SI" for e in g), sum(e.get("efe") != "SI" for e in g)   # NO APLICA = no venta
        return si / (si + no) * 100 if si + no else None

    return "claro-ec-out", fecha, por_mes(d, lambda e: (e.get("fl") or "")[:7], {
        "evaluaciones": len, "calidad": lambda g: media(copc(e) for e in g), "efectividad": efe})


def _unir(*partes):
    out = defaultdict(dict)
    for p in partes:
        for m, v in p.items():
            out[m].update(v)
    return dict(out)


VALIDADORES = [entel_in, entel_mt, entel_c2c, lambda: _out_ec("OUT", "entel-out"),
               lambda: _out_ec("EC", "entel-ec"), entel_emp, claro_in, claro_out]


# ---------------------------------------------------------------- comparación

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cons = json.loads((RAIZ / "data" / "consolidado.json").read_text(encoding="utf-8"))
    central = defaultdict(dict)
    for r in cons["registros"]:
        if r["c"] == TOTAL:
            central[(r["l"], r["per"])][r["i"]] = r["v"]

    filas, resumen = [], []
    for fn in VALIDADORES:
        try:
            linea, fecha_html, dash = fn()
        except Exception as e:                       # dashboard sin index.html local o con otro formato
            resumen.append({"linea": getattr(fn, "__name__", "?"), "error": str(e)})
            continue
        ok = dif = 0
        for per in sorted(dash):
            for ind, v_dash in dash[per].items():
                if v_dash is None:
                    continue
                v_cen = central.get((linea, per), {}).get(ind)
                estado = ("SOLO_DASHBOARD" if v_cen is None else
                          "OK" if abs(v_cen - v_dash) <= (0 if ind in ("evaluaciones", "encuestas") else TOLERANCIA) else
                          "DIFERENTE")
                ok += estado == "OK"
                dif += estado != "OK"
                filas.append({"linea": linea, "periodo": per, "indicador": ind, "dashboard": round(v_dash, 2),
                              "central": None if v_cen is None else round(v_cen, 2), "estado": estado})
        resumen.append({"linea": linea, "index_html": fecha_html.isoformat(timespec="minutes"), "coinciden": ok, "difieren": dif})

    salida = {"generado": datetime.now().isoformat(timespec="seconds"), "tolerancia": TOLERANCIA,
              "resumen": resumen, "comparaciones": filas}
    (RAIZ / "data" / "cargas" / "validacion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from perfiles import cifrar_perfiles     # la validación solo se publica dentro del paquete del administrador
    cifrar_perfiles(silencioso=True)

    for r in resumen:
        if "error" in r:
            print(f"{r['linea']:<14} ERROR: {r['error']}")
            continue
        print(f"{r['linea']:<14} index.html {r['index_html']}  coinciden {r['coinciden']:>4}  difieren {r['difieren']:>3}")
    malas = [f for f in filas if f["estado"] != "OK"]
    if malas:
        print("\nDiferencias:")
        for f in malas:
            print(f"  {f['linea']:<13} {f['periodo']} {f['indicador']:<12} dashboard {f['dashboard']!s:>8}  central {f['central']!s:>8}  {f['estado']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
