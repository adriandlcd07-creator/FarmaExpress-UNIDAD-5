"""Capa de dominio de FarmaExpress: VOs, entidades, agregados y eventos."""

import dataclasses
from datetime import date, datetime


class DomainException(Exception):
    """Excepción base para violaciones de reglas de negocio e invariantes."""


@dataclasses.dataclass(frozen=True)
class Receta:
    """Value Object inmutable que representa una receta médica."""

    folio: str
    medico: str
    cedula_medico: str
    nombre_paciente: str
    fecha_emision: date

    def es_vigente(self, fecha_actual: date, dias_max_vigencia: int = 30) -> bool:
        delta = (fecha_actual - self.fecha_emision).days
        return 0 <= delta <= dias_max_vigencia


@dataclasses.dataclass(frozen=True)
class AutorizacionDeExcepcion:
    """Value Object inmutable para excepciones del Responsable de Farmacia."""

    id_gerente: str
    motivo: str
    timestamp: datetime


class DomainEvent:
    """Clase base para eventos de negocio."""


@dataclasses.dataclass(frozen=True)
class VentaRegistrada(DomainEvent):
    id_venta: str
    folio_ticket: str
    total: float
    timestamp: datetime


@dataclasses.dataclass(frozen=True)
class VentaCancelada(DomainEvent):
    id_venta: str
    folio_ticket: str
    cancelada_por: str


@dataclasses.dataclass(frozen=True)
class LoteBloqueado(DomainEvent):
    numero_lote: str
    motivo: str


class Lote:
    """Entidad Lote dentro del Agregado ExistenciaDeProducto."""

    def __init__(
        self,
        numero_lote: str,
        fecha_caducidad: date,
        cantidad: int,
        bloqueado: bool = False,
    ):
        self.numero_lote = numero_lote
        self.fecha_caducidad = fecha_caducidad
        self.cantidad = cantidad
        self.bloqueado = bloqueado

    def esta_disponible_para_venta(self, fecha_actual: date) -> bool:
        return not self.bloqueado and self.fecha_caducidad > fecha_actual

    def validar_descuento(self, cantidad: int, fecha_actual: date) -> None:
        """Valida sin modificar el estado del lote."""
        if not self.esta_disponible_para_venta(fecha_actual):
            raise DomainException(f"El lote {self.numero_lote} está bloqueado o vencido.")
        if cantidad > self.cantidad:
            raise DomainException(
                f"Stock insuficiente en lote {self.numero_lote}. "
                f"Disponible: {self.cantidad}, Solicitado: {cantidad}"
            )

    def descontar(self, cantidad: int, fecha_actual: date) -> None:
        self.validar_descuento(cantidad, fecha_actual)
        self.cantidad -= cantidad

    def reingresar(self, cantidad: int) -> None:
        self.cantidad += cantidad


class ExistenciaDeProducto:
    """Aggregate Root que controla el inventario por producto y sucursal."""

    def __init__(
        self,
        id_existencia: str,
        producto_id: str,
        sucursal_id: str,
        lotes: list[Lote],
    ):
        self.id_existencia = id_existencia
        self.producto_id = producto_id
        self.sucursal_id = sucursal_id
        self.lotes = lotes

    def _buscar_lote(self, numero_lote: str) -> Lote | None:
        return next((x for x in self.lotes if x.numero_lote == numero_lote), None)

    def validar_disponibilidad(self, numero_lote: str, cantidad: int, fecha_actual: date) -> None:
        lote = self._buscar_lote(numero_lote)
        if not lote:
            raise DomainException(
                f"No se encontró el lote {numero_lote} en la sucursal {self.sucursal_id}."
            )
        lote.validar_descuento(cantidad, fecha_actual)

    def descontar_stock(self, numero_lote: str, cantidad: int, fecha_actual: date) -> None:
        self.validar_disponibilidad(numero_lote, cantidad, fecha_actual)
        self._buscar_lote(numero_lote).descontar(cantidad, fecha_actual)

    def reingresar_stock(self, numero_lote: str, cantidad: int) -> None:
        lote = self._buscar_lote(numero_lote)
        if not lote:
            raise DomainException(f"No se encontró el lote {numero_lote} para reingreso.")
        lote.reingresar(cantidad)

    def bloquear_lote_por_recall(self, numero_lote: str, motivo: str) -> LoteBloqueado:
        lote = self._buscar_lote(numero_lote)
        if not lote:
            raise DomainException(f"Lote {numero_lote} no encontrado para recall.")
        lote.bloqueado = True
        return LoteBloqueado(numero_lote=numero_lote, motivo=motivo)


