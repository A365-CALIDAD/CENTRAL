# Diccionario de módulos · Calidad A365

Referencia de cada módulo de la plataforma: qué muestra, cómo se calcula y de dónde salen los datos.
Sitio publicado: https://a365-calidad.github.io/CENTRAL/ · Actualizado: 14/10/2026 (menú por módulos).

**Contenido**

1. [Conceptos básicos](#1-conceptos-básicos)
2. [Módulos de la plataforma (páginas)](#2-módulos-de-la-plataforma-páginas)
3. [Diccionario de indicadores (KPI)](#3-diccionario-de-indicadores-kpi)
4. [Cuentas: indicadores y origen de datos](#4-cuentas-indicadores-y-origen-de-datos)
5. [Estados, colores y símbolos](#5-estados-colores-y-símbolos)
6. [Módulos técnicos (archivos)](#6-módulos-técnicos-archivos)
7. [Glosario](#7-glosario)

---

## 1. Conceptos básicos

| Término | Significado | Ejemplo |
|---|---|---|
| **Empresa** | Cliente para el que A365 mide la calidad | Entel, Claro |
| **País** | País de operación de la empresa | Chile, Ecuador, México |
| **Cuenta** (o servicio) | Cada operación evaluada; tiene su propio dashboard | Entel Inbound, Entel C2C, Claro Outbound |
| **Plataforma / campaña** | Subdivisión dentro de una cuenta, tal como viene en la base | S2S HOGAR, RETENCIONES C2C - MOVIL, PREPAGO |
| **Periodo** | Mes de la medición, en formato año-mes | 2026-10 (oct 2026) |
| **Total de la cuenta** | Resultado del mes de toda la cuenta, calculado con la misma fórmula de su dashboard | Nota de calidad de Entel C2C en septiembre: 83,2% |
| **Mes en curso** | Mes actual; sus cifras son parciales y siguen creciendo | Se marca "(en curso)" y las variaciones de cantidades dicen "parcial" |

---

## 2. Módulos de la plataforma (páginas)

Orden del menú (igual en computador y en el menú "Más" del celular):

| Módulo | Submódulos |
|---|---|
| **Inicio** | Vista general (incluye la tabla de KPI por cuenta) |
| **Clientes** | **Entel Chile:** Resumen de la empresa · Inbound · Mesa Técnica · C2C · Outbound · E-commerce · Empresas<br>**Claro Ecuador:** Resumen de la empresa · Inbound · Outbound · NPS (abre su dashboard)<br>**Claro México:** Próximamente |
| **Análisis** | Histórico y evolución · Tabla consolidada |
| **Gestión** | Seguimiento de cuentas · Avance equipo |
| **Herramientas** | Dashboards · Calidad de datos |

Barra inferior del celular: General · Dashboards · Seguimiento · Más (abre el menú completo).

### 2.1 Inicio

_Resumen de todas las cuentas._

#### 2.1.1 Vista general
- **Ruta:** `#/general` (página de inicio) · Menú: *Inicio › Vista general* · Celular: *General*
- **Para qué sirve:** ver en una pantalla cómo van todas las cuentas en el mes.
- **Muestra:**
  - **KPI por cuenta:** tabla resumen con una fila por cuenta (ver 2.1.2).
  - **Totales del mes:** evaluaciones de calidad, encuestas de clientes, cuentas con datos e indicadores bajo meta, con su variación contra el mes anterior.
  - **Tarjeta por cuenta**, agrupadas por empresa: cantidad de evaluaciones y encuestas, los 3 indicadores principales (el resto en "Ver más") y botones *Ver dashboard* y *Abrir ↗*.
  - **Evaluaciones por cuenta y mes:** tabla con la cantidad de monitoreos y encuestas de los últimos 12 meses (6 en celular), con totales.
- **Filtros:** Mes (por defecto, el mes en curso) y Empresa.
- **Acciones:** exportar a CSV la tabla de evaluaciones; tocar una cuenta para ir a su detalle.

#### 2.1.2 Tabla completa de KPI por cuenta
- **Ruta:** `#/kpis` · Se abre con *Ver tabla completa* en Vista general (no tiene entrada propia en el menú: la misma tabla ya aparece primero en Vista general)
- **Para qué sirve:** comparar las cuentas entre sí, KPI por KPI.
- **Muestra:** una fila por cuenta y una columna por KPI (evaluaciones, encuestas, nota de calidad, EPA, resolutividad, efectividad, PEC, PENC, adherencia y satisfacción global). En cada celda:
  - el valor del mes;
  - el punto de estado frente a la meta;
  - la flecha contra el mes anterior.
- **Filtros:** Mes y Empresa. Al tocar un encabezado se ordena por ese KPI.
- **Acciones:** *Exportar CSV*, con valor del mes, valor del mes anterior y meta de cada KPI; tocar una cuenta para ver su detalle.

### 2.2 Clientes

_Una sección desplegable por empresa; dentro, sus cuentas como submódulos._

#### 2.2.1 Resumen de la empresa
- **Ruta:** `#/empresa/<empresa>/<país>` · Menú: *Clientes › <empresa> › Resumen de la empresa*
- **Para qué sirve:** ver todas las cuentas y plataformas de una empresa.
- **Muestra:**
  - accesos a los dashboards de la empresa;
  - totales: plataformas evaluadas, indicadores vigentes, % de cumplimiento, críticos y alertas;
  - matriz *Resultados por plataforma / campaña*: una fila por cuenta y plataforma, una columna por KPI.
- **Filtros:** Periodo.
- **Claro México:** marcada *Próximamente* hasta que se configure.

#### 2.2.2 Detalle de cuenta (submódulo de cada empresa)
- **Ruta:** `#/servicio/<cuenta>` (por ejemplo `#/servicio/entel-c2c`) · Menú: *Clientes › <empresa> › <cuenta>*, o al tocar una cuenta en las tablas.
- **Para qué sirve:** analizar una cuenta en profundidad.
- **Muestra:**
  - **Tarjetas de KPI:** valor, meta, variación contra el mes anterior y cantidad de casos.
  - **Evolución de indicadores:** gráfico de los últimos 12 meses (KPI en % e índice EPA).
  - **Evaluaciones y encuestas:** gráfico de cantidades por mes.
  - **Por plataforma / campaña:** tabla del mes con cada plataforma de la cuenta.
- **Filtros:** Mes.
- **Acciones:** *Ver dashboard*, que abre el dashboard original de la cuenta.

### 2.3 Análisis

_Tendencias y detalle completo de las mediciones._

#### 2.3.1 Histórico y evolución
- **Ruta:** `#/historico` · Menú: *Análisis › Histórico y evolución*
- **Para qué sirve:** ver tendencias y comparar dos meses.
- **Gráfico de evolución:** depende de lo que se filtre.
  - Sin empresa: promedio por empresa.
  - Con empresa y país: cada plataforma, hasta 8.
  - Con una cuenta: su serie y su meta.
- **Comparación entre periodos:** valor base, valor comparado y variación, por plataforma e indicador. Por defecto compara el mes en curso con el anterior.
- **Filtros:** los mismos de la tabla consolidada, más *Periodo base* y *Periodo comparado*.

#### 2.3.2 Tabla consolidada
- **Ruta:** `#/indicadores` · Menú: *Análisis › Tabla consolidada*
- **Para qué sirve:** consultar el detalle completo de todas las mediciones.
- **Muestra:** una fila por empresa, cuenta, plataforma, indicador y mes, con valor, meta, brecha, muestras y estado. En celular se ve como tarjetas.
- **Filtros:** Empresa, País, Servicio, Cuenta, Indicador, Desde, Hasta y Estado.
- **Acciones:** *Exportar CSV*; *+ Seguimiento* en las filas bajo meta.

### 2.4 Gestión

_Planes de acción sobre lo que está bajo meta._

#### 2.4.1 Seguimiento de cuentas
- **Ruta:** `#/seguimiento` · Menú: *Gestión › Seguimiento de cuentas*
- **Para qué sirve:** detectar qué requiere acción y registrar el plan.
- **Pestaña *Cuentas a seguir*:** plataformas cuyo último resultado está en *Alerta* o *Crítico*. Para cada una muestra:
  - brecha frente a la meta;
  - **periodos seguidos** bajo meta (⚠ desde 3);
  - acciones abiertas.
- **Pestaña *Bitácora de acciones*:** observación, acción pendiente, responsable, fecha de compromiso y estado (*Abierta*, *En curso*, *Cerrada*). Marca las acciones *vencidas*.
- **Filtros:** Empresa, País, Servicio, Cuenta, Indicador, Estado.
- **Acciones:**
  - *+ Registrar* / *+ Nueva* / *Editar*: queda como borrador en el navegador.
  - *Exportar seguimiento.json*: para publicarlo, ese archivo se sube a `data/seguimiento.json`.

#### 2.4.2 Avance equipo
- **Ruta:** `#/avance` · Menú: *Gestión › Avance equipo* (aparece cuando hay datos)
- **Para qué sirve:** ver cuántas evaluaciones hizo cada monitor en cada franja del día y cuánto duraron las llamadas evaluadas.
- **Tabla:** una fila por monitor (con su cuenta); por cada franja entre cortes (07:00–08:00, 08:00–09:00, …; la franja que sigue abierta al momento de la extracción se marca *en curso*) muestra **Q** (evaluaciones enviadas) y **Tiempo** (suma de la duración de las llamadas evaluadas, h:mm:ss), más el total del día.
- **Filtros:** Día, Cuenta y Conteo (*Por franja* o *Acumulado al corte*). *Exportar CSV* descarga las evaluaciones del día.
- **Origen:** hora de envío y duración de la llamada de cada base: Entel (base de adherencias más las descargas *Reporte Pauta* de cada cuenta, que se bajan varias veces al día; *Realizador*, *Fecha/Hora Envío*, *TMO del caso* / *TMO2*) y Claro (exportaciones de Qualtrics de la carpeta *filtrado*, sin repetir *ResponseId*: *Analista de Calidad A365*, *RecordedDate*, *Duración de llamada*); en Outbound de Entel solo las descargas *Centros 2.0*. Configurable con la clave `avance` de cada fuente; los cortes, en `avance_equipo.cortes` de `config/portal.json`.
- **Movistar y BN:** desde sus aplicaciones web (`?avance=1` del dashboard de Movistar: Marca temporal y Evaluador; bloque `avance` de BN: Marca temporal y TMO, sin evaluador).
- **Descarga de Entel:** en cada extracción automática, `CalidadA365_Actualizar.exe` ejecuta antes `ENTELAvance_EquipoDescargar_avance_hoy.py`, que con el proceso de las adherencias descarga de una vez los Reporte Pauta de hoy de las cinco cuentas.
- **Actualización:** con cada actualización de CENTRAL; el día en curso se completa a medida que llegan las bases.

### 2.5 Herramientas

_Acceso a los dashboards originales y control de la carga de datos._

#### 2.5.1 Dashboards (visor)
- **Ruta:** `#/ver` y `#/ver/<cuenta>` · Menú: *Herramientas › Dashboards*
- **Para qué sirve:** abrir los dashboards originales de cada cuenta sin salir de la plataforma.
- **Muestra:** pestañas agrupadas por empresa y el dashboard seleccionado dentro de la página.
- **Acciones:** *Abrir en pestaña nueva* (recomendado en celular) y *Repositorio*.
- **Origen de los enlaces:** `config/portal.json`.

#### 2.5.2 Calidad de datos
- **Ruta:** `#/calidad` · Menú: *Herramientas › Calidad de datos*
- **Para qué sirve:** controlar que la información cargada sea confiable.
- **Muestra:**
  - **Totales:** cargas procesadas, mediciones en el histórico, registros con error y conflictos.
  - **Registro de cargas:** archivo, estado y conteos de cada ejecución.
  - **Validación contra los dashboards:** cuántos valores mensuales coinciden con cada dashboard y el detalle de las diferencias.
  - **Errores detectados:** fila del Excel, campo, tipo de error y detalle.
- **Acciones:** *Exportar CSV* de errores.

### Elementos comunes
| Elemento | Función |
|---|---|
| Menú lateral (☰ en celular) | Navegación completa |
| Barra inferior (celular) | General · Dashboards · Seguimiento · Más |
| Botón ◐ | Cambia entre tema claro y oscuro |
| "Datos actualizados" | Fecha y hora de la última carga |

---

### Perfiles y acceso

| Perfil | Ve | Calidad de datos |
|---|---|---|
| **Administrador** | Todos los clientes y cuentas | Sí |
| **Una por cuenta** (Entel Chile · Inbound, Mesa Técnica, C2C, Outbound, E-commerce, Empresas; Claro Ecuador · Inbound, Outbound, NPS) | Solo su cuenta: menú, Vista general, detalle, histórico, tabla, seguimiento y su dashboard | No |

- **Ingreso:** se elige el perfil y se escribe la contraseña. La sesión dura hasta cerrar el navegador, y el botón **Salir** la cierra antes.
- **Protección:** los datos de cada perfil viajan cifrados con su contraseña; sin ella no se pueden leer.
- **Seguimiento:** las acciones registradas por un perfil se exportan y el administrador las une a la bitácora oficial.

## 3. Diccionario de indicadores (KPI)

| KPI | Id | Unidad | Definición y fórmula | Sentido |
|---|---|---|---|---|
| **Evaluaciones** | `evaluaciones` | cantidad | Monitoreos de calidad realizados en el mes. Un ID Pauta repetido se cuenta una vez, salvo en Outbound y E-commerce, donde se respeta la regla de su dashboard. | — |
| **Encuestas** | `encuestas` | cantidad | Encuestas de clientes recibidas en el mes. | — |
| **Nota de calidad** | `calidad` | % (0–100) | Nota final del monitoreo. En Entel es el promedio de *Resultado Final*, que C2C y Mesa Técnica llaman "Adherencia Global". En Empresas es el promedio de *Nota*. En Claro es la *Nota COPC* (ver abajo). | Mayor es mejor |
| **EPA** | `epa` | índice (−100 a 100) | Encuesta post atención: cada encuesta vale +100 (satisfecho), 0 (neutro) o −100 (insatisfecho), y se promedian. En Outbound se recodifica la pregunta Global: 4–5 = 100, 3 = 0, 1–2 = −100. **No es un porcentaje.** | Mayor es mejor |
| **Resolutividad (FCR)** | `fcr` | % | % de casos resueltos. En Entel se toma *Resolutividad* (1 = sí, 2 = no). En Claro Inbound es SI ÷ (SI + NO) de la columna *FCR*. | Mayor es mejor |
| **PEC** | `pec` | % | Puntaje de errores críticos de la pauta de monitoreo; 100 = sin error crítico. | Mayor es mejor |
| **PENC** | `penc` | % | Puntaje de errores no críticos de la pauta de monitoreo. | Mayor es mejor |
| **Adherencia** | `adherencia` | % | Cumplimiento del bloque de adherencia de la pauta (*Adherencia (100%)*). Solo Entel Inbound. | Mayor es mejor |
| **Efectividad de venta** | `efectividad` | % | Llamadas monitoreadas con venta concretada: SI ÷ total de evaluaciones ("no aplica" cuenta como no venta, como su dashboard). Solo Claro Outbound. | Mayor es mejor |
| **Satisfacción global** | `global` | puntos (1–5) | Promedio de la pregunta *Global* de la encuesta. | Mayor es mejor |

**Nota COPC (Claro Ecuador).** Réplica exacta de la fórmula de sus dashboards:
- **Inbound:**
  1. Cada ítem vale 1 (SI CUMPLE), 0 (NO CUMPLE) o se omite (NO APLICA).
  2. Cada bloque es el promedio ponderado de sus ítems.
  3. La nota pondera los bloques: ASE 10, UF 25, NEG 30, CUM 15, COM 20.
  4. Si algún ítem crítico es NO CUMPLE, la nota es **0**.
- **Outbound:** la nota es la columna *EC*; vale **0** si algún ítem crítico es NO CUMPLE.

**Metas vigentes.** Solo se usan las metas que define cada dashboard; el resto aparece *sin meta*.

| Cuenta | KPI | Meta | Origen |
|---|---|---|---|
| Entel Inbound | EPA | Por plataforma: S2S Móvil 2.0 67 · Fibra 66 · S2S Hogar 64 · Técnico 62 · Adulto Mayor 75 · Reclamos Fibra 60 · Reclamos Inalámbrico 60 · Inalámbrico 50 | Script del dashboard Inbound |
| Entel Mesa Técnica | EPA | 65 | Dashboard Mesa Técnica |
| Claro Ecuador (Inbound y Outbound) | Nota de calidad | 85 (umbral crítico 75) | Dashboards Claro |

---

## 4. Cuentas: indicadores y origen de datos

| Cuenta | KPI disponibles | Base (hoja) | Mes según | Plataforma según | Origen del archivo |
|---|---|---|---|---|---|
| **Entel Inbound** · monitoreo | Evaluaciones, Nota de calidad, PEC, PENC, Adherencia | `Adherencias A365 *.xlsx` (Base) | Fecha Envío | Plataforma | Carpeta local · portal sergpp.cl |
| **Entel Inbound** · EPA | Encuestas, EPA, Resolutividad, Satisfacción global | `EPA *.xlsx` (BASE) | Fecha atención | Plataforma ok | Carpeta local · portal Ipsos |
| **Entel Mesa Técnica** · monitoreo | Evaluaciones, Nota de calidad, PENC | `Informe Adh *.xlsx` (Monitoreos) | Fecha Envío | Plataforma | Carpeta local · portal sergpp.cl |
| **Entel Mesa Técnica** · EPA | Encuestas, EPA, Resolutividad, Satisfacción global | `Evolutivo EPA *.xlsx` (BASE) | Mes de medición | Plataforma | Carpeta local · portal Ipsos |
| **Entel C2C** | Evaluaciones, Nota de calidad, PENC, PEC | `Informe Adh *Retenciones*.xlsx` (Matriz) | Fecha de atención | Plataforma | Carpeta local · portal sergpp.cl |
| **Entel Outbound** · monitoreo | Evaluaciones, PENC, PEC | `Reporte monitoreos interno outbound *.xlsx` (Matriz) + descargas diarias "Reporte Pauta Outbound" | Fecha de grabación (o Fecha Envío) | Plataforma | **Google Drive** ENTEL/OUT |
| **Entel Outbound** · EPA | Encuestas, EPA, Satisfacción global | Hoja "Resultados encuesta post atención Móvil A365" (Base Epa Movil) | Fecha Atención | Campaña | **Google Drive** (hoja de Google) |
| **Entel E-commerce** | Evaluaciones, Nota de calidad, PENC, PEC | `Reporte monitoreos Ecommerce *.xlsx` (Matriz) + descargas diarias "Reporte Pauta Ecommerce" | Fecha de grabación (o Fecha Envío) | Plataforma | **Google Drive** ENTEL/E-COMMERCE |
| **Entel Empresas** | Evaluaciones, Nota de calidad | Hoja "CAMPAÑA EMPRESA - NO VENTAS" (una hoja por mes) | Hoja del mes | — (cuenta única) | **Google Drive** (hoja de Google) |
| **Claro Ecuador Inbound** | Evaluaciones, Nota de calidad (COPC), Resolutividad | `Monitoreo Inbound A365 *.xlsx` | Fecha de interacción | Cola (Prepago / Postpago) | **Google Drive** ECUADOR/INBOUND · Qualtrics |
| **Claro Ecuador Outbound** | Evaluaciones, Nota de calidad (COPC), Efectividad | `Monitoreo Outbound A365 *.xlsx` | Fecha de interacción | Segmento (Móvil / Fijo) | **Google Drive** ECUADOR/OUTBOUND · Qualtrics |
| **Claro Ecuador NPS** | — | Sin base conectada | — | — | Solo enlace al dashboard |
| **Claro México** | — | Próximamente | — | — | — |

**Reglas de carga:**
- **Base más reciente:** de Drive se toma el archivo con la fecha más reciente en el nombre ("… - 12.10.xlsx"); de las carpetas locales, el último modificado.
- **Mínimo de casos:** las plataformas con menos de 5 monitoreos o 20 encuestas en el mes no se publican por separado, pero sí suman al total de la cuenta.
- **Filtros propios de cada dashboard:**
  - Claro Inbound excluye asesores de prueba ("xxxxx");
  - Empresas solo cuenta evaluaciones con algún criterio calificado;
  - Claro solo considera evaluaciones finalizadas en Qualtrics.

---

## 5. Estados, colores y símbolos

| Símbolo | Significado |
|---|---|
| 🟢 punto verde | **Cumple**: el valor alcanza la meta |
| 🟡 punto amarillo | **Alerta**: bajo la meta, pero mejor que el umbral crítico |
| 🔴 punto rojo | **Crítico**: igual o peor que el umbral crítico |
| ⚪ punto gris | **Sin meta**: el dashboard no define meta para ese KPI |
| ▲ verde / ▼ rojo | Mejora o empeora frente al mes anterior (en % se expresa en puntos: "pts") |
| ▲ / ▼ gris | Variación de cantidades (evaluaciones, encuestas) |
| "parcial" | Mes en curso: la cantidad todavía no es comparable |
| — | Sin dato para ese KPI o mes |
| ⚠ | 3 o más meses seguidos bajo la meta (en Seguimiento) |
| "(en curso)" | Mes actual en los filtros de mes |

---

## 6. Módulos técnicos (archivos)

| Archivo | Rol |
|---|---|
| `index.html` | Estructura de la página: menú, barra superior, barra inferior del celular y formulario de seguimiento |
| `assets/css/central.css` | Estilos, tema claro/oscuro y adaptación a celular |
| `assets/js/app.js` | Arranque, rutas (`#/general`, `#/kpis`, …) y menú |
| `assets/js/datos.js` | Carga de configuración y datos; formatos; consultas; bitácora de seguimiento |
| `assets/js/componentes.js` | Piezas reutilizables: tarjetas KPI, tablas (con vista de tarjetas en celular), filtros y gráficos |
| `assets/js/general.js` | Vista general, KPI por cuenta, detalle de cuenta y visor de dashboards |
| `assets/js/vistas.js` | Empresa, Seguimiento, Tabla consolidada, Histórico y Calidad de datos |
| `assets/img/` | Logo de A365 (`logo-a365.png`), ícono de la pestaña y del .exe |
| `config/portal.json` | Empresas, países y cuentas, con la URL de su dashboard y repositorio |
| `config/indicadores.json` | Catálogo de KPI: unidad, rango, sentido, metas y alias |
| `config/fuentes.json` | Cómo leer cada base: carpeta o Drive, hoja, columnas, fórmulas y filtros |
| `config/homologacion.json` | Equivalencias de nombres de plataformas |
| `etl/central_etl.py` | Proceso de carga: descarga de Drive, lectura, validación, cálculo, histórico y publicación |
| `etl/validar_dashboards.py` | Compara cada KPI mensual con el valor de su dashboard |
| `etl/perfiles.py` | Contraseñas, cifrado de los datos por perfil, respaldo cifrado e importación del seguimiento |
| `config/perfiles.json` | Perfiles y qué cuentas ve cada uno (sin contraseñas) |
| `config/perfiles.local.json` | Contraseñas de los perfiles; solo en el PC del administrador, no se publica |
| `data/seguro/` | Paquetes cifrados por perfil y respaldo cifrado: lo único que se publica de los datos |
| `etl/tests/` | Pruebas automáticas del proceso de carga |
| `actualizar_central.bat` | Ejecuta la carga y la validación (doble clic) |
| `data/consolidado.json` | Datos en claro (solo en el PC); la página usa la versión cifrada de `data/seguro/` |
| `data/historico/mediciones.csv` | Histórico completo con versiones (nunca se borra) |
| `data/cargas/` | Registro de cargas, errores y validación |
| `data/seguimiento.json` | Bitácora oficial de acciones |
| `data/chatbot/contexto.json` | Resumen autorizado para un futuro asistente |

**Actualización de los datos:**
1. Los programas de cada dashboard descargan sus bases.
2. Se ejecuta `actualizar_central.bat`, que descarga lo de Drive, procesa y valida.
3. Se hace el commit y el push de `data/`, y GitHub Pages publica en 1 a 5 minutos.

---

## 7. Glosario

| Término | Definición |
|---|---|
| **COPC** | Estándar de calidad para centros de contacto; en Claro da nombre a la nota que se anula con un error crítico |
| **EPA** | Encuesta Post Atención |
| **FCR** | First Contact Resolution: resolución en el primer contacto |
| **PEC / PENC** | Puntaje de Errores Críticos / No Críticos de la pauta |
| **ID Pauta** | Identificador único de cada monitoreo en las bases de Entel |
| **Pauta** | Formulario con que se evalúa una llamada |
| **Brecha** | Diferencia entre el valor y la meta (positiva = mejor que la meta) |
| **Umbral crítico** | Límite bajo la meta desde el cual el estado pasa a *Crítico* |
| **Validación cruzada** | Comprobación automática de que cada KPI coincide con el de su dashboard |
