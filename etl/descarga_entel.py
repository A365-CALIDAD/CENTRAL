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
import unicodedata
import sys
import time
from datetime import date
from pathlib import Path

import central_etl

ENTEL = central_etl.RAIZ.parent / "ENTEL"                  # C:\A365\ENTEL, al lado de CENTRAL
BASE = ENTEL / "ENTEL_BI_IN" / "Adherencias" / "Adherencias_Entel.py"     # proceso de adherencias (sesión y portal)

# Pauta del portal → carpeta donde la busca CENTRAL
# (pauta del portal, carpeta donde la busca CENTRAL, switch "Filtrar por" en Evaluador)
# Mesa Técnica y C2C se filtran por Evaluador, como en sus procesos de adherencias; el resto por Evaluado.
PAUTAS = [
    ("Pauta VOZ - Móvil y Hogar 5.0", ENTEL / "ENTEL_BI_IN" / "Adherencias" / "Descargas", False),
    ("Pauta Outbound - Centros 2.0", ENTEL / "ENTEL_BI_OUT" / "Adherencias" / "Descargas", False),
    ("Pauta Ecommerce - Centros 3.0", ENTEL / "ENTEL_BI_EC" / "Adherencias" / "Descargas", False),
    ("Pauta Voz - Fibra Técnico", ENTEL / "ENTEL_BI_MT" / "Adherencias" / "Descargas", True),
    ("Pauta Retenciones - Centros", ENTEL / "ENTEL_BI_CZC" / "Adherencias" / "Descargas", True),
]


def cargar_proceso():
    if not BASE.exists():
        raise FileNotFoundError(f"No está el proceso de adherencias de Entel: {BASE}")
    # Dentro del .exe el proceso toma su carpeta (.env, perfil de Chrome, Descargas) de A365_CARPETA_PASO
    os.environ["A365_CARPETA_PASO"] = str(BASE.parent)
    spec = importlib.util.spec_from_file_location("adherencias_entel", BASE)
    modulo = importlib.util.module_from_spec(spec)
    # Versiones anteriores del proceso no leen A365_CARPETA_PASO y, dentro de un .exe, buscan su .env junto al
    # ejecutable (C:\A365\CENTRAL). Se oculta sys.frozen mientras se carga: así usan la carpeta del script.
    congelado = getattr(sys, "frozen", None)
    if congelado is not None:
        del sys.frozen
    try:
        spec.loader.exec_module(modulo)
    finally:
        if congelado is not None:
            sys.frozen = congelado
    return modulo


def seleccionar_hoy(A, driver):
    """Como seleccionar_dia_anterior del proceso de adherencias, pero con la fecha de hoy en Desde y Hasta."""
    hoy = date.today().strftime("%d/%m/%Y")
    A.mostrar_info(f"Seleccionando el día de hoy: {hoy}")
    A.esperar_fin_carga(driver, 60)
    selector = A.WebDriverWait(driver, 30).until(A.EC.element_to_be_clickable((A.By.ID, "selector-fecha")))
    # Si el portal ya tiene hoy-hoy (quedó de la hora anterior, el Chrome sigue abierto), no hay nada que cambiar
    actual = (selector.get_attribute("value") or selector.text or "")
    if actual.count(hoy) >= 2:
        A.mostrar_exito(f"La fecha ya está en hoy ({actual.strip()}).")
        return

    def abrir_calendario():
        try:
            selector.click()
        except Exception:
            A.esperar_fin_carga(driver, 30)
            driver.execute_script("arguments[0].click();", selector)

    abrir_calendario()

    def campos_fecha(navegador):
        campos = []
        for elemento in navegador.find_elements(A.By.CSS_SELECTOR, "input"):
            try:
                if elemento.is_displayed() and re.fullmatch(r"\d{2}/\d{2}/\d{4}", elemento.get_attribute("value") or ""):
                    campos.append(elemento)
            except A.StaleElementReferenceException:
                continue
        return campos if len(campos) >= 2 else False

    try:
        campos = A.WebDriverWait(driver, 15).until(campos_fecha)
    except A.TimeoutException:          # el clic pudo cerrar un calendario que ya estaba abierto: otra vez
        abrir_calendario()
        campos = A.WebDriverWait(driver, 30).until(campos_fecha)
    for campo in campos[:2]:
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


