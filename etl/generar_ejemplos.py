"""
Genera archivos Excel FICTICIOS para probar el ETL de punta a punta.

    python etl/generar_ejemplos.py

Crea etl/entrada/demo_entel_cl/*.xlsx (formato ancho, un archivo por mes) y
etl/entrada/demo_claro_ec/claro_ec_resultados.xlsx (formato largo). Incluye a
propósito algunos errores (indicador desconocido, valor vacío, texto, fila
duplicada) para ver el reporte de calidad de datos.
"""
import random
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PERIODOS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
MESES_TXT = {"04": "abr", "05": "may", "06": "jun", "07": "jul", "08": "ago", "09": "sep"}

CUENTAS_ENTEL = ["Retenciones", "Mesa Técnica Hogar", "Inbound Móvil", "Outbound Ventas", "Ecommerce", "C2C"]
CUENTAS_CLARO = ["Postpago", "Prepago", "Hogar", "Corporativo", "Soporte Técnico"]


def paseo(rng, base, paso, lo, hi, n):
    v, out = base, []
    for _ in range(n):
        v = min(hi, max(lo, v + rng.uniform(-paso, paso)))
        out.append(v)
    return out


def main():
    rng = random.Random(365)
    d_entel = RAIZ / "etl" / "entrada" / "demo_entel_cl"
    d_claro = RAIZ / "etl" / "entrada" / "demo_claro_ec"
    d_entel.mkdir(parents=True, exist_ok=True)
    d_claro.mkdir(parents=True, exist_ok=True)

    series = {c: {"NPS": paseo(rng, rng.uniform(15, 55), 7, -20, 80, 6),
                  "CSAT": paseo(rng, rng.uniform(72, 92), 3, 50, 99, 6),
                  "Resolutividad": paseo(rng, rng.uniform(60, 85), 4, 40, 97, 6),
                  "TMO": paseo(rng, rng.uniform(330, 560), 35, 200, 800, 6)} for c in CUENTAS_ENTEL}
    for k, per in enumerate(PERIODOS):
        filas = []
        for c in CUENTAS_ENTEL:
            s = series[c]
            fraccion = per == "2026-06"          # un mes llega con % en formato 0-1
            filas.append({
                "Fecha": pd.Timestamp(f"{per}-28"),
                "Cuenta": c.upper() if k % 2 else c,   # mayúsculas/minúsculas mezcladas
                "NPS": round(s["NPS"][k], 1),
                "CSAT": round(s["CSAT"][k] / (100 if fraccion else 1), 4),
                "Resolutividad": round(s["Resolutividad"][k] / (100 if fraccion else 1), 4),
                "TMO": round(s["TMO"][k]),
                "Muestras": rng.randint(80, 600),
            })
        if per == "2026-09":
            filas.append(dict(filas[0]))                       # fila duplicada
            filas.append({**filas[1], "Cuenta": "", "Fecha": pd.Timestamp("2026-09-28")})  # cuenta vacía
            filas[2]["CSAT"] = "sin dato"                      # texto en columna numérica
        pd.DataFrame(filas).to_excel(d_entel / f"entel_cl_{per}.xlsx", index=False)

    filas = []
    for c in CUENTAS_CLARO:
        nps = paseo(rng, rng.uniform(10, 50), 8, -30, 80, 6)
        epa = paseo(rng, rng.uniform(68, 90), 4, 40, 99, 6)
        cal = paseo(rng, rng.uniform(80, 95), 3, 50, 100, 6)
        for k, per in enumerate(PERIODOS):
            a, m = per.split("-")
            txt = f"{MESES_TXT[m]}-{a}"
            filas += [
                {"Periodo": txt, "Servicio": c, "Indicador": "NPS", "Resultado": round(nps[k], 1), "Encuestas": rng.randint(50, 400)},
                {"Periodo": txt, "Servicio": c, "Indicador": "EPA", "Resultado": f"{epa[k]:.1f}%".replace(".", ","), "Encuestas": rng.randint(50, 400)},
                {"Periodo": txt, "Servicio": c, "Indicador": "Nota Calidad", "Resultado": round(cal[k], 1), "Encuestas": rng.randint(20, 120)},
            ]
    filas.append({"Periodo": "sep-2026", "Servicio": "Hogar", "Indicador": "Recontacto 48h", "Resultado": 12.5, "Encuestas": 90})
    filas.append({"Periodo": "sep-2026", "Servicio": "Prepago", "Indicador": "NPS", "Resultado": None, "Encuestas": 0})
    filas.append({"Periodo": "13-2026", "Servicio": "Hogar", "Indicador": "NPS", "Resultado": 30, "Encuestas": 10})
    with pd.ExcelWriter(d_claro / "claro_ec_resultados.xlsx") as w:
        pd.DataFrame(filas).to_excel(w, sheet_name="Resultados", index=False)
    print(f"Ejemplos generados en {d_entel.relative_to(RAIZ)} y {d_claro.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
