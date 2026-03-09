"""
Canvas interactivo para visualizar y editar la estructura.
"""

from typing import List, Optional, Tuple, Dict, Any

from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QColor,
    QFont,
    QWheelEvent,
    QMouseEvent,
    QKeyEvent,
)

from src.domain.model.modelo_estructural import ModeloEstructural
from src.domain.entities.nudo import Nudo
from src.domain.entities.barra import Barra
from src.domain.entities.vinculo import (
    Empotramiento, ApoyoFijo, Rodillo, Guia
)


class StructureCanvas(QGraphicsView):
    """
    Canvas interactivo para visualizar y editar estructuras.

    Características:
    - Zoom con rueda del mouse
    - Pan con botón central o Ctrl+arrastre
    - Creación de nudos y barras
    - Selección de elementos
    - Visualización de diagramas de esfuerzos
    - Snap to grid configurable

    Signals:
        selection_changed: Emitido cuando cambia la selección
        model_changed: Emitido cuando se modifica el modelo
        coordinates_changed: Emitido cuando cambian las coordenadas del cursor
    """

    # Señales
    selection_changed = pyqtSignal(list)
    model_changed = pyqtSignal()
    coordinates_changed = pyqtSignal(float, float)  # x, y en mundo

    # Colores
    COLOR_FONDO = QColor(250, 250, 250)
    COLOR_GRILLA = QColor(220, 220, 220)
    COLOR_GRILLA_PRINCIPAL = QColor(180, 180, 180)
    COLOR_NUDO = QColor(0, 80, 180)  # Azul más visible
    COLOR_NUDO_SELECCIONADO = QColor(255, 100, 0)
    COLOR_NUDO_HOVER = QColor(100, 180, 255)  # Para hover
    COLOR_BARRA = QColor(50, 50, 50)
    COLOR_BARRA_SELECCIONADA = QColor(255, 100, 0)
    COLOR_VINCULO = QColor(0, 130, 0)
    COLOR_CARGA = QColor(200, 0, 0)
    COLOR_MOMENTO = QColor(200, 0, 200)
    COLOR_PREVIEW = QColor(100, 100, 255, 150)  # Para previsualización

    def __init__(self, modelo: ModeloEstructural, parent=None):
        super().__init__(parent)

        self.modelo = modelo
        self._resultado = None

        # Configurar escena
        self.scene = QGraphicsScene()
        self.setScene(self.scene)

        # Configurar vista
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)  # Para detectar movimiento sin clic

        # Estado interno
        self._mode = "select"  # select, create_node, create_bar
        self._zoom_factor = 1.0
        self._show_grid = True
        self._show_diagrams = False

        # Opciones de diagramas
        self._show_diagrama_M = True   # Mostrar diagrama de momentos
        self._show_diagrama_V = True   # Mostrar diagrama de cortantes
        self._show_diagrama_N = True   # Mostrar diagrama de axiles
        self._escala_diagramas: float | None = None  # None = auto

        # Configuración de grilla
        self._grid_size = 1.0  # metros
        self._snap_enabled = True  # Snap to grid activado

        # Selección
        self._selected_nodes: List[int] = []
        self._selected_bars: List[int] = []

        # Estado de creación de barra
        self._temp_bar_start: Optional[Nudo] = None

        # Posición actual del cursor (en coordenadas del mundo)
        self._cursor_world_pos: Tuple[float, float] = (0.0, 0.0)
        self._cursor_snapped_pos: Tuple[float, float] = (0.0, 0.0)

        # Escala: píxeles por metro
        self._scale = 50.0

        # Callback opcional para Undo/Redo: se llama ANTES de cada mutación
        self._undo_callback = None  # Callable[[], None]

        # Configurar escena inicial
        self._setup_scene()

    def _setup_scene(self):
        """Configura la escena inicial."""
        # Tamaño inicial de la escena (en metros convertidos a píxeles)
        scene_size = 100 * self._scale
        self.scene.setSceneRect(-scene_size/2, -scene_size/2, scene_size, scene_size)
        self.setBackgroundBrush(QBrush(self.COLOR_FONDO))

    # =========================================================================
    # PROPIEDADES Y CONFIGURACIÓN
    # =========================================================================

    @property
    def grid_size(self) -> float:
        """Tamaño de la celda de la grilla en metros."""
        return self._grid_size

    @grid_size.setter
    def grid_size(self, value: float):
        """Establece el tamaño de la grilla."""
        if value > 0:
            self._grid_size = value
            self.viewport().update()

    @property
    def snap_enabled(self) -> bool:
        """True si el snap to grid está activado."""
        return self._snap_enabled

    @snap_enabled.setter
    def snap_enabled(self, value: bool):
        """Activa o desactiva el snap to grid."""
        self._snap_enabled = value

    def set_model(self, modelo: ModeloEstructural):
        """Establece el modelo a visualizar."""
        self.modelo = modelo
        self._resultado = None
        self._selected_nodes.clear()
        self._selected_bars.clear()
        self.viewport().update()

    def set_resultado(self, resultado):
        """Establece el resultado del análisis."""
        self._resultado = resultado
        self.viewport().update()

    def set_mode(self, mode: str):
        """Establece el modo de interacción."""
        self._mode = mode
        self._temp_bar_start = None

        if mode == "select":
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif mode == "create_node":
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif mode == "create_bar":
            self.setCursor(Qt.CursorShape.CrossCursor)

    def set_undo_callback(self, callback) -> None:
        """
        Registra un callback que se llama ANTES de cada mutación del modelo.

        El callback recibe el modelo actual y debe guardar un snapshot.
        Uso típico: conectar al UndoRedoManager.guardar_estado.

        Args:
            callback: Callable que recibe el modelo, p.ej.
                      ``lambda: manager.guardar_estado(self.modelo)``
        """
        self._undo_callback = callback

    def _guardar_snapshot_undo(self) -> None:
        """Llama al callback de undo si está registrado (antes de mutar)."""
        if self._undo_callback is not None:
            try:
                self._undo_callback()
            except Exception:
                pass  # No interrumpir la operación si el snapshot falla

    def set_grid_visible(self, visible: bool):
        """Muestra u oculta la grilla."""
        self._show_grid = visible
        self.viewport().update()

    def toggle_diagrams(self):
        """Alterna la visualización de diagramas."""
        self._show_diagrams = not self._show_diagrams
        self.viewport().update()

    # =========================================================================
    # TRANSFORMACIONES DE COORDENADAS
    # =========================================================================

    def _world_to_scene(self, x: float, y: float) -> QPointF:
        """Convierte coordenadas del mundo a coordenadas de escena."""
        # En PyQt, Y positivo es hacia abajo, invertimos
        return QPointF(x * self._scale, -y * self._scale)

    def _scene_to_world(self, point: QPointF) -> Tuple[float, float]:
        """Convierte coordenadas de escena a coordenadas del mundo."""
        return (point.x() / self._scale, -point.y() / self._scale)

    def _snap_to_grid(self, x: float, y: float) -> Tuple[float, float]:
        """Ajusta las coordenadas a la grilla si snap está activado."""
        if not self._snap_enabled:
            return (x, y)
        return (
            round(x / self._grid_size) * self._grid_size,
            round(y / self._grid_size) * self._grid_size
        )

    # =========================================================================
    # DIBUJO
    # =========================================================================

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Dibuja el fondo y la grilla."""
        super().drawBackground(painter, rect)

        if not self._show_grid:
            return

        # Dibujar grilla
        grid_pixels = self._grid_size * self._scale

        # Calcular límites de la grilla visible
        left = int(rect.left() / grid_pixels) * grid_pixels
        top = int(rect.top() / grid_pixels) * grid_pixels
        right = rect.right()
        bottom = rect.bottom()

        # Líneas secundarias
        painter.setPen(QPen(self.COLOR_GRILLA, 0.5))
        x = left
        while x <= right:
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid_pixels
        y = top
        while y <= bottom:
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid_pixels

        # Ejes principales (X=0, Y=0)
        painter.setPen(QPen(self.COLOR_GRILLA_PRINCIPAL, 1.5))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Dibuja los elementos del modelo."""
        super().drawForeground(painter, rect)

        # Dibujar barras primero (para que los nudos queden encima)
        for barra in self.modelo.barras:
            self._draw_barra(painter, barra)

        # Dibujar nudos
        for nudo in self.modelo.nudos:
            self._draw_nudo(painter, nudo)

        # Dibujar cargas
        for carga in self.modelo.cargas:
            self._draw_carga(painter, carga)

        # Dibujar diagramas si están activos
        if self._show_diagrams and self._resultado:
            self._draw_diagramas(painter)

        # Dibujar barra temporal
        if self._temp_bar_start is not None:
            self._draw_temp_bar(painter)

        # Dibujar previsualización del nudo en modo crear
        if self._mode == "create_node":
            self._draw_node_preview(painter)

    def _draw_nudo(self, painter: QPainter, nudo: Nudo):
        """Dibuja un nudo con visualización mejorada."""
        pos = self._world_to_scene(nudo.x, nudo.y)

        # Tamaño base del nudo
        radio_exterior = 8
        radio_interior = 5

        # Color según selección
        if nudo.id in self._selected_nodes:
            color = self.COLOR_NUDO_SELECCIONADO
            radio_exterior = 10
            radio_interior = 6
        else:
            color = self.COLOR_NUDO

        # Dibujar círculo exterior (borde)
        painter.setPen(QPen(color.darker(120), 2))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(pos, radio_exterior, radio_exterior)

        # Dibujar círculo interior (punto central más claro)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color.lighter(150)))
        painter.drawEllipse(pos, radio_interior, radio_interior)

        # Dibujar vínculo o reacciones según el estado
        if nudo.tiene_vinculo:
            if self._resultado is not None:
                # Si hay resultados, dibujar reacciones calculadas
                self._draw_reacciones_nudo(painter, nudo)
            else:
                # Si no hay resultados, dibujar símbolos de vínculos
                self._draw_vinculo(painter, nudo)

        # Etiqueta del nudo
        painter.setPen(QPen(Qt.GlobalColor.black))
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        label = nudo.nombre if nudo.nombre else f"N{nudo.id}"
        painter.drawText(pos + QPointF(12, -12), label)

        # Mostrar coordenadas si está seleccionado
        if nudo.id in self._selected_nodes:
            painter.setFont(QFont("Arial", 8))
            painter.setPen(QPen(QColor(80, 80, 80)))
            coord_text = f"({nudo.x:.2f}, {nudo.y:.2f})"
            painter.drawText(pos + QPointF(12, 2), coord_text)

    def _draw_node_preview(self, painter: QPainter):
        """Dibuja una previsualización del nudo donde se creará."""
        x, y = self._cursor_snapped_pos
        pos = self._world_to_scene(x, y)

        # Dibujar círculo semi-transparente
        painter.setPen(QPen(self.COLOR_PREVIEW.darker(110), 2, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(self.COLOR_PREVIEW))
        painter.drawEllipse(pos, 8, 8)

        # Mostrar coordenadas donde se creará
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QPen(QColor(50, 50, 150)))
        coord_text = f"({x:.2f}, {y:.2f})"
        painter.drawText(pos + QPointF(12, -5), coord_text)

    def _draw_barra(self, painter: QPainter, barra: Barra):
        """Dibuja una barra."""
        p1 = self._world_to_scene(barra.nudo_i.x, barra.nudo_i.y)
        p2 = self._world_to_scene(barra.nudo_j.x, barra.nudo_j.y)

        # Color según selección
        if barra.id in self._selected_bars:
            color = self.COLOR_BARRA_SELECCIONADA
            width = 4
        else:
            color = self.COLOR_BARRA
            width = 3

        painter.setPen(QPen(color, width))
        painter.drawLine(p1, p2)

        # Dibujar articulaciones internas
        if barra.articulacion_i:
            self._draw_articulacion(painter, p1)
        if barra.articulacion_j:
            self._draw_articulacion(painter, p2)

        # Etiqueta de la barra (en el centro)
        centro = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QPen(QColor(100, 100, 100)))
        painter.drawText(centro + QPointF(5, -5), f"B{barra.id}")

    def _draw_articulacion(self, painter: QPainter, pos: QPointF):
        """Dibuja símbolo de articulación interna."""
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.drawEllipse(pos, 6, 6)

    def _draw_reacciones_nudo(self, painter: QPainter, nudo: Nudo):
        """
        Dibuja las reacciones calculadas en un nudo (diagrama de cuerpo libre).

        Args:
            painter: QPainter para dibujar
            nudo: Nudo donde se dibujarán las reacciones
        """
        if self._resultado is None or not hasattr(self._resultado, 'reacciones_finales'):
            return

        # Obtener reacciones del nudo
        if nudo.id not in self._resultado.reacciones_finales:
            return

        Rx, Ry, Mz = self._resultado.reacciones_finales[nudo.id]
        pos = self._world_to_scene(nudo.x, nudo.y)

        # Color verde para reacciones (diferente de cargas externas rojas)
        COLOR_REACCION = QColor(0, 130, 0)
        painter.setPen(QPen(COLOR_REACCION, 3))

        # Dibujar reacción horizontal Rx si no es cero
        if abs(Rx) > 0.01:
            # Rx > 0 → reaccion hacia la derecha → 0° en pantalla
            # Rx < 0 → reaccion hacia la izquierda → 180°
            angulo = 0 if Rx > 0 else 180
            longitud = 35 + min(abs(Rx) * 2, 25)
            self._draw_arrow(painter, pos, angulo, longitud)

            # Etiqueta
            offset_x = 50 if Rx > 0 else -70
            offset_y = 5
            self._draw_reaction_label(painter, pos, offset_x, offset_y, f"Rx={Rx:.2f}kN")

        # Dibujar reacción vertical Ry si no es cero
        if abs(Ry) > 0.01:
            # Ry > 0 significa reacción hacia abajo (0°, Y+ es abajo)
            # Ry < 0 significa reacción hacia arriba (180°)
            # PERO en nuestra terna visual, 0°=derecha, así que:
            # - Hacia abajo (Y+): ángulo debe producir flecha hacia abajo
            # - Hacia arriba (Y-): ángulo debe producir flecha hacia arriba
            # En el sistema de _draw_arrow: 0°=derecha, 90°=abajo, -90°=arriba
            if Ry > 0:
                angulo = 90  # hacia abajo
            else:
                angulo = -90  # hacia arriba

            longitud = 35 + min(abs(Ry) * 2, 25)
            self._draw_arrow(painter, pos, angulo, longitud)

            # Etiqueta
            offset_x = 15 if Ry < 0 else -15
            offset_y = -40 if Ry < 0 else 50
            self._draw_reaction_label(painter, pos, offset_x, offset_y, f"Ry={Ry:.2f}kN")

        # Dibujar momento Mz si no es cero
        if abs(Mz) > 0.01:
            painter.setPen(QPen(COLOR_REACCION.darker(110), 3))
            radio = 22
            # Mz > 0: horario (según TERNA)
            # Mz < 0: antihorario
            sentido_antihorario = (Mz < 0)  # _draw_moment espera True para antihorario
            self._draw_moment(painter, pos, radio, sentido_antihorario)

            # Etiqueta
            offset_x = 35
            offset_y = -35
            self._draw_reaction_label(painter, pos, offset_x, offset_y, f"Mz={Mz:.2f}kNm")

    def _draw_reaction_label(self, painter: QPainter, pos: QPointF, offset_x: float,
                            offset_y: float, text: str):
        """Dibuja una etiqueta de reacción con fondo."""
        COLOR_REACCION = QColor(0, 130, 0)

        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))

        # Calcular tamaño del texto
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        text_height = metrics.height()

        # Posición de la etiqueta
        label_pos = pos + QPointF(offset_x, offset_y)

        # Dibujar fondo semi-transparente
        padding = 3
        rect = QRectF(
            label_pos.x() - padding,
            label_pos.y() - text_height + padding,
            text_width + 2 * padding,
            text_height
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(230, 255, 230, 220)))  # Verde muy claro
        painter.drawRect(rect)

        # Dibujar texto
        painter.setPen(QPen(COLOR_REACCION.darker(120)))
        painter.drawText(label_pos, text)

    def _angulo_barra_desde_nudo_screen(self, nudo) -> float:
        """
        Retorna el ángulo (grados) de la barra conectada al nudo en coordenadas
        de pantalla (Y+ hacia abajo en Qt). Se usa para rotar el símbolo del
        empotramiento de manera que su cara quede perpendicular a la barra.

        Para un nudo en la base de una columna vertical (barra va hacia arriba
        en pantalla, ángulo −90°) la rotación resultante orienta el símbolo
        como suelo horizontal con tramado hacia abajo.
        """
        import math
        p_nudo = self._world_to_scene(nudo.x, nudo.y)
        for barra in self.modelo.barras:
            if barra.nudo_i.id == nudo.id:
                p_otro = self._world_to_scene(barra.nudo_j.x, barra.nudo_j.y)
            elif barra.nudo_j.id == nudo.id:
                p_otro = self._world_to_scene(barra.nudo_i.x, barra.nudo_i.y)
            else:
                continue
            return math.degrees(
                math.atan2(p_otro.y() - p_nudo.y(), p_otro.x() - p_nudo.x())
            )
        return 0.0  # Sin barra conectada: orientación por defecto

    def _draw_vinculo(self, painter: QPainter, nudo: Nudo):
        """
        Dibuja el símbolo del vínculo con representación profesional.

        Convenciones:
        - Empotramiento: Línea vertical gruesa con rayas diagonales (hatching)
        - Apoyo fijo (articulado): Triángulo relleno + línea de tierra con hatching
        - Rodillo: Triángulo + círculos debajo + línea base
        - Guía: Dos líneas paralelas con rodillos
        """
        pos = self._world_to_scene(nudo.x, nudo.y)
        vinculo = nudo.vinculo
        size = 18  # Tamaño aumentado para mejor visibilidad

        painter.setPen(QPen(self.COLOR_VINCULO, 2.5))
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        if isinstance(vinculo, Empotramiento):
            # Empotramiento: rectángulo (muro) + tramado diagonal.
            # Se rota según el ángulo de la barra conectada para que la cara
            # del muro quede siempre perpendicular a la barra.
            # Coordenadas locales: el nudo está en (0,0) después de translate.
            ancho_muro = 8
            angulo_barra = self._angulo_barra_desde_nudo_screen(nudo)

            painter.save()
            painter.translate(pos)
            painter.rotate(angulo_barra)  # alinea el sistema local con la barra

            painter.setBrush(QBrush(self.COLOR_VINCULO.lighter(150)))
            painter.setPen(QPen(self.COLOR_VINCULO, 3))

            # Rectángulo del muro en coords locales (centrado en 0,0)
            rect_muro = QRectF(-ancho_muro / 2, -size, ancho_muro, size * 2)
            painter.drawRect(rect_muro)

            # Tramado diagonal a la izquierda del muro (coords locales)
            painter.setPen(QPen(self.COLOR_VINCULO, 2))
            n_rayas = 6
            espacio_rayas = size * 2 / (n_rayas - 1)
            longitud_raya = 12

            for i in range(n_rayas):
                y_start = -size + i * espacio_rayas
                x_start = -ancho_muro / 2
                x_end = x_start - longitud_raya
                y_end = y_start + longitud_raya
                painter.drawLine(
                    QPointF(x_start, y_start),
                    QPointF(x_end, y_end)
                )

            painter.restore()

        elif isinstance(vinculo, ApoyoFijo):
            # Apoyo fijo (articulado): Triángulo relleno + línea tierra con hatching
            # Triángulo
            from PyQt6.QtGui import QPolygonF

            triangulo = QPolygonF([
                pos,  # Vértice superior (en el nudo)
                pos + QPointF(-size, size),  # Vértice inferior izquierdo
                pos + QPointF(size, size),   # Vértice inferior derecho
            ])

            painter.setBrush(QBrush(self.COLOR_VINCULO.lighter(130)))
            painter.setPen(QPen(self.COLOR_VINCULO, 2.5))
            painter.drawPolygon(triangulo)

            # Línea de tierra (base)
            y_tierra = pos.y() + size
            x_left = pos.x() - size - 5
            x_right = pos.x() + size + 5
            painter.setPen(QPen(self.COLOR_VINCULO, 3))
            painter.drawLine(QPointF(x_left, y_tierra), QPointF(x_right, y_tierra))

            # Hatching debajo de la línea de tierra
            painter.setPen(QPen(self.COLOR_VINCULO, 2))
            n_rayas = 7
            espacio = (x_right - x_left) / (n_rayas - 1)
            longitud_raya = 10

            for i in range(n_rayas):
                x = x_left + i * espacio
                painter.drawLine(
                    QPointF(x, y_tierra),
                    QPointF(x - 5, y_tierra + longitud_raya)
                )

        elif isinstance(vinculo, Rodillo):
            # Rodillo: Triángulo + círculos (rodillos) + línea base
            from PyQt6.QtGui import QPolygonF

            # Triángulo más pequeño
            size_tri = size * 0.7
            triangulo = QPolygonF([
                pos,
                pos + QPointF(-size_tri, size_tri),
                pos + QPointF(size_tri, size_tri),
            ])

            painter.setBrush(QBrush(self.COLOR_VINCULO.lighter(130)))
            painter.setPen(QPen(self.COLOR_VINCULO, 2.5))
            painter.drawPolygon(triangulo)

            # Círculos (rodillos) debajo del triángulo
            radio_rodillo = 5
            y_rodillo = pos.y() + size_tri + radio_rodillo

            painter.setBrush(QBrush(Qt.GlobalColor.white))
            painter.setPen(QPen(self.COLOR_VINCULO, 2))

            # Dos rodillos
            painter.drawEllipse(
                QPointF(pos.x() - size_tri/2, y_rodillo),
                radio_rodillo,
                radio_rodillo
            )
            painter.drawEllipse(
                QPointF(pos.x() + size_tri/2, y_rodillo),
                radio_rodillo,
                radio_rodillo
            )

            # Línea de tierra debajo de los rodillos
            y_tierra = y_rodillo + radio_rodillo
            x_left = pos.x() - size - 5
            x_right = pos.x() + size + 5
            painter.setPen(QPen(self.COLOR_VINCULO, 3))
            painter.drawLine(QPointF(x_left, y_tierra), QPointF(x_right, y_tierra))

            # Hatching
            painter.setPen(QPen(self.COLOR_VINCULO, 2))
            n_rayas = 7
            espacio = (x_right - x_left) / (n_rayas - 1)
            longitud_raya = 10

            for i in range(n_rayas):
                x = x_left + i * espacio
                painter.drawLine(
                    QPointF(x, y_tierra),
                    QPointF(x - 5, y_tierra + longitud_raya)
                )

        elif isinstance(vinculo, Guia):
            # Guía: Dos líneas paralelas con pequeños rodillos
            # (Permite desplazamiento en una dirección, restringe en otra)
            espacio_guia = 12
            longitud_guia = size * 1.5

            # Determinar dirección de la guía según GDL restringidos
            gdl_rest = vinculo.gdl_restringidos()

            if 'Ux' in gdl_rest and 'Uy' not in gdl_rest:
                # Guía vertical (permite desplazamiento vertical)
                painter.drawLine(
                    pos + QPointF(-espacio_guia/2, -longitud_guia/2),
                    pos + QPointF(-espacio_guia/2, longitud_guia/2)
                )
                painter.drawLine(
                    pos + QPointF(espacio_guia/2, -longitud_guia/2),
                    pos + QPointF(espacio_guia/2, longitud_guia/2)
                )

                # Pequeños círculos (rodillos)
                for y_offset in [-longitud_guia/4, longitud_guia/4]:
                    painter.drawEllipse(
                        pos + QPointF(-espacio_guia/2, y_offset),
                        3, 3
                    )
                    painter.drawEllipse(
                        pos + QPointF(espacio_guia/2, y_offset),
                        3, 3
                    )
            else:
                # Guía horizontal (permite desplazamiento horizontal)
                painter.drawLine(
                    pos + QPointF(-longitud_guia/2, -espacio_guia/2),
                    pos + QPointF(longitud_guia/2, -espacio_guia/2)
                )
                painter.drawLine(
                    pos + QPointF(-longitud_guia/2, espacio_guia/2),
                    pos + QPointF(longitud_guia/2, espacio_guia/2)
                )

                # Pequeños círculos (rodillos)
                for x_offset in [-longitud_guia/4, longitud_guia/4]:
                    painter.drawEllipse(
                        pos + QPointF(x_offset, -espacio_guia/2),
                        3, 3
                    )
                    painter.drawEllipse(
                        pos + QPointF(x_offset, espacio_guia/2),
                        3, 3
                    )

    def _draw_carga(self, painter: QPainter, carga):
        """Dibuja una carga con visualización mejorada."""
        from src.domain.entities.carga import (
            CargaPuntualNudo,
            CargaPuntualBarra,
            CargaDistribuida,
        )

        if isinstance(carga, CargaPuntualNudo):
            self._draw_carga_puntual_nudo(painter, carga)
        elif isinstance(carga, CargaPuntualBarra):
            self._draw_carga_puntual_barra(painter, carga)
        elif isinstance(carga, CargaDistribuida):
            self._draw_carga_distribuida(painter, carga)

    def _draw_carga_puntual_nudo(self, painter: QPainter, carga):
        """Dibuja una carga puntual en nudo con etiquetas."""
        pos = self._world_to_scene(carga.nudo.x, carga.nudo.y)

        # Configurar color y grosor más visible
        painter.setPen(QPen(self.COLOR_CARGA, 3))

        # Dibujar flecha para Fy (vertical)
        # Convencion de _draw_arrow: 0°=derecha, 90°=abajo, -90°=arriba
        # Fy > 0 → fuerza hacia abajo (Y+ abajo en TERNA) → 90° en pantalla
        if abs(carga.Fy) > 0.01:
            angulo = 90 if carga.Fy > 0 else -90   # 90°=abajo, -90°=arriba
            longitud = 40 + min(abs(carga.Fy) * 2, 30)
            self._draw_arrow(painter, pos, angulo, longitud)

            # Etiqueta: arriba y a la derecha para flecha hacia abajo, y viceversa
            offset_x = 15
            offset_y = -25 if carga.Fy > 0 else 25
            self._draw_load_label(painter, pos, offset_x, offset_y, f"Fy={carga.Fy:.1f}kN")

        # Dibujar flecha para Fx (horizontal)
        # Fx > 0 → fuerza hacia la derecha → 0° en pantalla
        if abs(carga.Fx) > 0.01:
            angulo = 0 if carga.Fx > 0 else 180    # 0°=derecha, 180°=izquierda
            longitud = 40 + min(abs(carga.Fx) * 2, 30)
            self._draw_arrow(painter, pos, angulo, longitud)

            # Etiqueta: a la izquierda del tronco para flecha hacia derecha
            offset_x = -65 if carga.Fx > 0 else 50
            offset_y = -10
            self._draw_load_label(painter, pos, offset_x, offset_y, f"Fx={carga.Fx:.1f}kN")

        # Dibujar momento (Mz)
        if abs(carga.Mz) > 0.01:
            painter.setPen(QPen(self.COLOR_MOMENTO, 3))
            radio = 20
            sentido = carga.Mz > 0  # True = antihorario, False = horario
            self._draw_moment(painter, pos, radio, sentido)

            # Etiqueta del momento
            offset_x = 30
            offset_y = -30
            self._draw_load_label(painter, pos, offset_x, offset_y, f"Mz={carga.Mz:.1f}kNm", self.COLOR_MOMENTO)

    def _draw_carga_puntual_barra(self, painter: QPainter, carga):
        """Dibuja una carga puntual sobre barra con etiquetas."""
        import math

        barra = carga.barra
        t = carga.a / barra.L
        x_world = barra.nudo_i.x + t * (barra.nudo_j.x - barra.nudo_i.x)
        y_world = barra.nudo_i.y + t * (barra.nudo_j.y - barra.nudo_i.y)
        pos = self._world_to_scene(x_world, y_world)

        # Configurar color y grosor
        painter.setPen(QPen(self.COLOR_CARGA, 3))

        # Calcular ángulo en coordenadas globales
        # El ángulo de la carga está en coordenadas locales de la barra
        # Sistema local: 0° = dirección de la barra, -90° = perpendicular hacia derecha de la barra
        angulo_barra_rad = math.atan2(
            barra.nudo_j.y - barra.nudo_i.y,
            barra.nudo_j.x - barra.nudo_i.x
        )
        angulo_barra_grados = math.degrees(angulo_barra_rad)

        # Convertir de coordenadas locales a globales
        # En Qt: 0° = derecha, 90° = abajo, 180° = izquierda, -90° = arriba
        # El ángulo local se mide respecto al eje de la barra
        angulo_global_qt = angulo_barra_grados + carga.angulo

        # Longitud escalada según magnitud
        longitud = 40 + min(abs(carga.P) * 2, 30)

        # Dibujar flecha
        self._draw_arrow(painter, pos, angulo_global_qt, longitud)

        # Etiqueta con magnitud y posición
        offset_perpendicular = 35
        ang_perp = math.radians(angulo_global_qt + 90)  # Perpendicular a la flecha
        offset_x = offset_perpendicular * math.cos(ang_perp)
        offset_y = offset_perpendicular * math.sin(ang_perp)

        label = f"P={carga.P:.1f}kN @ a={carga.a:.2f}m"
        self._draw_load_label(painter, pos, offset_x, offset_y, label)

    def _draw_carga_distribuida(self, painter: QPainter, carga):
        """Dibuja una carga distribuida con visualización de trapecio."""
        import math

        barra = carga.barra
        painter.setPen(QPen(self.COLOR_CARGA, 2))

        # Calcular puntos de inicio y fin de la carga
        t1 = carga.x1 / barra.L
        t2 = (carga.x2 or barra.L) / barra.L

        x1_world = barra.nudo_i.x + t1 * (barra.nudo_j.x - barra.nudo_i.x)
        y1_world = barra.nudo_i.y + t1 * (barra.nudo_j.y - barra.nudo_i.y)
        x2_world = barra.nudo_i.x + t2 * (barra.nudo_j.x - barra.nudo_i.x)
        y2_world = barra.nudo_i.y + t2 * (barra.nudo_j.y - barra.nudo_i.y)

        # Ángulo de la barra
        angulo_barra = math.atan2(
            barra.nudo_j.y - barra.nudo_i.y,
            barra.nudo_j.x - barra.nudo_i.x
        )

        # Ángulo perpendicular para la dirección de la carga
        angulo_carga_rad = math.radians(carga.angulo)
        angulo_global = angulo_barra + angulo_carga_rad

        # Escala para visualización
        escala = 3.0  # píxeles por kN/m

        # Puntos del trapecio
        p1_base = self._world_to_scene(x1_world, y1_world)
        p2_base = self._world_to_scene(x2_world, y2_world)

        # Puntos del lado opuesto a la barra (donde nace la carga).
        # El trapecio se dibuja en la dirección CONTRARIA a la carga para que
        # quede "detrás" de las flechas: si la carga apunta hacia abajo, el
        # trapecio queda encima de la barra.
        offset1 = carga.q1 * escala
        offset2 = carga.q2 * escala

        p1_top = p1_base + QPointF(
            -offset1 * math.cos(angulo_global),
            -offset1 * math.sin(angulo_global)
        )
        p2_top = p2_base + QPointF(
            -offset2 * math.cos(angulo_global),
            -offset2 * math.sin(angulo_global)
        )

        # Dibujar trapecio relleno semi-transparente
        from PyQt6.QtGui import QPolygonF
        trapecio = QPolygonF([p1_base, p1_top, p2_top, p2_base])
        painter.setBrush(QBrush(QColor(200, 0, 0, 80)))  # Rojo semi-transparente
        painter.drawPolygon(trapecio)

        # Dibujar línea superior
        painter.setPen(QPen(self.COLOR_CARGA, 2))
        painter.drawLine(p1_top, p2_top)

        # Dibujar flechas verticales cada cierto intervalo
        n_flechas = 5
        for i in range(n_flechas + 1):
            t_flecha = i / n_flechas
            x_flecha = x1_world + t_flecha * (x2_world - x1_world)
            y_flecha = y1_world + t_flecha * (y2_world - y1_world)
            pos_flecha = self._world_to_scene(x_flecha, y_flecha)

            # Interpolar intensidad
            q_local = carga.q1 + t_flecha * (carga.q2 - carga.q1)
            longitud_flecha = q_local * escala

            if longitud_flecha > 2:  # Solo dibujar si es significativa
                # La flecha parte del borde del trapecio (lado opuesto a la carga)
                # y apunta HACIA la barra (en la dirección de angulo_global).
                start_flecha = pos_flecha + QPointF(
                    -longitud_flecha * math.cos(angulo_global),
                    -longitud_flecha * math.sin(angulo_global)
                )
                painter.drawLine(start_flecha, pos_flecha)

                # Punta de flecha en la barra, apuntando en dirección de la carga
                self._draw_small_arrow_head(painter, pos_flecha, angulo_global)

        # Etiqueta central
        x_centro = (x1_world + x2_world) / 2
        y_centro = (y1_world + y2_world) / 2
        pos_centro = self._world_to_scene(x_centro, y_centro)

        # Offset perpendicular: la etiqueta va en el mismo lado que el trapecio
        # (opuesto a la dirección de la carga, es decir, "sobre" la barra)
        offset_label = (carga.q1 + carga.q2) / 2 * escala + 20
        offset_x = -offset_label * math.cos(angulo_global)
        offset_y = -offset_label * math.sin(angulo_global)

        if carga.es_uniforme:
            label = f"q={carga.q1:.1f} kN/m"
        else:
            label = f"q₁={carga.q1:.1f}, q₂={carga.q2:.1f} kN/m"

        self._draw_load_label(painter, pos_centro, offset_x, offset_y, label)

    def _draw_load_label(self, painter: QPainter, pos: QPointF, offset_x: float,
                         offset_y: float, text: str, color=None):
        """Dibuja una etiqueta de carga con fondo."""
        if color is None:
            color = self.COLOR_CARGA

        painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))

        # Calcular tamaño del texto
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        text_height = metrics.height()

        # Posición de la etiqueta
        label_pos = pos + QPointF(offset_x, offset_y)

        # Dibujar fondo semi-transparente
        padding = 3
        rect = QRectF(
            label_pos.x() - padding,
            label_pos.y() - text_height + padding,
            text_width + 2 * padding,
            text_height
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
        painter.drawRect(rect)

        # Dibujar texto
        painter.setPen(QPen(color))
        painter.drawText(label_pos, text)

    def _draw_moment(self, painter: QPainter, pos: QPointF, radio: float, antihorario: bool):
        """Dibuja un símbolo de momento (arco circular con flecha)."""
        import math

        # Dibujar arco circular
        rect = QRectF(pos.x() - radio, pos.y() - radio, 2 * radio, 2 * radio)

        # Ángulo de inicio y span según sentido
        start_angle = 45 * 16  # QT usa 1/16 de grado
        span_angle = 270 * 16 if antihorario else -270 * 16

        painter.drawArc(rect, start_angle, span_angle)

        # Dibujar punta de flecha en el extremo
        if antihorario:
            tip_angle = math.radians(45 + 270)  # Extremo del arco
        else:
            tip_angle = math.radians(45 - 270)

        tip_pos = pos + QPointF(radio * math.cos(tip_angle), radio * math.sin(tip_angle))

        # Dirección de la punta
        tangent_angle = tip_angle + (math.pi/2 if antihorario else -math.pi/2)

        head_size = 8
        h1 = tip_pos + QPointF(
            head_size * math.cos(tangent_angle + math.radians(150)),
            head_size * math.sin(tangent_angle + math.radians(150))
        )
        h2 = tip_pos + QPointF(
            head_size * math.cos(tangent_angle - math.radians(150)),
            head_size * math.sin(tangent_angle - math.radians(150))
        )

        painter.drawLine(tip_pos, h1)
        painter.drawLine(tip_pos, h2)

    def _draw_small_arrow_head(self, painter: QPainter, pos: QPointF, angle_rad: float):
        """Dibuja una pequeña punta de flecha."""
        import math
        head_size = 5
        angle1 = angle_rad + math.radians(150)
        angle2 = angle_rad - math.radians(150)
        h1 = pos + QPointF(head_size * math.cos(angle1), head_size * math.sin(angle1))
        h2 = pos + QPointF(head_size * math.cos(angle2), head_size * math.sin(angle2))
        painter.drawLine(pos, h1)
        painter.drawLine(pos, h2)

    def _draw_arrow(self, painter: QPainter, pos: QPointF, angle: float, length: float):
        """
        Dibuja una flecha HACIA el punto de aplicación de la carga.

        Convención visual:
        - Carga hacia abajo (+90°): flecha por ENCIMA de la barra apuntando hacia abajo
        - Carga hacia arriba (-90°): flecha por DEBAJO de la barra apuntando hacia arriba

        Args:
            pos: Punto donde se aplica la carga (sobre la barra)
            angle: Ángulo de la carga (0° = derecha, 90° = abajo, 180° = izquierda, -90° = arriba)
            length: Longitud de la flecha en píxeles
        """
        import math
        rad = math.radians(angle)

        # La flecha debe dibujarse HACIA pos (no desde pos)
        # Invertimos la dirección: si la carga es hacia abajo (90°),
        # el origen de la flecha está arriba (-90°)
        rad_invertido = rad + math.pi  # +180° para invertir dirección

        # Punto de inicio de la flecha (origen, lejos del punto de aplicación)
        start = pos + QPointF(length * math.cos(rad_invertido), length * math.sin(rad_invertido))

        # Línea principal (cuerpo de la flecha) - desde start HACIA pos
        painter.drawLine(start, pos)

        # Cabeza de la flecha (triángulo en pos, apuntando en dirección de la carga)
        head_size = 8
        # Ángulos para las "aletas" de la punta
        angle1 = rad + math.radians(150)  # +150° desde la dirección de la carga
        angle2 = rad - math.radians(150)  # -150° desde la dirección de la carga
        h1 = pos + QPointF(head_size * math.cos(angle1), head_size * math.sin(angle1))
        h2 = pos + QPointF(head_size * math.cos(angle2), head_size * math.sin(angle2))

        # Dibujar las dos líneas de la punta desde pos
        painter.drawLine(pos, h1)
        painter.drawLine(pos, h2)

    def set_escala_diagramas(self, escala: float | None) -> None:
        """
        Establece la escala de los diagramas de esfuerzos.

        Args:
            escala: Factor de escala (metros por unidad de esfuerzo).
                    None = ajuste automático según el máximo de la estructura.
        """
        self._escala_diagramas = escala
        self.viewport().update()

    def _calcular_escala_auto(self) -> float:
        """
        Calcula una escala automática para que el diagrama más grande
        ocupe aproximadamente un 20 % de la longitud media de las barras.
        """
        if not self._resultado or not self.modelo.barras:
            return 0.1

        valor_max = 1e-10  # Evitar división por cero
        for barra in self.modelo.barras:
            diagrama = self._resultado.diagramas_finales.get(barra.id)
            if diagrama is None:
                continue
            n_pts = 11
            for k in range(n_pts):
                x = k * barra.L / (n_pts - 1)
                valor_max = max(valor_max, abs(diagrama.M(x)), abs(diagrama.V(x)), abs(diagrama.N(x)))

        L_media = sum(b.L for b in self.modelo.barras) / len(self.modelo.barras)
        escala = 0.2 * L_media / valor_max
        return escala

    def _draw_diagrama_componente(
        self,
        painter: QPainter,
        barra,
        diagrama,
        get_valor,  # callable(x) -> float
        escala: float,
        color: QColor,
    ):
        """
        Dibuja un diagrama de esfuerzos (M, V o N) sobre una barra.

        Desplaza cada punto perpendicularmente a la barra según el valor del esfuerzo.
        Llena el área entre la línea de esfuerzo y la barra con color semitransparente.
        """
        import math
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QPolygonF

        n_puntos = 21
        pts_offset: list[QPointF] = []
        pts_barra: list[QPointF] = []

        ang = barra.angulo + math.pi / 2  # Dirección perpendicular

        for k in range(n_puntos):
            x_local = k * barra.L / (n_puntos - 1)
            valor = get_valor(x_local)

            t = x_local / barra.L
            x_w = barra.nudo_i.x + t * (barra.nudo_j.x - barra.nudo_i.x)
            y_w = barra.nudo_i.y + t * (barra.nudo_j.y - barra.nudo_i.y)

            x_off = valor * escala * math.cos(ang)
            y_off = valor * escala * math.sin(ang)

            pts_offset.append(self._world_to_scene(x_w + x_off, y_w + y_off))
            pts_barra.append(self._world_to_scene(x_w, y_w))

        # Área rellena semitransparente
        color_fill = QColor(color)
        color_fill.setAlpha(40)
        polygon_pts = pts_offset + list(reversed(pts_barra))
        polygon = QPolygonF(polygon_pts)
        painter.setBrush(QBrush(color_fill))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(polygon)

        # Línea del diagrama
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 1.5))
        for k in range(len(pts_offset) - 1):
            painter.drawLine(pts_offset[k], pts_offset[k + 1])

        # Línea de referencia (eje de la barra) en gris punteado
        painter.setPen(QPen(QColor(150, 150, 150), 0.5, Qt.PenStyle.DashLine))
        for k in range(len(pts_barra) - 1):
            painter.drawLine(pts_barra[k], pts_barra[k + 1])

    def _draw_diagramas(self, painter: QPainter):
        """Dibuja los diagramas de esfuerzos N, V y M sobre cada barra."""
        if not self._resultado:
            return

        # Determinar escala
        escala = self._escala_diagramas if self._escala_diagramas is not None \
            else self._calcular_escala_auto()

        COLOR_N = QColor(0, 100, 200)      # Azul para Axil
        COLOR_V = QColor(0, 160, 80)       # Verde para Cortante
        COLOR_M = QColor(200, 0, 200)      # Magenta para Momento

        for barra in self.modelo.barras:
            diagrama = self._resultado.diagramas_finales.get(barra.id)
            if diagrama is None:
                continue

            if self._show_diagrama_N:
                self._draw_diagrama_componente(
                    painter, barra, diagrama,
                    lambda x, d=diagrama: d.N(x),
                    escala, COLOR_N
                )
            if self._show_diagrama_V:
                self._draw_diagrama_componente(
                    painter, barra, diagrama,
                    lambda x, d=diagrama: d.V(x),
                    escala, COLOR_V
                )
            if self._show_diagrama_M:
                self._draw_diagrama_componente(
                    painter, barra, diagrama,
                    lambda x, d=diagrama: d.M(x),
                    escala, COLOR_M
                )

    def _draw_temp_bar(self, painter: QPainter):
        """Dibuja la barra temporal durante la creación."""
        if self._temp_bar_start is None:
            return

        p1 = self._world_to_scene(self._temp_bar_start.x, self._temp_bar_start.y)

        # Usar la posición con snap
        x2, y2 = self._cursor_snapped_pos
        p2 = self._world_to_scene(x2, y2)

        painter.setPen(QPen(self.COLOR_PREVIEW.darker(110), 2, Qt.PenStyle.DashLine))
        painter.drawLine(p1, p2)

        # Mostrar longitud de la barra temporal
        import math
        dx = x2 - self._temp_bar_start.x
        dy = y2 - self._temp_bar_start.y
        length = math.hypot(dx, dy)

        mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QPen(QColor(50, 50, 150)))
        painter.drawText(mid + QPointF(5, -5), f"L={length:.2f} m")

    # =========================================================================
    # EVENTOS
    # =========================================================================

    def wheelEvent(self, event: QWheelEvent):
        """Maneja el zoom con la rueda del mouse."""
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
            self._zoom_factor *= factor
        else:
            self.scale(1/factor, 1/factor)
            self._zoom_factor /= factor

    def mousePressEvent(self, event: QMouseEvent):
        """Maneja el clic del mouse."""
        scene_pos = self.mapToScene(event.pos())
        world_x, world_y = self._scene_to_world(scene_pos)
        snap_x, snap_y = self._snap_to_grid(world_x, world_y)

        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == "create_node":
                self._create_node_at(snap_x, snap_y)
            elif self._mode == "create_bar":
                self._handle_bar_creation(snap_x, snap_y)
            elif self._mode == "select":
                self._handle_selection(world_x, world_y)

        elif event.button() == Qt.MouseButton.RightButton:
            # Menú contextual
            if self._mode == "select":
                self._show_context_menu(event.pos(), world_x, world_y)

        elif event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Maneja la liberación del mouse."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Maneja el movimiento del mouse."""
        scene_pos = self.mapToScene(event.pos())
        world_x, world_y = self._scene_to_world(scene_pos)

        # Guardar posición actual
        self._cursor_world_pos = (world_x, world_y)
        self._cursor_snapped_pos = self._snap_to_grid(world_x, world_y)

        # Emitir señal de coordenadas
        if self._snap_enabled:
            self.coordinates_changed.emit(*self._cursor_snapped_pos)
        else:
            self.coordinates_changed.emit(world_x, world_y)

        # Actualizar coordenadas en ventana principal (búsqueda hacia arriba)
        parent = self.parent()
        while parent:
            if hasattr(parent, 'label_coordenadas'):
                sx, sy = self._cursor_snapped_pos if self._snap_enabled else (world_x, world_y)
                snap_indicator = " [SNAP]" if self._snap_enabled else ""
                parent.label_coordenadas.setText(f"X: {sx:.2f}  Y: {sy:.2f}{snap_indicator}")
                break
            parent = parent.parent()

        # Actualizar visualización en modos de creación
        if self._mode in ("create_node", "create_bar"):
            self.viewport().update()

        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """Maneja teclas."""
        if event.key() == Qt.Key.Key_Escape:
            self._temp_bar_start = None
            self._selected_nodes.clear()
            self._selected_bars.clear()
            self.selection_changed.emit([])
            self.viewport().update()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_G:
            # Toggle snap to grid
            self._snap_enabled = not self._snap_enabled
            self.viewport().update()

        super().keyPressEvent(event)

    # =========================================================================
    # ACCIONES
    # =========================================================================

    def _create_node_at(self, x: float, y: float):
        """Crea un nudo en la posición especificada."""
        # Verificar si ya existe un nudo cerca
        for nudo in self.modelo.nudos:
            if abs(nudo.x - x) < 0.01 and abs(nudo.y - y) < 0.01:
                return  # Ya existe

        self._guardar_snapshot_undo()  # Antes de mutar
        self.modelo.agregar_nudo(x, y)
        self.model_changed.emit()
        self.viewport().update()

    def create_node_parametric(self, x: float, y: float) -> Optional[Nudo]:
        """
        Crea un nudo con coordenadas exactas (entrada paramétrica).

        Args:
            x: Coordenada X en metros
            y: Coordenada Y en metros

        Returns:
            El nudo creado, o None si ya existía
        """
        # Verificar si ya existe un nudo cerca
        for nudo in self.modelo.nudos:
            if abs(nudo.x - x) < 0.01 and abs(nudo.y - y) < 0.01:
                return nudo  # Retornar el existente

        self._guardar_snapshot_undo()  # Antes de mutar
        nudo = self.modelo.agregar_nudo(x, y)
        self.model_changed.emit()
        self.viewport().update()
        return nudo

    def create_bar_parametric(self, nudo_i_id: int, nudo_j_id: int) -> Optional[Barra]:
        """
        Crea una barra entre dos nudos existentes (entrada paramétrica).

        Args:
            nudo_i_id: ID del nudo inicial
            nudo_j_id: ID del nudo final

        Returns:
            La barra creada, o None si falló
        """
        nudo_i = self.modelo.obtener_nudo(nudo_i_id)
        nudo_j = self.modelo.obtener_nudo(nudo_j_id)

        if nudo_i is None or nudo_j is None:
            return None

        if nudo_i_id == nudo_j_id:
            return None

        from src.data.materials_db import MATERIALES
        from src.data.sections_db import SECCIONES_IPE

        material = MATERIALES.get("Acero A-36")
        seccion = SECCIONES_IPE.get("IPE 220")

        if material and seccion:
            try:
                self._guardar_snapshot_undo()  # Antes de mutar
                barra = self.modelo.agregar_barra(nudo_i, nudo_j, material, seccion)
                self.model_changed.emit()
                self.viewport().update()
                return barra
            except ValueError:
                return None
        return None

    def _handle_bar_creation(self, x: float, y: float):
        """Maneja la creación de barras."""
        # Buscar nudo cercano
        nudo_cercano = None
        for nudo in self.modelo.nudos:
            if abs(nudo.x - x) < 0.2 and abs(nudo.y - y) < 0.2:
                nudo_cercano = nudo
                break

        if nudo_cercano is None:
            # Crear nuevo nudo
            nudo_cercano = self.modelo.agregar_nudo(x, y)

        if self._temp_bar_start is None:
            # Primer clic: guardar nudo de inicio
            self._temp_bar_start = nudo_cercano
        else:
            # Segundo clic: crear barra
            if nudo_cercano != self._temp_bar_start:
                from src.data.materials_db import MATERIALES
                from src.data.sections_db import SECCIONES_IPE

                material = MATERIALES.get("Acero A-36")
                seccion = SECCIONES_IPE.get("IPE 220")

                if material and seccion:
                    try:
                        self._guardar_snapshot_undo()  # Antes de mutar
                        self.modelo.agregar_barra(
                            self._temp_bar_start,
                            nudo_cercano,
                            material,
                            seccion
                        )
                        self.model_changed.emit()
                    except ValueError:
                        pass  # Barra ya existe

            self._temp_bar_start = None

        self.viewport().update()

    def _handle_selection(self, x: float, y: float):
        """Maneja la selección de elementos."""
        # Buscar nudo cercano
        for nudo in self.modelo.nudos:
            if abs(nudo.x - x) < 0.3 and abs(nudo.y - y) < 0.3:
                if nudo.id in self._selected_nodes:
                    self._selected_nodes.remove(nudo.id)
                else:
                    self._selected_nodes = [nudo.id]
                    self._selected_bars.clear()

                self.selection_changed.emit(
                    [("nudo", nudo.id) for nudo in self.modelo.nudos if nudo.id in self._selected_nodes]
                )
                self.viewport().update()
                return

        # Buscar barra cercana
        for barra in self.modelo.barras:
            if self._point_near_line(x, y, barra):
                if barra.id in self._selected_bars:
                    self._selected_bars.remove(barra.id)
                else:
                    self._selected_bars = [barra.id]
                    self._selected_nodes.clear()

                self.selection_changed.emit(
                    [("barra", barra.id) for barra in self.modelo.barras if barra.id in self._selected_bars]
                )
                self.viewport().update()
                return

        # Clic en vacío: deseleccionar todo
        self._selected_nodes.clear()
        self._selected_bars.clear()
        self.selection_changed.emit([])
        self.viewport().update()

    def _point_near_line(self, x: float, y: float, barra: Barra, tolerance: float = 0.3) -> bool:
        """Verifica si un punto está cerca de una barra."""
        x1, y1 = barra.nudo_i.x, barra.nudo_i.y
        x2, y2 = barra.nudo_j.x, barra.nudo_j.y

        # Distancia punto-línea
        import math
        dx = x2 - x1
        dy = y2 - y1
        L_sq = dx*dx + dy*dy

        if L_sq == 0:
            return math.hypot(x - x1, y - y1) < tolerance

        t = max(0, min(1, ((x - x1)*dx + (y - y1)*dy) / L_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return math.hypot(x - proj_x, y - proj_y) < tolerance

    def delete_selected(self):
        """Elimina los elementos seleccionados."""
        if not self._selected_bars and not self._selected_nodes:
            return

        self._guardar_snapshot_undo()  # Antes de mutar

        for barra_id in self._selected_bars:
            self.modelo.remover_barra(barra_id)

        for nudo_id in self._selected_nodes:
            self.modelo.remover_nudo(nudo_id)

        self._selected_nodes.clear()
        self._selected_bars.clear()
        self.selection_changed.emit([])
        self.model_changed.emit()
        self.viewport().update()

    def _show_context_menu(self, pos_screen, world_x: float, world_y: float):
        """Muestra menú contextual con opciones."""
        from PyQt6.QtWidgets import QMenu
        from src.domain.entities.carga import CargaPuntualBarra, CargaDistribuida

        menu = QMenu(self)

        # Buscar si hay una barra seleccionada
        barra_seleccionada = None
        if len(self._selected_bars) == 1:
            barra_id = self._selected_bars[0]
            barra_seleccionada = self.modelo.obtener_barra(barra_id)

        # Si hay barra seleccionada, buscar cargas en ella
        if barra_seleccionada:
            cargas_en_barra = [
                c for c in self.modelo.cargas
                if isinstance(c, (CargaPuntualBarra, CargaDistribuida))
                and c.barra.id == barra_seleccionada.id
            ]

            if cargas_en_barra:
                submenu_cargas = menu.addMenu(f"Eliminar carga de Barra {barra_seleccionada.id}")

                for i, carga in enumerate(cargas_en_barra):
                    if isinstance(carga, CargaPuntualBarra):
                        texto = f"Puntual: P={carga.P:.1f}kN @ a={carga.a:.2f}m"
                    elif isinstance(carga, CargaDistribuida):
                        texto = f"Distribuida: q₁={carga.q1:.1f}, q₂={carga.q2:.1f} kN/m"
                    else:
                        texto = f"Carga {i+1}"

                    action = submenu_cargas.addAction(texto)
                    action.triggered.connect(lambda checked, c=carga: self._eliminar_carga(c))

                menu.addSeparator()

        # Opciones generales
        if self._selected_nodes or self._selected_bars:
            action_delete = menu.addAction("Eliminar selección (Del)")
            action_delete.triggered.connect(self.delete_selected)

        # Mostrar menú en la posición del cursor
        if not menu.isEmpty():
            menu.exec(self.mapToGlobal(pos_screen))

    def _eliminar_carga(self, carga):
        """Elimina una carga específica."""
        self._guardar_snapshot_undo()  # Antes de mutar
        self.modelo.remover_carga(carga)
        self.model_changed.emit()
        self.viewport().update()

    def zoom_in(self):
        """Acerca el zoom."""
        self.scale(1.2, 1.2)
        self._zoom_factor *= 1.2

    def zoom_out(self):
        """Aleja el zoom."""
        self.scale(1/1.2, 1/1.2)
        self._zoom_factor /= 1.2

    def zoom_fit(self):
        """Ajusta el zoom para ver toda la estructura."""
        if self.modelo.num_nudos == 0:
            return

        bbox = self.modelo.bounding_box
        x_min, y_min, x_max, y_max = bbox

        # Agregar margen
        margin = 2.0
        x_min -= margin
        y_min -= margin
        x_max += margin
        y_max += margin

        # Convertir a coordenadas de escena
        p1 = self._world_to_scene(x_min, y_max)
        p2 = self._world_to_scene(x_max, y_min)

        rect = QRectF(p1, p2)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
