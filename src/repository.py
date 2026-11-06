"""Adaptadores de infraestructura: en memoria y SQLAlchemy (SQLite)."""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.application import (
    IExistenciaRepository,
    IUnitOfWork,
    IVentaRepository,
)
from src.domain import ExistenciaDeProducto, Lote, Venta

# ---------------- En memoria ----------------


class InMemoryVentaRepository(IVentaRepository):
    def __init__(self):
        self._ventas: dict[str, Venta] = {}

    def agregar(self, venta: Venta):
        self._ventas[venta.id_venta] = venta

    def obtener(self, id_venta: str) -> Venta | None:
        return self._ventas.get(id_venta)


class InMemoryExistenciaRepository(IExistenciaRepository):
    def __init__(self):
        self._existencias: dict[str, ExistenciaDeProducto] = {}

    def guardar(self, existencia: ExistenciaDeProducto):
        key = f"{existencia.sucursal_id}_{existencia.producto_id}"
        self._existencias[key] = existencia

    def obtener_por_producto_y_sucursal(
        self, producto_id: str, sucursal_id: str
    ) -> ExistenciaDeProducto | None:
        return self._existencias.get(f"{sucursal_id}_{producto_id}")


class InMemoryUnitOfWork(IUnitOfWork):
    def __init__(self):
        self.in_transaction = False
        self.committed = False
        self.rolled_back = False

    def begin(self):
        self.in_transaction = True
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True
        self.in_transaction = False

    def rollback(self):
        self.rolled_back = True
        self.in_transaction = False


# ---------------- SQLAlchemy ----------------


class Base(DeclarativeBase):
    pass


class VentaRow(Base):
    __tablename__ = "ventas"
    id_venta: Mapped[str] = mapped_column(String, primary_key=True)
    folio_ticket: Mapped[str] = mapped_column(String, unique=True)
    sucursal_id: Mapped[str] = mapped_column(String)
    cajero_id: Mapped[str] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String)
    total: Mapped[float] = mapped_column(Float)
    creada_en: Mapped[datetime] = mapped_column(DateTime)


class DetalleRow(Base):
    __tablename__ = "detalles_venta"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_venta: Mapped[str] = mapped_column(String)
    producto_id: Mapped[str] = mapped_column(String)
    numero_lote: Mapped[str] = mapped_column(String)
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[float] = mapped_column(Float)
    es_controlado: Mapped[bool] = mapped_column(Boolean)


class LoteRow(Base):
    __tablename__ = "lotes"
    sucursal_id: Mapped[str] = mapped_column(String, primary_key=True)
    producto_id: Mapped[str] = mapped_column(String, primary_key=True)
    numero_lote: Mapped[str] = mapped_column(String, primary_key=True)
    fecha_caducidad: Mapped[date] = mapped_column(Date)
    cantidad: Mapped[int] = mapped_column(Integer)
    bloqueado: Mapped[bool] = mapped_column(Boolean, default=False)


class SqlUnitOfWork(IUnitOfWork):
    def __init__(self, session: Session):
        self.session = session

    def begin(self):
        pass  # SQLAlchemy abre la transacción de forma implícita.

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


class SqlVentaRepository(IVentaRepository):
    def __init__(self, session: Session):
        self.session = session

    def agregar(self, venta: Venta):
        self.session.merge(
            VentaRow(
                id_venta=venta.id_venta,
                folio_ticket=venta.folio_ticket,
                sucursal_id=venta.sucursal_id,
                cajero_id=venta.cajero_id,
                estado=venta.estado,
                total=venta.total,
                creada_en=venta.creada_en,
            )
        )
        if self.session.query(DetalleRow).filter_by(id_venta=venta.id_venta).count():
            return
        for d in venta.detalles:
            self.session.add(
                DetalleRow(
                    id_venta=venta.id_venta,
                    producto_id=d.producto_id,
                    numero_lote=d.numero_lote,
                    cantidad=d.cantidad,
                    precio_unitario=d.precio_unitario,
                    es_controlado=d.es_controlado,
                )
            )

    def obtener(self, id_venta: str) -> Venta | None:
        row = self.session.get(VentaRow, id_venta)
        if row is None:
            return None
        venta = Venta(
            row.id_venta,
            row.folio_ticket,
            row.sucursal_id,
            row.cajero_id,
            row.creada_en,
        )
        venta.estado = row.estado
        for d in self.session.query(DetalleRow).filter_by(id_venta=id_venta):
            venta.agregar_detalle(
                d.producto_id,
                d.numero_lote,
                d.cantidad,
                d.precio_unitario,
                d.es_controlado,
            )
        return venta


class SqlExistenciaRepository(IExistenciaRepository):
    def __init__(self, session: Session):
        self.session = session

    def guardar(self, existencia: ExistenciaDeProducto):
        for lote in existencia.lotes:
            self.session.merge(
                LoteRow(
                    sucursal_id=existencia.sucursal_id,
                    producto_id=existencia.producto_id,
                    numero_lote=lote.numero_lote,
                    fecha_caducidad=lote.fecha_caducidad,
                    cantidad=lote.cantidad,
                    bloqueado=lote.bloqueado,
                )
            )

    def obtener_por_producto_y_sucursal(
        self, producto_id: str, sucursal_id: str
    ) -> ExistenciaDeProducto | None:
        rows = (
            self.session.query(LoteRow)
            .filter_by(producto_id=producto_id, sucursal_id=sucursal_id)
            .all()
        )
        if not rows:
            return None
        lotes = [Lote(r.numero_lote, r.fecha_caducidad, r.cantidad, r.bloqueado) for r in rows]
        return ExistenciaDeProducto(
            f"EX-{sucursal_id}-{producto_id}", producto_id, sucursal_id, lotes
        )
