"""
Calidad A365 · Avisos por correo.

Envía a cada perfil un resumen de sus cuentas bajo meta (Crítico / Alerta), cuántos meses seguidos
llevan así y las acciones de seguimiento abiertas o vencidas. Solo envía cuando algo cambió desde el
último aviso (y como máximo una vez al día por perfil), salvo que se use --forzar.

Configuración (solo en este PC, no se publica):
    config/avisos.local.json  destinatarios por perfil y opciones (se crea con "iniciar")
    .env                      AVISOS_SMTP_USUARIO / AVISOS_SMTP_CLAVE (o GMAIL_USUARIO / GMAIL_CLAVE_APP)
                              Para Gmail se usa una "contraseña de aplicación", no la contraseña normal.

Uso:
    python etl/avisos.py iniciar                 # crea config/avisos.local.json para completar
    python etl/avisos.py vista                   # genera los correos en data/avisos/vista/*.html, sin enviar
    python etl/avisos.py prueba correo@gmail.com # envía el correo del administrador solo a esa dirección
    python etl/avisos.py enviar [--forzar] [--perfil id]
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import smtplib
import sys
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

# En el .exe (PyInstaller) la raíz es la carpeta donde está el ejecutable, junto a config/ y data/.
RAIZ = Path(os.environ.get("CALIDAD_A365_RAIZ") or (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent))
CONFIG = RAIZ / "config"
DATA = RAIZ / "data"
AVISOS = CONFIG / "avisos.local.json"
ESTADO = DATA / "avisos" / "enviados.json"
VISTA = DATA / "avisos" / "vista"
URL_DEFECTO = "https://a365-calidad.github.io/CENTRAL/"

PLANTILLA = {
    "_comentario": "Avisos por correo. Este archivo NO se publica. Complete los correos de cada perfil "
                   "(lista vacía = ese perfil no recibe avisos) y ponga 'activo': true para enviar.",
    "activo": False,
    "remitente_nombre": "Calidad A365",
    "url_plataforma": URL_DEFECTO,
    "smtp_servidor": "smtp.gmail.com",
    "smtp_puerto": 587,
    "estados": ["CRITICO", "ALERTA"],
    "incluir_acciones": True,
    "destinatarios": {},
}
NOMBRE_ESTADO = {"CRITICO": "Crítico", "ALERTA": "Alerta", "OK": "Cumple", "SIN_META": "Sin meta"}
COLOR = {"CRITICO": "#d03b3b", "ALERTA": "#c98500", "OK": "#0ca30c"}


def _leer(ruta: Path, defecto=None):
    if not ruta.exists():
        return defecto
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _escribir(ruta: Path, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def _env() -> dict:
    """Lee .env de la carpeta de la plataforma (sin dependencias)."""
    out = {}
    ruta = RAIZ / ".env"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return {**out, **{k: v for k, v in os.environ.items() if k.startswith(("AVISOS_", "GMAIL_"))}}


def iniciar():
    perfiles = (_leer(CONFIG / "perfiles.json", {}) or {}).get("perfiles", [])
    cfg = _leer(AVISOS) or dict(PLANTILLA)
    cfg.setdefault("destinatarios", {})
    for p in perfiles:
        cfg["destinatarios"].setdefault(p["id"], [])
    cfg["_perfiles"] = {p["id"]: p["nombre"] for p in perfiles}
    _escribir(AVISOS, cfg)
    print(f"Listo: complete los correos en {AVISOS.relative_to(RAIZ)} (perfiles: {', '.join(cfg['destinatarios'])})")


# ---------------------------------------------------------------- contenido

def _fmt(v, unidad):
    if v is None:
        return "—"
    if unidad == "%":
        return f"{v:.1f}%".replace(".", ",")
    if unidad == "n":
        return f"{v:,.0f}".replace(",", ".")
    if unidad == "pts":
        return f"{v:.2f}".replace(".", ",")
    return f"{v:.1f}".replace(".", ",")


def _mes_texto(per):
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    a, m = per.split("-")
    return f"{meses[int(m) - 1]} {a}"


def contenido(perfil: dict, cons: dict, seguimiento: list, catalogo: dict, portal: dict, cfg: dict) -> dict | None:
    """Arma el resumen de un perfil. None si no hay nada que avisar."""
    lineas = None if perfil.get("admin") else set(perfil.get("lineas", []))
    regs = [r for r in cons.get("registros", []) if lineas is None or r["l"] in lineas]
    if not regs:
        return None
    pers = sorted({r["per"] for r in regs})
    hoy = date.today().strftime("%Y-%m")
    per = hoy if hoy in pers else max(p for p in pers if p <= hoy) if any(p <= hoy for p in pers) else pers[-1]
    nombres = {d["id"]: f"{e['nombre']} {pa['nombre']} · {d.get('servicio') or d['nombre']}"
               for e in portal["empresas"] for pa in e["paises"] for d in pa.get("dashboards", [])}

    def racha(r):
        serie = sorted((x for x in regs if (x["l"], x["c"], x["i"]) == (r["l"], r["c"], r["i"])), key=lambda x: x["per"], reverse=True)
        n = 0
        for x in serie:
            if x["s"] in ("CRITICO", "ALERTA"):
                n += 1
            else:
                break
        return n

    riesgo = [r for r in regs if r["per"] == per and r["s"] in cfg.get("estados", ["CRITICO", "ALERTA"])
              and not catalogo.get(r["i"], {}).get("conteo")]
    riesgo.sort(key=lambda r: (r["s"] != "CRITICO", not r.get("t"), r["l"], r["c"]))
    items = [{"cuenta": nombres.get(r["l"], r["l"]), "plataforma": "Total de la cuenta" if r.get("t") else r["c"],
              "indicador": catalogo.get(r["i"], {}).get("nombre", r["i"]), "unidad": catalogo.get(r["i"], {}).get("unidad"),
              "valor": r["v"], "meta": r.get("m"), "estado": r["s"], "meses": racha(r), "clave": f"{r['l']}|{r['c']}|{r['i']}|{r['s']}"}
             for r in riesgo]

    hoy_iso = date.today().isoformat()
    acciones = []
    if cfg.get("incluir_acciones", True):
        for a in seguimiento:
            if a.get("estado") == "cerrada" or (lineas is not None and a.get("linea_id") not in lineas):
                continue
            vencida = bool(a.get("fecha_compromiso")) and a["fecha_compromiso"] < hoy_iso
            acciones.append({**a, "vencida": vencida, "cuenta_nombre": nombres.get(a.get("linea_id"), a.get("cuenta", ""))})
        acciones.sort(key=lambda a: (not a["vencida"], a.get("fecha_compromiso") or "9999"))

    if not items and not any(a["vencida"] for a in acciones):
        return None
    criticos = sum(i["estado"] == "CRITICO" for i in items)
    alertas = sum(i["estado"] == "ALERTA" for i in items)
    vencidas = sum(a["vencida"] for a in acciones)
    partes = [f"{criticos} crítico{'s' if criticos != 1 else ''}" if criticos else "",
              f"{alertas} alerta{'s' if alertas != 1 else ''}" if alertas else "",
              f"{vencidas} acción{'es' if vencidas != 1 else ''} vencida{'s' if vencidas != 1 else ''}" if vencidas else ""]
    asunto = f"[Calidad A365] {perfil['nombre']} · {_mes_texto(per)}: " + ", ".join(p for p in partes if p)
    huella = hashlib.sha256(json.dumps([per, sorted(i["clave"] for i in items),
                                        sorted(a["id"] for a in acciones if a["vencida"])]).encode()).hexdigest()
    return {"asunto": asunto, "html": _html(perfil, per, items, acciones, cfg), "huella": huella, "periodo": per}


def _html(perfil, per, items, acciones, cfg) -> str:
    e = html.escape
    url = cfg.get("url_plataforma") or URL_DEFECTO
    filas = "".join(f"""<tr>
        <td style="padding:8px;border-bottom:1px solid #eee"><b>{e(i['cuenta'])}</b><br><span style="color:#777;font-size:12px">{e(i['plataforma'])}</span></td>
        <td style="padding:8px;border-bottom:1px solid #eee">{e(i['indicador'])}</td>
        <td style="padding:8px;border-bottom:1px solid #eee;text-align:right"><b>{_fmt(i['valor'], i['unidad'])}</b></td>
        <td style="padding:8px;border-bottom:1px solid #eee;text-align:right">{_fmt(i['meta'], i['unidad'])}</td>
        <td style="padding:8px;border-bottom:1px solid #eee"><span style="color:{COLOR.get(i['estado'], '#555')};font-weight:bold">● {NOMBRE_ESTADO[i['estado']]}</span></td>
        <td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{i['meses']}{' ⚠' if i['meses'] >= 3 else ''}</td></tr>""" for i in items)
    tabla = (f"""<table style="border-collapse:collapse;width:100%;font-size:14px">
        <tr style="background:#f3f3f1;text-align:left;font-size:12px;color:#555">
        <th style="padding:8px">Cuenta / plataforma</th><th style="padding:8px">Indicador</th><th style="padding:8px;text-align:right">Valor</th>
        <th style="padding:8px;text-align:right">Meta</th><th style="padding:8px">Estado</th><th style="padding:8px">Meses seguidos</th></tr>{filas}</table>"""
             if items else "<p>No hay indicadores bajo meta este mes.</p>")
    acc = "".join(f"""<li style="margin-bottom:6px"><b>{e(a.get('cuenta_nombre') or '')}</b> · {e(a.get('cuenta') or '')}: {e(a.get('accion') or a.get('observacion') or '')}
        <br><span style="color:#777;font-size:12px">Responsable: {e(a.get('responsable') or '—')} · Compromiso: {e(a.get('fecha_compromiso') or '—')}
        {'· <b style="color:#d03b3b">VENCIDA</b>' if a['vencida'] else ''}</span></li>""" for a in acciones[:20])
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="margin:0;background:#f4f4f1;font-family:Segoe UI,Arial,sans-serif;color:#111">
<div style="max-width:720px;margin:0 auto;padding:20px">
  <div style="background:#0f1b2d;color:#fff;padding:16px 20px;border-radius:12px 12px 0 0">
    <div style="font-size:18px;font-weight:bold">Calidad A365 · Seguimiento</div>
    <div style="opacity:.8;font-size:13px">{e(perfil['nombre'])} · {_mes_texto(per)}</div>
  </div>
  <div style="background:#fff;padding:20px;border-radius:0 0 12px 12px">
    <h3 style="margin:0 0 10px;font-size:15px">Indicadores bajo meta</h3>
    {tabla}
    {f'<h3 style="margin:22px 0 10px;font-size:15px">Acciones de seguimiento abiertas</h3><ul style="padding-left:18px;font-size:14px">{acc}</ul>' if acciones else ''}
    <p style="margin:24px 0 8px"><a href="{e(url)}" style="background:#2a78d6;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;display:inline-block">Abrir la plataforma</a></p>
    <p style="color:#888;font-size:12px;margin:16px 0 0">Ingresa con tu perfil y contraseña. Recibes este aviso porque hay indicadores bajo meta o acciones vencidas en tus cuentas; solo se envía cuando algo cambia.</p>
  </div>
</div></body></html>"""


