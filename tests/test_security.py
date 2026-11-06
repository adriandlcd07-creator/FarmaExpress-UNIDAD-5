from datetime import datetime, timedelta

import pytest

from src.security import (
    CAJERO,
    RESPONSABLE,
    Actor,
    puede_autorizar_excepcion,
    puede_cancelar_venta,
)

CREADA = datetime(2026, 10, 15, 10, 0)
RESP = Actor("RESP-01", RESPONSABLE)
DUENO = Actor("CAJ-01", CAJERO)
TERCERO = Actor("CAJ-02", CAJERO)


def _can(actor, estado="CONFIRMADA", caja=True, horas=1.0):
    return puede_cancelar_venta(
        estado, actor, "CAJ-01", caja, CREADA, CREADA + timedelta(hours=horas)
    )


@pytest.mark.parametrize(
    "actor,estado,caja,horas,esperado",
    [
        (RESP, "CONFIRMADA", True, 100, True),  # responsable sin límite de tiempo
        (DUENO, "CONFIRMADA", True, 1, True),  # dueño dentro de 24 h
        (DUENO, "CONFIRMADA", True, 23.99, True),  # justo antes del límite
        (DUENO, "CONFIRMADA", True, 24, False),  # exactamente 24 h -> rechazo
        (DUENO, "CONFIRMADA", True, 30, False),  # fuera de ventana
        (TERCERO, "CONFIRMADA", True, 1, False),  # cajero ajeno
        (RESP, "CONFIRMADA", False, 1, False),  # caja cerrada, ni responsable
        (DUENO, "CONFIRMADA", False, 1, False),  # caja cerrada
        (RESP, "CANCELADA", True, 1, False),  # ya cancelada
    ],
)
def test_matriz_autorizacion_cancelacion(actor, estado, caja, horas, esperado):
    assert _can(actor, estado, caja, horas) is esperado


def test_solo_responsable_autoriza_excepciones():
    assert puede_autorizar_excepcion(RESPONSABLE) is True
    assert puede_autorizar_excepcion(CAJERO) is False
    assert puede_autorizar_excepcion(None) is False