def poner_switch(A, driver, evaluador: bool):
    """Switch "Filtrar por": Evaluado (apagado) o Evaluador (encendido). Igual que en el proceso de Mesa Técnica:
    el <input> está oculto y se hace clic en su <label>."""
    A.esperar_fin_carga(driver, 60)
    try:
        switch = A.WebDriverWait(driver, 20).until(A.EC.presence_of_element_located((A.By.ID, "filtro-switch-filtro")))
    except A.TimeoutException:
        switch = driver.find_element(
            A.By.XPATH, "//*[normalize-space(text())='Filtrar por']/following::input[@type='checkbox'][1]")
    if switch.is_selected() == evaluador:
        return
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", switch)
    try:
        driver.find_element(A.By.ID, "label-switch-filtro").click()
    except Exception:
        driver.execute_script("arguments[0].click();", switch)
    try:
        A.WebDriverWait(driver, 10).until(lambda d: switch.is_selected() == evaluador)
    except A.TimeoutException:
        driver.execute_script("arguments[0].click();", switch)
    A.mostrar_exito(f"Filtrar por: {'Evaluador' if evaluador else 'Evaluado'}.")


def filtrar(A, driver, evaluador: bool) -> dict:
    """Switch en su posición + "Filtrar pautas". Devuelve las pautas que muestra el portal (y las anota en el log)."""
    poner_switch(A, driver, evaluador)
    A.hacer_click_filtrar_pautas(driver)
    A.esperar_fin_carga(driver, 60)
    lista = pautas_en_pantalla(A, driver)
    A.mostrar_info(f"Pautas de hoy filtrando por {'Evaluador' if evaluador else 'Evaluado'} ({len(lista)}): "
                   f"{' | '.join(sorted(lista)) or 'ninguna'}")
    return lista


def _norm(texto) -> str:
    texto = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(texto.split())


def pautas_en_pantalla(A, driver, espera=60) -> dict:
    """{nombre normalizado: botón de descarga} de la lista filtrada. Espera a que la lista termine de cargar."""
    fin = time.time() + espera
    botones = []
    while time.time() < fin:
        A.esperar_fin_carga(driver, 30)
        botones = driver.find_elements(A.By.CSS_SELECTOR, "button.btn-download-excel[data-nombre_evaluacion]")
        if botones:
            break
        time.sleep(2)
    out = {}
    for b in botones:
        try:
            out.setdefault(_norm(b.get_attribute("data-nombre_evaluacion")), b)
        except A.StaleElementReferenceException:
            continue
    return out


def confirmar_descarga(A, driver, espera=20) -> bool:
    """Modal "Seleccione las categorías a descargar": clic en su botón Descargar VISIBLE (hay otros ocultos)."""
    fin = time.time() + espera
    while time.time() < fin:
        for b in driver.find_elements(A.By.XPATH, "//button[normalize-space()='Descargar'] | //a[normalize-space()='Descargar']"):
            try:
                if b.is_displayed() and b.is_enabled():
                    try:
                        b.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", b)
                    return True
            except A.StaleElementReferenceException:
                continue
        time.sleep(0.5)
    return False


# Pautas que se piden solo con la primera categoría ("Identificación del caso": trae ID Pauta, fecha y hora de envío,
# Realizador y TMO del caso, lo que usa el avance). Con todas sus categorías el portal no logra generar el reporte de
# Inbound (error del servidor desde la tarde del 21/10/2026); así sale en segundos.
LIVIANAS = {"Pauta VOZ - Móvil y Hogar 5.0"}


