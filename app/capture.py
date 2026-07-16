import threading
import time

import cv2


class CameraStream:
    """Lê a webcam numa thread própria e guarda só o frame mais recente.

    Se a câmera estiver ocupada (OBS, navegador) ou cair, tenta reabrir
    sozinha a cada poucos segundos — sem precisar reiniciar o app.
    """

    RETRY_SECONDS = 2.0

    def __init__(self, index: int, width: int, height: int):
        self.index = index
        self.width = width
        self.height = height
        self.cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        self._warned = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _open(self):
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)  # DSHOW: abre rápido no Windows
        if not cap.isOpened():
            cap.release()
            return None
        # MJPG destrava fps em resoluções altas (YUY2 satura o USB em 1080p+)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return cap

    def _loop(self):
        while self._running:
            if self.cap is None:
                self.cap = self._open()
                if self.cap is None:
                    if not self._warned:
                        print(f"câmera {self.index}: ocupada/indisponível — "
                              f"tentando de novo a cada {self.RETRY_SECONDS}s")
                        self._warned = True
                    time.sleep(self.RETRY_SECONDS)
                    continue
                print(f"câmera {self.index}: aberta")
                self._warned = False
            ok, frame = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = frame
            else:
                # câmera caiu (cabo, outro app tomou): larga e tenta reabrir
                self.cap.release()
                self.cap = None
                with self._lock:
                    self._frame = None

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._running = False
        self._thread.join(timeout=2)
        if self.cap is not None:
            self.cap.release()
