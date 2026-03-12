# PyStrAn 🏗️

**Python Structural Analysis — Pórticos Planos 2D**

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-337%2F337%20passing-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Anteriormente conocido como **PyANES-MF** y luego **PyANES**. Renombrado a **PyStrAn**
> (*Python Structural Analysis*) para reflejar el alcance general del sistema.
---

## 📋 Descripción

PyStrAn es un software de análisis estructural para **pórticos planos 2D** que implementa dos métodos
de resolución complementarios y los combina mediante un solver adaptativo con validación cruzada automática:

| Motor | Método | Incógnitas | Cuándo usarlo |
|-------|--------|-----------|---------------|
| `MotorMetodoFuerzas` | Método de las Fuerzas (MF) | Fuerzas redundantes | Estructuras con pocos redundantes |
| `MotorMetodoDeformaciones` | Método de las Deformaciones (MD) | Desplazamientos nodales | Cualquier estructura, siempre converge |
| `resolver_con_fallback` | Solver Adaptativo (MF+MD) | Ambas | Validación cruzada automática |

### ✨ Características Principales

**Motor de Análisis (MF):**
- ✅ **Análisis hiperestático completo** mediante Método de las Fuerzas
- ✅ **Propagación topológica (BFS)** para calcular M̄ᵢ, N̄ᵢ, V̄ᵢ en pórticos planos con nudos internos libres
- ✅ **Superposición correcta** de reacciones: componentes redundantes = Xᵢ, no redundantes = R⁰ + ΣXᵢ·Rᵢ
- ✅ **Trabajos virtuales** para cálculo de flexibilidades (fᵢⱼ) y términos independientes (e₀ᵢ)
- ✅ **Resolución del SECE** [F]·{X} = -{e₀}
- ✅ **Selección automática de redundantes** con heurística configurable

**Motor de Análisis (MD):**
- ✅ **Método de las Deformaciones** (Método de Rigidez Directo)
- ✅ **Ensamblaje automático** de la matriz de rigidez global [K]
- ✅ **Fuerzas de empotramiento** (FEF) para cargas distribuidas y puntuales sobre barras
- ✅ **Numeración automática** de grados de libertad (GDL)

**Solver Adaptativo:**
- ✅ **Validación cruzada MD↔MF** con tolerancia configurable
- ✅ **Búsqueda iterativa** de combinaciones de redundantes para MF
- ✅ **Fallback automático** a MD cuando MF no converge
- ✅ **Diagnóstico completo**: intentos, combinaciones, max diferencia

**Cargas y Vínculos:**
- ✅ **Cargas térmicas** (variación uniforme y gradiente térmico)
- ✅ **Resortes elásticos** (kx, ky, kθ) como vínculos
- ✅ **Movimientos impuestos** (hundimientos, levantamientos, rotaciones prescritas)

**Resultados y Visualización:**
- ✅ **Diagramas de esfuerzos** (N, V, M) con visualización profesional
- ✅ **Deformada elástica** con factor de escala automático
- ✅ **Interfaz gráfica interactiva** (PyQt6) con canvas drag-and-drop
- ✅ **Serialización de proyectos** en formato JSON (guardar/cargar)
- ✅ **Sistema Undo/Redo** (Ctrl+Z / Ctrl+Y)
- ✅ **Exportación de resultados** en formato PNG (300 DPI)
- ✅ **Suite de 241 tests** automatizados

---

## 🚀 Instalación

### Requisitos Previos

- **Python 3.9** o superior
- pip (gestor de paquetes)

### Pasos de Instalación

```bash
# 1. Clonar o descargar el repositorio
git clone https://github.com/federicoarielcasado/py-anes-mf.git
cd py-anes-mf

# 2. Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar tests para verificar instalación
pytest -v --tb=no -q

# 5. Ejecutar un ejemplo
python examples/ejemplo_visualizacion.py
```

### Dependencias Principales

- **NumPy** (≥1.20): Álgebra lineal
- **SciPy** (≥1.7): Integración numérica
- **Matplotlib** (≥3.5): Visualización de diagramas
- **pytest** (≥7.0): Testing

