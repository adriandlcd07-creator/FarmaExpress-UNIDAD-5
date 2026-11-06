"""Puertos y servicio de aplicación (orquestador) de FarmaExpress."""

import dataclasses
from abc import ABC, abstractmethod
from datetime import date, datetime

from src.domain import (
    AutorizacionDeExcepcion,
    DomainException,
    ExistenciaDeProducto,
    LoteBloqueado,
    Receta,
    Venta,
    VentaCancelada,
    VentaRegistrada,
)
from src.security import Actor, puede_autorizar_excepcion, puede_cancelar_venta


class PagoRechazado(Exception):
    """La pasarela rechazó el cobro."""


class PagoNoDisponible(Exception):
    """La pasarela no respondió (timeout / caída)."""


class AutorizacionDenegada(Exception):
    """El actor no tiene permiso para la operación."""


# ---------------- Puertos ----------------
class IVentaRepository(ABC):
    @abstractmethod
    def agregar(self, venta: Venta):
        pass

    @abstractmethod
    def obtener(self, id_venta: str) -> Venta | None:
        pass


class IExistenciaRepository(ABC):
    @abstractmethod
    def obtener_por_producto_y_sucursal(
        self, producto_id: str, sucursal_id: str
    ) -> ExistenciaDeProducto | None:
        pass

    @abstractmethod
    def guardar(self, existencia: ExistenciaDeProducto):
        pass


class IUnitOfWork(ABC):
    @abstractmethod
    def begin(self):
        pass

    @abstractmethod
    def commit(self):
        pass

    @abstractmethod
    def rollback(self):
        pass


class IPasarelaPago(ABC):
    @abstractmethod
    def cobrar(self, monto: float, referencia: str) -> bool:
        pass


# ---------------- Comandos ----------------
@dataclasses.dataclass
class RegistrarVentaCommand:
    id_venta: str
    folio_ticket: str
    sucursal_id: str
    cajero_id: str
    producto_id: str
    numero_lote: str
    cantidad: int
    precio_unitario: float
    es_controlado: bool
    receta: Receta | None = None
    pago_con_tarjeta: bool = False
    excepcion: AutorizacionDeExcepcion | None = None
    rol_autorizador: str | None = None
    creada_en: datetime | None = None


class VentaApplicationService:
    def __init__(
        self,
        venta_repo: IVentaRepository,
        existencia_repo: IExistenciaRepository,
        uow: IUnitOfWork,
        pasarela: IPasarelaPago | None = None,
    ):
        self.venta_repo = venta_repo
        self.existencia_repo = existencia_repo
        self.uow = uow
        self.pasarela = pasarela

    def registrar_venta(self, cmd: RegistrarVentaCommand, fecha_actual: date) -> VentaRegistrada:
        """CU-01. Orden: validar -> cobrar -> descontar -> guardar -> commit.

        El cobro ocurre ANTES de modificar inventario, de modo que un pago
        rechazado no deja stock descontado ni venta confirmada.
        """
        self.uow.begin()
        try:
            existencia = self.existencia_repo.obtener_por_producto_y_sucursal(
                cmd.producto_id, cmd.sucursal_id
            )
            if not existencia:
                raise DomainException("Producto no disponible en la sucursal.")

            venta = Venta(
                cmd.id_venta,
                cmd.folio_ticket,
                cmd.sucursal_id,
                cmd.cajero_id,
                cmd.creada_en,
            )
            venta.agregar_detalle(
                cmd.producto_id,
                cmd.numero_lote,
                cmd.cantidad,
                cmd.precio_unitario,
                cmd.es_controlado,
            )
            if cmd.receta:
                venta.asociar_receta(cmd.receta, fecha_actual)
            if cmd.excepcion:
                if not puede_autorizar_excepcion(cmd.rol_autorizador):
                    raise AutorizacionDenegada(
                        "Solo el Responsable de Farmacia autoriza excepciones."
                    )
                venta.autorizar_excepcion(cmd.excepcion)

            existencia.validar_disponibilidad(cmd.numero_lote, cmd.cantidad, fecha_actual)
            evento = venta.confirmar_venta()

            if cmd.pago_con_tarjeta:
                self._cobrar(venta)

            existencia.descontar_stock(cmd.numero_lote, cmd.cantidad, fecha_actual)
            self.venta_repo.agregar(venta)
            self.existencia_repo.guardar(existencia)
            self.uow.commit()
            return evento
        except Exception:
            self.uow.rollback()
            raise

    def _cobrar(self, venta: Venta) -> None:
        try:
            aprobado = self.pasarela.cobrar(venta.total, venta.folio_ticket)
        except TimeoutError as exc:
            raise PagoNoDisponible("La pasarela de pago no respondió.") from exc
        if not aprobado:
            raise PagoRechazado("payment rejected")

    def cancelar_venta(
        self, id_venta: str, actor: Actor, caja_abierta: bool, ahora: datetime
    ) -> VentaCancelada:
        """CU-03: autoriza, cancela y reingresa stock."""
        self.uow.begin()
        try:
            venta = self.venta_repo.obtener(id_venta)
            if venta is None:
                raise DomainException(f"Venta {id_venta} no encontrada.")
            if not puede_cancelar_venta(
                venta.estado,
                actor,
                venta.cajero_id,
                caja_abierta,
                venta.creada_en,
                ahora,
            ):
                raise AutorizacionDenegada("Cancelación no permitida.")

            evento = venta.cancelar(actor.usuario_id)
            for d in venta.detalles:
                ex = self.existencia_repo.obtener_por_producto_y_sucursal(
                    d.producto_id, venta.sucursal_id
                )
                ex.reingresar_stock(d.numero_lote, d.cantidad)
                self.existencia_repo.guardar(ex)
            self.venta_repo.agregar(venta)
            self.uow.commit()
            return evento
        except Exception:
            self.uow.rollback()
            raise

    def ejecutar_recall(
        self,
        producto_id: str,
        numero_lote: str,
        motivo: str,
        sucursales: list[str],
    ) -> list[LoteBloqueado]:
        """CU-04: bloqueo masivo del lote en todas las sucursales indicadas."""
        self.uow.begin()
        try:
            eventos = []
            for suc in sucursales:
                ex = self.existencia_repo.obtener_por_producto_y_sucursal(producto_id, suc)
                if ex is None:
                    continue
                eventos.append(ex.bloquear_lote_por_recall(numero_lote, motivo))
                self.existencia_repo.guardar(ex)
            self.uow.commit()
            return eventos
        except Exception:
            self.uow.rollback()
            raise
