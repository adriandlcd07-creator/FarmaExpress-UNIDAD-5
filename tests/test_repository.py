from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.application import VentaApplicationService
from src.domain import ExistenciaDeProducto, Lote, Venta
from src.repository import (
    SqlExistenciaRepository,
    SqlUnitOfWork,
    SqlVentaRepository,
)


def _venta(id_venta="V-1", folio="T-1"):
    v = Venta(id_venta, folio, "S001", "CAJ-01", datetime(2026, 10, 16, 9, 0))
    v.agregar_detalle("P100", "L1", 2, 120.0, False)
    return v


def test_repository_commit(session):
    repo = SqlVentaRepository(session)
    repo.agregar(_venta())
    session.commit()
    leida = repo.obtener("V-1")
    assert leida.total == 240.0
    assert leida.estado == "REGISTRADA"
    assert leida.detalles[0].numero_lote == "L1"


def test_repository_rollback(session):
    repo = SqlVentaRepository(session)
    repo.agregar(_venta())
    session.rollback()
    assert repo.obtener("V-1") is None


def test_folio_ticket_duplicado_viola_unicidad(session):
    repo = SqlVentaRepository(session)
    repo.agregar(_venta("V-1", "T-DUP"))
    session.commit()
    with pytest.raises(IntegrityError):
        repo.agregar(_venta("V-2", "T-DUP"))
        session.commit()
    session.rollback()


def test_guardar_de_nuevo_no_duplica_detalles(session):
    repo = SqlVentaRepository(session)
    venta = _venta()
    repo.agregar(venta)
    session.commit()
    venta.cancelar("RESP-01")
    repo.agregar(venta)
    session.commit()
    leida = repo.obtener("V-1")
    assert leida.estado == "CANCELADA"
    assert len(leida.detalles) == 1


def test_existencia_se_persiste_y_se_reconstruye(session):
    repo = SqlExistenciaRepository(session)
    repo.guardar(
        ExistenciaDeProducto(
            "E", "P100", "S001", [Lote("L1", date(2027, 1, 1), 10, bloqueado=True)]
        )
    )
    session.commit()
    ex = repo.obtener_por_producto_y_sucursal("P100", "S001")
    assert ex.lotes[0].cantidad == 10
    assert ex.lotes[0].bloqueado is True
    assert repo.obtener_por_producto_y_sucursal("P999", "S001") is None


def test_servicio_con_sqlite_hace_commit_real(session, make_cmd):
    ex_repo = SqlExistenciaRepository(session)
    ex_repo.guardar(
        ExistenciaDeProducto("E", "P100", "S001", [Lote("LOTE-001", date(2027, 5, 1), 50)])
    )
    session.commit()
    svc = VentaApplicationService(SqlVentaRepository(session), ex_repo, SqlUnitOfWork(session))
    svc.registrar_venta(make_cmd(), date(2026, 10, 16))
    session.expire_all()
    assert SqlVentaRepository(session).obtener("V-101").total == 750.0
    ex = ex_repo.obtener_por_producto_y_sucursal("P100", "S001")
    assert ex.lotes[0].cantidad == 45


def test_servicio_con_sqlite_hace_rollback_ante_error(session, make_cmd):
    ex_repo = SqlExistenciaRepository(session)
    ex_repo.guardar(
        ExistenciaDeProducto("E", "P100", "S001", [Lote("LOTE-001", date(2027, 5, 1), 50)])
    )
    session.commit()
    svc = VentaApplicationService(SqlVentaRepository(session), ex_repo, SqlUnitOfWork(session))
    with pytest.raises(Exception, match="controlado exige receta"):
        svc.registrar_venta(make_cmd(es_controlado=True), date(2026, 10, 16))
    assert SqlVentaRepository(session).obtener("V-101") is None
    assert ex_repo.obtener_por_producto_y_sucursal("P100", "S001").lotes[0].cantidad == 50
