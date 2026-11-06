---
title: "FarmaExpress — Reporte de la Unidad 5: Integración, Pruebas y Calidad"
subtitle: "Equipo 10 · Componentes de Lógica de Negocios · FIME UANL"
---

**Integrantes:** Emiliano Salas Padron (2157333), Jesus Adrian De la Cruz Dominguez (2156493), Joel Guadalupe Taméz Olmos (2158224). **Profesor:** Miguel Ángel Gómez Marroquín.
**Repositorio:** https://github.com/Salasdotcom/FarmaExpress

# 0. Plan de pruebas

Se prueban las reglas del PIA de FarmaExpress: (1) medicamento controlado exige receta vigente (≤30 días) o excepción del Responsable de Farmacia; (2) inventario por lotes: no se vende lote vencido, bloqueado por recall ni sin stock; (3) cancelación con caja abierta, reingreso de stock y ventana de 24 h para el cajero propietario. Además: cobro con pasarela simulada, persistencia SQLite y autorización. Alcance de cobertura: `src/` completo (domain, application, repository, security). Matriz completa en `docs/Matriz_Pruebas_U5.csv` (25 casos: 7 éxito, 14 error, 4 límite).

Además, siguiendo el paquete del laboratorio (casos CP01–CP15 del proyecto base), se adaptó el formato de `casos_de_prueba.csv` a FarmaExpress en `data/casos_de_prueba.csv` y se ejecuta con pruebas parametrizadas (`tests/test_casos_csv.py`, `csv.DictReader`). CP13–CP15 (pago rechazado, commit, rollback) se cubren con `test_pago_rechazado_...`, `test_repository_commit` y `test_repository_rollback`. Los CSV/SQLite de pedidos del paquete son datos didácticos del dominio genérico de pedidos y no se importaron.

# E1. Entorno y ejecución

Sirve `venv` para aislar dependencias del curso y `pytest` para descubrir y ejecutar automáticamente las funciones `test_*`. Con ello cualquier integrante reproduce las mismas pruebas. Al instalar `requirements.txt` quedan pytest, pytest-cov, SQLAlchemy y Ruff.

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0 -- /usr/bin/python
cachedir: .pytest_cache
rootdir: /home/claude/FarmaExpress
configfile: pytest.ini
testpaths: tests
plugins: platformdirs-4.13.0, cov-7.1.0
collecting ... collected 63 items
...
tests/test_service.py::test_recall_con_lote_inexistente_hace_rollback PASSED [100%]

----------- generated xml file: /home/claude/FarmaExpress/junit.xml ------------
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.12.3-final-0 ________________

Name                 Stmts   Miss  Cover   Missing
--------------------------------------------------
src/__init__.py          0      0   100%
src/application.py     125      8    94%   36, 40, 48, 52, 58, 62, 66, 72
src/domain.py          133      0   100%
src/repository.py      102      0   100%
src/security.py         21      0   100%
--------------------------------------------------
TOTAL                  381      8    98%
Coverage HTML written to dir htmlcov
Required test coverage of 80% reached. Total coverage: 97.90%
============================== 63 passed in 0.51s ==============================
```

*[Insertar aquí captura de terminal con el comando y el resumen.]*

# E2. Pruebas unitarias (Arrange–Act–Assert)

Ejemplo (CP-10, límite): vender exactamente todo el stock.

```python
def test_vender_exactamente_todo_el_stock(service, repos, make_cmd):
    service.registrar_venta(make_cmd(cantidad=50), HOY)   # Arrange + Act
    assert _stock(repos) == 0                              # Assert
```

Nuevas pruebas de límite de receta (CP-03, CP-04) y de lote que caduca hoy (CP-08): ver `tests/test_domain.py` y `tests/test_service.py`. Entrada, regla, esperado y real están en la matriz del punto E9.

# E3. TDD real: Red → Green → Refactor

Regla nueva: **una venta no puede confirmarse dos veces** (el código original lo permitía).

**RED** — prueba escrita antes de tocar `confirmar_venta()`:

```
... collected 1 item

tests/test_domain.py::test_cannot_confirm_twice FAILED                   [100%]

=================================== FAILURES ===================================
__________________________ test_cannot_confirm_twice ___________________________

    def test_cannot_confirm_twice():
        venta = _venta()
        venta.confirmar_venta()
>       with pytest.raises(DomainException, match="ya fue confirmada"):
E       Failed: DID NOT RAISE DomainException

