"""
CENTRAL · ETL de indicadores de calidad de posventa.

Lee los Excel de cada fuente configurada en config/fuentes.json, valida y
homologa los datos, los consolida en un histórico versionado y publica los
JSON que consume el portal (data/).

Uso:
    python etl/central_etl.py procesar                 # todas las fuentes activas
    python etl/central_etl.py procesar --fuente demo_claro_ec
    python etl/central_etl.py procesar --simular       # valida sin escribir nada
    python etl/central_etl.py procesar --permitir-correcciones
    python etl/central_etl.py procesar --fuente entel_emp_monitoreo --reprocesar
    python etl/central_etl.py publicar                 # regenera solo los JSON
    python etl/central_etl.py validar-config

Formatos de fuente (config/fuentes.json):
    ancho   -> una fila por cuenta y periodo, un indicador por columna.
    largo   -> una fila por cuenta, periodo e indicador.
    detalle -> una fila por evaluación/encuesta (bases originales de los dashboards);
               el ETL agrega por cuenta y mes (promedio o porcentaje de casos).
La carpeta de una fuente puede estar fuera del repositorio (ej. ../ENTEL/ENTEL_BI_IN/Reporte EPA).

Reglas del histórico:
    * Clave única de una medición: empresa + país + cuenta + indicador + periodo.
    * Un archivo ya procesado (mismo hash SHA-256) se omite.
    * Si llega la misma clave con el mismo valor, se ignora (duplicado).
    * Si llega con un valor distinto:
        - periodo en curso (>= --periodo-abierto, por defecto el mes actual):
          se crea una nueva versión y la anterior queda como no vigente;
        - periodo cerrado: se rechaza como CONFLICTO_HISTORICO, salvo que se
          use --permitir-correcciones (también versiona, nunca borra).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html as html_lib
import json
import os
import shutil
import urllib.request
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

# En el .exe (PyInstaller) la raíz es la carpeta donde está el ejecutable, junto a config/ y data/.
RAIZ = Path(os.environ.get("CALIDAD_A365_RAIZ") or (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent.parent))
CONFIG = RAIZ / "config"
DATA = RAIZ / "data"
HISTORICO = DATA / "historico" / "mediciones.csv"
REGISTRO = DATA / "cargas" / "registro_cargas.csv"
DIR_ERRORES = DATA / "cargas" / "errores"
DIR_DRIVE = RAIZ / "etl" / "entrada" / "drive"    # copias locales de lo descargado de Google Drive (no se versionan)

CLAVE = ["empresa_id", "pais_id", "linea_id", "cuenta", "indicador_id", "periodo"]
TOTAL = "(TOTAL)"   # cuenta que resume todo el servicio, calculada como el dashboard (sin mínimo de muestras)
COLS_HISTORICO = CLAVE + [
    "fecha_medicion", "valor", "meta_archivo", "muestras",
    "fuente_id", "archivo", "archivo_hash", "carga_id", "fecha_carga",
    "version", "vigente",
]
COLS_REGISTRO = [
    "carga_id", "fecha_carga", "fuente_id", "archivo", "archivo_hash", "estado",
    "filas_leidas", "mediciones_validas", "nuevas", "versionadas",
    "duplicadas", "rechazadas", "conflictos", "errores", "simulacion",
]
COLS_ERRORES = ["carga_id", "fuente_id", "archivo", "fila_excel", "campo", "tipo_error", "valor", "detalle"]

MESES = {
    "ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3, "abr": 4, "abril": 4,
    "may": 5, "mayo": 5, "jun": 6, "junio": 6, "jul": 7, "julio": 7, "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "set": 9, "setiembre": 9, "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11, "dic": 12, "diciembre": 12,
}


# ---------------------------------------------------------------- utilidades

def normalizar(texto) -> str:
    """Minúsculas, sin tildes, sin signos y con espacios simples."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9%]+", " ", t.lower())
    return " ".join(t.split())


def normalizar_cuenta(texto) -> str:
    return " ".join(str(texto).split()).upper() if not vacio(texto) else ""


