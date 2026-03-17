"""
Panel de propiedades para editar elementos seleccionados.
"""

from typing import List, Tuple, Optional
import math

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QSpacerItem,
    QSizePolicy,
    QCheckBox,
    QFrame,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSignal

from src.domain.entities.material import Material, hormigon
from src.domain.entities.seccion import SeccionPerfil
from src.domain.entities.vinculo import (
    Empotramiento,
    ApoyoFijo,
    Rodillo,
    Guia,
)


# ---------------------------------------------------------------------------
# Catálogo de materiales predefinidos
# ---------------------------------------------------------------------------
_MATERIALES_PREDEFINIDOS = {
    "Acero A-36":    Material("Acero A-36",   E=200e6, alpha=1.2e-5, rho=7850),
    "Acero S235":    Material("Acero S235",   E=210e6, alpha=1.2e-5, rho=7850),
    "Acero S275":    Material("Acero S275",   E=210e6, alpha=1.2e-5, rho=7850),
    "Acero S355":    Material("Acero S355",   E=210e6, alpha=1.2e-5, rho=7850),
    "Hormigón H-25": hormigon(25),
    "Hormigón H-30": hormigon(30),
}

# ---------------------------------------------------------------------------
# Catálogo de secciones predefinidas  (A [m²], Iz [m⁴], h [m])
# ---------------------------------------------------------------------------
_SECCIONES_PREDEFINIDAS = {
    "IPE 200": SeccionPerfil("IPE 200", _A=28.5e-4, _Iz=1943e-8, _h=0.200),
    "IPE 220": SeccionPerfil("IPE 220", _A=33.4e-4, _Iz=2772e-8, _h=0.220),
    "IPE 240": SeccionPerfil("IPE 240", _A=39.1e-4, _Iz=3892e-8, _h=0.240),
    "IPE 270": SeccionPerfil("IPE 270", _A=45.9e-4, _Iz=5790e-8, _h=0.270),
    "IPE 300": SeccionPerfil("IPE 300", _A=53.8e-4, _Iz=8356e-8, _h=0.300),
    "HEA 200": SeccionPerfil("HEA 200", _A=53.8e-4, _Iz=3692e-8, _h=0.190),
    "HEA 220": SeccionPerfil("HEA 220", _A=64.3e-4, _Iz=5410e-8, _h=0.210),
}