# ---------------------------------------------------------------- envío

def _preparar():
    cfg = _leer(AVISOS)
    if not cfg:
        raise SystemExit("Falta config/avisos.local.json. Ejecute: python etl/avisos.py iniciar")
    perfiles = (_leer(CONFIG / "perfiles.json", {}) or {}).get("perfiles", [])
    cons = _leer(DATA / "consolidado.json", {"registros": []})
    seg = (_leer(DATA / "seguimiento.json", {}) or {}).get("acciones", [])
    catalogo = {i["id"]: i for i in _leer(CONFIG / "indicadores.json")["indicadores"]}
    portal = _leer(CONFIG / "portal.json")
    return cfg, perfiles, cons, seg, catalogo, portal


def vista():
    cfg, perfiles, cons, seg, catalogo, portal = _preparar()
    VISTA.mkdir(parents=True, exist_ok=True)
    for p in perfiles:
        c = contenido(p, cons, seg, catalogo, portal, cfg)
        destino = VISTA / f"{p['id']}.html"
        if c:
            destino.write_text(c["html"], encoding="utf-8")
            print(f"{p['id']:<16} {c['asunto']}  ->  {destino.relative_to(RAIZ)}")
        else:
            destino.unlink(missing_ok=True)
            print(f"{p['id']:<16} sin avisos")


