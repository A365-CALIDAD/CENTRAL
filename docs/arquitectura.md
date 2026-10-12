# Arquitectura de CENTRAL

## 1. Principios

1. **Los dashboards existentes no se tocan.** Cada uno sigue en su organización, repositorio y URL de GitHub Pages. CENTRAL solo los *enlaza* desde `config/portal.json`.
2. **Configuración antes que código.** Agregar empresa, país, dashboard, indicador o fuente de Excel = editar un JSON de `config/`.
3. **Sitio estático.** El portal es HTML + CSS + JavaScript (módulos ES) sin build ni servidor. Los datos llegan como JSON generados por el ETL.
4. **Histórico inmutable.** El ETL nunca borra mediciones: versiona y deja trazabilidad de cada carga.

## 2. Capas

```
 Excel por empresa/país ──► ETL Python (pandas) ──► data/historico/mediciones.csv  (fuente de verdad)
  etl/entrada/<fuente>/      validar · homologar    data/cargas/registro_cargas.csv (bitácora de cargas)
                             deduplicar · versionar data/cargas/errores/*.csv       (reporte de errores)
                                       │
                                       ▼ publicar
                             data/consolidado.json   ──► Portal CENTRAL (GitHub Pages)
                             data/cargas/resumen.json      ├─ Panel general
                             data/chatbot/contexto.json    ├─ Entel Chile / Claro Ecuador / Claro México
                             data/seguimiento.json         ├─ Seguimiento · Tabla consolidada · Histórico
                                                           ├─ Calidad de datos
 config/portal.json  ── enlaces ──────────────────────────►└─ Dashboards externos (repos independientes)
```

| Capa | Ubicación | Responsabilidad |
|---|---|---|
| Configuración | `config/portal.json` | Empresas, países, estado (activo/próximamente) y dashboards con URL y repo |
| | `config/indicadores.json` | Catálogo maestro: unidad, rango válido, sentido, meta, umbral crítico, alias |
| | `config/fuentes.json` | Cómo leer cada Excel: carpeta, hoja, formato ancho/largo, mapeo de columnas |
| | `config/homologacion.json` | Equivalencias de nombres de cuentas |
| ETL | `etl/central_etl.py` | Lectura, validación, homologación, consolidación, histórico, publicación |
| Datos | `data/` | Salidas del ETL, versionadas en Git |
| Frontend | `index.html`, `assets/` | SPA con rutas por hash, componentes reutilizables, Chart.js |

## 3. Modelo de datos

Medición canónica (formato largo, una fila por indicador):

| Campo | Descripción |
|---|---|
| `empresa_id`, `pais_id` | Deben existir en `portal.json` |
| `cuenta` | Normalizada en mayúsculas y homologada |
| `indicador_id` | Id del catálogo (los alias del Excel se traducen) |
| `periodo` | `YYYY-MM` |
| `fecha_medicion`, `valor`, `meta_archivo`, `muestras` | Datos de la medición |
| `fuente_id`, `archivo`, `archivo_hash`, `carga_id`, `fecha_carga` | Trazabilidad |
| `version`, `vigente` | Versionado; solo una versión vigente por clave |

**Clave única:** `empresa_id + pais_id + cuenta + indicador_id + periodo`.

**Estado** (lo calcula el ETL al publicar): `OK` (cumple meta), `ALERTA` (no cumple, sin llegar al umbral), `CRITICO` (igual o peor que el umbral), `SIN_META`. Respeta el sentido del indicador (en TMO, menor es mejor). Prioridad de la meta: la del archivo › `metas_por_empresa` › catálogo.

## 4. Reglas del ETL

