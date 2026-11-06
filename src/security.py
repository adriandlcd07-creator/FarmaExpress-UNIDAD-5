"""Políticas de autorización de negocio (autorización != autenticación)."""

import dataclasses
from datetime import datetime, timedelta

RESPONSABLE = "RESPONSABLE_FARMACIA"
CAJERO = "CAJERO"
VENTANA_CANCELACION = timedelta(hours=24)


@dataclasses.dataclass(frozen=True)
class Actor:
    usuario_id: str
    rol: str


def puede_autorizar_excepcion(rol: str | None) -> bool:
    """Solo el Responsable de Farmacia autoriza excepciones (CU-02)."""
    return rol == RESPONSABLE


def puede_cancelar_venta(
    estado: str,
    actor: Actor,
    cajero_id: str,
    caja_abierta: bool,
    creada_en: datetime,
    ahora: datetime,
) -> bool:
    """CU-03: reglas de cancelación.

    1. Una venta ya cancelada no se cancela de nuevo.
    2. Sin caja abierta nadie cancela (ni el Responsable).
    3. El Responsable de Farmacia puede cancelar.
    4. El cajero propietario solo durante las primeras 24 h (exactas = rechazo).
    """
    if estado == "CANCELADA":
        return False
    if not caja_abierta:
        return False
    if actor.rol == RESPONSABLE:
        return True
    if actor.usuario_id == cajero_id:
        return (ahora - creada_en) < VENTANA_CANCELACION
    return False
