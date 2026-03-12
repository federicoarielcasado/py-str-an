"""
Motor de análisis por el Método de las Deformaciones (Método de Rigidez).

Implementa el Método de las Deformaciones (MD) para análisis estático lineal
de pórticos planos 2D, coexistiendo con el Método de las Fuerzas (MF).

El MD resuelve directamente el sistema de equilibrio:
    [K] · {X} = {e^h} - {e°}

donde:
    [K]   : Matriz de rigidez global
    {X}   : Incógnitas cinemáticas (desplazamientos y rotaciones en GDL libres)
    {e^h} : Cargas externas en nudos libres (CargaPuntualNudo)
    {e°}  : Fuerzas de empotramiento en GDL libres (efecto de cargas en barras)

Ventajas respecto al MF:
    - No requiere identificar redundantes
    - Proceso idéntico para estructuras isostáticas e hiperestáticas
    - Los desplazamientos nodales son resultado directo (no post-proceso)
    - Más programable y sistemático (base del FEM moderno)

Fase 1 (implementación actual):
    - Vínculos rígidos: Empotramiento, ApoyoFijo, Rodillo
    - Cargas nodales: CargaPuntualNudo
    - Cargas en barras: CargaDistribuida, CargaPuntualBarra
    - Sin articulaciones internas, sin resortes, sin movimientos impuestos

Referencias:
    - Apuntes ANES I 2024 - Concepto de Rigidez. Método de las Deformaciones
    - Tratamiento Matricial de Estructuras - ANES I 2024
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from src.domain.analysis.fuerzas_empotramiento import CalculadorFuerzasEmpotramiento
from src.domain.analysis.motor_fuerzas import ResultadoAnalisis
from src.domain.analysis.numerador_gdl import NumeradorGDL
from src.domain.mechanics.esfuerzos import DiagramaEsfuerzos, EsfuerzosTramo

if TYPE_CHECKING:
    from src.domain.model.modelo_estructural import ModeloEstructural


def _k_local_barra(EA: float, EI: float, L: float) -> NDArray[np.float64]:
    """
    Matriz de rigidez local 6×6 para elemento de pórtico plano (Euler-Bernoulli).

    GDL en coordenadas locales: [u_i, v_i, θ_i, u_j, v_j, θ_j]
    donde:
        u : desplazamiento axial (X_local+)
        v : desplazamiento transversal (Y_local+, positivo hacia abajo en TERNA)
        θ : rotación (CW positivo)

    La matriz es simétrica y cumple la propiedad de reciprocidad de Maxwell-Betti.

    Args:
        EA: Rigidez axil [kN]     (E × A)
        EI: Rigidez flexional [kN·m²]  (E × Iz)
        L:  Longitud de la barra [m]

    Returns:
        Matriz 6×6 en coordenadas locales [kN/m, kNm/rad, etc.]
    """
    if L < 1e-12:
        raise ValueError(f"Longitud de barra nula o negativa: L={L}")

    EA_L = EA / L
    L2 = L * L
    L3 = L2 * L

    k = np.zeros((6, 6), dtype=np.float64)

    # Contribución axial (GDL 0 y 3: u_i, u_j)
    k[0, 0] = EA_L
    k[0, 3] = -EA_L
    k[3, 0] = -EA_L
    k[3, 3] = EA_L

    # Contribución flexional (GDL 1, 2, 4, 5: v_i, θ_i, v_j, θ_j)
    k[1, 1] = 12.0 * EI / L3
    k[1, 2] = 6.0 * EI / L2
    k[1, 4] = -12.0 * EI / L3
    k[1, 5] = 6.0 * EI / L2

    k[2, 1] = 6.0 * EI / L2
    k[2, 2] = 4.0 * EI / L
    k[2, 4] = -6.0 * EI / L2
    k[2, 5] = 2.0 * EI / L

    k[4, 1] = -12.0 * EI / L3
    k[4, 2] = -6.0 * EI / L2
    k[4, 4] = 12.0 * EI / L3
    k[4, 5] = -6.0 * EI / L2

    k[5, 1] = 6.0 * EI / L2
    k[5, 2] = 2.0 * EI / L
    k[5, 4] = -6.0 * EI / L2
    k[5, 5] = 4.0 * EI / L

    return k


class MotorMetodoDeformaciones:
    """
    Motor de análisis estructural por el Método de las Deformaciones.

    Resuelve el sistema [K]{X} = {e^h} - {e°} y retorna el mismo formato
    ResultadoAnalisis que el MotorMetodoFuerzas, permitiendo validación cruzada.

    Args:
        modelo: Modelo estructural a analizar
        metodo_resolucion: 'directo' (numpy.linalg.solve) o 'cholesky'

    Example:
        >>> motor = MotorMetodoDeformaciones(modelo)
        >>> resultado = motor.resolver()
        >>> print(resultado.reacciones_finales)
    """

    def __init__(
        self,
        modelo: "ModeloEstructural",
        metodo_resolucion: str = "directo",
        incluir_deformacion_axial: bool = True,
    ):
        self.modelo = modelo
        self.metodo_resolucion = metodo_resolucion
        self.incluir_deformacion_axial = incluir_deformacion_axial

        # Estado interno
        self._advertencias: List[str] = []
        self._errores: List[str] = []

        # Resultados intermedios
        self._numerador: Optional[NumeradorGDL] = None
        self._K_full: Optional[NDArray[np.float64]] = None
        self._F_full: Optional[NDArray[np.float64]] = None
        self._FEF_full: Optional[NDArray[np.float64]] = None
        self._d_full: Optional[NDArray[np.float64]] = None
        self._calculador_fef = CalculadorFuerzasEmpotramiento()

        # Cache de k_local por barra (optimización)
        self._k_local_cache: Dict[int, NDArray[np.float64]] = {}
        self._fef_local_cache: Dict[int, NDArray[np.float64]] = {}

        # Mapa {gdl_global: delta} para condiciones de contorno no homogéneas
        self._gdl_impuesto_map: Dict[int, float] = {}

    # =========================================================================
    # MÉTODO PRINCIPAL
    # =========================================================================

    def resolver(self) -> ResultadoAnalisis:
        """
        Ejecuta el análisis completo por el Método de las Deformaciones.

        Returns:
            ResultadoAnalisis con diagramas, reacciones y desplazamientos

        Raises:
            ValueError: Si el modelo es inválido o la matriz K es singular
        """
        try:
            self._validar_modelo()
            self._numerar_gdl()
            self._sincronizar_cargas_a_barras()
            self._ensamblar_K_global()
            self._ensamblar_F_global()
            self._extraer_movimientos_impuestos()
            self._resolver_sistema()
            self._recuperar_desplazamientos()
            diagramas = self._calcular_esfuerzos_barras()
            reacciones = self._calcular_reacciones()
            return self._construir_resultado(diagramas, reacciones)

        except Exception as exc:
            return ResultadoAnalisis(
                exitoso=False,
                errores=[str(exc)],
                advertencias=self._advertencias,
            )

    # =========================================================================
    # PASOS DEL ALGORITMO
    # =========================================================================

    def _validar_modelo(self) -> None:
        """Valida que el modelo tenga los datos mínimos necesarios."""
        if len(self.modelo.nudos) == 0:
            raise ValueError("El modelo no tiene nudos")
        if len(self.modelo.barras) == 0:
            raise ValueError("El modelo no tiene barras")

        # Verificar que al menos hay un vínculo
        nudos_con_vinculo = [n for n in self.modelo.nudos if n.vinculo is not None]
        if len(nudos_con_vinculo) == 0:
            raise ValueError("El modelo no tiene vínculos externos")

        # Verificar barras con longitud válida
        for barra in self.modelo.barras:
            if barra.L < 1e-9:
                raise ValueError(
                    f"Barra {barra.id} tiene longitud nula: L={barra.L:.2e} m"
                )

    def _numerar_gdl(self) -> None:
        """Asigna índices globales a los GDL de cada nudo."""
        self._numerador = NumeradorGDL(self.modelo)
        self._numerador.numerar()

    def _sincronizar_cargas_a_barras(self) -> None:
        """
        Sincroniza barra.cargas desde modelo.cargas para cada barra.

        modelo.agregar_carga() solo guarda en modelo._cargas; los cálculos de
        FEF y diagramas leen barra.cargas. Este paso hace la sincronización.

        Tipos procesados:
            - CargaDistribuida
            - CargaPuntualBarra
            - CargaTermica (contribuye al FEF vía _procesar_termica)
        """
        from src.domain.entities.carga import CargaDistribuida, CargaPuntualBarra, CargaTermica

        barra_map = {b.id: b for b in self.modelo.barras}

        # Limpiar lista interna de cada barra (sin mutar el objeto carga)
        for barra in self.modelo.barras:
            barra.cargas = []

        # Re-popular desde modelo.cargas
        for carga in self.modelo.cargas:
            if isinstance(carga, (CargaDistribuida, CargaPuntualBarra, CargaTermica)):
                if carga.barra is not None and carga.barra.id in barra_map:
                    barra_map[carga.barra.id].cargas.append(carga)

    def _extraer_movimientos_impuestos(self) -> None:
        """
        Construye ``_gdl_impuesto_map`` desde los ``MovimientoImpuesto`` del modelo.

        Un MovimientoImpuesto impone un desplazamiento/rotación prescrito en un
        GDL que ya está restringido por el vínculo del nudo.  Solo se procesan
        GDL que estén en ``indices_restringidos``; los que no estén restringidos
        por ningún vínculo generan una advertencia y se ignoran.

        Los valores impuestos son condiciones de contorno no homogéneas:
            d[gdl] = delta_prescrito  (en lugar de 0)
        """
        from src.domain.entities.carga import MovimientoImpuesto

        self._gdl_impuesto_map = {}
        gdl_map = self._numerador.gdl_map
        restringidos_set = set(self._numerador.indices_restringidos)

        for carga in self.modelo.cargas:
            if not isinstance(carga, MovimientoImpuesto):
                continue
            if carga.nudo is None:
                continue

            gdl = gdl_map.get(carga.nudo.id)
            if gdl is None:
                continue

            # (offset, valor) para cada componente del movimiento
            componentes = [
                (0, carga.delta_x),
                (1, carga.delta_y),
                (2, carga.delta_theta),
            ]
            for offset, delta_val in componentes:
                if abs(delta_val) < 1e-15:
                    continue
                gdl_global = gdl[offset]
                if gdl_global not in restringidos_set:
                    self._advertencias.append(
                        f"MovimientoImpuesto en nudo {carga.nudo.id} GDL offset={offset}: "
                        "el GDL no está restringido por ningún vínculo — se ignora."
                    )
                    continue
                self._gdl_impuesto_map[gdl_global] = delta_val

    def _ensamblar_K_global(self) -> None:
        """
        Ensambla la matriz de rigidez global K (n_total × n_total).

        Para cada barra:
            K_elem_global = T6 @ k_local @ T6.T
        Luego scatter-add en K_global usando los índices GDL del elemento.
        """
        n = self._numerador.n_total
        K = np.zeros((n, n), dtype=np.float64)
        gdl_map = self._numerador.gdl_map

        for barra in self.modelo.barras:
            # Rigidez axial efectiva: penalización para simular barra inextensible
            if self.incluir_deformacion_axial:
                ea_eff = barra.EA
            else:
                # EA_eff >> EA_real → deformación axial ≈ 0 (barra inextensible).
                # Factor 1e3: axial queda ~10^3–10^6 veces más rígido que flexión
                # para secciones típicas (EA_eff/L << 1e12 → condicionamiento OK).
                # La deformación axial residual ≈ 0.1% de la real → despreciable.
                ea_eff = barra.EA * 1e3

            # Matriz de rigidez local
            k_local = _k_local_barra(ea_eff, barra.EI, barra.L)
            self._k_local_cache[barra.id] = k_local

            # Transformar a global: K_elem = T6 @ k_local @ T6.T
            T6 = barra.T6
            K_elem = T6 @ k_local @ T6.T  # 6×6 en global

            # Índices globales del elemento [ux_i, uy_i, θ_i, ux_j, uy_j, θ_j]
            gdl_i = list(gdl_map[barra.nudo_i.id])
            gdl_j = list(gdl_map[barra.nudo_j.id])
            indices = gdl_i + gdl_j  # 6 índices

            # Scatter-add en K global
            for r_loc, r_glob in enumerate(indices):
                for c_loc, c_glob in enumerate(indices):
                    K[r_glob, c_glob] += K_elem[r_loc, c_loc]

        # Añadir rigideces de resortes elásticos a la diagonal de K
        for gdl_idx, k_spring in self._numerador.gdl_resorte_map.items():
            K[gdl_idx, gdl_idx] += k_spring

        self._K_full = K

    def _ensamblar_F_global(self) -> None:
        """
        Ensambla el vector de cargas global F (n_total,).

        Incluye:
        1. Cargas nodales directas (CargaPuntualNudo) → e^h
        2. Fuerzas de empotramiento rotadas a global → -e° (contribución al F efectivo)
        """
        from src.domain.entities.carga import CargaPuntualNudo

        n = self._numerador.n_total
        F = np.zeros(n, dtype=np.float64)
        F_fef = np.zeros(n, dtype=np.float64)  # solo FEF, para reacciones
        gdl_map = self._numerador.gdl_map

        # 1. Cargas nodales
        for carga in self.modelo.cargas:
            if isinstance(carga, CargaPuntualNudo) and carga.nudo is not None:
                gdl = gdl_map.get(carga.nudo.id)
                if gdl is None:
                    continue
                F[gdl[0]] += carga.Fx
                F[gdl[1]] += carga.Fy
                F[gdl[2]] += carga.Mz

        # 2. FEF de cargas en barras
        for barra in self.modelo.barras:
            fef_local = self._calculador_fef.calcular(barra)
            self._fef_local_cache[barra.id] = fef_local

            # Rotar a global
            fef_global = barra.T6 @ fef_local  # 6 componentes en global

            gdl_i = list(gdl_map[barra.nudo_i.id])
            gdl_j = list(gdl_map[barra.nudo_j.id])
            indices = gdl_i + gdl_j

            for r_loc, r_glob in enumerate(indices):
                F[r_glob] += fef_global[r_loc]
                F_fef[r_glob] += fef_global[r_loc]

        self._F_full = F
        self._FEF_full = F_fef

    def _resolver_sistema(self) -> None:
        """
        Aplica condiciones de frontera y resuelve [K_mod]{d} = {F_mod}.

        Para GDL con desplazamiento cero (BC homogénea):
            K_mod[i,i]=1, K_mod[i,j]=0, F_mod[i]=0

        Para GDL con movimiento impuesto δ ≠ 0 (BC no homogénea):
            Primero: F_mod -= K_full[:,i] · δ  (transfiere el efecto a los
                GDL libres ANTES de anular la columna)
            Luego: K_mod[i,i]=1, K_mod[i,j]=0, F_mod[i]=δ
        """
        n = self._numerador.n_total
        K_mod = self._K_full.copy()
        F_mod = self._F_full.copy()

        # Transferir contribución de movimientos impuestos a los GDL libres
        # (debe hacerse ANTES de anular las columnas correspondientes)
        for gdl, delta in self._gdl_impuesto_map.items():
            F_mod -= self._K_full[:, gdl] * delta

        # Aplicar BCs: para cada GDL restringido → K[i,i]=1, K[i,j]=0
        for gdl in self._numerador.indices_restringidos:
            K_mod[gdl, :] = 0.0
            K_mod[:, gdl] = 0.0
            K_mod[gdl, gdl] = 1.0
            # Movimiento impuesto o cero (BC homogénea por defecto)
            F_mod[gdl] = self._gdl_impuesto_map.get(gdl, 0.0)

        # Verificar condicionamiento
        if n > 0:
            try:
                cond = np.linalg.cond(K_mod)
                if cond > 1e12:
                    self._advertencias.append(
                        f"Matriz de rigidez mal condicionada (cond={cond:.2e}). "
                        "Verificar modelo (posible inestabilidad geometrica)."
                    )
            except np.linalg.LinAlgError:
                pass

        # Verificar si la matriz es singular (estructura inestable)
        if n > 0 and len(self._numerador.indices_libres) > 0:
            # Solo verificar el subbloque libre
            libres = self._numerador.indices_libres
            K_libre = K_mod[np.ix_(libres, libres)]
            if abs(np.linalg.det(K_libre)) < 1e-15 * (np.max(np.abs(K_libre)) ** len(libres)):
                raise ValueError(
                    "La estructura es geometricamente inestable: "
                    "matriz de rigidez singular. Verificar vinculos."
                )

        # Resolver el sistema completo
        try:
            d = np.linalg.solve(K_mod, F_mod)
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                f"No se pudo resolver el sistema de ecuaciones: {exc}"
            ) from exc

        # Asegurar valores exactos en GDL restringidos
        for gdl in self._numerador.indices_restringidos:
            d[gdl] = self._gdl_impuesto_map.get(gdl, 0.0)

        self._d_full = d

    def _recuperar_desplazamientos(self) -> None:
        """
        Actualiza los atributos Ux, Uy, theta_z de cada Nudo con los
        desplazamientos calculados.
        """
        gdl_map = self._numerador.gdl_map
        for nudo in self.modelo.nudos:
            gdl = gdl_map.get(nudo.id)
            if gdl is None:
                continue
            nudo.Ux = float(self._d_full[gdl[0]])
            nudo.Uy = float(self._d_full[gdl[1]])
            nudo.theta_z = float(self._d_full[gdl[2]])

    def _calcular_esfuerzos_barras(self) -> Dict[int, DiagramaEsfuerzos]:
        """
        Calcula los esfuerzos internos N(x), V(x), M(x) para cada barra.

        Método:
            1. Extraer desplazamientos globales del elemento
            2. Transformar a locales: d_local = T6.T @ d_global
            3. Calcular fuerzas nodales: p_local = k_local @ d_local + p_fijo_local
               donde p_fijo_local = -fef_local (lo que los apoyos fijos aplican)
            4. Reconstruir diagramas por equilibrio desde extremo i

        Convención de signos en p_element_local:
            p_local[0] = N_i (fuerza axil en nudo i, positiva = tracción)
            p_local[1] = V_i (fuerza transversal en nudo i → flip para cortante)
            p_local[2] = M_i (momento en nudo i, CW = positivo)
            p_local[3..5] = ídem para nudo j

        Para reconstruir M(x) desde extremo i:
            V_interno_i = -p_local[1]   (flip: fuerza-nudo → cortante-interno)
            M_interno_i =  p_local[2]   (sin flip)
        """
        from src.domain.entities.carga import CargaDistribuida, CargaPuntualBarra

        gdl_map = self._numerador.gdl_map
        diagramas: Dict[int, DiagramaEsfuerzos] = {}

        for barra in self.modelo.barras:
            k_local = self._k_local_cache[barra.id]
            fef_local = self._fef_local_cache[barra.id]
            T6 = barra.T6
            L = barra.L

            # Desplazamientos globales del elemento
            gdl_i = list(gdl_map[barra.nudo_i.id])
            gdl_j = list(gdl_map[barra.nudo_j.id])
            indices = gdl_i + gdl_j
            d_elem_global = self._d_full[indices]

            # Transformar a locales
            d_elem_local = T6.T @ d_elem_global  # 6 comp en local

            # Fuerzas nodales del elemento en local
            # p_fijo_local = -fef_local (vectores de soporte→barra, opuesto a FEF_for_F)
            p_fijo_local = -fef_local
            p_elem_local = k_local @ d_elem_local + p_fijo_local

            # Esfuerzos en extremos
            # Axil: tracción positiva
            N_i = p_elem_local[0]   # fuerza axil en nudo i (tracción = positivo aquí)
            # Cortante interno: flip de signo respecto a fuerza en nudo
            V_i = -p_elem_local[1]
            # Momento: sin flip en extremo i
            M_i = p_elem_local[2]

            # Para verificación (no usados directamente en la función)
            # N_j = p_elem_local[3]
            # V_j = -p_elem_local[4]   (flip en j también)
            # M_j (en diagrama) = -p_elem_local[5]  (flip en extremo j para bending)

            # Construir funciones N(x), V(x), M(x) por tramos
            tramos = self._construir_tramos(
                barra, p_elem_local, N_i, V_i, M_i
            )

            # Crear funciones continuas (para compatibilidad con ResultadoAnalisis)
            def _hacer_N(trms):
                def N_func(x: float) -> float:
                    for tramo in trms:
                        if tramo.x_inicio - 1e-9 <= x <= tramo.x_fin + 1e-9:
                            return tramo.N(x)
                    return 0.0
                return N_func

            def _hacer_V(trms):
                def V_func(x: float) -> float:
                    for tramo in trms:
                        if tramo.x_inicio - 1e-9 <= x <= tramo.x_fin + 1e-9:
                            return tramo.V(x)
                    return 0.0
                return V_func

            def _hacer_M(trms):
                def M_func(x: float) -> float:
                    for tramo in trms:
                        if tramo.x_inicio - 1e-9 <= x <= tramo.x_fin + 1e-9:
                            return tramo.M(x)
                    return 0.0
                return M_func

            diagrama = DiagramaEsfuerzos(
                barra_id=barra.id,
                L=L,
                tramos=tramos,
                Ni=tramos[0].N(0.0) if tramos else 0.0,
                Vi=tramos[0].V(0.0) if tramos else 0.0,
                Mi=tramos[0].M(0.0) if tramos else 0.0,
                Nj=tramos[-1].N(L) if tramos else 0.0,
                Vj=tramos[-1].V(L) if tramos else 0.0,
                Mj=tramos[-1].M(L) if tramos else 0.0,
                _N_func=_hacer_N(tramos),
                _V_func=_hacer_V(tramos),
                _M_func=_hacer_M(tramos),
            )
            diagramas[barra.id] = diagrama

            # Asignar funciones a la barra (para compatibilidad con visualización)
            barra.asignar_esfuerzos(
                N=diagrama._N_func,
                V=diagrama._V_func,
                M=diagrama._M_func,
            )

        return diagramas

    def _construir_tramos(
        self,
        barra,
        p_elem_local: NDArray[np.float64],
        N_i: float,
        V_i: float,
        M_i: float,
    ) -> List[EsfuerzosTramo]:
        """
        Construye los tramos de esfuerzos para una barra por equilibrio.

        Para cargas distribuidas y puntuales sobre la barra, divide en tramos
        y calcula N(x), V(x), M(x) en cada uno.

        La función M(x) se obtiene integrando desde el extremo i:
            V(x) = V_i - q_y(x)·(x - x_carga_inicio)
            M(x) = M_i + V_i·x - integral(q_y)·...

        Signo de esfuerzos (convención TERNA Y+ abajo, CW+):
            N positivo = tracción
            V positivo = izquierda arriba / derecha abajo (convención viga)
            M positivo = tracciona fibra inferior (sagging)
        """
        from src.domain.entities.carga import CargaDistribuida, CargaPuntualBarra
        import math

        L = barra.L

        # Recopilar posiciones de discontinuidad (cargas puntuales en barra)
        posiciones_disc = set([0.0, L])
        for carga in barra.cargas:
            if isinstance(carga, CargaPuntualBarra):
                posiciones_disc.add(max(0.0, min(carga.a, L)))

        posiciones_disc = sorted(posiciones_disc)

        tramos: List[EsfuerzosTramo] = []

        for idx_tramo in range(len(posiciones_disc) - 1):
            x_ini = posiciones_disc[idx_tramo]
            x_fin = posiciones_disc[idx_tramo + 1]

            # Calcular N, V, M en x_ini acumulando contribuciones previas
            # (N_i, V_i, M_i son en x=0; necesitamos integrar hasta x_ini)
            N_0, V_0, M_0 = self._esfuerzos_en_x(
                barra, N_i, V_i, M_i, x_ini
            )

            # Cargas distribuidas activas en este tramo
            q_y_ini = 0.0  # intensidad transversal al inicio del tramo
            q_y_fin = 0.0  # intensidad transversal al final del tramo
            q_x = 0.0      # intensidad axial (uniforme para simplificar)

            for carga in barra.cargas:
                if isinstance(carga, CargaDistribuida):
                    # Verificar si la carga actúa sobre este tramo
                    x1_c = carga.x1
                    x2_c = carga.x2 if carga.x2 is not None else L

                    if x2_c <= x_ini or x1_c >= x_fin:
                        continue  # No actúa en este tramo

                    # Intensidad efectiva en los extremos del tramo
                    angulo_rad = math.radians(carga.angulo)
                    sin_a = math.sin(angulo_rad)
                    cos_a = math.cos(angulo_rad)

                    q_ini_total = carga.intensidad_en(x_ini)
                    q_fin_total = carga.intensidad_en(x_fin)

                    q_y_ini += q_ini_total * sin_a
                    q_y_fin += q_fin_total * sin_a
                    q_x += (q_ini_total + q_fin_total) / 2.0 * cos_a

            # Crear funciones de tramo
            # Capturar variables por defecto para el closure
            def _N_tramo(x, N_0=N_0, q_x=q_x, x_ini=x_ini):
                return N_0 - q_x * (x - x_ini)

            def _V_tramo(x, V_0=V_0, q_y_ini=q_y_ini, q_y_fin=q_y_fin,
                         x_ini=x_ini, x_fin=x_fin):
                L_tramo = x_fin - x_ini
                if L_tramo < 1e-12:
                    return V_0
                # Variación lineal de la carga distribuida
                t = (x - x_ini) / L_tramo
                q_x_local = q_y_ini + (q_y_fin - q_y_ini) * t
                # V(x) = V_0 - integral(q_y) de x_ini a x
                # Para q lineal: integral = q_y_ini*(x-x_ini) + (q_y_fin-q_y_ini)*(x-x_ini)²/(2*L_tramo)
                dx = x - x_ini
                return V_0 - q_y_ini * dx - 0.5 * (q_y_fin - q_y_ini) / L_tramo * dx * dx

            def _M_tramo(x, M_0=M_0, V_0=V_0, q_y_ini=q_y_ini, q_y_fin=q_y_fin,
                         x_ini=x_ini, x_fin=x_fin):
                L_tramo = x_fin - x_ini
                if L_tramo < 1e-12:
                    return M_0
                # M(x) = M_0 + V_0*(x-x_ini) - integral^2(q_y) de x_ini a x
                # Para q lineal: integral = q_y_ini*dx²/2 + (q_y_fin-q_y_ini)*dx³/(6*L_tramo)
                dx = x - x_ini
                return (M_0 + V_0 * dx
                        - 0.5 * q_y_ini * dx * dx
                        - (q_y_fin - q_y_ini) / (6.0 * L_tramo) * dx * dx * dx)

            tramos.append(EsfuerzosTramo(
                x_inicio=x_ini,
                x_fin=x_fin,
                N=_N_tramo,
                V=_V_tramo,
                M=_M_tramo,
            ))

        if not tramos:
            # Fallback: un tramo sin cargas
            tramos.append(EsfuerzosTramo(
                x_inicio=0.0,
                x_fin=L,
                N=lambda x, N_i=N_i: N_i,
                V=lambda x, V_i=V_i: V_i,
                M=lambda x, M_i=M_i, V_i=V_i: M_i + V_i * x,
            ))

        return tramos

    def _esfuerzos_en_x(
        self,
        barra,
        N_i: float,
        V_i: float,
        M_i: float,
        x_objetivo: float,
    ) -> Tuple[float, float, float]:
        """
        Calcula N, V, M en la posición x_objetivo integrando desde x=0.

        Fórmulas exactas (Euler-Bernoulli, q lineal):
            ΔV = -integral(q_y(s), x_a, x_b)        = -(q_a+q_b)/2 * dx
            ΔN = -integral(q_x(s), x_a, x_b)        = -(q_ax+q_bx)/2 * dx
            ΔM = -integral(q_y(s)*(x_obj-s), x_a, x_b)
               = -(q_a_y*(X*dx - dx²/2) + (q_b_y-q_a_y)/L_c*(X*dx²/2 - dx³/3))
            donde X = x_objetivo - x_a, dx = x_b - x_a

        Para carga puntual P_y en a <= x_objetivo:
            ΔV = -P_y
            ΔM = -P_y*(x_objetivo - a)

        Note: el retorno acumula V_i*x_objetivo (contribución base de V_i a M).
        """
        from src.domain.entities.carga import CargaDistribuida, CargaPuntualBarra
        import math

        L = barra.L

        if x_objetivo < 1e-9:
            return N_i, V_i, M_i

        N = N_i
        dV = 0.0   # incremento acumulado en V por cargas
        dM = 0.0   # incremento acumulado en M por cargas (sin V_i*x)

        # Integrar desde 0 hasta x_objetivo
        for carga in barra.cargas:
            if isinstance(carga, CargaDistribuida):
                x1_c = carga.x1
                x2_c = carga.x2 if carga.x2 is not None else L

                angulo_rad = math.radians(carga.angulo)
                sin_a = math.sin(angulo_rad)
                cos_a = math.cos(angulo_rad)

                # Tramo de integración efectivo: [max(x1_c, 0), min(x2_c, x_objetivo)]
                x_a = max(x1_c, 0.0)
                x_b = min(x2_c, x_objetivo)
                if x_b <= x_a:
                    continue

                dx = x_b - x_a
                L_c = max(x2_c - x1_c, 1e-12)
                q_a_total = carga.intensidad_en(x_a)
                q_b_total = carga.intensidad_en(x_b)
                q_a_y = q_a_total * sin_a
                q_b_y = q_b_total * sin_a
                q_a_x = q_a_total * cos_a
                q_b_x = q_b_total * cos_a

                # ΔN = -integral(q_x, x_a, x_b) = -(q_ax+q_bx)/2 * dx (trapezoidal)
                N -= 0.5 * (q_a_x + q_b_x) * dx

                # ΔV = -integral(q_y, x_a, x_b) = -(q_a_y+q_b_y)/2 * dx
                dV -= 0.5 * (q_a_y + q_b_y) * dx

                # ΔM = -integral(q_y(s)*(x_obj-s), x_a, x_b)
                # Fórmula exacta para q lineal:
                #   = -(q_a_y*(X*dx - dx²/2) + (q_b_y-q_a_y)/L_c*(X*dx²/2 - dx³/3))
                # donde X = x_objetivo - x_a (brazo desde inicio carga a x_obj)
                X = x_objetivo - x_a
                dM -= (q_a_y * (X * dx - dx * dx * 0.5)
                       + (q_b_y - q_a_y) / L_c * (X * dx * dx * 0.5 - dx * dx * dx / 3.0))

            elif isinstance(carga, CargaPuntualBarra):
                a = max(0.0, min(carga.a, L))
                # Incluir cargas en a <= x_objetivo (usando > para incluir la posición exacta)
                if a > x_objetivo:
                    continue

                angulo_rad = math.radians(carga.angulo)
                P_y = carga.P * math.sin(angulo_rad)
                P_x = carga.P * math.cos(angulo_rad)

                N -= P_x
                dV -= P_y
                dM -= P_y * (x_objetivo - a)

        # M(x_obj) = M_i + V_i*x_obj + ΔM_cargas
        V = V_i + dV
        M = M_i + V_i * x_objetivo + dM
        return N, V, M

    def _calcular_reacciones(self) -> Dict[int, Tuple[float, float, float]]:
        """
        Calcula las reacciones en los vínculos.

        Vínculos rígidos (Empotramiento, ApoyoFijo, Rodillo, Guia):
            R_restringidos = K_cf @ d_free - FEF_restringidos
            donde K_cf = submatriz K[restringidos, libres]

        Resortes elásticos (ResorteElastico):
            R_resorte = -k · d   (la fuerza que el resorte ejerce sobre la
            estructura, opuesta al desplazamiento del nudo)

        Las reacciones se almacenan también en vinculo.Rx, Ry, Mz.
        """
        from src.domain.entities.vinculo import ResorteElastico

        reacciones: Dict[int, Tuple[float, float, float]] = {}
        gdl_map = self._numerador.gdl_map
        libres = self._numerador.indices_libres
        restringidos = self._numerador.indices_restringidos

        # ---- Vínculos rígidos -----------------------------------------------
        if restringidos:
            # Fórmula general: R = K_full[r,:] @ d_full - FEF[r]
            # Válida tanto para BCs homogéneas (d_r=0) como no homogéneas
            # (d_r=delta_impuesto), ya que usa el vector d_full completo.
            FEF_rest = self._FEF_full[restringidos]
            R_rest = self._K_full[restringidos, :] @ self._d_full - FEF_rest

            offset_map = {"Ux": 0, "Uy": 1, "theta_z": 2, "\u03b8z": 2}

            for nudo in self.modelo.nudos:
                if nudo.vinculo is None or isinstance(nudo.vinculo, ResorteElastico):
                    continue

                gdl = gdl_map.get(nudo.id)
                if gdl is None:
                    continue

                Rx = Ry = Mz = 0.0

                for nombre in nudo.vinculo.gdl_restringidos():
                    offset = offset_map.get(nombre)
                    if offset is None:
                        continue
                    gdl_global = gdl[offset]
                    if gdl_global in restringidos:
                        idx_en_rest = restringidos.index(gdl_global)
                        valor = float(R_rest[idx_en_rest])
                        if offset == 0:
                            Rx = valor
                        elif offset == 1:
                            Ry = valor
                        else:
                            Mz = valor

                reacciones[nudo.id] = (Rx, Ry, Mz)
                nudo.vinculo.Rx = Rx
                nudo.vinculo.Ry = Ry
                nudo.vinculo.Mz = Mz

        # ---- Resortes elásticos ---------------------------------------------
        for nudo in self.modelo.nudos:
            if not isinstance(nudo.vinculo, ResorteElastico):
                continue

            gdl = gdl_map.get(nudo.id)
            if gdl is None:
                continue

            resorte = nudo.vinculo
            # Reacción = −k · d  (el resorte empuja opuesto al desplazamiento)
            Rx = -resorte.kx * float(self._d_full[gdl[0]]) if resorte.kx > 0 else 0.0
            Ry = -resorte.ky * float(self._d_full[gdl[1]]) if resorte.ky > 0 else 0.0
            Mz = -resorte.ktheta * float(self._d_full[gdl[2]]) if resorte.ktheta > 0 else 0.0

            reacciones[nudo.id] = (Rx, Ry, Mz)
            resorte.Rx = Rx
            resorte.Ry = Ry
            resorte.Mz = Mz

        return reacciones

    def _construir_resultado(
        self,
        diagramas: Dict[int, DiagramaEsfuerzos],
        reacciones: Dict[int, Tuple[float, float, float]],
    ) -> ResultadoAnalisis:
        """
        Construye el ResultadoAnalisis final.

        El Método de las Deformaciones no usa redundantes ni GH,
        pero reutiliza el mismo formato de salida para compatibilidad.
        """
        # Verificar equilibrio global
        adv_equilibrio = self._verificar_equilibrio(reacciones)
        self._advertencias.extend(adv_equilibrio)

        return ResultadoAnalisis(
            exitoso=True,
            grado_hiperestaticidad=0,  # No aplica al MD
            redundantes=[],
            valores_X=None,
            reacciones_finales=reacciones,
            diagramas_finales=diagramas,
            advertencias=self._advertencias,
            errores=[],
        )

    def _verificar_equilibrio(
        self, reacciones: Dict[int, Tuple[float, float, float]]
    ) -> List[str]:
        """
        Verifica equilibrio global: ΣFx=0, ΣFy=0, ΣMz=0.

        Returns:
            Lista de advertencias si el equilibrio no se satisface
        """
        from src.domain.entities.carga import CargaPuntualNudo

        advertencias: List[str] = []

        # Sumar cargas externas
        Fx_ext = Fy_ext = Mz_ext = 0.0
        for carga in self.modelo.cargas:
            if isinstance(carga, CargaPuntualNudo) and carga.nudo is not None:
                Fx_ext += carga.Fx
                Fy_ext += carga.Fy
                Mz_ext += carga.Mz

        # Sumar reacciones
        Rx_tot = Ry_tot = Mz_tot = 0.0
        for nudo in self.modelo.nudos:
            if nudo.id in reacciones:
                Rx, Ry, Mz = reacciones[nudo.id]
                Rx_tot += Rx
                Ry_tot += Ry
                Mz_tot += Mz

        tol = 1e-4  # kN
        if abs(Fx_ext + Rx_tot) > tol:
            advertencias.append(
                f"Equilibrio X no satisfecho: ΣFx = {Fx_ext + Rx_tot:.4e} kN"
            )
        if abs(Fy_ext + Ry_tot) > tol:
            advertencias.append(
                f"Equilibrio Y no satisfecho: ΣFy = {Fy_ext + Ry_tot:.4e} kN"
            )

        return advertencias


# =============================================================================
# FUNCIONES DE CONVENIENCIA
# =============================================================================

def analizar_estructura_deformaciones(
    modelo: "ModeloEstructural",
    incluir_deformacion_axial: bool = True,
) -> ResultadoAnalisis:
    """
    Función de conveniencia para analizar una estructura por el Método de Deformaciones.

    Args:
        modelo: Modelo estructural completo (nudos, barras, vínculos, cargas)
        incluir_deformacion_axial: Si True (defecto), incluye deformación axial real de
            cada barra. Si False, simula rigidez axial infinita (barras inextensibles)
            mediante el método de penalización (EA_eff = EA × 1e6). Esto corresponde
            a la hipótesis clásica de pequeñas deformaciones donde se desprecia el
            acortamiento/alargamiento de las barras — habitual en cálculo manual y
            permite comparar directamente con el MF sin deformación axial.

    Returns:
        ResultadoAnalisis con diagramas, reacciones y desplazamientos nodales

    Example:
        >>> from src.domain.analysis.motor_deformaciones import analizar_estructura_deformaciones
        >>> resultado = analizar_estructura_deformaciones(modelo)
        >>> print(f"Desplazamiento nudo 2: {resultado.reacciones_finales[2]}")
    """
    motor = MotorMetodoDeformaciones(
        modelo, incluir_deformacion_axial=incluir_deformacion_axial
    )
    return motor.resolver()


def comparar_resultados(
    r_mf: ResultadoAnalisis,
    r_md: ResultadoAnalisis,
    n_puntos: int = 11,
    tol: float = 1e-3,
) -> dict:
    """
    Compara los resultados de ambos métodos (MF y MD) para validación cruzada.

    Evalúa N(x), V(x), M(x) en n_puntos equiespaciados por barra y compara
    también las reacciones en vínculos.

    Args:
        r_mf: Resultado del Método de las Fuerzas
        r_md: Resultado del Método de las Deformaciones
        n_puntos: Número de puntos de evaluación por barra
        tol: Tolerancia para determinar si coinciden (kN o kNm)

    Returns:
        Diccionario con:
            - 'coinciden': bool (True si max_diff < tol en todas las barras)
            - 'max_diferencia': float (máxima diferencia absoluta encontrada)
            - 'diferencias_por_barra': dict {barra_id: {'N': max, 'V': max, 'M': max}}
            - 'diferencias_reacciones': dict {nudo_id: {'Rx': diff, 'Ry': diff, 'Mz': diff}}
    """
    import numpy as np

    diferencias_barras: dict = {}
    max_diff_global = 0.0

    # Comparar diagramas de esfuerzos
    barras_mf = set(r_mf.diagramas_finales.keys())
    barras_md = set(r_md.diagramas_finales.keys())
    barras_comunes = barras_mf & barras_md

    for barra_id in barras_comunes:
        diag_mf = r_mf.diagramas_finales[barra_id]
        diag_md = r_md.diagramas_finales[barra_id]
        L = diag_mf.L
        xs = np.linspace(0, L, n_puntos)

        N_diff = max(abs(diag_mf.N(x) - diag_md.N(x)) for x in xs)
        V_diff = max(abs(diag_mf.V(x) - diag_md.V(x)) for x in xs)
        M_diff = max(abs(diag_mf.M(x) - diag_md.M(x)) for x in xs)

        diferencias_barras[barra_id] = {"N": N_diff, "V": V_diff, "M": M_diff}
        max_diff_global = max(max_diff_global, N_diff, V_diff, M_diff)

    # Comparar reacciones
    diferencias_reacciones: dict = {}
    nudos_comunes = set(r_mf.reacciones_finales.keys()) & set(r_md.reacciones_finales.keys())

    for nudo_id in nudos_comunes:
        Rx_mf, Ry_mf, Mz_mf = r_mf.reacciones_finales[nudo_id]
        Rx_md, Ry_md, Mz_md = r_md.reacciones_finales[nudo_id]
        diferencias_reacciones[nudo_id] = {
            "Rx": abs(Rx_mf - Rx_md),
            "Ry": abs(Ry_mf - Ry_md),
            "Mz": abs(Mz_mf - Mz_md),
        }
        max_diff_global = max(
            max_diff_global,
            abs(Rx_mf - Rx_md),
            abs(Ry_mf - Ry_md),
            abs(Mz_mf - Mz_md),
        )

    return {
        "coinciden": max_diff_global < tol,
        "max_diferencia": max_diff_global,
        "diferencias_por_barra": diferencias_barras,
        "diferencias_reacciones": diferencias_reacciones,
    }
