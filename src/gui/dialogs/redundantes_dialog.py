"""
Diálogo para selección manual de redundantes.
"""

from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from src.domain.model.modelo_estructural import ModeloEstructural
from src.domain.analysis.redundantes import Redundante, SelectorRedundantes, TipoRedundante


class RedundantesDialog(QDialog):
    """
    Diálogo para seleccionar redundantes manual o automáticamente.

    Permite al usuario:
    - Ver el grado de hiperestaticidad
    - Seleccionar redundantes automáticamente (heurística)
    - Seleccionar redundantes manualmente desde lista de candidatos
    - Ver descripción de cada redundante
    """

    def __init__(self, modelo: ModeloEstructural, parent=None):
        super().__init__(parent)
        self.modelo = modelo
        self.selector = SelectorRedundantes(modelo)
        self.redundantes_seleccionados: List[Redundante] = []

        self.setWindowTitle("Selección de Redundantes")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self._init_ui()
        self._cargar_candidatos()

    def _init_ui(self):
        """Inicializa la interfaz de usuario."""
        layout = QVBoxLayout(self)

        # Información del modelo
        group_info = QGroupBox("Información de la Estructura")
        layout_info = QVBoxLayout()

        gh = self.modelo.grado_hiperestaticidad

        label_gh = QLabel(f"<b>Grado de Hiperestaticidad (GH):</b> {gh}")
        label_gh.setStyleSheet("font-size: 14px; padding: 5px;")
        layout_info.addWidget(label_gh)

        if gh < 0:
            label_error = QLabel(
                f"<b>Estructura HIPOSTATICA</b> — faltan {-gh} vinculos"
            )
            label_error.setStyleSheet("color: #cc0000; font-size: 12px; padding: 5px;")
            layout_info.addWidget(label_error)
        elif gh == 0:
            label_iso = QLabel("Estructura ISOSTATICA — no requiere seleccion de redundantes")
            label_iso.setStyleSheet("color: #00aa00; font-size: 12px; padding: 5px;")
            layout_info.addWidget(label_iso)
        else:
            label_hiper = QLabel(
                f"Estructura HIPERESTATICA — se requieren {gh} redundantes"
            )
            label_hiper.setStyleSheet("color: #0066cc; font-size: 12px; padding: 5px;")
            layout_info.addWidget(label_hiper)

        group_info.setLayout(layout_info)
        layout.addWidget(group_info)

        # Botón de selección automática
        btn_auto = QPushButton("Seleccionar Automáticamente (Heurística)")
        btn_auto.clicked.connect(self._seleccionar_automatico)
        layout.addWidget(btn_auto)

        # Listas de candidatos y seleccionados
        layout_listas = QHBoxLayout()

        # Lista de candidatos disponibles
        group_candidatos = QGroupBox("Candidatos Disponibles")
        layout_candidatos = QVBoxLayout()

        label_candidatos = QLabel(
            "<i>Haga doble clic para agregar a la selección →</i>"
        )
        label_candidatos.setStyleSheet("color: #666; font-size: 11px;")
        layout_candidatos.addWidget(label_candidatos)

        self.list_candidatos = QListWidget()
        self.list_candidatos.itemDoubleClicked.connect(self._agregar_redundante)
        layout_candidatos.addWidget(self.list_candidatos)

        group_candidatos.setLayout(layout_candidatos)
        layout_listas.addWidget(group_candidatos)

        # Lista de redundantes seleccionados
        group_seleccionados = QGroupBox(f"Redundantes Seleccionados (0/{gh})")
        layout_seleccionados = QVBoxLayout()

        label_seleccionados = QLabel(
            "<i>← Haga doble clic para quitar de la selección</i>"
        )
        label_seleccionados.setStyleSheet("color: #666; font-size: 11px;")
        layout_seleccionados.addWidget(label_seleccionados)

        self.list_seleccionados = QListWidget()
        self.list_seleccionados.itemDoubleClicked.connect(self._quitar_redundante)
        layout_seleccionados.addWidget(self.list_seleccionados)

        group_seleccionados.setLayout(layout_seleccionados)
        self.group_seleccionados = group_seleccionados
        layout_listas.addWidget(group_seleccionados)

        layout.addLayout(layout_listas)

        # Nota informativa
        label_nota = QLabel(
            "<b>Criterio de selección automática:</b><br>"
            "1. Prioriza momentos de reacción (Mz) en empotramientos<br>"
            "2. Luego reacciones verticales (Ry)<br>"
            "3. Luego reacciones horizontales (Rx)<br>"
            "4. Evita crear subestructuras inestables<br>"
            "<br>"
            "<b>Selección manual:</b> Elija exactamente {gh} redundantes de la lista de candidatos."
        )
        label_nota.setWordWrap(True)
        label_nota.setStyleSheet(
            "background: #f5f5f5; padding: 10px; border-radius: 5px; font-size: 11px;"
        )
        layout.addWidget(label_nota)

        # Botones
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _cargar_candidatos(self):
        """Carga todos los candidatos posibles."""
        self.selector._identificar_candidatos()

        self.list_candidatos.clear()
        for candidato in self.selector.candidatos:
            item = QListWidgetItem(candidato.descripcion)
            item.setData(Qt.ItemDataRole.UserRole, candidato)
            self.list_candidatos.addItem(item)

    def _seleccionar_automatico(self):
        """Realiza selección automática de redundantes."""
        try:
            redundantes = self.selector.seleccionar_automatico()

            # Limpiar selección actual
            self.list_seleccionados.clear()
            self.redundantes_seleccionados = []

            # Agregar redundantes seleccionados automáticamente
            for red in redundantes:
                self._agregar_redundante_directo(red)

            QMessageBox.information(
                self,
                "Selección Automática",
                f"Se seleccionaron automáticamente {len(redundantes)} redundantes:\n\n" +
                "\n".join(f"• {r.descripcion}" for r in redundantes)
            )

        except ValueError as e:
            QMessageBox.warning(
                self,
                "Error en Selección Automática",
                str(e)
            )

    def _agregar_redundante(self, item: QListWidgetItem):
        """Agrega un redundante desde la lista de candidatos."""
        gh = self.modelo.grado_hiperestaticidad

        if len(self.redundantes_seleccionados) >= gh:
            QMessageBox.warning(
                self,
                "Máximo alcanzado",
                f"Ya se seleccionaron {gh} redundantes (máximo permitido)"
            )
            return

        redundante = item.data(Qt.ItemDataRole.UserRole)
        self._agregar_redundante_directo(redundante)

    def _agregar_redundante_directo(self, redundante: Redundante):
        """Agrega un redundante directamente sin verificar límite."""
        # Verificar que no esté duplicado
        for red_sel in self.redundantes_seleccionados:
            if (red_sel.tipo == redundante.tipo and
                red_sel.nudo_id == redundante.nudo_id and
                red_sel.barra_id == redundante.barra_id):
                return  # Ya está seleccionado

        # Agregar a lista
        self.redundantes_seleccionados.append(redundante)

        # Actualizar UI
        item = QListWidgetItem(redundante.descripcion)
        item.setData(Qt.ItemDataRole.UserRole, redundante)
        self.list_seleccionados.addItem(item)

        # Actualizar contador
        gh = self.modelo.grado_hiperestaticidad
        self.group_seleccionados.setTitle(
            f"Redundantes Seleccionados ({len(self.redundantes_seleccionados)}/{gh})"
        )

    def _quitar_redundante(self, item: QListWidgetItem):
        """Quita un redundante de la selección."""
        redundante = item.data(Qt.ItemDataRole.UserRole)

        # Quitar de lista
        self.redundantes_seleccionados = [
            r for r in self.redundantes_seleccionados
            if not (r.tipo == redundante.tipo and
                   r.nudo_id == redundante.nudo_id and
                   r.barra_id == redundante.barra_id)
        ]

        # Actualizar UI
        row = self.list_seleccionados.row(item)
        self.list_seleccionados.takeItem(row)

        # Actualizar contador
        gh = self.modelo.grado_hiperestaticidad
        self.group_seleccionados.setTitle(
            f"Redundantes Seleccionados ({len(self.redundantes_seleccionados)}/{gh})"
        )

    def _on_accept(self):
        """Valida y acepta la selección."""
        gh = self.modelo.grado_hiperestaticidad

        if gh <= 0:
            self.accept()
            return

        if len(self.redundantes_seleccionados) != gh:
            QMessageBox.warning(
                self,
                "Selección Incompleta",
                f"Debe seleccionar exactamente {gh} redundantes.\n"
                f"Actualmente hay {len(self.redundantes_seleccionados)} seleccionados."
            )
            return

        # Asignar índices
        for i, red in enumerate(self.redundantes_seleccionados):
            red.indice = i + 1

        self.accept()

    def obtener_redundantes(self) -> List[Redundante]:
        """
        Retorna la lista de redundantes seleccionados.

        Returns:
            Lista de redundantes seleccionados (vacía si se canceló)
        """
        return self.redundantes_seleccionados if self.result() == QDialog.DialogCode.Accepted else []
