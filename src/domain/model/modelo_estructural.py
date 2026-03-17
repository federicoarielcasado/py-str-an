"""
Clase ModeloEstructural: contenedor principal del modelo de pórtico plano.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Set, Tuple

from src.domain.entities.barra import Barra
from src.domain.entities.carga import (
    Carga,
    CargaDistribuida,
    CargaPuntualBarra,
    CargaPuntualNudo,
    CargaTermica,
    MovimientoImpuesto,
)
from src.domain.entities.material import Material
from src.domain.entities.nudo import Nudo
from src.domain.entities.seccion import Seccion
from src.domain.entities.vinculo import Vinculo
from src.utils.constants import GDL_POR_NUDO, LENGTH_TOLERANCE


@dataclass
class ModeloEstructural:
    """
    Contenedor principal del modelo estructural de un pórtico plano 2D.

    Esta clase agrupa todos los componentes del modelo:
    - Nudos con sus coordenadas y vínculos
    - Barras conectando nudos
    - Cargas aplicadas
    - Materiales y secciones disponibles

    Proporciona métodos para:
    - Agregar y remover elementos
    - Validar la consistencia del modelo
    - Calcular propiedades globales (grado de hiperestaticidad, etc.)

    Attributes:
        nombre: Nombre identificador del proyecto
        descripcion: Descripción opcional del modelo

    Example:
        >>> modelo = ModeloEstructural("Viga biempotrada")
        >>> n1 = modelo.agregar_nudo(0, 0, "A")
        >>> n2 = modelo.agregar_nudo(6, 0, "B")
        >>> mat = Material("Acero", E=200e6)
        >>> sec = SeccionRectangular("30x50", b=0.30, _h=0.50)
        >>> barra = modelo.agregar_barra(n1, n2, mat, sec)
    """

    nombre: str = "Sin título"
    descripcion: str = ""

    # Colecciones principales
    _nudos: Dict[int, Nudo] = field(default_factory=dict, repr=False)
    _barras: Dict[int, Barra] = field(default_factory=dict, repr=False)
    _cargas: List[Carga] = field(default_factory=list, repr=False)

    # Catálogos de materiales y secciones disponibles
    _materiales: Dict[str, Material] = field(default_factory=dict, repr=False)
    _secciones: Dict[str, Seccion] = field(default_factory=dict, repr=False)

    # Contadores para IDs automáticos
    _siguiente_id_nudo: int = field(default=1, repr=False)
    _siguiente_id_barra: int = field(default=1, repr=False)

    # Estado del modelo
    _modificado: bool = field(default=False, repr=False)
    _resuelto: bool = field(default=False, repr=False)

    # =========================================================================
    # PROPIEDADES DE ACCESO A COLECCIONES
    # =========================================================================

    @property
    def nudos(self) -> List[Nudo]:
        """Lista de todos los nudos del modelo."""
        return list(self._nudos.values())

    @property
    def barras(self) -> List[Barra]:
        """Lista de todas las barras del modelo."""
        return list(self._barras.values())

    @property
    def cargas(self) -> List[Carga]:
        """Lista de todas las cargas del modelo (instantánea de solo lectura).

        Devuelve una **copia** de la lista interna para proteger el estado
        del modelo. Cualquier modificación directa sobre la lista retornada
        (p.ej. ``.append()``) no tendrá efecto.

        Para agregar, usar :meth:`agregar_carga`.
        Para eliminar, usar :meth:`remover_carga`.
        """
        return list(self._cargas)

    @property
    def materiales(self) -> List[Material]:
        """Lista de materiales disponibles en el modelo."""
        return list(self._materiales.values())

    @property
    def secciones(self) -> List[Seccion]:
        """Lista de secciones disponibles en el modelo."""
        return list(self._secciones.values())

    # =========================================================================
    # CONTADORES Y ESTADÍSTICAS
    # =========================================================================

    @property
    def num_nudos(self) -> int:
        """Número de nudos en el modelo."""
        return len(self._nudos)

    @property
    def num_barras(self) -> int:
        """Número de barras en el modelo."""
        return len(self._barras)

    @property
    def num_cargas(self) -> int:
        """Número de cargas aplicadas."""
        return len(self._cargas)

    @property
    def num_vinculos(self) -> int:
        """Número de nudos con vínculos externos."""
        return sum(1 for n in self._nudos.values() if n.tiene_vinculo)

    @property
    def num_reacciones(self) -> int:
        """
        Número total de reacciones de vínculo (GDL restringidos).

        Es la suma de los GDL restringidos por todos los vínculos.
        """
        return sum(n.num_reacciones for n in self._nudos.values())

    @property
    def num_gdl_totales(self) -> int:
        """
        Número total de grados de libertad del sistema.

        Para pórticos planos 2D: 3 GDL por nudo (Ux, Uy, θz).
        """
        return self.num_nudos * GDL_POR_NUDO

    @property
    def num_gdl_libres(self) -> int:
        """Número de grados de libertad no restringidos."""
        return self.num_gdl_totales - self.num_reacciones

    # =========================================================================
    # GRADO DE HIPERESTATICIDAD
    # =========================================================================

    @property
    def grado_hiperestaticidad(self) -> int:
        """
        Calcula el grado de hiperestaticidad del sistema.

        Fórmula para pórticos planos cerrados:
            gh = r + 3*c - 3*n

        Donde:
            r = número de reacciones de vínculo externo
            c = número de barras (conectividades)
            n = número de nudos

        Interpretación:
            gh < 0: Estructura hipostática (mecanismo)
            gh = 0: Estructura isostática
            gh > 0: Estructura hiperestática (gh redundantes)

        Returns:
            Grado de hiperestaticidad (entero)
        """
        r = self.num_reacciones
        c = self.num_barras
        n = self.num_nudos

        # Ajuste por articulaciones internas (cada una reduce GH en 1)
        articulaciones_internas = sum(
            (1 if b.articulacion_i else 0) + (1 if b.articulacion_j else 0)
            for b in self._barras.values()
        )

        # Fórmula: gh = r + 3*c - 3*n - articulaciones
        gh = r + 3 * c - 3 * n - articulaciones_internas

        return gh

    @property
    def es_hipostatica(self) -> bool:
        """True si la estructura es hipostática (mecanismo)."""
        return self.grado_hiperestaticidad < 0

    @property
    def es_isostatica(self) -> bool:
        """True si la estructura es isostática."""
        return self.grado_hiperestaticidad == 0

    @property
    def es_hiperestatica(self) -> bool:
        """True si la estructura es hiperestática."""
        return self.grado_hiperestaticidad > 0

    @property
    def clasificacion_estatica(self) -> str:
        """Clasificación estática del sistema."""
        gh = self.grado_hiperestaticidad
        if gh < 0:
            return f"Hipostática (faltan {-gh} vínculos)"
        elif gh == 0:
            return "Isostática"
        else:
            return f"Hiperestática de grado {gh}"

    # =========================================================================
    # GESTIÓN DE NUDOS
    # =========================================================================

    def agregar_nudo(
        self,
        x: float,
        y: float,
        nombre: str = "",
        id: Optional[int] = None
    ) -> Nudo:
        """
        Agrega un nuevo nudo al modelo.

        Args:
            x: Coordenada X [m]
            y: Coordenada Y [m]
            nombre: Nombre opcional del nudo
            id: ID específico (se genera automáticamente si no se proporciona)

        Returns:
            El nudo creado

        Raises:
            ValueError: Si ya existe un nudo con el mismo ID
            ValueError: Si ya existe un nudo en las mismas coordenadas
        """
        # Determinar ID
        if id is None:
            id = self._siguiente_id_nudo
            self._siguiente_id_nudo += 1
        elif id in self._nudos:
            raise ValueError(f"Ya existe un nudo con ID {id}")

        # Verificar que no haya otro nudo en las mismas coordenadas
        import math
        for nudo_existente in self._nudos.values():
            dist = math.hypot(nudo_existente.x - x, nudo_existente.y - y)
            if dist < LENGTH_TOLERANCE:
                raise ValueError(
                    f"Ya existe un nudo (ID {nudo_existente.id}) en las coordenadas ({x}, {y})"
                )

        # Crear y agregar nudo
        nudo = Nudo(id=id, x=x, y=y, nombre=nombre)
        self._nudos[id] = nudo
        self._marcar_modificado()

        # Actualizar contador si es necesario
        if id >= self._siguiente_id_nudo:
            self._siguiente_id_nudo = id + 1

        return nudo

    def obtener_nudo(self, id: int) -> Optional[Nudo]:
        """
        Obtiene un nudo por su ID.

        Args:
            id: ID del nudo

        Returns:
            El nudo, o None si no existe
        """
        return self._nudos.get(id)

    def remover_nudo(self, id: int) -> bool:
        """
        Remueve un nudo del modelo.

        También remueve todas las barras conectadas al nudo.

        Args:
            id: ID del nudo a remover

        Returns:
            True si se removió, False si no existía
        """
        if id not in self._nudos:
            return False

        nudo = self._nudos[id]

        # Remover barras conectadas
        barras_a_remover = [
            b.id for b in self._barras.values()
            if b.nudo_i.id == id or b.nudo_j.id == id
        ]
        for barra_id in barras_a_remover:
            self.remover_barra(barra_id)

        # Remover cargas nodales asociadas
        self._cargas = [
            c for c in self._cargas
            if not (isinstance(c, (CargaPuntualNudo, MovimientoImpuesto)) and c.nudo == nudo)
        ]

        # Remover el nudo
        del self._nudos[id]
        self._marcar_modificado()
        return True

    def nudo_en_coordenadas(self, x: float, y: float, tolerancia: float = 0.01) -> Optional[Nudo]:
        """
        Busca un nudo cerca de las coordenadas especificadas.

        Args:
            x: Coordenada X [m]
            y: Coordenada Y [m]
            tolerancia: Distancia máxima para considerar coincidencia [m]

        Returns:
            El nudo más cercano dentro de la tolerancia, o None
        """
        import math
        for nudo in self._nudos.values():
            dist = math.hypot(nudo.x - x, nudo.y - y)
            if dist < tolerancia:
                return nudo
        return None

    # =========================================================================
    # GESTIÓN DE BARRAS
    # =========================================================================

    def agregar_barra(
        self,
        nudo_i: Nudo,
        nudo_j: Nudo,
        material: Material,
        seccion: Seccion,
        nombre: str = "",
        id: Optional[int] = None
    ) -> Barra:
        """
        Agrega una nueva barra al modelo.

        Args:
            nudo_i: Nudo inicial
            nudo_j: Nudo final
            material: Material de la barra
            seccion: Sección transversal
            nombre: Nombre opcional
            id: ID específico (se genera automáticamente si no se proporciona)

        Returns:
            La barra creada

        Raises:
            ValueError: Si los nudos no pertenecen al modelo
            ValueError: Si ya existe una barra con el mismo ID
            ValueError: Si ya existe una barra entre los mismos nudos
        """
        # Validar que los nudos pertenecen al modelo
        if nudo_i.id not in self._nudos:
            raise ValueError(f"El nudo inicial (ID {nudo_i.id}) no pertenece al modelo")
        if nudo_j.id not in self._nudos:
            raise ValueError(f"El nudo final (ID {nudo_j.id}) no pertenece al modelo")

        # Determinar ID
        if id is None:
            id = self._siguiente_id_barra
            self._siguiente_id_barra += 1
        elif id in self._barras:
            raise ValueError(f"Ya existe una barra con ID {id}")

        # Verificar que no exista barra duplicada
        for barra in self._barras.values():
            if (barra.nudo_i.id == nudo_i.id and barra.nudo_j.id == nudo_j.id) or \
               (barra.nudo_i.id == nudo_j.id and barra.nudo_j.id == nudo_i.id):
                raise ValueError(
                    f"Ya existe una barra (ID {barra.id}) entre los nudos {nudo_i.id} y {nudo_j.id}"
                )

        # Registrar material y sección si no existen
        if material.nombre not in self._materiales:
            self._materiales[material.nombre] = material
        if seccion.nombre not in self._secciones:
            self._secciones[seccion.nombre] = seccion

        # Crear y agregar barra
        barra = Barra(
            id=id,
            nudo_i=nudo_i,
            nudo_j=nudo_j,
            material=material,
            seccion=seccion,
            nombre=nombre,
        )
        self._barras[id] = barra
        self._marcar_modificado()

        # Actualizar contador
        if id >= self._siguiente_id_barra:
            self._siguiente_id_barra = id + 1

        return barra

    def obtener_barra(self, id: int) -> Optional[Barra]:
        """
        Obtiene una barra por su ID.

        Args:
            id: ID de la barra

        Returns:
            La barra, o None si no existe
        """
        return self._barras.get(id)

    def remover_barra(self, id: int) -> bool:
        """
        Remueve una barra del modelo.

        También remueve las cargas asociadas a la barra.

        Args:
            id: ID de la barra a remover

        Returns:
            True si se removió, False si no existía
        """
        if id not in self._barras:
            return False

        barra = self._barras[id]

        # Remover cargas sobre la barra
        self._cargas = [
            c for c in self._cargas
            if not (isinstance(c, (CargaPuntualBarra, CargaDistribuida, CargaTermica))
                   and c.barra == barra)
        ]

        del self._barras[id]
        self._marcar_modificado()
        return True

    def barras_conectadas_a_nudo(self, nudo_id: int) -> List[Barra]:
        """
        Obtiene todas las barras conectadas a un nudo.

        Args:
            nudo_id: ID del nudo

        Returns:
            Lista de barras conectadas
        """
        return [
            b for b in self._barras.values()
            if b.nudo_i.id == nudo_id or b.nudo_j.id == nudo_id
        ]

    # =========================================================================
    # GESTIÓN DE VÍNCULOS
    # =========================================================================

    def asignar_vinculo(self, nudo_id: int, vinculo: Vinculo) -> None:
        """
        Asigna un vínculo externo a un nudo.

        Args:
            nudo_id: ID del nudo
            vinculo: Vínculo a asignar

        Raises:
            ValueError: Si el nudo no existe
        """
        nudo = self._nudos.get(nudo_id)
        if nudo is None:
            raise ValueError(f"No existe el nudo con ID {nudo_id}")

        nudo.asignar_vinculo(vinculo)
        self._marcar_modificado()

    def liberar_vinculo(self, nudo_id: int) -> Optional[Vinculo]:
        """
        Libera el vínculo de un nudo.

        Args:
            nudo_id: ID del nudo

        Returns:
            El vínculo que estaba asignado, o None
        """
        nudo = self._nudos.get(nudo_id)
        if nudo is None:
            return None

        vinculo = nudo.liberar_vinculo()
        if vinculo is not None:
            self._marcar_modificado()
        return vinculo

    @property
    def nudos_vinculados(self) -> List[Nudo]:
        """Lista de nudos que tienen vínculos externos."""
        return [n for n in self._nudos.values() if n.tiene_vinculo]

    @property
    def nudos_libres(self) -> List[Nudo]:
        """Lista de nudos sin vínculos externos."""
        return [n for n in self._nudos.values() if n.es_libre]

    # =========================================================================
    # GESTIÓN DE ARTICULACIONES INTERNAS (RÓTULAS)
    # =========================================================================

    def agregar_articulacion(
        self,
        barra_id: int,
        extremo: str = "i"
    ) -> None:
        """
        Agrega una articulación interna (rótula) en el extremo de una barra.

        Una articulación interna libera la continuidad de momento, permitiendo
        rotación relativa. Reduce el grado de hiperestaticidad en 1.

        Args:
            barra_id: ID de la barra
            extremo: "i" para extremo inicial, "j" para extremo final

        Raises:
            ValueError: Si la barra no existe o el extremo es inválido
        """
        barra = self._barras.get(barra_id)
        if barra is None:
            raise ValueError(f"No existe la barra con ID {barra_id}")

        if extremo.lower() == "i":
            barra.articulacion_i = True
        elif extremo.lower() == "j":
            barra.articulacion_j = True
        else:
            raise ValueError(f"Extremo inválido: '{extremo}'. Use 'i' o 'j'")

        self._marcar_modificado()

    def remover_articulacion(
        self,
        barra_id: int,
        extremo: str = "i"
    ) -> None:
        """
        Remueve una articulación interna de una barra.

        Args:
            barra_id: ID de la barra
            extremo: "i" para extremo inicial, "j" para extremo final
        """
        barra = self._barras.get(barra_id)
        if barra is None:
            return

        if extremo.lower() == "i":
            barra.articulacion_i = False
        elif extremo.lower() == "j":
            barra.articulacion_j = False

        self._marcar_modificado()

    def tiene_articulacion(self, barra_id: int, extremo: str = "i") -> bool:
        """
        Verifica si una barra tiene articulación en un extremo.

        Args:
            barra_id: ID de la barra
            extremo: "i" o "j"

        Returns:
            True si tiene articulación en ese extremo
        """
        barra = self._barras.get(barra_id)
        if barra is None:
            return False

        if extremo.lower() == "i":
            return barra.articulacion_i
        elif extremo.lower() == "j":
            return barra.articulacion_j
        return False

    @property
    def num_articulaciones_internas(self) -> int:
        """Número total de articulaciones internas en el modelo."""
        return sum(
            (1 if b.articulacion_i else 0) + (1 if b.articulacion_j else 0)
            for b in self._barras.values()
        )

    @property
    def barras_con_articulacion(self) -> List[Barra]:
        """Lista de barras que tienen al menos una articulación interna."""
        return [
            b for b in self._barras.values()
            if b.articulacion_i or b.articulacion_j
        ]

    # =========================================================================
    # GESTIÓN DE CARGAS
    # =========================================================================

    def agregar_carga(self, carga: Carga) -> None:
        """
        Agrega una carga al modelo.

        Args:
            carga: Carga a agregar (nodal, sobre barra, térmica, etc.)

        Raises:
            ValueError: Si la carga referencia elementos que no existen
        """
        # Validar que los elementos referenciados existen
        if isinstance(carga, (CargaPuntualNudo, MovimientoImpuesto)):
            if carga.nudo is not None and carga.nudo.id not in self._nudos:
                raise ValueError(f"El nudo de la carga (ID {carga.nudo.id}) no existe en el modelo")

        if isinstance(carga, (CargaPuntualBarra, CargaDistribuida, CargaTermica)):
            if carga.barra is not None and carga.barra.id not in self._barras:
                raise ValueError(f"La barra de la carga (ID {carga.barra.id}) no existe en el modelo")

        self._cargas.append(carga)
        self._marcar_modificado()

    def remover_carga(self, carga: Carga) -> bool:
        """
        Remueve una carga del modelo.

        Args:
            carga: Carga a remover

        Returns:
            True si se removió, False si no existía
        """
        if carga in self._cargas:
            self._cargas.remove(carga)
            self._marcar_modificado()
            return True
        return False

    def limpiar_cargas(self) -> None:
        """Remueve todas las cargas del modelo."""
        self._cargas.clear()
        self._marcar_modificado()

    @property
    def cargas_nodales(self) -> List[CargaPuntualNudo]:
        """Lista de cargas puntuales en nudos."""
        return [c for c in self._cargas if isinstance(c, CargaPuntualNudo)]

    @property
    def cargas_en_barras(self) -> List[Carga]:
        """Lista de cargas sobre barras (puntuales y distribuidas)."""
        return [c for c in self._cargas if isinstance(c, (CargaPuntualBarra, CargaDistribuida))]

    @property
    def cargas_termicas(self) -> List[CargaTermica]:
        """Lista de cargas térmicas."""
        return [c for c in self._cargas if isinstance(c, CargaTermica)]

    @property
    def movimientos_impuestos(self) -> List[MovimientoImpuesto]:
        """Lista de movimientos impuestos."""
        return [c for c in self._cargas if isinstance(c, MovimientoImpuesto)]

    # =========================================================================
    # VALIDACIÓN
    # =========================================================================

    def validar(self) -> List[str]:
        """
        Valida la consistencia del modelo.

        Returns:
            Lista de mensajes de error/advertencia (vacía si todo está bien)
        """
        errores = []

        # Verificar que hay al menos un nudo y una barra
        if self.num_nudos == 0:
            errores.append("El modelo no tiene nudos")
        if self.num_barras == 0:
            errores.append("El modelo no tiene barras")

        # Verificar que hay vínculos
        if self.num_vinculos == 0:
            errores.append("El modelo no tiene vínculos externos")

        # Verificar hiperestaticidad
        if self.es_hipostatica:
            errores.append(f"Estructura hipostática: {self.clasificacion_estatica}")

        # Verificar conectividad (todos los nudos deben estar conectados)
        nudos_conectados = set()
        for barra in self._barras.values():
            nudos_conectados.add(barra.nudo_i.id)
            nudos_conectados.add(barra.nudo_j.id)

        nudos_aislados = set(self._nudos.keys()) - nudos_conectados
        if nudos_aislados:
            errores.append(f"Nudos sin conectar a barras: {nudos_aislados}")

        # Verificar propiedades de barras
        for barra in self._barras.values():
            if barra.L < LENGTH_TOLERANCE:
                errores.append(f"Barra {barra.id} tiene longitud prácticamente cero")
            if barra.material.E <= 0:
                errores.append(f"Barra {barra.id} tiene módulo de elasticidad no positivo")
            if barra.seccion.A <= 0:
                errores.append(f"Barra {barra.id} tiene área de sección no positiva")
            if barra.seccion.Iz <= 0:
                errores.append(f"Barra {barra.id} tiene momento de inercia no positivo")

        return errores

    @property
    def es_valido(self) -> bool:
        """True si el modelo pasa todas las validaciones."""
        return len(self.validar()) == 0

    # =========================================================================
    # GEOMETRÍA GLOBAL
    # =========================================================================

    @property
    def bounding_box(self) -> Tuple[float, float, float, float]:
        """
        Calcula el rectángulo envolvente del modelo.

        Returns:
            Tupla (x_min, y_min, x_max, y_max)
        """
        if not self._nudos:
            return (0, 0, 0, 0)

        x_coords = [n.x for n in self._nudos.values()]
        y_coords = [n.y for n in self._nudos.values()]

        return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))

    @property
    def centro_geometrico(self) -> Tuple[float, float]:
        """
        Calcula el centro geométrico del modelo.

        Returns:
            Tupla (x_centro, y_centro)
        """
        if not self._nudos:
            return (0, 0)

        x_sum = sum(n.x for n in self._nudos.values())
        y_sum = sum(n.y for n in self._nudos.values())
        n = len(self._nudos)

        return (x_sum / n, y_sum / n)

    # =========================================================================
    # ESTADO DEL MODELO
    # =========================================================================

    def _marcar_modificado(self) -> None:
        """Marca el modelo como modificado (invalida resultados previos)."""
        self._modificado = True
        self._resuelto = False

    @property
    def esta_modificado(self) -> bool:
        """True si el modelo ha sido modificado desde el último guardado."""
        return self._modificado

    @property
    def esta_resuelto(self) -> bool:
        """True si el modelo ha sido resuelto y los resultados son válidos."""
        return self._resuelto

    def marcar_guardado(self) -> None:
        """Marca el modelo como guardado."""
        self._modificado = False

    def marcar_resuelto(self) -> None:
        """Marca el modelo como resuelto."""
        self._resuelto = True

    # =========================================================================
    # REINICIO
    # =========================================================================

    def reiniciar_resultados(self) -> None:
        """Reinicia todos los resultados del análisis."""
        for nudo in self._nudos.values():
            nudo.reiniciar_resultados()
            if nudo.vinculo:
                nudo.vinculo.reiniciar_reacciones()

        for barra in self._barras.values():
            barra.asignar_esfuerzos(
                lambda x: 0.0,
                lambda x: 0.0,
                lambda x: 0.0
            )

        self._resuelto = False

    def limpiar(self) -> None:
        """Elimina todos los elementos del modelo."""
        self._nudos.clear()
        self._barras.clear()
        self._cargas.clear()
        self._materiales.clear()
        self._secciones.clear()
        self._siguiente_id_nudo = 1
        self._siguiente_id_barra = 1
        self._marcar_modificado()

    # =========================================================================
    # REPRESENTACIÓN
    # =========================================================================

    def __str__(self) -> str:
        return (
            f"ModeloEstructural '{self.nombre}': "
            f"{self.num_nudos} nudos, {self.num_barras} barras, "
            f"{self.num_cargas} cargas, {self.clasificacion_estatica}"
        )

    def resumen(self) -> str:
        """Genera un resumen detallado del modelo."""
        lineas = [
            f"=== Modelo: {self.nombre} ===",
            f"Descripción: {self.descripcion or 'N/A'}",
            "",
            "GEOMETRÍA:",
            f"  Nudos: {self.num_nudos}",
            f"  Barras: {self.num_barras}",
            f"  Vínculos externos: {self.num_vinculos}",
            "",
            "ANÁLISIS ESTÁTICO:",
            f"  GDL totales: {self.num_gdl_totales}",
            f"  Reacciones: {self.num_reacciones}",
            f"  GDL libres: {self.num_gdl_libres}",
            f"  Grado de hiperestaticidad: {self.grado_hiperestaticidad}",
            f"  Clasificación: {self.clasificacion_estatica}",
            "",
            "CARGAS:",
            f"  Cargas nodales: {len(self.cargas_nodales)}",
            f"  Cargas en barras: {len(self.cargas_en_barras)}",
            f"  Cargas térmicas: {len(self.cargas_termicas)}",
            f"  Movimientos impuestos: {len(self.movimientos_impuestos)}",
        ]

        if self._modificado:
            lineas.append("\n[!] Modelo modificado desde último guardado")
        if self._resuelto:
            lineas.append("[OK] Modelo resuelto")
        else:
            lineas.append("[x] Modelo no resuelto")

        return "\n".join(lineas)
