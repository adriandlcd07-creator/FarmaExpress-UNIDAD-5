"""Pruebas parametrizadas desde data/casos_de_prueba.csv (csv.DictReader)."""

import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.domain import DomainException, Receta, Venta

HOY = date(2026, 10, 16)
RUTA = Path(__file__).resolve().parent.parent / "data" / "casos_de_prueba.csv"


def _casos():
    with RUTA.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("caso", _casos(), ids=lambda c: c["caso_id"])
def test_caso_desde_csv(caso, service, make_cmd):
    esperado = caso["resultado_esperado"]

    if caso["accion"] == "confirmar_dos_veces":
        venta = Venta("V", "T", "S001", "CAJ-01")
        venta.agregar_detalle("P100", caso["lote"], 1, float(caso["precio"]), False)
        venta.confirmar_venta()
        with pytest.raises(DomainException):
            venta.confirmar_venta()
        return

    receta = None
    if caso["dias_receta"]:
        emision = HOY - timedelta(days=int(caso["dias_receta"]))
        receta = Receta("R-1", "Dr. X", "CED-1", "Paciente", emision)
    cmd = make_cmd(
        numero_lote=caso["lote"],
        cantidad=int(caso["cantidad"]),
        precio_unitario=float(caso["precio"]),
        es_controlado=caso["controlado"] == "1",
        receta=receta,
    )

    if esperado.startswith("OK"):
        evento = service.registrar_venta(cmd, HOY)
        assert evento.total == pytest.approx(float(esperado.split()[1]))
    else:
        with pytest.raises(DomainException):
            service.registrar_venta(cmd, HOY)