def _smtp(cfg):
    env = _env()
    usuario = env.get("AVISOS_SMTP_USUARIO") or env.get("GMAIL_USUARIO")
    clave = env.get("AVISOS_SMTP_CLAVE") or env.get("GMAIL_CLAVE_APP")
    if not usuario or not clave:
        raise SystemExit("Falta el remitente: agregue AVISOS_SMTP_USUARIO y AVISOS_SMTP_CLAVE (contraseña de aplicación) en .env")
    srv = smtplib.SMTP(cfg.get("smtp_servidor", "smtp.gmail.com"), int(cfg.get("smtp_puerto", 587)), timeout=60)
    srv.starttls()
    srv.login(usuario, clave)
    return srv, usuario


def _mensaje(cfg, remitente, para, c):
    m = EmailMessage()
    m["Subject"] = c["asunto"]
    m["From"] = f"{cfg.get('remitente_nombre', 'Calidad A365')} <{remitente}>"
    m["To"] = ", ".join(para)
    m.set_content("Este aviso necesita un lector de correo con HTML. Abra la plataforma: " + (cfg.get("url_plataforma") or URL_DEFECTO))
    m.add_alternative(c["html"], subtype="html")
    return m


def prueba(correo: str):
    cfg, perfiles, cons, seg, catalogo, portal = _preparar()
    admin = next(p for p in perfiles if p.get("admin"))
    c = contenido(admin, cons, seg, catalogo, portal, cfg) or {"asunto": "[Calidad A365] Prueba de aviso", "html": "<p>Prueba de envío.</p>"}
    srv, remitente = _smtp(cfg)
    with srv:
        srv.send_message(_mensaje(cfg, remitente, [correo], {**c, "asunto": "[PRUEBA] " + c["asunto"]}))
    print(f"Correo de prueba enviado a {correo}")