def vacio(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def a_numero(v):
    """Convierte 85,3% / '1.234,5' / 0.853 / ' 85 ' en float. Devuelve None si no es numérico."""
    if vacio(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace("%", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s):      # 1.234,5
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):    # 1,234.5
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def a_fecha(v):
    if vacio(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return pd.Timestamp(v).normalize()
    if isinstance(v, (int, float)) and 20000 < v < 80000:     # serial de Excel
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
    s = str(v).strip()
    formato = "%Y-%m-%d" if re.match(r"^\d{4}-\d{2}-\d{2}", s) else None
    f = pd.to_datetime(s[:10] if formato else s, format=formato, dayfirst=True, errors="coerce")
    return None if pd.isna(f) else f.normalize()


def a_periodo(v):
    """Acepta 2026-09, 09/2026, 'sep-2026', 'Septiembre 2026', fechas. Devuelve 'YYYY-MM' o None."""
    if vacio(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return pd.Timestamp(v).strftime("%Y-%m")
    s = normalizar(v)
    m = re.fullmatch(r"(\d{4}) (\d{1,2})", s)
    if m:
        a, mes = int(m[1]), int(m[2])
    else:
        m = re.fullmatch(r"(\d{1,2}) (\d{4})", s)
        if m:
            mes, a = int(m[1]), int(m[2])
        else:
            m = re.fullmatch(r"([a-z]+) (\d{2,4})", s)
            if not m or m[1] not in MESES:
                f = a_fecha(v)
                return f.strftime("%Y-%m") if f is not None else None
            mes, a = MESES[m[1]], int(m[2])
            a = a + 2000 if a < 100 else a
    if not (1 <= mes <= 12 and 2000 <= a <= 2100):
        return None
    return f"{a:04d}-{mes:02d}"


def hash_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_json(ruta: Path):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def escribir_json(ruta: Path, datos, compacto=False):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        if compacto:
            json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(datos, f, ensure_ascii=False, indent=2)


def leer_csv(ruta: Path, columnas):
    if not ruta.exists():
        return pd.DataFrame(columns=columnas)
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8")


# ------------------------------------------------------------ configuración

class Catalogo:
    def __init__(self):
        cfg = leer_json(CONFIG / "indicadores.json")
        self.indicadores = {i["id"]: i for i in cfg["indicadores"]}
        self.alias = {}
        for i in cfg["indicadores"]:
            for a in [i["id"], i["nombre"], *i.get("alias", [])]:
                self.alias[normalizar(a)] = i["id"]
        self.metas_empresa = {k: v for k, v in cfg.get("metas_por_empresa", {}).items() if not k.startswith("_")}
        self.metas_son_ejemplo = cfg.get("metas_son_ejemplo", False)
        hom = leer_json(CONFIG / "homologacion.json") if (CONFIG / "homologacion.json").exists() else {}
        self.cuentas = {
            ambito: {normalizar_cuenta(normalizar(k)): v for k, v in mapa.items()}
            for ambito, mapa in hom.get("cuentas", {}).items()
        }
        portal = leer_json(CONFIG / "portal.json")
        self.empresas = {e["id"]: {p["id"] for p in e["paises"]} for e in portal["empresas"]}
        self.lineas = {d["id"] for e in portal["empresas"] for p in e["paises"] for d in p.get("dashboards", [])}

    def indicador(self, nombre):
        return self.alias.get(normalizar(nombre))

    def cuenta(self, nombre, empresa, pais):
        base = normalizar_cuenta(nombre)
        clave = normalizar_cuenta(normalizar(nombre))
        for ambito in (f"{empresa}|{pais}", "*"):
            if clave in self.cuentas.get(ambito, {}):
                return self.cuentas[ambito][clave]
        return base

    def meta(self, empresa, pais, indicador):
        ind = self.indicadores[indicador]
        propio = self.metas_empresa.get(f"{empresa}|{pais}", {}).get(indicador, {})
        return propio.get("meta", ind.get("meta")), propio.get("umbral_critico", ind.get("umbral_critico"))

    def estado(self, valor, meta, umbral, indicador):
        if meta is None or valor is None:
            return "SIN_META"
        mayor = self.indicadores[indicador].get("sentido", "mayor_mejor") == "mayor_mejor"
        if (valor >= meta) if mayor else (valor <= meta):
            return "OK"
        if umbral is not None and ((valor <= umbral) if mayor else (valor >= umbral)):
            return "CRITICO"
        return "ALERTA"


def validar_config(catalogo: Catalogo, fuentes) -> list[str]:
    problemas = []
    ids = set()
    for f in fuentes:
        fid = f.get("id", "?")
        if fid in ids:
            problemas.append(f"Fuente duplicada: {fid}")
        ids.add(fid)
        if not f.get("activo"):
            continue
        if f.get("linea_id") and f["linea_id"] not in catalogo.lineas:
            problemas.append(f"{fid}: linea_id '{f['linea_id']}' no es un dashboard de portal.json")
        if f.get("empresa_id") not in catalogo.empresas:
            problemas.append(f"{fid}: empresa_id '{f.get('empresa_id')}' no existe en portal.json")
        elif f.get("pais_id") not in catalogo.empresas[f["empresa_id"]]:
            problemas.append(f"{fid}: pais_id '{f.get('pais_id')}' no existe para {f['empresa_id']}")
        if f.get("formato") not in ("ancho", "largo", "detalle"):
            problemas.append(f"{fid}: formato debe ser 'ancho', 'largo' o 'detalle'")
        elif not ruta_fuente(f).is_dir():
            problemas.append(f"{fid}: no existe la carpeta {f.get('carpeta')}")
        if f.get("formato") == "detalle":
            if not f.get("indicadores_detalle"):
                problemas.append(f"{fid}: el formato detalle requiere 'indicadores_detalle'")
            if f.get("conteo") and f["conteo"] not in catalogo.indicadores:
                problemas.append(f"{fid}: conteo '{f['conteo']}' no existe en el catálogo")
            if f.get("hoja") == "*" and not f.get("encabezado_contiene"):
                problemas.append(f"{fid}: con hoja '*' hay que indicar 'encabezado_contiene'")
            for d in f.get("indicadores_detalle", []):
                if d.get("indicador") not in catalogo.indicadores:
                    problemas.append(f"{fid}: indicador inexistente '{d.get('indicador')}'")
                if d.get("agregacion", "promedio") not in ("promedio", "porcentaje", "nota_ponderada"):
                    problemas.append(f"{fid}: agregación inválida en {d.get('indicador')}")
        cols = f.get("columnas", {})
        if "fecha" not in cols and "periodo" not in cols and not {"anio", "mes"} <= set(cols):
            problemas.append(f"{fid}: falta mapear 'fecha', 'periodo' o 'anio' + 'mes'")
        if "cuenta" not in cols and not f.get("cuenta_fija"):
            problemas.append(f"{fid}: falta mapear 'cuenta' o definir 'cuenta_fija'")
        if f.get("formato") == "largo" and not {"indicador", "valor"} <= set(cols):
            problemas.append(f"{fid}: el formato largo requiere 'indicador' y 'valor'")
        if f.get("formato") == "ancho":
            for col, ind in f.get("columnas_indicador", {}).items():
                if ind not in catalogo.indicadores:
                    problemas.append(f"{fid}: la columna '{col}' apunta a un indicador inexistente '{ind}'")
    return problemas


# ---------------------------------------------------------------- lectura

class Errores:
    LIMITE_POR_TIPO = 100   # en bases de detalle un mismo error puede repetirse miles de veces

    def __init__(self, carga_id, fuente_id, archivo):
        self.base = {"carga_id": carga_id, "fuente_id": fuente_id, "archivo": archivo}
        self.filas = []
        self.conteo = {}

    def add(self, fila, campo, tipo, valor="", detalle=""):
        self.conteo[tipo] = self.conteo.get(tipo, 0) + 1
        if self.conteo[tipo] <= self.LIMITE_POR_TIPO:
            self.filas.append({**self.base, "fila_excel": fila, "campo": campo, "tipo_error": tipo,
                               "valor": "" if vacio(valor) else str(valor)[:200], "detalle": detalle})

    @property
    def total(self):
        return sum(self.conteo.values())

    def cerrar(self):
        for tipo, n in self.conteo.items():
            if n > self.LIMITE_POR_TIPO:
                self.filas.append({**self.base, "fila_excel": "", "campo": "", "tipo_error": tipo, "valor": str(n),
                                   "detalle": f"{n} casos en total; se detallan los primeros {self.LIMITE_POR_TIPO}"})


def coincide(v, lista) -> bool:
    """True si v está en la lista (números como números; textos sin tildes ni mayúsculas)."""
    n = a_numero(v)
    t = normalizar(v)
    for x in lista:
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            if n is not None and abs(n - x) < 1e-9:
                return True
        elif t == normalizar(x):
            return True
    return False


def norm_id(v) -> str:
    if vacio(v):
        return ""
    n = a_numero(v)
    if n is not None and float(n).is_integer():
        return str(int(n))
    return normalizar(v)


def palabras_reales(texto, quitar=None) -> int:
    """Cantidad de palabras de 2+ letras que no son una letra repetida ('xxxxx'), como es_prueba() de Claro."""
    t = re.sub(quitar, "", str(texto).upper()).strip() if quitar else str(texto)
    return len([p for p in t.split() if len(p) > 1 and not re.fullmatch(r"(.)\1+", p)])


def valor_item(v, si, no):
    """1 = cumple, 0 = no cumple, None = no aplica / vacío (como item() de los scripts de Claro)."""
    if vacio(v):
        return None
    t = normalizar(v)
    if any(t.startswith(normalizar(x)) for x in si):
        return 1
    if any(t.startswith(normalizar(x)) for x in no):
        return 0
    return None


def nota_ponderada(r, d, cols_items, col_base):
    """Nota por bloques ponderados con anulación por error crítico (réplica de los dashboards de Claro).
    Sin 'columna_base': cada bloque = promedio ponderado de sus ítems; nota = suma(peso_bloque * bloque) / suma(pesos).
    Con 'columna_base': la nota viene en esa columna (ej. 'EC'). En ambos casos, un ítem crítico en 0 deja la nota en 0."""
    si, no = d.get("si", ["SI CUMPLE"]), d.get("no", ["NO CUMPLE"])
    vals = {it["columna"]: valor_item(r[cols_items[it["columna"]]], si, no)
            for it in d.get("items", []) if it["columna"] in cols_items}
    if col_base:
        fin = a_numero(r[col_base])
    else:
        got = cap = 0.0
        for bloque, peso in d.get("bloques", {}).items():
            its = [it for it in d["items"] if it["bloque"] == bloque and vals.get(it["columna"]) is not None]
            if not its:
                continue
            w = sum(it["peso"] for it in its)
            got += peso * sum(it["peso"] * vals[it["columna"]] for it in its) / w
            cap += peso
        fin = got / cap * 100 if cap else None
    if fin is None:
        return None
    if any(it.get("critico") and vals.get(it["columna"]) == 0 for it in d.get("items", [])):
        return 0.0
    return fin


def recodificar(v, mapa):
    for k, x in mapa.items():
        clave = a_numero(k) if re.fullmatch(r"-?\d+(\.\d+)?", str(k)) else k
        if coincide(v, [clave]):
            return float(x)
    return None


# ---------------------------------------------------------------- Google Drive (carpetas y hojas públicas)

def _descargar(url: str, destino: Path):
    """Descarga a un temporal y solo reemplaza el destino si llegó un Excel válido (zip 'PK')."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(pedido, timeout=300) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    with open(tmp, "rb") as f:
        valido = f.read(2) == b"PK"
    if not valido:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Drive no devolvió un Excel (¿el archivo dejó de ser público?)")
    tmp.replace(destino)


def listar_drive(carpeta_id: str) -> list[tuple[str, str]]:
    """[(nombre, id_archivo)] de una carpeta pública de Drive (vista embebida, sin iniciar sesión)."""
    url = f"https://drive.google.com/embeddedfolderview?id={carpeta_id}"
    pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    pagina = urllib.request.urlopen(pedido, timeout=60).read().decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r'<a href="([^"]+)"[^>]*>.*?<div class="flip-entry-title">(.*?)</div>', pagina, re.S):
        f = re.search(r"/file/d/([\w-]+)", m.group(1))
        if f:
            out.append((html_lib.unescape(m.group(2)).strip(), f.group(1)))
    return out


def fecha_en_nombre(nombre: str):
    """'Reporte ... - 12.10.xlsx' -> 2026-10-12 (año actual, o el anterior si la fecha quedaría en el futuro)."""
    m = re.search(r"(\d{1,2})[.\-_](\d{1,2})(?:[.\-_](\d{2,4}))?(?=\D*\.xls)", nombre)
    if not m:
        return datetime.min
    d, mes = int(m[1]), int(m[2])
    hoy = datetime.now()
    anio = int(m[3]) + (2000 if m[3] and len(m[3]) == 2 else 0) if m[3] else hoy.year
    try:
        f = datetime(anio, mes, d)
    except ValueError:
        return datetime.min
    return f.replace(year=anio - 1) if not m[3] and f > hoy.replace(hour=23, minute=59) else f


def sincronizar_drive(fuente) -> Path | None:
    """Trae de Drive el archivo más reciente de la fuente y devuelve su ruta local (None si no usa Drive).
    'drive': {"carpeta_id", "patron"} -> el archivo con la fecha más reciente en el nombre;
    'drive': {"hoja_id", "nombre"}    -> una hoja de Google exportada a Excel (se descarga siempre).
    Si Drive falla, se usa la última copia descargada; si no hay, la carpeta local de la fuente."""
    d = fuente.get("drive")
    if not d:
        return None
    destino_dir = DIR_DRIVE / fuente["id"]
    try:
        if d.get("carpeta_id"):
            candidatos = [(n, i) for n, i in listar_drive(d["carpeta_id"])
                          if fnmatch.fnmatch(normalizar(n), normalizar(d.get("patron", "*.xlsx")).replace(" xls", "*.xls"))
                          or fnmatch.fnmatch(n, d.get("patron", "*.xlsx"))]
            if not candidatos:
                raise RuntimeError(f"la carpeta no tiene archivos '{d.get('patron')}'")
            nombre, id_archivo = max(candidatos, key=lambda x: (fecha_en_nombre(x[0]), x[0]))
            destino = destino_dir / nombre
            if not destino.exists() or d.get("siempre"):
                _descargar(f"https://drive.usercontent.google.com/download?id={id_archivo}&export=download&confirm=t", destino)
                print(f"[{fuente['id']}] Drive: descargado {nombre}")
            else:
                print(f"[{fuente['id']}] Drive: {nombre} ya estaba descargado")
        else:
            destino = destino_dir / d.get("nombre", f"{d['hoja_id']}.xlsx")
            _descargar(f"https://docs.google.com/spreadsheets/d/{d['hoja_id']}/export?format=xlsx", destino)
            print(f"[{fuente['id']}] Drive: hoja actualizada ({destino.name})")
        return destino
    except Exception as e:
        previos = sorted((p for p in destino_dir.glob("*.xls*")), key=lambda p: (fecha_en_nombre(p.name), p.stat().st_mtime))
        print(f"[{fuente['id']}] Drive no disponible ({e}); se usa {'la copia ' + previos[-1].name if previos else 'la carpeta local'}")
        return previos[-1] if previos else None


def ruta_fuente(fuente) -> Path:
    c = Path(fuente["carpeta"])
    return c if c.is_absolute() else (RAIZ / c).resolve()


def relativa(ruta: Path) -> str:
    try:
        return Path(os.path.relpath(ruta, RAIZ)).as_posix()
    except ValueError:      # otra unidad de disco en Windows
        return ruta.as_posix()


def columnas_necesarias(fuente) -> set:
    nombres = []
    for v in fuente.get("columnas", {}).values():
        nombres += v if isinstance(v, list) else [v]
    for d in fuente.get("indicadores_detalle", []):
        nombres += [d.get("columna", ""), d.get("columna_base", "")]
        nombres += [it["columna"] for it in d.get("items", [])]
    for f in fuente.get("filtros", []):
        nombres += [f.get("columna", "")] + f.get("columnas", []) + f.get("alguno_no_vacio", [])
    nombres += [fuente.get("id_unico", "")]
    return {normalizar(n) for n in nombres if n}


def archivos_complemento(fuente) -> list:
    """Descargas diarias que complementan la base principal (ej. 'Reporte Pauta Outbound*')."""
    out = []
    for c in fuente.get("complementos", []):
        carpeta = ruta_fuente({"carpeta": c["carpeta"]})
        out += [(p, c) for p in carpeta.glob(c.get("patron", "*.xlsx")) if not p.name.startswith("~$")]
    return sorted(out, key=lambda x: (x[0].stat().st_mtime, x[0].name))


def unir_complementos(df: pd.DataFrame, fuente: dict, err: Errores) -> pd.DataFrame:
    """Agrega a la base las filas de los complementos cuyo id_unico todavía no está (como el script del dashboard)."""
    clave = normalizar(fuente["id_unico"])
    df = df.copy()
    df.columns = [normalizar(c) for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    if clave not in df.columns:
        return df
    ids = set(df[clave].map(norm_id))
    necesarias = columnas_necesarias(fuente)
    agregadas = 0
    for ruta, c in archivos_complemento(fuente):
        try:
            crudo = pd.read_excel(ruta, sheet_name=c.get("hoja", 0), header=None)
        except Exception as e:
            err.add("", "", "ARCHIVO_ILEGIBLE", ruta.name, str(e))
            continue
        enc = normalizar(c.get("encabezado_contiene", fuente["id_unico"]))
        fila = next((i for i in range(min(15, len(crudo))) if enc in {normalizar(x) for x in crudo.iloc[i]}), None)
        if fila is None:
            err.add("", "", "COLUMNA_FALTANTE", ruta.name, f"Complemento sin encabezado '{enc}'")
            continue
        parte = crudo.iloc[fila + 1:].copy()
        parte.columns = [f"_{j}" if vacio(x) else normalizar(x) for j, x in enumerate(crudo.iloc[fila])]
        parte = parte.loc[:, ~pd.Index(parte.columns).duplicated()]
        parte = parte[[x for x in parte.columns if x in necesarias and x in df.columns]]
        nuevas = parte[~parte[clave].map(norm_id).isin(ids) & ~parte[clave].map(vacio)]
        if len(nuevas):
            df = pd.concat([df, nuevas], ignore_index=True)
            ids |= set(nuevas[clave].map(norm_id))
            agregadas += len(nuevas)
    if agregadas:
        print(f"    + {agregadas} filas desde complementos ({len(archivos_complemento(fuente))} archivos)")
    return df


def resolver_columnas(df: pd.DataFrame, mapeo: dict) -> dict:
    """Devuelve {campo_canonico: columna_real} buscando alias normalizados."""
    reales = {normalizar(c): c for c in df.columns}
    out = {}
    for campo, alias in mapeo.items():
        for a in (alias if isinstance(alias, list) else [alias]):
            if normalizar(a) in reales:
                out[campo] = reales[normalizar(a)]
                break
    return out


def leer_todas_las_hojas(ruta: Path, fuente: dict, err: Errores):
    """Une todas las hojas que tengan el encabezado indicado en 'encabezado_contiene' (ej. una hoja por mes).
    Agrega la columna '_hoja' = "<nombre de hoja> <anio>" para poder usarla como periodo."""
    try:
        hojas = pd.read_excel(ruta, sheet_name=None, header=None)
    except Exception as e:
        err.add("", "", "ARCHIVO_ILEGIBLE", detalle=str(e))
        return None
    clave = normalizar(fuente.get("encabezado_contiene", ""))
    partes = []
    for nombre, crudo in hojas.items():
        if fuente.get("solo_hojas_mes") and a_periodo(f"{nombre} {fuente.get('anio', 2000)}") is None:
            continue    # ej. Dotacion, PLANTILLA
        fila_enc = next((i for i in range(min(15, len(crudo)))
                         if clave in {normalizar(x) for x in crudo.iloc[i]}), None)
        if fila_enc is None:
            continue
        parte = crudo.iloc[fila_enc + 1:].copy()
        # Nombres normalizados: cada hoja puede escribir distinto el mismo encabezado ("Nota" / "NOTA ").
        parte.columns = [f"_{j}" if vacio(c) else normalizar(c) for j, c in enumerate(crudo.iloc[fila_enc])]
        parte = parte.loc[:, ~pd.Index(parte.columns).duplicated()]
        parte["_hoja"] = f"{nombre} {fuente.get('anio', '')}".strip()
        partes.append(parte)
    if not partes:
        err.add("", "encabezado", "COLUMNA_FALTANTE", fuente.get("encabezado_contiene"), "Ninguna hoja tiene ese encabezado")
        return None
    return pd.concat(partes, ignore_index=True)


def leer_archivo(ruta: Path, fuente: dict, catalogo: Catalogo, err: Errores):
    """Convierte un Excel en una lista de mediciones en formato largo canónico."""
    df = None
    if fuente.get("hoja") == "*":
        df = leer_todas_las_hojas(ruta, fuente, err)
        if df is None:
            return [], 0
    opciones = {}
    if fuente["formato"] == "detalle":     # bases grandes: leer solo las columnas configuradas
        necesarias = columnas_necesarias(fuente)
        opciones["usecols"] = lambda c: normalizar(c) in necesarias
    try:
        if df is None:
            df = pd.read_excel(ruta, sheet_name=fuente.get("hoja", 0), header=fuente.get("fila_encabezado", 0), **opciones)
    except Exception as e:  # archivo corrupto, hoja inexistente, etc.
        err.add("", "", "ARCHIVO_ILEGIBLE", detalle=str(e))
        return [], 0
    df = df.dropna(how="all")
    if fuente.get("complementos"):
        df = unir_complementos(df, fuente, err)
    if fuente.get("id_unico"):
        col_id = resolver_columnas(df, {"x": [fuente["id_unico"]]}).get("x")
        if col_id is not None:
            ids = df[col_id].map(norm_id)
            validos = ids.str.fullmatch(r"\d+") if fuente.get("id_solo_numerico") else ids != ""
            # Outbound y E-commerce no quitan repetidos de la base (solo de los complementos): id_deduplicar = false
            repetidos = validos & ids.duplicated(keep=fuente.get("id_mantener", "first")) & fuente.get("id_deduplicar", True)
            if repetidos.any():
                err.add("", col_id, "DUPLICADO_EN_ARCHIVO", int(repetidos.sum()),
                        f"{int(repetidos.sum())} filas con {fuente['id_unico']} repetido se cuentan una vez")
            df = df[validos & ~repetidos]
    filas_leidas = len(df)
    offset = fuente.get("fila_encabezado", 0) + 2   # fila Excel = índice + offset

    mapeo = {k: v for k, v in fuente.get("columnas", {}).items() if v and v != [""]}
    cols = resolver_columnas(df, mapeo)
    obligatorias = ["cuenta"] if not fuente.get("cuenta_fija") else []
    obligatorias += ["indicador", "valor"] if fuente["formato"] == "largo" else []
    if "fecha" not in cols and "periodo" not in cols and not {"anio", "mes"} <= set(cols):
        obligatorias.append("fecha|periodo")
    faltan = [c for c in obligatorias if c not in cols]

    col_ind = {}
    if fuente["formato"] == "ancho":
        for c, ind in fuente.get("columnas_indicador", {}).items():
            real = resolver_columnas(df, {"x": [c]}).get("x") if c else None
            if real:
                col_ind[real] = ind
            elif c:
                err.add(1, c, "COLUMNA_FALTANTE", detalle="Columna de indicador configurada pero ausente en el archivo")
        if not col_ind:
            faltan.append("columnas_indicador")
    det_cols = {}
    if fuente["formato"] == "detalle":
        for d in fuente.get("indicadores_detalle", []):
            if d.get("agregacion") == "nota_ponderada":
                items = {it["columna"]: resolver_columnas(df, {"x": [it["columna"]]}).get("x") for it in d.get("items", [])}
                for c in [c for c, real in items.items() if real is None]:
                    err.add(1, c, "COLUMNA_FALTANTE", detalle=f"Ítem de {d['indicador']} ausente")
                base = resolver_columnas(df, {"x": [d["columna_base"]]}).get("x") if d.get("columna_base") else None
                if d.get("columna_base") and base is None:
                    err.add(1, d["columna_base"], "COLUMNA_FALTANTE", detalle=f"Columna base de {d['indicador']} ausente")
                    continue
                det_cols[d["indicador"]] = ({c: real for c, real in items.items() if real}, base)
                continue
            real = resolver_columnas(df, {"x": [d["columna"]]}).get("x")
            if real:
                det_cols[d["indicador"]] = real
            else:
                err.add(1, d["columna"], "COLUMNA_FALTANTE", detalle=f"Columna del indicador {d['indicador']} ausente")
        if not det_cols:
            faltan.append("indicadores_detalle")
        for flt in fuente.get("filtros", []):
            if "alguno_no_vacio" in flt:     # al menos una de estas columnas con valor (ej. criterios evaluados)
                reales = [x for x in (resolver_columnas(df, {"x": [c]}).get("x") for c in flt["alguno_no_vacio"]) if x]
                if not reales:
                    faltan.append("filtro:alguno_no_vacio")
                else:
                    df = df[df[reales].apply(lambda fila: any(a_numero(v) is not None for v in fila), axis=1)]
                continue
            if "min_palabras" in flt:       # primer nombre no vacío entre varias columnas con N palabras reales
                reales = [x for x in (resolver_columnas(df, {"x": [c]}).get("x") for c in flt["columnas"]) if x]
                quitar = flt.get("quitar")

                def nombre(fila):
                    for c in reales:
                        t = re.sub(quitar, "", str(fila[c]).upper()).strip() if quitar and not vacio(fila[c]) else ("" if vacio(fila[c]) else str(fila[c]))
                        if t and t not in ("NA", "N/A", "NAN"):
                            return t
                    return ""
                df = df[df.apply(lambda fila: palabras_reales(nombre(fila)) >= flt["min_palabras"], axis=1)]
                continue
            real = resolver_columnas(df, {"x": [flt["columna"]]}).get("x")
            if real is None:
                faltan.append(f"filtro:{flt['columna']}")
            elif "incluir" in flt:
                df = df[df[real].map(lambda v, lista=flt["incluir"]: coincide(v, lista))]
            elif "excluir" in flt:
                df = df[~df[real].map(lambda v, lista=flt["excluir"]: coincide(v, lista))]
            elif flt.get("no_vacio"):
                df = df[~df[real].map(vacio)]
            elif flt.get("numerico"):
                df = df[df[real].map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and not vacio(v))]
    for c in faltan:
        err.add(1, c, "COLUMNA_FALTANTE", detalle=f"Columnas del archivo: {', '.join(map(str, df.columns))[:300]}")
    if faltan:
        return [], filas_leidas
    alias_fecha = mapeo.get("fecha", [])
    cols_fecha = [x for x in (resolver_columnas(df, {"x": [a]}).get("x") for a in
                              (alias_fecha if isinstance(alias_fecha, list) else [alias_fecha])) if x]
    grupos = {}     # solo formato detalle: (cuenta, periodo, indicador) -> [valores, fecha máxima, metas por fila]
    metas = {d["indicador"]: {normalizar_cuenta(normalizar(k)): v for k, v in d.get("metas_por_cuenta", {}).items()}
             for d in fuente.get("indicadores_detalle", [])}
    con_total = fuente["formato"] == "detalle" and fuente.get("total_servicio", True)

    def sumar(cuenta, periodo, ind, x, fecha):
        meta = metas.get(ind, {}).get(normalizar_cuenta(normalizar(cuenta)))
        for c in ([cuenta, TOTAL] if con_total else [cuenta]):
            g = grupos.setdefault((c, periodo, ind), [[], fecha, []])
            g[0].append(x)
            g[1] = max(g[1], fecha)
            g[2].append(meta)

    empresa, pais = fuente["empresa_id"], fuente["pais_id"]
    crudas = []
    for idx, r in df.iterrows():
        fila = idx + offset
        cuenta_raw = fuente.get("cuenta_fija") or r.get(cols.get("cuenta"))
        if vacio(cuenta_raw):
            err.add(fila, "cuenta", "VALOR_FALTANTE")
            continue
        fecha = next((f for f in (a_fecha(r[c]) for c in cols_fecha) if f is not None), None) if cols_fecha else None
        periodo = a_periodo(r[cols["periodo"]]) if "periodo" in cols else None
        if "anio" in cols and "mes" in cols:     # mes de medición informado en columnas propias
            a, mm = a_numero(r[cols["anio"]]), a_numero(r[cols["mes"]])
            periodo = f"{int(a):04d}-{int(mm):02d}" if a and mm and 2000 <= a <= 2100 and 1 <= mm <= 12 else None
            if periodo is None:
                err.add(fila, "mes", "FECHA_INVALIDA", f"{r[cols['anio']]}-{r[cols['mes']]}")
                continue
        if "fecha" in cols and fecha is None and not periodo:
            err.add(fila, "fecha", "FECHA_INVALIDA" if not vacio(r[cols["fecha"]]) else "VALOR_FALTANTE", r[cols["fecha"]])
            continue
        if "periodo" in cols and periodo is None and fecha is None:
            err.add(fila, "periodo", "FECHA_INVALIDA" if not vacio(r[cols["periodo"]]) else "VALOR_FALTANTE", r[cols["periodo"]])
            continue
        periodo = periodo or fecha.strftime("%Y-%m")
        fecha = fecha or pd.Timestamp(f"{periodo}-01")

        muestras = a_numero(r[cols["muestras"]]) if "muestras" in cols else None
        meta_archivo = a_numero(r[cols["meta"]]) if "meta" in cols else None
        cuenta = catalogo.cuenta(cuenta_raw, empresa, pais)

        if fuente["formato"] == "detalle":
            if fuente.get("conteo"):
                sumar(cuenta, periodo, fuente["conteo"], 1.0, fecha)
            for d in fuente.get("indicadores_detalle", []):
                col = det_cols.get(d["indicador"])
                if isinstance(col, tuple):
                    x = nota_ponderada(r, d, *col)
                    if x is not None:
                        sumar(cuenta, periodo, d["indicador"], x, fecha)
                    continue
                if col is None:
                    continue
                if vacio(r[col]):
                    if d.get("vacio_es_negativo"):      # p. ej. venta sin marcar = no venta, como el dashboard
                        sumar(cuenta, periodo, d["indicador"], 0.0, fecha)
                    continue
                v = r[col]
                if "recodificar" in d:
                    x = recodificar(v, d["recodificar"])
                    if x is None:
                        continue
                elif d.get("agregacion", "promedio") == "porcentaje":
                    if coincide(v, d.get("positivos", [])):
                        x = 100.0
                    elif "negativos" not in d or coincide(v, d["negativos"]):
                        x = 0.0
                    else:
                        continue
                else:
                    x = a_numero(v)
                    if x is None:
                        err.add(fila, col, "TIPO_INVALIDO", v, "Se esperaba un número")
                        continue
                if d.get("multiplicar"):
                    x *= d["multiplicar"]
                sumar(cuenta, periodo, d["indicador"], x, fecha)
            continue

        if fuente["formato"] == "largo":
            pares = [(r[cols["indicador"]], r[cols["valor"]], cols["valor"])]
        else:
            pares = [(ind, r[c], c) for c, ind in col_ind.items()]

        for ind_raw, valor_raw, campo in pares:
            ind = ind_raw if ind_raw in catalogo.indicadores else catalogo.indicador(ind_raw)
            if ind is None:
                err.add(fila, "indicador", "INDICADOR_DESCONOCIDO", ind_raw,
                        "Agregar el alias en config/indicadores.json")
                continue
            if vacio(valor_raw):
                if fuente["formato"] == "largo":
                    err.add(fila, campo, "VALOR_FALTANTE")
                continue    # en formato ancho una celda vacía = indicador no medido
            valor = a_numero(valor_raw)
            if valor is None:
                err.add(fila, campo, "TIPO_INVALIDO", valor_raw, "Se esperaba un número")
                continue
            crudas.append({"fila": fila, "empresa_id": empresa, "pais_id": pais, "cuenta": cuenta,
                           "indicador_id": ind, "periodo": periodo, "fecha_medicion": fecha.strftime("%Y-%m-%d"),
                           "valor": valor, "meta_archivo": meta_archivo,
                           "muestras": int(muestras) if muestras is not None else None,
                           "_texto_porcentaje": isinstance(valor_raw, str) and "%" in valor_raw})

    if fuente["formato"] == "detalle":
        minimo = fuente.get("min_muestras", 1)
        for (cuenta, periodo, ind), (valores, fecha, metas_filas) in grupos.items():
            if ind == fuente.get("conteo"):
                crudas.append({"fila": "", "empresa_id": empresa, "pais_id": pais, "cuenta": cuenta,
                               "indicador_id": ind, "periodo": periodo, "fecha_medicion": fecha.strftime("%Y-%m-%d"),
                               "valor": float(len(valores)), "meta_archivo": None,
                               "muestras": len(valores), "_texto_porcentaje": True})
                continue
            if cuenta == TOTAL:    # total del servicio: meta = promedio de las metas de cada fila (como el dashboard)
                con_meta = [x for x in metas_filas if x is not None]
                crudas.append({"fila": "", "empresa_id": empresa, "pais_id": pais, "cuenta": cuenta,
                               "indicador_id": ind, "periodo": periodo, "fecha_medicion": fecha.strftime("%Y-%m-%d"),
                               "valor": sum(valores) / len(valores),
                               "meta_archivo": sum(con_meta) / len(con_meta) if con_meta else None,
                               "muestras": len(valores), "_texto_porcentaje": True})
                continue
            if len(valores) < minimo:
                err.add("", "muestras", "MUESTRA_INSUFICIENTE", len(valores),
                        f"{cuenta} · {ind} · {periodo}: {len(valores)} casos (mínimo {minimo})")
                continue
            crudas.append({"fila": "", "empresa_id": empresa, "pais_id": pais, "cuenta": cuenta,
                           "indicador_id": ind, "periodo": periodo, "fecha_medicion": fecha.strftime("%Y-%m-%d"),
                           "valor": sum(valores) / len(valores),
                           "meta_archivo": metas.get(ind, {}).get(normalizar_cuenta(normalizar(cuenta))),
                           "muestras": len(valores), "_texto_porcentaje": True})

    for m in crudas:
        m["linea_id"] = fuente.get("linea_id", "")

    # Escala de porcentajes: si todos los valores de un indicador en % están entre 0 y 1, se multiplican por 100.
    if fuente.get("escala_porcentaje", "auto") in ("auto", "fraccion"):
        for ind in {m["indicador_id"] for m in crudas}:
            if catalogo.indicadores[ind].get("unidad") != "%":
                continue
            grupo = [m for m in crudas if m["indicador_id"] == ind and not m["_texto_porcentaje"]]
            if grupo and (fuente.get("escala_porcentaje") == "fraccion" or all(-1 <= m["valor"] <= 1 for m in grupo)):
                for m in grupo:
                    m["valor"] *= 100
                    if m["meta_archivo"] is not None and m["meta_archivo"] <= 1:
                        m["meta_archivo"] *= 100

    validas = []
    for m in crudas:
        lo, hi = catalogo.indicadores[m["indicador_id"]].get("rango", [None, None])
        if m["indicador_id"] != fuente.get("conteo") and (
                (lo is not None and m["valor"] < lo) or (hi is not None and m["valor"] > hi)):
            err.add(m["fila"], m["indicador_id"], "FUERA_DE_RANGO", m["valor"], f"Rango permitido {lo} a {hi}")
            continue
        m["valor"] = round(m["valor"], 4)
        m.pop("_texto_porcentaje")
        validas.append(m)

    # Duplicados dentro del mismo archivo: se conserva la primera aparición.
    vistos, unicas = {}, []
    for m in validas:
        k = tuple(m[c] for c in CLAVE)
        if k in vistos:
            err.add(m["fila"], "clave", "DUPLICADO_EN_ARCHIVO", " | ".join(map(str, k)),
                    f"Repite la fila {vistos[k]}; se conserva la primera")
            continue
        vistos[k] = m["fila"]
        unicas.append(m)
    return unicas, filas_leidas


# ---------------------------------------------------------------- histórico

def integrar(historico: pd.DataFrame, mediciones, meta_carga, err: Errores, periodo_abierto, permitir_correcciones):
    """Integra mediciones al histórico sin borrar nada. Devuelve (historico, contadores).
    permitir_correcciones=True también se usa para fuentes con "politica_cambios": "versionar"
    (bases acumuladas que se re-descargan y pueden ajustar meses anteriores)."""
    cont = {"nuevas": 0, "versionadas": 0, "duplicadas": 0, "conflictos": 0}
    if historico.empty:
        indice = {}
    else:
        vig = historico[historico["vigente"] == "1"]
        indice = {tuple(r[c] for c in CLAVE): (i, r) for i, r in zip(vig.index, vig.to_dict("records"))}
    nuevas_filas = []
    for m in mediciones:
        k = tuple(str(m[c]) for c in CLAVE)
        fila = {c: "" for c in COLS_HISTORICO}
        fila.update({c: "" if m.get(c) is None else str(m[c]) for c in COLS_HISTORICO if c in m})
        fila.update(meta_carga)
        if k not in indice:
            fila.update(version="1", vigente="1")
            nuevas_filas.append(fila)
            cont["nuevas"] += 1
            continue
        i, previo = indice[k]
        if previo["fuente_id"] != meta_carga["fuente_id"]:
            err.add(m["fila"], "clave", "CONFLICTO_FUENTES", " | ".join(k),
                    f"Esta medición ya la informa la fuente '{previo['fuente_id']}'. "
                    "Use nombres de cuenta distintos (homologación) o desactive una de las fuentes.")
            cont["conflictos"] += 1
            continue
        if abs(float(previo["valor"]) - float(m["valor"])) < 1e-9 and previo["muestras"] == fila["muestras"]:
            cont["duplicadas"] += 1
            continue
        if m["periodo"] < periodo_abierto and not permitir_correcciones:
            err.add(m["fila"], "valor", "CONFLICTO_HISTORICO", m["valor"],
                    f"Periodo cerrado {m['periodo']}: el histórico tiene {previo['valor']} (carga {previo['carga_id']}). "
                    "Usar --permitir-correcciones si es una corrección legítima.")
            cont["conflictos"] += 1
            continue
        historico.at[i, "vigente"] = "0"
        fila.update(version=str(int(previo["version"] or 1) + 1), vigente="1")
        nuevas_filas.append(fila)
        cont["versionadas"] += 1
    if nuevas_filas:
        historico = pd.concat([historico, pd.DataFrame(nuevas_filas, columns=COLS_HISTORICO)], ignore_index=True)
    return historico, cont


# ---------------------------------------------------------------- publicación

def publicar(catalogo: Catalogo, fuentes):
    """Genera data/consolidado.json, data/cargas/resumen.json y data/chatbot/contexto.json."""
    hist = leer_csv(HISTORICO, COLS_HISTORICO)
    vig = hist[hist["vigente"] == "1"].copy()
    fuentes_demo = {f["id"] for f in fuentes if f.get("demo")}
    registros = []
    for r in vig.to_dict("records"):
        valor = float(r["valor"])
        meta_arch = a_numero(r["meta_archivo"])
        meta, umbral = catalogo.meta(r["empresa_id"], r["pais_id"], r["indicador_id"])
        if meta_arch is not None:
            # El umbral conserva la misma distancia a la meta que en el catálogo.
            umbral = None if umbral is None or meta is None else meta_arch + (umbral - meta)
            meta = meta_arch
        registros.append({
            "e": r["empresa_id"], "p": r["pais_id"], "l": r["linea_id"], "c": r["cuenta"], "i": r["indicador_id"],
            "per": r["periodo"], "f": r["fecha_medicion"], "v": valor,
            "m": meta, "u": umbral, "n": int(r["muestras"]) if r["muestras"] else None,
            "s": catalogo.estado(valor, meta, umbral, r["indicador_id"]),
            "src": r["fuente_id"], "ver": int(r["version"] or 1), "t": r["cuenta"] == TOTAL,
            "demo": r["fuente_id"] in fuentes_demo,
        })
    registros.sort(key=lambda x: (x["e"], x["p"], x["l"], x["c"], x["i"], x["per"]))
    ahora = datetime.now().isoformat(timespec="seconds")
    escribir_json(DATA / "consolidado.json", {
        "generado": ahora,
        "esquema": {"e": "empresa_id", "p": "pais_id", "l": "linea_id (servicio/dashboard)", "c": "cuenta", "i": "indicador_id", "per": "periodo YYYY-MM",
                    "f": "fecha_medicion", "v": "valor", "m": "meta", "u": "umbral_critico", "n": "muestras",
                    "s": "estado", "src": "fuente_id", "ver": "version", "t": "total del servicio", "demo": "dato ficticio"},
        "metas_son_ejemplo": catalogo.metas_son_ejemplo,
        "hay_datos_demo": any(r["demo"] for r in registros),
        "registros": registros,
    }, compacto=True)

    reg = leer_csv(REGISTRO, COLS_REGISTRO)
    ultimas = reg.tail(100).iloc[::-1].to_dict("records")
    errores_recientes = []
    for r in ultimas[:20]:
        ruta = DIR_ERRORES / f"{r['carga_id']}_errores.csv"
        if ruta.exists():
            errores_recientes += leer_csv(ruta, COLS_ERRORES).head(200).to_dict("records")
    escribir_json(DATA / "cargas" / "resumen.json", {
        "generado": ahora, "cargas": ultimas, "errores": errores_recientes[:1000],
        "total_historico": len(hist), "total_vigentes": len(vig),
    })
    publicar_chatbot(registros, catalogo, ahora)
    from perfiles import cifrar_perfiles      # paquetes cifrados por perfil (lo único que se publica)
    cifrar_perfiles()
    return len(registros)


def publicar_chatbot(registros, catalogo: Catalogo, ahora):
    """Contexto autorizado y resumido para un futuro chatbot (sin datos personales)."""
    df = pd.DataFrame(registros)
    resumen = []
    if not df.empty:
        ultimo = df["per"].max()
        for (e, p, i), g in df.groupby(["e", "p", "i"]):
            act = g[g["per"] == g["per"].max()]
            resumen.append({
                "empresa": e, "pais": p, "indicador": catalogo.indicadores[i]["nombre"],
                "periodo": g["per"].max(), "promedio": round(act["v"].mean(), 2),
                "cuentas": int(act["c"].nunique()),
                "criticas": sorted(act.loc[act["s"] == "CRITICO", "c"].unique().tolist()),
                "alertas": sorted(act.loc[act["s"] == "ALERTA", "c"].unique().tolist()),
            })
    escribir_json(DATA / "chatbot" / "contexto.json", {
        "generado": ahora,
        "descripcion": "Resumen autorizado de CENTRAL para responder preguntas. Contiene solo indicadores agregados por cuenta; no incluye datos personales.",
        "ultimo_periodo": None if df.empty else ultimo,
        "indicadores": [{k: v for k, v in i.items() if k != "alias"} for i in catalogo.indicadores.values()],
        "resumen_por_indicador": resumen,
        "fuente_detalle": "data/consolidado.json",
    })


# ---------------------------------------------------------------- orquestación

def procesar(args):
    catalogo = Catalogo()
    fuentes = leer_json(CONFIG / "fuentes.json")["fuentes"]
    problemas = validar_config(catalogo, fuentes)
    if problemas:
        print("Configuración con problemas:\n  - " + "\n  - ".join(problemas))
        return 2
    seleccion = [f for f in fuentes if f.get("activo") and (not args.fuente or f["id"] in args.fuente)]
    if args.fuente and not seleccion:
        print(f"No hay fuentes activas con id {args.fuente}")
        return 2

    historico = leer_csv(HISTORICO, COLS_HISTORICO)
    registro = leer_csv(REGISTRO, COLS_REGISTRO)
    procesados = set(registro.loc[registro["estado"].isin(["OK", "OK_CON_ERRORES"]) & (registro["simulacion"] != "1"),
                                  "archivo_hash"])
    periodo_abierto = args.periodo_abierto or datetime.now().strftime("%Y-%m")
    nuevas_cargas, total_err = [], 0

    for fuente in seleccion:
        carpeta = ruta_fuente(fuente)
        if fuente.get("complementos") and not archivos_complemento(fuente):
            # Sin las descargas diarias el resultado sería incompleto y pisaría el del PC que sí las tiene.
            print(f"[{fuente['id']}] se omite: este PC no tiene las descargas complementarias "
                  f"({', '.join(c['patron'] for c in fuente['complementos'])}); se conserva lo último publicado")
            continue
        desde_drive = sincronizar_drive(fuente)
        if desde_drive:
            archivos = [desde_drive]
        else:
            archivos = sorted((p for p in carpeta.glob(fuente.get("patron", "*.xlsx")) if not p.name.startswith("~$")),
                              key=lambda p: (p.stat().st_mtime, p.name))
            if fuente.get("seleccion") == "mas_reciente":
                archivos = archivos[-1:]
        if not archivos:
            print(f"[{fuente['id']}] sin archivos en {relativa(carpeta)}")
        for ruta in archivos:
            ahora = datetime.now()
            carga_id = f"{ahora:%Y%m%d-%H%M%S}-{fuente['id']}-{len(nuevas_cargas) + 1:03d}"
            h = hash_archivo(ruta)
            if fuente.get("complementos"):     # un complemento nuevo también obliga a reprocesar
                h = hashlib.sha256((h + "".join(hash_archivo(p) for p, _ in archivos_complemento(fuente))).encode()).hexdigest()
            rel = relativa(ruta)
            base = {c: "0" for c in COLS_REGISTRO}
            base.update(carga_id=carga_id, fecha_carga=ahora.isoformat(timespec="seconds"), fuente_id=fuente["id"],
                        archivo=rel, archivo_hash=h, simulacion="1" if args.simular else "0")
            if h in procesados and not args.reprocesar:
                print(f"[{fuente['id']}] {ruta.name}: ya procesado (mismo hash), se omite")
                base["estado"] = "OMITIDO_YA_PROCESADO"
                nuevas_cargas.append(base)
                continue
            err = Errores(carga_id, fuente["id"], rel)
            mediciones, leidas = leer_archivo(ruta, fuente, catalogo, err)
            meta_carga = {"fuente_id": fuente["id"], "archivo": rel, "archivo_hash": h,
                          "carga_id": carga_id, "fecha_carga": base["fecha_carga"]}
            historico, cont = integrar(historico, mediciones, meta_carga, err, periodo_abierto,
                                       args.permitir_correcciones or fuente.get("politica_cambios") == "versionar")
            err.cerrar()
            filas_con_error = {e["fila_excel"] for e in err.filas if e["tipo_error"] != "DUPLICADO_EN_ARCHIVO"}
            estado = ("ERROR" if not mediciones and err.filas else "OK_CON_ERRORES" if err.filas else "OK")
            base.update(estado=estado, filas_leidas=str(leidas), mediciones_validas=str(len(mediciones)),
                        duplicadas=str(cont["duplicadas"] + sum(e["tipo_error"] == "DUPLICADO_EN_ARCHIVO" for e in err.filas)),
                        rechazadas=str(len(filas_con_error)), errores=str(err.total),
                        **{k: str(v) for k, v in cont.items() if k != "duplicadas"})
            nuevas_cargas.append(base)
            procesados.add(h)
            total_err += err.total
            if err.filas and not args.simular:
                DIR_ERRORES.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(err.filas, columns=COLS_ERRORES).to_csv(
                    DIR_ERRORES / f"{carga_id}_errores.csv", index=False, encoding="utf-8")
            print(f"[{fuente['id']}] {ruta.name}: {estado} · leídas {leidas} · válidas {len(mediciones)} · "
                  f"nuevas {cont['nuevas']} · versionadas {cont['versionadas']} · duplicadas {cont['duplicadas']} · "
                  f"conflictos {cont['conflictos']} · errores {err.total}")
            if args.simular and err.filas:
                print(pd.DataFrame(err.filas)[["fila_excel", "campo", "tipo_error", "valor", "detalle"]]
                      .head(30).to_string(index=False))

    if args.simular:
        print("\nSimulación: no se escribió ningún archivo.")
        return 0
    HISTORICO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    historico.sort_values(CLAVE + ["version"], key=lambda s: s.str.zfill(6) if s.name == "version" else s) \
        .to_csv(HISTORICO, index=False, encoding="utf-8")
    if nuevas_cargas:
        pd.concat([registro, pd.DataFrame(nuevas_cargas, columns=COLS_REGISTRO)], ignore_index=True) \
            .to_csv(REGISTRO, index=False, encoding="utf-8")
    n = publicar(catalogo, fuentes)
    print(f"\nPublicado: {n} mediciones vigentes · {total_err} errores registrados en data/cargas/errores/")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="ETL de CENTRAL")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("procesar", help="Procesa los Excel de las fuentes activas")
    p.add_argument("--fuente", action="append", help="Procesar solo esta fuente (repetible)")
    p.add_argument("--simular", action="store_true", help="Valida y muestra errores sin escribir")
    p.add_argument("--reprocesar", action="store_true",
                   help="Vuelve a leer archivos ya procesados (tras cambiar la configuración de una fuente)")
    p.add_argument("--permitir-correcciones", action="store_true",
                   help="Permite versionar mediciones de periodos cerrados")
    p.add_argument("--periodo-abierto", help="Primer periodo (YYYY-MM) que se puede actualizar sin la opción anterior")
    sub.add_parser("publicar", help="Regenera los JSON del portal desde el histórico")
    sub.add_parser("validar-config", help="Revisa config/*.json")
    args = ap.parse_args(argv)

    if args.cmd == "procesar":
        return procesar(args)
    catalogo = Catalogo()
    fuentes = leer_json(CONFIG / "fuentes.json")["fuentes"]
    if args.cmd == "publicar":
        print(f"Publicado: {publicar(catalogo, fuentes)} mediciones vigentes")
        return 0
    problemas = validar_config(catalogo, fuentes)
    print("Configuración correcta" if not problemas else "Problemas:\n  - " + "\n  - ".join(problemas))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
