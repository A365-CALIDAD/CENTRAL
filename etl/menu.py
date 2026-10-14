"""
Calidad A365 · Programa de administración (CalidadA365.exe).

Menú para operar la plataforma sin instalar Python. El .exe debe estar en la carpeta CENTRAL
(junto a config/ y data/), que es una copia del repositorio A365-CALIDAD/CENTRAL.
"""
from __future__ import annotations

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
import validar_dashboards

RAIZ = central_etl.RAIZ
URL = "https://a365-calidad.github.io/CENTRAL/"


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
    if not shutil.which("git"):
        faltan.append("Git no está instalado: no se podrá publicar (instálalo desde https://git-scm.com).")
    if not (RAIZ / "data" / "historico" / "mediciones.csv").exists() and (RAIZ / "data" / "seguro" / "respaldo.json").exists():
        faltan.append("Este PC no tiene el histórico de datos: usa la opción 6 para recuperarlo del respaldo cifrado.")
    return faltan


# ---------------------------------------------------------------- acciones

def actualizar():
    titulo("Actualizar datos (Drive + carpetas locales)")
    print("Descargando bases, procesando y cifrando por perfil. Puede tardar unos minutos...\n")
    if central_etl.main(["procesar"]) not in (0, None):
        print("\nEl proceso terminó con problemas. Revisa los mensajes anteriores.")
        return
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
    print("\nListo. Usa la opción 2 para publicar los cambios en la página.")


def publicar():
    titulo("Publicar en la página (GitHub Pages)")
    if not shutil.which("git"):
        print("Git no está instalado en este PC.")
        return
    print("Trayendo los cambios publicados desde otros PC...")
    git("pull", "--rebase", "--autostash")
    git("add", "-A", "data/seguro", "config")
    if not git("diff", "--cached", "--quiet", mostrar=False).returncode:
        print("No hay cambios nuevos para publicar.")
        return
    mensaje = f"Actualiza datos Calidad A365 ({datetime.now():%d/%m/%Y %H:%M})"
    git("commit", "-m", mensaje)
    r = git("push")
    if r.returncode == 0:
        print(f"\nPublicado. La página se actualiza en 1 a 5 minutos: {URL}")
    else:
        print("\nNo se pudo publicar. Revisa que este PC tenga acceso a GitHub (inicio de sesión de Git).")


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
    except SystemExit as e:
        print(e)


def abrir_pagina():
    webbrowser.open(URL)
    print(f"Abriendo {URL}")


OPCIONES = [
    ("Actualizar datos", actualizar),
    ("Publicar en la página", publicar),
    ("Cambiar contraseñas", cambiar_contrasenas),
    ("Ver correos de aviso (vista previa)", ver_avisos),
    ("Enviar correo de prueba", enviar_prueba),
    ("Preparar este PC (recuperar datos del respaldo)", recuperar_respaldo),
    ("Abrir la plataforma", abrir_pagina),
]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
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