class PropertiesPanel(QWidget):
    """
    Panel para ver y editar propiedades de elementos seleccionados.

    Muestra diferentes controles según el tipo de elemento seleccionado:
    - Nudo: coordenadas, nombre, vínculo
    - Barra: material, sección, articulaciones
    - Cualquier elemento: panel de agregar carga

    También incluye:
    - Entrada paramétrica para crear nudos/barras con precisión
    - Configuración de grilla y snap
    """

    # Señales
    property_changed = pyqtSignal()
    create_node_requested = pyqtSignal(float, float)   # x, y
    create_bar_requested = pyqtSignal(int, int)        # nudo_i_id, nudo_j_id
    grid_settings_changed = pyqtSignal(float, bool)    # grid_size, snap_enabled

    def __init__(self, parent=None):
        super().__init__(parent)

        self._selected_items: List[Tuple[str, int]] = []
        self._canvas = None  # Referencia al canvas (StructureCanvas)

        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Referencia al canvas
    # ------------------------------------------------------------------

    def set_canvas(self, canvas):
        """Establece referencia al canvas para operaciones interactivas."""
        self._canvas = canvas

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Construye todos los widgets del panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # --- Grilla y Snap -------------------------------------------
        self.group_grilla = QGroupBox("Grilla y Snap")
        grilla_layout = QFormLayout(self.group_grilla)

        self.spin_grid_size = QDoubleSpinBox()
        self.spin_grid_size.setRange(0.1, 10.0)
        self.spin_grid_size.setValue(1.0)
        self.spin_grid_size.setDecimals(2)
        self.spin_grid_size.setSuffix(" m")
        self.spin_grid_size.setSingleStep(0.5)
        grilla_layout.addRow("Tamaño celda:", self.spin_grid_size)

        self.check_snap = QCheckBox("Snap to Grid (G)")
        self.check_snap.setChecked(True)
        grilla_layout.addRow("", self.check_snap)

        layout.addWidget(self.group_grilla)

        # --- Crear Nudo paramétrico ----------------------------------
        self.group_crear_nudo = QGroupBox("Crear Nudo (Paramétrico)")
        crear_nudo_layout = QFormLayout(self.group_crear_nudo)

        self.spin_nuevo_x = QDoubleSpinBox()
        self.spin_nuevo_x.setRange(-1000, 1000)
        self.spin_nuevo_x.setDecimals(3)
        self.spin_nuevo_x.setSuffix(" m")
        crear_nudo_layout.addRow("X:", self.spin_nuevo_x)

        self.spin_nuevo_y = QDoubleSpinBox()
        self.spin_nuevo_y.setRange(-1000, 1000)
        self.spin_nuevo_y.setDecimals(3)
        self.spin_nuevo_y.setSuffix(" m")
        crear_nudo_layout.addRow("Y:", self.spin_nuevo_y)

        self.btn_crear_nudo = QPushButton("Crear Nudo")
        crear_nudo_layout.addRow("", self.btn_crear_nudo)

        self.group_crear_nudo.setVisible(False)  # oculto hasta activar herramienta Nudo
        layout.addWidget(self.group_crear_nudo)

        # --- Crear Barra paramétrica ---------------------------------
        self.group_crear_barra = QGroupBox("Crear Barra (Paramétrico)")
        crear_barra_layout = QFormLayout(self.group_crear_barra)

        self.spin_barra_nudo_i = QSpinBox()
        self.spin_barra_nudo_i.setRange(1, 9999)
        self.spin_barra_nudo_i.setPrefix("N")
        crear_barra_layout.addRow("Nudo inicial:", self.spin_barra_nudo_i)

        self.spin_barra_nudo_j = QSpinBox()
        self.spin_barra_nudo_j.setRange(1, 9999)
        self.spin_barra_nudo_j.setPrefix("N")
        crear_barra_layout.addRow("Nudo final:", self.spin_barra_nudo_j)

        self.btn_crear_barra = QPushButton("Crear Barra")
        crear_barra_layout.addRow("", self.btn_crear_barra)

        self.group_crear_barra.setVisible(False)  # oculto hasta activar herramienta Barra
        layout.addWidget(self.group_crear_barra)

        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # --- Etiqueta de selección -----------------------------------
        self.label_seleccion = QLabel("Sin selección")
        self.label_seleccion.setStyleSheet(
            "font-weight: bold; padding: 5px; background-color: #f0f0f0;"
        )
        layout.addWidget(self.label_seleccion)

        # --- Propiedades del Nudo ------------------------------------
        self.group_nudo = QGroupBox("Propiedades del Nudo")
        nudo_layout = QFormLayout(self.group_nudo)

        self.spin_nudo_x = QDoubleSpinBox()
        self.spin_nudo_x.setRange(-1000, 1000)
        self.spin_nudo_x.setDecimals(3)
        self.spin_nudo_x.setSuffix(" m")
        nudo_layout.addRow("X:", self.spin_nudo_x)

        self.spin_nudo_y = QDoubleSpinBox()
        self.spin_nudo_y.setRange(-1000, 1000)
        self.spin_nudo_y.setDecimals(3)
        self.spin_nudo_y.setSuffix(" m")
        nudo_layout.addRow("Y:", self.spin_nudo_y)

        self.edit_nudo_nombre = QLineEdit()
        self.edit_nudo_nombre.setPlaceholderText("Nombre opcional")
        nudo_layout.addRow("Nombre:", self.edit_nudo_nombre)

        self.combo_vinculo = QComboBox()
        self.combo_vinculo.addItems([
            "Sin vínculo",
            "Empotramiento",
            "Apoyo Fijo",
            "Rodillo Horizontal",
            "Rodillo Vertical",
            "Guía Horizontal",
            "Guía Vertical",
        ])
        nudo_layout.addRow("Vínculo:", self.combo_vinculo)

        self.group_nudo.setVisible(False)
        layout.addWidget(self.group_nudo)

        # --- Propiedades de la Barra ---------------------------------
        self.group_barra = QGroupBox("Propiedades de la Barra")
        barra_layout = QFormLayout(self.group_barra)

        self.label_longitud = QLabel("0.000 m")
        barra_layout.addRow("Longitud:", self.label_longitud)

        self.label_angulo = QLabel("0.00°")
        barra_layout.addRow("Ángulo:", self.label_angulo)

        self.combo_material = QComboBox()
        self.combo_material.addItems(list(_MATERIALES_PREDEFINIDOS.keys()))
        barra_layout.addRow("Material:", self.combo_material)

        self.combo_seccion = QComboBox()
        self.combo_seccion.addItems(list(_SECCIONES_PREDEFINIDAS.keys()))
        barra_layout.addRow("Sección:", self.combo_seccion)

        self.btn_art_i = QPushButton("Articulación en i")
        self.btn_art_i.setCheckable(True)
        barra_layout.addRow("", self.btn_art_i)

        self.btn_art_j = QPushButton("Articulación en j")
        self.btn_art_j.setCheckable(True)
        barra_layout.addRow("", self.btn_art_j)

        self.group_barra.setVisible(False)
        layout.addWidget(self.group_barra)

        # --- Agregar Carga -------------------------------------------
        self.group_carga = QGroupBox("Agregar Carga")
        carga_layout = QFormLayout(self.group_carga)

        self.combo_tipo_carga = QComboBox()
        self.combo_tipo_carga.addItems([
            "Puntual en nudo",
            "Puntual en barra",
            "Distribuida uniforme",
        ])
        carga_layout.addRow("Tipo:", self.combo_tipo_carga)

        self.spin_carga_valor = QDoubleSpinBox()
        self.spin_carga_valor.setRange(-10000, 10000)
        self.spin_carga_valor.setDecimals(2)
        self.spin_carga_valor.setValue(-10.0)
        self.spin_carga_valor.setSuffix(" kN")
        carga_layout.addRow("Valor:", self.spin_carga_valor)

        self.spin_carga_pos = QDoubleSpinBox()
        self.spin_carga_pos.setRange(0, 100)
        self.spin_carga_pos.setDecimals(2)
        self.spin_carga_pos.setSuffix(" m")
        carga_layout.addRow("Posición:", self.spin_carga_pos)

        self.btn_agregar_carga = QPushButton("Agregar Carga")
        carga_layout.addRow("", self.btn_agregar_carga)

        self.group_carga.setVisible(False)
        layout.addWidget(self.group_carga)

        # --- Espaciador + Botón aplicar ------------------------------
        layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        self.btn_aplicar = QPushButton("Aplicar Cambios")
        self.btn_aplicar.setEnabled(False)
        layout.addWidget(self.btn_aplicar)

    # ------------------------------------------------------------------
    # Conexión de señales
    # ------------------------------------------------------------------

    def _connect_signals(self):
        """Conecta todos los widgets a sus handlers."""
        # Grilla
        self.spin_grid_size.valueChanged.connect(self._on_grid_settings_changed)
        self.check_snap.stateChanged.connect(self._on_grid_settings_changed)

        # Creación paramétrica
        self.btn_crear_nudo.clicked.connect(self._on_crear_nudo)
        self.btn_crear_barra.clicked.connect(self._on_crear_barra)

        # Aplicar cambios de propiedades
        self.btn_aplicar.clicked.connect(self._on_aplicar_cambios)

        # Articulaciones: aplican inmediatamente al toggler
        self.btn_art_i.toggled.connect(self._on_art_i_toggled)
        self.btn_art_j.toggled.connect(self._on_art_j_toggled)

        # Agregar carga
        self.btn_agregar_carga.clicked.connect(self._on_agregar_carga)

        # Adaptar label del valor de carga según tipo
        self.combo_tipo_carga.currentIndexChanged.connect(self._on_tipo_carga_changed)

    # ------------------------------------------------------------------
    # Handlers de grilla
    # ------------------------------------------------------------------

    def _on_grid_settings_changed(self):
        """Propaga cambios de grilla al canvas."""
        grid_size = self.spin_grid_size.value()
        snap_enabled = self.check_snap.isChecked()
        if self._canvas is not None:
            self._canvas.grid_size = grid_size
            self._canvas.snap_enabled = snap_enabled
            self._canvas.viewport().update()
        self.grid_settings_changed.emit(grid_size, snap_enabled)

    def sync_snap_state(self, snap_enabled: bool):
        """Sincroniza el checkbox de snap desde el canvas (tecla G)."""
        self.check_snap.blockSignals(True)
        self.check_snap.setChecked(snap_enabled)
        self.check_snap.blockSignals(False)

    # ------------------------------------------------------------------
    # Handlers de creación paramétrica
    # ------------------------------------------------------------------

    def _on_crear_nudo(self):
        """Crea nudo con las coordenadas del spinbox."""
        x = self.spin_nuevo_x.value()
        y = self.spin_nuevo_y.value()
        if self._canvas is not None:
            nudo = self._canvas.create_node_parametric(x, y)
            if nudo:
                self.spin_barra_nudo_j.setValue(nudo.id)
        self.create_node_requested.emit(x, y)

    def _on_crear_barra(self):
        """Crea barra entre los nudos indicados en los spinboxes."""
        nudo_i_id = self.spin_barra_nudo_i.value()
        nudo_j_id = self.spin_barra_nudo_j.value()
        if nudo_i_id == nudo_j_id:
            return
        if self._canvas is not None:
            self._canvas.create_bar_parametric(nudo_i_id, nudo_j_id)
        self.create_bar_requested.emit(nudo_i_id, nudo_j_id)

    # ------------------------------------------------------------------
    # Handler: Aplicar cambios de propiedades
    # ------------------------------------------------------------------

    def _on_aplicar_cambios(self):
        """
        Aplica los cambios del panel al elemento seleccionado.

        - Nudo: actualiza coordenadas, nombre y vínculo.
        - Barra: actualiza material y sección.
        """
        if not self._selected_items or len(self._selected_items) != 1:
            return
        if self._canvas is None:
            return

        tipo, id_ = self._selected_items[0]

        if tipo == "nudo":
            self._aplicar_cambios_nudo(id_)
        elif tipo == "barra":
            self._aplicar_cambios_barra(id_)

    def _aplicar_cambios_nudo(self, nudo_id: int):
        """Actualiza coordenadas, nombre y vínculo de un nudo."""
        modelo = self._canvas.modelo
        nudo = modelo.obtener_nudo(nudo_id)
        if nudo is None:
            return

        # Coordenadas
        nuevo_x = self.spin_nudo_x.value()
        nuevo_y = self.spin_nudo_y.value()
        nudo.x = nuevo_x
        nudo.y = nuevo_y

        # Nombre
        nudo.nombre = self.edit_nudo_nombre.text().strip()

        # Vínculo
        texto_vinculo = self.combo_vinculo.currentText()
        nudo.vinculo = self._crear_vinculo(texto_vinculo, nudo)

        # L y angulo son propiedades calculadas dinámicamente en Barra,
        # no hace falta recalcular explícitamente.
        modelo._marcar_modificado()
        self._canvas.viewport().update()
        self.property_changed.emit()

    def _aplicar_cambios_barra(self, barra_id: int):
        """Actualiza material y sección de una barra."""
        modelo = self._canvas.modelo
        barra = modelo.obtener_barra(barra_id)
        if barra is None:
            return

        nombre_mat = self.combo_material.currentText()
        nombre_sec = self.combo_seccion.currentText()

        # Material
        nuevo_material = _MATERIALES_PREDEFINIDOS.get(nombre_mat)
        if nuevo_material is None:
            QMessageBox.warning(self, "Material no encontrado",
                                f"No se encontró el material '{nombre_mat}'.")
            return

        # Sección
        nueva_seccion = _SECCIONES_PREDEFINIDAS.get(nombre_sec)
        if nueva_seccion is None:
            QMessageBox.warning(self, "Sección no encontrada",
                                f"No se encontró la sección '{nombre_sec}'.")
            return

        barra.material = nuevo_material
        barra.seccion = nueva_seccion

        # Registrar en el catálogo del modelo
        modelo._materiales[nuevo_material.nombre] = nuevo_material
        modelo._secciones[nueva_seccion.nombre] = nueva_seccion

        modelo._marcar_modificado()
        self._canvas.viewport().update()
        self.property_changed.emit()

    # ------------------------------------------------------------------
    # Helpers de vínculo
    # ------------------------------------------------------------------

    def _crear_vinculo(self, texto: str, nudo):
        """Instancia el vínculo correspondiente al texto del combo."""
        if texto == "Sin vínculo":
            return None
        elif texto == "Empotramiento":
            return Empotramiento(nudo=nudo)
        elif texto == "Apoyo Fijo":
            return ApoyoFijo(nudo=nudo)
        elif texto == "Rodillo Horizontal":
            return Rodillo(nudo=nudo, direccion="Uy")   # restringe Uy
        elif texto == "Rodillo Vertical":
            return Rodillo(nudo=nudo, direccion="Ux")   # restringe Ux
        elif texto == "Guía Horizontal":
            return Guia(nudo=nudo, direccion_libre="Ux")
        elif texto == "Guía Vertical":
            return Guia(nudo=nudo, direccion_libre="Uy")
        return None

    def _texto_vinculo(self, vinculo) -> str:
        """Devuelve el texto del combo correspondiente a un vínculo existente."""
        if vinculo is None:
            return "Sin vínculo"
        if isinstance(vinculo, Empotramiento):
            return "Empotramiento"
        if isinstance(vinculo, ApoyoFijo):
            return "Apoyo Fijo"
        if isinstance(vinculo, Rodillo):
            return "Rodillo Horizontal" if vinculo.direccion == "Uy" else "Rodillo Vertical"
        if isinstance(vinculo, Guia):
            return "Guía Horizontal" if vinculo.direccion_libre == "Ux" else "Guía Vertical"
        return "Sin vínculo"

    # ------------------------------------------------------------------
    # Handlers de articulaciones (toggling inmediato)
    # ------------------------------------------------------------------

    def _on_art_i_toggled(self, checked: bool):
        """Activa/desactiva articulación en el extremo i de la barra seleccionada."""
        if not self._selected_items or self._canvas is None:
            return
        tipo, id_ = self._selected_items[0]
        if tipo != "barra":
            return
        barra = self._canvas.modelo.obtener_barra(id_)
        if barra is None:
            return
        if checked:
            barra.articular_extremo_i()
        else:
            barra.articulacion_i = False
        self._canvas.modelo._marcar_modificado()
        self._canvas.viewport().update()

    def _on_art_j_toggled(self, checked: bool):
        """Activa/desactiva articulación en el extremo j de la barra seleccionada."""
        if not self._selected_items or self._canvas is None:
            return
        tipo, id_ = self._selected_items[0]
        if tipo != "barra":
            return
        barra = self._canvas.modelo.obtener_barra(id_)
        if barra is None:
            return
        if checked:
            barra.articular_extremo_j()
        else:
            barra.articulacion_j = False
        self._canvas.modelo._marcar_modificado()
        self._canvas.viewport().update()

    # ------------------------------------------------------------------
    # Handler: tipo de carga cambia → actualiza etiqueta del valor
    # ------------------------------------------------------------------

    def _on_tipo_carga_changed(self, index: int):
        """Adapta el suffix del spinbox de valor según el tipo de carga."""
        tipo = self.combo_tipo_carga.currentText()
        if tipo == "Distribuida uniforme":
            self.spin_carga_valor.setSuffix(" kN/m")
            self.spin_carga_pos.setVisible(False)
        elif tipo == "Puntual en barra":
            self.spin_carga_valor.setSuffix(" kN")
            self.spin_carga_pos.setVisible(True)
        else:  # Puntual en nudo
            self.spin_carga_valor.setSuffix(" kN")
            self.spin_carga_pos.setVisible(False)

    # ------------------------------------------------------------------
    # Handler: Agregar Carga
    # ------------------------------------------------------------------

    def _on_agregar_carga(self):
        """
        Abre el diálogo de carga apropiado según el tipo seleccionado
        y el tipo de elemento activo.

        - Si hay un nudo seleccionado → CargaPuntualNudoDialog
        - Si hay una barra seleccionada → CargaPuntualBarraDialog o CargaDistribuidaDialog
        """
        if self._canvas is None:
            return

        modelo = self._canvas.modelo
        tipo_carga = self.combo_tipo_carga.currentText()

        # Determinar elemento seleccionado
        elem_tipo = None
        elem_id = None
        if len(self._selected_items) == 1:
            elem_tipo, elem_id = self._selected_items[0]

        from src.gui.dialogs.carga_dialog import (
            CargaPuntualNudoDialog,
            CargaPuntualBarraDialog,
            CargaDistribuidaDialog,
        )

        if tipo_carga == "Puntual en nudo":
            dlg = CargaPuntualNudoDialog(modelo, parent=self)
            # Pre-seleccionar el nudo si hay uno seleccionado
            if elem_tipo == "nudo" and elem_id is not None:
                for i in range(dlg.combo_nudo.count()):
                    if dlg.combo_nudo.itemData(i) == elem_id:
                        dlg.combo_nudo.setCurrentIndex(i)
                        break
            if dlg.exec() and dlg.carga_creada is not None:
                modelo.agregar_carga(dlg.carga_creada)
                self._canvas.viewport().update()
                self.property_changed.emit()

        elif tipo_carga == "Puntual en barra":
            if elem_tipo != "barra":
                QMessageBox.information(
                    self, "Selección requerida",
                    "Seleccione una barra en el canvas antes de agregar una carga puntual en barra."
                )
                return
            dlg = CargaPuntualBarraDialog(modelo, parent=self)
            # Pre-seleccionar la barra activa
            for i in range(dlg.combo_barra.count()):
                if dlg.combo_barra.itemData(i) == elem_id:
                    dlg.combo_barra.setCurrentIndex(i)
                    break
            if dlg.exec() and dlg.carga_creada is not None:
                modelo.agregar_carga(dlg.carga_creada)
                self._canvas.viewport().update()
                self.property_changed.emit()

        elif tipo_carga == "Distribuida uniforme":
            if elem_tipo != "barra":
                QMessageBox.information(
                    self, "Selección requerida",
                    "Seleccione una barra en el canvas antes de agregar una carga distribuida."
                )
                return
            dlg = CargaDistribuidaDialog(modelo, parent=self)
            for i in range(dlg.combo_barra.count()):
                if dlg.combo_barra.itemData(i) == elem_id:
                    dlg.combo_barra.setCurrentIndex(i)
                    break
            if dlg.exec() and dlg.carga_creada is not None:
                modelo.agregar_carga(dlg.carga_creada)
                self._canvas.viewport().update()
                self.property_changed.emit()

    # ------------------------------------------------------------------
    # Actualizar panel según selección del canvas
    # ------------------------------------------------------------------

    def update_selection(self, selected_items: List[Tuple[str, int]]):
        """
        Muestra/oculta grupos de propiedades según el elemento seleccionado.

        Args:
            selected_items: Lista de tuplas (tipo, id) – normalmente 0 ó 1 elemento.
        """
        self._selected_items = selected_items

        # Ocultar todo
        self.group_nudo.setVisible(False)
        self.group_barra.setVisible(False)
        self.group_carga.setVisible(False)
        self.btn_aplicar.setEnabled(False)

        if not selected_items:
            self.label_seleccion.setText("Sin selección")
            return

        if len(selected_items) == 1:
            tipo, id_ = selected_items[0]

            if tipo == "nudo":
                self.label_seleccion.setText(f"Nudo N{id_}")
                self.group_nudo.setVisible(True)
                self.group_carga.setVisible(True)
                self.btn_aplicar.setEnabled(True)

                # Poblar con datos del nudo
                if self._canvas is not None:
                    nudo = self._canvas.modelo.obtener_nudo(id_)
                    if nudo:
                        # Bloquear señales para no disparar cambios no deseados
                        self.spin_nudo_x.blockSignals(True)
                        self.spin_nudo_y.blockSignals(True)
                        self.combo_vinculo.blockSignals(True)

                        self.spin_nudo_x.setValue(nudo.x)
                        self.spin_nudo_y.setValue(nudo.y)
                        self.edit_nudo_nombre.setText(nudo.nombre or "")
                        texto = self._texto_vinculo(nudo.vinculo)
                        idx = self.combo_vinculo.findText(texto)
                        if idx >= 0:
                            self.combo_vinculo.setCurrentIndex(idx)

                        self.spin_nudo_x.blockSignals(False)
                        self.spin_nudo_y.blockSignals(False)
                        self.combo_vinculo.blockSignals(False)

            elif tipo == "barra":
                self.label_seleccion.setText(f"Barra B{id_}")
                self.group_barra.setVisible(True)
                self.group_carga.setVisible(True)
                self.btn_aplicar.setEnabled(True)

                # Poblar con datos de la barra
                if self._canvas is not None:
                    barra = self._canvas.modelo.obtener_barra(id_)
                    if barra:
                        self.label_longitud.setText(f"{barra.L:.3f} m")
                        self.label_angulo.setText(f"{math.degrees(barra.angulo):.2f}°")

                        # Material
                        idx_mat = self.combo_material.findText(barra.material.nombre)
                        if idx_mat >= 0:
                            self.combo_material.blockSignals(True)
                            self.combo_material.setCurrentIndex(idx_mat)
                            self.combo_material.blockSignals(False)

                        # Sección
                        idx_sec = self.combo_seccion.findText(barra.seccion.nombre)
                        if idx_sec >= 0:
                            self.combo_seccion.blockSignals(True)
                            self.combo_seccion.setCurrentIndex(idx_sec)
                            self.combo_seccion.blockSignals(False)

                        # Articulaciones (sin disparar los toggled)
                        self.btn_art_i.blockSignals(True)
                        self.btn_art_j.blockSignals(True)
                        self.btn_art_i.setChecked(barra.articulacion_i)
                        self.btn_art_j.setChecked(barra.articulacion_j)
                        self.btn_art_i.blockSignals(False)
                        self.btn_art_j.blockSignals(False)

        else:
            self.label_seleccion.setText(f"{len(selected_items)} elementos seleccionados")

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def set_tool_mode(self, mode: str) -> None:
        """
        Ajusta la sección de creación paramétrica visible según la herramienta activa.

        Args:
            mode: "select"       → oculta creación de nudo y barra
                  "create_node"  → muestra creación de nudo, oculta barra
                  "create_bar"   → muestra creación de barra, oculta nudo
        """
        if mode == "create_node":
            self.group_crear_nudo.setVisible(True)
            self.group_crear_barra.setVisible(False)
        elif mode == "create_bar":
            self.group_crear_nudo.setVisible(False)
            self.group_crear_barra.setVisible(True)
        else:
            # "select" u otro modo: ocultar ambas secciones de creación
            self.group_crear_nudo.setVisible(False)
            self.group_crear_barra.setVisible(False)

    def clear(self):
        """Limpia el panel (sin selección)."""
        self._selected_items.clear()
        self.update_selection([])
