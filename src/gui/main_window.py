"""
Ventana principal de la aplicación.
"""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QStatusBar,
    QMenuBar,
    QMenu,
    QMessageBox,
    QFileDialog,
    QDockWidget,
    QLabel,
    QScrollArea,
    QDialog,
    QPushButton,
    QSizePolicy,
    QComboBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont

from src.domain.model.modelo_estructural import ModeloEstructural
from src.domain.entities.vinculo import Empotramiento, ApoyoFijo, Rodillo
from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas, ResultadoAnalisis
from src.domain.analysis.motor_deformaciones import MotorMetodoDeformaciones
from src.gui.canvas.structure_canvas import StructureCanvas
from src.gui.widgets.properties_panel import PropertiesPanel
from src.gui.widgets.results_panel import ResultsPanel
from src.gui.dialogs import (
    CargaPuntualNudoDialog,
    CargaPuntualBarraDialog,
    CargaDistribuidaDialog,
    RedundantesDialog,
)
from src.gui.history import UndoRedoManager


class MainWindow(QMainWindow):
    """
    Ventana principal de la aplicación de análisis estructural.

    Componentes:
    - Menú superior con opciones de archivo, edición, análisis
    - Barra de herramientas con acciones rápidas
    - Canvas central para visualizar/editar la estructura
    - Panel lateral de propiedades
    - Panel inferior de resultados
    - Barra de estado
    """

    def __init__(self):
        super().__init__()

        # Modelo estructural actual
        self.modelo = ModeloEstructural("Nuevo proyecto")

        # Ruta del archivo actualmente abierto (None = sin guardar)
        self._ruta_archivo: str | None = None

        # Ultimo resultado de analisis (None = no resuelto)
        self._resultado: ResultadoAnalisis | None = None

        # Configurar ventana
        self._setup_window()
        self._setup_menus()

        # Gestor de Deshacer/Rehacer (debe crearse DESPUÉS de _setup_menus para
        # que self.action_deshacer y self.action_rehacer ya existan)
        self._undo_manager = UndoRedoManager(
            max_historial=50,
            puede_deshacer_changed=self.action_deshacer.setEnabled,
            puede_rehacer_changed=self.action_rehacer.setEnabled,
        )

        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_dock_widgets()
        self._setup_statusbar()

        # Estado inicial
        self._update_title()

    def _setup_window(self):
        """Configura propiedades básicas de la ventana."""
        self.setWindowTitle("Análisis Estructural - Método de las Fuerzas")
        self.setMinimumSize(1024, 768)
        self.resize(1400, 900)

    def _setup_menus(self):
        """Configura el menú principal."""
        menubar = self.menuBar()

        # ===== Menú Archivo =====
        menu_archivo = menubar.addMenu("&Archivo")

        action_nuevo = QAction("&Nuevo", self)
        action_nuevo.setShortcut(QKeySequence.StandardKey.New)
        action_nuevo.setStatusTip("Crear nuevo proyecto")
        action_nuevo.triggered.connect(self._on_nuevo)
        menu_archivo.addAction(action_nuevo)

        action_abrir = QAction("&Abrir...", self)
        action_abrir.setShortcut(QKeySequence.StandardKey.Open)
        action_abrir.setStatusTip("Abrir proyecto existente")
        action_abrir.triggered.connect(self._on_abrir)
        menu_archivo.addAction(action_abrir)

        action_guardar = QAction("&Guardar", self)
        action_guardar.setShortcut(QKeySequence.StandardKey.Save)
        action_guardar.setStatusTip("Guardar proyecto")
        action_guardar.triggered.connect(self._on_guardar)
        menu_archivo.addAction(action_guardar)

        action_guardar_como = QAction("Guardar &como...", self)
        action_guardar_como.setShortcut(QKeySequence.StandardKey.SaveAs)
        action_guardar_como.triggered.connect(self._on_guardar_como)
        menu_archivo.addAction(action_guardar_como)

        menu_archivo.addSeparator()

        action_exportar = QAction("&Exportar imagen (PNG)...", self)
        action_exportar.setStatusTip("Exportar vista del canvas como imagen PNG")
        action_exportar.triggered.connect(self._on_exportar)
        menu_archivo.addAction(action_exportar)

        action_exportar_pdf = QAction("Exportar informe (P&DF)...", self)
        action_exportar_pdf.setShortcut("Ctrl+Shift+E")
        action_exportar_pdf.setStatusTip("Exportar informe tecnico completo en PDF")
        action_exportar_pdf.triggered.connect(self._on_exportar_pdf)
        menu_archivo.addAction(action_exportar_pdf)

        menu_archivo.addSeparator()

        action_salir = QAction("&Salir", self)
        action_salir.setShortcut(QKeySequence.StandardKey.Quit)
        action_salir.triggered.connect(self.close)
        menu_archivo.addAction(action_salir)

        # ===== Menú Edición =====
        menu_edicion = menubar.addMenu("&Edición")

        self.action_deshacer = QAction("&Deshacer", self)
        self.action_deshacer.setShortcut(QKeySequence.StandardKey.Undo)
        self.action_deshacer.setEnabled(False)
        self.action_deshacer.triggered.connect(self._on_deshacer)
        menu_edicion.addAction(self.action_deshacer)

        self.action_rehacer = QAction("&Rehacer", self)
        self.action_rehacer.setShortcut(QKeySequence.StandardKey.Redo)
        self.action_rehacer.setEnabled(False)
        self.action_rehacer.triggered.connect(self._on_rehacer)
        menu_edicion.addAction(self.action_rehacer)

        menu_edicion.addSeparator()

        action_eliminar = QAction("&Eliminar selección", self)
        action_eliminar.setShortcut(QKeySequence.StandardKey.Delete)
        action_eliminar.triggered.connect(self._on_eliminar)
        menu_edicion.addAction(action_eliminar)

        # ===== Menú Ver =====
        menu_ver = menubar.addMenu("&Ver")

        action_zoom_in = QAction("Acercar", self)
        action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        action_zoom_in.triggered.connect(self._on_zoom_in)
        menu_ver.addAction(action_zoom_in)

        action_zoom_out = QAction("Alejar", self)
        action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        action_zoom_out.triggered.connect(self._on_zoom_out)
        menu_ver.addAction(action_zoom_out)

        action_zoom_fit = QAction("Ajustar a ventana", self)
        action_zoom_fit.setShortcut("Ctrl+0")
        action_zoom_fit.triggered.connect(self._on_zoom_fit)
        menu_ver.addAction(action_zoom_fit)

        menu_ver.addSeparator()

        self.action_mostrar_grilla = QAction("Mostrar grilla", self)
        self.action_mostrar_grilla.setCheckable(True)
        self.action_mostrar_grilla.setChecked(True)
        self.action_mostrar_grilla.triggered.connect(self._on_toggle_grilla)
        menu_ver.addAction(self.action_mostrar_grilla)

        # ===== Menú Análisis =====
        menu_analisis = menubar.addMenu("&Análisis")

        action_selec_redundantes = QAction("Seleccionar &redundantes...", self)
        action_selec_redundantes.setShortcut("F4")
        action_selec_redundantes.setStatusTip("Seleccionar redundantes manual o automáticamente")
        action_selec_redundantes.triggered.connect(self._on_seleccionar_redundantes)
        menu_analisis.addAction(action_selec_redundantes)

        menu_analisis.addSeparator()

        action_resolver = QAction("&Resolver estructura", self)
        action_resolver.setShortcut("F5")
        action_resolver.setStatusTip("Ejecutar análisis por Método de las Fuerzas")
        action_resolver.triggered.connect(self._on_resolver)
        menu_analisis.addAction(action_resolver)

        menu_analisis.addSeparator()

        action_ver_diagramas = QAction("Ver &diagramas", self)
        action_ver_diagramas.setShortcut("F6")
        action_ver_diagramas.triggered.connect(self._on_ver_diagramas)
        menu_analisis.addAction(action_ver_diagramas)

        # ===== Menú Ayuda =====
        menu_ayuda = menubar.addMenu("A&yuda")

        action_acerca = QAction("&Acerca de...", self)
        action_acerca.triggered.connect(self._on_acerca)
        menu_ayuda.addAction(action_acerca)

    def _toolbar_label(self, texto: str) -> QLabel:
        """Crea una etiqueta de sección para la toolbar."""
        lbl = QLabel(texto)
        lbl.setStyleSheet(
            "color: #555; font-size: 10px; font-weight: bold; "
            "padding: 0 4px; border-left: 1px solid #bbb; margin-left: 2px;"
        )
        return lbl

    def _setup_toolbar(self):
        """Configura la barra de herramientas con grupos visuales."""
        toolbar = QToolBar("Herramientas principales")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        # ── Geometría ────────────────────────────────────────────────────
        toolbar.addWidget(self._toolbar_label("Geometria"))

        self.action_seleccionar = QAction("Seleccionar", self)
        self.action_seleccionar.setCheckable(True)
        self.action_seleccionar.setChecked(True)
        self.action_seleccionar.setStatusTip("Modo seleccion (S)")
        self.action_seleccionar.setShortcut("S")
        toolbar.addAction(self.action_seleccionar)

        self.action_crear_nudo = QAction("Nudo", self)
        self.action_crear_nudo.setCheckable(True)
        self.action_crear_nudo.setStatusTip("Crear nudo haciendo clic en el canvas (N)")
        self.action_crear_nudo.setShortcut("N")
        toolbar.addAction(self.action_crear_nudo)

        self.action_crear_barra = QAction("Barra", self)
        self.action_crear_barra.setCheckable(True)
        self.action_crear_barra.setStatusTip("Crear barra arrastrando entre nudos (B)")
        self.action_crear_barra.setShortcut("B")
        toolbar.addAction(self.action_crear_barra)

        toolbar.addSeparator()

        # ── Vínculos ──────────────────────────────────────────────────────
        toolbar.addWidget(self._toolbar_label("Vinculos"))

        self.action_empotramiento = QAction("Empotr.", self)
        self.action_empotramiento.setStatusTip("Asignar empotramiento al nudo seleccionado (E)")
        self.action_empotramiento.setShortcut("E")
        self.action_empotramiento.triggered.connect(lambda: self._on_asignar_vinculo("empotramiento"))
        toolbar.addAction(self.action_empotramiento)

        self.action_apoyo_fijo = QAction("Ap. Fijo", self)
        self.action_apoyo_fijo.setStatusTip("Asignar apoyo fijo al nudo seleccionado (A)")
        self.action_apoyo_fijo.setShortcut("A")
        self.action_apoyo_fijo.triggered.connect(lambda: self._on_asignar_vinculo("apoyo_fijo"))
        toolbar.addAction(self.action_apoyo_fijo)

        self.action_rodillo = QAction("Rodillo", self)
        self.action_rodillo.setStatusTip("Asignar rodillo al nudo seleccionado (R)")
        self.action_rodillo.setShortcut("R")
        self.action_rodillo.triggered.connect(lambda: self._on_asignar_vinculo("rodillo"))
        toolbar.addAction(self.action_rodillo)

        toolbar.addSeparator()

        # ── Cargas ────────────────────────────────────────────────────────
        toolbar.addWidget(self._toolbar_label("Cargas"))

        self.action_carga_puntual = QAction("Puntual", self)
        self.action_carga_puntual.setStatusTip("Agregar carga puntual en nudo o barra (P)")
        self.action_carga_puntual.setShortcut("P")
        self.action_carga_puntual.triggered.connect(self._on_agregar_carga_puntual)
        toolbar.addAction(self.action_carga_puntual)

        self.action_carga_distribuida = QAction("Distribuida", self)
        self.action_carga_distribuida.setStatusTip("Agregar carga distribuida en barra (D)")
        self.action_carga_distribuida.setShortcut("D")
        self.action_carga_distribuida.triggered.connect(self._on_agregar_carga_distribuida)
        toolbar.addAction(self.action_carga_distribuida)

        toolbar.addSeparator()

        # ── Análisis ──────────────────────────────────────────────────────
        # Selector de método de análisis
        toolbar.addWidget(self._toolbar_label("Método"))
        self.combo_metodo = QComboBox()
        self.combo_metodo.addItem("Fuerzas (MF)", userData="MF")
        self.combo_metodo.addItem("Deformaciones (MD)", userData="MD")
        self.combo_metodo.setToolTip(
            "<b>Método de análisis</b><br>"
            "<b>Fuerzas (MF):</b> Método clásico de flexibilidad. "
            "Requiere selección de redundantes.<br>"
            "<b>Deformaciones (MD):</b> Método de rigidez (FEM). "
            "Resuelve directamente sin selección de redundantes."
        )
        self.combo_metodo.setFixedWidth(160)
        self.combo_metodo.setStyleSheet(
            "QComboBox { padding: 3px 6px; border: 1px solid #93c5fd; "
            "border-radius: 4px; background: white; }"
            "QComboBox:focus { border: 1px solid #2563eb; }"
        )
        toolbar.addWidget(self.combo_metodo)

        # Botón "Resolver" como QPushButton prominente
        self.btn_resolver = QPushButton("  Resolver (F5)  ")
        self.btn_resolver.setStatusTip("Ejecutar analisis por el Metodo de las Fuerzas")
        self.btn_resolver.setToolTip(
            "<b>Resolver estructura</b><br>"
            "Ejecuta el Metodo de las Fuerzas:<br>"
            "- Calcula grado de hiperestaticidad<br>"
            "- Selecciona redundantes<br>"
            "- Resuelve el SECE<br>"
            "- Genera diagramas M/V/N<br><br>"
            "<b>Atajo:</b> F5"
        )
        self.btn_resolver.setStyleSheet(
            "QPushButton {"
            "  background-color: #2563eb;"
            "  color: white;"
            "  border: none;"
            "  border-radius: 4px;"
            "  padding: 4px 12px;"
            "  font-weight: bold;"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:pressed { background-color: #1e40af; }"
            "QPushButton:disabled {"
            "  background-color: #93c5fd;"
            "  color: #dbeafe;"
            "}"
        )
        self.btn_resolver.setShortcut("F5")
        self.btn_resolver.clicked.connect(self._on_resolver)
        toolbar.addWidget(self.btn_resolver)

        # Acción fantasma para mantener compatibilidad con código que usa
        # self.action_resolver_toolbar (por si hay referencias externas)
        self.action_resolver_toolbar = QAction("Resolver", self)
        self.action_resolver_toolbar.triggered.connect(self._on_resolver)

        toolbar.addSeparator()

        # ── Diagramas ─────────────────────────────────────────────────────
        toolbar.addWidget(self._toolbar_label("Diagramas"))

        self.btn_diagrama_N = QPushButton("N")
        self.btn_diagrama_N.setCheckable(True)
        self.btn_diagrama_N.setChecked(False)
        self.btn_diagrama_N.setEnabled(False)
        self.btn_diagrama_N.setFixedWidth(30)
        self.btn_diagrama_N.setStatusTip("Mostrar/ocultar diagrama de Axiles")
        self.btn_diagrama_N.setToolTip("<b>Axil (N)</b><br>Azul — esfuerzo normal en cada barra")
        self.btn_diagrama_N.setStyleSheet(
            "QPushButton { border: 1px solid #93c5fd; border-radius: 3px; padding: 2px; font-weight: bold; }"
            "QPushButton:checked { background-color: #2563eb; color: white; border-color: #1d4ed8; }"
            "QPushButton:disabled { color: #aaa; border-color: #ddd; }"
        )
        self.btn_diagrama_N.clicked.connect(self._on_toggle_diagrama_N)
        toolbar.addWidget(self.btn_diagrama_N)

        self.btn_diagrama_V = QPushButton("V")
        self.btn_diagrama_V.setCheckable(True)
        self.btn_diagrama_V.setChecked(False)
        self.btn_diagrama_V.setEnabled(False)
        self.btn_diagrama_V.setFixedWidth(30)
        self.btn_diagrama_V.setStatusTip("Mostrar/ocultar diagrama de Cortantes")
        self.btn_diagrama_V.setToolTip("<b>Cortante (V)</b><br>Verde — esfuerzo cortante en cada barra")
        self.btn_diagrama_V.setStyleSheet(
            "QPushButton { border: 1px solid #6ee7b7; border-radius: 3px; padding: 2px; font-weight: bold; }"
            "QPushButton:checked { background-color: #059669; color: white; border-color: #047857; }"
            "QPushButton:disabled { color: #aaa; border-color: #ddd; }"
        )
        self.btn_diagrama_V.clicked.connect(self._on_toggle_diagrama_V)
        toolbar.addWidget(self.btn_diagrama_V)

        self.btn_diagrama_M = QPushButton("M")
        self.btn_diagrama_M.setCheckable(True)
        self.btn_diagrama_M.setChecked(False)
        self.btn_diagrama_M.setEnabled(False)
        self.btn_diagrama_M.setFixedWidth(30)
        self.btn_diagrama_M.setStatusTip("Mostrar/ocultar diagrama de Momentos Flectores")
        self.btn_diagrama_M.setToolTip("<b>Flector (M)</b><br>Magenta — momento flector en cada barra")
        self.btn_diagrama_M.setStyleSheet(
            "QPushButton { border: 1px solid #e9d5ff; border-radius: 3px; padding: 2px; font-weight: bold; }"
            "QPushButton:checked { background-color: #9333ea; color: white; border-color: #7e22ce; }"
            "QPushButton:disabled { color: #aaa; border-color: #ddd; }"
        )
        self.btn_diagrama_M.clicked.connect(self._on_toggle_diagrama_M)
        toolbar.addWidget(self.btn_diagrama_M)

        self.btn_deformada = QPushButton("Def.")
        self.btn_deformada.setEnabled(False)
        self.btn_deformada.setStatusTip("Ver deformada elastica (ventana externa)")
        self.btn_deformada.setToolTip("<b>Deformada elastica</b><br>Abre grafico matplotlib con la deformada exagerada")
        self.btn_deformada.setStyleSheet(
            "QPushButton { border: 1px solid #d1d5db; border-radius: 3px; padding: 2px 6px; }"
            "QPushButton:hover { background-color: #f3f4f6; }"
            "QPushButton:disabled { color: #aaa; border-color: #ddd; }"
        )
        self.btn_deformada.clicked.connect(self._on_ver_deformada)
        toolbar.addWidget(self.btn_deformada)

        # Conectar acciones de herramientas para modo exclusivo
        self._setup_tool_actions()

    def _setup_tool_actions(self):
        """Configura las acciones de herramientas como grupo exclusivo."""
        tool_actions = [
            self.action_seleccionar,
            self.action_crear_nudo,
            self.action_crear_barra,
        ]

        for action in tool_actions:
            action.triggered.connect(
                lambda checked, a=action: self._on_tool_changed(a, checked)
            )

    def _on_tool_changed(self, action, checked):
        """Maneja el cambio de herramienta activa."""
        if checked:
            # Desactivar otras herramientas
            for other in [self.action_seleccionar, self.action_crear_nudo, self.action_crear_barra]:
                if other != action:
                    other.setChecked(False)

            # Notificar al canvas y al panel de propiedades
            if hasattr(self, 'canvas'):
                if action == self.action_seleccionar:
                    self.canvas.set_mode("select")
                    if hasattr(self, 'properties_panel'):
                        self.properties_panel.set_tool_mode("select")
                elif action == self.action_crear_nudo:
                    self.canvas.set_mode("create_node")
                    if hasattr(self, 'properties_panel'):
                        self.properties_panel.set_tool_mode("create_node")
                elif action == self.action_crear_barra:
                    self.canvas.set_mode("create_bar")
                    if hasattr(self, 'properties_panel'):
                        self.properties_panel.set_tool_mode("create_bar")

    def _setup_central_widget(self):
        """Configura el widget central con el canvas."""
        self.canvas = StructureCanvas(self.modelo)
        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.model_changed.connect(self._on_model_changed)

        # Conectar callback de undo: el canvas llama a esto ANTES de cada mutación
        self.canvas.set_undo_callback(self._guardar_snapshot_undo)

        self.setCentralWidget(self.canvas)

    def _setup_dock_widgets(self):
        """Configura los paneles acoplables."""
        # Panel de propiedades (derecha) - con scroll
        self.properties_panel = PropertiesPanel()
        self.properties_panel.set_canvas(self.canvas)

        # Conectar cambio de vínculo desde el panel
        self.properties_panel.combo_vinculo.currentIndexChanged.connect(self._on_vinculo_combo_changed)
        self.properties_panel.btn_aplicar.clicked.connect(self._on_aplicar_propiedades)

        # Envolver en scroll area para paneles largos
        scroll_props = QScrollArea()
        scroll_props.setWidget(self.properties_panel)
        scroll_props.setWidgetResizable(True)
        scroll_props.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        dock_props = QDockWidget("Propiedades", self)
        dock_props.setWidget(scroll_props)
        dock_props.setMinimumWidth(300)
        dock_props.setMaximumWidth(400)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_props)

        # Panel de resultados (abajo)
        self.results_panel = ResultsPanel()
        dock_results = QDockWidget("Resultados", self)
        dock_results.setWidget(self.results_panel)
        dock_results.setMinimumHeight(180)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock_results)

    def _setup_statusbar(self):
        """Configura la barra de estado."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)

        # Labels permanentes (de derecha a izquierda — addPermanentWidget agrega a la derecha)
        self.label_coordenadas = QLabel("X: 0.00  Y: 0.00")
        self.label_coordenadas.setMinimumWidth(160)
        self.statusbar.addPermanentWidget(self.label_coordenadas)

        self.label_gh = QLabel("GH: 0")
        self.label_gh.setMinimumWidth(80)
        self.statusbar.addPermanentWidget(self.label_gh)

        self.label_elementos = QLabel("Nudos: 0  Barras: 0")
        self.label_elementos.setMinimumWidth(150)
        self.statusbar.addPermanentWidget(self.label_elementos)

        # Indicador de estado de análisis (el más importante — va a la izquierda)
        self.label_estado_analisis = QLabel("[ Sin resolver ]")
        self.label_estado_analisis.setMinimumWidth(200)
        self.label_estado_analisis.setStyleSheet(
            "color: #92400e; background-color: #fef3c7; "
            "border: 1px solid #d97706; border-radius: 3px; padding: 1px 6px;"
        )
        self.statusbar.addPermanentWidget(self.label_estado_analisis)

        self._update_statusbar()

    def _update_title(self):
        """Actualiza el título de la ventana."""
        modificado = "*" if self.modelo.esta_modificado else ""
        if self._ruta_archivo:
            from pathlib import Path
            nombre_archivo = Path(self._ruta_archivo).name
            self.setWindowTitle(f"{nombre_archivo}{modificado} - Análisis Estructural")
        else:
            self.setWindowTitle(f"{self.modelo.nombre}{modificado} - Análisis Estructural")

    def _update_statusbar(self):
        """Actualiza la información en la barra de estado."""
        gh = self.modelo.grado_hiperestaticidad
        self.label_gh.setText(f"GH: {gh}")

        # Color del label GH según estabilidad
        if gh < 0:
            self.label_gh.setStyleSheet("color: #dc2626; font-weight: bold;")
            self.label_gh.setToolTip(f"Estructura hipostatica (GH={gh}). Faltan {-gh} vinculos.")
        elif gh == 0:
            self.label_gh.setStyleSheet("color: #059669; font-weight: bold;")
            self.label_gh.setToolTip("Estructura isostatica")
        else:
            self.label_gh.setStyleSheet("color: #2563eb; font-weight: bold;")
            self.label_gh.setToolTip(f"Estructura hiperestatica de grado {gh}")

        self.label_elementos.setText(
            f"Nudos: {self.modelo.num_nudos}  Barras: {self.modelo.num_barras}"
        )

        # Habilitar/deshabilitar botón Resolver
        puede_resolver = (
            self.modelo.num_nudos >= 2
            and self.modelo.num_barras >= 1
            and gh >= 0
        )
        if hasattr(self, 'btn_resolver'):
            self.btn_resolver.setEnabled(puede_resolver)
            if not puede_resolver:
                if gh < 0:
                    self.btn_resolver.setToolTip(
                        "No se puede resolver: estructura hipostatica (GH < 0).\n"
                        f"Faltan {-gh} vinculos."
                    )
                else:
                    self.btn_resolver.setToolTip(
                        "No se puede resolver: el modelo necesita al menos\n"
                        "2 nudos y 1 barra."
                    )
            else:
                self.btn_resolver.setToolTip(
                    "<b>Resolver estructura</b><br>"
                    "Ejecuta el Metodo de las Fuerzas (F5)"
                )

    def _update_estado_analisis(self, exitoso: bool | None = None):
        """
        Actualiza el indicador visual de estado de analisis.

        Args:
            exitoso: True=resuelto, False=error, None=sin resolver/modelo modificado
        """
        if not hasattr(self, 'label_estado_analisis'):
            return

        if exitoso is None:
            self.label_estado_analisis.setText("[ Sin resolver ]")
            self.label_estado_analisis.setStyleSheet(
                "color: #92400e; background-color: #fef3c7; "
                "border: 1px solid #d97706; border-radius: 3px; padding: 1px 6px;"
            )
            self.label_estado_analisis.setToolTip(
                "Presione F5 para resolver la estructura"
            )
            # Deshabilitar y desmarcar botones de diagramas
            for btn in ('btn_diagrama_N', 'btn_diagrama_V', 'btn_diagrama_M', 'btn_deformada'):
                if hasattr(self, btn):
                    b = getattr(self, btn)
                    b.setEnabled(False)
                    if hasattr(b, 'setChecked'):
                        b.setChecked(False)
        elif exitoso:
            self.label_estado_analisis.setText("[ Resuelto OK ]")
            self.label_estado_analisis.setStyleSheet(
                "color: #065f46; background-color: #d1fae5; "
                "border: 1px solid #10b981; border-radius: 3px; padding: 1px 6px; "
                "font-weight: bold;"
            )
            self.label_estado_analisis.setToolTip(
                "Analisis completado. Resultados disponibles en el panel inferior."
            )
            # Habilitar botones de diagramas
            for btn in ('btn_diagrama_N', 'btn_diagrama_V', 'btn_diagrama_M', 'btn_deformada'):
                if hasattr(self, btn):
                    getattr(self, btn).setEnabled(True)
        else:
            self.label_estado_analisis.setText("[ Error en analisis ]")
            self.label_estado_analisis.setStyleSheet(
                "color: #7f1d1d; background-color: #fee2e2; "
                "border: 1px solid #ef4444; border-radius: 3px; padding: 1px 6px; "
                "font-weight: bold;"
            )
            self.label_estado_analisis.setToolTip(
                "El analisis fallo. Revise el modelo y vuelva a intentarlo."
            )
            # Deshabilitar y desmarcar botones de diagramas
            for btn in ('btn_diagrama_N', 'btn_diagrama_V', 'btn_diagrama_M', 'btn_deformada'):
                if hasattr(self, btn):
                    b = getattr(self, btn)
                    b.setEnabled(False)
                    if hasattr(b, 'setChecked'):
                        b.setChecked(False)

    # =========================================================================
    # Undo / Redo
    # =========================================================================

    def _guardar_snapshot_undo(self) -> None:
        """
        Guarda el estado actual del modelo en la pila de deshacer.

        Se llama:
        - Desde el canvas, a través del callback, ANTES de cada mutación
          que el canvas realiza directamente (crear nudo, crear barra, borrar,
          eliminar carga).
        - Explícitamente desde los métodos de MainWindow que mutan el modelo
          (asignar vínculo, agregar carga, aplicar propiedades).
        """
        try:
            self._undo_manager.guardar_estado(self.modelo)
        except Exception:
            pass  # No interrumpir la operación si el snapshot falla

    def _on_deshacer(self) -> None:
        """Deshace la última acción restaurando el modelo al estado previo."""
        modelo_restaurado = self._undo_manager.deshacer()
        if modelo_restaurado is None:
            return

        self.modelo = modelo_restaurado
        self._aplicar_modelo_restaurado()
        self.statusbar.showMessage("Accion deshecha", 2000)

    def _on_rehacer(self) -> None:
        """Rehace la última acción deshecha."""
        modelo_restaurado = self._undo_manager.rehacer()
        if modelo_restaurado is None:
            return

        self.modelo = modelo_restaurado
        self._aplicar_modelo_restaurado()
        self.statusbar.showMessage("Accion rehecha", 2000)

    def _aplicar_modelo_restaurado(self) -> None:
        """
        Actualiza todos los componentes de la UI para reflejar un modelo
        recien restaurado (tras deshacer o rehacer).
        """
        self.canvas.set_model(self.modelo)
        self.properties_panel.set_canvas(self.canvas)
        self.results_panel.limpiar()
        self._resultado = None
        self._update_title()
        self._update_statusbar()
        self._update_estado_analisis(exitoso=None)
        self._refresh_canvas()

    # =========================================================================
    # SLOTS - Vínculos
    # =========================================================================

    def _on_asignar_vinculo(self, tipo_vinculo: str):
        """Asigna un vínculo al nudo seleccionado."""
        # Obtener nudos seleccionados
        selected_nodes = self.canvas._selected_nodes
        if not selected_nodes:
            self.statusbar.showMessage("Seleccione un nudo primero", 3000)
            return

        self._guardar_snapshot_undo()

        for nudo_id in selected_nodes:
            nudo = self.modelo.obtener_nudo(nudo_id)
            if nudo:
                if tipo_vinculo == "empotramiento":
                    vinculo = Empotramiento(nudo_id)
                elif tipo_vinculo == "apoyo_fijo":
                    vinculo = ApoyoFijo(nudo_id)
                elif tipo_vinculo == "rodillo":
                    vinculo = Rodillo(nudo_id, direccion="Uy")
                else:
                    continue

                self.modelo.asignar_vinculo(nudo_id, vinculo)

        self._on_model_changed()
        self._refresh_canvas()
        self.statusbar.showMessage(f"Vínculo '{tipo_vinculo}' asignado", 3000)

    def _on_agregar_carga_puntual(self):
        """Muestra diálogo para agregar una carga puntual."""
        # Crear un submenú para elegir tipo de carga puntual
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        action_nudo = menu.addAction("Carga en Nudo")
        action_barra = menu.addAction("Carga en Barra")

        # Mostrar menú en posición del cursor
        from PyQt6.QtGui import QCursor
        action = menu.exec(QCursor.pos())

        if action == action_nudo:
            self._agregar_carga_puntual_nudo()
        elif action == action_barra:
            self._agregar_carga_puntual_barra()

    def _agregar_carga_puntual_nudo(self):
        """Abre diálogo para agregar carga puntual en nudo."""
        if self.modelo.num_nudos == 0:
            QMessageBox.information(
                self,
                "Sin nudos",
                "Primero debe crear nudos en la estructura."
            )
            return

        dialog = CargaPuntualNudoDialog(self.modelo, self)

        if dialog.exec():
            if dialog.carga_creada:
                self._guardar_snapshot_undo()
                self.modelo.agregar_carga(dialog.carga_creada)
                self._on_model_changed()
                self._refresh_canvas()
                self.statusbar.showMessage(
                    f"Carga puntual agregada en Nudo {dialog.carga_creada.nudo.id}",
                    3000
                )

    def _agregar_carga_puntual_barra(self):
        """Abre diálogo para agregar carga puntual en barra."""
        if self.modelo.num_barras == 0:
            QMessageBox.information(
                self,
                "Sin barras",
                "Primero debe crear barras en la estructura."
            )
            return

        dialog = CargaPuntualBarraDialog(self.modelo, self)

        if dialog.exec():
            if dialog.carga_creada:
                self._guardar_snapshot_undo()
                self.modelo.agregar_carga(dialog.carga_creada)
                self._on_model_changed()
                self._refresh_canvas()
                self.statusbar.showMessage(
                    f"Carga puntual agregada en Barra {dialog.carga_creada.barra.id}",
                    3000
                )

    def _on_agregar_carga_distribuida(self):
        """Abre diálogo para agregar carga distribuida."""
        if self.modelo.num_barras == 0:
            QMessageBox.information(
                self,
                "Sin barras",
                "Primero debe crear barras en la estructura."
            )
            return

        dialog = CargaDistribuidaDialog(self.modelo, self)

        if dialog.exec():
            if dialog.carga_creada:
                self._guardar_snapshot_undo()
                self.modelo.agregar_carga(dialog.carga_creada)
                self._on_model_changed()
                self._refresh_canvas()
                tipo_carga = "uniforme" if dialog.carga_creada.es_uniforme else "distribuida"
                self.statusbar.showMessage(
                    f"Carga {tipo_carga} agregada en Barra {dialog.carga_creada.barra.id}",
                    3000
                )

    def _on_vinculo_combo_changed(self, index):
        """Maneja el cambio en el combobox de vínculo."""
        # Solo aplicar si hay un nudo seleccionado
        if not self.properties_panel._selected_items:
            return

        tipo, id_ = self.properties_panel._selected_items[0]
        if tipo != "nudo":
            return

        # Mapear índice a tipo de vínculo
        vinculo_map = {
            0: None,  # Sin vínculo
            1: "empotramiento",
            2: "apoyo_fijo",
            3: "rodillo_h",
            4: "rodillo_v",
            5: "guia_h",
            6: "guia_v",
        }

        tipo_vinculo = vinculo_map.get(index)

        nudo = self.modelo.obtener_nudo(id_)
        if not nudo:
            return

        self._guardar_snapshot_undo()

        if tipo_vinculo is None:
            # Remover vínculo
            nudo.vinculo = None
        elif tipo_vinculo == "empotramiento":
            self.modelo.asignar_vinculo(id_, Empotramiento(id_))
        elif tipo_vinculo == "apoyo_fijo":
            self.modelo.asignar_vinculo(id_, ApoyoFijo(id_))
        elif tipo_vinculo == "rodillo_h":
            self.modelo.asignar_vinculo(id_, Rodillo(id_, direccion="Uy"))
        elif tipo_vinculo == "rodillo_v":
            self.modelo.asignar_vinculo(id_, Rodillo(id_, direccion="Ux"))
        # TODO: implementar guías

        self._on_model_changed()
        self._refresh_canvas()

    def _on_aplicar_propiedades(self):
        """Aplica los cambios de propiedades al elemento seleccionado."""
        if not self.properties_panel._selected_items:
            return

        self._guardar_snapshot_undo()

        tipo, id_ = self.properties_panel._selected_items[0]

        if tipo == "nudo":
            nudo = self.modelo.obtener_nudo(id_)
            if nudo:
                # Actualizar coordenadas
                nudo.x = self.properties_panel.spin_nudo_x.value()
                nudo.y = self.properties_panel.spin_nudo_y.value()
                nudo.nombre = self.properties_panel.edit_nudo_nombre.text() or None

        elif tipo == "barra":
            barra = self.modelo.obtener_barra(id_)
            if barra:
                # Actualizar articulaciones
                if self.properties_panel.btn_art_i.isChecked() != barra.articulacion_i:
                    if self.properties_panel.btn_art_i.isChecked():
                        self.modelo.agregar_articulacion(id_, "i")
                    else:
                        self.modelo.remover_articulacion(id_, "i")

                if self.properties_panel.btn_art_j.isChecked() != barra.articulacion_j:
                    if self.properties_panel.btn_art_j.isChecked():
                        self.modelo.agregar_articulacion(id_, "j")
                    else:
                        self.modelo.remover_articulacion(id_, "j")

        self._on_model_changed()
        self._refresh_canvas()
        self.statusbar.showMessage("Propiedades aplicadas", 2000)

    def _refresh_canvas(self):
        """Fuerza el repintado del canvas."""
        self.canvas.viewport().update()

    # =========================================================================
    # SLOTS - Acciones del menú
    # =========================================================================

    def _on_nuevo(self):
        """Crea un nuevo proyecto."""
        if self.modelo.esta_modificado:
            resp = QMessageBox.question(
                self,
                "Guardar cambios",
                "¿Desea guardar los cambios antes de crear un nuevo proyecto?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if resp == QMessageBox.StandardButton.Save:
                self._on_guardar()
            elif resp == QMessageBox.StandardButton.Cancel:
                return

        self.modelo = ModeloEstructural("Nuevo proyecto")
        self._ruta_archivo = None
        self._undo_manager.limpiar()
        self.canvas.set_model(self.modelo)
        self.properties_panel.set_canvas(self.canvas)
        self.results_panel.limpiar()
        self._update_title()
        self._update_statusbar()
        self._refresh_canvas()
        self.statusbar.showMessage("Nuevo proyecto creado", 3000)

    def _on_abrir(self):
        """Abre un proyecto existente desde un archivo JSON."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir proyecto",
            "",
            "Proyectos (*.json);;Todos los archivos (*)"
        )
        if not filename:
            return

        try:
            from src.data.proyecto_serializer import cargar_proyecto
            nuevo_modelo = cargar_proyecto(filename)
            self.modelo = nuevo_modelo
            self._ruta_archivo = filename
            self._undo_manager.limpiar()
            self.canvas.set_model(self.modelo)
            self.properties_panel.set_canvas(self.canvas)
            self.results_panel.limpiar()
            self._update_title()
            self._update_statusbar()
            self._refresh_canvas()
            self.statusbar.showMessage(f"Proyecto cargado: {filename}", 5000)
        except Exception as e:
            QMessageBox.critical(
                self, "Error al abrir",
                f"No se pudo cargar el proyecto:\n\n{e}"
            )

    def _on_guardar(self):
        """Guarda el proyecto actual (usa la ruta conocida o pide una nueva)."""
        if self._ruta_archivo:
            self._guardar_en(self._ruta_archivo)
        else:
            self._on_guardar_como()

    def _on_guardar_como(self):
        """Guarda el proyecto con un nuevo nombre."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar proyecto como",
            self.modelo.nombre + ".json",
            "Proyectos (*.json)"
        )
        if filename:
            self._guardar_en(filename)

    def _guardar_en(self, filename: str) -> None:
        """Realiza el guardado efectivo en la ruta indicada."""
        try:
            from src.data.proyecto_serializer import guardar_proyecto
            guardar_proyecto(self.modelo, filename)
            self._ruta_archivo = filename
            self.modelo.marcar_guardado()
            self._update_title()
            self.statusbar.showMessage(f"Guardado: {filename}", 3000)
        except Exception as e:
            QMessageBox.critical(
                self, "Error al guardar",
                f"No se pudo guardar el proyecto:\n\n{e}"
            )

    def _on_exportar(self):
        """Exporta la vista actual del canvas como imagen PNG."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar imagen",
            self.modelo.nombre + ".png",
            "Imágenes PNG (*.png);;Imágenes JPEG (*.jpg)"
        )
        if not filename:
            return

        try:
            from PyQt6.QtGui import QPixmap
            # Capturar el canvas completo como pixmap
            pixmap = self.canvas.grab()
            if pixmap.save(filename):
                self.statusbar.showMessage(f"Exportado: {filename}", 3000)
            else:
                QMessageBox.warning(
                    self, "Error al exportar",
                    "No se pudo guardar la imagen."
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Error al exportar",
                f"Error inesperado al exportar:\n\n{e}"
            )

    def _on_exportar_pdf(self):
        """Exporta el informe de analisis completo como PDF."""
        if self._resultado is None:
            QMessageBox.warning(
                self,
                "Sin resultados",
                "Primero debe resolver la estructura (F5) antes de exportar el PDF."
            )
            return

        nombre_default = (getattr(self.modelo, "nombre", "proyecto") or "proyecto")
        nombre_default = nombre_default.replace(" ", "_") + "_informe.pdf"

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar informe PDF",
            nombre_default,
            "Documentos PDF (*.pdf)"
        )
        if not filename:
            return

        try:
            from src.ui.export.reporte_pdf import generar_reporte_pdf
            generar_reporte_pdf(self.modelo, self._resultado, filename)
            self.statusbar.showMessage(f"PDF exportado: {filename}", 5000)
            QMessageBox.information(
                self,
                "PDF generado",
                f"El informe fue exportado exitosamente:\n\n{filename}"
            )
        except ImportError:
            QMessageBox.critical(
                self,
                "Dependencia faltante",
                "Falta la biblioteca 'reportlab'.\n\n"
                "Instalar con:\n    pip install reportlab"
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al exportar PDF",
                f"No se pudo generar el PDF:\n\n{str(exc)}"
            )

    def _on_eliminar(self):
        """Elimina los elementos seleccionados."""
        if hasattr(self, 'canvas'):
            self.canvas.delete_selected()
            self._refresh_canvas()

    def _on_zoom_in(self):
        """Acerca el zoom."""
        if hasattr(self, 'canvas'):
            self.canvas.zoom_in()

    def _on_zoom_out(self):
        """Aleja el zoom."""
        if hasattr(self, 'canvas'):
            self.canvas.zoom_out()

    def _on_zoom_fit(self):
        """Ajusta el zoom para ver toda la estructura."""
        if hasattr(self, 'canvas'):
            self.canvas.zoom_fit()

    def _on_toggle_grilla(self, checked):
        """Muestra/oculta la grilla."""
        if hasattr(self, 'canvas'):
            self.canvas.set_grid_visible(checked)


    def _on_seleccionar_redundantes(self):
        """Abre el diálogo para seleccionar redundantes."""
        # Verificar que hay estructura
        if self.modelo.num_nudos == 0 or self.modelo.num_barras == 0:
            QMessageBox.warning(
                self,
                "Estructura vacía",
                "No hay elementos en la estructura. Cree nudos y barras primero."
            )
            return

        # Calcular grado de hiperestaticidad
        gh = self.modelo.grado_hiperestaticidad

        if gh < 0:
            QMessageBox.warning(
                self,
                "Estructura Hipostática",
                f"La estructura es hipostática (GH={gh}).\n"
                f"Faltan {-gh} vínculos para que sea estable."
            )
            return

        if gh == 0:
            QMessageBox.information(
                self,
                "Estructura Isostática",
                "La estructura es isostática (GH=0).\n"
                "No es necesario seleccionar redundantes."
            )
            return

        # Abrir diálogo de selección
        dialog = RedundantesDialog(self.modelo, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            redundantes = dialog.obtener_redundantes()
            if redundantes:
                # Guardar redundantes en el modelo
                self.modelo.redundantes_seleccionados = redundantes
                self.statusbar.showMessage(
                    f"Seleccionados {len(redundantes)} redundantes: " +
                    ", ".join(r.descripcion for r in redundantes),
                    5000
                )
                QMessageBox.information(
                    self,
                    "Redundantes Seleccionados",
                    f"Se seleccionaron {len(redundantes)} redundantes:\n\n" +
                    "\n".join(f"{i}. {r.descripcion}" for i, r in enumerate(redundantes, 1)) +
                    "\n\nAhora puede resolver la estructura (F5)."
                )

    def _on_resolver(self):
        """Ejecuta el análisis de la estructura."""
        # Verificar que hay estructura
        if self.modelo.num_nudos == 0 or self.modelo.num_barras == 0:
            QMessageBox.warning(
                self,
                "Estructura vacía",
                "No hay elementos en la estructura."
            )
            return

        metodo_seleccionado = self.combo_metodo.currentData()
        gh = self.modelo.grado_hiperestaticidad

        if gh < 0:
            QMessageBox.warning(
                self,
                "Estructura Hipostática",
                f"La estructura es hipostática (GH={gh}).\n"
                "No se puede resolver."
            )
            return

        # El MD no necesita selección de redundantes: resuelve directamente
        if gh > 0 and metodo_seleccionado == "MF":
            # Verificar si se seleccionaron redundantes
            if not hasattr(self.modelo, 'redundantes_seleccionados') or \
               not self.modelo.redundantes_seleccionados:
                # Si no, abrir diálogo
                resp = QMessageBox.question(
                    self,
                    "Seleccionar Redundantes",
                    f"La estructura es hiperestática (GH={gh}).\n"
                    "¿Desea seleccionar redundantes automáticamente?",
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel
                )

                if resp == QMessageBox.StandardButton.Yes:
                    # Selección automática
                    from src.domain.analysis.redundantes import SelectorRedundantes
                    selector = SelectorRedundantes(self.modelo)
                    try:
                        redundantes = selector.seleccionar_automatico()
                        self.modelo.redundantes_seleccionados = redundantes
                        self.statusbar.showMessage(
                            f"Seleccionados automáticamente: " +
                            ", ".join(r.descripcion for r in redundantes),
                            5000
                        )
                    except ValueError as e:
                        QMessageBox.critical(self, "Error", str(e))
                        return

                elif resp == QMessageBox.StandardButton.No:
                    # Abrir diálogo manual
                    dialog = RedundantesDialog(self.modelo, self)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        redundantes = dialog.obtener_redundantes()
                        self.modelo.redundantes_seleccionados = redundantes
                    else:
                        return  # Usuario canceló
                else:
                    return  # Usuario canceló

        # Ejecutar análisis
        metodo = self.combo_metodo.currentData()
        self.statusbar.showMessage(f"Resolviendo estructura ({metodo})...", 0)

        try:
            if metodo == "MD":
                # Método de las Deformaciones: no requiere redundantes
                motor = MotorMetodoDeformaciones(modelo=self.modelo)
            else:
                # Método de las Fuerzas
                redundantes_manuales = None
                if hasattr(self.modelo, 'redundantes_seleccionados') and self.modelo.redundantes_seleccionados:
                    redundantes_manuales = self.modelo.redundantes_seleccionados

                motor = MotorMetodoFuerzas(
                    modelo=self.modelo,
                    seleccion_manual_redundantes=redundantes_manuales,
                    incluir_deformacion_axial=False,
                    incluir_deformacion_cortante=False,
                )

            # Resolver
            resultado = motor.resolver()

            if resultado.exitoso:
                # Guardar resultado para exportacion PDF
                self._resultado = resultado

                # Actualizar indicador de estado
                self._update_estado_analisis(exitoso=True)

                # Actualizar panel de resultados (pasar modelo para equilibrio correcto)
                self.results_panel.mostrar_resultado(resultado, modelo=self.modelo)

                # Actualizar canvas con diagramas
                if hasattr(self.canvas, 'set_resultado'):
                    self.canvas.set_resultado(resultado)

                self._refresh_canvas()

                # Mensaje de exito (sin emojis: evitar UnicodeEncodeError en consola Windows)
                msg = f"Analisis completado exitosamente\n\n"
                msg += f"Grado de hiperestaticidad: GH = {resultado.grado_hiperestaticidad}\n\n"

                if resultado.redundantes:
                    msg += "Redundantes resueltos:\n"
                    for i, red in enumerate(resultado.redundantes, 1):
                        valor = resultado.Xi(i)
                        msg += f"  X{i} = {valor:+.4f}  ({red.descripcion})\n"
                    msg += "\n"

                msg += "Reacciones calculadas:\n"
                for nudo in self.modelo.nudos:
                    if nudo.tiene_vinculo:
                        Rx, Ry, Mz = resultado.obtener_reaccion(nudo.id)
                        msg += (
                            f"  Nudo {nudo.id}:  "
                            f"Rx = {Rx:+.3f} kN,  "
                            f"Ry = {Ry:+.3f} kN,  "
                            f"Mz = {Mz:+.3f} kNm\n"
                        )

                # Advertencias relevantes para el usuario (omitir las informativas de GH)
                advertencias_usuario = [
                    adv for adv in resultado.advertencias
                    if "hiperestatica" not in adv.lower()
                    and "isostatica" not in adv.lower()
                    and "redundante x" not in adv.lower()[:15]
                ]
                if advertencias_usuario:
                    msg += f"\nAdvertencias ({len(advertencias_usuario)}):\n"
                    for adv in advertencias_usuario[:3]:
                        msg += f"  * {adv}\n"

                QMessageBox.information(self, "Analisis Completado", msg)
                self.statusbar.showMessage("Analisis completado exitosamente", 5000)

            else:
                # Error en analisis
                self._update_estado_analisis(exitoso=False)
                msg_error = "Error durante el analisis:\n\n"
                msg_error += "\n".join(f"- {e}" for e in resultado.errores)

                QMessageBox.critical(self, "Error en Analisis", msg_error)
                self.statusbar.showMessage("Error en analisis", 5000)

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()

            self._update_estado_analisis(exitoso=False)
            QMessageBox.critical(
                self,
                "Error Inesperado",
                f"Ocurrio un error inesperado durante el analisis:\n\n{str(e)}\n\n"
                f"Detalles tecnicos:\n{error_detail[:500]}"
            )
            self.statusbar.showMessage("Error en analisis", 5000)

    def _on_ver_diagramas(self):
        """Alterna todos los diagramas a la vez (F6). Sincroniza los botones del toolbar."""
        if hasattr(self, 'canvas'):
            self.canvas.toggle_diagrams()
            # Sincronizar estado de botones con el canvas
            for btn_name, flag in (
                ('btn_diagrama_N', self.canvas._show_diagrama_N),
                ('btn_diagrama_V', self.canvas._show_diagrama_V),
                ('btn_diagrama_M', self.canvas._show_diagrama_M),
            ):
                if hasattr(self, btn_name):
                    getattr(self, btn_name).setChecked(flag)
            self._refresh_canvas()

    def _on_toggle_diagrama_N(self, checked: bool) -> None:
        """Activa o desactiva el diagrama de axiles."""
        if hasattr(self, 'canvas'):
            self.canvas.set_mostrar_diagrama_N(checked)

    def _on_toggle_diagrama_V(self, checked: bool) -> None:
        """Activa o desactiva el diagrama de cortantes."""
        if hasattr(self, 'canvas'):
            self.canvas.set_mostrar_diagrama_V(checked)

    def _on_toggle_diagrama_M(self, checked: bool) -> None:
        """Activa o desactiva el diagrama de momentos."""
        if hasattr(self, 'canvas'):
            self.canvas.set_mostrar_diagrama_M(checked)

    def _on_ver_deformada(self) -> None:
        """Abre la deformada elástica en una ventana matplotlib."""
        if self._resultado is None or self.modelo is None:
            return
        try:
            from src.ui.visualization.deformada import graficar_deformada
            import matplotlib.pyplot as plt
            graficar_deformada(self.modelo, self._resultado)
            plt.show(block=False)
        except Exception as e:
            QMessageBox.warning(
                self, "Error",
                f"No se pudo generar la deformada:\n{e}"
            )

    def _on_acerca(self):
        """Muestra información sobre la aplicación."""
        QMessageBox.about(
            self,
            "Acerca de",
            "<h3>Análisis Estructural</h3>"
            "<p>Sistema de análisis de pórticos planos 2D</p>"
            "<p>Método de las Fuerzas (Flexibilidad)</p>"
            "<p><b>Versión:</b> 1.0.0</p>"
        )

    # =========================================================================
    # SLOTS - Eventos del canvas
    # =========================================================================

    def _on_selection_changed(self, selected_items):
        """Maneja el cambio de selección."""
        self.properties_panel.update_selection(selected_items)

        # Cargar el vínculo actual en el combo
        if selected_items and len(selected_items) == 1:
            tipo, id_ = selected_items[0]
            if tipo == "nudo":
                nudo = self.modelo.obtener_nudo(id_)
                if nudo:
                    # Bloquear señales para evitar bucle
                    self.properties_panel.combo_vinculo.blockSignals(True)

                    if not nudo.tiene_vinculo:
                        self.properties_panel.combo_vinculo.setCurrentIndex(0)
                    elif isinstance(nudo.vinculo, Empotramiento):
                        self.properties_panel.combo_vinculo.setCurrentIndex(1)
                    elif isinstance(nudo.vinculo, ApoyoFijo):
                        self.properties_panel.combo_vinculo.setCurrentIndex(2)
                    elif isinstance(nudo.vinculo, Rodillo):
                        if nudo.vinculo.direccion == "Uy":
                            self.properties_panel.combo_vinculo.setCurrentIndex(3)
                        else:
                            self.properties_panel.combo_vinculo.setCurrentIndex(4)

                    self.properties_panel.combo_vinculo.blockSignals(False)

    def _on_model_changed(self):
        """Maneja cambios en el modelo."""
        self._update_title()
        self._update_statusbar()
        # Cualquier cambio en el modelo invalida el resultado anterior
        self._resultado = None
        self._update_estado_analisis(exitoso=None)
        self._refresh_canvas()

    def closeEvent(self, event):
        """Maneja el cierre de la ventana."""
        if self.modelo.esta_modificado:
            resp = QMessageBox.question(
                self,
                "Guardar cambios",
                "¿Desea guardar los cambios antes de salir?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if resp == QMessageBox.StandardButton.Save:
                self._on_guardar()
                event.accept()
            elif resp == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
