"""
Calidad A365 · Perfiles con contraseña.

La página se publica en GitHub Pages (pública), así que los datos NO se publican en claro:
cada perfil recibe un paquete cifrado con su contraseña (PBKDF2-SHA256 + AES-256-GCM), que el
navegador descifra al iniciar sesión. Sin la contraseña el archivo no se puede leer.

    config/perfiles.json        lista de perfiles y qué cuentas ve cada uno (se publica, sin contraseñas)
    config/perfiles.local.json  contraseñas (SOLO en este PC, está en .gitignore)
    data/seguro/<perfil>.json   paquete cifrado de cada perfil (se publica)
    data/seguro/respaldo.json   respaldo cifrado (clave del administrador) del histórico, cargas y seguimiento

Uso:
    python etl/perfiles.py cifrar                       # regenera los paquetes (lo hace solo el ETL al publicar)
    python etl/perfiles.py lista                        # perfiles y cuentas, sin mostrar contraseñas
    python etl/perfiles.py editar                       # cambiar contraseñas en forma interactiva (cambiar_contrasenas.bat)
    python etl/perfiles.py clave <perfil> [nueva]       # cambia la contraseña (sin 'nueva' genera una)
    python etl/perfiles.py importar-seguimiento <archivo.json>
    python etl/perfiles.py restaurar-respaldo           # recupera data/ desde el respaldo cifrado
    python etl/perfiles.py bitacora                     # genera bitacora/Codigo.gs para pegar en Google Apps Script
    python etl/perfiles.py bitacora-url <url>           # guarda la URL de la aplicación web publicada

Bitácora en línea: cada perfil tiene una clave de acceso aleatoria (config/bitacora.local.json, solo en este
PC) que viaja dentro de su paquete cifrado; el script de Google solo guarda su huella SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import sys
import tarfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# En el .exe (PyInstaller) la raíz es la carpeta donde está el ejecutable, junto a config/ y data/.
RAIZ = Path(os.environ.get("CALIDAD_A365_RAIZ") or (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent))
CONFIG = RAIZ / "config"
DATA = RAIZ / "data"
PERFILES = CONFIG / "perfiles.json"
CLAVES = CONFIG / "perfiles.local.json"
DIR_SEGURO = DATA / "seguro"
ITERACIONES = 600_000           # costo de derivar la clave: frena los intentos de adivinar contraseñas
RESPALDAR = ["historico", "cargas", "seguimiento.json"]
BITACORA = CONFIG / "bitacora.local.json"          # URL de la aplicación web y claves de acceso (no se publica)
PLANTILLA_GS = Path(__file__).resolve().parent / "bitacora_codigo.gs"
SALIDA_GS = RAIZ / "bitacora" / "Codigo.gs"


def _leer(ruta: Path, defecto=None):
    if not ruta.exists():
        return defecto
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _escribir(ruta: Path, datos, compacto=False):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, **({"separators": (",", ":")} if compacto else {"indent": 2}))


# ---------------------------------------------------------------- cifrado

def _clave_aes(clave: str, sal: bytes, iteraciones: int = ITERACIONES) -> bytes:
    return PBKDF2HMAC(hashes.SHA256(), 32, sal, iteraciones).derive(clave.encode("utf-8"))


def cifrar(datos: bytes, clave: str) -> dict:
    """Sobre compatible con WebCrypto: el texto cifrado lleva la etiqueta GCM al final."""
    sal, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_clave_aes(clave, sal)).encrypt(iv, datos, None)
    b64 = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "kdf": "PBKDF2-SHA256", "iter": ITERACIONES, "alg": "AES-256-GCM",
            "salt": b64(sal), "iv": b64(iv), "ct": b64(ct)}


def descifrar(sobre: dict, clave: str) -> bytes:
    d = lambda k: base64.b64decode(sobre[k])
    return AESGCM(_clave_aes(clave, d("salt"), sobre.get("iter", ITERACIONES))).decrypt(d("iv"), d("ct"), None)


# ---------------------------------------------------------------- perfiles y contraseñas

def generar_clave(largo: int = 14) -> str:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"   # sin caracteres confundibles
    while True:
        c = "".join(secrets.choice(alfabeto) for _ in range(largo))
        if any(x.isdigit() for x in c) and any(x.isupper() for x in c) and any(x.islower() for x in c):
            return c


def perfiles() -> list[dict]:
    return (_leer(PERFILES) or {}).get("perfiles", [])


def claves(lista=None, avisar=True) -> dict:
    """Contraseñas de config/perfiles.local.json; genera las que falten (nunca las imprime)."""
    lista = lista if lista is not None else perfiles()
    guardadas = _leer(CLAVES, {}) or {}
    nuevas = [p["id"] for p in lista if not guardadas.get(p["id"])]
    for pid in nuevas:
        guardadas[pid] = generar_clave()
    ids = {p["id"] for p in lista}
    sobran = [k for k in guardadas if k != "_comentario" and k not in ids]   # perfiles eliminados
    for k in sobran:
        del guardadas[k]
    if sobran and avisar:
        print(f"Perfiles: se eliminaron las contraseñas de {', '.join(sobran)}")
    if nuevas or sobran:
        _escribir(CLAVES, {"_comentario": "Contraseñas de los perfiles. NO subir a GitHub (está en .gitignore).",
                           **{k: v for k, v in guardadas.items() if k != "_comentario"}})
        if avisar:
            print(f"Perfiles: se generaron contraseñas para {', '.join(nuevas)} en config/perfiles.local.json")
    return guardadas


def _paquete(p: dict, cons: dict, resumen, validacion, seguimiento, bitacora=None) -> dict:
    admin = bool(p.get("admin"))
    lineas = None if admin else set(p.get("lineas", []))
    return {
        "bitacora": ({"url": bitacora["url"], "token": bitacora["tokens"][p["id"]]}
                     if bitacora and bitacora.get("url") and bitacora.get("tokens", {}).get(p["id"]) else None),
        "perfil": {"id": p["id"], "nombre": p["nombre"], "admin": admin, "lineas": "*" if admin else sorted(lineas)},
        "consolidado": {**cons, "registros": cons.get("registros", []) if admin
                        else [r for r in cons.get("registros", []) if r.get("l") in lineas]},
        "resumen": resumen if admin else None,
        "validacion": validacion if admin else None,
        "seguimiento": {"acciones": seguimiento if admin else [a for a in seguimiento if a.get("linea_id") in lineas]},
    }


def cifrar_perfiles(silencioso=False) -> int:
    """Genera data/seguro/<perfil>.json y el respaldo cifrado. Devuelve la cantidad de perfiles."""
    lista = perfiles()
    if not lista:
        return 0
    cl = claves(lista, avisar=not silencioso)
    cons = _leer(DATA / "consolidado.json", {"registros": []})
    resumen = _leer(DATA / "cargas" / "resumen.json")
    validacion = _leer(DATA / "cargas" / "validacion.json")
    seguimiento = (_leer(DATA / "seguimiento.json", {}) or {}).get("acciones", [])
    DIR_SEGURO.mkdir(parents=True, exist_ok=True)
    bitacora = config_bitacora(lista) if BITACORA.exists() else None
    vigentes = set()
    for p in lista:
        datos = json.dumps(_paquete(p, cons, resumen, validacion, seguimiento, bitacora), ensure_ascii=False, separators=(",", ":"))
        _escribir(DIR_SEGURO / f"{p['id']}.json", cifrar(datos.encode("utf-8"), cl[p["id"]]), compacto=True)
        vigentes.add(f"{p['id']}.json")
    admin = next((p for p in lista if p.get("admin")), None)
    if admin:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for nombre in RESPALDAR:
                if (DATA / nombre).exists():
                    tar.add(DATA / nombre, arcname=f"data/{nombre}")
        _escribir(DIR_SEGURO / "respaldo.json", cifrar(buf.getvalue(), cl[admin["id"]]), compacto=True)
        vigentes.add("respaldo.json")
    for viejo in DIR_SEGURO.glob("*.json"):     # perfiles eliminados
        if viejo.name not in vigentes:
            viejo.unlink()
    if not silencioso:
        print(f"Perfiles: {len(lista)} paquetes cifrados en data/seguro/")
    return len(lista)


# ---------------------------------------------------------------- seguimiento y respaldo

def importar_seguimiento(archivo: str) -> int:
    """Une a data/seguimiento.json las acciones exportadas desde la página (por id; gana la más reciente)."""
    entrantes = (_leer(Path(archivo), {}) or {}).get("acciones", [])
    actual = (_leer(DATA / "seguimiento.json", {}) or {}).get("acciones", [])
    por_id = {a["id"]: a for a in actual}
    cambios = 0
    for a in entrantes:
        previo = por_id.get(a.get("id"))
        if not previo or (a.get("actualizado") or "") > (previo.get("actualizado") or ""):
            por_id[a["id"]] = a
            cambios += 1
    _escribir(DATA / "seguimiento.json", {"version": 1, "acciones": sorted(por_id.values(), key=lambda a: a.get("creado") or "")})
    cifrar_perfiles(silencioso=True)
    print(f"Seguimiento: {cambios} acciones nuevas o actualizadas · {len(por_id)} en total")
    return cambios


def restaurar_respaldo(clave: str | None = None):
    admin = next((p for p in perfiles() if p.get("admin")), None)
    clave = clave or (_leer(CLAVES, {}) or {}).get(admin["id"] if admin else "")
    if not clave:
        raise SystemExit("Indique la contraseña del administrador: python etl/perfiles.py restaurar-respaldo <clave>")
    datos = descifrar(_leer(DIR_SEGURO / "respaldo.json"), clave)
    with tarfile.open(fileobj=io.BytesIO(datos), mode="r:gz") as tar:
        miembros = [m for m in tar.getmembers() if m.name.startswith("data/") and ".." not in m.name]
        tar.extractall(RAIZ, members=miembros, filter="data")
    print(f"Respaldo restaurado: {len(miembros)} archivos en data/")


# ---------------------------------------------------------------- bitácora en línea (Google Apps Script)

def config_bitacora(lista=None) -> dict:
    """{url, hoja, tokens}: crea las claves de acceso que falten y quita las de perfiles eliminados."""
    lista = lista if lista is not None else perfiles()
    cfg = _leer(BITACORA, {}) or {}
    tokens = cfg.get("tokens", {})
    ids = {p["id"] for p in lista}
    cambio = False
    for pid in ids - set(tokens):
        tokens[pid] = secrets.token_urlsafe(32)
        cambio = True
    for pid in set(tokens) - ids:
        del tokens[pid]
        cambio = True
    cfg["tokens"] = tokens
    if cambio or not BITACORA.exists():
        _escribir(BITACORA, {"_comentario": "Bitácora en línea: URL de la aplicación web de Google y claves de acceso por perfil. "
                                            "NO subir a GitHub (está en .gitignore).", **{k: v for k, v in cfg.items() if k != "_comentario"}})
    return cfg


def generar_script_bitacora() -> Path:
    """Escribe bitacora/Codigo.gs con la huella de la clave de cada perfil (nunca la clave)."""
    lista = perfiles()
    cfg = config_bitacora(lista)
    conf = {"perfiles": {p["id"]: {"hash": hashlib.sha256(cfg["tokens"][p["id"]].encode()).hexdigest(),
                                   "admin": bool(p.get("admin")), "lineas": [] if p.get("admin") else p.get("lineas", [])}
                         for p in lista}}
    plantilla = PLANTILLA_GS.read_text(encoding="utf-8")
    codigo = plantilla.replace("/*CONFIG*/{}/*FIN_CONFIG*/", "/*CONFIG*/" + json.dumps(conf, ensure_ascii=False) + "/*FIN_CONFIG*/")
    SALIDA_GS.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_GS.write_text(codigo, encoding="utf-8")
    return SALIDA_GS


def guardar_url_bitacora(url: str):
    if not url.startswith("https://script.google.com/") and not url.startswith("http://localhost"):
        raise SystemExit("La URL debe ser la de la aplicación web: https://script.google.com/macros/s/.../exec")
    cfg = config_bitacora()
    cfg["url"] = url.strip()
    _escribir(BITACORA, cfg)
    cifrar_perfiles(silencioso=True)
    print("URL de la bitácora guardada y paquetes cifrados de nuevo (publica data/seguro para activarla).")


def api_bitacora(op: str, perfil_id: str | None = None, **extra) -> dict:
    """Llama a la bitácora en línea (por defecto como administrador). Lanza RuntimeError si falla."""
    import urllib.request
    cfg = _leer(BITACORA, {}) or {}
    if not cfg.get("url"):
        raise RuntimeError("La bitácora en línea no está configurada")
    pid = perfil_id or next((p["id"] for p in perfiles() if p.get("admin")), "admin")
    cuerpo = json.dumps({"op": op, "perfil": pid, "token": cfg["tokens"][pid], **extra}).encode("utf-8")
    pedido = urllib.request.Request(cfg["url"], data=cuerpo, headers={"Content-Type": "text/plain;charset=utf-8"})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    if not d.get("ok"):
        raise RuntimeError(d.get("error") or "Error de la bitácora")
    return d


MINIMO = 10


def validar_clave(clave: str) -> str | None:
    """Devuelve el problema de la contraseña, o None si sirve."""
    if len(clave) < MINIMO:
        return f"debe tener al menos {MINIMO} caracteres"
    if clave.strip() != clave:
        return "no puede empezar ni terminar con espacios"
    if clave.isdigit() or clave.isalpha():
        return "debe combinar letras y números"
    return None


def editar():
    """Menú en consola para cambiar contraseñas; al terminar vuelve a cifrar los datos."""
    from getpass import getpass
    lista = perfiles()
    cl = claves(lista, avisar=False)
    cambios = 0
    while True:
        print("\nPerfiles:")
        for i, p in enumerate(lista, 1):
            print(f"  {i}. {p['nombre']}  ({p['id']})")
        op = input("\nNúmero del perfil a cambiar (Enter para terminar): ").strip()
        if not op:
            break
        if not op.isdigit() or not 1 <= int(op) <= len(lista):
            print("Opción no válida.")
            continue
        p = lista[int(op) - 1]
        print(f"\nNueva contraseña para {p['nombre']} (no se verá al escribir; Enter vacío = generar una automática).")
        nueva = getpass("Contraseña: ")
        if not nueva:
            nueva = generar_clave()
            print(f"Se generó una contraseña automática; la verás en {CLAVES.relative_to(RAIZ)}.")
        else:
            problema = validar_clave(nueva)
            if problema:
                print(f"No se cambió: la contraseña {problema}.")
                continue
            if getpass("Repite la contraseña: ") != nueva:
                print("No se cambió: las contraseñas no coinciden.")
                continue
        cl[p["id"]] = nueva
        _escribir(CLAVES, cl)
        cambios += 1
        print(f"Contraseña de '{p['nombre']}' actualizada.")
    if cambios:
        cifrar_perfiles(silencioso=True)
        print(f"\n{cambios} contraseña(s) cambiada(s) y datos cifrados de nuevo.")
        print("Para publicar: git add data/seguro  ->  git commit -m \"Cambio de contraseñas\"  ->  git push")
    else:
        print("Sin cambios.")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "lista"
    if cmd == "cifrar":
        cifrar_perfiles()
    elif cmd == "lista":
        cl = claves(avisar=True)
        for p in perfiles():
            alcance = "todo" if p.get("admin") else ", ".join(p.get("lineas", []))
            print(f"{p['id']:<14} {p['nombre']:<28} {alcance:<40} contraseña: {'definida' if cl.get(p['id']) else 'falta'}")
    elif cmd == "editar":
        editar()
    elif cmd == "clave" and len(args) >= 2:
        if args[1] not in {p["id"] for p in perfiles()}:
            raise SystemExit(f"No existe el perfil '{args[1]}'")
        if len(args) > 2 and validar_clave(args[2]):
            raise SystemExit(f"La contraseña {validar_clave(args[2])}.")
        cl = claves(avisar=False)
        cl[args[1]] = args[2] if len(args) > 2 else generar_clave()
        _escribir(CLAVES, cl)
        cifrar_perfiles(silencioso=True)
        print(f"Contraseña de '{args[1]}' actualizada en config/perfiles.local.json y paquetes regenerados")
    elif cmd == "importar-seguimiento" and len(args) >= 2:
        importar_seguimiento(args[1])
    elif cmd == "bitacora":
        ruta = generar_script_bitacora()
        print(f"Código generado en {ruta.relative_to(RAIZ)}. Pégalo completo en Extensiones › Apps Script de la hoja de la bitácora.")
    elif cmd == "bitacora-url" and len(args) > 1:
        guardar_url_bitacora(args[1])
    elif cmd == "restaurar-respaldo":
        restaurar_respaldo(args[1] if len(args) > 1 else None)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
