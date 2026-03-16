"""
Genera 3 capturas representativas del proyecto PyANES-MF.
Las tres capturas corresponden al mismo portico biempotrado (GH=3):

  captura_1_geometria.png   -- Geometria + cargas aplicadas
  captura_2_diagramas.png   -- Diagramas de esfuerzos N, V, M
  captura_3_deformada.png   -- Deformada elastica + tabla de reacciones
"""

import sys
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from src.data.proyecto_serializer import cargar_proyecto
from src.domain.analysis import resolver_con_fallback
from src.ui.visualization.geometria import graficar_estructura_con_cargas
from src.ui.visualization.diagramas import graficar_diagramas_combinados
from src.ui.visualization.deformada import graficar_deformada

# ─── Cargar modelo y resolver ─────────────────────────────────────────────────
print("Cargando portico biempotrado...")
modelo = cargar_proyecto("portico_ejemplo.json")

print("Resolviendo...")
res_adapt = resolver_con_fallback(modelo, tol=1e-2, verbose=False)
resultado = res_adapt.mejor_resultado
metodo = res_adapt.metodo_exitoso.upper() if hasattr(res_adapt, "metodo_exitoso") else "MD"
print(f"  Metodo: {metodo}")

GH = modelo.grado_hiperestaticidad
titulo_base = f"{modelo.nombre}  (GH = {GH}, metodo: {metodo})"

# ── Captura 1: Geometria + cargas ─────────────────────────────────────────────
fig1, ax1 = graficar_estructura_con_cargas(modelo=modelo, titulo=modelo.nombre)
fig1.set_size_inches(10, 7)
fig1.patch.set_facecolor("#FAFAFA")
ax1.set_facecolor("#FAFAFA")
ax1.set_title(
    f"{modelo.nombre}  --  Geometria y Cargas  (GH = {GH})",
    fontsize=14, fontweight="bold", pad=14,
)
fig1.savefig("captura_1_geometria.png", dpi=150, bbox_inches="tight",
             facecolor=fig1.get_facecolor())
plt.close(fig1)
print("OK  captura_1_geometria.png")

# ── Captura 2: Diagramas N, V, M ──────────────────────────────────────────────
fig2, axes2 = graficar_diagramas_combinados(
    modelo=modelo,
    resultado=resultado,
    titulo_general=f"{modelo.nombre}  --  Diagramas de Esfuerzos  (metodo: {metodo})",
    mostrar_valores=True,
)
fig2.set_size_inches(14, 8)
fig2.patch.set_facecolor("#FAFAFA")
axs2 = axes2 if hasattr(axes2, "__iter__") else [axes2]
for ax in axs2:
    ax.set_facecolor("#FAFAFA")

fig2.savefig("captura_2_diagramas.png", dpi=150, bbox_inches="tight",
             facecolor=fig2.get_facecolor())
plt.close(fig2)
print("OK  captura_2_diagramas.png")

# ── Captura 3: Deformada elastica + tabla de reacciones ───────────────────────
fig3, ax3 = graficar_deformada(
    modelo, resultado,
    titulo=f"{modelo.nombre}  --  Deformada Elastica  (metodo: {metodo})",
)
fig3.set_size_inches(10, 7)
fig3.patch.set_facecolor("#FAFAFA")
ax3.set_facecolor("#FAFAFA")

# Tabla de reacciones como anotacion en esquina superior derecha
nudos_vinculo = [n for n in sorted(modelo.nudos, key=lambda n: n.id) if n.vinculo is not None]
lineas = ["Reacciones en vinculos", ""]
for n in nudos_vinculo:
    Rx, Ry, Mz = resultado.obtener_reaccion(n.id)
    # Y+ hacia abajo => Ry negativo = reaccion hacia arriba
    lineas.append(f"N{n.id} ({type(n.vinculo).__name__})")
    lineas.append(f"  Rx = {Rx:+.2f} kN")
    lineas.append(f"  Ry = {-Ry:+.2f} kN  [+arriba]")
    lineas.append(f"  Mz = {Mz:+.2f} kNm")
    lineas.append("")

# verificacion de equilibrio
SumRx = sum(resultado.obtener_reaccion(n.id)[0] for n in nudos_vinculo)
SumRy = sum(resultado.obtener_reaccion(n.id)[1] for n in nudos_vinculo)
from src.domain.entities.carga import CargaPuntualNudo
SumFx_ext = sum(getattr(c, "Fx", 0.0) for c in modelo.cargas if isinstance(c, CargaPuntualNudo))
SumFy_ext = sum(getattr(c, "Fy", 0.0) for c in modelo.cargas if isinstance(c, CargaPuntualNudo))
ok_x = abs(SumRx + SumFx_ext) < 1e-3
ok_y = abs(SumRy + SumFy_ext + 60.0) < 1e-1  # 60 kN de la carga distribuida

lineas.append("Verificacion equilibrio")
lineas.append(f"  SFx = {SumRx + SumFx_ext:+.2e}  {'OK' if ok_x else 'FALLA'}")
lineas.append(f"  SFy = {SumRy + SumFy_ext + 60.0:+.2e}  {'OK' if ok_y else 'FALLA'}")

textbox = "\n".join(lineas)
ax3.text(
    0.97, 0.97, textbox,
    transform=ax3.transAxes,
    fontsize=8, verticalalignment="top", horizontalalignment="right",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor="#555", alpha=0.88),
    fontfamily="monospace",
)

fig3.savefig("captura_3_deformada.png", dpi=150, bbox_inches="tight",
             facecolor=fig3.get_facecolor())
plt.close(fig3)
print("OK  captura_3_deformada.png")

print("\n--- Listo ---")
print("  captura_1_geometria.png  -- Geometria + cargas")
print("  captura_2_diagramas.png  -- Diagramas N, V, M")
print("  captura_3_deformada.png  -- Deformada + reacciones")
