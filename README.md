# CENTRAL

Plataforma central de BI y seguimiento de calidad de posventa de A365 Calidad.
Integra en una sola interfaz los dashboards existentes de **Entel Chile**, **Claro Ecuador** y, próximamente, **Claro México**, sin fusionar sus repositorios, y consolida los indicadores de calidad de todas las cuentas evaluadas.

## Qué incluye

- **Portal web** (`index.html`): panel general con métricas, secciones por empresa con enlaces a sus dashboards, tabla consolidada con filtros (empresa, país, cuenta, indicador, periodo, estado) y exportación CSV, histórico y comparación entre periodos, seguimiento de cuentas críticas con bitácora de acciones, y reporte de calidad de datos. Responsive y con modo oscuro.
- **ETL en Python** (`etl/central_etl.py`): lee los Excel de cada empresa, valida columnas y tipos, homologa cuentas, fechas e indicadores, detecta duplicados y errores, registra cada carga y conserva el histórico versionado sin sobrescribir periodos anteriores.
- **Configuración centralizada** (`config/`): agregar un dashboard, país, indicador o formato de Excel no requiere tocar el código.

Detalle técnico: [docs/arquitectura.md](docs/arquitectura.md).

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
python -m unittest discover -s etl/tests -v
```

## Estado actual y pendientes

- **Vista general** (página de inicio): todos los servicios de Entel Chile (Inbound, Mesa Técnica, C2C, Outbound, E-commerce, Empresas) y Claro Ecuador (Inbound, Outbound, NPS) en una pantalla, con cantidad de evaluaciones y encuestas, indicadores principales y la tabla **Evaluaciones por servicio y mes**.
- **Dashboards**: visor que muestra cada dashboard publicado dentro de CENTRAL, con pestañas por servicio.
- Datos reales leídos de las carpetas locales `C:\A365\ENTEL` y `C:\A365\CLARO` (detalle en [docs/arquitectura.md](docs/arquitectura.md#41-conexión-con-las-bases-de-los-dashboards)).

Pendientes:

1. **Visualización de Entel Inbound y Mesa Técnica:** falta su URL de GitHub Pages en `config/portal.json`.
2. **Indicadores calculados en los dashboards:** la nota de Claro EC (Inbound/Outbound) y la EPA de Entel Outbound se calculan en el HTML de cada dashboard; hay que replicar esas reglas para traerlas.
3. **Homologar cuentas** entre monitoreo y EPA de Entel Inbound en `config/homologacion.json`.
4. **Metas:** validar metas y umbrales de `config/indicadores.json` (PENC, PEC, efectividad y global aún no tienen meta) y luego poner `metas_son_ejemplo: false`.
5. **GitHub Pages:** Settings → Pages → *Deploy from a branch* → `main` / raíz. Ver privacidad.

## Privacidad

Un sitio de GitHub Pages es accesible públicamente aunque el repositorio sea privado (salvo GitHub Enterprise Cloud con Pages privado), y publicar Pages desde un repo privado requiere plan Team o Enterprise. `data/` contiene solo indicadores agregados por cuenta, sin datos personales, y los Excel de entrada están excluidos por `.gitignore`. Si los resultados son confidenciales, revisar las alternativas de [docs/arquitectura.md](docs/arquitectura.md#6-seguridad-y-privacidad-importante).
