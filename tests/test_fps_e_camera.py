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

def test_frame_repetido_NAO_paga_inferencia_de_novo(monkeypatch):
    """A inferência é determinística: re-inferir a mesma imagem dá o mesmo
    resultado e queima 19-22 ms de GPU por volta.

    Medido em 2026-09-03: 1-37% das voltas eram repetição, conforme a gravação.
    O teste fixa as duas metades do contrato — a inferência não repete E o
    pipeline continua recebendo a mesma detecção, porque todo parâmetro é
    contado em VOLTAS DO LAÇO.
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

    assert len(vistos) == 4, "a volta repetida continua alimentando o pipeline"
    assert detector.chamadas == 2, "só 2 capturas distintas = só 2 inferências"
    assert all(d is vistos[0] for d in vistos[:3]), \
        "a volta repetida tem de reaproveitar a MESMA detecção"
