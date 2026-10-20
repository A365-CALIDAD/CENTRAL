# CENTRAL

Plataforma central de BI y seguimiento de calidad de posventa de A365 Calidad.
Integra en una sola interfaz los dashboards existentes de **Entel Chile**, **Claro Ecuador** y, próximamente, **Claro México**, sin fusionar sus repositorios, y consolida los indicadores de calidad de todas las cuentas evaluadas.

## Qué incluye

- **Portal web** (`index.html`): panel general con métricas, secciones por empresa con enlaces a sus dashboards, tabla consolidada con filtros (empresa, país, cuenta, indicador, periodo, estado) y exportación CSV, histórico y comparación entre periodos, seguimiento de cuentas críticas con bitácora de acciones, y reporte de calidad de datos. Responsive y con modo oscuro.
- **ETL en Python** (`etl/central_etl.py`): lee los Excel de cada empresa, valida columnas y tipos, homologa cuentas, fechas e indicadores, detecta duplicados y errores, registra cada carga y conserva el histórico versionado sin sobrescribir periodos anteriores.
- **Configuración centralizada** (`config/`): agregar un dashboard, país, indicador o formato de Excel no requiere tocar el código.

Detalle técnico: [docs/arquitectura.md](docs/arquitectura.md). Qué hace cada página y cómo se calcula cada KPI: [docs/diccionario_modulos.md](docs/diccionario_modulos.md).

## Estructura

```
CENTRAL/
├── index.html                  Portal (SPA estática)
├── assets/css/central.css      Estilos y tema claro/oscuro
├── assets/js/                  app.js (rutas) · datos.js · componentes.js · vistas.js
├── config/
│   ├── portal.json             Empresas, países y dashboards (URLs pendientes)
│   ├── indicadores.json        Catálogo de indicadores, metas, umbrales y alias
│   ├── fuentes.json            Cómo leer los Excel de cada empresa
│   └── homologacion.json       Equivalencias de nombres de cuentas
├── etl/
│   ├── central_etl.py          ETL
│   ├── generar_ejemplos.py     Genera Excel ficticios de prueba
│   ├── entrada/<fuente>/       Excel de entrada (no se versionan)
│   └── tests/                  Pruebas unitarias
├── data/                       Salidas del ETL que lee el portal
│   ├── consolidado.json
│   ├── seguimiento.json        Bitácora oficial de acciones
│   ├── historico/mediciones.csv
│   ├── cargas/                 registro_cargas.csv · resumen.json · errores/
│   └── chatbot/contexto.json
└── actualizar_central.bat      Ejecuta el ETL en Windows
```

## Uso rápido

```bash
pip install -r requirements.txt
python etl/central_etl.py procesar           # procesa etl/entrada/* y publica data/
python -m http.server 8000                   # luego abrir http://localhost:8000
```

Otros comandos:

```bash
python etl/central_etl.py procesar --simular                # valida sin escribir nada
python etl/central_etl.py procesar --fuente demo_claro_ec   # solo una fuente
python etl/central_etl.py procesar --permitir-correcciones  # versiona correcciones de periodos cerrados
python etl/central_etl.py publicar                          # regenera los JSON desde el histórico
python etl/central_etl.py validar-config
python etl/validar_dashboards.py                         # compara cada indicador con su dashboard
python -m unittest discover -s etl/tests -v
```

## Estado actual y pendientes

