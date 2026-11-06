# FarmaExpress · Unidad 5 — Integración, Pruebas y Calidad

**Equipo 10**  
Emiliano Salas Padron (2157333) 
Jesus Adrian De la Cruz Dominguez (2156493) 
Joel Guadalupe Taméz Olmos (2158224)
Profesor: Miguel Ángel Gómez Marroquín · Componentes de Lógica de Negocios · FIME · UANL

Suite automatizada de pruebas sobre la lógica de negocio de FarmaExpress (venta en mostrador de medicamentos generales y controlados, lotes/caducidades, excepciones, recall y cancelación).

## Arquitectura

```
Usuario/API → VentaApplicationService (src/application.py)
                    ↓ puertos: IVentaRepository · IExistenciaRepository · IUnitOfWork · IPasarelaPago
              Dominio (src/domain.py): Venta, Receta, Lote, ExistenciaDeProducto, eventos
              Seguridad (src/security.py): can_cancel / autorizar excepción
                    ↓ adaptadores (src/repository.py)
              En memoria | SQLAlchemy + SQLite | (pasarela simulada con Mock)
```

El dominio no importa SQLAlchemy ni ninguna biblioteca de pagos.

## Instalación y comandos

```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
python -m ruff check src tests
python -m pytest -v --cov=src --cov-report=term-missing --cov-report=html --cov-fail-under=80
```

Reporte de cobertura: `htmlcov/index.html`.

## Estructura

```
src/domain.py        Reglas de negocio (VOs, entidades, agregados, eventos)
src/application.py   Puertos + servicio (registrar venta, cancelar, recall)
src/repository.py    Repos en memoria y SQLAlchemy, Unit of Work
src/security.py      Políticas de autorización
tests/               test_casos_csv · test_domain · test_service · test_repository · test_security
data/                casos_de_prueba.csv (casos parametrizados con csv.DictReader)
docs/                Matriz_Pruebas_U5.csv · Reporte_Unidad5_FarmaExpress.(md|docx)
.github/workflows/ci.yml   Ruff + pytest (≥80%) + build
```

## Casos de uso cubiertos
CU-01 Registrar venta · CU-02 Autorizar excepción · CU-03 Cancelar venta · CU-04 Recall sanitario. (CU-05 Resurtido queda fuera del alcance de esta unidad.)
