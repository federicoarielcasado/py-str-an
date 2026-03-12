"""
Selección de redundantes para el Método de las Fuerzas.

Define los tipos de redundantes y proporciona algoritmos para
seleccionar automáticamente los redundantes óptimos.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from src.domain.model.modelo_estructural import ModeloEstructural
    from src.domain.entities.nudo import Nudo
    from src.domain.entities.barra import Barra


class TipoRedundante(Enum):
    """
    Tipos de redundantes que se pueden elegir.

    Los redundantes pueden ser:
    - Reacciones de vínculo externo (Rx, Ry, Mz)
    - Esfuerzos internos en barras (N, V, M en un punto)
    """
    # Reacciones de vínculo
    REACCION_RX = auto()      # Reacción horizontal
    REACCION_RY = auto()      # Reacción vertical
    REACCION_MZ = auto()      # Momento de reacción

    # Esfuerzos internos (en articulaciones virtuales)
    MOMENTO_INTERNO = auto()   # Momento en sección de barra
    CORTANTE_INTERNO = auto()  # Cortante en sección (menos común)
    AXIL_INTERNO = auto()      # Axil en sección (para armaduras)


@dataclass
class Redundante:
    """
    Representa un redundante seleccionado.

    Attributes:
        tipo: Tipo de redundante
        nudo_id: ID del nudo donde se aplica (para reacciones)
        barra_id: ID de la barra (para esfuerzos internos)
        posicion: Posición en la barra donde se libera el esfuerzo [m]
        descripcion: Descripción legible del redundante
        indice: Índice en el sistema de ecuaciones (X1, X2, etc.)
    """
    tipo: TipoRedundante
    nudo_id: Optional[int] = None
    barra_id: Optional[int] = None
    posicion: float = 0.0
    descripcion: str = ""
    indice: int = 0

    def __post_init__(self):
        """Genera descripción automática si no se proporciona."""
        if not self.descripcion:
            self.descripcion = self._generar_descripcion()

    def _generar_descripcion(self) -> str:
        """Genera una descripción legible del redundante."""
        if self.tipo == TipoRedundante.REACCION_RX:
            return f"Rx en nudo {self.nudo_id}"
        elif self.tipo == TipoRedundante.REACCION_RY:
            return f"Ry en nudo {self.nudo_id}"
        elif self.tipo == TipoRedundante.REACCION_MZ:
            return f"Mz en nudo {self.nudo_id}"
        elif self.tipo == TipoRedundante.MOMENTO_INTERNO:
            return f"M interno en barra {self.barra_id} (x={self.posicion:.2f}m)"
        elif self.tipo == TipoRedundante.CORTANTE_INTERNO:
            return f"V interno en barra {self.barra_id} (x={self.posicion:.2f}m)"
        elif self.tipo == TipoRedundante.AXIL_INTERNO:
            return f"N interno en barra {self.barra_id}"
        return f"Redundante {self.indice}"

    @property
    def nombre_corto(self) -> str:
        """Nombre corto para usar en matrices y vectores."""
        return f"X{self.indice}"


class SelectorRedundantes:
    """
    Selecciona automáticamente los redundantes para el método de las fuerzas.

    Implementa diferentes estrategias de selección:
    1. Priorizar momentos de reacción (empotramientos)
    2. Priorizar reacciones verticales
    3. Evitar crear subestructuras inestables
    4. Optimizar para matrices bien condicionadas

    Attributes:
        modelo: Modelo estructural a analizar
    """

    def __init__(self, modelo: ModeloEstructural):
        """
        Inicializa el selector.

        Args:
            modelo: Modelo estructural
        """
        self.modelo = modelo
        self._candidatos: List[Redundante] = []
        self._seleccionados: List[Redundante] = []

    def seleccionar_automatico(self) -> List[Redundante]:
        """
        Selecciona automáticamente los redundantes.

        Estrategia de selección en dos niveles:

        **Nivel 1 — QR con pivoteo columnar** (``scipy`` requerido):
            Construye la matriz de equilibrio global 3×r donde cada columna
            representa la contribución de una reacción candidata a ΣFx, ΣFy
            y ΣMz.  El QR con pivoteo identifica directamente las columnas
            linealmente dependientes (= redundantes) sin búsqueda combinatoria.

        **Nivel 2 — Spanning tree** (para redundancias internas):
            Cuando los redundantes no provienen solo de reacciones (estructuras
            con lazos cerrados), el spanning tree BFS del grafo de barras
            identifica qué barras crean loops y las marca como cortes internos.

        Si ``scipy`` no está disponible, cae en la heurística original (Mz→Ry→Rx).

        Returns:
            Lista de redundantes seleccionados

        Raises:
            ValueError: Si la estructura es hipostática
        """
        gh = self.modelo.grado_hiperestaticidad

        if gh <= 0:
            if gh < 0:
                raise ValueError(
                    f"Estructura hipostática (GH={gh}). "
                    "No se pueden seleccionar redundantes."
                )
            return []  # Isostática, no hay redundantes

        # Identificar todos los candidatos posibles
        self._identificar_candidatos()

        # Intentar selección determinística por QR; fallback a heurística
        try:
            self._seleccionados = self._seleccionar_por_qr(gh)
        except Exception:
            self._seleccionados = self._aplicar_heuristica(gh)

        # Asignar índices
        for i, red in enumerate(self._seleccionados):
            red.indice = i + 1

        return self._seleccionados

    def seleccionar_manual(self, redundantes: List[Redundante]) -> List[Redundante]:
        """
        Acepta una selección manual de redundantes.

        Args:
            redundantes: Lista de redundantes elegidos por el usuario

        Returns:
            Lista de redundantes con índices asignados

        Raises:
            ValueError: Si el número de redundantes no coincide con GH
        """
        gh = self.modelo.grado_hiperestaticidad

        if len(redundantes) != gh:
            raise ValueError(
                f"Se requieren {gh} redundantes, se proporcionaron {len(redundantes)}"
            )

        # Validar que los redundantes son válidos
        for red in redundantes:
            self._validar_redundante(red)

        # Asignar índices
        self._seleccionados = list(redundantes)
        for i, red in enumerate(self._seleccionados):
            red.indice = i + 1

        return self._seleccionados

    def _identificar_candidatos(self) -> None:
        """Identifica todos los posibles redundantes."""
        self._candidatos = []

        # Candidatos de reacciones de vínculo
        for nudo in self.modelo.nudos:
            if not nudo.tiene_vinculo:
                continue

            gdl_restringidos = nudo.vinculo.gdl_restringidos()

            if "Ux" in gdl_restringidos:
                self._candidatos.append(Redundante(
                    tipo=TipoRedundante.REACCION_RX,
                    nudo_id=nudo.id,
                ))

            if "Uy" in gdl_restringidos:
                self._candidatos.append(Redundante(
                    tipo=TipoRedundante.REACCION_RY,
                    nudo_id=nudo.id,
                ))

            if "θz" in gdl_restringidos:
                self._candidatos.append(Redundante(
                    tipo=TipoRedundante.REACCION_MZ,
                    nudo_id=nudo.id,
                ))

        # Candidatos de momentos internos (en nudos de conexión de barras)
        for nudo in self.modelo.nudos:
            barras_conectadas = self.modelo.barras_conectadas_a_nudo(nudo.id)
            if len(barras_conectadas) >= 2 and not nudo.tiene_vinculo:
                # Nudo interno con múltiples barras: candidato para articulación virtual
                for barra in barras_conectadas:
                    if barra.nudo_i.id == nudo.id:
                        pos = 0.0
                    else:
                        pos = barra.L

                    self._candidatos.append(Redundante(
                        tipo=TipoRedundante.MOMENTO_INTERNO,
                        barra_id=barra.id,
                        nudo_id=nudo.id,
                        posicion=pos,
                    ))

    def _seleccionar_por_qr(self, n_redundantes: int) -> List[Redundante]:
        """
        Selecciona redundantes usando QR con pivoteo (Nivel 1) y spanning tree (Nivel 2).

        **Nivel 1 — QR sobre reacciones:**
            Construye A (3×r) donde cada columna j captura la contribución de la
            j-ésima reacción candidata al equilibrio global:

            - Rx en (xₙ, yₙ): columna = [1, 0, −(yₙ−y_ref)]
            - Ry en (xₙ, yₙ): columna = [0, 1,  (xₙ−x_ref)]
            - Mz en (xₙ, yₙ): columna = [0, 0,  1           ]

            ``scipy.linalg.qr(A, pivoting=True)`` devuelve el vector de pivotes P
            tal que las primeras 3 columnas de A[:,P] son linealmente independientes
            → forman la base isostática.  Las columnas P[3:] son los redundantes.

        **Nivel 2 — Spanning tree (BFS):**
            Si aún se necesitan redundantes internos, recorre el grafo de barras
            con BFS.  Las barras que no pertenecen al árbol de expansión crean
            loops cerrados: sus cortes (MOMENTO_INTERNO) son los redundantes.

        Args:
            n_redundantes: GH de la estructura

        Returns:
            Lista de redundantes seleccionados (longitud == n_redundantes)

        Raises:
            ImportError: Si scipy no está disponible
            ValueError: Si no se pueden encontrar suficientes redundantes válidos
        """
        import numpy as np
        from scipy.linalg import qr as scipy_qr  # lanza ImportError si no hay scipy

        cand_reaccion = [
            c for c in self._candidatos
            if c.tipo in (
                TipoRedundante.REACCION_RX,
                TipoRedundante.REACCION_RY,
                TipoRedundante.REACCION_MZ,
            )
        ]
        r = len(cand_reaccion)
        seleccionados: List[Redundante] = []

        # ── Nivel 1: QR para redundantes de apoyo ────────────────────────────
        if r > 3:
            nudos_vinculados = [n for n in self.modelo.nudos if n.tiene_vinculo]
            denom = max(len(nudos_vinculados), 1)
            x_ref = sum(n.x for n in nudos_vinculados) / denom
            y_ref = sum(n.y for n in nudos_vinculados) / denom

            nudos_map: Dict[int, object] = {n.id: n for n in self.modelo.nudos}
            A = np.zeros((3, r), dtype=np.float64)

            for j, cand in enumerate(cand_reaccion):
                nudo = nudos_map.get(cand.nudo_id)
                if nudo is None:
                    continue
                dx = nudo.x - x_ref
                dy = nudo.y - y_ref
                if cand.tipo == TipoRedundante.REACCION_RX:
                    A[0, j] = 1.0       # ΣFx
                    A[2, j] = -dy       # ΣMz: Rx·(−Δy)
                elif cand.tipo == TipoRedundante.REACCION_RY:
                    A[1, j] = 1.0       # ΣFy
                    A[2, j] = dx        # ΣMz: Ry·(+Δx)
                elif cand.tipo == TipoRedundante.REACCION_MZ:
                    A[2, j] = 1.0       # ΣMz directo

            _, _, piv = scipy_qr(A, pivoting=True)

            # Columnas piv[3:] = reacciones redundantes (fuera de la base)
            n_red_reaccion = min(r - 3, n_redundantes)
            for k in range(n_red_reaccion):
                seleccionados.append(cand_reaccion[piv[3 + k]])

        # ── Nivel 2: spanning tree para redundantes internos ─────────────────
        n_restantes = n_redundantes - len(seleccionados)
        if n_restantes > 0:
            internos = self._seleccionar_internos_spanning_tree(n_restantes)
            seleccionados.extend(internos)

        # ── Fallback parcial: candidatos internos pre-identificados ───────────
        n_restantes = n_redundantes - len(seleccionados)
        if n_restantes > 0:
            cand_internos = [
                c for c in self._candidatos
                if c.tipo == TipoRedundante.MOMENTO_INTERNO
            ]
            usados_ids = {id(s) for s in seleccionados}
            for c in cand_internos:
                if n_restantes <= 0:
                    break
                if id(c) not in usados_ids:
                    seleccionados.append(c)
                    n_restantes -= 1

        if len(seleccionados) < n_redundantes:
            raise ValueError(
                f"QR: no se encontraron suficientes redundantes "
                f"(necesarios={n_redundantes}, encontrados={len(seleccionados)})"
            )

        return seleccionados

    def _seleccionar_internos_spanning_tree(
        self, n_internos: int
    ) -> List[Redundante]:
        """
        Identifica redundantes internos mediante spanning tree BFS.

        El grafo de la estructura tiene nudos como vértices y barras como aristas.
        Un spanning tree de (n_nudos) vértices tiene exactamente (n_nudos − 1)
        aristas.  Toda barra adicional crea un loop cerrado, lo que equivale a
        un grado de hiperestaticidad interno.

        Para cada barra extra se genera un ``MOMENTO_INTERNO`` en la sección
        media (x = L/2), que equivale a introducir una rótula virtual en ese
        punto para la estructura isostática principal.

        Args:
            n_internos: Número de redundantes internos necesarios

        Returns:
            Lista de redundantes MOMENTO_INTERNO (puede ser menor que n_internos
            si no hay suficientes barras extra)
        """
        if not self.modelo.barras or n_internos <= 0:
            return []

        # Grafo de adyacencia: nudo_id → [(nudo_vecino_id, barra), ...]
        adj: Dict[int, List] = {n.id: [] for n in self.modelo.nudos}
        for barra in self.modelo.barras:
            adj[barra.nudo_i.id].append((barra.nudo_j.id, barra))
            adj[barra.nudo_j.id].append((barra.nudo_i.id, barra))

        # BFS para construir el spanning tree
        inicio = self.modelo.nudos[0].id
        visitados: Set[int] = {inicio}
        barras_en_arbol: Set[int] = set()
        cola: deque = deque([inicio])

        while cola:
            nudo_actual = cola.popleft()
            for nudo_vecino, barra in adj[nudo_actual]:
                if nudo_vecino not in visitados:
                    visitados.add(nudo_vecino)
                    barras_en_arbol.add(barra.id)
                    cola.append(nudo_vecino)

        # Barras que NO están en el spanning tree → crean loops (redundantes)
        barras_extra = [
            b for b in self.modelo.barras if b.id not in barras_en_arbol
        ]

        redundantes: List[Redundante] = []
        for barra in barras_extra:
            if len(redundantes) >= n_internos:
                break
            redundantes.append(Redundante(
                tipo=TipoRedundante.MOMENTO_INTERNO,
                barra_id=barra.id,
                nudo_id=barra.nudo_i.id,
                posicion=barra.L / 2.0,
            ))

        return redundantes

    def _aplicar_heuristica(self, n_redundantes: int) -> List[Redundante]:
        """
        Aplica heurística para seleccionar los mejores redundantes.

        Orden de prioridad:
        1. Momentos de reacción (Mz) - suelen dar mejor condicionamiento
        2. Reacciones verticales (Ry) - fáciles de interpretar
        3. Reacciones horizontales (Rx)
        4. Momentos internos

        Args:
            n_redundantes: Número de redundantes a seleccionar

        Returns:
            Lista de redundantes seleccionados
        """
        # Ordenar candidatos por prioridad
        def prioridad(red: Redundante) -> int:
            if red.tipo == TipoRedundante.REACCION_MZ:
                return 0  # Máxima prioridad
            elif red.tipo == TipoRedundante.REACCION_RY:
                return 1
            elif red.tipo == TipoRedundante.REACCION_RX:
                return 2
            elif red.tipo == TipoRedundante.MOMENTO_INTERNO:
                return 3
            else:
                return 4

        candidatos_ordenados = sorted(self._candidatos, key=prioridad)

        # Seleccionar los primeros n_redundantes, verificando estabilidad
        seleccionados = []
        usados: Set[Tuple[int, TipoRedundante]] = set()

        for candidato in candidatos_ordenados:
            if len(seleccionados) >= n_redundantes:
                break

            # Evitar redundantes duplicados
            clave = (candidato.nudo_id, candidato.tipo)
            if clave in usados:
                continue

            # Verificar que la selección no crea inestabilidad
            if self._crea_inestabilidad(seleccionados + [candidato]):
                continue

            seleccionados.append(candidato)
            usados.add(clave)

        if len(seleccionados) < n_redundantes:
            raise ValueError(
                f"No se pudieron seleccionar {n_redundantes} redundantes válidos. "
                f"Solo se encontraron {len(seleccionados)} candidatos viables."
            )

        return seleccionados

    def _crea_inestabilidad(self, redundantes: List[Redundante]) -> bool:
        """
        Verifica si la selección de redundantes crea una subestructura inestable.

        Una selección es inestable si al liberar los redundantes, la estructura
        fundamental resultante es un mecanismo.

        Realiza dos verificaciones:
        1. Conteo básico: deben quedar exactamente 3 reacciones para isostática.
        2. Rango geométrico: la matriz de equilibrio de las reacciones restantes
           debe tener rango 3 (no degenerar por fuerzas colineales o paralelas).

        Args:
            redundantes: Lista de redundantes a verificar

        Returns:
            True si la selección crea inestabilidad
        """
        import numpy as np

        # ── 1. Conteo básico ──────────────────────────────────────────────────
        reacciones_totales = self.modelo.num_reacciones
        reacciones_liberadas = sum(
            1 for r in redundantes
            if r.tipo in (
                TipoRedundante.REACCION_RX,
                TipoRedundante.REACCION_RY,
                TipoRedundante.REACCION_MZ,
            )
        )
        reacciones_restantes = reacciones_totales - reacciones_liberadas

        # Para estructura isostática necesitamos exactamente 3 reacciones
        if reacciones_restantes < 3:
            return True

        # ── 2. Verificación de rango geométrico ───────────────────────────────
        # (Única verificación necesaria: la comprobación por-nudo de "todos los
        # GDL liberados" era demasiado conservadora — rechazaba combinaciones
        # válidas como liberar el único GDL de un Rodillo intermediario, lo cual
        # produce una estructura isostática correcta si el rango de la matriz de
        # equilibrio resultante es 3.  El rank-check a continuación es suficiente.)
        # Construir la matriz de equilibrio para las reacciones que QUEDAN
        # (sin las redundantes actuales). Si la matriz es singular o de rango < 3,
        # la selección genera inestabilidad geométrica (e.g. todas las fuerzas
        # son paralelas y no equilibran momentos).
        ids_redundantes = set(
            (r.nudo_id, r.tipo) for r in redundantes
        )

        # Punto de referencia para momentos: primer nudo vinculado
        nudos_vinculados = [n for n in self.modelo.nudos if n.tiene_vinculo]
        if not nudos_vinculados:
            return True

        x_ref = nudos_vinculados[0].x
        y_ref = nudos_vinculados[0].y

        # Identificar incógnitas que QUEDAN tras liberar los redundantes
        incognitas_restantes = []
        for nudo in self.modelo.nudos:
            if not nudo.tiene_vinculo:
                continue
            gdl_nudo = nudo.vinculo.gdl_restringidos()
            for gdl in gdl_nudo:
                if gdl == "Ux":
                    tipo = TipoRedundante.REACCION_RX
                elif gdl == "Uy":
                    tipo = TipoRedundante.REACCION_RY
                elif gdl == "θz":
                    tipo = TipoRedundante.REACCION_MZ
                else:
                    continue
                # Incluir solo si NO es redundante
                if (nudo.id, tipo) not in ids_redundantes:
                    incognitas_restantes.append((nudo, gdl))

        if len(incognitas_restantes) != 3:
            # Si no quedan exactamente 3, ya lo detectamos arriba
            return reacciones_restantes < 3

        # Construir matriz A (3×3) para las 3 incógnitas restantes
        A = np.zeros((3, 3))
        for j, (nudo, gdl) in enumerate(incognitas_restantes):
            if gdl == "Ux":
                A[0, j] = 1.0
                A[2, j] = (nudo.y - y_ref)
            elif gdl == "Uy":
                A[1, j] = 1.0
                A[2, j] = -(nudo.x - x_ref)
            elif gdl == "θz":
                A[2, j] = -1.0  # Convención adoptada (negativa, ver equilibrio.py)

        # Si la matriz es singular, la selección es inestable
        rank = np.linalg.matrix_rank(A)
        if rank < 3:
            return True

        return False

    def _validar_redundante(self, red: Redundante) -> None:
        """
        Valida que un redundante sea válido para el modelo.

        Args:
            red: Redundante a validar

        Raises:
            ValueError: Si el redundante no es válido
        """
        if red.tipo in (
            TipoRedundante.REACCION_RX,
            TipoRedundante.REACCION_RY,
            TipoRedundante.REACCION_MZ,
        ):
            # Verificar que el nudo existe y tiene el vínculo apropiado
            nudo = self.modelo.obtener_nudo(red.nudo_id)
            if nudo is None:
                raise ValueError(f"Nudo {red.nudo_id} no existe")
            if not nudo.tiene_vinculo:
                raise ValueError(f"Nudo {red.nudo_id} no tiene vínculo")

            gdl = nudo.vinculo.gdl_restringidos()
            if red.tipo == TipoRedundante.REACCION_RX and "Ux" not in gdl:
                raise ValueError(f"Nudo {red.nudo_id} no restringe Ux")
            if red.tipo == TipoRedundante.REACCION_RY and "Uy" not in gdl:
                raise ValueError(f"Nudo {red.nudo_id} no restringe Uy")
            if red.tipo == TipoRedundante.REACCION_MZ and "θz" not in gdl:
                raise ValueError(f"Nudo {red.nudo_id} no restringe θz")

        elif red.tipo == TipoRedundante.MOMENTO_INTERNO:
            # Verificar que la barra existe
            barra = self.modelo.obtener_barra(red.barra_id)
            if barra is None:
                raise ValueError(f"Barra {red.barra_id} no existe")

    @property
    def candidatos(self) -> List[Redundante]:
        """Lista de todos los candidatos identificados."""
        return self._candidatos

    @property
    def seleccionados(self) -> List[Redundante]:
        """Lista de redundantes seleccionados."""
        return self._seleccionados
