from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.application import RegistrarVentaCommand, VentaApplicationService
from src.domain import ExistenciaDeProducto, Lote, Receta
from src.repository import (
    Base,
    InMemoryExistenciaRepository,
    InMemoryUnitOfWork,
    InMemoryVentaRepository,
)

HOY = date(2026, 10, 16)


@pytest.fixture
def hoy():
    return HOY


@pytest.fixture
def repos():
    return (
        InMemoryVentaRepository(),
        InMemoryExistenciaRepository(),
        InMemoryUnitOfWork(),
    )


def _inventario():
    return ExistenciaDeProducto(
        "EX-001",
        "P100",
        "S001",
        [
            Lote("LOTE-001", date(2027, 5, 1), 50),
            Lote("LOTE-VENCIDO", date(2026, 1, 1), 20),
            Lote("LOTE-HOY", HOY, 10),
        ],
    )


@pytest.fixture
def service(repos):
    venta_repo, existencia_repo, uow = repos
    existencia_repo.guardar(_inventario())
    return VentaApplicationService(venta_repo, existencia_repo, uow)


@pytest.fixture
def receta_valida():
    return Receta("REC-8899", "Dr. Carlos Gómez", "CED-12345", "Juan Pérez", date(2026, 10, 11))


@pytest.fixture
def make_cmd():
    def _make(**kw):
        base = {
            "id_venta": "V-101",
            "folio_ticket": "TICK-001",
            "sucursal_id": "S001",
            "cajero_id": "CAJ-01",
            "producto_id": "P100",
            "numero_lote": "LOTE-001",
            "cantidad": 5,
            "precio_unitario": 150.0,
            "es_controlado": False,
        }
        base.update(kw)
        return RegistrarVentaCommand(**base)

    return _make


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