tests/test_domain.py:30: Failed
=========================== short test summary info ============================
FAILED tests/test_domain.py::test_cannot_confirm_twice - Failed: DID NOT RAIS...
============================== 1 failed in 0.03s ===============================
```

**GREEN** — implementación mínima en `src/domain.py`:

```python
if self.estado == "CONFIRMADA":
    raise DomainException("La venta ya fue confirmada.")
```

```
... collected 1 item

tests/test_domain.py::test_cannot_confirm_twice PASSED                   [100%]

============================== 1 passed in 0.02s ===============================
```

**REFACTOR** — se extrajo la lógica de descuento a `Lote.validar_descuento()` (sin efectos), reutilizada por `descontar()` y por el servicio; se volvió a ejecutar toda la suite en verde.

**¿Por qué TDD no es ejecutar pruebas al final?** Porque la prueba se escribe primero, falla por la razón correcta y define el comportamiento; el código solo se escribe para hacerla pasar. Una prueba escrita después puede pasar por accidente y nunca se comprueba que detecte el defecto.

*[Insertar capturas RED y GREEN.]*

# E4. Integración con base de datos y transacciones

```python
def test_repository_commit(session):
    repo = SqlVentaRepository(session)
    repo.agregar(_venta())
    session.commit()
    leida = repo.obtener("V-1")
    assert leida.total == 240.0 and leida.estado == "REGISTRADA"
```

Además: `test_repository_rollback`, `test_folio_ticket_duplicado_viola_unicidad` (IntegrityError), y dos pruebas del servicio con `SqlUnitOfWork` (commit real y rollback ante error). Cada prueba usa un SQLite en memoria propio.

**Commit vs rollback:** `commit` vuelve permanentes los cambios de la transacción (venta y descuento de lote); `rollback` los descarta completos, de modo que tras un error la venta no existe y el inventario queda como estaba. SQLite en memoria no sustituye pruebas contra el motor productivo.

# E5. Servicios externos sin cobros reales

Se agregó el puerto `IPasarelaPago` (cobro con tarjeta en mostrador). En pruebas se usa `Mock`; nunca se contacta a un proveedor real.

```python
def test_pago_aprobado(service, repos, make_cmd):
    pasarela = Mock(); pasarela.cobrar.return_value = True
    svc = VentaApplicationService(repos[0], repos[1], repos[2], pasarela)
    evento = svc.registrar_venta(make_cmd(pago_con_tarjeta=True), HOY)
    assert evento.total == 750.0
    pasarela.cobrar.assert_called_once_with(750.0, "TICK-001")
```

Rutas probadas: aprobado (CP-19), rechazado → `PagoRechazado` (CP-20), timeout → `PagoNoDisponible` (CP-21) y efectivo → la pasarela no se invoca.

**Riesgo de consistencia y propuesta aplicada:** si se confirma/descuenta stock antes de conocer el resultado del pago, un cobro rechazado deja inventario descontado. El servicio valida → cobra → descuenta → guarda → commit; en el rechazo, `test_pago_rechazado_no_descuenta_stock_ni_confirma` comprueba stock intacto y rollback. Pendiente para producción: *outbox* para publicar `VentaRegistrada` solo después del commit y reintentos/circuit breaker en la pasarela.

# E6. Seguridad y autorización

Se prueba lo que realmente implementa `src/security.py` (cancelación de ventas, CU-03):

| Rol | ¿Propietario? | Estado | Caja | Antigüedad | Resultado |
|---|---|---|---|---|---|
| Responsable | — | CONFIRMADA | abierta | 100 h | Permitido |
| Cajero | Sí | CONFIRMADA | abierta | 1 h | Permitido |
| Cajero | Sí | CONFIRMADA | abierta | 23.99 h | Permitido |
| Cajero | Sí | CONFIRMADA | abierta | 24 h exactas | **Denegado** |
| Cajero | Sí | CONFIRMADA | abierta | 30 h | Denegado |
| Cajero | No | CONFIRMADA | abierta | 1 h | Denegado |
| Responsable | — | CONFIRMADA | **cerrada** | 1 h | Denegado |
| Cajero | Sí | CONFIRMADA | cerrada | 1 h | Denegado |
| Responsable | — | CANCELADA | abierta | 1 h | Denegado |

Además, solo el Responsable de Farmacia autoriza excepciones (CU-02): un cajero recibe `AutorizacionDenegada` (CP-06). Todas las pruebas usan fechas fijas (`now` explícito).

# E7. Cobertura y calidad

```
$ python -m ruff check src tests
All checks passed!

