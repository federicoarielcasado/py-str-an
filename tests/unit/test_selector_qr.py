"""
Tests para la selección automática de redundantes por QR + spanning tree.

Cubre:
- Nivel 1 (QR): selección correcta de redundantes de apoyo
  · Viga continua GH=1 (Ry central como redundante)
  · Viga con 4 apoyos GH=2 (2 Ry redundantes)
  · Portico simple biempotrado GH=3 (3 redundantes de reaccion)
- Nivel 2 (spanning tree): deteccion de barras que cierran loops
- Fallback: la heuristica original sigue funcionando cuando se la llama
- Propiedad: el resultado QR es valido (no crea inestabilidad)
- Integracion: SelectorRedundantes.seleccionar_automatico() usa QR
"""

import pytest
import math

from src.domain.entities.material import Material
from src.domain.entities.seccion import SeccionRectangular
from src.domain.entities.vinculo import Empotramiento, ApoyoFijo, Rodillo
from src.domain.entities.carga import CargaDistribuida, CargaPuntualBarra
from src.domain.model.modelo_estructural import ModeloEstructural
from src.domain.analysis.redundantes import (
    Redundante,
    SelectorRedundantes,
    TipoRedundante,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def acero():
    return Material(nombre="Acero", E=200e6, alpha=1.2e-5)


@pytest.fixture
def seccion():
    return SeccionRectangular(nombre="30x50", b=0.30, _h=0.50)


# ---------------------------------------------------------------------------
# Helpers para construir modelos
# ---------------------------------------------------------------------------


def _viga_continua(acero, seccion, L1=4.0, L2=4.0, q=10.0):
    """
    Viga continua de 2 tramos sobre 3 apoyos (A=fijo, B=rodillo, C=rodillo).
    GH = 3*2 + 4 - 3*3 = 6 + 4 - 9 = 1.
    Redundante natural: Ry_B (apoyo central).
    """
    m = ModeloEstructural("VigaContinua")
    nA = m.agregar_nudo(0.0, 0.0, "A")
    nB = m.agregar_nudo(L1, 0.0, "B")
    nC = m.agregar_nudo(L1 + L2, 0.0, "C")
    b1 = m.agregar_barra(nA, nB, acero, seccion)
    b2 = m.agregar_barra(nB, nC, acero, seccion)
    m.asignar_vinculo(nA.id, ApoyoFijo())
    m.asignar_vinculo(nB.id, Rodillo())
    m.asignar_vinculo(nC.id, Rodillo())
    m.agregar_carga(CargaDistribuida(barra=b1, q1=q, q2=q, angulo=+90))
    m.agregar_carga(CargaDistribuida(barra=b2, q1=q, q2=q, angulo=+90))
    return m


def _viga_cuatro_apoyos(acero, seccion, L=3.0, q=10.0):
    """
    Viga de 3 tramos sobre 4 apoyos (A=fijo, B=C=D=rodillo).
    b=3, r=2+1+1+1=5, n=4: GH = 9 + 5 - 12 = 2.
    """
    m = ModeloEstructural("VigaCuatroApoyos")
    nA = m.agregar_nudo(0.0, 0.0, "A")
    nB = m.agregar_nudo(L, 0.0, "B")
    nC = m.agregar_nudo(2 * L, 0.0, "C")
    nD = m.agregar_nudo(3 * L, 0.0, "D")
    b1 = m.agregar_barra(nA, nB, acero, seccion)
    b2 = m.agregar_barra(nB, nC, acero, seccion)
    b3 = m.agregar_barra(nC, nD, acero, seccion)
    m.asignar_vinculo(nA.id, ApoyoFijo())
    m.asignar_vinculo(nB.id, Rodillo())
    m.asignar_vinculo(nC.id, Rodillo())
    m.asignar_vinculo(nD.id, Rodillo())
    m.agregar_carga(CargaDistribuida(barra=b1, q1=q, q2=q, angulo=+90))
    m.agregar_carga(CargaDistribuida(barra=b2, q1=q, q2=q, angulo=+90))
    m.agregar_carga(CargaDistribuida(barra=b3, q1=q, q2=q, angulo=+90))
    return m


def _portico_biempotrado(acero, seccion, L=4.0, H=3.0, P=50.0):
    """
    Portico plano: 2 columnas empotradas en base, viga horizontal en techo.
    Nudos: A (base izq, empotrado), B (techo izq), C (techo der), D (base der, empotrado).
    Barras: AB (columna izq), BC (viga), CD (columna der).
    GH = 3*3 + 6 - 3*4 = 9 + 6 - 12 = 3.
    """
    m = ModeloEstructural("Portico")
    nA = m.agregar_nudo(0.0, H, "A")    # base izq (Y+ abajo → base a y=H)
    nB = m.agregar_nudo(0.0, 0.0, "B")  # techo izq
    nC = m.agregar_nudo(L, 0.0, "C")   # techo der
    nD = m.agregar_nudo(L, H, "D")     # base der
    bAB = m.agregar_barra(nA, nB, acero, seccion)
    bBC = m.agregar_barra(nB, nC, acero, seccion)
    bCD = m.agregar_barra(nC, nD, acero, seccion)
    m.asignar_vinculo(nA.id, Empotramiento())
    m.asignar_vinculo(nD.id, Empotramiento())
    m.agregar_carga(CargaPuntualBarra(barra=bBC, P=P, a=L / 2.0, angulo=+90))
    return m


# ---------------------------------------------------------------------------
# Clase TestSelectorQRVigaContinua (GH=1)
# ---------------------------------------------------------------------------


class TestSelectorQRVigaContinua:
    """
    Viga continua 2 tramos (GH=1).
    El QR debe seleccionar exactamente 1 redundante de reaccion.
    """

    def test_gh_es_uno(self, acero, seccion):
        m = _viga_continua(acero, seccion)
        assert m.grado_hiperestaticidad == 1

    def test_selecciona_un_redundante(self, acero, seccion):
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert len(reds) == 1

    def test_redundante_es_reaccion(self, acero, seccion):
        """El unico redundante debe ser una reaccion de apoyo."""
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert reds[0].tipo in (
            TipoRedundante.REACCION_RX,
            TipoRedundante.REACCION_RY,
            TipoRedundante.REACCION_MZ,
        )

    def test_no_crea_inestabilidad(self, acero, seccion):
        """La seleccion QR no debe crear inestabilidad."""
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert not sel._crea_inestabilidad(reds)

    def test_indice_asignado(self, acero, seccion):
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert reds[0].indice == 1

    def test_redundante_no_es_Rx(self, acero, seccion):
        """Para viga horizontal pura, el QR no debe seleccionar Rx como redundante
        (la unica Rx disponible es necesaria para equilibrar cargas horizontales)."""
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert reds[0].tipo != TipoRedundante.REACCION_RX


# ---------------------------------------------------------------------------
# Clase TestSelectorQRVigaCuatroApoyos (GH=2)
# ---------------------------------------------------------------------------


class TestSelectorQRVigaCuatroApoyos:
    """
    Viga con 4 apoyos (GH=2).
    El QR debe seleccionar 2 redundantes de reaccion.
    """

    def test_gh_es_dos(self, acero, seccion):
        m = _viga_cuatro_apoyos(acero, seccion)
        assert m.grado_hiperestaticidad == 2

    def test_selecciona_dos_redundantes(self, acero, seccion):
        m = _viga_cuatro_apoyos(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert len(reds) == 2

    def test_redundantes_son_reacciones(self, acero, seccion):
        m = _viga_cuatro_apoyos(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        for r in reds:
            assert r.tipo in (
                TipoRedundante.REACCION_RX,
                TipoRedundante.REACCION_RY,
                TipoRedundante.REACCION_MZ,
            )

    def test_no_crea_inestabilidad(self, acero, seccion):
        m = _viga_cuatro_apoyos(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert not sel._crea_inestabilidad(reds)

    def test_indices_asignados(self, acero, seccion):
        m = _viga_cuatro_apoyos(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert reds[0].indice == 1
        assert reds[1].indice == 2

    def test_redundantes_en_nudos_distintos(self, acero, seccion):
        """Los 2 redundantes deben estar en nudos diferentes."""
        m = _viga_cuatro_apoyos(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        nudo_ids = {r.nudo_id for r in reds}
        assert len(nudo_ids) == 2


# ---------------------------------------------------------------------------
# Clase TestSelectorQRPortico (GH=3)
# ---------------------------------------------------------------------------


class TestSelectorQRPortico:
    """
    Portico plano biempotrado (GH=3).
    El QR debe seleccionar 3 redundantes, todos de reaccion.
    """

    def test_gh_es_tres(self, acero, seccion):
        m = _portico_biempotrado(acero, seccion)
        assert m.grado_hiperestaticidad == 3

    def test_selecciona_tres_redundantes(self, acero, seccion):
        m = _portico_biempotrado(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert len(reds) == 3

    def test_redundantes_son_reacciones(self, acero, seccion):
        m = _portico_biempotrado(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        for r in reds:
            assert r.tipo in (
                TipoRedundante.REACCION_RX,
                TipoRedundante.REACCION_RY,
                TipoRedundante.REACCION_MZ,
            )

    def test_no_crea_inestabilidad(self, acero, seccion):
        m = _portico_biempotrado(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        assert not sel._crea_inestabilidad(reds)

    def test_indices_correlativos(self, acero, seccion):
        m = _portico_biempotrado(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        indices = [r.indice for r in reds]
        assert indices == [1, 2, 3]

    def test_base_isostatica_contiene_tres_reacciones(self, acero, seccion):
        """Liberar 3 reacciones debe dejar exactamente 3 en la base."""
        m = _portico_biempotrado(acero, seccion)
        sel = SelectorRedundantes(m)
        reds = sel.seleccionar_automatico()
        total_r = m.num_reacciones
        liberadas = sum(
            1 for r in reds
            if r.tipo in (
                TipoRedundante.REACCION_RX,
                TipoRedundante.REACCION_RY,
                TipoRedundante.REACCION_MZ,
            )
        )
        assert total_r - liberadas == 3


# ---------------------------------------------------------------------------
# Clase TestSpanningTree
# ---------------------------------------------------------------------------


class TestSpanningTree:
    """
    Tests del metodo _seleccionar_internos_spanning_tree().
    """

    def test_cadena_sin_loops(self, acero, seccion):
        """
        Barras en cadena A-B-C: spanning tree cubre todas → 0 extra → lista vacia.
        """
        m = ModeloEstructural("Cadena")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(3.0, 0.0, "B")
        nC = m.agregar_nudo(6.0, 0.0, "C")
        m.agregar_barra(nA, nB, acero, seccion)
        m.agregar_barra(nB, nC, acero, seccion)
        m.asignar_vinculo(nA.id, Empotramiento())
        m.asignar_vinculo(nC.id, Rodillo())

        sel = SelectorRedundantes(m)
        internos = sel._seleccionar_internos_spanning_tree(5)
        # 2 barras, 3 nudos → spanning tree = 2 bordes → 0 extra
        assert internos == []

    def test_triangulo_un_loop(self, acero, seccion):
        """
        Triangulo A-B-C-A: 3 barras, 3 nudos → 1 barra extra → 1 redundante.
        """
        m = ModeloEstructural("Triangulo")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(3.0, 0.0, "B")
        nC = m.agregar_nudo(1.5, 2.5, "C")
        m.agregar_barra(nA, nB, acero, seccion)
        m.agregar_barra(nB, nC, acero, seccion)
        m.agregar_barra(nC, nA, acero, seccion)
        m.asignar_vinculo(nA.id, Empotramiento())

        sel = SelectorRedundantes(m)
        # 3 barras, 3 nudos → spanning tree tiene 2 bordes → 1 extra
        internos = sel._seleccionar_internos_spanning_tree(3)
        assert len(internos) == 1
        assert internos[0].tipo == TipoRedundante.MOMENTO_INTERNO

    def test_redundante_en_barra_valida(self, acero, seccion):
        """El redundante interno generado apunta a una barra del modelo."""
        m = ModeloEstructural("Triangulo2")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(4.0, 0.0, "B")
        nC = m.agregar_nudo(2.0, 3.0, "C")
        b1 = m.agregar_barra(nA, nB, acero, seccion)
        b2 = m.agregar_barra(nB, nC, acero, seccion)
        b3 = m.agregar_barra(nC, nA, acero, seccion)
        m.asignar_vinculo(nA.id, Empotramiento())

        sel = SelectorRedundantes(m)
        internos = sel._seleccionar_internos_spanning_tree(1)
        assert len(internos) == 1
        barra_ids = {b1.id, b2.id, b3.id}
        assert internos[0].barra_id in barra_ids

    def test_posicion_en_mitad_de_barra(self, acero, seccion):
        """La posicion del redundante interno debe estar en x = L/2."""
        m = ModeloEstructural("TrianguloPos")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(6.0, 0.0, "B")
        nC = m.agregar_nudo(3.0, 4.0, "C")
        m.agregar_barra(nA, nB, acero, seccion)
        m.agregar_barra(nB, nC, acero, seccion)
        m.agregar_barra(nC, nA, acero, seccion)
        m.asignar_vinculo(nA.id, Empotramiento())

        sel = SelectorRedundantes(m)
        internos = sel._seleccionar_internos_spanning_tree(1)
        barra = next(b for b in m.barras if b.id == internos[0].barra_id)
        assert abs(internos[0].posicion - barra.L / 2.0) < 1e-9

    def test_n_internos_cero(self, acero, seccion):
        """Si n_internos=0, retorna lista vacia sin error."""
        m = ModeloEstructural("Cadena0")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(3.0, 0.0, "B")
        m.agregar_barra(nA, nB, acero, seccion)
        m.asignar_vinculo(nA.id, Empotramiento())
        m.asignar_vinculo(nB.id, Rodillo())

        sel = SelectorRedundantes(m)
        assert sel._seleccionar_internos_spanning_tree(0) == []

    def test_limita_al_pedido(self, acero, seccion):
        """Si hay mas barras extra que n_internos, solo retorna n_internos."""
        m = ModeloEstructural("CuadradoBarras")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(3.0, 0.0, "B")
        nC = m.agregar_nudo(3.0, 3.0, "C")
        nD = m.agregar_nudo(0.0, 3.0, "D")
        m.agregar_barra(nA, nB, acero, seccion)
        m.agregar_barra(nB, nC, acero, seccion)
        m.agregar_barra(nC, nD, acero, seccion)
        m.agregar_barra(nD, nA, acero, seccion)
        m.agregar_barra(nA, nC, acero, seccion)  # diagonal extra
        m.asignar_vinculo(nA.id, Empotramiento())

        sel = SelectorRedundantes(m)
        internos = sel._seleccionar_internos_spanning_tree(2)
        assert len(internos) == 2

    def test_dos_loops_dos_redundantes(self, acero, seccion):
        """Cuadrado ABCD (4 nudos, 4 barras): 1 extra barra → 1 redundante."""
        m = ModeloEstructural("Cuadrado")
        nA = m.agregar_nudo(0.0, 0.0, "A")
        nB = m.agregar_nudo(4.0, 0.0, "B")
        nC = m.agregar_nudo(4.0, 4.0, "C")
        nD = m.agregar_nudo(0.0, 4.0, "D")
        m.agregar_barra(nA, nB, acero, seccion)
        m.agregar_barra(nB, nC, acero, seccion)
        m.agregar_barra(nC, nD, acero, seccion)
        m.agregar_barra(nD, nA, acero, seccion)
        m.asignar_vinculo(nA.id, Empotramiento())

        sel = SelectorRedundantes(m)
        # 4 barras, 4 nudos → spanning tree = 3 bordes → 1 extra
        internos = sel._seleccionar_internos_spanning_tree(5)
        assert len(internos) == 1


# ---------------------------------------------------------------------------
# Clase TestQRMatrizEquilibrio
# ---------------------------------------------------------------------------


class TestQRMatrizEquilibrio:
    """
    Verifica la logica interna del metodo _seleccionar_por_qr():
    la matriz A (3xr) captura correctamente el equilibrio.
    """

    def test_candidatos_identificados_antes_de_qr(self, acero, seccion):
        """_seleccionar_por_qr() requiere _identificar_candidatos() previo."""
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)
        sel._identificar_candidatos()
        reds = sel._seleccionar_por_qr(1)
        assert len(reds) == 1

    def test_qr_no_selecciona_rx_cuando_no_hay_Rx_extra(self, acero, seccion):
        """
        Viga horizontal: solo hay 1 Rx (en ApoyoFijo A) y es necesaria para
        equilibrio → el QR no debe marcarla como redundante.
        """
        m = _viga_continua(acero, seccion)  # ApoyoFijo(A) + Rodillo(B) + Rodillo(C)
        sel = SelectorRedundantes(m)
        sel._identificar_candidatos()
        reds = sel._seleccionar_por_qr(1)  # GH=1
        # El unico redundante no deberia ser Rx_A (es la unica Rx disponible)
        for r in reds:
            assert r.tipo != TipoRedundante.REACCION_RX

    def test_fallback_cuando_qr_falla(self, acero, seccion):
        """
        Si _seleccionar_por_qr lanza excepcion, seleccionar_automatico() debe
        usar la heuristica original sin error.
        """
        m = _viga_continua(acero, seccion)
        sel = SelectorRedundantes(m)

        # Simular fallo de QR parcheando el metodo en la instancia
        original_qr = sel._seleccionar_por_qr

        def qr_que_falla(n):
            raise RuntimeError("scipy simulado no disponible")

        sel._seleccionar_por_qr = qr_que_falla

        # seleccionar_automatico debe capturar la excepcion y usar heuristica
        reds = sel.seleccionar_automatico()
        assert len(reds) == 1  # GH=1

    def test_portico_qr_resultado_valido(self, acero, seccion):
        """El resultado QR para el portico pasa el check de inestabilidad."""
        m = _portico_biempotrado(acero, seccion)
        sel = SelectorRedundantes(m)
        sel._identificar_candidatos()
        reds = sel._seleccionar_por_qr(3)
        assert not sel._crea_inestabilidad(reds)

    def test_viga_cuatro_apoyos_qr_valido(self, acero, seccion):
        """El resultado QR para viga 4 apoyos pasa el check de inestabilidad."""
        m = _viga_cuatro_apoyos(acero, seccion)
        sel = SelectorRedundantes(m)
        sel._identificar_candidatos()
        reds = sel._seleccionar_por_qr(2)
        assert not sel._crea_inestabilidad(reds)


# ---------------------------------------------------------------------------
# Clase TestIntegracionQRConMF
# ---------------------------------------------------------------------------


class TestIntegracionQRConMF:
    """
    Tests de integracion: verifica que la seleccion QR produce redundantes
    que el motor MF puede utilizar exitosamente, y que los resultados
    coinciden con MD dentro de tolerancia.
    """

    def test_viga_continua_mf_exitoso(self, acero, seccion):
        """MF con redundante seleccionado por QR debe resolver exitosamente."""
        from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas

        m = _viga_continua(acero, seccion)
        motor = MotorMetodoFuerzas(m)
        res = motor.resolver()
        assert res.exitoso
        assert len(res.redundantes) == 1

    def test_viga_cuatro_apoyos_mf_exitoso(self, acero, seccion):
        """Viga 4 apoyos GH=2: MF resuelve con redundantes por QR."""
        from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas

        m = _viga_cuatro_apoyos(acero, seccion)
        motor = MotorMetodoFuerzas(m)
        res = motor.resolver()
        assert res.exitoso
        assert len(res.redundantes) == 2

    def test_portico_mf_exitoso(self, acero, seccion):
        """Portico GH=3: MF resuelve con 3 redundantes por QR."""
        from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas

        m = _portico_biempotrado(acero, seccion)
        motor = MotorMetodoFuerzas(m)
        res = motor.resolver()
        assert res.exitoso
        assert len(res.redundantes) == 3

    def test_mf_md_coinciden_viga_continua(self, acero, seccion):
        """MF y MD coinciden para viga continua GH=1."""
        from src.domain.analysis.motor_deformaciones import (
            analizar_estructura_deformaciones,
            comparar_resultados,
        )
        from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas

        m = _viga_continua(acero, seccion)
        r_md = analizar_estructura_deformaciones(m)
        r_mf = MotorMetodoFuerzas(m).resolver()

        assert r_md.exitoso
        assert r_mf.exitoso
        comp = comparar_resultados(r_mf, r_md, tol=1e-2)
        assert comp["coinciden"], (
            f"MF y MD no coinciden: max_diff={comp['max_diferencia']:.4e}"
        )

    def test_mf_md_coinciden_viga_cuatro_apoyos(self, acero, seccion):
        """MF y MD coinciden para viga con 4 apoyos GH=2."""
        from src.domain.analysis.motor_deformaciones import (
            analizar_estructura_deformaciones,
            comparar_resultados,
        )
        from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas

        m = _viga_cuatro_apoyos(acero, seccion)
        r_md = analizar_estructura_deformaciones(m)
        r_mf = MotorMetodoFuerzas(m).resolver()

        assert r_md.exitoso
        assert r_mf.exitoso
        comp = comparar_resultados(r_mf, r_md, tol=1e-2)
        assert comp["coinciden"], (
            f"MF y MD no coinciden: max_diff={comp['max_diferencia']:.4e}"
        )

    def test_mf_md_coinciden_portico(self, acero, seccion):
        """
        MF y MD coinciden para portico GH=3.

        Para porticos, el MF debe activar la deformacion axial para coincidir
        con el MD: ignorar el efecto axial introduce un error sistematico de
        ~0.16 kNm en los momentos de empotramiento (diferencia fisica real,
        no un bug de signo).
        """
        from src.domain.analysis.motor_deformaciones import (
            analizar_estructura_deformaciones,
            comparar_resultados,
        )
        from src.domain.analysis.motor_fuerzas import MotorMetodoFuerzas

        m = _portico_biempotrado(acero, seccion)
        r_md = analizar_estructura_deformaciones(m)
        # Incluir axial para que MF coincida con MD en porticos
        r_mf = MotorMetodoFuerzas(m, incluir_deformacion_axial=True).resolver()

        assert r_md.exitoso
        assert r_mf.exitoso
        comp = comparar_resultados(r_mf, r_md, tol=1e-2)
        assert comp["coinciden"], (
            f"MF y MD no coinciden: max_diff={comp['max_diferencia']:.4e}"
        )

    def test_solver_adaptativo_portico_pocos_intentos(self, acero, seccion):
        """
        Con QR, el solver adaptativo debe encontrar la solucion MF en pocos
        intentos (idealmente 1) en lugar de iterar todas las combinaciones.
        """
        from src.domain.analysis.solver_adaptativo import resolver_con_fallback

        m = _portico_biempotrado(acero, seccion)
        res = resolver_con_fallback(m, tol=1e-2)

        assert res.resultado_md is not None
        assert res.resultado_md.exitoso
        # Con QR determinístico, debe encontrar la solución inmediatamente
        if res.resultado_mf is not None:
            assert res.intentos_mf <= 5
