import threading
import time

import cv2


class CameraStream:
    """Lê a webcam numa thread própria e guarda só o frame mais recente.

    Se a câmera estiver ocupada (OBS, navegador) ou cair, tenta reabrir
    sozinha a cada poucos segundos — sem precisar reiniciar o app.
    """

    RETRY_SECONDS = 2.0
    # DirectShow: 0,25 = manual, 0,75 = automática. A EXPOSIÇÃO em si vem em
    # log2(segundos) — -7 é 1/128 s.
    EXPOSICAO_MANUAL = 0.25
    EXPOSICAO_AUTO = 0.75

    def __init__(self, index: int, width: int, height: int, fps: int = 0,
                 foco: int = 0, exposicao: int | None = None):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps                 # 0 = aceita o padrão do driver
        self.foco = foco               # 0 = deixa o AUTOfoco decidir
        self.exposicao = exposicao     # None = deixa a exposição automática
        self.fps_negociado = 0.0       # o que a câmera respondeu de verdade
        self.foco_negociado = -1.0     # idem para o foco
        self.cap = None
        self._frame = None
        self._seq = 0                  # conta CAPTURAS, não leituras
        self._lock = threading.Lock()
        self._running = True
        self._warned = False
        self._pedir_fps = True         # cai para False se o pedido derrubar a câmera
        self._backend = 0              # índice em BACKENDS; anda se o atual não abrir
        self._backend_nome = ""
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # O BACKEND é o teto real da taxa, e isso custou meses sem ninguém ver.
    # Medido em 2026-09-17, na MESMA câmera (MX Brio), mesmo cabo, mesma luz,
    # mesmo MJPG 1920x1080 com `CAP_PROP_FPS=60` pedido nos dois:
    #
    #     DSHOW -> driver DIZ 60, entrega  30,0
    #     MSMF  -> driver diz 60, entrega  60,1
    #
    # O DirectShow aceita o `set()`, informa 60 em `get()` e entrega 30 — ou
    # seja, mente nas duas pontas. Não é luz, não é USB e não é a câmera: dá
    # 30,0 cravado até em 640x480, e forçar exposição de 1/128 s não passa de
    # 30 (só escurece). A queda para DSHOW fica porque ele abre mais rápido e
    # é o que este projeto usou desde sempre; o MSMF é que precisa provar.
    #
    # O ganho não é só o dobro de votos: a 60 fps a câmera é OBRIGADA a expor
    # em no máximo 1/60 s, o que corta pela metade o borrão de movimento — e o
    # borrão é a causa medida da perda de detecção (16x mais com a mão mexendo
    # do que com o leque parado, medido em 16/09 no mesmo dia e mesma câmera).
    # ...E MESMO ASSIM O MSMF FICA DE FORA, por um efeito colateral pior que
    # os 10 fps que ele ganha. Medido na mesma sessão: quando a abertura dele
    # estoura o tempo, a chamada continua PRESA numa thread que não dá para
    # matar — e essa thread SEGURA a câmera. O DirectShow então enumera só os
    # dispositivos livres, o índice 0 deixa de ser a Brio e passa a ser a
    # webcam do notebook: o app abre, não acusa erro nenhum e lê a câmera
    # ERRADA, em 720p. Foi o que aconteceu ao vivo em 2026-09-17.
    #
    # Para usar o MSMF é preciso sondá-lo num PROCESSO à parte, que possa ser
    # morto de verdade. Enquanto isso não existir, 30 fps confiáveis valem
    # mais que 40 com a câmera trocada — e a lista fica aqui, com a ordem
    # pronta, para quando a sonda em processo separado for feita.
    BACKENDS = (("DSHOW", cv2.CAP_DSHOW),)

    # O MSMF pode TRAVAR DENTRO do `VideoCapture()` — medido em 2026-09-17:
    # depois de o app morrer sem fechar a câmera, ele fica >20 s lá dentro
    # enquanto o DSHOW abre em 0,6 s. Sem limite de tempo isso deixa o app
    # CEGO e calado, que é pior do que os 30 fps do DSHOW. Não dá para
    # interromper a chamada, então ela roda numa thread descartável: se
    # estourar, o backend é abandonado e a vez passa para o seguinte.
    ABRE_TIMEOUT = 8.0

    def _abre_backend(self, backend, pedir_fps):
        """Abre num thread à parte e devolve None se estourar o tempo."""
        caixa = {}

        def trabalho():
            cap = cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                cap.release()
                return
            # MJPG destrava fps em resoluções altas (YUY2 satura o USB em 1080p+)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if pedir_fps and self.fps:
                cap.set(cv2.CAP_PROP_FPS, self.fps)
            # O AUTOFOCO MIRA O QUE PREENCHE O QUADRO, e com a câmera sobre a
            # mesa isso é o FELTRO — não o leque, que fica mais perto. Medido
            # em 2026-09-18, no estúdio: a gravação saiu com o foco parado em
            # 14, nitidez 2.679 com o leque PARADO, contra ~4.000 no foco certo
            # (~95, platô 85-105). Não é exposição: brilho 185 dentro do índice
            # e 0,7% de pixel estourado. Reaferir com `scripts/afina_foco.py`
            # sempre que a câmera ou a distância da mesa mudarem.
            if self.foco:
                cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                cap.set(cv2.CAP_PROP_FOCUS, self.foco)
            # EXPOSIÇÃO CURTA CONGELA O MOVIMENTO, e o movimento é o que sobra
            # depois do foco: medido em 18/09, perda de 1,55% com o leque
            # parado contra 17,69% com a mão mexendo. O sentinela é None e não
            # 0 de propósito — nesta escala 0 vale 1 SEGUNDO de exposição, que
            # é o extremo oposto do que se quer.
            if self.exposicao is not None:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, self.EXPOSICAO_MANUAL)
                cap.set(cv2.CAP_PROP_EXPOSURE, self.exposicao)
            caixa["cap"] = cap

        t = threading.Thread(target=trabalho, daemon=True)
        t.start()
        t.join(self.ABRE_TIMEOUT)
        if t.is_alive():
            return None                # a thread fica presa; é descartável
        return caixa.get("cap")

    def _open(self, pedir_fps=True):
        for nome, backend in self.BACKENDS[self._backend:]:
            cap = self._abre_backend(backend, pedir_fps)
            if cap is not None:
                self._backend_nome = nome
                return cap
            print(f"câmera {self.index}: {nome} não abriu em "
                  f"{self.ABRE_TIMEOUT:g}s — tentando o próximo", flush=True)
            self._backend += 1
        self._backend = 0              # recomeça a busca na próxima tentativa
        return None
        # A TAXA DA CÂMERA É O TETO DO PIPELINE, e até 2026-09-14 ninguém a
        # pedia: o DirectShow entregava o padrão (30) enquanto o laço girava a
        # 29-48, ou seja até um terço do trabalho da GPU era re-inferir a MESMA
        # imagem (medido nas dez gravações: 1-37% de frames repetidos, e a taxa
        # DISTINTA batendo em 28-32 em todas). Como todo parâmetro é contado em
        # QUADROS, dobrar a taxa distinta faz `lock_frames=20` valer 0,33 s em
        # vez de 0,67 s — é o ganho mais barato que existe, e não toca o modelo.


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
        foco = ""
        if self.exposicao is not None:
            foco += (f" | exposição 1/{2 ** -self.exposicao:g}s"
                     if self.exposicao < 0 else
                     f" | exposição {self.exposicao}")
        if self.foco:
            self.foco_negociado = float(self.cap.get(cv2.CAP_PROP_FOCUS))
            foco = (f" | foco FIXO {self.foco_negociado:g}"
                    f" (pedimos {self.foco})")
        print(f"câmera {self.index}: aberta {w}x{h} @ "
              f"{self.fps_negociado:g} fps{pedido} "
              f"[{self._backend_nome}]{foco}", flush=True)
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
                elif primeiro_read and self._backend + 1 < len(self.BACKENDS):
                    # abriu e não entregou imagem nem sem o pedido de taxa: o
                    # suspeito passa a ser o BACKEND. Cair para o seguinte é o
                    # que impede o MSMF de deixar o app cego numa máquina onde
                    # ele não funcione — e isso não dá para testar sem câmera.
                    self._backend += 1
                    self._pedir_fps = True
                    print(f"câmera {self.index}: {self._backend_nome} não "
                          f"entregou imagem — caindo para "
                          f"{self.BACKENDS[self._backend][0]}", flush=True)
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
