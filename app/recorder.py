"""Gravação da partida — o que torna a medição de volume possível.

A meta de aceite (≥95% dos descartes, ≥90% das compras) só se mede numa partida
inteira. Sem gravação, cada tentativa de conserto custa OUTRA partida: o único
rastro de um erro no minuto 12 era o `print` do `log_lock` no stdout, que some
com o terminal e não permite repetir o experimento.

Grava três coisas, e cada uma habilita um nível diferente de experimento:

- `sessao.jsonl` — as detecções **brutas** de cada frame, antes do
  `hand_instances`. Permite repetir o pipeline inteiro offline (`scripts/replay.py`),
  em segundos e sem câmera, mexendo em qualquer parâmetro — inclusive no
  `MERGE_FACTOR`, que já teria sido consumido se gravássemos as detecções
  deduplicadas.
- `mao.avi` — o vídeo cru 1080p da câmera da mão. É o que permite rodar um
  MODELO NOVO contra a mesma partida; o JSONL sozinho não permite, porque as
  detecções que ele guarda já SÃO a saída do modelo velho.
- `meta.json` — a config vigente. Sem ela não se sabe quais parâmetros
  produziram aqueles eventos, e a gravação vira anedota em vez de medição.

O vídeo é escrito numa thread própria com fila LIMITADA e escrita BLOQUEANTE.
Bloquear é de propósito: se o disco não acompanhar, o FPS cai à vista (e fica
registrado nos timestamps) em vez de o vídeo dessincronizar do JSONL em
silêncio, o que estragaria a revisão frame a frame sem dar nenhum sinal.
"""

import json
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path

import cv2


class SessionRecorder:
    """Grava uma partida em `<base_dir>/<AAAAMMDD-HHMMSS>/`."""

    def __init__(self, base_dir="gravacoes", gravar_video=True,
                 fps_nominal=30, config=None, nome=None):
        stamp = nome or time.strftime("%Y%m%d-%H%M%S")
        self.dir = Path(base_dir) / stamp
        self.dir.mkdir(parents=True, exist_ok=True)
        self.t0 = time.time()
        self._jsonl = open(self.dir / "sessao.jsonl", "w",
                           encoding="utf-8", buffering=1)
        self._i = 0
        self._video_i = 0
        self._gravar_video = gravar_video
        self._fps_nominal = fps_nominal
        self._writer = None
        self._fila: queue.Queue = queue.Queue(maxsize=30)
        self._thread = None
        self._fechado = False

        meta = {
            "inicio": time.strftime("%Y-%m-%d %H:%M:%S"),
            "video": "mao.avi" if gravar_video else None,
            "config": asdict(config) if config is not None else None,
        }
        (self.dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        if gravar_video:
            self._thread = threading.Thread(target=self._loop_video, daemon=True)
            self._thread.start()

    # ---------------------------------------------------------------- vídeo

    def _loop_video(self):
        while True:
            item = self._fila.get()
            if item is None:
                break
            if self._writer is None:
                # o tamanho do frame só é conhecido quando o primeiro chega
                h, w = item.shape[:2]
                self._writer = cv2.VideoWriter(
                    str(self.dir / "mao.avi"),
                    cv2.VideoWriter_fourcc(*"MJPG"),
                    self._fps_nominal, (w, h))
            self._writer.write(item)
        if self._writer is not None:
            self._writer.release()

    # ------------------------------------------------------------ registros

    def _escreve(self, rec: dict):
        self._jsonl.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def frame(self, detections, imagem=None) -> int:
        """Registra um frame e devolve o índice dele.

        `detections` são as detecções BRUTAS do modelo (saída de
        `CardDetector.detect`), e `imagem` é o frame CRU — nada de anotado:
        as caixas verdes desenhadas em cima estragariam a re-detecção com
        outro modelo, que é a razão de o vídeo existir.
        """
        i = self._i
        self._i += 1
        v = -1
        if self._gravar_video and imagem is not None:
            v = self._video_i
            self._video_i += 1
            self._fila.put(imagem)      # bloqueia se o disco não acompanhar
        self._escreve({
            "t": "frame",
            "i": i,
            "ts": round(time.time() - self.t0, 3),
            "v": v,
            "dets": [[d.card.code, round(d.confidence, 4),
                      *(round(float(x), 1) for x in d.box)]
                     for d in detections],
        })
        return i

    def mao(self, i: int, cards: list[str]):
        """A mão exibida mudou (o `StableHand` trocou de leitura)."""
        self._escreve({"t": "mao", "i": i, "cards": list(cards)})

    def evento(self, i: int, evento: dict):
        """Compra ou descarte emitido pelo tracker, com o frame que o gerou."""
        self._escreve({"t": "evento", "i": i, **evento})

    def marca(self, i: int, texto: str):
        """Marcador manual — para anotar 'aqui errou' sem parar a partida."""
        self._escreve({"t": "marca", "i": i, "texto": texto})

    # -------------------------------------------------------------- término

    def close(self):
        if self._fechado:
            return
        self._fechado = True
        if self._thread is not None:
            self._fila.put(None)
            self._thread.join(timeout=30)
        self._jsonl.close()
        print(f"gravação salva em {self.dir} "
              f"({self._i} frames, {self._video_i} no vídeo)", flush=True)
