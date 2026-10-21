"""AvanceEquipo.exe: programa aparte, solo para el módulo Avance equipo de CENTRAL (no tiene menú).

Cada vez que se abre (doble clic o la tarea de cada hora):
  1. trae lo último publicado (y los datos del otro PC si los hay);
  2. en este orden: Claro (Qualtrics) → Entel (Reporte Pauta de HOY de las cinco cuentas, con el proceso de las
     adherencias) → Banco de la Nación → Movistar (sus aplicaciones web);
  3. reparte cada evaluación en su franja horaria, cifra los paquetes y publica. No toca los KPI.
Registro en logs/avance_equipo.log. No necesita Python en el PC.

Opciones (desde una ventana de comandos):
  AvanceEquipo.exe --qualtrics   conecta Qualtrics (centro de datos y token; se hace una vez)
  AvanceEquipo.exe --verificar   revisa que el PC tenga todo, sin abrir Chrome
  AvanceEquipo.exe --sin-entel   no descarga de la plataforma de Entel (usa los archivos que haya)
"""
from __future__ import annotations

import shutil
import sys
import time
import traceback
from datetime import datetime

import avance
import central_etl
import descarga_claro
import descarga_entel
import menu            # solo sus funciones de sincronizar y publicar; su menú no se muestra
import perfiles
import qualtrics

LOG = central_etl.RAIZ / "logs" / "avance_equipo.log"


def descargar_entel():
    if not descarga_entel.BASE.exists():
        print(f"No está el proceso de adherencias de Entel en este PC ({descarga_entel.BASE}); se omite la descarga.")
        return
    menu.titulo("2/4 · Entel: Reporte Pauta de hoy (plataforma de adherencias)")
    try:
        if descarga_entel.main() != 0:
            print("La descarga de Entel terminó con problemas; se sigue con los archivos que haya.")
    except Exception:
        traceback.print_exc()
        print("La descarga de Entel falló; se sigue con los archivos que haya.")


def extraer(con_entel=True) -> bool:
    menu.titulo(f"Avance equipo · extracción de las {datetime.now():%H:%M}")
    if not menu.sincronizar():
        return False
    fuentes = central_etl.leer_json(central_etl.CONFIG / "fuentes.json")["fuentes"]
    menu.titulo("1/4 · Claro Ecuador: Qualtrics")
    if qualtrics.leer_config().get("token"):          # con token de API: directo por la API
        avance.descargar_qualtrics(fuentes)
    else:                                              # si no: el proceso de descarga que ya usa Claro
        try:
            if descarga_claro.main() != 0:
                print("La descarga de Qualtrics terminó con problemas; se sigue con los archivos que haya.")
        except Exception:
            traceback.print_exc()
            print("La descarga de Qualtrics falló; se sigue con los archivos que haya.")
        avance.QUALTRICS_LISTO = True
    if con_entel:
        descargar_entel()
    else:
        print("\n(Entel: descarga omitida con --sin-entel; se usan los archivos que haya)")
    menu.titulo("3/4 · Banco de la Nación")
    avance.precargar(fuentes, "bn_fraude_monitoreo")
    menu.titulo("4/4 · Movistar México")
    avance.precargar(fuentes, "mov_mx_out_monitoreo")
    menu.titulo("Ordenando las evaluaciones por franja horaria y publicando")
    avance.generar(fuentes)
    perfiles.cifrar_perfiles()
    return menu.publicar()