- **Vista general** (página de inicio): todos los servicios de Entel Chile (Inbound, Mesa Técnica, C2C, Outbound, E-commerce, Empresas) y Claro Ecuador (Inbound, Outbound, NPS) en una pantalla, con cantidad de evaluaciones y encuestas, indicadores principales y la tabla **Evaluaciones por servicio y mes**.
- **Dashboards**: visor que muestra cada dashboard publicado dentro de CENTRAL, con pestañas por servicio.
- Bases más recientes de **Google Drive** para Entel Outbound, E-commerce, EPA Outbound y Empresas, y Claro Ecuador Inbound y Outbound; Banco de la Nación · Fraude se lee del Google Sheet de fraude a través de la aplicación web que alimenta su dashboard, sin datos del cliente ni nombre del asesor; Movistar México · Outbound, de los Google Forms a través de la aplicación web de su dashboard (`?central=1`, sin datos personales) (detalle en [docs/arquitectura.md](docs/arquitectura.md#descarga-desde-google-drive)); el resto, desde las carpetas locales.
- Datos reales leídos de las carpetas locales `C:\A365\ENTEL` y `C:\A365\CLARO` (detalle en [docs/arquitectura.md](docs/arquitectura.md#41-conexión-con-las-bases-de-los-dashboards)).

Pendientes:

1. **Histórico EPA de Mesa Técnica:** el dashboard lo toma del Evolutivo `.xlsb` (desde abril 2024); CENTRAL hoy solo lee el Excel mensual.
2. **Homologar cuentas** entre monitoreo y EPA de Entel Inbound en `config/homologacion.json`.
3. **Metas:** solo hay metas donde el dashboard las define (EPA Entel Inbound y Mesa Técnica, Nota COPC de Claro). Acordar las del resto en `config/indicadores.json`.
4. **GitHub Pages:** Settings → Pages → *Deploy from a branch* → `main` / raíz. Ver privacidad.

## Perfiles y privacidad

La página pide **perfil y contraseña**. Hay un perfil **Administrador** (ve todo, incluida Calidad de datos) y **uno por cuenta** (Entel Inbound, Entel C2C, Claro Outbound…), que ve solo su cuenta. La lista está en `config/perfiles.json`.

- Los datos **no se publican en claro**: el ETL genera un paquete cifrado por perfil en `data/seguro/` (PBKDF2-SHA256, 600.000 iteraciones + AES-256-GCM) y el navegador lo descifra con la contraseña. Sin ella, el archivo no se puede leer aunque la página sea pública.
- Las contraseñas están **solo en este PC**, en `config/perfiles.local.json` (excluido de Git). Se generan solas la primera vez.
- Los datos en claro (`data/consolidado.json`, `data/historico/`, `data/cargas/`, `data/seguimiento.json`) quedan solo en este PC; en `data/seguro/respaldo.json` se publica un respaldo cifrado con la clave del administrador. Ese respaldo también lleva las contraseñas de los perfiles y las claves de la bitácora, para que todos los PC usen las mismas: gana lo publicado, salvo lo que se cambió en ese PC desde su última publicación.
- Los dashboards originales de cada cuenta siguen siendo públicos en sus propias URLs.

**Cambiar contraseñas:** doble clic en `cambiar_contrasenas.bat`. Elige el perfil y escribe la contraseña nueva dos veces (mínimo 10 caracteres, letras y números); al terminar, los datos se cifran de nuevo. También se puede editar `config/perfiles.local.json` a mano y luego ejecutar `python etl/perfiles.py cifrar`. En ambos casos hay que publicar `data/seguro/` (commit y push).

```bash
python etl/perfiles.py lista                          # perfiles y cuentas (sin mostrar contraseñas)
python etl/perfiles.py clave entel-c2c NuevaClave123  # cambiar una contraseña (sin la clave, genera una)
python etl/perfiles.py importar-seguimiento archivo.json   # unir acciones exportadas desde la página
python etl/perfiles.py restaurar-respaldo             # recuperar data/ desde el respaldo cifrado
```

Después de cambiar una contraseña hay que publicar (`git add data/seguro && git commit && git push`) y avisar al usuario de ese perfil.

## Avisos por correo

`etl/avisos.py` envía a cada perfil un resumen de sus indicadores bajo meta (Crítico / Alerta), los meses seguidos bajo meta y las acciones de seguimiento vencidas. Solo envía cuando algo cambió desde el último aviso, como máximo una vez al día por perfil. `actualizar_central.bat` lo ejecuta al final.

1. `python etl/avisos.py iniciar` crea `config/avisos.local.json` (no se publica): escribe los correos de cada perfil y pon `"activo": true`.
2. En `CENTRAL/.env` (no se publica) agrega el remitente: `AVISOS_SMTP_USUARIO=cuenta@gmail.com` y `AVISOS_SMTP_CLAVE=` la **contraseña de aplicación** de esa cuenta de Google (Cuenta de Google › Seguridad › Verificación en 2 pasos › Contraseñas de aplicaciones).
3. `python etl/avisos.py vista` genera los correos en `data/avisos/vista/` para revisarlos sin enviar.
4. `python etl/avisos.py prueba tu-correo@gmail.com` envía solo el correo del administrador a esa dirección.

Los correos llevan el resumen en claro (fuera del cifrado de la página); solo incluyen lo que está bajo meta, no el detalle completo.

## Programa CalidadA365.exe (para usar en otro PC)

`CalidadA365.exe` reúne todo en un menú y no necesita Python: **1** Actualizar datos · **2** Publicar en la página · **3** Cambiar contraseñas · **4** Ver correos de aviso · **5** Enviar correo de prueba · **6** Preparar este PC (recuperar datos del respaldo) · **7** Abrir la plataforma.

Se genera con `generar_exe.bat` y no se sube a GitHub (pesa ~46 MB); se copia a mano.

**Instalar en otro PC**

1. Instalar Git (https://git-scm.com) e iniciar sesión con una cuenta con acceso a `A365-CALIDAD/CENTRAL`.
2. Clonar el repositorio: `git clone https://github.com/A365-CALIDAD/CENTRAL.git`
3. Copiar dentro de esa carpeta `CENTRAL`, desde el PC del administrador:
   - `CalidadA365.exe`
   - `config/perfiles.local.json` (contraseñas, obligatorio)
   - `config/avisos.local.json` y `.env` (solo si ese PC enviará avisos)
4. Abrir `CalidadA365.exe` y elegir **6** para recuperar el histórico desde el respaldo cifrado.
5. Desde ahí, **1** para actualizar y **2** para publicar.

Las bases de Drive (Entel Outbound, E-commerce, EPA Outbound, Empresas, Claro Ecuador y BN Fraude) se descargan en cualquier PC. Las de carpetas locales (Entel Inbound, Mesa Técnica y C2C) solo se leen si ese PC tiene las carpetas `ENTEL\...` al lado de `CENTRAL`; si no, se conservan sus últimos datos. "Publicar" trae primero lo que publicó el otro PC, para no pisarse.

## Bitácora de acciones en línea

Las acciones de seguimiento se guardan en una **hoja de Google** mediante un script de Google Apps publicado como aplicación web, así que se ven al instante en cualquier equipo.

- **Administrador:** en *Gestión › Seguimiento de cuentas* ve las cuentas bajo meta, crea acciones ("+ Crear acción"), las edita, elimina y revisa su historial.
- **Perfiles de cuenta:** en *Gestión › Mis acciones* ven solo las acciones de sus cuentas y pueden **Actualizar avance** (estado + comentario).
- Cada cambio queda en la hoja "Historial". Los correos de aviso usan las acciones vencidas de la bitácora.
- Seguridad: cada perfil tiene una clave de acceso aleatoria (`config/bitacora.local.json`, no se publica) que viaja dentro de su paquete cifrado; el script solo guarda su huella SHA-256 y valida los permisos en cada pedido.

**Puesta en marcha (una vez)**

1. `python etl/perfiles.py bitacora` (o `.exe` › Bitácora en línea › 1) genera `bitacora/Codigo.gs`.
2. En la hoja de Google: *Extensiones › Apps Script*, borrar lo que haya, pegar todo `Codigo.gs` y guardar.
3. *Implementar › Nueva implementación › Tipo: Aplicación web* · Ejecutar como: **Yo** · Quién tiene acceso: **Cualquier usuario** · Implementar y autorizar.
4. Copiar la URL que termina en `/exec` y guardarla: `python etl/perfiles.py bitacora-url <URL>` (o `.exe` › Bitácora en línea › 2).
5. Publicar (`data/seguro`).

Si se agregan o quitan perfiles, repetir 1 y 2 y, en Apps Script, *Implementar › Administrar implementaciones › Editar › Nueva versión* (la URL no cambia). Cambiar contraseñas no requiere tocar el script. Para probar sin Google: `python etl/bitacora_simulador.py` y `python etl/perfiles.py bitacora-url http://localhost:8791`.

## Actualización automática

- `CalidadA365_Actualizar.exe` es el mismo programa que `CalidadA365.exe`, pero **no muestra el menú**: al abrirlo trae lo publicado, actualiza (Drive + carpetas locales), valida, envía avisos y publica. Al terminar cierra solo y deja el registro en `logsutomatico.log`. (`CalidadA365.exe --auto` hace lo mismo.)
- Para que corra solo: doble clic en `programar_actualizacion.bat` (o `programar_actualizacion.bat 08:30 4 10` = desde las 08:30, cada 4 horas, durante 10 horas). Crea la tarea "Calidad A365 - Actualizar y publicar" en el Programador de tareas de Windows.
- Requisitos del PC: haber usado una vez *Solo publicar* en `CalidadA365.exe` (nombre/correo de Git y sesión de GitHub guardados), estar encendido con la sesión iniciada, y correr después de los scripts de descarga de los dashboards. Conviene automatizar un solo PC: el que tiene las carpetas `ENTEL` y `CLARO` con sus descargas diarias.
- Si un PC no tiene las descargas diarias "Reporte Pauta" de Outbound o E-commerce, omite esas fuentes y conserva lo publicado por el PC que sí las tiene.