| Situación | Resultado |
|---|---|
| Columna obligatoria ausente | Archivo rechazado (`COLUMNA_FALTANTE`) |
| Celda vacía obligatoria | Fila rechazada (`VALOR_FALTANTE`) |
| Texto en campo numérico / fecha ilegible | `TIPO_INVALIDO` / `FECHA_INVALIDA` |
| Indicador no reconocido | `INDICADOR_DESCONOCIDO` (agregar alias al catálogo) |
| Valor fuera del rango del indicador | `FUERA_DE_RANGO` |
| Porcentajes 0–1 | Se escalan a 0–100 automáticamente (`escala_porcentaje: auto`) |
| Clave repetida en el mismo archivo | Se conserva la primera (`DUPLICADO_EN_ARCHIVO`) |
| Mismo archivo procesado otra vez (hash SHA-256) | Se omite (`OMITIDO_YA_PROCESADO`) |
| Misma clave y mismo valor que el histórico | Se ignora (duplicada) |
| Valor distinto, periodo en curso | Nueva versión; la anterior queda `vigente=0` |
| Valor distinto, periodo cerrado | `CONFLICTO_HISTORICO`, no se sobrescribe. Con `--permitir-correcciones` se versiona |

## 4.1 Conexión con las bases de los dashboards

CENTRAL lee directamente las mismas bases que usan los scripts `actualizar_dashboard.py` / `actualizar_bi.py` de cada dashboard, en sus carpetas originales (`C:\A365\ENTEL\...`, `C:\A365\CLARO\...`), sin copiarlas ni modificarlas. Se configuran en `config/fuentes.json` con `formato: "detalle"`:

```json
{
  "id": "entel_in_epa",
  "carpeta": "../ENTEL/ENTEL_BI_IN/Reporte EPA",   // relativa a CENTRAL
  "patron": "EPA*.xls*", "hoja": "BASE",
  "seleccion": "mas_reciente",                     // la base es acumulada: basta la última
  "politica_cambios": "versionar",                 // una descarga nueva puede ajustar meses anteriores
  "formato": "detalle", "min_muestras": 20,
  "columnas": { "fecha": ["Fecha atención"], "cuenta": ["Plataforma ok"] },
  "filtros": [ { "columna": "Finished", "incluir": ["True"] } ],
  "indicadores_detalle": [
    { "indicador": "epa", "columna": "EPA", "agregacion": "promedio", "metas_por_cuenta": { "Fibra": 66 } },
    { "indicador": "fcr", "columna": "Resolutividad", "agregacion": "porcentaje", "positivos": [1], "negativos": [2] }
  ]
}
```

- `promedio`: media de la columna por cuenta y mes (notas, EPA recodificada 0/100).
- `porcentaje`: % de casos con valor en `positivos` (SI/NO, 1/2).
- Las cuentas con menos de `min_muestras` casos en el mes se descartan y quedan en el reporte de errores.
- Si dos fuentes informan la misma cuenta e indicador, la segunda se rechaza (`CONFLICTO_FUENTES`).
- Como lee carpetas locales, el ETL corre en el PC donde están las bases (igual que los scripts actuales), y luego se publica `data/` con Git.

Reglas copiadas de los scripts de los dashboards:

- `id_unico: "ID Pauta"`: un monitoreo repetido se cuenta una vez (Inbound conserva el último, Mesa Técnica el primero).
- `complementos`: Outbound y E-commerce suman a la base histórica las descargas diarias "Reporte Pauta …" sin repetir ID Pauta, igual que su `actualizar_dashboard.py`.
- `conteo`: cada fuente publica la cantidad de evaluaciones o encuestas por servicio, cuenta y mes (tabla de la Vista general).

Estado de conexión (12/10/2026). Cada servicio es un dashboard de `config/portal.json` (`linea_id`):

