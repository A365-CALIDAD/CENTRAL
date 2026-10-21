"""
Calidad A365 · Programa de administración (CalidadA365.exe).

Menú para operar la plataforma sin instalar Python. El .exe debe estar en la carpeta CENTRAL
(junto a config/ y data/), que es una copia del repositorio A365-CALIDAD/CENTRAL.

    CalidadA365.exe           menú
    CalidadA365.exe --auto    sincroniza, actualiza y publica sin preguntar (para el Programador de tareas);
                              deja el registro en logs/automatico.log

Varios PC: antes de actualizar se trae lo último publicado y, si otro PC publicó datos nuevos, se recupera
su respaldo cifrado; así cada PC suma sus fuentes sobre lo último y nadie pisa los datos del otro.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

import avisos
import central_etl
import perfiles
import qualtrics
import validar_dashboards

RAIZ = central_etl.RAIZ
URL = "https://a365-calidad.github.io/CENTRAL/"
RESPALDO = RAIZ / "data" / "seguro" / "respaldo.json"
MARCA = RAIZ / "data" / ".respaldo_sincronizado"     # huella del último respaldo publicado que este PC ya tiene
INTERACTIVO = True                                   # False en modo --auto (no se hacen preguntas)


def titulo(texto):
    print("\n" + "=" * 64 + f"\n  {texto}\n" + "=" * 64)


def pausa():
    input("\nPresiona Enter para volver al menú...")


def git(*args, mostrar=True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if mostrar and (r.stdout.strip() or r.stderr.strip()):
        print((r.stdout + r.stderr).strip())
    return r


# ---------------------------------------------------------------- revisión del equipo

def revisar_equipo() -> list[str]:
    """Avisos de lo que falta en este PC (no detiene el programa)."""
    faltan = []
    if not (RAIZ / "config" / "fuentes.json").exists():
        faltan.append("No se encontró config/fuentes.json: el .exe debe estar dentro de la carpeta CENTRAL.")
    if not (RAIZ / "config" / "perfiles.local.json").exists():
        faltan.append("Falta config/perfiles.local.json (contraseñas): cópialo desde el PC del administrador.")
    if not (RAIZ / "config" / "bitacora.local.json").exists():
        faltan.append("Falta config/bitacora.local.json (bitácora en línea): cópialo desde el PC del administrador.")
    if not shutil.which("git"):
        faltan.append("Git no está instalado: no se podrá publicar (instálalo desde https://git-scm.com).")
    if not (RAIZ / "data" / "historico" / "mediciones.csv").exists() and RESPALDO.exists():
        faltan.append("Este PC aún no tiene el histórico: 'Actualizar datos y publicar' lo recupera solo del respaldo.")
    return faltan


# ---------------------------------------------------------------- acciones

def _huella(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest() if ruta.exists() else ""


def reparar_git() -> bool:
    """Deja el repositorio listo para sincronizar: cancela un rebase/merge a medias y descarta los conflictos
    en data/seguro (paquetes cifrados que se regeneran en cada actualización). Si hay conflictos en otros
    archivos no toca nada y lo informa."""
    carpeta_git = RAIZ / ".git"
    if (carpeta_git / "rebase-merge").exists() or (carpeta_git / "rebase-apply").exists():
        print("Había una sincronización a medias: se cancela.")
        git("rebase", "--abort", mostrar=False)
    if (carpeta_git / "MERGE_HEAD").exists():
        print("Había una combinación a medias: se cancela.")
        git("merge", "--abort", mostrar=False)
    conflictos = git("diff", "--name-only", "--diff-filter=U", mostrar=False).stdout.split()
    ajenos = [c for c in conflictos if not c.startswith("data/seguro/")]
    if ajenos:
        print("Hay conflictos en archivos que no son datos generados y hay que revisarlos a mano:")
        for c in ajenos:
            print(f"   - {c}")
        return False
    # Publicaciones locales que no llegaron a subirse: si solo traen datos cifrados (se regeneran), se
    # descartan y se parte de lo publicado; si traen otros archivos, se avisa sin tocar nada.
    if git("fetch", "-q", mostrar=False).returncode == 0:
        base = git("merge-base", "HEAD", "@{u}", mostrar=False).stdout.strip()
        pendientes = git("rev-list", "--count", "@{u}..HEAD", mostrar=False).stdout.strip()
        if base and pendientes not in ("", "0"):
            tocados = git("diff", "--name-only", base, "HEAD", mostrar=False).stdout.split()
            otros = [t for t in tocados if not t.startswith("data/seguro/")]
            if otros:
                print("Hay publicaciones de este PC sin subir que incluyen otros archivos; revísalas a mano:")
                for t in otros:
                    print(f"   - {t}")
                return False
            print(f"Se descartan {pendientes} publicación(es) de este PC que no se subieron (solo datos cifrados).")
            git("reset", "-q", "--", "data/seguro", mostrar=False)
            git("checkout", "HEAD", "--", "data/seguro", mostrar=False)
            # --keep: lleva todo a lo publicado y conserva los cambios propios del PC que no estén en conflicto.
            if git("reset", "-q", "--keep", "@{u}", mostrar=False).returncode != 0:
                print("No se pudo alinear con lo publicado sin perder cambios locales; revisa la carpeta a mano.")
                return False
    # Los paquetes cifrados se vuelven a generar al actualizar: se parte siempre de la versión publicada.
    git("reset", "-q", "--", "data/seguro", mostrar=False)
    git("checkout", "HEAD", "--", "data/seguro", mostrar=False)
    if conflictos:
        print(f"Se descartaron {len(conflictos)} datos cifrados en conflicto (se regeneran al actualizar).")
    return True


def sincronizar() -> bool:
    """Trae lo último publicado; si otro PC publicó datos nuevos, recupera su respaldo antes de actualizar."""
    if shutil.which("git"):
        if not reparar_git():
            return False
        print("Trayendo lo último publicado...")
        if git("pull", "--rebase", "--autostash").returncode != 0:
            reparar_git()
            print("No se pudo traer lo publicado (revisa la conexión y el inicio de sesión de Git) y vuelve a intentar.")
            return False
    huella = _huella(RESPALDO)
    if huella and (not MARCA.exists() or MARCA.read_text().strip() != huella):
        print("Hay datos publicados más nuevos que los de este PC: se recuperan del respaldo cifrado...")
        try:
            perfiles.restaurar_respaldo()
        except SystemExit as e:
            print(f"No se pudo recuperar el respaldo: {e}")
            return False
        MARCA.write_text(huella)
    return True


def actualizar(sincronizar_antes=True) -> bool:
    titulo("Actualizar datos (Drive + carpetas locales)")
    if sincronizar_antes and not sincronizar():
        return False
    print("Descargando bases, procesando y cifrando por perfil. Puede tardar unos minutos...\n")
    if central_etl.main(["procesar"]) not in (0, None):
        print("\nEl proceso terminó con problemas. Revisa los mensajes anteriores.")
        return False
    print("\nValidando contra los dashboards...")
    try:
        validar_dashboards.main()
    except Exception as e:                       # en otro PC puede no haber dashboards locales
        print(f"Validación omitida: {e}")
    print("\nAvisos por correo...")
    try:
        avisos.enviar()
    except SystemExit as e:
        print(e)
    print("\nDatos actualizados.")
    return True


def actualizar_avance() -> bool:
    """Solo el módulo Avance equipo (extracción de cada hora): descarga lo de hoy (Entel por la plataforma, Claro por
    Qualtrics, Movistar y BN por sus aplicaciones web), lo reparte por franja, cifra y publica. No reprocesa los KPI."""
    titulo("Avance equipo (extracción de la hora)")
    if not sincronizar():
        return False
    descargar_avance_entel()
    import avance
    avance.generar(central_etl.leer_json(central_etl.CONFIG / "fuentes.json")["fuentes"])
    perfiles.cifrar_perfiles()
    return publicar()


def actualizar_y_publicar() -> bool:
    if not actualizar():
        print("\nNo se publicó porque la actualización no terminó bien.")
        return False
    return publicar()


def asegurar_identidad() -> bool:
    """Git exige nombre y correo para registrar una publicación. Si este PC no los tiene, los pide
    una vez y los guarda solo para este repositorio (no cambia la configuración global de Git)."""
    nombre = git("config", "user.name", mostrar=False).stdout.strip()
    correo = git("config", "user.email", mostrar=False).stdout.strip()
    if nombre and correo:
        return True
    if not INTERACTIVO:
        print("Falta el nombre y correo de Git en este PC: abre CalidadA365.exe y usa 'Solo publicar' una vez para configurarlos.")
        return False
    print("\nEste PC aún no tiene un nombre y correo para registrar las publicaciones (se pide una sola vez).")
    nombre = nombre or input("Tu nombre: ").strip()
    correo = correo or input("Tu correo: ").strip()
    if not nombre or "@" not in correo:
        print("Se necesitan un nombre y un correo válidos para publicar.")
        return False
    git("config", "user.name", nombre, mostrar=False)
    git("config", "user.email", correo, mostrar=False)
    print("Guardado para este repositorio.")
    return True


def publicar() -> bool:
    titulo("Publicar en la página (GitHub Pages)")
    if not shutil.which("git"):
        print("Git no está instalado en este PC.")
        return False
    if not asegurar_identidad():
        return False
    git("add", "-A", "data/seguro", "config")
    hay_cambios = git("diff", "--cached", "--quiet", mostrar=False).returncode != 0
    if hay_cambios:
        mensaje = f"Actualiza datos Calidad A365 ({datetime.now():%d/%m/%Y %H:%M})"
        if git("commit", "-m", mensaje).returncode != 0:
            print("\nNo se pudo registrar la publicación (commit). Revisa el mensaje de arriba.")
            return False
    print("Sincronizando con lo publicado desde otros PC...")
    if git("pull", "--rebase", "--autostash").returncode != 0:
        git("rebase", "--abort", mostrar=False)
        print("\nOtro PC publicó al mismo tiempo. Vuelve a usar 'Actualizar y publicar' para combinar ambos datos.")
        return False
    if git("push").returncode != 0:
        print("\nNo se pudo subir a GitHub. Revisa el inicio de sesión de Git y vuelve a intentar.")
        return False
    MARCA.write_text(_huella(RESPALDO))          # el respaldo publicado ahora es el de este PC
    perfiles.marcar_secretos()                   # y sus contraseñas, las publicadas
    print("\nPublicado." if hay_cambios else "\nNo había datos nuevos; la página ya estaba al día.")
    print(f"La página se actualiza en 1 a 5 minutos: {URL}")
    return True


def cambiar_contrasenas():
    titulo("Cambiar contraseñas de los perfiles")
    perfiles.editar()


def ver_avisos():
    titulo("Vista previa de los correos de aviso")
    try:
        avisos.vista()
    except SystemExit as e:
        print(e)
        return
    carpeta = RAIZ / "data" / "avisos" / "vista"
    if carpeta.exists():
        os.startfile(carpeta)                    # abre la carpeta en el Explorador


def enviar_prueba():
    titulo("Enviar un correo de prueba")
    correo = input("Correo de destino: ").strip()
    if "@" not in correo:
        print("Correo no válido.")
        return
    try:
        avisos.prueba(correo)
    except SystemExit as e:
        print(e)


def recuperar_respaldo():
    titulo("Preparar este PC: recuperar datos desde el respaldo cifrado")
    if (RAIZ / "data" / "historico" / "mediciones.csv").exists():
        if input("Este PC ya tiene datos. ¿Reemplazarlos por el respaldo publicado? (s/n): ").strip().lower() != "s":
            return
    if shutil.which("git"):
        print("Trayendo el último respaldo publicado...")
        git("pull", "--rebase", "--autostash")
    try:
        perfiles.restaurar_respaldo()
        MARCA.write_text(_huella(RESPALDO))
    except SystemExit as e:
        print(e)


def bitacora_en_linea():
    titulo("Bitácora en línea (hoja de Google)")
    print("1. Generar el código para Google Apps Script")
    print("2. Guardar la URL de la aplicación web publicada")
    op = input("\nOpción: ").strip()
    if op == "1":
        ruta = perfiles.generar_script_bitacora()
        print(f"\nCódigo generado en {ruta}.")
        print("Ábrelo, copia todo y pégalo en la hoja: Extensiones › Apps Script (reemplazando lo que haya).")
        os.startfile(ruta.parent)
    elif op == "2":
        url = input("URL de la aplicación web (https://script.google.com/macros/s/.../exec): ").strip()
        try:
            perfiles.guardar_url_bitacora(url)
            print("Prueba de conexión:", "correcta" if perfiles.api_bitacora("listar").get("ok") else "con problemas")
            print("Usa 'Solo publicar' (o 'Actualizar datos y publicar') en el menú principal para activarla en la página.")
        except (SystemExit, RuntimeError, OSError) as e:
            print(f"No se pudo: {e}")


def conectar_qualtrics():
    titulo("Conectar Qualtrics (Claro Ecuador)")
    qualtrics.configurar()


def abrir_pagina():
    webbrowser.open(URL)
    print(f"Abriendo {URL}")


OPCIONES = [
    ("Actualizar datos y publicar (recomendado)", actualizar_y_publicar),
    ("Solo actualizar datos (sin publicar)", actualizar),
    ("Solo Avance equipo: descargar lo de hoy y publicar", actualizar_avance),
    ("Solo publicar", publicar),
    ("Cambiar contraseñas", cambiar_contrasenas),
    ("Ver correos de aviso (vista previa)", ver_avisos),
    ("Enviar correo de prueba", enviar_prueba),
    ("Preparar este PC (recuperar datos del respaldo)", recuperar_respaldo),
    ("Bitácora en línea (código y URL)", bitacora_en_linea),
    ("Conectar Qualtrics (Claro, avance del día)", conectar_qualtrics),
    ("Probar descarga de Entel (Reporte Pauta de hoy)", lambda: descargar_avance_entel()),
    ("Abrir la plataforma", abrir_pagina),
]


def descargar_avance_entel():
    """Antes de cada extracción baja los Reporte Pauta de hoy de todas las cuentas de Entel con el proceso de las
    adherencias (va dentro del .exe: no necesita Python). Si falla, se sigue con los archivos que haya."""
    import descarga_entel
    if not descarga_entel.BASE.exists():
        print(f"Avance equipo: no está el proceso de adherencias de Entel en este PC ({descarga_entel.BASE}); se omite la descarga.")
        return
    titulo("Descargando los Reporte Pauta de hoy (Entel)")
    try:
        if descarga_entel.main() != 0:
            print("La descarga de Entel terminó con problemas; se actualiza con los archivos que haya.")
    except Exception:
        traceback.print_exc()
        print("La descarga de Entel falló; se actualiza con los archivos que haya.")


def verificar_equipo() -> int:
    """CalidadA365.exe --verificar: revisa sin abrir Chrome que este PC tenga lo necesario para la extracción de cada hora."""
    titulo("Verificación de este PC para Avance equipo")
    ok = True
    import descarga_entel
    import qualtrics
    try:
        A = descarga_entel.cargar_proceso()
        print(f"  ✓ Proceso de adherencias de Entel cargado ({descarga_entel.BASE})")
        print(f"    .env: {'sí' if A.ARCHIVO_ENV.exists() else 'NO'} · perfil de Chrome: {'sí' if A.PERFIL_CHROME_RPA.exists() else 'NO'}"
              f" · Chrome: {'sí' if A.CHROME_EXE_PATH.exists() else 'NO'}")
        ok &= A.ARCHIVO_ENV.exists() and A.CHROME_EXE_PATH.exists()
    except Exception as e:
        print(f"  ✗ Proceso de adherencias de Entel: {e}")
        ok = False
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager
        print(f"  ✓ Selenium incluido (administrador de controladores: {SeleniumManager()._get_binary().name})")
    except Exception as e:
        print(f"  ✗ Selenium: {e}")
        ok = False
    q = qualtrics.leer_config()
    print(f"  {'✓' if q.get('token') else '·'} Qualtrics {'conectado' if q.get('token') else 'sin conectar (opción Conectar Qualtrics)'}"
          f"{' · encuestas: ' + str(len(q.get('encuestas') or {})) if q.get('token') else ''}")
    print(f"  {'✓' if shutil.which('git') else '✗'} Git {'instalado' if shutil.which('git') else 'NO instalado'}")
    print("\nTodo listo." if ok else "\nHay puntos por resolver (✗).")
    return 0 if ok else 1


def modo_automatico(solo_avance=False) -> int:
    """Sin preguntas: sincroniza, actualiza y publica (o solo Avance equipo). Registro en logs/automatico.log."""
    global INTERACTIVO
    INTERACTIVO = False
    logs = RAIZ / "logs"
    logs.mkdir(exist_ok=True)

    class Duplicar:                               # escribe en pantalla y en el registro a la vez
        def __init__(self, *salidas):
            self.salidas = salidas

        def write(self, t):
            for s in self.salidas:
                s.write(t)

        def flush(self):
            for s in self.salidas:
                s.flush()

    with open(logs / "automatico.log", "a", encoding="utf-8") as reg:
        sys.stdout = sys.stderr = Duplicar(sys.__stdout__, reg)
        modo = "solo Avance equipo" if solo_avance else "ejecución automática"
        print(f"\n######## {datetime.now():%d/%m/%Y %H:%M:%S} · {modo} ########")
        try:
            ok = actualizar_avance() if solo_avance else actualizar_y_publicar()
        except Exception:
            traceback.print_exc()
            ok = False
        print(f"Resultado: {'OK' if ok else 'CON PROBLEMAS'}")
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    return 0 if ok else 1


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Modo automático: con --auto, o si el ejecutable se llama "...Actualizar..." / "...Auto..."
    # (CalidadA365_Actualizar.exe), para usarlo con doble clic o en el Programador de tareas sin menú.
    if "--verificar" in sys.argv[1:]:
        return verificar_equipo()
    nombre = Path(sys.executable).stem.lower() if getattr(sys, "frozen", False) else ""
    # CalidadA365_Avance.exe / --avance: solo Avance equipo (para la tarea de cada hora)
    solo_avance = "--avance" in sys.argv[1:] or "avance" in nombre
    if solo_avance or "--auto" in sys.argv[1:] or "actualizar" in nombre or "auto" in nombre:
        codigo = modo_automatico(solo_avance)
        if sys.stdin and sys.stdin.isatty() and "--sin-espera" not in sys.argv[1:]:
            print("\nEsta ventana se cierra en 15 segundos...")
            import time
            time.sleep(15)
        return codigo
    os.system("title Calidad A365")
    while True:
        titulo("CALIDAD A365 · Administración")
        print(f"  Carpeta: {RAIZ}")
        for aviso in revisar_equipo():
            print(f"  ⚠ {aviso}")
        print()
        for i, (nombre, _) in enumerate(OPCIONES, 1):
            print(f"  {i}. {nombre}")
        print("  0. Salir")
        op = input("\nElige una opción: ").strip()
        if op == "0":
            return 0
        if not op.isdigit() or not 1 <= int(op) <= len(OPCIONES):
            continue
        try:
            OPCIONES[int(op) - 1][1]()
        except KeyboardInterrupt:
            print("\nCancelado.")
        except Exception:
            print("\nOcurrió un error inesperado:")
            traceback.print_exc()
        pausa()


if __name__ == "__main__":
    sys.exit(main())
