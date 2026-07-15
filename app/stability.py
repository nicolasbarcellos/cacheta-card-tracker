class StabilityFilter:
    """Emite um valor apenas após N observações consecutivas idênticas.

    Dispara uma única vez por valor: depois de emitir, só emite de novo
    quando um valor diferente se estabilizar (ou após reset()).
    """

    def __init__(self, frames_required: int):
        self.frames_required = frames_required
        self._candidate = None
        self._count = 0
        self._emitted = None

    def update(self, value):
        if value is None:
            self._candidate = None
            self._count = 0
            return None
        if value == self._candidate:
            self._count += 1
        else:
            self._candidate = value
            self._count = 1
        if self._count >= self.frames_required and value != self._emitted:
            self._emitted = value
            return value
        return None

    def reset(self):
        self._candidate = None
        self._count = 0
        self._emitted = None
