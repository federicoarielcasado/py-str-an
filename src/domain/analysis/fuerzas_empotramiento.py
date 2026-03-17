"""
Cálculo de Fuerzas de Empotramiento (FEF) para el Método de las Deformaciones.

Las Fuerzas de Empotramiento (también llamadas "pares y fuerzas extremas de barra"
en el contexto del Método de las Deformaciones) son las fuerzas equivalentes
nodales en coordenadas LOCALES que representan el efecto de las cargas distribuidas
y puntuales sobre las barras.

Convención de signos:
    Los vectores FEF retornados por este módulo son las **fuerzas equivalentes
    nodales** (lo que se suma al vector F_global). Su signo positivo indica que
    la fuerza se aplica en la misma dirección que el eje positivo local.

    Para carga distribuida q uniforme (q > 0 = dirección Y_local+ = hacia abajo):
        FEF = [0, +qL/2, +qL²/12, 0, +qL/2, -qL²/12]

    Para recuperar esfuerzos internos usar: p_fijo_local = -FEF

Referencias:
    - Apuntes ANES I - Tabla de Pares y Fuerzas Extremas de Barra
    - Tratamiento Matricial de Estructuras (ANES I 2024)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, List

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from src.domain.entities.barra import Barra
    from src.domain.entities.carga import Carga, CargaDistribuida, CargaPuntualBarra


def _fef_distribuida_transversal(
    q_a: float, q_b: float, L: float
) -> NDArray[np.float64]:
    """
    Fuerzas de empotramiento para carga distribuida trapezoidal transversal.

    La carga varía linealmente de q_a (en nudo i, x=0) a q_b (en nudo j, x=L),
    actuando en la dirección Y_local+ (transversal positiva).

    Fórmulas (derivadas por trabajo virtual con funciones de forma Hermite):
        F_vi = L(7q_a + 3q_b) / 20
        F_Mi = L²(3q_a + 2q_b) / 60
        F_vj = L(3q_a + 7q_b) / 20
        F_Mj = -L²(2q_a + 3q_b) / 60

    Args:
        q_a: Intensidad de carga en nudo i [kN/m], positiva = Y_local+
        q_b: Intensidad de carga en nudo j [kN/m], positiva = Y_local+
        L: Longitud de la barra [m]

    Returns:
        Vector FEF [N_i, V_i, M_i, N_j, V_j, M_j] en LOCAL (6 componentes)
    """
    fef = np.zeros(6, dtype=np.float64)
    fef[1] = L * (7.0 * q_a + 3.0 * q_b) / 20.0   # V_i
    fef[2] = L * L * (3.0 * q_a + 2.0 * q_b) / 60.0  # M_i
    fef[4] = L * (3.0 * q_a + 7.0 * q_b) / 20.0   # V_j
    fef[5] = -L * L * (2.0 * q_a + 3.0 * q_b) / 60.0  # M_j
    return fef


def _fef_distribuida_axial(
    q_a: float, q_b: float, L: float
) -> NDArray[np.float64]:
    """
    Fuerzas de empotramiento para carga distribuida trapezoidal axial.

    La carga varía linealmente de q_a a q_b en dirección X_local+ (axial).

    Para carga uniforme: F_xi = F_xj = q·L/2
    Para trapezoidal (derivada por equilibrio): F_xi = L(2q_a+q_b)/6, F_xj = L(q_a+2q_b)/6

    Args:
        q_a: Intensidad en nudo i [kN/m], positiva = X_local+
        q_b: Intensidad en nudo j [kN/m], positiva = X_local+
        L: Longitud de la barra [m]

    Returns:
        Vector FEF [N_i, V_i, M_i, N_j, V_j, M_j] en LOCAL (6 componentes)
    """
    fef = np.zeros(6, dtype=np.float64)
    fef[0] = L * (2.0 * q_a + q_b) / 6.0   # N_i
    fef[3] = L * (q_a + 2.0 * q_b) / 6.0   # N_j
    return fef


def _fef_puntual_transversal(
    P: float, a: float, L: float
) -> NDArray[np.float64]:
    """
    Fuerzas de empotramiento para carga puntual transversal.

    Carga P actuando en dirección Y_local+ a distancia a del nudo i.

    Fórmulas (barra biempotrada):
        b = L - a
        F_vi = P·b²(3a + b) / L³
        F_Mi = P·a·b² / L²
        F_vj = P·a²(a + 3b) / L³
        F_Mj = -P·a²·b / L²

    Args:
        P: Magnitud de la carga [kN], positiva = Y_local+
        a: Distancia desde nudo i [m]
        L: Longitud de la barra [m]

    Returns:
        Vector FEF [N_i, V_i, M_i, N_j, V_j, M_j] en LOCAL (6 componentes)
    """
    if L < 1e-12:
        return np.zeros(6, dtype=np.float64)

    b = L - a
    L2 = L * L
    L3 = L2 * L

    fef = np.zeros(6, dtype=np.float64)
    fef[1] = P * b * b * (3.0 * a + b) / L3   # V_i
    fef[2] = P * a * b * b / L2                # M_i
    fef[4] = P * a * a * (a + 3.0 * b) / L3   # V_j
    fef[5] = -P * a * a * b / L2               # M_j
    return fef


def _fef_puntual_axial(
    P: float, a: float, L: float
) -> NDArray[np.float64]:
    """
    Fuerzas de empotramiento para carga puntual axial.

    Carga P en dirección X_local+ a distancia a del nudo i.

    Por equilibrio estático:
        F_xi = P·(L - a)/L
        F_xj = P·a/L

    Args:
        P: Magnitud [kN], positiva = X_local+
        a: Distancia desde nudo i [m]
        L: Longitud de la barra [m]

    Returns:
        Vector FEF en LOCAL (6 componentes)
    """
    if L < 1e-12:
        return np.zeros(6, dtype=np.float64)

    fef = np.zeros(6, dtype=np.float64)
    fef[0] = P * (L - a) / L   # N_i
    fef[3] = P * a / L          # N_j
    return fef


class CalculadorFuerzasEmpotramiento:
    """
    Calcula el vector de Fuerzas de Empotramiento (FEF) para una barra.

    Procesa todas las cargas asociadas a la barra y retorna el vector FEF
    acumulado en coordenadas LOCALES de la barra.

    El vector FEF tiene el formato: [N_i, V_i, M_i, N_j, V_j, M_j]
    donde los índices i/j corresponden a nudo_i y nudo_j de la barra.

    Convención:
        - Positivo en dirección del eje local (X+ axial, Y+ transversal, θ+ CW)
        - FEF es la fuerza EQUIVALENTE NODAL (lo que entra al vector F global)
        - Para recuperar esfuerzos: p_fijo = -FEF

    Cargas soportadas en Fase 1:
        - CargaDistribuida (uniforme, triangular, trapezoidal)
        - CargaPuntualBarra

    Example:
        >>> calculador = CalculadorFuerzasEmpotramiento()
        >>> fef_local = calculador.calcular(barra)  # np.ndarray shape (6,)
    """

    def calcular(self, barra: "Barra") -> NDArray[np.float64]:
        """
        Calcula el vector FEF acumulado para todas las cargas de una barra.

        Args:
            barra: Barra con sus cargas asignadas

        Returns:
            Vector FEF [N_i, V_i, M_i, N_j, V_j, M_j] en coordenadas LOCALES [kN, kN, kNm, ...]
        """
        from src.domain.entities.carga import CargaDistribuida, CargaPuntualBarra, CargaTermica

        fef_total = np.zeros(6, dtype=np.float64)

        for carga in barra.cargas:
            if isinstance(carga, CargaDistribuida):
                fef_total += self._procesar_distribuida(carga, barra)
            elif isinstance(carga, CargaPuntualBarra):
                fef_total += self._procesar_puntual(carga, barra)
            elif isinstance(carga, CargaTermica):
                fef_total += self._procesar_termica(carga, barra)
            # Otros tipos de carga no soportados → se ignoran

        return fef_total

    def _procesar_termica(
        self, carga: "CargaTermica", barra: "Barra"
    ) -> NDArray[np.float64]:
        """
        Procesa una CargaTermica y retorna su contribución al FEF local.

        Las cargas térmicas en el Método de las Deformaciones generan fuerzas
        de empotramiento equivalentes (FEF) que se añaden al vector de cargas
        global.  No modifican la matriz de rigidez.

        Componentes:

        1. Variación uniforme ΔT_u [°C]:
           El elemento quiere alargarse δ = α·ΔT_u·L.  En biempotrado la
           reacción axial es N = -EA·α·ΔT_u (compresión para ΔT_u > 0).

           FEF axial (convención de este motor):
               fef[0] = +EA·α·ΔT_u   (en nudo i, dirección X_local+)
               fef[3] = -EA·α·ΔT_u   (en nudo j, dirección X_local+)

           De este modo:  N_i = p_elem[0] = k@d[0] - fef[0] = -EA·α·ΔT_u  (correcto)

        2. Gradiente lineal ΔT_g [°C] (ΔT entre fibra superior e inferior):
           Curvatura libre: κ_T = α·ΔT_g/h.  En biempotrado el momento
           interno es M = -EI·κ_T (hogging si ΔT_g > 0 con fibra sup. más
           caliente → tendencia a pandear hacia abajo).

           FEF de momento:
               fef[2] = +EI·κ_T   (en nudo i, dirección θ+)
               fef[5] = -EI·κ_T   (en nudo j, dirección θ+)

           De este modo:  M_i = p_elem[2] = k@d[2] - fef[2] = -EI·κ_T  (correcto)

        Args:
            carga: CargaTermica con delta_T_uniforme y/o delta_T_gradiente
            barra: Barra a la que pertenece la carga

        Returns:
            Vector FEF [N_i, V_i, M_i, N_j, V_j, M_j] en LOCAL (6 componentes)
        """
        fef = np.zeros(6, dtype=np.float64)

        alpha = barra.material.alpha
        EA = barra.material.E * barra.seccion.A
        EI = barra.material.E * barra.seccion.Iz

        # --- Componente axial (variación uniforme de temperatura) ---
        if abs(carga.delta_T_uniforme) > 1e-12:
            delta_T_u = carga.delta_T_uniforme
            fef[0] = +EA * alpha * delta_T_u   # N en nudo i
            fef[3] = -EA * alpha * delta_T_u   # N en nudo j

        # --- Componente flexional (gradiente térmico entre fibras) ---
        if abs(carga.delta_T_gradiente) > 1e-12:
            h = barra.seccion.h
            if h < 1e-10:
                # Sección sin altura definida: sin efecto de gradiente
                pass
            else:
                kappa_T = alpha * carga.delta_T_gradiente / h
                fef[2] = +EI * kappa_T   # M en nudo i
                fef[5] = -EI * kappa_T   # M en nudo j

        return fef

    def _procesar_distribuida(
        self, carga: "CargaDistribuida", barra: "Barra"
    ) -> NDArray[np.float64]:
        """
        Procesa una CargaDistribuida y retorna su contribución al FEF.

        La carga puede estar definida en parte de la barra (x1 a x2).
        Para simplificar Fase 1, se asume carga sobre toda la barra (x1=0, x2=L).
        La intensidad puede variar linealmente de q1 a q2.

        Descomposición por ángulo de la carga:
            q_y = q · sin(angulo)  (componente transversal local)
            q_x = q · cos(angulo)  (componente axial local)
        """
        import math as _math

        L = barra.L
        angulo_rad = math.radians(carga.angulo)

        # Determinar tramo efectivo de la carga
        x1 = carga.x1
        x2 = carga.x2 if carga.x2 is not None else L

        # Longitud del tramo cargado
        L_carga = x2 - x1

        if L_carga < 1e-12:
            return np.zeros(6, dtype=np.float64)

        # Para Fase 1: si la carga no cubre toda la barra, aproximar como
        # superposición de una carga sobre [0, x2] menos [0, x1]
        # Esta aproximación es exacta para el caso más común (toda la barra)
        fef = np.zeros(6, dtype=np.float64)

        # Intensidades en los extremos del tramo cargado
        q1 = carga.q1  # en x = x1
        q2 = carga.q2  # en x = x2

        # Descomponer en componentes locales
        sin_a = math.sin(angulo_rad)
        cos_a = math.cos(angulo_rad)

        q1_y = q1 * sin_a   # transversal (Y_local+)
        q2_y = q2 * sin_a
        q1_x = q1 * cos_a   # axial (X_local+)
        q2_x = q2 * cos_a

        if abs(x1) < 1e-9 and abs(x2 - L) < 1e-9:
            # Caso estándar: carga sobre toda la barra
            if abs(sin_a) > 1e-10:
                fef += _fef_distribuida_transversal(q1_y, q2_y, L)
            if abs(cos_a) > 1e-10:
                fef += _fef_distribuida_axial(q1_x, q2_x, L)
        else:
            # Carga parcial: usar integración por superposición
            # Carga sobre [0, x2] con intensidades interpoladas
            # menos carga sobre [0, x1]
            # Nota: esta aproximación es válida para tramos contiguos al nudo i
            # Para el caso general se usa integración numérica con FEF equivalente
            fef += self._fef_carga_parcial(
                q1_y, q2_y, q1_x, q2_x, x1, x2, L
            )

        return fef

    def _fef_carga_parcial(
        self,
        q1_y: float, q2_y: float,
        q1_x: float, q2_x: float,
        x1: float, x2: float,
        L: float,
    ) -> NDArray[np.float64]:
        """
        FEF para carga distribuida que no ocupa toda la barra [x1, x2].

        Usa integración por funciones de forma de Hermite:
            F_i = integral(x1, x2) q(x) * N_i(x) dx

        Para una distribución lineal q(x) = q_a + (q_b-q_a)(x-x1)/(x2-x1):
        Se evalúa numéricamente con cuadratura de Gauss (5 puntos).
        """
        # Puntos y pesos de cuadratura Gauss en [-1, 1] (5 puntos)
        gauss_pts = np.array([-0.9061798459, -0.5384693101, 0.0,
                               0.5384693101,  0.9061798459])
        gauss_wts = np.array([0.2369268851,  0.4786286705, 0.5688888889,
                               0.4786286705,  0.2369268851])

        fef = np.zeros(6, dtype=np.float64)
        L_tramo = x2 - x1

        for xi, wi in zip(gauss_pts, gauss_wts):
            # Punto de cuadratura en coordenadas globales de barra
            x = x1 + 0.5 * L_tramo * (xi + 1.0)
            peso = wi * 0.5 * L_tramo

            # Interpolación lineal de la carga
            t = (x - x1) / L_tramo if L_tramo > 1e-12 else 0.0
            qy = q1_y + (q2_y - q1_y) * t
            qx = q1_x + (q2_x - q1_x) * t

            # Funciones de forma Hermite en posición x/L
            s = x / L
            N1 = 1.0 - 3.0 * s**2 + 2.0 * s**3        # v_i = 1
            N2 = L * s * (1.0 - s)**2                    # theta_i = 1
            N3 = 3.0 * s**2 - 2.0 * s**3                # v_j = 1
            N4 = L * s**2 * (s - 1.0)                    # theta_j = 1
            NA_i = 1.0 - s                               # u_i = 1
            NA_j = s                                     # u_j = 1

            # Contribución transversal
            fef[1] += qy * N1 * peso    # V_i
            fef[2] += qy * N2 * peso    # M_i
            fef[4] += qy * N3 * peso    # V_j
            fef[5] += qy * N4 * peso    # M_j

            # Contribución axial
            fef[0] += qx * NA_i * peso  # N_i
            fef[3] += qx * NA_j * peso  # N_j

        return fef

    def _procesar_puntual(
        self, carga: "CargaPuntualBarra", barra: "Barra"
    ) -> NDArray[np.float64]:
        """
        Procesa una CargaPuntualBarra y retorna su contribución al FEF.

        Descomposición:
            P_y = P · sin(angulo)  (componente transversal)
            P_x = P · cos(angulo)  (componente axial)
        """
        L = barra.L
        a = carga.a

        # Clamp para evitar singularidades en extremos
        a = max(0.0, min(a, L))

        angulo_rad = math.radians(carga.angulo)
        P_y = carga.P * math.sin(angulo_rad)   # transversal
        P_x = carga.P * math.cos(angulo_rad)   # axial

        fef = np.zeros(6, dtype=np.float64)

        if abs(P_y) > 1e-12:
            fef += _fef_puntual_transversal(P_y, a, L)

        if abs(P_x) > 1e-12:
            fef += _fef_puntual_axial(P_x, a, L)

        return fef
