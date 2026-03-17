"""
Panel de resultados del análisis estructural.
"""

from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QLabel,
    QComboBox,
    QGroupBox,
    QSplitter,
    QHeaderView,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class ResultsPanel(QWidget):
    """
    Panel para mostrar los resultados del análisis estructural.

    Organizado en pestañas:
    - Resumen: información general del análisis
    - Reacciones: tabla de reacciones en vínculos
    - Esfuerzos: tabla de esfuerzos en barras
    - Log: registro detallado del análisis
    """

    # Señales
    barra_seleccionada = pyqtSignal(int)  # ID de barra para ver diagrama

    def __init__(self, parent=None):
        super().__init__(parent)

        self._resultado = None
        self._modelo = None   # Referencia al ModeloEstructural (para equilibrio)

        self._setup_ui()

    def _setup_ui(self):
        """Configura la interfaz del panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Pestañas de resultados
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Pestaña Resumen
        self._setup_tab_resumen()

        # Pestaña Reacciones
        self._setup_tab_reacciones()

        # Pestaña Esfuerzos
        self._setup_tab_esfuerzos()

        # Pestaña Log
        self._setup_tab_log()

    def _setup_tab_resumen(self):
        """Configura la pestaña de resumen."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Información del modelo
        group_modelo = QGroupBox("Modelo")
        model_layout = QVBoxLayout(group_modelo)

        self.label_gh = QLabel("Grado de hiperestaticidad: 0")
        self.label_redundantes = QLabel("Redundantes: -")
        self.label_num_red = QLabel("Número de redundantes: 0")

        model_layout.addWidget(self.label_gh)
        model_layout.addWidget(self.label_num_red)
        model_layout.addWidget(self.label_redundantes)
        model_layout.addStretch()

        layout.addWidget(group_modelo)

        # Información del análisis
        group_analisis = QGroupBox("Análisis")
        analysis_layout = QVBoxLayout(group_analisis)

        self.label_estado = QLabel("Estado: Sin analizar")
        self.label_estado.setStyleSheet("font-weight: bold;")
        self.label_condicionamiento = QLabel("Condicionamiento: -")
        self.label_residual = QLabel("Residual: -")

        analysis_layout.addWidget(self.label_estado)
        analysis_layout.addWidget(self.label_condicionamiento)
        analysis_layout.addWidget(self.label_residual)
        analysis_layout.addStretch()

        layout.addWidget(group_analisis)

        # Valores de redundantes
        group_redundantes = QGroupBox("Valores de Redundantes")
        red_layout = QVBoxLayout(group_redundantes)

        self.table_redundantes = QTableWidget()
        self.table_redundantes.setColumnCount(2)
        self.table_redundantes.setHorizontalHeaderLabels(["Redundante", "Valor"])
        self.table_redundantes.horizontalHeader().setStretchLastSection(True)
        red_layout.addWidget(self.table_redundantes)

        layout.addWidget(group_redundantes)

        self.tabs.addTab(widget, "Resumen")

    def _setup_tab_reacciones(self):
        """Configura la pestaña de reacciones."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.table_reacciones = QTableWidget()
        self.table_reacciones.setColumnCount(4)
        self.table_reacciones.setHorizontalHeaderLabels([
            "Nudo", "Rx (kN)", "Ry (kN)", "Mz (kNm)"
        ])
        header = self.table_reacciones.horizontalHeader()
        # Nudo: ancho fijo compacto; columnas de valores: repartidas equitativamente
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_reacciones.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        layout.addWidget(self.table_reacciones)

        # Verificación de equilibrio
        self.label_equilibrio = QLabel("Verificación de equilibrio: -")
        layout.addWidget(self.label_equilibrio)

        self.tabs.addTab(widget, "Reacciones")

    def _setup_tab_esfuerzos(self):
        """Configura la pestaña de esfuerzos."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Selector de barra
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Barra:"))
        self.combo_barra = QComboBox()
        self.combo_barra.currentIndexChanged.connect(self._on_barra_changed)
        selector_layout.addWidget(self.combo_barra)
        selector_layout.addStretch()
        layout.addLayout(selector_layout)

        # Tabla de esfuerzos en extremos
        self.table_esfuerzos = QTableWidget()
        self.table_esfuerzos.setColumnCount(7)
        self.table_esfuerzos.setHorizontalHeaderLabels([
            "Extremo", "Ni (kN)", "Vi (kN)", "Mi (kNm)",
            "Nj (kN)", "Vj (kN)", "Mj (kNm)"
        ])
        header = self.table_esfuerzos.horizontalHeader()
        # 7 columnas: Extremo fijo, esfuerzos con ancho mínimo legible
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(1, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.table_esfuerzos.setColumnWidth(col, 90)
        self.table_esfuerzos.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        layout.addWidget(self.table_esfuerzos)

        # Valores máximos
        group_max = QGroupBox("Valores Máximos")
        max_layout = QHBoxLayout(group_max)

        self.label_n_max = QLabel("N máx: -")
        self.label_v_max = QLabel("V máx: -")
        self.label_m_max = QLabel("M máx: -")

        max_layout.addWidget(self.label_n_max)
        max_layout.addWidget(self.label_v_max)
        max_layout.addWidget(self.label_m_max)

        layout.addWidget(group_max)

        self.tabs.addTab(widget, "Esfuerzos")

    def _setup_tab_log(self):
        """Configura la pestaña de log."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setFont(QFont("Consolas", 9))
        layout.addWidget(self.text_log)

        # Botón limpiar
        btn_limpiar = QPushButton("Limpiar log")
        btn_limpiar.clicked.connect(self.text_log.clear)
        layout.addWidget(btn_limpiar)

        self.tabs.addTab(widget, "Log")

    def mostrar_resultado(self, resultado, modelo=None):
        """
        Muestra los resultados del análisis.

        Args:
            resultado: Objeto ResultadoAnalisis del motor de fuerzas
            modelo: ModeloEstructural opcional (necesario para equilibrio correcto)
        """
        self._resultado = resultado
        self._modelo = modelo  # Guardar referencia para cálculo de equilibrio

        # Actualizar resumen
        self._actualizar_resumen(resultado)

        # Actualizar reacciones
        self._actualizar_reacciones(resultado)

        # Actualizar esfuerzos
        self._actualizar_esfuerzos(resultado)

        # Actualizar log
        self._actualizar_log(resultado)

    def _actualizar_resumen(self, resultado):
        """Actualiza la pestaña de resumen."""
        # Info del modelo
        self.label_gh.setText(f"Grado de hiperestaticidad: {resultado.grado_hiperestaticidad}")
        self.label_num_red.setText(f"Número de redundantes: {len(resultado.redundantes)}")

        # Nombres de redundantes
        if resultado.redundantes:
            nombres = [str(r) for r in resultado.redundantes]
            self.label_redundantes.setText(
                f"Redundantes: {', '.join(nombres[:3])}{'...' if len(nombres) > 3 else ''}"
            )
        else:
            self.label_redundantes.setText("Redundantes: (estructura isostática)")

        # Estado del análisis
        if resultado.exitoso:
            self.label_estado.setText("Estado: EXITOSO")
            self.label_estado.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.label_estado.setText("Estado: ERROR")
            self.label_estado.setStyleSheet("font-weight: bold; color: red;")

        # Info numérica
        self.label_condicionamiento.setText(
            f"Condicionamiento: {resultado.condicionamiento:.2e}"
        )
        self.label_residual.setText(f"Residual SECE: {resultado.residual_sece:.2e}")

        # Tabla de valores de redundantes
        if resultado.valores_X is not None and len(resultado.valores_X) > 0:
            self.table_redundantes.setRowCount(len(resultado.valores_X))
            for i, val in enumerate(resultado.valores_X):
                nombre = str(resultado.redundantes[i]) if i < len(resultado.redundantes) else f"X{i+1}"
                self.table_redundantes.setItem(i, 0, QTableWidgetItem(nombre))
                self.table_redundantes.setItem(i, 1, QTableWidgetItem(f"{val:.4f}"))
        else:
            self.table_redundantes.setRowCount(0)

    def _actualizar_reacciones(self, resultado):
        """Actualiza la pestaña de reacciones."""
        reacciones = resultado.reacciones_finales
        if not reacciones:
            self.table_reacciones.setRowCount(0)
            self.label_equilibrio.setText("Verificación de equilibrio: -")
            return

        self.table_reacciones.setRowCount(len(reacciones))

        # Suma de reacciones
        sum_rx = 0.0
        sum_ry = 0.0
        sum_mz_reac = 0.0

        for i, (nudo_id, (rx, ry, mz)) in enumerate(reacciones.items()):
            self.table_reacciones.setItem(i, 0, QTableWidgetItem(str(nudo_id)))
            self.table_reacciones.setItem(i, 1, QTableWidgetItem(f"{rx:.3f}"))
            self.table_reacciones.setItem(i, 2, QTableWidgetItem(f"{ry:.3f}"))
            self.table_reacciones.setItem(i, 3, QTableWidgetItem(f"{mz:.3f}"))

            sum_rx += rx
            sum_ry += ry
            sum_mz_reac += mz

        # Suma de cargas aplicadas (si tenemos referencia al modelo)
        sum_fx_cargas = 0.0
        sum_fy_cargas = 0.0
        sum_mz_cargas = 0.0

        if self._modelo is not None:
            from src.domain.entities.carga import (
                CargaPuntualNudo, CargaPuntualBarra, CargaDistribuida
            )
            for carga in self._modelo.cargas:
                if isinstance(carga, CargaPuntualNudo):
                    sum_fx_cargas += carga.Fx
                    sum_fy_cargas += carga.Fy
                    sum_mz_cargas += carga.Mz
                elif isinstance(carga, (CargaPuntualBarra, CargaDistribuida)):
                    # Las cargas en barra se transforman a fuerzas nodales
                    # equivalentes; su resultante global es la integral
                    # de la carga. Para la verificación rápida del panel,
                    # usamos la resultante de la carga.
                    try:
                        if isinstance(carga, CargaPuntualBarra):
                            import math
                            ang_global = carga.barra.angulo + math.radians(carga.angulo)
                            P = carga.P
                            sum_fx_cargas += P * math.cos(ang_global)
                            sum_fy_cargas += P * math.sin(ang_global)
                        elif isinstance(carga, CargaDistribuida):
                            # Resultante del trapecio
                            dx = carga.x2 - carga.x1
                            R = (carga.q1 + carga.q2) * dx / 2.0
                            import math
                            ang_global = carga.barra.angulo + math.radians(carga.angulo)
                            sum_fx_cargas += R * math.cos(ang_global)
                            sum_fy_cargas += R * math.sin(ang_global)
                    except Exception:
                        pass  # Si falla el cálculo, omitir esta carga

        # Equilibrio: ΣReacciones + ΣCargas = 0
        res_fx = abs(sum_rx + sum_fx_cargas)
        res_fy = abs(sum_ry + sum_fy_cargas)
        # Para Mz del equilibrio global usamos sólo reacciones+cargas puntuales nudo
        # (simplificado, ya que las cargas en barras generan momentos que dependen
        # del punto de referencia)
        tol = 1e-3

        if res_fx < tol and res_fy < tol:
            self.label_equilibrio.setText("Verificacion de equilibrio: OK")
            self.label_equilibrio.setStyleSheet("color: green;")
        else:
            self.label_equilibrio.setText(
                f"Equilibrio: ResidFx={res_fx:.4f} kN, ResidFy={res_fy:.4f} kN"
            )
            self.label_equilibrio.setStyleSheet("color: orange;")

    def _actualizar_esfuerzos(self, resultado):
        """Actualiza la pestaña de esfuerzos."""
        # Llenar combo de barras
        self.combo_barra.clear()

        if not resultado.diagramas_finales:
            return

        # Calcular máximos globales muestreando el vano completo
        n_max = 0.0
        v_max = 0.0
        m_max = 0.0

        N_PUNTOS = 21  # Puntos de muestreo por barra

        for barra_id, diagrama in resultado.diagramas_finales.items():
            self.combo_barra.addItem(f"Barra {barra_id}", barra_id)

            # Muestrear toda la barra (no sólo x=0)
            try:
                valores = diagrama.valores_en_puntos(N_PUNTOS)
                n_max_barra = float(max(abs(v) for v in valores["N"]))
                v_max_barra = float(max(abs(v) for v in valores["V"]))
                m_max_barra = float(max(abs(v) for v in valores["M"]))
            except Exception:
                # Fallback: evaluar en 21 puntos directamente
                import numpy as np
                xs = [i * diagrama.L / (N_PUNTOS - 1) for i in range(N_PUNTOS)]
                n_max_barra = max(abs(diagrama.N(x)) for x in xs)
                v_max_barra = max(abs(diagrama.V(x)) for x in xs)
                m_max_barra = max(abs(diagrama.M(x)) for x in xs)

            n_max = max(n_max, n_max_barra)
            v_max = max(v_max, v_max_barra)
            m_max = max(m_max, m_max_barra)

        self.label_n_max.setText(f"N max: {n_max:.2f} kN")
        self.label_v_max.setText(f"V max: {v_max:.2f} kN")
        self.label_m_max.setText(f"M max: {m_max:.2f} kNm")

    def _on_barra_changed(self, index):
        """Maneja el cambio de barra seleccionada."""
        if index < 0 or self._resultado is None:
            return

        barra_id = self.combo_barra.currentData()
        if barra_id is None:
            return

        diagrama = self._resultado.diagramas_finales.get(barra_id)
        if diagrama is None:
            return

        # Obtener valores en extremos
        Ni = diagrama.N(0)
        Vi = diagrama.V(0)
        Mi = diagrama.M(0)
        Nj = diagrama.N(diagrama.L)
        Vj = diagrama.V(diagrama.L)
        Mj = diagrama.M(diagrama.L)

        self.table_esfuerzos.setRowCount(1)
        self.table_esfuerzos.setItem(0, 0, QTableWidgetItem("i-j"))
        self.table_esfuerzos.setItem(0, 1, QTableWidgetItem(f"{Ni:.3f}"))
        self.table_esfuerzos.setItem(0, 2, QTableWidgetItem(f"{Vi:.3f}"))
        self.table_esfuerzos.setItem(0, 3, QTableWidgetItem(f"{Mi:.3f}"))
        self.table_esfuerzos.setItem(0, 4, QTableWidgetItem(f"{Nj:.3f}"))
        self.table_esfuerzos.setItem(0, 5, QTableWidgetItem(f"{Vj:.3f}"))
        self.table_esfuerzos.setItem(0, 6, QTableWidgetItem(f"{Mj:.3f}"))

        # Emitir señal para que el canvas muestre el diagrama
        self.barra_seleccionada.emit(barra_id)

    def _actualizar_log(self, resultado):
        """Actualiza la pestaña de log."""
        self.text_log.clear()

        # Información general
        self.text_log.append("=" * 60)
        self.text_log.append("ANÁLISIS ESTRUCTURAL - MÉTODO DE LAS FUERZAS")
        self.text_log.append("=" * 60)
        self.text_log.append("")

        self.text_log.append(f"Grado de hiperestaticidad (GH): {resultado.grado_hiperestaticidad}")
        self.text_log.append(f"Número de redundantes: {len(resultado.redundantes)}")
        self.text_log.append("")

        # Redundantes
        if resultado.redundantes:
            self.text_log.append("Redundantes seleccionados:")
            for i, red in enumerate(resultado.redundantes):
                if resultado.valores_X is not None and i < len(resultado.valores_X):
                    valor = resultado.valores_X[i]
                    self.text_log.append(f"  X{i+1} = {red}: {valor:.4f}")
                else:
                    self.text_log.append(f"  X{i+1} = {red}")
            self.text_log.append("")

        # Información numérica
        self.text_log.append(f"Condicionamiento de [F]: {resultado.condicionamiento:.2e}")
        self.text_log.append(f"Residual del SECE: {resultado.residual_sece:.2e}")
        self.text_log.append("")

        # Estado
        if resultado.exitoso:
            self.text_log.append("Estado: ANÁLISIS EXITOSO")
        else:
            self.text_log.append("Estado: ERROR EN ANÁLISIS")

        # Advertencias
        if resultado.advertencias:
            self.text_log.append("")
            self.text_log.append("Advertencias:")
            for adv in resultado.advertencias:
                self.text_log.append(f"  - {adv}")

        # Errores
        if resultado.errores:
            self.text_log.append("")
            self.text_log.append("Errores:")
            for err in resultado.errores:
                self.text_log.append(f"  - {err}")

        self.text_log.append("")
        self.text_log.append("=" * 60)

    def limpiar(self):
        """Limpia todos los resultados."""
        self._resultado = None
        self._modelo = None

        # Limpiar resumen
        self.label_gh.setText("Grado de hiperestaticidad: 0")
        self.label_num_red.setText("Número de redundantes: 0")
        self.label_redundantes.setText("Redundantes: -")
        self.label_estado.setText("Estado: Sin analizar")
        self.label_estado.setStyleSheet("font-weight: bold;")
        self.label_condicionamiento.setText("Condicionamiento: -")
        self.label_residual.setText("Residual: -")
        self.table_redundantes.setRowCount(0)

        # Limpiar reacciones
        self.table_reacciones.setRowCount(0)
        self.label_equilibrio.setText("Verificación de equilibrio: -")

        # Limpiar esfuerzos
        self.combo_barra.clear()
        self.table_esfuerzos.setRowCount(0)
        self.label_n_max.setText("N máx: -")
        self.label_v_max.setText("V máx: -")
        self.label_m_max.setText("M máx: -")

        # Limpiar log
        self.text_log.clear()
