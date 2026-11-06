from datetime import date, datetime

import pytest

from src.domain import (
    AutorizacionDeExcepcion,
    DomainException,
    ExistenciaDeProducto,
    Lote,
    Receta,
    Venta,
)

HOY = date(2026, 10, 16)


def _venta(controlado=False, cantidad=2, precio=100.0):
    v = Venta("V-1", "T-1", "S001", "CAJ-01")
    v.agregar_detalle("P100", "L1", cantidad, precio, controlado)
    return v


def _receta(dias_atras):
    return Receta(
        "R-1",
        "Dr. X",
        "CED-1",
        "Paciente",
        date.fromordinal(HOY.toordinal() - dias_atras),
    )


# ---- TDD (RED -> GREEN): no confirmar dos veces ----
def test_cannot_confirm_twice():
    venta = _venta()
    venta.confirmar_venta()
    with pytest.raises(DomainException, match="ya fue confirmada"):
        venta.confirmar_venta()


# ---- Venta ----
def test_total_se_calcula_por_detalle():
    venta = _venta(cantidad=3, precio=50.0)
    assert venta.total == 150.0


def test_cantidad_cero_o_negativa_se_rechaza():
    venta = Venta("V", "T", "S", "C")
    for cantidad in (0, -1):
        with pytest.raises(DomainException, match="mayor a cero"):
            venta.agregar_detalle("P", "L", cantidad, 10.0, False)


def test_confirmar_cambia_estado_y_registra_evento():
    venta = _venta()
    evento = venta.confirmar_venta()
    assert venta.estado == "CONFIRMADA"
    assert evento.total == 200.0
    assert venta.eventos == [evento]


def test_controlado_sin_receta_ni_excepcion_se_rechaza():
    with pytest.raises(DomainException, match="controlado exige receta"):
        _venta(controlado=True).confirmar_venta()


def test_no_controlado_se_vende_sin_receta():
    assert _venta(controlado=False).confirmar_venta().total == 200.0


def test_controlado_con_excepcion_se_confirma():
    venta = _venta(controlado=True)
    venta.autorizar_excepcion(
        AutorizacionDeExcepcion("RESP-01", "Paciente crónico sin receta", datetime(2026, 10, 16))
    )
    assert venta.confirmar_venta().folio_ticket == "T-1"


def test_excepcion_sin_motivo_se_rechaza():
    venta = _venta(controlado=True)
    with pytest.raises(DomainException, match="motivo"):
        venta.autorizar_excepcion(AutorizacionDeExcepcion("RESP-01", "  ", datetime(2026, 10, 16)))


# ---- Receta: límites de vigencia ----
def test_receta_vigente_exactamente_30_dias():
    assert _receta(30).es_vigente(HOY) is True


def test_receta_vencida_a_los_31_dias():
    assert _receta(31).es_vigente(HOY) is False


def test_receta_con_fecha_futura_es_invalida():
    assert _receta(-1).es_vigente(HOY) is False


def test_asociar_receta_vencida_se_rechaza():
    with pytest.raises(DomainException, match="vencida"):
        _venta(controlado=True).asociar_receta(_receta(31), HOY)


def test_asociar_receta_valida_la_guarda():
    venta = _venta(controlado=True)
    venta.asociar_receta(_receta(0), HOY)
    assert venta.receta.folio == "R-1"


# ---- Lotes e inventario ----
def test_lote_que_caduca_hoy_no_esta_disponible():
    assert Lote("L", HOY, 5).esta_disponible_para_venta(HOY) is False


def test_lote_que_caduca_manana_esta_disponible():
    assert Lote("L", date(2026, 10, 17), 5).esta_disponible_para_venta(HOY) is True


def test_descontar_toda_la_existencia_deja_cero():
    lote = Lote("L", date(2027, 1, 1), 5)
    lote.descontar(5, HOY)
    assert lote.cantidad == 0


def test_descontar_mas_de_lo_disponible_falla_y_no_modifica():
    lote = Lote("L", date(2027, 1, 1), 5)
    with pytest.raises(DomainException, match="Stock insuficiente"):
        lote.descontar(6, HOY)
    assert lote.cantidad == 5


def test_existencia_lote_inexistente():
    ex = ExistenciaDeProducto("E", "P", "S", [])
    with pytest.raises(DomainException, match="No se encontró el lote"):
        ex.descontar_stock("X", 1, HOY)
    with pytest.raises(DomainException, match="para reingreso"):
        ex.reingresar_stock("X", 1)
    with pytest.raises(DomainException, match="para recall"):
        ex.bloquear_lote_por_recall("X", "m")


def test_reingresar_stock_suma_cantidad():
    ex = ExistenciaDeProducto("E", "P", "S", [Lote("L", date(2027, 1, 1), 5)])
    ex.reingresar_stock("L", 3)
    assert ex.lotes[0].cantidad == 8


def test_recall_bloquea_lote_y_emite_evento():
    ex = ExistenciaDeProducto("E", "P", "S", [Lote("L", date(2027, 1, 1), 5)])
    evento = ex.bloquear_lote_por_recall("L", "Alerta COFEPRIS")
    assert evento.motivo == "Alerta COFEPRIS"
    assert ex.lotes[0].esta_disponible_para_venta(HOY) is False


# ---- Cancelación ----
def test_cancelar_cambia_estado_y_emite_evento():
    venta = _venta()
    venta.confirmar_venta()
    evento = venta.cancelar("RESP-01")
    assert venta.estado == "CANCELADA"
    assert evento.cancelada_por == "RESP-01"


def test_no_se_cancela_dos_veces():
    venta = _venta()
    venta.cancelar("RESP-01")
    with pytest.raises(DomainException, match="ya fue cancelada"):
        venta.cancelar("RESP-01")