---

## 📖 Guía de Uso

### Caso 1: Resolver con Solver Adaptativo (recomendado)

El solver adaptativo usa MD como referencia e intenta validar con MF automáticamente:

```python
from src.domain.entities.material import Material
from src.domain.entities.seccion import SeccionPerfil
from src.domain.entities.vinculo import Empotramiento
from src.domain.entities.carga import CargaPuntualBarra
from src.domain.model.modelo_estructural import ModeloEstructural
from src.domain.analysis import resolver_con_fallback

# Definir material y sección
acero = Material(nombre="Acero A-36", E=200e6)
ipe220 = SeccionPerfil(nombre="IPE 220", _A=33.4e-4, _Iz=2772e-8, _h=0.220)

# Crear modelo
modelo = ModeloEstructural("Viga biempotrada")
nA = modelo.agregar_nudo(0.0, 0.0, "A")
nB = modelo.agregar_nudo(6.0, 0.0, "B")
barra = modelo.agregar_barra(nA, nB, acero, ipe220)
modelo.asignar_vinculo(nA.id, Empotramiento())
modelo.asignar_vinculo(nB.id, Empotramiento())

carga = CargaPuntualBarra(barra=barra, P=10.0, a=3.0, angulo=+90)
modelo.agregar_carga(carga)

# Resolver con validación cruzada automática
resultado = resolver_con_fallback(modelo, tol=1e-2, verbose=True)

print(resultado.resumen())
# === Solver Adaptativo ===
#   Metodo exitoso  : ambos
#   Intentos MF     : 1
#   Max diferencia  : 3.55e-14
#   Validacion OK   : True

# Acceder al resultado (MD siempre disponible)
M_centro = resultado.mejor_resultado.M(barra.id, 3.0)
print(f"M(centro) = {M_centro:.3f} kNm")  # ≈ -3.75 kNm

# Si MF también coincidió, ver redundantes
if resultado.ambos_validos:
    for r in resultado.redundantes_usados:
        print(f"  {r.descripcion}: valor en resultados MF")
```

### Caso 2: Método de las Deformaciones directamente

```python
from src.domain.analysis import analizar_estructura_deformaciones

resultado_md = analizar_estructura_deformaciones(modelo)

# Reacciones
for nudo_id, (Rx, Ry, Mz) in resultado_md.reacciones_finales.items():
    print(f"Nudo {nudo_id}: Rx={Rx:+.2f} kN, Ry={Ry:+.2f} kN, Mz={Mz:+.2f} kNm")

# Diagramas
M_en_x = resultado_md.M(barra.id, x=3.0)
V_en_x = resultado_md.V(barra.id, x=3.0)
N_en_x = resultado_md.N(barra.id, x=3.0)
```

### Caso 3: Método de las Fuerzas con selección manual de redundantes

```python
from src.domain.analysis import MotorMetodoFuerzas, Redundante, TipoRedundante

redundantes = [
    Redundante(tipo=TipoRedundante.REACCION_MZ, nudo_id=nA.id, indice=1),
    Redundante(tipo=TipoRedundante.REACCION_MZ, nudo_id=nB.id, indice=2),
]

motor = MotorMetodoFuerzas(modelo, seleccion_manual_redundantes=redundantes)
resultado_mf = motor.resolver()

print(f"X1 = {resultado_mf.Xi(1):.3f} kNm")
print(f"X2 = {resultado_mf.Xi(2):.3f} kNm")
```

### Caso 4: Validación cruzada MF vs MD

```python
from src.domain.analysis import (
    analizar_estructura_deformaciones,
    comparar_resultados,
    MotorMetodoFuerzas,
)

r_md = analizar_estructura_deformaciones(modelo)
r_mf = MotorMetodoFuerzas(modelo).resolver()

comp = comparar_resultados(r_mf, r_md, n_puntos=21, tol=1e-3)
print(f"Coinciden: {comp['coinciden']}")
print(f"Max diferencia: {comp['max_diferencia']:.2e}")
```

