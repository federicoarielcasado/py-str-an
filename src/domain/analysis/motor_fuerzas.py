"""
Motor principal del Método de las Fuerzas.

Este módulo orquesta todo el proceso de análisis hiperestático:
1. Validación del modelo
2. Cálculo del grado de hiperestaticidad
3. Selección de redundantes
4. Generación de subestructuras
5. Cálculo de esfuerzos en subestructuras
6. Cálculo de coeficientes de flexibilidad (trabajos virtuales)
7. Resolución del SECE
8. Superposición de resultados
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Callable

import numpy as np
from numpy.typing import NDArray

from src.domain.analysis.redundantes import (
    SelectorRedundantes,
    Redundante,
    TipoRedundante,
)
from src.domain.analysis.subestructuras import (
    GeneradorSubestructuras,
    Subestructura,
)
from src.domain.analysis.trabajos_virtuales import (
    CalculadorFlexibilidad,
    CoeficientesFlexibilidad,
)
from src.domain.analysis.sece_solver import (
    SolverSECE,
    SolucionSECE,
    resolver_sece,
)
from src.domain.mechanics.esfuerzos import DiagramaEsfuerzos
from src.utils.constants import TOLERANCE, CONDITION_NUMBER_WARNING

if TYPE_CHECKING:
    from src.domain.model.modelo_estructural import ModeloEstructural
    from src.domain.entities.barra import Barra
    from src.domain.entities.nudo import Nudo


class EstadoAnalisis(Enum):
    """Estados posibles del motor de análisis."""
    NO_INICIADO = auto()
    VALIDADO = auto()
    HIPERESTATICIDAD_CALCULADA = auto()
    REDUNDANTES_SELECCIONADOS = auto()
    SUBESTRUCTURAS_GENERADAS = auto()
    ESFUERZOS_CALCULADOS = auto()
    SECE_ENSAMBLADO = auto()
    SECE_RESUELTO = auto()
    RESULTADOS_CALCULADOS = auto()
    ERROR = auto()


@dataclass
class ResultadoAnalisis:
    """
    Resultado completo del análisis por el Método de las Fuerzas.

    Attributes:
        exitoso: True si el análisis se completó sin errores
        grado_hiperestaticidad: Valor de GH
        redundantes: Lista de redundantes seleccionados
        valores_X: Valores de los redundantes resueltos
        reacciones_finales: Reacciones en vínculos {nudo_id: (Rx, Ry, Mz)}
        diagramas_finales: Diagramas de esfuerzos finales {barra_id: DiagramaEsfuerzos}
        advertencias: Lista de advertencias generadas
        errores: Lista de errores (si hubo)
    """
    exitoso: bool = False
    grado_hiperestaticidad: int = 0
    redundantes: List[Redundante] = field(default_factory=list)
    valores_X: Optional[NDArray[np.float64]] = None
    reacciones_finales: Dict[int, Tuple[float, float, float]] = field(default_factory=dict)
    diagramas_finales: Dict[int, DiagramaEsfuerzos] = field(default_factory=dict)
    advertencias: List[str] = field(default_factory=list)
    errores: List[str] = field(default_factory=list)

    # Resultados intermedios para inspección
    matriz_F: Optional[NDArray[np.float64]] = None
    vector_e0: Optional[NDArray[np.float64]] = None
    condicionamiento: float = 1.0
    residual_sece: float = 0.0

    def Xi(self, i: int) -> float:
        """
        Obtiene el valor del redundante Xi.

        Args:
            i: Índice del redundante (1-indexed)

        Returns:
            Valor de Xi
        """
        if self.valores_X is None:
            raise ValueError("No hay solución disponible")
        return self.valores_X[i - 1]

    def obtener_reaccion(self, nudo_id: int) -> Tuple[float, float, float]:
        """
        Obtiene las reacciones finales en un nudo.

        Args:
            nudo_id: ID del nudo

        Returns:
            Tupla (Rx, Ry, Mz)
        """
        return self.reacciones_finales.get(nudo_id, (0.0, 0.0, 0.0))

    def M(self, barra_id: int, x: float) -> float:
        """
        Obtiene el momento flector final en una posición.

        Args:
            barra_id: ID de la barra
            x: Posición desde el nudo i [m]

        Returns:
            Momento flector M(x) [kNm]
        """
        if barra_id not in self.diagramas_finales:
            return 0.0
        return self.diagramas_finales[barra_id].M(x)

    def V(self, barra_id: int, x: float) -> float:
        """
        Obtiene el cortante final en una posición.

        Args:
            barra_id: ID de la barra
            x: Posición desde el nudo i [m]

        Returns:
            Esfuerzo cortante V(x) [kN]
        """
        if barra_id not in self.diagramas_finales:
            return 0.0
        return self.diagramas_finales[barra_id].V(x)

    def N(self, barra_id: int, x: float) -> float:
        """
        Obtiene el axil final en una posición.

        Args:
            barra_id: ID de la barra
            x: Posición desde el nudo i [m]

        Returns:
            Esfuerzo axil N(x) [kN]
        """
        if barra_id not in self.diagramas_finales:
            return 0.0
        return self.diagramas_finales[barra_id].N(x)


class MotorMetodoFuerzas:
    """
    Motor principal del Método de las Fuerzas.

    Coordina todo el proceso de análisis estructural hiperestático:

    1. VALIDACIÓN: Verificar modelo (geometría, materiales, conectividad)
    2. HIPERESTATICIDAD: Calcular GH = r + 3c - 3n
    3. REDUNDANTES: Seleccionar redundantes (automático o manual)
    4. SUBESTRUCTURAS: Generar fundamental + Xi con cargas unitarias
    5. ESFUERZOS: Calcular N, V, M en cada subestructura (isostática)
    6. TRABAJOS VIRTUALES: Calcular fij y e0i
    7. SECE: Ensamblar y resolver [F]·{X} = -{e0}
    8. SUPERPOSICIÓN: Mh = M0 + Σ(Xi·Mi)

    Example:
        >>> modelo = ModeloEstructural("Viga biempotrada")
        >>> # ... definir nudos, barras, vínculos, cargas ...
        >>> motor = MotorMetodoFuerzas(modelo)
        >>> resultado = motor.resolver()
        >>> print(f"X1 = {resultado.Xi(1):.3f}")
        >>> print(f"M(L/2) = {resultado.M(1, 3.0):.3f} kNm")
    """

    def __init__(
        self,
        modelo: ModeloEstructural,
        seleccion_manual_redundantes: Optional[List[Redundante]] = None,
        incluir_deformacion_axial: bool = False,
        incluir_deformacion_cortante: bool = False,
        metodo_resolucion: str = "directo",
    ):
        """
        Inicializa el motor de análisis.

        Args:
            modelo: Modelo estructural a analizar
            seleccion_manual_redundantes: Redundantes seleccionados manualmente
                (si None, se seleccionan automáticamente)
            incluir_deformacion_axial: Si True, incluye efecto axial en fij
            incluir_deformacion_cortante: Si True, incluye efecto cortante
            metodo_resolucion: "directo", "cholesky", o "iterativo"
        """
        self.modelo = modelo
        self.seleccion_manual = seleccion_manual_redundantes
        self.incluir_axial = incluir_deformacion_axial
        self.incluir_cortante = incluir_deformacion_cortante
        self.metodo_resolucion = metodo_resolucion

        # Estado interno
        self._estado = EstadoAnalisis.NO_INICIADO
        self._advertencias: List[str] = []
        self._errores: List[str] = []

        # Resultados intermedios
        self._gh: int = 0
        self._redundantes: List[Redundante] = []
        self._fundamental: Optional[Subestructura] = None
        self._subestructuras_xi: List[Subestructura] = []
        self._coeficientes: Optional[CoeficientesFlexibilidad] = None
        self._solucion_sece: Optional[SolucionSECE] = None

    @property
    def estado(self) -> EstadoAnalisis:
        """Estado actual del análisis."""
        return self._estado

    @property
    def grado_hiperestaticidad(self) -> int:
        """Grado de hiperestaticidad calculado."""
        return self._gh

    def resolver(self) -> ResultadoAnalisis:
        """
        Ejecuta el análisis completo por el Método de las Fuerzas.

        Returns:
            ResultadoAnalisis con todos los resultados y diagramas

        Raises:
            ValueError: Si el modelo es inválido o hipostático
        """
        try:
            # 1. Validar modelo
            self._validar_modelo()
            self._estado = EstadoAnalisis.VALIDADO

            # 2. Calcular grado de hiperestaticidad
            self._calcular_hiperestaticidad()
            self._estado = EstadoAnalisis.HIPERESTATICIDAD_CALCULADA

            # Verificar tipo de estructura
            if self._gh < 0:
                raise ValueError(
                    f"Estructura hipostática (GH = {self._gh}). "
                    f"Faltan {abs(self._gh)} vínculos o la geometría es inestable."
                )

            if self._gh == 0:
                # Estructura isostática: resolver directamente
                return self._resolver_isostatica()

            # 3. Seleccionar redundantes
            self._seleccionar_redundantes()
            self._estado = EstadoAnalisis.REDUNDANTES_SELECCIONADOS

            # 4. Generar subestructuras
            self._generar_subestructuras()
            self._estado = EstadoAnalisis.SUBESTRUCTURAS_GENERADAS

            # 5. Calcular esfuerzos en subestructuras
            self._calcular_esfuerzos_subestructuras()
            self._estado = EstadoAnalisis.ESFUERZOS_CALCULADOS

            # 6. Calcular coeficientes de flexibilidad
            self._calcular_coeficientes_flexibilidad()
            self._estado = EstadoAnalisis.SECE_ENSAMBLADO

            # 7. Resolver SECE
            self._resolver_sece()
            self._estado = EstadoAnalisis.SECE_RESUELTO

            # 8. Superponer resultados
            resultado = self._superponer_resultados()
            self._estado = EstadoAnalisis.RESULTADOS_CALCULADOS

            return resultado

        except Exception as e:
            self._estado = EstadoAnalisis.ERROR
            self._errores.append(str(e))

            return ResultadoAnalisis(
                exitoso=False,
                grado_hiperestaticidad=self._gh,
                redundantes=self._redundantes,
                advertencias=self._advertencias.copy(),
                errores=self._errores.copy(),
            )

    def _validar_modelo(self) -> None:
        """
        Valida que el modelo sea apto para análisis.

        Verifica:
        - Al menos 2 nudos
        - Al menos 1 barra
        - Geometría válida (barras con L > 0)
        - Materiales válidos (E > 0, A > 0, I > 0)
        - Estructura conexa (opcional)
        """
        # Verificar mínimos
        if len(self.modelo.nudos) < 2:
            raise ValueError("El modelo debe tener al menos 2 nudos")

        if len(self.modelo.barras) < 1:
            raise ValueError("El modelo debe tener al menos 1 barra")

        # Verificar barras
        for barra in self.modelo.barras:
            if barra.L < TOLERANCE:
                raise ValueError(
                    f"Barra {barra.id} tiene longitud nula o negativa ({barra.L:.6f} m)"
                )

            if barra.material.E <= 0:
                raise ValueError(
                    f"Barra {barra.id}: módulo de elasticidad inválido ({barra.material.E})"
                )

            if barra.seccion.A <= 0:
                raise ValueError(
                    f"Barra {barra.id}: área de sección inválida ({barra.seccion.A})"
                )

            if barra.seccion.Iz <= 0:
                raise ValueError(
                    f"Barra {barra.id}: momento de inercia inválido ({barra.seccion.Iz})"
                )

        # Verificar que hay vínculos
        if self.modelo.num_reacciones == 0:
            raise ValueError("El modelo no tiene vínculos externos")

    def _calcular_hiperestaticidad(self) -> None:
        """
        Calcula el grado de hiperestaticidad.

        Fórmula: GH = r + 3c - 3n - articulaciones_internas

        Donde:
        - r: número de reacciones de vínculo
        - c: número de barras
        - n: número de nudos
        """
        self._gh = self.modelo.grado_hiperestaticidad

        if self._gh > 0:
            self._advertencias.append(
                f"Estructura hiperestática de grado {self._gh}. "
                f"Se resolverá por el Método de las Fuerzas."
            )
        elif self._gh == 0:
            self._advertencias.append(
                "Estructura isostática. Se resolverá directamente por equilibrio."
            )

    def _seleccionar_redundantes(self) -> None:
        """
        Selecciona los redundantes para el análisis.

        Usa selección manual si se proporcionó, o automática en caso contrario.
        """
        if self.seleccion_manual is not None:
            # Validar que la cantidad coincide
            if len(self.seleccion_manual) != self._gh:
                raise ValueError(
                    f"Se proporcionaron {len(self.seleccion_manual)} redundantes "
                    f"pero el grado de hiperestaticidad es {self._gh}"
                )
            self._redundantes = self.seleccion_manual

        else:
            # Selección automática
            selector = SelectorRedundantes(self.modelo)
            self._redundantes = selector.seleccionar_automatico()

        # Registrar redundantes seleccionados
        for i, red in enumerate(self._redundantes):
            self._advertencias.append(
                f"Redundante X{i+1}: {red.descripcion}"
            )

    def _generar_subestructuras(self) -> None:
        """
        Genera la estructura fundamental y las subestructuras Xi.
        """
        generador = GeneradorSubestructuras(
            nudos=self.modelo.nudos,
            barras=self.modelo.barras,
            cargas=self.modelo.cargas,
            redundantes=self._redundantes,
        )

        self._fundamental, self._subestructuras_xi = generador.generar_todas()

    def _calcular_esfuerzos_subestructuras(self) -> None:
        """
        Calcula N, V, M en cada subestructura.

        Para la fundamental: esfuerzos por cargas reales
        Para Xi: esfuerzos por carga unitaria
        """
        # Los esfuerzos ya se calculan en GeneradorSubestructuras
        # Aquí verificamos que estén disponibles

        if self._fundamental is None:
            raise ValueError("Estructura fundamental no generada")

        for sub in self._subestructuras_xi:
            if len(sub.diagramas) == 0:
                self._advertencias.append(
                    f"Subestructura {sub.nombre} no tiene diagramas calculados"
                )

    def _calcular_coeficientes_flexibilidad(self) -> None:
        """
        Calcula la matriz de flexibilidad F y el vector e0.

        Usa el Teorema de Trabajos Virtuales:
        - fij = ∫(Mi × Mj)/(EI) dx + [axial + cortante]
        - e0i = ∫(Mi × M0)/(EI) dx + [axial + térmico]
        """
        # Filtrar cargas térmicas del modelo
        from src.domain.entities.carga import CargaTermica, MovimientoImpuesto
        cargas_termicas = [c for c in self.modelo.cargas if isinstance(c, CargaTermica)]
        movimientos_impuestos = [c for c in self.modelo.cargas if isinstance(c, MovimientoImpuesto)]

        calculador = CalculadorFlexibilidad(
            barras=self.modelo.barras,
            fundamental=self._fundamental,
            subestructuras_xi=self._subestructuras_xi,
            incluir_axil=self.incluir_axial,
            incluir_cortante=self.incluir_cortante,
            cargas_termicas=cargas_termicas,
            redundantes=self._redundantes,
            nudos=self.modelo.nudos,
            movimientos_impuestos=movimientos_impuestos,
        )

        # Usar tabla de Mohr solo si NO se incluyen efectos axiales o cortantes
        # (Mohr solo funciona para flexión)
        if not self.incluir_axial and not self.incluir_cortante:
            try:
                self._coeficientes = calculador.calcular_con_tabla_mohr()
            except Exception:
                # Fallback a integración numérica
                self._coeficientes = calculador.calcular()
        else:
            # Con axil o cortante, usar integración numérica directamente
            self._coeficientes = calculador.calcular()

        # Verificar resultados
        if not self._coeficientes.es_simetrica:
            self._advertencias.append(
                "La matriz de flexibilidad no es simétrica. "
                "Esto puede indicar un error en el cálculo de esfuerzos."
            )

        if self._coeficientes.condicionamiento > CONDITION_NUMBER_WARNING:
            # Distinguir entre mal condicionamiento real y redundantes con
            # contribución nula en flexión (p.ej. Rx en viga horizontal con
            # cargas solo verticales → fii = 0 es físicamente correcto).
            F = self._coeficientes.F
            ceros_diagonales = [
                i for i in range(len(F))
                if abs(F[i, i]) < TOLERANCE
            ]
            if ceros_diagonales:
                for idx in ceros_diagonales:
                    red = self._redundantes[idx]
                    self._advertencias.append(
                        f"Redundante X{idx+1} ({red.descripcion}): "
                        f"su diagrama de momentos es nulo para las cargas "
                        f"aplicadas (fii = 0). Su valor sera 0 por equilibrio "
                        f"y no indica inestabilidad real de la estructura."
                    )
            else:
                self._advertencias.append(
                    f"Matriz de flexibilidad mal condicionada "
                    f"(cond = {self._coeficientes.condicionamiento:.2e}). "
                    "Considere reseleccionar redundantes."
                )

    def _calcular_movimientos_impuestos_en_redundantes(self) -> NDArray[np.float64]:
        """
        Construye el vector δₕ con movimientos impuestos en direcciones de redundantes.

        Este vector modifica el lado derecho del SECE:
        [F]·{X} = -{e₀} - {δₕ}

        REGLA: Solo los movimientos que coinciden con redundantes van a δₕ.
        Los movimientos en otros nudos contribuyen a e₀ᵢ (ya calculado).

        Returns:
            Vector δₕ de dimensión (n_redundantes,)
        """
        from src.domain.entities.carga import MovimientoImpuesto

        n = len(self._redundantes)
        eh = np.zeros(n, dtype=np.float64)

        # Obtener movimientos impuestos del modelo
        movimientos_impuestos = [
            c for c in self.modelo.cargas if isinstance(c, MovimientoImpuesto)
        ]

        if not movimientos_impuestos:
            return eh

        # Para cada redundante, buscar si hay movimiento impuesto en ese nudo
        for i, redundante in enumerate(self._redundantes):
            for movimiento in movimientos_impuestos:
                if not movimiento.nudo or movimiento.nudo.id != redundante.nudo_id:
                    continue

                # Asignar movimiento según tipo de redundante
                if redundante.tipo == TipoRedundante.REACCION_RX:
                    eh[i] = movimiento.delta_x
                elif redundante.tipo == TipoRedundante.REACCION_RY:
                    eh[i] = movimiento.delta_y
                elif redundante.tipo == TipoRedundante.REACCION_MZ:
                    eh[i] = movimiento.delta_theta

        return eh

    def _resolver_sece(self) -> None:
        """
        Resuelve el Sistema de Ecuaciones de Compatibilidad Elástica.

        [F]·{X} = {eₕ} - {e0}

        Con movimientos impuestos: eₕ ≠ 0
        Sin movimientos impuestos: eₕ = 0 → [F]·{X} = -{e0}
        """
        # Calcular vector de movimientos impuestos en redundantes
        eh = self._calcular_movimientos_impuestos_en_redundantes()

        self._solucion_sece = resolver_sece(
            F=self._coeficientes.F,
            e0=self._coeficientes.e0,
            eh=eh,
            metodo=self.metodo_resolucion,
        )

        # Agregar advertencias del solver
        self._advertencias.extend(self._solucion_sece.advertencias)

        if not self._solucion_sece.es_valida:
            raise ValueError(
                "La solución del SECE no es válida. "
                f"Residual: {self._solucion_sece.residual:.2e}"
            )

    def _superponer_resultados(self) -> ResultadoAnalisis:
        """
        Superpone los diagramas finales.

        Mh = M0 + Σ(Xi × Mi)
        Vh = V0 + Σ(Xi × Vi)
        Nh = N0 + Σ(Xi × Ni)
        Rh = R0 + Σ(Xi × Ri)

        Returns:
            ResultadoAnalisis con todos los resultados
        """
        X = self._solucion_sece.X
        diagramas_finales: Dict[int, DiagramaEsfuerzos] = {}
        reacciones_finales: Dict[int, Tuple[float, float, float]] = {}

        # Superponer diagramas para cada barra
        for barra in self.modelo.barras:
            # Obtener diagrama fundamental
            diag_0 = self._fundamental.diagramas.get(barra.id)

            if diag_0 is None:
                continue

            # Crear funciones de superposición
            def M_final(x: float, b=barra) -> float:
                M = self._fundamental.M(b.id, x)
                for i, Xi in enumerate(X):
                    M += Xi * self._subestructuras_xi[i].M(b.id, x)
                return M

            def V_final(x: float, b=barra) -> float:
                V = self._fundamental.V(b.id, x)
                for i, Xi in enumerate(X):
                    V += Xi * self._subestructuras_xi[i].V(b.id, x)
                return V

            def N_final(x: float, b=barra) -> float:
                N = self._fundamental.N(b.id, x)
                for i, Xi in enumerate(X):
                    N += Xi * self._subestructuras_xi[i].N(b.id, x)
                return N

            # Crear diagrama final
            # Muestrear valores en extremos para almacenar
            Mi = M_final(0)
            Mj = M_final(barra.L)

            diagramas_finales[barra.id] = DiagramaEsfuerzos(
                barra_id=barra.id,
                L=barra.L,
                Mi=Mi,
                Mj=Mj,
                _M_func=M_final,
                _V_func=V_final,
                _N_func=N_final,
            )

        # Superponer reacciones
        #
        # En el Método de las Fuerzas, la reacción final en cada nudo se calcula:
        #
        #   - Para componentes REDUNDANTES (ej: Mz en empotramiento liberado):
        #     La reacción final ES el valor Xi resuelto.
        #
        #   - Para componentes NO REDUNDANTES (ej: Ry en apoyo fijo de la fundamental):
        #     La reacción final es R0 de la estructura fundamental.
        #     La fundamental fue resuelta bajo las cargas reales, con los vínculos
        #     no-redundantes activos; su equilibrio ya es el correcto.
        #
        # Nota: la verificación de equilibrio global (verificar_equilibrio_global)
        # usa la fórmula completa R0+ΣXi·Ri internamente para comprobar ΣF=0,
        # independientemente de lo que se almacene en reacciones_finales.
        from src.domain.analysis.redundantes import TipoRedundante

        # Construir mapa {(nudo_id, componente) → valor_Xi}
        redundante_map: Dict[Tuple[int, str], float] = {}
        for i, red in enumerate(self._redundantes):
            if red.nudo_id is None:
                continue
            if red.tipo == TipoRedundante.REACCION_RX:
                redundante_map[(red.nudo_id, "Rx")] = float(X[i])
            elif red.tipo == TipoRedundante.REACCION_RY:
                redundante_map[(red.nudo_id, "Ry")] = float(X[i])
            elif red.tipo == TipoRedundante.REACCION_MZ:
                redundante_map[(red.nudo_id, "Mz")] = float(X[i])

        for nudo in self.modelo.nudos:
            if not nudo.tiene_vinculo:
                continue

            R0 = self._fundamental.obtener_reaccion(nudo.id)

            # Para componentes redundantes: el valor Xi ES la reacción final.
            # Para componentes no redundantes: usar R0 (la fundamental ya incorpora
            # el equilibrio bajo las cargas reales; la superposición cruzada Xi·Ri
            # no es aplicable porque las reacciones de las subestructuras Xi no
            # representan contribuciones a GDL distintos del propio redundante).
            Rx = redundante_map.get((nudo.id, "Rx"), R0[0])
            Ry = redundante_map.get((nudo.id, "Ry"), R0[1])
            Mz = redundante_map.get((nudo.id, "Mz"), R0[2])

            reacciones_finales[nudo.id] = (Rx, Ry, Mz)

        # Calcular desplazamientos en resortes elásticos
        self._calcular_desplazamientos_resortes(X, reacciones_finales)

        # Crear resultado final
        return ResultadoAnalisis(
            exitoso=True,
            grado_hiperestaticidad=self._gh,
            redundantes=self._redundantes,
            valores_X=X,
            reacciones_finales=reacciones_finales,
            diagramas_finales=diagramas_finales,
            advertencias=self._advertencias.copy(),
            errores=[],
            matriz_F=self._coeficientes.F,
            vector_e0=self._coeficientes.e0,
            condicionamiento=self._coeficientes.condicionamiento,
            residual_sece=self._solucion_sece.residual,
        )

    def _calcular_desplazamientos_resortes(
        self,
        X: NDArray,
        reacciones: Dict[int, Tuple[float, float, float]]
    ) -> None:
        """
        Calcula desplazamientos en resortes elásticos usando R = -k × δ.

        Para cada resorte con rigidez k:
        - δ = R / k (desplazamiento producido por la reacción)

        IMPORTANTE: La constante k debe ser definida por el usuario al crear
        el ResorteElastico.

        Args:
            X: Vector de redundantes resueltos
            reacciones: Reacciones finales en cada nudo
        """
        from src.domain.entities.vinculo import ResorteElastico
        from src.domain.analysis.redundantes import TipoRedundante

        for i, redundante in enumerate(self._redundantes):
            # Obtener nudo asociado
            nudo = next((n for n in self.modelo.nudos if n.id == redundante.nudo_id), None)

            if nudo is None or not isinstance(nudo.vinculo, ResorteElastico):
                continue

            resorte = nudo.vinculo
            Xi = X[i]  # Valor del redundante (= reacción en el resorte)

            # Calcular desplazamiento según tipo de redundante
            # δ = R / k (con signo adecuado)

            if redundante.tipo == TipoRedundante.REACCION_RX and resorte.kx > 0:
                # Desplazamiento horizontal
                # Rx = -kx × Ux → Ux = -Rx / kx = -Xi / kx
                desplazamiento_x = -Xi / resorte.kx
                # Almacenar reacción en el vínculo y desplazamiento en el nudo
                resorte.Rx = Xi
                nudo.Ux = desplazamiento_x

            elif redundante.tipo == TipoRedundante.REACCION_RY and resorte.ky > 0:
                # Desplazamiento vertical
                # Ry = -ky × Uy → Uy = -Ry / ky = -Xi / ky
                desplazamiento_y = -Xi / resorte.ky
                # Almacenar reacción en el vínculo y desplazamiento en el nudo
                resorte.Ry = Xi
                nudo.Uy = desplazamiento_y

            elif redundante.tipo == TipoRedundante.REACCION_MZ and resorte.ktheta > 0:
                # Rotación
                # Mz = -kθ × θz → θz = -Mz / kθ = -Xi / kθ
                rotacion_z = -Xi / resorte.ktheta
                # Almacenar reacción en el vínculo y rotación en el nudo
                resorte.Mz = Xi
                nudo.theta_z = rotacion_z

    def _resolver_isostatica(self) -> ResultadoAnalisis:
        """
        Resuelve una estructura isostática directamente.

        Returns:
            ResultadoAnalisis para estructura isostática
        """
        from src.domain.mechanics.equilibrio import resolver_reacciones_isostatica
        from src.domain.mechanics.esfuerzos import calcular_esfuerzos_viga_isostatica

        # Resolver reacciones
        try:
            resultado_equilibrio = resolver_reacciones_isostatica(
                self.modelo.nudos,
                self.modelo.barras,
                self.modelo.cargas,
            )
        except Exception as e:
            return ResultadoAnalisis(
                exitoso=False,
                grado_hiperestaticidad=0,
                errores=[f"Error al resolver equilibrio: {e}"],
                advertencias=self._advertencias,
            )

        # Calcular esfuerzos
        diagramas_finales: Dict[int, DiagramaEsfuerzos] = {}

        for barra in self.modelo.barras:
            cargas_barra = [
                c for c in self.modelo.cargas
                if hasattr(c, 'barra') and c.barra == barra
            ]

            reac_i = resultado_equilibrio.reacciones.get(barra.nudo_i.id, (0, 0, 0))
            reac_j = resultado_equilibrio.reacciones.get(barra.nudo_j.id, (0, 0, 0))

            diagrama = calcular_esfuerzos_viga_isostatica(
                barra, cargas_barra, reac_i, reac_j
            )
            diagramas_finales[barra.id] = diagrama

        return ResultadoAnalisis(
            exitoso=True,
            grado_hiperestaticidad=0,
            reacciones_finales=resultado_equilibrio.reacciones,
            diagramas_finales=diagramas_finales,
            advertencias=self._advertencias.copy(),
        )

    # =========================================================================
    # MÉTODOS DE VERIFICACIÓN
    # =========================================================================

    def verificar_equilibrio_global(self) -> Tuple[bool, Dict[str, float]]:
        """
        Verifica que las reacciones satisfagan el equilibrio global.

        ΣFx = 0, ΣFy = 0, ΣMz = 0

        Suma cargas externas aplicadas y reacciones finales (superposición
        R_final = R0 + ΣXi·Ri) y comprueba que el residual sea nulo.

        Returns:
            Tupla (equilibrio_satisfecho, residuales)
        """
        if self._estado != EstadoAnalisis.RESULTADOS_CALCULADOS:
            raise ValueError("Primero debe ejecutar el análisis")

        # --- 1. Sumar cargas aplicadas (fuerzas y momentos externos) ---
        Fx_cargas = 0.0
        Fy_cargas = 0.0
        Mz_cargas = 0.0

        import math as _math
        from src.domain.entities.carga import (
            CargaPuntualNudo, CargaPuntualBarra, CargaDistribuida
        )

        # Momento de una fuerza (Fx, Fy) en (x, y) respecto al origen:
        # M = -Fy*(0 - x) + Fx*(0 - y) = Fy*x - Fx*y
        def _mz_fuerza(Fx_f, Fy_f, x_f, y_f):
            return Fy_f * x_f - Fx_f * y_f

        for carga in self.modelo.cargas:
            if isinstance(carga, CargaPuntualNudo):
                Fx_cargas += carga.Fx
                Fy_cargas += carga.Fy
                x_n = carga.nudo.x
                y_n = carga.nudo.y
                Mz_cargas += _mz_fuerza(carga.Fx, carga.Fy, x_n, y_n) + carga.Mz
            elif isinstance(carga, CargaPuntualBarra):
                alpha = carga.barra.angulo
                ang_rad = _math.radians(carga.angulo)
                Px_local = carga.P * _math.cos(ang_rad)
                Py_local = carga.P * _math.sin(ang_rad)
                Fx_g = Px_local * _math.cos(alpha) - Py_local * _math.sin(alpha)
                Fy_g = Px_local * _math.sin(alpha) + Py_local * _math.cos(alpha)
                x_app = carga.barra.nudo_i.x + carga.a * _math.cos(alpha)
                y_app = carga.barra.nudo_i.y + carga.a * _math.sin(alpha)
                Fx_cargas += Fx_g
                Fy_cargas += Fy_g
                Mz_cargas += _mz_fuerza(Fx_g, Fy_g, x_app, y_app)
            elif isinstance(carga, CargaDistribuida):
                barra = carga.barra
                alpha = barra.angulo
                x1 = carga.x1
                x2 = carga.x2 if carga.x2 is not None else barra.L
                L_carga = x2 - x1
                resultante = (carga.q1 + carga.q2) / 2.0 * L_carga
                ang_rad = _math.radians(carga.angulo)
                Px_local = resultante * _math.cos(ang_rad)
                Py_local = resultante * _math.sin(ang_rad)
                Fx_g = Px_local * _math.cos(alpha) - Py_local * _math.sin(alpha)
                Fy_g = Px_local * _math.sin(alpha) + Py_local * _math.cos(alpha)
                Fx_cargas += Fx_g
                Fy_cargas += Fy_g
                suma_q = carga.q1 + carga.q2
                if abs(suma_q) > 1e-10:
                    x_centroide_local = x1 + L_carga * (carga.q1 + 2*carga.q2) / (3*suma_q)
                else:
                    x_centroide_local = x1 + L_carga / 2.0
                x_app = barra.nudo_i.x + x_centroide_local * _math.cos(alpha)
                y_app = barra.nudo_i.y + x_centroide_local * _math.sin(alpha)
                Mz_cargas += _mz_fuerza(Fx_g, Fy_g, x_app, y_app)

        # --- 2. Sumar reacciones finales (superposición) ---
        # R_final = R0 + ΣXi·Ri  (reconstruido desde subestructuras internas)
        Rx_reac = 0.0
        Ry_reac = 0.0
        Mz_reac = 0.0

        X = self._solucion_sece.X if self._solucion_sece is not None else []

        # Mapa de redundantes para override de componentes redundantes
        from src.domain.analysis.redundantes import TipoRedundante
        redundante_map: Dict[Tuple[int, str], float] = {}
        for i, red in enumerate(self._redundantes):
            if red.nudo_id is None:
                continue
            if red.tipo == TipoRedundante.REACCION_RX:
                redundante_map[(red.nudo_id, "Rx")] = float(X[i])
            elif red.tipo == TipoRedundante.REACCION_RY:
                redundante_map[(red.nudo_id, "Ry")] = float(X[i])
            elif red.tipo == TipoRedundante.REACCION_MZ:
                redundante_map[(red.nudo_id, "Mz")] = float(X[i])

        for nudo in self.modelo.nudos:
            if not nudo.tiene_vinculo:
                continue

            # Superposición: R0 + ΣXi·Ri
            R0 = self._fundamental.obtener_reaccion(nudo.id)
            Rx, Ry, Mz_r = R0[0], R0[1], R0[2]
            for i, Xi in enumerate(X):
                Ri = self._subestructuras_xi[i].obtener_reaccion(nudo.id)
                Rx += float(Xi) * Ri[0]
                Ry += float(Xi) * Ri[1]
                Mz_r += float(Xi) * Ri[2]

            # Para componentes redundantes: el valor Xi ES la reacción final
            Rx = redundante_map.get((nudo.id, "Rx"), Rx)
            Ry = redundante_map.get((nudo.id, "Ry"), Ry)
            Mz_r = redundante_map.get((nudo.id, "Mz"), Mz_r)

            Rx_reac += Rx
            Ry_reac += Ry
            # Momento de la reacción respecto al origen: fuerzas + momento puro
            Mz_reac += _mz_fuerza(Rx, Ry, nudo.x, nudo.y) + Mz_r

        # --- 3. Residuales: ΣFuerzas_externas + ΣReacciones = 0 ---
        residuales = {
            "Fx": abs(Fx_cargas + Rx_reac),
            "Fy": abs(Fy_cargas + Ry_reac),
            "Mz": abs(Mz_cargas + Mz_reac),
        }

        equilibrio_ok = all(r < TOLERANCE for r in residuales.values())

        return equilibrio_ok, residuales

    def verificar_compatibilidad(self) -> Tuple[bool, List[float]]:
        """
        Verifica que los desplazamientos en redundantes sean ~0.

        Esta es la condición de compatibilidad que debe satisfacerse.

        Returns:
            Tupla (compatibilidad_satisfecha, desplazamientos)
        """
        if self._solucion_sece is None:
            raise ValueError("Primero debe resolver el SECE")

        # Calcular desplazamientos: e0 + F·X debe ser ≈ 0
        F = self._coeficientes.F
        e0 = self._coeficientes.e0
        X = self._solucion_sece.X

        desplazamientos = e0 + F @ X
        compatibilidad_ok = np.allclose(desplazamientos, 0, atol=TOLERANCE)

        return compatibilidad_ok, desplazamientos.tolist()


# =============================================================================
# FUNCIONES DE CONVENIENCIA
# =============================================================================

def analizar_estructura(
    modelo: ModeloEstructural,
    redundantes_manuales: Optional[List[Redundante]] = None,
) -> ResultadoAnalisis:
    """
    Función de conveniencia para analizar una estructura.

    Args:
        modelo: Modelo estructural a analizar
        redundantes_manuales: Redundantes seleccionados manualmente (opcional)

    Returns:
        ResultadoAnalisis con todos los resultados
    """
    motor = MotorMetodoFuerzas(
        modelo=modelo,
        seleccion_manual_redundantes=redundantes_manuales,
    )
    return motor.resolver()


def verificar_resultado(resultado: ResultadoAnalisis) -> Dict[str, bool]:
    """
    Verifica la validez de un resultado de análisis.

    Args:
        resultado: Resultado a verificar

    Returns:
        Diccionario con verificaciones {nombre: pasó}
    """
    verificaciones = {
        "exitoso": resultado.exitoso,
        "sin_errores": len(resultado.errores) == 0,
        "condicionamiento_ok": resultado.condicionamiento < CONDITION_NUMBER_WARNING,
        "residual_bajo": resultado.residual_sece < TOLERANCE,
    }

    return verificaciones
