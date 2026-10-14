"""Pruebas del ETL. Ejecutar desde la raíz:  python -m unittest discover -s etl/tests -v"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import central_etl as etl  # noqa: E402


class Conversiones(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(etl.a_numero("85,3%"), 85.3)
        self.assertEqual(etl.a_numero("1.234,5"), 1234.5)
        self.assertEqual(etl.a_numero("1,234.5"), 1234.5)
        self.assertEqual(etl.a_numero(0.853), 0.853)
        self.assertIsNone(etl.a_numero("sin dato"))
        self.assertIsNone(etl.a_numero(float("nan")))

    def test_periodos(self):
        self.assertEqual(etl.a_periodo("sep-2026"), "2026-09")
        self.assertEqual(etl.a_periodo("Septiembre 2026"), "2026-09")
        self.assertEqual(etl.a_periodo("09/2026"), "2026-09")
        self.assertEqual(etl.a_periodo("2026-09"), "2026-09")
        self.assertEqual(etl.a_periodo(pd.Timestamp("2026-09-15")), "2026-09")
        self.assertIsNone(etl.a_periodo("13-2026"))

    def test_normalizar(self):
        self.assertEqual(etl.normalizar("  Resolución   Primer-Contacto "), "resolucion primer contacto")


class Estados(unittest.TestCase):
    def setUp(self):
        self.cat = etl.Catalogo()

    def test_mayor_es_mejor(self):
        self.assertEqual(self.cat.estado(90, 85, 75, "csat"), "OK")
        self.assertEqual(self.cat.estado(80, 85, 75, "csat"), "ALERTA")
        self.assertEqual(self.cat.estado(70, 85, 75, "csat"), "CRITICO")

    def test_menor_es_mejor(self):
        self.assertEqual(self.cat.estado(400, 420, 540, "tmo"), "OK")
        self.assertEqual(self.cat.estado(500, 420, 540, "tmo"), "ALERTA")
        self.assertEqual(self.cat.estado(600, 420, 540, "tmo"), "CRITICO")

    def test_sin_meta(self):
        self.assertEqual(self.cat.estado(1, None, None, "csat"), "SIN_META")


class Historico(unittest.TestCase):
    META = {"fuente_id": "t", "archivo": "a.xlsx", "archivo_hash": "h", "carga_id": "c1", "fecha_carga": "x"}

    def med(self, periodo, valor):
        return {"fila": 2, "empresa_id": "entel", "pais_id": "cl", "linea_id": "entel-in", "cuenta": "X", "indicador_id": "nps",
                "periodo": periodo, "fecha_medicion": f"{periodo}-01", "valor": valor,
                "meta_archivo": None, "muestras": 10}

    def integrar(self, hist, meds, abierto="2026-10", corregir=False):
        err = etl.Errores("c", "t", "a.xlsx")
        h, cont = etl.integrar(hist, meds, self.META, err, abierto, corregir)
        return h, cont, err

    def test_nuevo_duplicado_conflicto_y_version(self):
        h = pd.DataFrame(columns=etl.COLS_HISTORICO)
        h, c, _ = self.integrar(h, [self.med("2026-09", 30)])
        self.assertEqual(c["nuevas"], 1)

        h, c, _ = self.integrar(h, [self.med("2026-09", 30)])
        self.assertEqual(c["duplicadas"], 1)
        self.assertEqual(len(h), 1)

        h, c, err = self.integrar(h, [self.med("2026-09", 35)])       # periodo cerrado
        self.assertEqual(c["conflictos"], 1)
        self.assertEqual(err.filas[0]["tipo_error"], "CONFLICTO_HISTORICO")
        self.assertEqual(len(h), 1)

        h, c, _ = self.integrar(h, [self.med("2026-09", 35)], corregir=True)
        self.assertEqual(c["versionadas"], 1)
        self.assertEqual(list(h["vigente"]), ["0", "1"])              # nada se borra
        self.assertEqual(list(h["version"]), ["1", "2"])

    def test_periodo_abierto_versiona_sin_flag(self):
        h = pd.DataFrame(columns=etl.COLS_HISTORICO)
        h, _, _ = self.integrar(h, [self.med("2026-10", 30)])
        h, c, _ = self.integrar(h, [self.med("2026-10", 31)])
        self.assertEqual(c["versionadas"], 1)


if __name__ == "__main__":
    unittest.main()


class Perfiles(unittest.TestCase):
    def test_cifrado_ida_y_vuelta(self):
        import perfiles as P
        sobre = P.cifrar(b'{"ok": 1}', "Clave-de-prueba-9")
        self.assertEqual(P.descifrar(sobre, "Clave-de-prueba-9"), b'{"ok": 1}')
        with self.assertRaises(Exception):
            P.descifrar(sobre, "otra-clave")

    def test_paquete_de_cuenta_solo_trae_su_cuenta(self):
        import perfiles as P
        cons = {"registros": [{"l": "entel-c2c", "v": 1}, {"l": "entel-in", "v": 2}]}
        seg = [{"id": "a", "linea_id": "entel-c2c"}, {"id": "b", "linea_id": "entel-in"}]
        p = P._paquete({"id": "entel-c2c", "nombre": "C2C", "lineas": ["entel-c2c"]}, cons, {"x": 1}, {"y": 1}, seg)
        self.assertEqual([r["l"] for r in p["consolidado"]["registros"]], ["entel-c2c"])
        self.assertEqual([a["id"] for a in p["seguimiento"]["acciones"]], ["a"])
        self.assertIsNone(p["resumen"])
        self.assertIsNone(p["validacion"])
        admin = P._paquete({"id": "admin", "nombre": "Admin", "admin": True}, cons, {"x": 1}, {"y": 1}, seg)
        self.assertEqual(len(admin["consolidado"]["registros"]), 2)
        self.assertIsNotNone(admin["resumen"])

    def test_claves_generadas_son_fuertes(self):
        import perfiles as P
        c = P.generar_clave()
        self.assertGreaterEqual(len(c), 14)
        self.assertTrue(any(x.isdigit() for x in c) and any(x.isupper() for x in c) and any(x.islower() for x in c))
