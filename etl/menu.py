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


def sincronizar() -> bool:
    """Trae lo último publicado; si otro PC publicó datos nuevos, recupera su respaldo antes de actualizar."""
    if shutil.which("git"):
        print("Trayendo lo último publicado...")
        if git("pull", "--rebase", "--autostash").returncode != 0:
            print("No se pudo traer lo publicado (revisa conexión e inicio de sesión de Git).")
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
            print("Usa "Solo publicar" (o "Actualizar datos y publicar") en el menú principal para activarla en la página.")
        except (SystemExit, RuntimeError, OSError) as e:
            print(f"No se pudo: {e}")


def abrir_pagina():
    webbrowser.open(URL)
    print(f"Abriendo {URL}")


OPCIONES = [
    ("Actualizar datos y publicar (recomendado)", actualizar_y_publicar),
    ("Solo actualizar datos (sin publicar)", actualizar),
    ("Solo publicar", publicar),
    ("Cambiar contraseñas", cambiar_contrasenas),
    ("Ver correos de aviso (vista previa)", ver_avisos),
    ("Enviar correo de prueba", enviar_prueba),
    ("Preparar este PC (recuperar datos del respaldo)", recuperar_respaldo),
    ("Bitácora en línea (código y URL)", bitacora_en_linea),
    ("Abrir la plataforma", abrir_pagina),
]


def modo_automatico() -> int:
    """Sin preguntas: sincroniza, actualiza y publica. Registro en logs/automatico.log."""
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
        print(f"\n######## {datetime.now():%d/%m/%Y %H:%M:%S} · ejecución automática ########")
        try:
            ok = actualizar_y_publicar()
        except Exception:
            traceback.print_exc()
            ok = False
        print(f"Resultado: {'OK' if ok else 'CON PROBLEMAS'}")
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    return 0 if ok else 1


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if "--auto" in sys.argv[1:]:
        return modo_automatico()
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