class DetalleVenta:
    """Entidad de línea de detalle de la venta."""

    def __init__(
        self,
        producto_id: str,
        numero_lote: str,
        cantidad: int,
        precio_unitario: float,
        es_controlado: bool,
    ):
        self.producto_id = producto_id
        self.numero_lote = numero_lote
        self.cantidad = cantidad
        self.precio_unitario = precio_unitario
        self.es_controlado = es_controlado

    @property
    def subtotal(self) -> float:
        return self.cantidad * self.precio_unitario


class Venta:
    """Aggregate Root de Venta en Mostrador."""

    def __init__(
        self,
        id_venta: str,
        folio_ticket: str,
        sucursal_id: str,
        cajero_id: str,
        creada_en: datetime | None = None,
    ):
        self.id_venta = id_venta
        self.folio_ticket = folio_ticket
        self.sucursal_id = sucursal_id
        self.cajero_id = cajero_id
        self.creada_en = creada_en or datetime.now()

        self.detalles: list[DetalleVenta] = []
        self.receta: Receta | None = None
        self.excepcion: AutorizacionDeExcepcion | None = None
        self.estado: str = "REGISTRADA"
        self.eventos: list[DomainEvent] = []

    @property
    def total(self) -> float:
        return sum(d.subtotal for d in self.detalles)

    def agregar_detalle(
        self,
        producto_id: str,
        numero_lote: str,
        cantidad: int,
        precio: float,
        es_controlado: bool,
    ) -> None:
        if cantidad <= 0:
            raise DomainException("La cantidad debe ser mayor a cero.")
        self.detalles.append(
            DetalleVenta(producto_id, numero_lote, cantidad, precio, es_controlado)
        )

    def asociar_receta(self, receta: Receta, fecha_actual: date) -> None:
        if not receta.es_vigente(fecha_actual):
            raise DomainException(f"La receta folio {receta.folio} está vencida o es inválida.")
        self.receta = receta

    def autorizar_excepcion(self, autorizacion: AutorizacionDeExcepcion) -> None:
        if not autorizacion.motivo.strip():
            raise DomainException("La excepción requiere un motivo trazable.")
        self.excepcion = autorizacion

    def confirmar_venta(self) -> VentaRegistrada:
        if self.estado == "CONFIRMADA":
            raise DomainException("La venta ya fue confirmada.")
        tiene_controlados = any(d.es_controlado for d in self.detalles)
        if tiene_controlados and not self.receta and not self.excepcion:
            raise DomainException(
                "No se puede completar la venta: "
                "Medicamento controlado exige receta médica válida "
                "o autorización de excepción."
            )
        evento = VentaRegistrada(
            id_venta=self.id_venta,
            folio_ticket=self.folio_ticket,
            total=self.total,
            timestamp=datetime.now(),
        )
        self.estado = "CONFIRMADA"
        self.eventos.append(evento)
        return evento

    def cancelar(self, cancelada_por: str) -> VentaCancelada:
        if self.estado == "CANCELADA":
            raise DomainException("La venta ya fue cancelada.")
        self.estado = "CANCELADA"
        evento = VentaCancelada(self.id_venta, self.folio_ticket, cancelada_por)
        self.eventos.append(evento)
        return evento
