"""Demostración en consola de las reglas de negocio de FarmaExpress.

Uso:  python demo.py
"""

from datetime import date, datetime

from src.application import (
    IPasarelaPago,
    PagoRechazado,
    RegistrarVentaCommand,
    VentaApplicationService,
)
from src.domain import DomainException, ExistenciaDeProducto, Lote, Receta
from src.repository import (
    InMemoryExistenciaRepository,
    InMemoryUnitOfWork,
    InMemoryVentaRepository,
)
from src.security import RESPONSABLE, Actor

HOY = date(2026, 10, 16)


class PasarelaSimulada(IPasarelaPago):
    """Simula el terminal bancario: rechaza montos mayores a $1,000."""

    def cobrar(self, monto, referencia):
        return monto <= 1000


def titulo(texto):
    print(f"\n{'=' * 60}\n{texto}\n{'=' * 60}")


def stock(repo):
    ex = repo.obtener_por_producto_y_sucursal("P100", "S001")
    return ex.lotes[0].cantidad


def cmd(**kw):
    base = {
        "id_venta": "V-1",
        "folio_ticket": "TICK-1",
        "sucursal_id": "S001",
        "cajero_id": "CAJ-01",
        "producto_id": "P100",
        "numero_lote": "LOTE-001",
        "cantidad": 2,
        "precio_unitario": 150.0,
        "es_controlado": False,
    }
    base.update(kw)
    return RegistrarVentaCommand(**base)


def main():
    ventas, existencias = InMemoryVentaRepository(), InMemoryExistenciaRepository()
    existencias.guardar(
        ExistenciaDeProducto("E1", "P100", "S001", [Lote("LOTE-001", date(2027, 5, 1), 50)])
    )
    svc = VentaApplicationService(ventas, existencias, InMemoryUnitOfWork(), PasarelaSimulada())
    print("FarmaExpress - Demostración de reglas de negocio")
    print(f"Fecha simulada: {HOY} | Stock inicial de LOTE-001: {stock(existencias)}")

    titulo("1) Venta de medicamento controlado CON receta vigente")
    receta = Receta("REC-8899", "Dr. Carlos Gómez", "CED-12345", "Juan Pérez", date(2026, 10, 11))
    ev = svc.registrar_venta(cmd(es_controlado=True, receta=receta, cantidad=5), HOY)
    print(f"[OK] Venta registrada. Ticket {ev.folio_ticket}, total ${ev.total:.2f}")
    print(f"Stock actual: {stock(existencias)}")

    titulo("2) Venta de controlado SIN receta")
    try:
        svc.registrar_venta(cmd(id_venta="V-2", folio_ticket="TICK-2", es_controlado=True), HOY)
    except DomainException as e:
        print(f"[RECHAZADA] {e}")
    print(f"Stock actual (sin cambio): {stock(existencias)}")

    titulo("3) Pago con tarjeta rechazado por el banco")
    try:
        svc.registrar_venta(
            cmd(id_venta="V-3", folio_ticket="TICK-3", cantidad=10, pago_con_tarjeta=True), HOY
        )
    except PagoRechazado:
        print("[RECHAZADA] El banco rechazó el cobro; no se confirmó la venta.")
    print(f"Stock actual (sin cambio): {stock(existencias)}")

    titulo("4) Cancelación de la venta V-1 por el Responsable de Farmacia")
    svc.cancelar_venta("V-1", Actor("RESP-01", RESPONSABLE), True, datetime.now())
    print("[OK] Venta cancelada y mercancía regresada al inventario.")
    print(f"Stock actual: {stock(existencias)}")

    titulo("5) Alerta sanitaria (recall) del LOTE-001")
    svc.ejecutar_recall("P100", "LOTE-001", "Alerta COFEPRIS", ["S001"])
    try:
        svc.registrar_venta(cmd(id_venta="V-5", folio_ticket="TICK-5"), HOY)
    except DomainException as e:
        print(f"[RECHAZADA] {e}")

    print("\nFin de la demostración.")


if __name__ == "__main__":
    main()