def enviar(forzar=False, solo=None):
    cfg, perfiles, cons, seg, catalogo, portal = _preparar()
    if not cfg.get("activo") and not forzar:
        print("Avisos desactivados ('activo': false en config/avisos.local.json); no se envía nada.")
        return 0
    estado = _leer(ESTADO, {}) or {}
    hoy = date.today().isoformat()
    pendientes = []
    for p in perfiles:
        if solo and p["id"] != solo:
            continue
        para = [x for x in (cfg.get("destinatarios", {}).get(p["id"]) or []) if "@" in x]
        if not para:
            continue
        c = contenido(p, cons, seg, catalogo, portal, cfg)
        if not c:
            continue
        previo = estado.get(p["id"], {})
        if not forzar and (previo.get("huella") == c["huella"] or previo.get("fecha") == hoy):
            print(f"{p['id']:<16} sin cambios desde el último aviso ({previo.get('fecha')}); no se envía")
            continue
        pendientes.append((p, para, c))
    if not pendientes:
        print("No hay avisos nuevos para enviar.")
        return 0
    srv, remitente = _smtp(cfg)
    with srv:
        for p, para, c in pendientes:
            srv.send_message(_mensaje(cfg, remitente, para, c))
            estado[p["id"]] = {"fecha": hoy, "huella": c["huella"], "asunto": c["asunto"], "enviado": datetime.now().isoformat(timespec="seconds")}
            print(f"{p['id']:<16} enviado a {len(para)} destinatario(s): {c['asunto']}")
    _escribir(ESTADO, estado)
    return len(pendientes)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "vista"
    if cmd == "iniciar":
        iniciar()
    elif cmd == "vista":
        vista()
    elif cmd == "prueba" and len(args) > 1:
        prueba(args[1])
    elif cmd == "enviar":
        solo = args[args.index("--perfil") + 1] if "--perfil" in args else None
        enviar(forzar="--forzar" in args, solo=solo)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