def verificar() -> int:
    menu.titulo("Verificación de este PC para Avance equipo")
    ok = True
    try:
        A = descarga_entel.cargar_proceso()
        print(f"  ✓ Proceso de adherencias de Entel: {descarga_entel.BASE}")
        print(f"    .env: {'sí' if A.ARCHIVO_ENV.exists() else 'NO'} · perfil de Chrome: {'sí' if A.PERFIL_CHROME_RPA.exists() else 'NO'}"
              f" · Chrome: {'sí' if A.CHROME_EXE_PATH.exists() else 'NO'}")
        ok &= A.ARCHIVO_ENV.exists() and A.CHROME_EXE_PATH.exists()
    except Exception as e:
        print(f"  ✗ Proceso de adherencias de Entel: {e}")
        ok = False
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager
        print(f"  ✓ Selenium incluido ({SeleniumManager()._get_binary().name})")
    except Exception as e:
        print(f"  ✗ Selenium: {e}")
        ok = False
    for titulo, carpeta in descarga_claro.CUENTAS:
        hay = (carpeta / "descarga_qualtrics.py").exists() and (carpeta / ".env").exists()
        print(f"  {'✓' if hay else '✗'} {titulo}: proceso de Qualtrics {'y .env encontrados' if hay else 'NO encontrado'} ({carpeta})")
        ok &= hay
    q = qualtrics.leer_config()
    print(f"  {'✓' if q.get('token') else '·'} Qualtrics: "
          f"{'conectado, ' + str(len(q.get('encuestas') or {})) + ' encuesta(s)' if q.get('token') else 'sin conectar (AvanceEquipo.exe --qualtrics)'}")
    print(f"  {'✓' if shutil.which('git') else '✗'} Git {'instalado' if shutil.which('git') else 'NO instalado'}")
    ok &= bool(shutil.which("git"))
    print("\nTodo listo." if ok else "\nHay puntos por resolver (✗).")
    return 0 if ok else 1


def elegir_al_abrir(segundos=5) -> str:
    """Al abrirlo con doble clic: Q = conectar Qualtrics, V = verificar el PC; sin tecla, la extracción de siempre
    (así la tarea programada nunca queda esperando)."""
    try:
        import msvcrt
    except ImportError:
        return ""
    print("AVANCE EQUIPO · Calidad A365")
    print(f"  Q = conectar Qualtrics · V = verificar este PC · (sin tecla: extracción en {segundos} s)")
    fin = time.time() + segundos
    while time.time() < fin:
        if msvcrt.kbhit():
            tecla = msvcrt.getwch().lower()
            return {"q": "--qualtrics", "v": "--verificar"}.get(tecla, "")
        time.sleep(0.1)
    return ""


def cerrar(interactivo):
    if interactivo:
        try:
            input("\nPresiona Enter para cerrar...")
        except EOFError:
            pass


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    interactivo = bool(sys.stdin and sys.stdin.isatty())
    if interactivo and not args:
        args = [elegir_al_abrir()]
    if "--qualtrics" in args:
        menu.titulo("Conectar Qualtrics (Claro Ecuador)")
        qualtrics.configurar()
        cerrar(interactivo)
        return 0
    if "--verificar" in args:
        codigo = verificar()
        cerrar(interactivo)
        return codigo
    # Con doble clic se puede pedir una vez el nombre y correo de Git; en la tarea programada no se pregunta nada.
    menu.INTERACTIVO = interactivo
    LOG.parent.mkdir(exist_ok=True)

    class Duplicar:                       # en pantalla y en el registro a la vez
        def __init__(self, *salidas):
            self.salidas = salidas

        def write(self, t):
            for s in self.salidas:
                s.write(t)

        def flush(self):
            for s in self.salidas:
                s.flush()

    with open(LOG, "a", encoding="utf-8") as reg:
        sys.stdout = sys.stderr = Duplicar(sys.__stdout__, reg)
        print(f"\n######## {datetime.now():%d/%m/%Y %H:%M:%S} · Avance equipo ########")
        try:
            ok = extraer(con_entel="--sin-entel" not in args)
        except Exception:
            traceback.print_exc()
            ok = False
        print(f"Resultado: {'OK' if ok else 'CON PROBLEMAS'}")
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    if interactivo:
        print("\nEsta ventana se cierra en 15 segundos...")
        time.sleep(15)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