def solo_primera_categoria(A, driver) -> bool:
    """En la ventana "Seleccione las categorías a descargar" deja marcada solo la primera."""
    fin = time.time() + 15
    while time.time() < fin:
        valores = driver.execute_script(
            "return [...document.querySelectorAll('#select-categorias option')].map(o => o.value)")
        if valores:
            driver.execute_script("$('#select-categorias').selectpicker('val', [arguments[0]]);", valores[0])
            return True
        time.sleep(0.5)
    return False


def descargar_pauta(A, driver, nombre: str, liviana=None) -> Path | None:
    """Descarga la pauta 'nombre' de la lista filtrada; None si hoy no tiene evaluaciones (no aparece en la lista).
    liviana=True pide solo la primera categoría (por defecto, las pautas de LIVIANAS)."""
    liviana = nombre in LIVIANAS if liviana is None else liviana
    clave = _norm(nombre)
    antes = {p: p.stat().st_mtime for p in A.CARPETA_DESCARGAS.glob("*.xlsx")}
    # La tabla se vuelve a dibujar después de filtrar: el botón se busca justo antes del clic (y de nuevo si quedó viejo)
    for intento in range(4):
        lista = pautas_en_pantalla(A, driver)
        boton = lista.get(clave) or next((b for n, b in lista.items() if clave in n or n in clave), None)
        if boton is None:
            A.mostrar_advertencia(f"'{nombre}' no aparece hoy (sin evaluaciones todavía).")
            return None
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boton)
            time.sleep(0.5)
            # Clic por JavaScript: el clic normal a veces cae en otro elemento encima (burbuja de chat, cabecera fija)
            # y no abre la ventana de categorías.
            driver.execute_script("arguments[0].click();", boton)
            break
        except A.StaleElementReferenceException:
            time.sleep(2)
    else:
        raise A.TimeoutException(f"La lista de pautas no dejó de recargarse para '{nombre}'.")
    if liviana and solo_primera_categoria(A, driver):
        A.mostrar_info("Solo la primera categoría (reporte liviano).")
    if not confirmar_descarga(A, driver):
        A.mostrar_info("No apareció la ventana de categorías; se espera la descarga directa.")
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


# Chrome propio del avance: queda abierto entre una hora y la siguiente, así la sesión de Microsoft sigue activa
# y no pide aprobar en el celular cada vez. Perfil aparte (copia del de adherencias la primera vez) y otro puerto,
# para no chocar con la automatización diaria de las adherencias.
PERFIL_AVANCE = central_etl.RAIZ / "etl" / "entrada" / "chrome_avance"
PUERTO_AVANCE = 9223
SIN_COPIAR = shutil.ignore_patterns("Cache", "Code Cache", "GPUCache", "DawnCache", "GrShaderCache", "ShaderCache",
                                    "Service Worker", "Crashpad", "*.log", "Singleton*", "lockfile")


def preparar_perfil(A):
    if (PERFIL_AVANCE / A.CHROME_PROFILE_DIR).exists():
        return
    if A.PERFIL_CHROME_RPA.exists():
        A.mostrar_info("Preparando el Chrome del avance (copia del perfil de adherencias, una sola vez)...")
        shutil.copytree(A.PERFIL_CHROME_RPA, PERFIL_AVANCE, ignore=SIN_COPIAR, dirs_exist_ok=True,
                        copy_function=_copiar_si_se_puede)
    (PERFIL_AVANCE / A.CHROME_PROFILE_DIR).mkdir(parents=True, exist_ok=True)


def _copiar_si_se_puede(origen, destino):
    try:
        return shutil.copy2(origen, destino)
    except OSError:          # archivos en uso: se omiten
        return destino


