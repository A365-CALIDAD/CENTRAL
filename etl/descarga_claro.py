"""Avance equipo: descarga las respuestas de Qualtrics de Claro Ecuador (Inbound y Outbound) con el proceso que ya
existe en CLARO/ECUADOR/CLARO_IN y CLARO_OUT (descarga_qualtrics.py, con su .env y su perfil de Chrome).

Solo hace la parte de descarga: inicia sesión, exporta la encuesta filtrada por A365, cierra la sesión y deja el
archivo filtrado ("Monitoreo Inbound A365 - DD.MM.xlsx") en la carpeta filtrado, de donde lo toma CENTRAL. No
actualiza el BI de Claro ni sube a Drive o GitHub (eso lo sigue haciendo su propio proceso). Va dentro de
AvanceEquipo.exe: no necesita Python en el PC.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path

import central_etl

CLARO = central_etl.RAIZ.parent / "CLARO" / "ECUADOR"
CUENTAS = [("Claro Ecuador · Inbound", CLARO / "CLARO_IN"), ("Claro Ecuador · Outbound", CLARO / "CLARO_OUT")]


def cargar_proceso(carpeta: Path, nombre: str):
    """Carga descarga_qualtrics.py de esa carpeta. Su .env y sus carpetas se resuelven desde la ubicación del
    script; dentro del .exe se oculta un momento sys.frozen para que no las busque junto al .exe."""
    archivo = carpeta / "descarga_qualtrics.py"
    if not archivo.exists():
        raise FileNotFoundError(f"No está el proceso de Qualtrics: {archivo}")
    spec = importlib.util.spec_from_file_location(nombre, archivo)
    modulo = importlib.util.module_from_spec(spec)
    congelado = getattr(sys, "frozen", None)
    if congelado is not None:
        del sys.frozen
    # Cada .env se carga en las variables de entorno (sin pisar las que ya están): si no se limpian, Outbound
    # heredaría las carpetas y el nombre de archivo de Inbound. El script lee su configuración al cargarse.
    entorno = dict(os.environ)
    try:
        spec.loader.exec_module(modulo)
    finally:
        os.environ.clear()
        os.environ.update(entorno)
        if congelado is not None:
            sys.frozen = congelado
    return modulo


def descargar_cuenta(titulo: str, carpeta: Path) -> Path | None:
    print(f"\n→ {titulo}")
    Q = cargar_proceso(carpeta, f"qualtrics_{carpeta.name.lower()}")
    if not (Q.USER and Q.PASS):
        print(f"   Falta QUALTRICS_USER / QUALTRICS_PASS en {carpeta / '.env'}; se omite.")
        return None
    if not Q.bloquear_ejecucion():
        print("   Su proceso de Qualtrics ya está corriendo en este momento; se usa el último archivo filtrado.")
        return None
    Q.PERFIL_QUALTRICS.mkdir(parents=True, exist_ok=True)
    driver = Q.crear_driver(perfil=Q.PERFIL_QUALTRICS)
    try:
        Q.login(driver)
        encuesta = Q.SURVEY_ID or Q.buscar_encuesta(driver)
        if not encuesta:
            print("   No se encontró la encuesta en Qualtrics.")
            return None
        descargado = Q.exportar(driver, encuesta)
    except Exception:
        captura = Q.LOG_DIR / "error_avance_equipo.png"
        try:
            driver.save_screenshot(str(captura))
        except Exception:
            pass
        raise
    finally:
        Q.cerrar_sesion(driver)       # si no, Qualtrics acumula sesiones y termina rechazando el login
        driver.quit()
        try:
            Q._CANDADO.close()        # libera el candado para su propio proceso
        except Exception:
            pass
    filtrado = Q.filtrar(descargado)
    print(f"   ✓ {filtrado.name} (en {filtrado.parent})")
    return filtrado


def main() -> int:
    errores = 0
    for titulo, carpeta in CUENTAS:
        try:
            descargar_cuenta(titulo, carpeta)
        except Exception as e:
            errores += 1
            print(f"   ✗ No se pudo descargar de Qualtrics: {e}")
            traceback.print_exc()
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
