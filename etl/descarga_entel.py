"""Avance equipo: descarga de una vez los Reporte Pauta de HOY de todas las cuentas de Entel (va dentro del .exe).

Usa el mismo proceso de las adherencias (ENTEL_BI_IN/Adherencias/Adherencias_Entel.py): el mismo perfil de Chrome con
la sesión iniciada y el mismo inicio de sesión. En el portal (sergpp.cl/calidad/reporte) filtra solo el día de hoy,
presiona "Filtrar pautas" y descarga una tras otra las pautas de cada cuenta. Cada archivo queda en la carpeta
Adherencias/Descargas de su cuenta, de donde lo toma CENTRAL (módulo Avance equipo), que reparte las evaluaciones en
las franjas horarias según su hora de envío.

En el .exe no hace falta Python: el proceso de adherencias se carga desde su carpeta (ENTEL/ENTEL_BI_IN/Adherencias,
con su .env y su perfil de Chrome) y usa Selenium incluido en el .exe. Lo ejecuta AvanceEquipo.exe antes de
cada extracción de la hora.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import central_etl

ENTEL = central_etl.RAIZ.parent / "ENTEL"                  # C:\A365\ENTEL, al lado de CENTRAL
BASE = ENTEL / "ENTEL_BI_IN" / "Adherencias" / "Adherencias_Entel.py"     # proceso de adherencias (sesión y portal)

# Pauta del portal → carpeta donde la busca CENTRAL
PAUTAS = [
    ("Pauta VOZ - Móvil y Hogar 5.0", ENTEL / "ENTEL_BI_IN" / "Adherencias" / "Descargas"),
    ("Pauta Voz - Fibra Técnico", ENTEL / "ENTEL_BI_MT" / "Adherencias" / "Descargas"),
    ("Pauta Retenciones - Centros", ENTEL / "ENTEL_BI_CZC" / "Adherencias" / "Descargas"),
    ("Pauta Outbound - Centros 2.0", ENTEL / "ENTEL_BI_OUT" / "Adherencias" / "Descargas"),
    ("Pauta Ecommerce - Centros 3.0", ENTEL / "ENTEL_BI_EC" / "Adherencias" / "Descargas"),
]


def cargar_proceso():
    if not BASE.exists():
        raise FileNotFoundError(f"No está el proceso de adherencias de Entel: {BASE}")
    # Dentro del .exe el proceso toma su carpeta (.env, perfil de Chrome, Descargas) de A365_CARPETA_PASO
    os.environ["A365_CARPETA_PASO"] = str(BASE.parent)
    spec = importlib.util.spec_from_file_location("adherencias_entel", BASE)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def seleccionar_hoy(A, driver):
    """Como seleccionar_dia_anterior del proceso de adherencias, pero con la fecha de hoy en Desde y Hasta."""
    hoy = date.today().strftime("%d/%m/%Y")
    A.mostrar_info(f"Seleccionando el día de hoy: {hoy}")
    A.esperar_fin_carga(driver, 60)
    selector = A.WebDriverWait(driver, 30).until(A.EC.element_to_be_clickable((A.By.ID, "selector-fecha")))
    try:
        selector.click()
    except Exception:
        A.esperar_fin_carga(driver, 30)
        driver.execute_script("arguments[0].click();", selector)

    def campos_fecha(navegador):
        campos = []
        for elemento in navegador.find_elements(A.By.CSS_SELECTOR, "input"):
            try:
                if elemento.is_displayed() and re.fullmatch(r"\d{2}/\d{2}/\d{4}", elemento.get_attribute("value") or ""):
                    campos.append(elemento)
            except A.StaleElementReferenceException:
                continue
        return campos if len(campos) >= 2 else False

    for campo in A.WebDriverWait(driver, 30).until(campos_fecha)[:2]:
        try:
            campo.click()
            campo.send_keys(A.Keys.CONTROL, "a")
            campo.send_keys(hoy)
        except A.StaleElementReferenceException:
            continue
    boton = A.WebDriverWait(driver, 15).until(
        A.EC.element_to_be_clickable((A.By.XPATH, "//button[normalize-space()='Seleccionar']")))
    try:
        boton.click()
    except Exception:
        driver.execute_script("arguments[0].click();", boton)
    time.sleep(1)
    A.hacer_click_filtrar_pautas(driver)
    A.esperar_fin_carga(driver, 60)
    A.mostrar_exito(f"Pautas filtradas para hoy ({hoy}).")


def descargar_pauta(A, driver, nombre: str) -> Path | None:
    """Descarga la pauta 'nombre' de la lista filtrada; None si hoy no tiene evaluaciones (no aparece en la lista)."""
    A.esperar_fin_carga(driver, 60)
    try:
        boton = A.WebDriverWait(driver, 15).until(A.EC.presence_of_element_located(
            (A.By.XPATH, f"//button[@data-nombre_evaluacion='{nombre}']")))
    except A.TimeoutException:
        try:
            fila = driver.find_element(A.By.XPATH, f"//tr[td[normalize-space(.)='{nombre}']]")
            boton = fila.find_element(A.By.XPATH, ".//button[contains(@class, 'btn-download-excel')] | .//button")
        except Exception:
            A.mostrar_advertencia(f"'{nombre}' no aparece hoy (sin evaluaciones todavía).")
            return None
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boton)
    time.sleep(0.5)
    antes = {p: p.stat().st_mtime for p in A.CARPETA_DESCARGAS.glob("*.xlsx")}
    try:
        boton.click()
    except Exception:
        driver.execute_script("arguments[0].click();", boton)
    try:          # modal "Seleccione las categorías a descargar"
        confirmar = A.WebDriverWait(driver, 15).until(A.EC.element_to_be_clickable(
            (A.By.XPATH, "//div[contains(@class, 'modal')]//button[normalize-space()='Descargar']"
                         " | //button[normalize-space()='Descargar']")))
        try:
            confirmar.click()
        except Exception:
            driver.execute_script("arguments[0].click();", confirmar)
    except A.TimeoutException:
        pass
    inicio = time.perf_counter()
    while time.perf_counter() - inicio < A.TIEMPO_MAXIMO_DESCARGA:
        temporales = list(A.CARPETA_DESCARGAS.glob("*.crdownload")) + list(A.CARPETA_DESCARGAS.glob("*.tmp"))
        nuevos = [p for p in A.CARPETA_DESCARGAS.glob("*.xlsx") if p not in antes or p.stat().st_mtime > antes[p]]
        if nuevos and not temporales:
            archivo = max(nuevos, key=lambda p: p.stat().st_mtime)
            A.mostrar_exito(f"Descargado: {archivo.name}", time.perf_counter() - inicio)
            # cerrar el modal si quedó abierto antes de la siguiente pauta
            try:
                driver.find_element(A.By.TAG_NAME, "body").send_keys(A.Keys.ESCAPE)
            except Exception:
                pass
            return archivo
        time.sleep(1)
    raise A.TimeoutException(f"La descarga de '{nombre}' superó {A.TIEMPO_MAXIMO_DESCARGA} segundos.")


def main() -> int:
    A = cargar_proceso()
    print("=" * 70)
    print(f"AVANCE EQUIPO · Reporte Pauta de hoy ({date.today():%d/%m/%Y}) de todas las cuentas de Entel")
    print("=" * 70)
    navegador, errores = None, 0
    try:
        A.validar_configuracion()
        navegador = A.abrir_portal()
        A.iniciar_sesion_portal(navegador)
        navegador.get(A.URL_PORTAL)
        A.WebDriverWait(navegador, 60, ignored_exceptions=(A.WebDriverException,)).until(
            lambda d: "/calidad/reporte" in (d.current_url or ""))
        seleccionar_hoy(A, navegador)
        for nombre, carpeta in PAUTAS:
            try:
                archivo = descargar_pauta(A, navegador, nombre)
            except Exception as e:
                errores += 1
                A.mostrar_error(f"{nombre}: {e}")
                continue
            if archivo is None:
                continue
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / archivo.name
            if archivo.resolve() != destino.resolve():
                shutil.move(str(archivo), str(destino))
            A.mostrar_info(f"→ {destino.relative_to(ENTEL)}")
    except Exception as e:
        A.mostrar_error(f"No se pudo completar la descarga: {e}")
        return 1
    finally:
        if navegador is not None:
            try:
                navegador.quit()
            except Exception:
                pass
    print("\nListo." if not errores else f"\nTerminó con {errores} pauta(s) con error.")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