def conectar_chrome(A):
    """Se conecta al Chrome del avance si ya está abierto; si no, lo abre (queda abierto al terminar)."""
    preparar_perfil(A)
    A.PERFIL_CHROME_RPA = A.CHROME_USER_DATA_DIR = PERFIL_AVANCE
    A.CHROME_REMOTE_DEBUGGING_PORT = PUERTO_AVANCE
    if A.chrome_ya_esta_abierto():
        A.mostrar_exito("Chrome del avance ya abierto: se reutiliza su sesión.")
    else:
        A.lanzar_chrome_con_cdp()
    opciones = A.webdriver.ChromeOptions()
    opciones.add_experimental_option("debuggerAddress", f"127.0.0.1:{PUERTO_AVANCE}")
    driver = A.webdriver.Chrome(options=opciones)
    driver.switch_to.window(driver.window_handles[-1])
    driver.execute_cdp_cmd("Browser.setDownloadBehavior",
                           {"behavior": "allow", "downloadPath": str(A.CARPETA_DESCARGAS)})
    return driver


def abrir_reporte(A, driver):
    driver.get(A.URL_PORTAL)
    time.sleep(2)
    A.iniciar_sesion_portal(driver)          # si la sesión sigue activa, no hace nada
    if "/calidad/reporte" not in (driver.current_url or ""):
        driver.get(A.URL_PORTAL)
    A.WebDriverWait(driver, 60, ignored_exceptions=(A.WebDriverException,)).until(
        lambda d: "/calidad/reporte" in (d.current_url or ""))
    seleccionar_hoy(A, driver)


def bajar_y_mover(A, driver, nombre, carpeta, liviana=None) -> bool | None:
    archivo = descargar_pauta(A, driver, nombre, liviana)
    if archivo is None:
        return None
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / archivo.name
    if archivo.resolve() != destino.resolve():
        shutil.move(str(archivo), str(destino))
    A.mostrar_info(f"→ {destino.relative_to(ENTEL)}")
    return True


def rondas(A, driver, pautas, aviso, liviana=None) -> list:
    """Primero las pautas filtradas por Evaluado, luego las de Evaluador. Devuelve las que fallaron."""
    fallidas = []
    for evaluador in (False, True):
        grupo = [p for p in pautas if p[2] == evaluador]
        if not grupo:
            continue
        filtrar(A, driver, evaluador)
        for nombre, carpeta, ev in grupo:
            try:
                bajar_y_mover(A, driver, nombre, carpeta, liviana)
            except Exception as e:
                aviso(f"{nombre}: {str(e).splitlines()[0]}")
                fallidas.append((nombre, carpeta, ev))
    poner_switch(A, driver, False)           # se deja como estaba
    return fallidas


def main() -> int:
    A = cargar_proceso()
    print("=" * 70)
    print(f"AVANCE EQUIPO · Reporte Pauta de hoy ({date.today():%d/%m/%Y}) de todas las cuentas de Entel")
    print("=" * 70)
    navegador, fallidas = None, []
    try:
        A.validar_configuracion()
        navegador = conectar_chrome(A)
        abrir_reporte(A, navegador)
        fallidas = rondas(A, navegador, PAUTAS, aviso=A.mostrar_advertencia)
        if fallidas:        # segundo intento: página recargada y más tiempo (los reportes grandes tardan en generarse)
            A.mostrar_info(f"Reintentando {len(fallidas)} pauta(s) con más tiempo...")
            A.TIEMPO_MAXIMO_DESCARGA = max(A.TIEMPO_MAXIMO_DESCARGA, 360)
            abrir_reporte(A, navegador)
            fallidas = rondas(A, navegador, fallidas, aviso=A.mostrar_error, liviana=True)   # reintento liviano
    except Exception as e:
        A.mostrar_error(f"No se pudo completar la descarga: {e}")
        return 1
    finally:
        if navegador is not None:      # se suelta el control pero Chrome queda abierto con la sesión
            try:
                navegador.service.stop()
            except Exception:
                pass
    print("\nListo." if not fallidas else f"\nTerminó con {len(fallidas)} pauta(s) con error.")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