### Caso 5: Viga Continua con Hundimiento de Apoyo

```python
from src.domain.entities.vinculo import ApoyoFijo
from src.domain.entities.carga import MovimientoImpuesto

modelo = ModeloEstructural("Viga continua")
nA = modelo.agregar_nudo(0.0, 0.0, "A")
nB = modelo.agregar_nudo(6.0, 0.0, "B")
nC = modelo.agregar_nudo(12.0, 0.0, "C")

modelo.agregar_barra(nA, nB, acero, ipe220)
modelo.agregar_barra(nB, nC, acero, ipe220)

modelo.asignar_vinculo(nA.id, Empotramiento())
modelo.asignar_vinculo(nB.id, ApoyoFijo())
modelo.asignar_vinculo(nC.id, ApoyoFijo())

hundimiento = MovimientoImpuesto(
    nudo=nB,
    delta_x=0.0,
    delta_y=-0.010,   # -10mm (Y+ hacia abajo)
    delta_theta=0.0
)
modelo.agregar_carga(hundimiento)

resultado = resolver_con_fallback(modelo, tol=1e-2)
```

### Caso 6: Visualización de Diagramas

```python
from src.ui.visualization.diagramas import graficar_diagrama_combinado
from src.ui.visualization.deformada import graficar_deformada_elastica

graficar_diagrama_combinado(
    barras=modelo.barras,
    resultado=resultado.mejor_resultado,
    archivo_salida="diagramas_completos.png"
)

graficar_deformada_elastica(
    barras=modelo.barras,
    resultado=resultado.mejor_resultado,
    factor_escala=50.0,
    archivo_salida="deformada.png"
)
```

---

## 📐 Fundamento Teórico

### Método de las Fuerzas (Método de Flexibilidad)

Método clásico para análisis hiperestático. El sistema a resolver es:

```
[F]·{X} = -{e₀}
```

Donde `[F]` es la matriz de flexibilidad (fᵢⱼ calculados por Trabajos Virtuales),
`{X}` son los redundantes y `{e₀}` los términos independientes.

**Pasos:**
1. Calcular GH = r + v - 3n
2. Seleccionar GH redundantes → estructura fundamental isostática
3. Calcular fᵢⱼ = ∫(M̄ᵢ·M̄ⱼ)/(EI) dx y e₀ᵢ = ∫(M̄ᵢ·M⁰)/(EI) dx
4. Resolver [F]·{X} = -{e₀}
5. Superponer: Mₕ = M⁰ + Σ(Xᵢ·M̄ᵢ)

### Método de las Deformaciones (Método de Rigidez)

Método matricial sistemático. El sistema a resolver es:

```
[K]·{d} = {F_ext} - {F_0}
```

Donde `[K]` es la matriz de rigidez global, `{d}` son los desplazamientos nodales libres,
`{F_ext}` las cargas externas nodales y `{F_0}` las fuerzas de empotramiento equivalentes.

**Pasos:**
1. Numerar GDL: nudo i → (3i, 3i+1, 3i+2) = (Ux, Uy, θz)
2. Construir k_local 6×6 (Euler-Bernoulli) por barra
3. Rotar: K_elem = T⁶ · k_local · T⁶ᵀ
4. Ensamblar [K] global (scatter-add)
5. Aplicar condiciones de frontera (GDL restringidos)
6. Resolver el sistema lineal
7. Recuperar esfuerzos por equilibrio local: N(x), V(x), M(x)

### Solver Adaptativo

```
MD (siempre correcto) ──→ resultado de referencia
         │
         ▼
Iterar C(n_cand, GH) combinaciones de redundantes:
  ├─ Descartar inestables
  ├─ Intentar MF con esa combinación
  ├─ Comparar MF vs MD (tolerancia configurable)
  └─ Primera coincidencia → retornar "ambos"
         │
         ▼ (si ninguna coincide)
Retornar solo MD (siempre confiable)
```

### Sistema de Coordenadas (TERNA)

