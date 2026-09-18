"""A taxa que o app publica, e a taxa que a câmera realmente entrega.

Medido em 2026-09-03 nas dez gravações: o `FpsMeter` publicava 47,8 onde a
câmera entregava 30,2 imagens distintas — o `CameraStream` guarda o frame mais
recente e o laço lê o que estiver lá, então quando o laço corre mais que a
câmera ele re-infere a MESMA imagem. Por meses esse número foi lido como se
fosse taxa de imagens, e foi com ele que os contadores em FRAMES do `config.py`
foram dimensionados.
"""
import threading
import time

from app.capture import CameraStream
from app.main import FpsMeter


class Relogio:
    """Tempo controlado: sem isso o teste mediria a máquina, não o contador."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_a_taxa_do_LACO_e_a_da_CAMERA_sao_publicadas_separadas():
    rel = Relogio()
    fps = FpsMeter(intervalo=5.0, agora=rel)
    for i in range(10):          # 10 voltas do laço...
        rel.t += 0.5
        fps.tick(novo=(i % 2 == 0))   # ...e só 5 imagens novas
    assert fps.fps == 2.0
    assert fps.fps_distintos == 1.0


def test_frame_REPETIDO_nao_conta_como_imagem_nova():
    """Guarda contra ignorar o `novo` e publicar duas vezes a taxa do laço.

    É o defeito que existia: as duas taxas saíam iguais e a de cima era tomada
    como quantidade de imagem vista por segundo.
    """
    rel = Relogio()
    fps = FpsMeter(intervalo=1.0, agora=rel)
    for _ in range(9):
        fps.tick(novo=False)
    rel.t += 1.0
    fps.tick(novo=True)
    assert fps.fps == 10.0
    assert fps.fps_distintos == 1.0


def test_a_janela_recomeca_zerada_nas_duas_contagens():
    rel = Relogio()
    fps = FpsMeter(intervalo=1.0, agora=rel)
    rel.t += 1.0
    fps.tick(novo=True)               # fecha a primeira janela
    for _ in range(3):
        fps.tick(novo=False)
    rel.t += 1.0
    fps.tick(novo=True)
    assert fps.fps == 4.0             # 4 voltas na janela nova, não 5
    assert fps.fps_distintos == 1.0


# --------------------------------------------------------------------------
# CameraStream: o contador de capturas e a guarda do pedido de FPS.

class CapFalso:
    """VideoCapture de mentira. `falha_com_fps` reproduz o modo não suportado."""

    def __init__(self, falha_com_fps=False):
        self.falha_com_fps = falha_com_fps
        self.props = {}
        self.aberta = True
        self.lida = 0

    def isOpened(self):
        return True

    def set(self, prop, valor):
        self.props[prop] = valor
        return True

    def get(self, prop):
        return self.props.get(prop, 0)

    def read(self):
        if self.falha_com_fps and self.props.get("fps"):
            return False, None
        self.lida += 1
        return True, [[self.lida]]

    def release(self):
        self.aberta = False


class Cv2Falso:
    CAP_DSHOW = 0
    CAP_PROP_FOURCC = "fourcc"
    CAP_PROP_FRAME_WIDTH = "w"
    CAP_PROP_FRAME_HEIGHT = "h"
    CAP_PROP_FPS = "fps"
    CAP_PROP_AUTOFOCUS = "autofoco"
    CAP_PROP_FOCUS = "foco"
    CAP_PROP_AUTO_EXPOSURE = "autoexp"
    CAP_PROP_EXPOSURE = "exp"

    def __init__(self, falha_com_fps=False):
        self.falha_com_fps = falha_com_fps
        self.abertas = []

    def VideoWriter_fourcc(self, *a):
        return 0

    def VideoCapture(self, index, api):
        cap = CapFalso(self.falha_com_fps)
        self.abertas.append(cap)
        return cap


def _espera(condicao, limite=2.0):
    fim = time.time() + limite
    while time.time() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return False


def _camera(monkeypatch, cv2_falso, **kw):
    monkeypatch.setattr("app.capture.cv2", cv2_falso)
    cam = CameraStream(0, 1920, 1080, **kw)
    return cam


def test_seq_so_avanca_quando_a_camera_entrega_imagem_nova(monkeypatch):
    cam = _camera(monkeypatch, Cv2Falso(), fps=60)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        _, a = cam.read_seq()
        _, b = cam.read_seq()          # duas leituras seguidas do MESMO frame
        assert a == b, "ler duas vezes não pode contar como imagem nova"
        assert _espera(lambda: cam.read_seq()[1] > a)
    finally:
        cam.stop()


def test_pedido_de_fps_nao_suportado_NAO_derruba_a_camera(monkeypatch):
    """A guarda que não dá para testar com a câmera na mesa.

    Pedir 60 fps é o ganho mais barato do projeto, mas pedir não é obter — e um
    modo não suportado pode fazer a câmera abrir e não entregar frame nenhum.
    Sem esta guarda, ligar o `cam_fps` deixaria o app cego.
    """
    cv2_falso = Cv2Falso(falha_com_fps=True)
    cam = _camera(monkeypatch, cv2_falso, fps=60)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None), \
            "a câmera tinha de voltar sozinha para o padrão do driver"
        assert cam._pedir_fps is False
        assert cv2_falso.abertas[0].props.get("fps") == 60
        assert cv2_falso.abertas[-1].props.get("fps") in (None, 0)
    finally:
        cam.stop()


def test_foco_FIXO_desliga_o_autofoco_e_fixa_o_valor(monkeypatch):
    """O autofoco mira o que PREENCHE o quadro — o feltro, não o leque.

    Medido em 2026-09-18 no estúdio: a gravação saiu com o foco parado em 14 e
    nitidez 2.679 no leque PARADO, contra ~4.000 no foco certo. Não adianta
    fixar o valor sem desligar o automático: o driver sobrescreve na volta
    seguinte.
    """
    cv2_falso = Cv2Falso()
    cam = _camera(monkeypatch, cv2_falso, fps=60, foco=95)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        props = cv2_falso.abertas[0].props
        assert props.get("autofoco") == 0, "fixar o foco sem desligar o auto não segura"
        assert props.get("foco") == 95
    finally:
        cam.stop()


def test_sem_cam_foco_o_AUTOfoco_fica_INTACTO(monkeypatch):
    """`cam_foco = 0` não pode virar "foco no infinito".

    É o lado que uma implementação ingênua erra em silêncio: mandando o valor
    sempre, o 0 do padrão desligaria o automático e travaria a lente no
    extremo — onde a nitidez medida é 501, a pior de toda a varredura.
    """
    cv2_falso = Cv2Falso()
    cam = _camera(monkeypatch, cv2_falso, fps=60, foco=0)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        props = cv2_falso.abertas[0].props
        assert "autofoco" not in props and "foco" not in props
    finally:
        cam.stop()


def test_exposicao_FIXA_sai_do_automatico(monkeypatch):
    """Exposição curta congela o movimento, que é o que sobra depois do foco.

    Medido em 18/09: perda de 1,55% com o leque parado contra 17,69% com a mão
    mexendo. Mandar o tempo sem tirar a câmera do automático não segura nada —
    o driver recalcula no quadro seguinte.
    """
    cv2_falso = Cv2Falso()
    cam = _camera(monkeypatch, cv2_falso, fps=60, exposicao=-7)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        props = cv2_falso.abertas[0].props
        assert props.get("autoexp") == CameraStream.EXPOSICAO_MANUAL
        assert props.get("exp") == -7
    finally:
        cam.stop()


def test_exposicao_None_NAO_vira_um_SEGUNDO_de_exposicao(monkeypatch):
    """O sentinela é None, não 0 — e a diferença é o dia e a noite.

    Nesta escala o valor é log2(segundos), então 0 vale 1 SEGUNDO: um sentinela
    0 tratado como valor daria a exposição mais LONGA possível, o extremo
    oposto do que a medição pediu, e ainda por cima em silêncio.
    """
    cv2_falso = Cv2Falso()
    cam = _camera(monkeypatch, cv2_falso, fps=60, exposicao=None)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        props = cv2_falso.abertas[0].props
        assert "autoexp" not in props and "exp" not in props
    finally:
        cam.stop()


def test_sem_cam_fps_nada_e_pedido_ao_driver(monkeypatch):
    cv2_falso = Cv2Falso()
    cam = _camera(monkeypatch, cv2_falso, fps=0)
    try:
        assert _espera(lambda: cam.read_seq()[0] is not None)
        assert cv2_falso.abertas[0].props.get("fps") in (None, 0)
    finally:
        cam.stop()


# --------------------------------------------------------------------------
# vision_loop: a volta repetida não paga inferência de novo.

def test_imagem_repetida_NAO_conta_volta_nem_paga_inferencia(monkeypatch):
    """Só imagem NOVA avança o pipeline.

    Até 2026-09-16 a volta repetida pulava a inferência mas continuava
    alimentando o `process_frame` — e, sem custo nenhum, o laço disparava a
    280-570 voltas/s sempre que a câmera ficava mais lenta que a GPU. Como todo
    parâmetro é contado em VOLTAS, `lock_frames=20` passava a valer menos de
    0,1 s e a tela lia o vulto do leque antes de ele parar.
    """
    import numpy as np

    from app.hand_reader import FanReader
    from app.main import vision_loop
    from app.stable_hand import StableHand
    from app.tracker import GameTracker

    quadro = np.zeros((20, 20, 3), dtype=np.uint8)

    class CamFalsa:
        """Entrega a MESMA captura 3 vezes, depois uma nova."""

        def __init__(self):
            self.n = 0

        def read_seq(self):
            self.n += 1
            return quadro, 7 if self.n <= 3 else 8

    class DetectorFalso:
        def __init__(self):
            self.chamadas = 0

        def detect(self, frame):
            self.chamadas += 1
            return []

    class RodaNVezes:
        def __init__(self, n):
            self.n = n

        def is_set(self):
            self.n -= 1
            return self.n >= 0

    vistos = []
    monkeypatch.setattr("app.main.process_frame",
                        lambda dets, *a, **kw: vistos.append(dets))
    detector = DetectorFalso()
    vision_loop({"hand": CamFalsa()}, detector, GameTracker(), {},
                RodaNVezes(4), FanReader(), StableHand())

    assert detector.chamadas == 2, "só 2 capturas distintas = só 2 inferências"
    assert len(vistos) == 2, \
        "imagem repetida não pode contar volta: é ela que dá tempo aos parâmetros"