_______________ coverage: platform linux, python 3.12.3-final-0 ________________

Name                 Stmts   Miss  Cover   Missing
--------------------------------------------------
src/__init__.py          0      0   100%
src/application.py     125      8    94%   36, 40, 48, 52, 58, 62, 66, 72
src/domain.py          133      0   100%
src/repository.py      102      0   100%
src/security.py         21      0   100%
--------------------------------------------------
TOTAL                  381      8    98%
Coverage HTML written to dir htmlcov
Required test coverage of 80% reached. Total coverage: 97.90%
============================== 63 passed in 0.51s ==============================
```

*[Insertar captura de terminal y del reporte `htmlcov/index.html`.]*

**Rama no probada:** en `src/application.py` quedan sin ejecutar 8 líneas, que son los cuerpos `pass` de los métodos abstractos de los puertos (no contienen lógica). No se agregaron pruebas artificiales para cubrirlas.

**La cobertura no es corrección:** se verificó con una mutación manual: al cambiar `<` por `<=` en el límite de 24 h de `security.py`, la suite detectó el defecto:

```
FAILED tests/test_security.py::test_matriz_autorizacion_cancelacion[actor3-CONFIRMADA-True-24-False]
FAILED tests/test_service.py::test_cajero_dueno_a_las_24_horas_exactas_se_deniega
2 failed, 61 passed in 0.13s
```

# E8. GitHub Actions

Workflow `.github/workflows/ci.yml` (nombre: *CI Business Logic*): instala dependencias, ejecuta Ruff, pytest con `--cov-fail-under=80` y `compileall src`.

- URL del repositorio: *[pegar URL]*
- Ejecución verde: *[captura]*
- Ejecución roja (aserción modificada temporalmente, p. ej. en `test_pago_aprobado` cambiar `750.0` por `751.0`): *[captura + qué detectó]*
- Ejecución verde tras revertir: *[captura]*

Nota: el bloqueo obligatorio de merge requiere activar *branch protection / rulesets* en GitHub.

# E9. Adaptación al PIA (matriz de casos)

Tres reglas del PIA con éxito, error y límite (25 casos en total; versión CSV en `docs/Matriz_Pruebas_U5.csv`).

| ID | Regla | Entrada | Esperado | Tipo | Real |
|---|---|---|---|---|---|
| CP-01 | Venta de controlado exige receta o excepción (CU-01) | Controlado, 5 pzas x $150, receta vigente (5 días) | Venta registrada, total $750, stock 50→45 | Éxito | PASSED |
| CP-02 | Venta de controlado exige receta o excepción (CU-01) | Controlado sin receta ni excepción | DomainException + rollback, stock sin cambio | Error | PASSED |
| CP-03 | Vigencia de receta 30 días | Receta emitida hace exactamente 30 días | Vigente | Límite | PASSED |
| CP-04 | Vigencia de receta 30 días | Receta emitida hace 31 días | Venta rechazada (receta vencida) | Error/Límite | PASSED |
| CP-05 | Excepción autorizada por Responsable (CU-02) | Controlado sin receta, excepción con rol RESPONSABLE_FARMACIA | Venta registrada | Éxito | PASSED |
| CP-06 | Excepción autorizada por Responsable (CU-02) | Excepción solicitada con rol CAJERO | AutorizacionDenegada + rollback | Error | PASSED |
| CP-07 | Lotes vencidos/bloqueados no se venden | Venta de LOTE-VENCIDO (caducó 2026-01-01) | DomainException 'bloqueado o vencido' | Error | PASSED |
| CP-08 | Lotes vencidos/bloqueados no se venden | Lote que caduca el mismo día de la venta | Rechazo (caducidad debe ser > hoy) | Límite | PASSED |
| CP-09 | Stock suficiente por lote | Cantidad 51 con stock 50 | DomainException 'Stock insuficiente', stock intacto | Error | PASSED |
| CP-10 | Stock suficiente por lote | Cantidad 50 con stock 50 | Venta registrada, stock = 0 | Límite | PASSED |
| CP-11 | Cantidad positiva | Cantidad 0 y -1 | DomainException 'mayor a cero' | Error | PASSED |
| CP-12 | Recall sanitario bloquea lotes (CU-04) | Recall de LOTE-001 en S001 y S002 (S002 sin producto) | 1 evento LoteBloqueado, commit | Éxito | PASSED |
| CP-13 | Recall sanitario bloquea lotes (CU-04) | Venta de lote tras recall | Rechazo 'bloqueado o vencido' | Error | PASSED |
| CP-14 | Cancelación con caja abierta y reingreso (CU-03) | Responsable cancela venta con caja abierta | Estado CANCELADA, stock 45→50 | Éxito | PASSED |
| CP-15 | Cancelación con caja abierta y reingreso (CU-03) | Responsable cancela con caja cerrada | AutorizacionDenegada, stock sin cambio | Error | PASSED |
| CP-16 | Cajero propietario cancela solo en 24 h | Cajero dueño a las 24:00 h exactas | AutorizacionDenegada | Límite | PASSED |
| CP-17 | Cajero propietario cancela solo en 24 h | Cajero dueño a las 23:59 h | Cancelación permitida, stock reingresado | Éxito | PASSED |
| CP-18 | Cancelación solo por propietario/Responsable | Otro cajero intenta cancelar | AutorizacionDenegada | Error | PASSED |
| CP-19 | Cobro con tarjeta vía pasarela (mock) | Pasarela aprueba, total $750 | cobrar(750.0,'TICK-001') 1 vez, stock 45 | Éxito | PASSED |
| CP-20 | Cobro rechazado no confirma ni descuenta | Pasarela devuelve False | PagoRechazado, rollback, venta no guardada, stock 50 | Error | PASSED |
| CP-21 | Pasarela no disponible | Pasarela lanza TimeoutError | PagoNoDisponible + rollback | Error | PASSED |
| CP-22 | Persistencia de venta (SQLite) | Guardar venta y commit | Venta recuperable con total 240 y detalle | Éxito | PASSED |
| CP-23 | Persistencia: rollback | Guardar venta y rollback | obtener() devuelve None | Error | PASSED |
| CP-24 | Unicidad de folio de ticket | Dos ventas con mismo folio | IntegrityError | Error | PASSED |
| CP-25 | Una venta no se confirma dos veces (TDD) | confirmar_venta() dos veces | DomainException 'ya fue confirmada' | Error | PASSED |

**Decisiones de diseño:** (a) `confirmar_venta` y la validación de disponibilidad no mutan estado, así el rollback en memoria es confiable; (b) el cobro ocurre antes del descuento de inventario; (c) caducidad `> hoy` (un lote que caduca hoy no se vende); (d) receta vigente de 0 a 30 días, fecha futura inválida; (e) la ventana de cancelación del cajero es estricta (<24 h) y la caja cerrada bloquea incluso al Responsable.

# Uso de IA (Vibe Coding)

**Prompt:** «Analiza este código de dominio de FarmaExpress y estas reglas aprobadas. Propón casos pytest de éxito, error y límite sin inventar reglas nuevas; señala supuestos y ramas sin cobertura.»

**Resultado y corrección:** el primer borrador del servicio descontaba el inventario antes de cobrar; con repositorios en memoria el `rollback` no restaura el stock, por lo que un pago rechazado habría dejado stock perdido. Se corrigió reordenando (validar → cobrar → descontar) y agregando `test_pago_rechazado_no_descuenta_stock_ni_confirma`. También se verificó manualmente que los límites (30/31 días, 24 h exactas, caducidad hoy) coincidieran con las reglas del PIA y no se aceptaron casos que inventaran reglas.

# Reflexión final

El defecto más costoso en producción sería vender un medicamento controlado sin receta válida ni excepción autorizada, o vender un lote bloqueado por recall sanitario. Además del daño económico, implica riesgo para la salud del paciente y sanciones regulatorias de la fiscalización sanitaria. Por eso las pruebas CP-02, CP-04 y CP-13 verifican que el sistema rechace la venta y que el inventario quede intacto gracias al rollback. Aprendimos que un programa que abre y registra ventas puede seguir violando reglas de negocio: solo las pruebas de éxito, error y límite, junto con el pipeline, dan evidencia reproducible. También vimos que la cobertura (98%) mide ejecución, no corrección, y que un caso como el cobro rechazado puede dejar inconsistencias si no se prueba. Por último, la automatización con GitHub Actions evita que un cambio posterior rompa estas reglas sin que nadie lo note. Finalmente, la IA acelera la generación de casos, pero cada expectativa debe contrastarse con las reglas aprobadas del cliente.