**Convención adoptada en PyStrAn:**

- **X+ → Derecha**
- **Y+ → Abajo** ⬇️ (gravedad positiva)
- **Mz+ → Horario** ⟳

**Ángulos de carga:** `+90°` = hacia abajo ⬇️, `-90°` = hacia arriba ⬆️

**Momentos:** positivo = tracciona fibra inferior (sagging en viga horizontal)

---

## 🧩 Arquitectura del Software

### Estructura de Directorios

```
py-anes-mf/
├── src/
│   ├── domain/
│   │   ├── entities/         # Nudo, Barra, Material, Sección, Carga, Vínculo
│   │   ├── mechanics/        # Equilibrio, cálculo de esfuerzos isostáticos
│   │   ├── analysis/         # Motores de análisis
│   │   │   ├── motor_fuerzas.py           # Motor MF (SECE)
│   │   │   ├── motor_deformaciones.py     # Motor MD (Rigidez)
│   │   │   ├── solver_adaptativo.py       # Solver MF+MD con fallback
│   │   │   ├── fuerzas_empotramiento.py   # FEF para MD
│   │   │   ├── numerador_gdl.py           # Numeración de GDL para MD
│   │   │   ├── redundantes.py             # Selección de redundantes para MF
│   │   │   ├── subestructuras.py          # Generación de M⁰ y Xᵢ
│   │   │   ├── trabajos_virtuales.py      # Cálculo de fᵢⱼ y e₀ᵢ
│   │   │   └── sece_solver.py             # Resolución del SECE
│   │   └── model/            # ModeloEstructural (contenedor)
│   ├── gui/                  # Interfaz gráfica (PyQt6)
│   │   ├── main_window.py
│   │   ├── canvas/           # Canvas interactivo drag-and-drop
│   │   ├── widgets/          # Panel de propiedades y resultados
│   │   ├── dialogs/          # Diálogos de cargas y redundantes
│   │   └── history/          # Gestor Undo/Redo
│   ├── ui/
│   │   └── visualization/    # Diagramas (M,V,N), deformada, geometría
│   ├── utils/                # Constantes, integración numérica
│   └── data/                 # Materiales, secciones, serialización JSON
├── tests/
│   ├── unit/                 # Tests unitarios (motor_fuerzas, motor_deformaciones,
│   │                         #   solver_adaptativo, cargas, vínculos...)
│   ├── integration/          # Tests de integración y casos clásicos
│   └── domain/               # Tests de entidades del dominio
├── examples/                 # Ejemplos didácticos
│   ├── ejemplo_visualizacion.py
│   ├── ejemplo_deformada.py
│   ├── ejemplo_carga_termica.py
│   ├── ejemplo_resortes_elasticos.py
│   ├── ejemplo_movimientos_impuestos.py
│   └── ejemplo_viga_biempotrada_gh1.py
├── docs/
│   ├── teoria/
│   │   ├── NOTAS_CARGAS_TERMICAS.md
│   │   ├── NOTAS_RESORTES_ELASTICOS.md
│   │   ├── NOTAS_MOVIMIENTOS_IMPUESTOS.md
│   │   ├── SELECCION_REDUNDANTES.md
│   │   ├── SISTEMA_COORDENADAS_LOCALES.md
│   │   └── VISUALIZACION.md
│   ├── ARQUITECTURA_PROYECTO.md
│   └── PLANIFICACION_DESARROLLO.md
├── main.py                   # Punto de entrada (lanza GUI)
├── README.md
├── CLAUDE.md                 # Contexto para agentes IA
└── requirements.txt
```

### Flujo de Ejecución

```
ModeloEstructural (nudos, barras, cargas, vínculos)
         │
         ├──→ MotorMetodoDeformaciones.resolver()
         │         [K]{d} = {F} - {F0}
         │         → ResultadoAnalisis (MD)
         │
         ├──→ MotorMetodoFuerzas.resolver()
         │         [F]{X} = -{e0}
         │         → ResultadoAnalisis (MF)
         │
         └──→ resolver_con_fallback()
                   MD como referencia
                   + iteración MF hasta coincidencia
                   → ResultadoAdaptativo
                         .resultado_md
                         .resultado_mf
                         .validacion_cruzada
```

