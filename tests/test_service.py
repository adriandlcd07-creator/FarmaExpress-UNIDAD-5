from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest

from src.application import (
    AutorizacionDenegada,
    PagoNoDisponible,
    PagoRechazado,
    VentaApplicationService,
)
from src.domain import AutorizacionDeExcepcion, DomainException, Receta
from src.security import CAJERO, RESPONSABLE, Actor

HOY = date(2026, 10, 16)


def _stock(repos, lote="LOTE-001"):
    ex = repos[1].obtener_por_producto_y_sucursal("P100", "S001")
    return next(x for x in ex.lotes if x.numero_lote == lote).cantidad


def _con_pasarela(repos, pasarela):
    return VentaApplicationService(repos[0], repos[1], repos[2], pasarela)


# ---------- CU-01 Registrar venta ----------
def test_01_venta_controlado_con_receta_valida(service, repos, make_cmd, receta_valida):
    evento = service.registrar_venta(make_cmd(es_controlado=True, receta=receta_valida), HOY)
    assert evento.folio_ticket == "TICK-001"
    assert evento.total == 750.0
    assert repos[2].committed
    assert _stock(repos) == 45


def test_02_rechazo_controlado_sin_receta_y_rollback(service, repos, make_cmd):
    with pytest.raises(DomainException, match="controlado exige receta"):
        service.registrar_venta(make_cmd(es_controlado=True, cantidad=2), HOY)
    assert repos[2].rolled_back and not repos[2].committed
    assert _stock(repos) == 50


def test_03_lote_vencido(service, repos, make_cmd, receta_valida):
    cmd = make_cmd(numero_lote="LOTE-VENCIDO", es_controlado=True, receta=receta_valida)
    with pytest.raises(DomainException, match="bloqueado o vencido"):
        service.registrar_venta(cmd, HOY)
    assert repos[2].rolled_back


def test_04_recall_bloquea_ventas_posteriores(service, repos, make_cmd, receta_valida):
    service.ejecutar_recall("P100", "LOTE-001", "Alerta COFEPRIS", ["S001"])
    cmd = make_cmd(es_controlado=True, receta=receta_valida, cantidad=1)
    with pytest.raises(DomainException, match="bloqueado o vencido"):
        service.registrar_venta(cmd, HOY)


def test_producto_no_disponible_en_sucursal(service, make_cmd):
    with pytest.raises(DomainException, match="Producto no disponible"):
        service.registrar_venta(make_cmd(sucursal_id="S999"), HOY)


def test_lote_que_caduca_hoy_se_rechaza(service, make_cmd):
    with pytest.raises(DomainException, match="bloqueado o vencido"):
        service.registrar_venta(make_cmd(numero_lote="LOTE-HOY", cantidad=1), HOY)


def test_vender_exactamente_todo_el_stock(service, repos, make_cmd):
    service.registrar_venta(make_cmd(cantidad=50), HOY)
    assert _stock(repos) == 0


def test_stock_insuficiente_no_modifica_inventario(service, repos, make_cmd):
    with pytest.raises(DomainException, match="Stock insuficiente"):
        service.registrar_venta(make_cmd(cantidad=51), HOY)
    assert _stock(repos) == 50


def test_receta_vencida_rechaza_venta(service, make_cmd):
    vieja = Receta("R", "Dr", "C", "P", date(2026, 9, 1))
    with pytest.raises(DomainException, match="vencida"):
        service.registrar_venta(make_cmd(es_controlado=True, receta=vieja), HOY)


# ---------- CU-02 Excepciones ----------
def _excepcion():
    return AutorizacionDeExcepcion(
        "RESP-01", "Tratamiento oncológico urgente", datetime(2026, 10, 16)
    )


def test_excepcion_autorizada_por_responsable_permite_venta(service, make_cmd):
    cmd = make_cmd(es_controlado=True, excepcion=_excepcion(), rol_autorizador=RESPONSABLE)
    assert service.registrar_venta(cmd, HOY).total == 750.0


def test_excepcion_por_cajero_es_denegada(service, repos, make_cmd):
    cmd = make_cmd(es_controlado=True, excepcion=_excepcion(), rol_autorizador=CAJERO)
    with pytest.raises(AutorizacionDenegada):
        service.registrar_venta(cmd, HOY)
    assert repos[2].rolled_back
    assert _stock(repos) == 50


# ---------- Pasarela de pago (mock, sin cobros reales) ----------
def test_pago_aprobado(service, repos, make_cmd):
    pasarela = Mock()
    pasarela.cobrar.return_value = True
    svc = _con_pasarela(repos, pasarela)
    evento = svc.registrar_venta(make_cmd(pago_con_tarjeta=True), HOY)
    assert evento.total == 750.0
    pasarela.cobrar.assert_called_once_with(750.0, "TICK-001")
    assert _stock(repos) == 45


