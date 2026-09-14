import threading
import time

import cv2


class CameraStream:
    """Lê a webcam numa thread própria e guarda só o frame mais recente.

    Se a câmera estiver ocupada (OBS, navegador) ou cair, tenta reabrir
    sozinha a cada poucos segundos — sem precisar reiniciar o app.
    """

    RETRY_SECONDS = 2.0

    def __init__(self, index: int, width: int, height: int, fps: int = 0):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps                 # 0 = aceita o padrão do driver
        self.fps_negociado = 0.0       # o que a câmera respondeu de verdade
        self.cap = None
        self._frame = None
        self._seq = 0                  # conta CAPTURAS, não leituras
        self._lock = threading.Lock()
        self._running = True
        self._warned = False
        self._pedir_fps = True         # cai para False se o pedido derrubar a câmera
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _open(self, pedir_fps=True):
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)  # DSHOW: abre rápido no Windows
        if not cap.isOpened():
            cap.release()
            return None
        # MJPG destrava fps em resoluções altas (YUY2 satura o USB em 1080p+)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # A TAXA DA CÂMERA É O TETO DO PIPELINE, e até 2026-09-14 ninguém a
        # pedia: o DirectShow entregava o padrão (30) enquanto o laço girava a
        # 29-48, ou seja até um terço do trabalho da GPU era re-inferir a MESMA
        # imagem (medido nas dez gravações: 1-37% de frames repetidos, e a taxa
        # DISTINTA batendo em 28-32 em todas). Como todo parâmetro é contado em
        # QUADROS, dobrar a taxa distinta faz `lock_frames=20` valer 0,33 s em
        # vez de 0,67 s — é o ganho mais barato que existe, e não toca o modelo.
        if pedir_fps and self.fps:
            cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def _anuncia(self):
        """Diz o que a câmera NEGOCIOU, não o que pedimos.

        O driver aceita `set()` em silêncio e entrega outra coisa. Sem esta
        linha, "a câmera faz 1080p60" fica sendo suposição — e foi assim que a
        taxa real passou meses sem ser conhecida.
        """
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps_negociado = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        pedido = f" (pedimos {self.fps})" if self.fps else ""
        print(f"câmera {self.index}: aberta {w}x{h} @ "
              f"{self.fps_negociado:g} fps{pedido}", flush=True)
        if self.fps and self.fps_negociado and self.fps_negociado < self.fps:
            print(f"câmera {self.index}: a câmera NÃO deu {self.fps} fps — o "
                  f"teto do pipeline continua em {self.fps_negociado:g}",
                  flush=True)

    def _loop(self):
        primeiro_read = False
        while self._running:
            if self.cap is None:
                self.cap = self._open(pedir_fps=self._pedir_fps)
                if self.cap is None:
                    if not self._warned:
                        print(f"câmera {self.index}: ocupada/indisponível — "
                              f"tentando de novo a cada {self.RETRY_SECONDS}s")
                        self._warned = True
                    time.sleep(self.RETRY_SECONDS)
                    continue
                self._anuncia()
                self._warned = False
                primeiro_read = True
            ok, frame = self.cap.read()
            if ok:
                primeiro_read = False
                with self._lock:
                    self._frame = frame
                    self._seq += 1
            else:
                # A câmera abriu e não entregou o PRIMEIRO frame: o pedido de
                # taxa é o suspeito, porque é a única coisa nova que mandamos.
                # Desligá-lo e reabrir é o que impede um modo não suportado de
                # derrubar o app — e não dá para testar isto sem a câmera na
                # mesa, então a guarda existe justamente por isso.
                if primeiro_read and self._pedir_fps and self.fps:
                    print(f"câmera {self.index}: não entregou frame com "
                          f"{self.fps} fps pedidos — reabrindo sem o pedido",
                          flush=True)
                    self._pedir_fps = False
                # câmera caiu (cabo, outro app tomou): larga e tenta reabrir
                self.cap.release()
                self.cap = None
                with self._lock:
                    self._frame = None

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def read_seq(self):
        """(frame, seq) — `seq` só muda quando a câmera entregou imagem NOVA.

        O laço de visão gira mais rápido que a câmera e `read()` devolve sempre
        o último frame guardado, então sem o contador não há como distinguir
        "processei 48 imagens" de "processei 30 imagens e 18 repetições". Era o
        que fazia o `FpsMeter` publicar 47,8 onde a câmera entregava 30,2.
        """
        with self._lock:
            if self._frame is None:
                return None, self._seq
            return self._frame.copy(), self._seq

    def stop(self):
        self._running = False
        self._thread.join(timeout=2)
        if self.cap is not None:
            self.cap.release()