---

## 🧪 Testing

### Suite de Tests Automatizados

PyStrAn cuenta con **337 tests automatizados** que garantizan la corrección de los cálculos:

```bash
# Ejecutar todos los tests
pytest -v --tb=no -q

# Por módulo
pytest tests/unit/test_motor_deformaciones.py -v   # 102 tests MD (resortes + MI + cargas termicas)
pytest tests/unit/test_solver_adaptativo.py -v     # 22 tests Solver Adaptativo
pytest tests/unit/test_carga_termica.py -v         # 20 tests cargas térmicas
pytest tests/unit/test_resorte_elastico.py -v      # 30 tests resortes
pytest tests/integration/ -v                       # casos clásicos de validación

# Ver cobertura
pytest --cov=src --cov-report=html
```

### Casos de Validación

| Caso | GH | Error numérico |
|------|----|---------------|
| Viga biempotrada carga puntual (MF+MD) | 3 | < 0.1% |
| Viga biempotrada carga uniforme (MD) | 2 | < 0.01% |
| Viga simplemente apoyada (MD) | 0 | < 0.01% |
| Pórtico biempotrado carga horizontal (MF+MD) | 3 | < 0.1% |
| Cargas térmicas | — | < 0.5% |
| Movimientos impuestos | — | < 0.1% |

---

## 📚 API Principal

### `resolver_con_fallback`

```python
from src.domain.analysis import resolver_con_fallback

resultado = resolver_con_fallback(
    modelo,
    tol=1e-3,           # Tolerancia [kN, kNm] para comparar MF vs MD
    max_combinaciones=500,  # Limite de combinaciones de redundantes
    verbose=False       # Emitir mensajes de logging
) -> ResultadoAdaptativo
```

**`ResultadoAdaptativo`** — propiedades principales:

| Propiedad | Tipo | Descripción |
|-----------|------|-------------|
| `mejor_resultado` | `ResultadoAnalisis` | Resultado MD (siempre correcto) |
| `resultado_mf` | `ResultadoAnalisis?` | Resultado MF (None si no coincidió) |
| `ambos_validos` | `bool` | True si MF y MD coincidieron |
| `max_diferencia` | `float` | Máxima diferencia MF-MD [kN,kNm] |
| `intentos_mf` | `int` | Combinaciones probadas |
| `redundantes_usados` | `List[Redundante]?` | Combo MF ganadora |
| `resumen()` | `str` | Texto diagnóstico para imprimir |

### `MotorMetodoDeformaciones`

```python
from src.domain.analysis import MotorMetodoDeformaciones, analizar_estructura_deformaciones

motor = MotorMetodoDeformaciones(modelo)
resultado = motor.resolver() -> ResultadoAnalisis

# O la función de conveniencia:
resultado = analizar_estructura_deformaciones(modelo)
```

### `MotorMetodoFuerzas`

```python
from src.domain.analysis import MotorMetodoFuerzas

motor = MotorMetodoFuerzas(
    modelo,
    seleccion_manual_redundantes=None,  # auto si None
    incluir_deformacion_axial=False,
    incluir_deformacion_cortante=False,
    metodo_resolucion="directo"         # "directo", "cholesky", "iterativo"
)
resultado = motor.resolver() -> ResultadoAnalisis
```

### `ResultadoAnalisis` — acceso a resultados

```python
# Esfuerzos en posición x de una barra
resultado.M(barra_id, x)   # Momento flector [kNm]
resultado.V(barra_id, x)   # Cortante [kN]
resultado.N(barra_id, x)   # Axil [kN]

# Reacciones en nudos vinculados
Rx, Ry, Mz = resultado.reacciones_finales[nudo_id]

# Redundantes (solo MF)
resultado.Xi(1)   # Valor del primer redundante
```

---

## 🔬 Precisión Numérica