| Servicio | Base | En CENTRAL |
|---|---|---|
| Entel · Inbound | `ENTEL_BI_IN/Adherencias/Adherencias*.xlsx` (Base) · `Reporte EPA/EPA*.xlsx` (BASE) | Evaluaciones, nota de calidad, adherencia · encuestas, EPA (meta por plataforma), resolutividad, satisfacción global |
| Entel · Mesa Técnica | `ENTEL_BI_MT/Adherencias/Informe Adh*.xlsx` (Monitoreos) · `Reporte EPA/Evolutivo EPA*.xlsx` (BASE) | Evaluaciones, nota, adherencia, PENC · encuestas, EPA, resolutividad, global |
| Entel · C2C | `ENTEL_BI_CZC/Adherencias/Informe Adh*Retenciones*.xlsx` (Matriz) | Evaluaciones, nota, adherencia, PENC, PEC |
| Entel · Outbound | `ENTEL_BI_OUT/Adherencias/Reporte monitoreos interno outbound*.xlsx` + `Reporte Pauta Outbound*` · `BI/Descargas/EPA_drive.xlsx` | Evaluaciones, PENC, PEC · encuestas, satisfacción global (la EPA del dashboard aún no se replica) |
| Entel · E-commerce | `ENTEL_BI_EC/Adherencias/Reporte monitoreos Ecommerce*.xlsx` + `Reporte Pauta Ecommerce*` | Evaluaciones, nota, PENC, PEC |
| Entel · Empresas | `ENTEL_BI_EMP/Descargas/CAMPAÑA EMPRESA*.xlsx` (una hoja por mes) | Evaluaciones, nota |
| Claro EC · Inbound | `CLARO_IN/filtrado/*.xlsx` | Evaluaciones, FCR (la nota con pesos por bloque aún no se replica) |
| Claro EC · Outbound | `CLARO_OUT/filtrado/*.xlsx` | Evaluaciones, efectividad de venta (nota pendiente) |
| Claro EC · NPS | Sin base local (solo el HTML publicado) | Solo enlace al dashboard |

Validación: los conteos mensuales de Outbound coinciden exactamente con los datos del `index.html` local del dashboard generado con los mismos archivos.

## 5. Seguimiento (observaciones, acciones, responsables)

GitHub Pages es estático y no puede guardar datos. Diseño actual:

- `data/seguimiento.json` es la bitácora oficial versionada en Git.
- En el portal se registran acciones como **borrador local** del navegador y se exportan como `seguimiento.json` para subirlo al repo.

Evolución recomendada cuando se necesite edición multiusuario: una API ligera (por ejemplo Azure Functions, Cloudflare Workers o Supabase) con autenticación, que reemplace la carga de `data/seguimiento.json` en `assets/js/datos.js` (función `cargar`) y `guardarAccion`.

## 6. Seguridad y privacidad (importante)

- Un sitio de GitHub Pages es **público en Internet** aunque el repositorio sea privado, salvo en GitHub Enterprise Cloud con visibilidad privada de Pages. Además, publicar Pages desde un repo privado requiere plan GitHub Team/Enterprise.
- Por eso `data/` solo contiene **indicadores agregados por cuenta**, sin datos personales (RUT, teléfonos, nombres de ejecutivos). Los Excel de entrada están en `.gitignore`.
- Si los resultados por cuenta son confidenciales, las opciones son: Pages privado (Enterprise Cloud), Cloudflare Pages + Cloudflare Access, o Azure Static Web Apps con autenticación.

## 7. Preparación para chatbot

- `data/chatbot/contexto.json`: resumen autorizado por empresa/país/indicador del último periodo (promedio, cuentas críticas y en alerta) + catálogo de indicadores.
- `data/consolidado.json`: detalle con esquema documentado en el propio archivo.
- Flujo previsto: el chatbot recibe la pregunta, filtra el consolidado según los permisos del usuario (empresa/país) y responde citando periodo y fuente. La API de LLM debe llamarse desde un backend (nunca exponer la clave en el frontend). Los repos de Entel ya tienen una carpeta `chatbot_ia` que puede reutilizar este contexto.

## 8. Cómo extender

| Quiero… | Editar |
|---|---|
| Agregar un dashboard | `config/portal.json` → `dashboards[]` del país (completar `url` y `repo`) |
| Activar Claro México | `config/portal.json` → `estado: "activo"` + dashboards; `config/fuentes.json` → nueva fuente con `empresa_id: "claro"`, `pais_id: "mx"` |
| Agregar una empresa/país | `config/portal.json` → nueva empresa o país |
| Agregar un indicador o alias | `config/indicadores.json` |
| Leer un nuevo formato de Excel | `config/fuentes.json` (copiar `plantilla_nueva_fuente`) |
| Unificar nombres de cuentas | `config/homologacion.json` |