def test_pago_rechazado_no_descuenta_stock_ni_confirma(service, repos, make_cmd):
    pasarela = Mock()
    pasarela.cobrar.return_value = False
    svc = _con_pasarela(repos, pasarela)
    with pytest.raises(PagoRechazado, match="payment rejected"):
        svc.registrar_venta(make_cmd(pago_con_tarjeta=True), HOY)
    pasarela.cobrar.assert_called_once_with(750.0, "TICK-001")
    assert repos[2].rolled_back and not repos[2].committed
    assert repos[0].obtener("V-101") is None
    assert _stock(repos) == 50


def test_pago_timeout_se_traduce_y_hace_rollback(service, repos, make_cmd):
    pasarela = Mock()
    pasarela.cobrar.side_effect = TimeoutError
    svc = _con_pasarela(repos, pasarela)
    with pytest.raises(PagoNoDisponible):
        svc.registrar_venta(make_cmd(pago_con_tarjeta=True), HOY)
    assert repos[2].rolled_back
    assert _stock(repos) == 50


def test_pago_en_efectivo_no_llama_a_la_pasarela(service, repos, make_cmd):
    pasarela = Mock()
    svc = _con_pasarela(repos, pasarela)
    svc.registrar_venta(make_cmd(pago_con_tarjeta=False), HOY)
    pasarela.cobrar.assert_not_called()


# ---------- CU-03 Cancelar venta ----------
CREADA = datetime(2026, 10, 16, 9, 0)


def _venta_registrada(service, make_cmd):
    service.registrar_venta(make_cmd(creada_en=CREADA), HOY)


def test_responsable_cancela_y_reingresa_stock(service, repos, make_cmd):
    _venta_registrada(service, make_cmd)
    assert _stock(repos) == 45
    evento = service.cancelar_venta(
        "V-101", Actor("RESP-01", RESPONSABLE), True, CREADA + timedelta(hours=30)
    )
    assert evento.cancelada_por == "RESP-01"
    assert repos[0].obtener("V-101").estado == "CANCELADA"
    assert _stock(repos) == 50


def test_cancelar_con_caja_cerrada_se_deniega(service, repos, make_cmd):
    _venta_registrada(service, make_cmd)
    with pytest.raises(AutorizacionDenegada):
        service.cancelar_venta(
            "V-101", Actor("RESP-01", RESPONSABLE), False, CREADA + timedelta(hours=1)
        )
    assert _stock(repos) == 45


def test_cajero_dueno_a_las_24_horas_exactas_se_deniega(service, make_cmd):
    _venta_registrada(service, make_cmd)
    with pytest.raises(AutorizacionDenegada):
        service.cancelar_venta("V-101", Actor("CAJ-01", CAJERO), True, CREADA + timedelta(hours=24))


def test_cajero_dueno_dentro_de_24_horas_cancela(service, repos, make_cmd):
    _venta_registrada(service, make_cmd)
    service.cancelar_venta(
        "V-101", Actor("CAJ-01", CAJERO), True, CREADA + timedelta(hours=23, minutes=59)
    )
    assert _stock(repos) == 50


def test_cajero_ajeno_no_puede_cancelar(service, make_cmd):
    _venta_registrada(service, make_cmd)
    with pytest.raises(AutorizacionDenegada):
        service.cancelar_venta("V-101", Actor("CAJ-02", CAJERO), True, CREADA + timedelta(hours=1))


def test_cancelar_venta_inexistente(service):
    with pytest.raises(DomainException, match="no encontrada"):
        service.cancelar_venta("NOPE", Actor("RESP-01", RESPONSABLE), True, CREADA)


def test_no_se_cancela_dos_veces_ni_se_reingresa_dos_veces(service, repos, make_cmd):
    _venta_registrada(service, make_cmd)
    resp = Actor("RESP-01", RESPONSABLE)
    service.cancelar_venta("V-101", resp, True, CREADA + timedelta(hours=1))
    with pytest.raises(AutorizacionDenegada):
        service.cancelar_venta("V-101", resp, True, CREADA + timedelta(hours=2))
    assert _stock(repos) == 50


# ---------- CU-04 Recall ----------
def test_recall_masivo_bloquea_en_varias_sucursales(service, repos):
    eventos = service.ejecutar_recall("P100", "LOTE-001", "Alerta COFEPRIS", ["S001", "S002"])
    assert len(eventos) == 1  # S002 no maneja el producto
    assert repos[2].committed


def test_recall_con_lote_inexistente_hace_rollback(service, repos):
    with pytest.raises(DomainException, match="para recall"):
        service.ejecutar_recall("P100", "NO-EXISTE", "m", ["S001"])
    assert repos[2].rolled_back