| Aspecto | Valor |
|---------|-------|
| Integración numérica (MF) | Simpson con subdivisión adaptativa |
| Residual SECE | < 1×10⁻⁸ |
| Condicionamiento [F] | Advertencia si cond(F) > 1×10¹² |
| Tolerancia comparación MF-MD | configurable (default 1×10⁻³) |
| Verificación de equilibrio | \|ΣF\|, \|ΣM\| < 1×10⁻⁶ |

---

## 🎓 Referencias Bibliográficas

1. **Timoshenko, S. & Young, D.H.** (1965). *Theory of Structures*. McGraw-Hill.
2. **Gere, J.M. & Weaver, W.** (1965). *Analysis of Framed Structures*. Van Nostrand.
3. **Hibbeler, R.C.** (2018). *Structural Analysis*. 10th Edition, Pearson.
4. **Weaver, W. & Gere, J.M.** (1990). *Matrix Analysis of Framed Structures*. 3rd Ed.

---

## 📝 Changelog

### v2.2.0 (12 de Marzo de 2026)

**Selector de redundantes y corrección de convenio de signos:**
- ✅ Selector QR de redundantes algebraicamente independientes en `redundantes.py` (`scipy.linalg.qr` con pivoteo de columnas)
- ✅ Árbol generador para redundantes internos: elimina barras por BFS garantizando isostática
- ✅ Corrección de convenio V(x) en `esfuerzos.py`: `return -cortante` — consistente con MD (`V_i = −p_elem_local[1]`)
- ✅ 37 nuevos tests en `test_selector_qr.py` incluyendo validación cruzada MF↔MD para vigas y pórticos (337 total)

### v2.1.0 (12 de Marzo de 2026)

**Motor de Deformaciones (MD) — extensiones:**
- ✅ Soporte de resortes elásticos en MD: `K[i,i] += k`, reacciones `R = −k·δ`, 13 tests nuevos
- ✅ Soporte de movimientos impuestos en MD: BC no homogéneas, `F_eff -= K[:,p]·δ`, 22 tests nuevos
- ✅ Soporte de cargas térmicas en MD: FEF axiales y de gradiente en `CalculadorFuerzasEmpotramiento`, 24 tests nuevos

### v2.0.0 (11 de Marzo de 2026)

**Incorporado:**
- ✅ Motor completo del Método de las Deformaciones (`MotorMetodoDeformaciones`)
- ✅ Ensamblaje de matriz de rigidez global [K] con transformación de coordenadas
- ✅ Calculador de Fuerzas de Empotramiento (FEF) — cargas distribuidas y puntuales
- ✅ Numerador de GDL automático (`NumeradorGDL`)
- ✅ Solver Adaptativo con búsqueda iterativa de redundantes (`resolver_con_fallback`)
- ✅ Validación cruzada automática MF↔MD (`comparar_resultados`)
- ✅ 65 nuevos tests automatizados (241 total)
- ✅ Renombrado de PyANES-MF → PyANES → PyStrAn

### v1.0.0 (19 de Febrero de 2026)

**Implementado:**
- ✅ Motor completo del Método de las Fuerzas
- ✅ Trabajos virtuales con integración numérica
- ✅ Resolución del SECE con múltiples métodos
- ✅ Diagramas de esfuerzos (M, V, N) y deformada elástica
- ✅ Cargas térmicas, resortes elásticos, movimientos impuestos
- ✅ Interfaz gráfica PyQt6 con drag-and-drop
- ✅ 176 tests automatizados

---

## 📄 Licencia

Este proyecto está licenciado bajo la **Licencia MIT** - ver el archivo [LICENSE](LICENSE) para más detalles.

---

## 👨‍💻 Autor

**Federico** - Ingeniería Civil

- 🎓 Especialización: Análisis estructural avanzado
- 💻 Stack técnico: Python, NumPy, SciPy, Matplotlib, PyQt6
- 📚 Dominio: Método de las Fuerzas, Método de las Deformaciones, Trabajos Virtuales

---

*Última actualización: 11 de Marzo de 2026*
