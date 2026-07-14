# Cacheta Card Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sistema local com 2 webcams + YOLO que detecta a carta descartada e a carta comprada numa partida de cacheta e exibe os PNGs num overlay web (OBS Browser Source), com painel de correção manual.

**Architecture:** App Python único: threads de captura (OpenCV) alimentam um detector YOLO (Ultralytics, GPU); a lógica de estado (`GameTracker`, código puro e testável) transforma detecções estáveis em eventos de compra/descarte; um servidor FastAPI faz broadcast do estado via WebSocket para duas páginas HTML (overlay do OBS e painel de controle).

**Tech Stack:** Python 3.11+, Ultralytics YOLO11, OpenCV, FastAPI, uvicorn, pytest, HTML/JS puro.

## Global Constraints

- Python 3.11+; GPU NVIDIA disponível (PyTorch com CUDA).
- Baralho padrão de 52 cartas, sem coringa, baralho único (sem repetidas).
- Mão da cacheta: **9 cartas** (`hand_size = 9`).
- Confiança mínima do detector: **0.75**; estabilidade: **10 frames consecutivos**.
- Servidor local em `http://127.0.0.1:8000`; overlay em `/overlay`, painel em `/painel`.
- Códigos de carta: `RANK + SUIT`, ex. `QS`, `10H`, `AD` (S=espadas, H=copas, D=ouros, C=paus).
- Eventos: `draw` (compra, com `source` = `monte`|`lixo`) e `discard` (descarte).
- Commits em Conventional Commits, mensagens em português.

---

### Task 1: Scaffold do projeto

**Files:**
- Create: `requirements.txt`, `.gitignore`, `app/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `app.config.config` — instância de `Config` com os campos abaixo, importável em todo o projeto.

- [ ] **Step 1: Criar `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
models/*.pt
training/datasets/
training/runs/
assets/cards/*.png
.pytest_cache/
```

- [ ] **Step 2: Criar `requirements.txt`**

```
ultralytics>=8.3
opencv-python>=4.10
fastapi>=0.115
uvicorn[standard]>=0.32
pytest>=8.0
httpx>=0.27
websockets>=13.0
```

- [ ] **Step 3: Criar venv e instalar (PyTorch CUDA primeiro, senão o pip instala a versão CPU)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
python -c "import torch; print(torch.cuda.is_available())"
```

Expected: última linha imprime `True`. Se imprimir `False`, verificar driver NVIDIA antes de seguir.

- [ ] **Step 4: Criar `app/__init__.py` (vazio) e `app/config.py`**

```python
from dataclasses import dataclass


@dataclass
class Config:
    discard_cam_index: int = 0
    hand_cam_index: int = 1
    frame_width: int = 1280
    frame_height: int = 720
    model_path: str = "models/cards.pt"
    min_confidence: float = 0.75
    confirm_confidence: float = 0.85
    stable_frames: int = 10
    hand_size: int = 9
    server_host: str = "127.0.0.1"
    server_port: int = 8000


config = Config()
```

- [ ] **Step 5: Criar `tests/__init__.py` (vazio) e `tests/test_config.py`**

```python
from app.config import config


def test_config_defaults():
    assert config.hand_size == 9
    assert config.min_confidence == 0.75
    assert config.stable_frames == 10
```

- [ ] **Step 6: Rodar testes**

Run: `pytest -v`
Expected: `1 passed`

- [ ] **Step 7: Commit**

```powershell
git add .gitignore requirements.txt app tests
git commit -m "chore: scaffold do projeto com config e pytest"
```

---

### Task 2: Modelo de domínio — `Card`

**Files:**
- Create: `app/cards.py`
- Test: `tests/test_cards.py`

**Interfaces:**
- Produces: `Card` (frozen dataclass, campos `rank: str`, `suit: str`), `Card.from_label(raw: str) -> Card` (aceita `"QS"`, `"10h"`, `"As"`; levanta `InvalidCardLabel` se inválido), propriedades `code -> str` (ex. `"QS"`), `asset -> str` (ex. `"QS.png"`), `display -> str` (ex. `"dama de espadas"`), `to_dict() -> dict` com chaves `code`, `asset`, `display`. Constantes `RANKS: tuple`, `SUITS: dict` (código → nome PT).

- [ ] **Step 1: Escrever testes que falham — `tests/test_cards.py`**

```python
import pytest

from app.cards import Card, InvalidCardLabel


def test_from_label_simple():
    card = Card.from_label("QS")
    assert card.rank == "Q"
    assert card.suit == "S"
    assert card.code == "QS"


def test_from_label_ten_and_lowercase():
    card = Card.from_label("10h")
    assert card.code == "10H"


def test_from_label_invalid():
    with pytest.raises(InvalidCardLabel):
        Card.from_label("ZZ")
    with pytest.raises(InvalidCardLabel):
        Card.from_label("JOKER")


def test_asset_and_display():
    card = Card.from_label("AD")
    assert card.asset == "AD.png"
    assert card.display == "ás de ouros"
    assert Card.from_label("7C").display == "7 de paus"


def test_to_dict():
    d = Card.from_label("KH").to_dict()
    assert d == {"code": "KH", "asset": "KH.png", "display": "rei de copas"}


def test_equality_and_hash():
    assert Card.from_label("2S") == Card.from_label("2s")
    assert len({Card.from_label("2S"), Card.from_label("2s")}) == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_cards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.cards'`

- [ ] **Step 3: Implementar `app/cards.py`**

```python
from dataclasses import dataclass

RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = {"S": "espadas", "H": "copas", "D": "ouros", "C": "paus"}
RANK_NAMES = {"A": "ás", "J": "valete", "Q": "dama", "K": "rei"}


class InvalidCardLabel(ValueError):
    pass


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @classmethod
    def from_label(cls, raw: str) -> "Card":
        label = raw.strip().upper()
        rank, suit = label[:-1], label[-1:]
        if rank not in RANKS or suit not in SUITS:
            raise InvalidCardLabel(raw)
        return cls(rank, suit)

    @property
    def code(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def asset(self) -> str:
        return f"{self.code}.png"

    @property
    def display(self) -> str:
        return f"{RANK_NAMES.get(self.rank, self.rank)} de {SUITS[self.suit]}"

    def to_dict(self) -> dict:
        return {"code": self.code, "asset": self.asset, "display": self.display}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_cards.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```powershell
git add app/cards.py tests/test_cards.py
git commit -m "feat: modelo de carta com parsing de rotulos do YOLO"
```

---

### Task 3: Filtro de estabilidade

**Files:**
- Create: `app/stability.py`
- Test: `tests/test_stability.py`

**Interfaces:**
- Produces: `StabilityFilter(frames_required: int)` com `update(value) -> value | None` (emite o valor quando visto `frames_required` vezes consecutivas; emite **uma única vez** por mudança; `None` como entrada zera a contagem) e `reset()` (esquece tudo, inclusive o último emitido).
- Consumes: nada (valores são qualquer hashable — códigos de carta ou frozensets).

- [ ] **Step 1: Escrever testes que falham — `tests/test_stability.py`**

```python
from app.stability import StabilityFilter


def test_emits_after_n_consecutive_frames():
    f = StabilityFilter(frames_required=3)
    assert f.update("QS") is None
    assert f.update("QS") is None
    assert f.update("QS") == "QS"


def test_emits_only_once_per_value():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    assert f.update("QS") == "QS"
    assert f.update("QS") is None  # já emitido, não repete


def test_interruption_resets_count():
    f = StabilityFilter(frames_required=3)
    f.update("QS")
    f.update("QS")
    f.update("7D")  # mão passou na frente, viu outra coisa
    assert f.update("QS") is None
    assert f.update("QS") is None
    assert f.update("QS") == "QS"


def test_none_resets_count():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    f.update(None)
    assert f.update("QS") is None
    assert f.update("QS") == "QS"


def test_new_value_can_emit_after_previous():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    assert f.update("QS") == "QS"
    f.update("7D")
    assert f.update("7D") == "7D"


def test_reset_allows_same_value_again():
    f = StabilityFilter(frames_required=2)
    f.update("QS")
    assert f.update("QS") == "QS"
    f.reset()
    f.update("QS")
    assert f.update("QS") == "QS"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_stability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.stability'`

- [ ] **Step 3: Implementar `app/stability.py`**

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_stability.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```powershell
git add app/stability.py tests/test_stability.py
git commit -m "feat: filtro de estabilidade por frames consecutivos"
```

---

### Task 4: GameTracker — descarte

**Files:**
- Create: `app/tracker.py`
- Test: `tests/test_tracker_discard.py`

**Interfaces:**
- Consumes: `Card` de `app.cards`.
- Produces: `Event` (dataclass: `id: int`, `type: str` — `"draw"`|`"discard"`, `card: Card`, `source: str | None`, `confirmed: bool`, método `to_dict()`); `GameTracker(hand_size: int = 9, on_change=None)` com `events: list[Event]`, `paused: bool`, e `on_stable_top_card(card: Card, confidence: float = 1.0)`. `on_change` é chamado (sem argumentos) após qualquer mutação de estado. Tasks 5 e 6 adicionam os demais métodos NESTE MESMO arquivo.

- [ ] **Step 1: Escrever testes que falham — `tests/test_tracker_discard.py`**

```python
from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def test_new_top_card_emits_discard():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    assert len(t.events) == 1
    assert t.events[0].type == "discard"
    assert t.events[0].card == c("QS")


def test_same_top_card_does_not_repeat():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    t.on_stable_top_card(c("QS"))
    assert len(t.events) == 1


def test_old_top_reappearing_is_not_a_new_discard():
    # alguém comprou o topo do lixo e a carta de baixo (descarte antigo) reapareceu
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    t.on_stable_top_card(c("7D"))
    t.on_stable_top_card(c("QS"))  # 7D saiu do lixo, QS reapareceu
    assert [e.card.code for e in t.events] == ["QS", "7D"]


def test_paused_ignores_detections():
    t = GameTracker()
    t.paused = True
    t.on_stable_top_card(c("QS"))
    assert t.events == []


def test_low_confidence_marks_unconfirmed():
    t = GameTracker()
    t.on_stable_top_card(c("QS"), confidence=0.78)
    assert t.events[0].confirmed is False


def test_on_change_called():
    calls = []
    t = GameTracker(on_change=lambda: calls.append(1))
    t.on_stable_top_card(c("QS"))
    assert calls == [1]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_tracker_discard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tracker'`

- [ ] **Step 3: Implementar `app/tracker.py`**

```python
from dataclasses import dataclass

from app.cards import Card
from app.config import config


@dataclass
class Event:
    id: int
    type: str  # "draw" | "discard"
    card: Card
    source: str | None = None  # "monte" | "lixo" (apenas draw)
    confirmed: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "card": self.card.to_dict(),
            "source": self.source,
            "confirmed": self.confirmed,
        }


class GameTracker:
    """Estado do jogo: transforma detecções estáveis em eventos draw/discard."""

    def __init__(self, hand_size: int = 9, on_change=None):
        self.hand_size = hand_size
        self.on_change = on_change or (lambda: None)
        self.paused = False
        self.events: list[Event] = []
        self._next_id = 1
        self._hand_ref: frozenset[Card] | None = None
        self._top_discard: Card | None = None
        self._discard_history: set[Card] = set()

    def _emit(self, type_: str, card: Card, source=None, confidence=1.0):
        event = Event(
            id=self._next_id,
            type=type_,
            card=card,
            source=source,
            confirmed=confidence >= config.confirm_confidence,
        )
        self._next_id += 1
        self.events.append(event)
        self.on_change()

    def on_stable_top_card(self, card: Card, confidence: float = 1.0):
        if self.paused or card == self._top_discard:
            return
        if card in self._discard_history:
            # topo antigo reapareceu (compraram do lixo) — não é descarte novo
            self._top_discard = card
            return
        self._top_discard = card
        self._discard_history.add(card)
        self._emit("discard", card, confidence=confidence)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_tracker_discard.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```powershell
git add app/tracker.py tests/test_tracker_discard.py
git commit -m "feat: tracker de descarte com historico do lixo"
```

---

### Task 5: GameTracker — compra (diff da mão)

**Files:**
- Modify: `app/tracker.py` (adicionar método à classe `GameTracker`)
- Test: `tests/test_tracker_draw.py`

**Interfaces:**
- Produces: `GameTracker.on_stable_hand(cards: frozenset[Card])` — conjunto estável de cartas visto na câmera da mão. Regras: primeiro conjunto de tamanho `hand_size` vira referência; conjunto de `hand_size + 1` com exatamente 1 carta nova → evento `draw` (source `"lixo"` se a carta era o histórico do lixo, senão `"monte"`); conjunto de `hand_size` atualiza a referência (pós-descarte).

- [ ] **Step 1: Escrever testes que falham — `tests/test_tracker_draw.py`**

```python
from app.cards import Card
from app.tracker import GameTracker

HAND = frozenset(Card.from_label(x) for x in
                 ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])


def c(code):
    return Card.from_label(code)


def test_first_full_hand_sets_reference_without_event():
    t = GameTracker()
    t.on_stable_hand(HAND)
    assert t.events == []


def test_extra_card_emits_draw_from_monte():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_hand(HAND | {c("KC")})
    assert len(t.events) == 1
    assert t.events[0].type == "draw"
    assert t.events[0].card == c("KC")
    assert t.events[0].source == "monte"


def test_draw_from_lixo_detected_by_history():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_top_card(c("KC"))       # alguém descartou KC no lixo
    t.on_stable_hand(HAND | {c("KC")})  # eu peguei o KC
    draws = [e for e in t.events if e.type == "draw"]
    assert draws[0].source == "lixo"


def test_card_taken_from_lixo_can_be_discarded_again():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_top_card(c("KC"))
    t.on_stable_hand(HAND | {c("KC")})  # comprei do lixo
    t.on_stable_top_card(c("KC"))       # e descartei o mesmo KC de volta
    discards = [e for e in t.events if e.type == "discard"]
    assert [e.card.code for e in discards] == ["KC", "KC"]


def test_nine_card_set_updates_reference():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_hand(HAND | {c("KC")})            # comprou KC
    new_hand = frozenset(list(HAND)[1:]) | {c("KC")}  # descartou uma antiga
    t.on_stable_hand(new_hand)                     # mão volta a 9
    t.on_stable_hand(new_hand | {c("QC")})         # próximo turno: compra QC
    draws = [e for e in t.events if e.type == "draw"]
    assert [e.card.code for e in draws] == ["KC", "QC"]


def test_garbage_sets_are_ignored():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.on_stable_hand(frozenset([c("KC"), c("QC")]))  # detecção ruim (2 cartas)
    assert t.events == []
    t.on_stable_hand(HAND | {c("KC")})
    assert len(t.events) == 1  # referência não foi corrompida


def test_paused_ignores_hand():
    t = GameTracker()
    t.on_stable_hand(HAND)
    t.paused = True
    t.on_stable_hand(HAND | {c("KC")})
    assert t.events == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_tracker_draw.py -v`
Expected: FAIL — `AttributeError: 'GameTracker' object has no attribute 'on_stable_hand'`

- [ ] **Step 3: Adicionar método à classe `GameTracker` em `app/tracker.py`**

```python
    def on_stable_hand(self, cards: frozenset[Card]):
        if self.paused or not cards:
            return
        if self._hand_ref is None:
            if len(cards) == self.hand_size:
                self._hand_ref = cards
                self.on_change()
            return
        new = cards - self._hand_ref
        if len(cards) == self.hand_size + 1 and len(new) == 1:
            (card,) = new
            source = "monte"
            if card in self._discard_history:
                source = "lixo"
                self._discard_history.discard(card)
                if self._top_discard == card:
                    self._top_discard = None
            self._hand_ref = cards
            self._emit("draw", card, source=source)
        elif len(cards) == self.hand_size:
            self._hand_ref = cards
            self.on_change()
```

- [ ] **Step 4: Rodar TODOS os testes**

Run: `pytest -v`
Expected: todos passam (config + cards + stability + tracker_discard + tracker_draw)

- [ ] **Step 5: Commit**

```powershell
git add app/tracker.py tests/test_tracker_draw.py
git commit -m "feat: deteccao de compra por diff da mao com origem monte/lixo"
```

---

### Task 6: GameTracker — correção, desfazer, nova rodada, pausa e state()

**Files:**
- Modify: `app/tracker.py`
- Test: `tests/test_tracker_control.py`

**Interfaces:**
- Produces: `correct_event(event_id: int, card: Card) -> bool`, `undo_last() -> bool`, `new_round()`, `set_paused(paused: bool)`, `state() -> dict` com chaves `draw` (último evento draw como dict ou `None`), `discard` (idem), `paused: bool`, `events: list[dict]` (últimos 20, mais recente primeiro). O servidor (Task 7) consome exatamente esse formato.

- [ ] **Step 1: Escrever testes que falham — `tests/test_tracker_control.py`**

```python
from app.cards import Card
from app.tracker import GameTracker


def c(code):
    return Card.from_label(code)


def test_correct_event_replaces_card():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    event_id = t.events[0].id
    assert t.correct_event(event_id, c("QH")) is True
    assert t.events[0].card == c("QH")
    assert t.events[0].confirmed is True


def test_correct_discard_fixes_history():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    t.correct_event(t.events[0].id, c("QH"))
    t.on_stable_top_card(c("QS"))  # agora QS é um descarte novo de verdade
    assert [e.card.code for e in t.events] == ["QH", "QS"]


def test_correct_unknown_id_returns_false():
    t = GameTracker()
    assert t.correct_event(99, c("QS")) is False


def test_undo_removes_last_event():
    t = GameTracker()
    t.on_stable_top_card(c("QS"))
    assert t.undo_last() is True
    assert t.events == []
    t.on_stable_top_card(c("QS"))  # pode ser detectado de novo
    assert len(t.events) == 1


def test_undo_empty_returns_false():
    assert GameTracker().undo_last() is False


def test_new_round_clears_state():
    t = GameTracker()
    hand = frozenset(Card.from_label(x) for x in
                     ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])
    t.on_stable_hand(hand)
    t.on_stable_top_card(c("QS"))
    t.new_round()
    assert t.events == []
    t.on_stable_top_card(c("QS"))  # rodada nova: QS pode ser descartada de novo
    assert len(t.events) == 1


def test_state_shape():
    t = GameTracker()
    hand = frozenset(Card.from_label(x) for x in
                     ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])
    t.on_stable_hand(hand)
    t.on_stable_hand(hand | {c("KC")})
    t.on_stable_top_card(c("QS"))
    s = t.state()
    assert s["draw"]["card"]["code"] == "KC"
    assert s["discard"]["card"]["code"] == "QS"
    assert s["paused"] is False
    assert len(s["events"]) == 2
    assert s["events"][0]["card"]["code"] == "QS"  # mais recente primeiro


def test_state_empty():
    s = GameTracker().state()
    assert s == {"draw": None, "discard": None, "paused": False, "events": []}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_tracker_control.py -v`
Expected: FAIL — `AttributeError: ... 'correct_event'`

- [ ] **Step 3: Adicionar métodos à classe `GameTracker` em `app/tracker.py`**

```python
    def correct_event(self, event_id: int, card: Card) -> bool:
        event = next((e for e in self.events if e.id == event_id), None)
        if event is None:
            return False
        if event.type == "discard":
            self._discard_history.discard(event.card)
            self._discard_history.add(card)
            if self._top_discard == event.card:
                self._top_discard = card
        event.card = card
        event.confirmed = True
        self.on_change()
        return True

    def undo_last(self) -> bool:
        if not self.events:
            return False
        event = self.events.pop()
        if event.type == "discard":
            self._discard_history.discard(event.card)
            if self._top_discard == event.card:
                self._top_discard = None
        self.on_change()
        return True

    def new_round(self):
        self.events.clear()
        self._hand_ref = None
        self._top_discard = None
        self._discard_history.clear()
        self.on_change()

    def set_paused(self, paused: bool):
        self.paused = paused
        self.on_change()

    def state(self) -> dict:
        def last(type_):
            for e in reversed(self.events):
                if e.type == type_:
                    return e.to_dict()
            return None

        return {
            "draw": last("draw"),
            "discard": last("discard"),
            "paused": self.paused,
            "events": [e.to_dict() for e in reversed(self.events[-20:])],
        }
```

- [ ] **Step 4: Rodar TODOS os testes**

Run: `pytest -v`
Expected: todos passam

- [ ] **Step 5: Commit**

```powershell
git add app/tracker.py tests/test_tracker_control.py
git commit -m "feat: correcao, desfazer, nova rodada e snapshot de estado"
```

---

### Task 7: Servidor FastAPI + WebSocket

**Files:**
- Create: `app/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `GameTracker` (Task 6), `Card` (Task 2).
- Produces: `create_app(tracker: GameTracker, annotated_frames: dict | None = None, on_new_round=None) -> FastAPI`. Rotas: `GET /api/state`, `POST /api/correct` (`{"event_id": int, "card": "QS"}`), `POST /api/undo`, `POST /api/new-round`, `POST /api/pause` (`{"paused": bool}`), `WS /ws` (envia `{"type": "state", ...state}` na conexão e a cada mudança), `GET /overlay`, `GET /painel`, mounts `/static` → `web/` e `/assets` → `assets/`, `GET /stream/{cam}` (MJPEG de `annotated_frames[cam]`). `on_new_round` é chamado junto com `tracker.new_round()` (usado na Task 13 para resetar os StabilityFilters).

- [ ] **Step 1: Escrever testes que falham — `tests/test_server.py`**

```python
from fastapi.testclient import TestClient

from app.cards import Card
from app.server import create_app
from app.tracker import GameTracker


def make_client():
    tracker = GameTracker()
    app = create_app(tracker)
    return tracker, TestClient(app)


def test_state_endpoint():
    tracker, client = make_client()
    resp = client.get("/api/state")
    assert resp.status_code == 200
    assert resp.json() == {"draw": None, "discard": None,
                           "paused": False, "events": []}


def test_correct_endpoint():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    event_id = tracker.events[0].id
    resp = client.post("/api/correct", json={"event_id": event_id, "card": "QH"})
    assert resp.status_code == 200
    assert tracker.events[0].card.code == "QH"


def test_correct_invalid_card_returns_422():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    resp = client.post("/api/correct",
                       json={"event_id": tracker.events[0].id, "card": "ZZ"})
    assert resp.status_code == 422


def test_correct_unknown_event_returns_404():
    _, client = make_client()
    resp = client.post("/api/correct", json={"event_id": 99, "card": "QS"})
    assert resp.status_code == 404


def test_undo_and_pause_and_new_round():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    assert client.post("/api/undo").status_code == 200
    assert tracker.events == []
    assert client.post("/api/pause", json={"paused": True}).status_code == 200
    assert tracker.paused is True
    assert client.post("/api/new-round").status_code == 200


def test_websocket_sends_state_on_connect():
    tracker, client = make_client()
    tracker.on_stable_top_card(Card.from_label("QS"))
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert data["type"] == "state"
        assert data["discard"]["card"]["code"] == "QS"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.server'`

- [ ] **Step 3: Implementar `app/server.py`**

```python
import asyncio
import queue
from pathlib import Path

import cv2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.cards import Card, InvalidCardLabel
from app.tracker import GameTracker

ROOT = Path(__file__).resolve().parent.parent


class CorrectBody(BaseModel):
    event_id: int
    card: str


class PauseBody(BaseModel):
    paused: bool


def create_app(tracker: GameTracker,
               annotated_frames: dict | None = None,
               on_new_round=None) -> FastAPI:
    app = FastAPI()
    annotated_frames = annotated_frames if annotated_frames is not None else {}
    clients: set[WebSocket] = set()
    changes: queue.Queue = queue.Queue()

    # o tracker roda na thread de visão; o WS roda no event loop.
    # on_change enfileira; um task assíncrono drena a fila e faz broadcast.
    tracker.on_change = lambda: changes.put(True)

    async def broadcast_state():
        payload = {"type": "state", **tracker.state()}
        for ws in list(clients):
            try:
                await ws.send_json(payload)
            except Exception:
                clients.discard(ws)

    @app.on_event("startup")
    async def start_broadcaster():
        async def pump():
            while True:
                try:
                    changes.get_nowait()
                    while not changes.empty():  # colapsa rajadas
                        changes.get_nowait()
                    await broadcast_state()
                except queue.Empty:
                    await asyncio.sleep(0.05)
        asyncio.create_task(pump())

    @app.get("/")
    async def index():
        return RedirectResponse("/painel")

    @app.get("/overlay")
    async def overlay():
        return FileResponse(ROOT / "web" / "overlay" / "index.html")

    @app.get("/painel")
    async def painel():
        return FileResponse(ROOT / "web" / "painel" / "index.html")

    @app.get("/api/state")
    async def get_state():
        return tracker.state()

    @app.post("/api/correct")
    async def correct(body: CorrectBody):
        try:
            card = Card.from_label(body.card)
        except InvalidCardLabel:
            raise HTTPException(422, f"carta inválida: {body.card}")
        if not tracker.correct_event(body.event_id, card):
            raise HTTPException(404, f"evento {body.event_id} não existe")
        return {"ok": True}

    @app.post("/api/undo")
    async def undo():
        tracker.undo_last()
        return {"ok": True}

    @app.post("/api/new-round")
    async def new_round():
        tracker.new_round()
        if on_new_round:
            on_new_round()
        return {"ok": True}

    @app.post("/api/pause")
    async def pause(body: PauseBody):
        tracker.set_paused(body.paused)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        clients.add(ws)
        await ws.send_json({"type": "state", **tracker.state()})
        try:
            while True:
                await ws.receive_text()  # mantém a conexão viva
        except WebSocketDisconnect:
            clients.discard(ws)

    @app.get("/stream/{cam}")
    async def stream(cam: str):
        async def frames():
            while True:
                frame = annotated_frames.get(cam)
                if frame is not None:
                    ok, jpg = cv2.imencode(".jpg", frame)
                    if ok:
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                               + jpg.tobytes() + b"\r\n")
                await asyncio.sleep(0.1)  # ~10 fps é suficiente p/ preview
        return StreamingResponse(
            frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    for mount, folder in (("/static", "web"), ("/assets", "assets")):
        path = ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
        app.mount(mount, StaticFiles(directory=path), name=folder)

    return app
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/test_server.py -v`
Expected: `6 passed`

- [ ] **Step 5: Rodar TODOS os testes e commit**

Run: `pytest -v` — Expected: todos passam

```powershell
git add app/server.py tests/test_server.py
git commit -m "feat: servidor fastapi com websocket, api de controle e mjpeg"
```

---

### Task 8: Assets das 52 cartas

**Files:**
- Create: `scripts/download_assets.py`
- Create (gerados): `assets/cards/*.png` (52 arquivos, ignorados pelo git)

**Interfaces:**
- Consumes: `RANKS`, `SUITS` de `app.cards`.
- Produces: `assets/cards/{code}.png` para cada carta (ex. `QS.png`, `10H.png`) — exatamente o nome retornado por `Card.asset`.

- [ ] **Step 1: Criar `scripts/download_assets.py`**

```python
"""Baixa os PNGs das 52 cartas do deckofcardsapi.com (imagens estáticas).

Lá o rank 10 usa código "0" (ex.: 0S.png); salvamos com nosso código (10S.png).
"""
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cards import RANKS, SUITS  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "assets" / "cards"
OUT.mkdir(parents=True, exist_ok=True)

for rank in RANKS:
    for suit in SUITS:
        remote = ("0" if rank == "10" else rank) + suit
        dest = OUT / f"{rank}{suit}.png"
        if dest.exists():
            continue
        url = f"https://deckofcardsapi.com/static/img/{remote}.png"
        print(f"baixando {url} -> {dest.name}")
        urllib.request.urlretrieve(url, dest)

count = len(list(OUT.glob("*.png")))
print(f"{count} cartas em {OUT}")
assert count == 52, f"esperava 52 PNGs, tem {count}"
```

- [ ] **Step 2: Rodar e verificar**

Run: `python scripts/download_assets.py`
Expected: termina com `52 cartas em ...assets\cards`

- [ ] **Step 3: Commit (só o script; os PNGs estão no .gitignore)**

```powershell
git add scripts/download_assets.py
git commit -m "feat: script de download dos assets das 52 cartas"
```

---

### Task 9: Overlay do OBS

**Files:**
- Create: `web/overlay/index.html`

**Interfaces:**
- Consumes: `WS /ws` (mensagens `{"type": "state", "draw": {...}|null, "discard": {...}|null, ...}`) e `/assets/cards/{asset}`.

- [ ] **Step 1: Criar `web/overlay/index.html`**

```html
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Overlay</title>
<style>
  /* fundo transparente para o OBS Browser Source */
  body { margin: 0; background: transparent; font-family: Arial, sans-serif; }
  .slots { display: flex; gap: 40px; padding: 20px; }
  .slot { text-align: center; }
  .slot .titulo {
    color: #fff; font-size: 22px; font-weight: bold;
    text-shadow: 0 2px 4px rgba(0,0,0,.8); margin-bottom: 8px;
    text-transform: uppercase; letter-spacing: 2px;
  }
  .slot img {
    width: 140px; display: block;
    filter: drop-shadow(0 4px 10px rgba(0,0,0,.6));
  }
  .slot img.nova { animation: entrada .4s ease-out; }
  @keyframes entrada {
    from { transform: translateY(-30px) rotateY(90deg); opacity: 0; }
    to   { transform: none; opacity: 1; }
  }
  .selo {
    display: inline-block; margin-top: 6px; padding: 2px 10px;
    background: #e6b800; color: #000; font-size: 14px; font-weight: bold;
    border-radius: 10px;
  }
  .vazio { width: 140px; height: 196px; border: 3px dashed rgba(255,255,255,.4);
           border-radius: 8px; box-sizing: border-box; }
</style>
</head>
<body>
<div class="slots">
  <div class="slot">
    <div class="titulo">Compra</div>
    <div id="draw"><div class="vazio"></div></div>
  </div>
  <div class="slot">
    <div class="titulo">Descarte</div>
    <div id="discard"><div class="vazio"></div></div>
  </div>
</div>
<script>
  const shown = { draw: null, discard: null };

  function render(kind, event) {
    const el = document.getElementById(kind);
    if (!event) { el.innerHTML = '<div class="vazio"></div>'; shown[kind] = null; return; }
    if (shown[kind] === event.card.code + ':' + event.id) return;
    shown[kind] = event.card.code + ':' + event.id;
    const selo = (kind === 'draw' && event.source === 'lixo')
      ? '<div class="selo">do lixo</div>' : '';
    el.innerHTML = `<img class="nova" src="/assets/cards/${event.card.asset}"
                        alt="${event.card.display}">${selo}`;
  }

  function connect() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (msg) => {
      const state = JSON.parse(msg.data);
      render('draw', state.draw);
      render('discard', state.discard);
    };
    ws.onclose = () => setTimeout(connect, 1000);  // reconecta sozinho
  }
  connect();
</script>
</body>
</html>
```

- [ ] **Step 2: Verificar manualmente com um tracker fake**

Criar arquivo temporário `scripts/demo_server.py` (não commitar):

```python
import threading
import time

import uvicorn

from app.cards import Card
from app.server import create_app
from app.tracker import GameTracker

tracker = GameTracker()
app = create_app(tracker)


def simulate():
    time.sleep(3)
    hand = frozenset(Card.from_label(x) for x in
                     ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"])
    tracker.on_stable_hand(hand)
    tracker.on_stable_hand(hand | {Card.from_label("KC")})
    time.sleep(2)
    tracker.on_stable_top_card(Card.from_label("QS"))


threading.Thread(target=simulate, daemon=True).start()
uvicorn.run(app, host="127.0.0.1", port=8000)
```

Run: `python scripts/demo_server.py`, abrir `http://127.0.0.1:8000/overlay` no navegador.
Expected: após ~3s aparece o rei de paus em COMPRA com animação; após mais 2s a dama de espadas em DESCARTE.

- [ ] **Step 3: Commit**

```powershell
git add web/overlay/index.html
git commit -m "feat: overlay do obs com compra e descarte via websocket"
```

---

### Task 10: Painel de controle

**Files:**
- Create: `web/painel/index.html`

**Interfaces:**
- Consumes: `WS /ws`, `POST /api/correct|undo|new-round|pause`, `GET /stream/discard`, `GET /stream/hand`, `/assets/cards/*`.

- [ ] **Step 1: Criar `web/painel/index.html`**

```html
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Painel — Cacheta Tracker</title>
<style>
  body { margin: 0; background: #1a1a2e; color: #eee;
         font-family: Arial, sans-serif; }
  h1 { font-size: 18px; padding: 12px 16px; margin: 0; background: #16213e; }
  .cols { display: flex; gap: 16px; padding: 16px; }
  .cams { flex: 2; }
  .cams img { width: 100%; border-radius: 6px; background: #000;
              margin-bottom: 12px; }
  .cams .rotulo { font-size: 13px; color: #9aa; margin-bottom: 4px; }
  .lado { flex: 1; min-width: 320px; }
  .acoes { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  button { background: #0f3460; color: #fff; border: 0; padding: 10px 14px;
           border-radius: 6px; cursor: pointer; font-size: 14px; }
  button:hover { background: #16498c; }
  button.perigo { background: #7a1f1f; }
  #pausar.ativo { background: #b8860b; }
  .evento { display: flex; align-items: center; gap: 10px; padding: 8px;
            background: #16213e; border-radius: 6px; margin-bottom: 6px; }
  .evento.pendente { outline: 2px solid #e6b800; }  /* confiança baixa */
  .evento img { width: 40px; }
  .evento .info { flex: 1; font-size: 14px; }
  .evento .tipo { font-size: 11px; color: #9aa; text-transform: uppercase; }
  dialog { background: #16213e; color: #eee; border: 1px solid #0f3460;
           border-radius: 8px; }
  select { font-size: 16px; padding: 6px; margin: 4px; }
</style>
</head>
<body>
<h1>Painel — Cacheta Tracker</h1>
<div class="cols">
  <div class="cams">
    <div class="rotulo">Câmera do descarte</div>
    <img src="/stream/discard" alt="descarte">
    <div class="rotulo">Câmera da mão</div>
    <img src="/stream/hand" alt="mão">
  </div>
  <div class="lado">
    <div class="acoes">
      <button id="pausar">Pausar detecção</button>
      <button id="desfazer">Desfazer último</button>
      <button id="novarodada" class="perigo">Nova rodada</button>
    </div>
    <div id="eventos"></div>
  </div>
</div>

<dialog id="corrigir">
  <p>Corrigir carta do evento <span id="dlg-id"></span>:</p>
  <select id="dlg-rank"></select>
  <select id="dlg-suit">
    <option value="S">♠ espadas</option><option value="H">♥ copas</option>
    <option value="D">♦ ouros</option><option value="C">♣ paus</option>
  </select>
  <div><button id="dlg-ok">Salvar</button>
       <button id="dlg-cancel">Cancelar</button></div>
</dialog>

<script>
  const RANKS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"];
  document.getElementById('dlg-rank').innerHTML =
    RANKS.map(r => `<option>${r}</option>`).join('');

  let paused = false;
  const post = (url, body) => fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : null,
  });

  document.getElementById('desfazer').onclick = () => post('/api/undo');
  document.getElementById('novarodada').onclick = () => {
    if (confirm('Zerar a rodada?')) post('/api/new-round');
  };
  const btnPause = document.getElementById('pausar');
  btnPause.onclick = () => post('/api/pause', { paused: !paused });

  const dlg = document.getElementById('corrigir');
  let corrigindoId = null;
  function abrirCorrecao(id) {
    corrigindoId = id;
    document.getElementById('dlg-id').textContent = '#' + id;
    dlg.showModal();
  }
  document.getElementById('dlg-cancel').onclick = () => dlg.close();
  document.getElementById('dlg-ok').onclick = () => {
    const card = document.getElementById('dlg-rank').value
               + document.getElementById('dlg-suit').value;
    post('/api/correct', { event_id: corrigindoId, card });
    dlg.close();
  };

  function renderEventos(state) {
    paused = state.paused;
    btnPause.textContent = paused ? 'Retomar detecção' : 'Pausar detecção';
    btnPause.classList.toggle('ativo', paused);
    document.getElementById('eventos').innerHTML = state.events.map(e => `
      <div class="evento ${e.confirmed ? '' : 'pendente'}">
        <img src="/assets/cards/${e.card.asset}" alt="">
        <div class="info">
          <div class="tipo">${e.type === 'draw'
            ? 'compra' + (e.source === 'lixo' ? ' (do lixo)' : ' (do monte)')
            : 'descarte'}${e.confirmed ? '' : ' — confirmar?'}</div>
          ${e.card.display}
        </div>
        <button onclick="abrirCorrecao(${e.id})">corrigir</button>
      </div>`).join('');
  }

  function connect() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = (msg) => renderEventos(JSON.parse(msg.data));
    ws.onclose = () => setTimeout(connect, 1000);
  }
  connect();
</script>
</body>
</html>
```

- [ ] **Step 2: Verificar manualmente**

Run: `python scripts/demo_server.py` (da Task 9), abrir `http://127.0.0.1:8000/painel`.
Expected: eventos de compra (KC) e descarte (QS) aparecem na lista; botão "corrigir" abre o diálogo e trocar a carta atualiza a lista E o overlay (abrir `/overlay` em outra aba para conferir); "desfazer" remove o último; "pausar" muda o rótulo do botão. Os previews das câmeras ficam pretos (ainda não há captura — ok).

- [ ] **Step 3: Apagar `scripts/demo_server.py` e commit**

```powershell
Remove-Item scripts/demo_server.py
git add web/painel/index.html
git commit -m "feat: painel de controle com correcao, desfazer e pausa"
```

---

### Task 11: Captura das webcams e wrapper do YOLO

**Files:**
- Create: `app/capture.py`, `app/detector.py`, `scripts/check_cams.py`
- Test: `tests/test_detector_logic.py` (só a lógica pura; câmera e modelo são verificação manual)

**Interfaces:**
- Produces: `CameraStream(index: int, width: int, height: int)` com `.read() -> ndarray | None` (último frame, thread-safe), `.stop()`; `Detection` (dataclass: `card: Card`, `confidence: float`, `box: tuple[int, int, int, int]`); `CardDetector(model_path: str, min_confidence: float)` com `.detect(frame) -> list[Detection]`; funções puras `pick_top_card(detections) -> Detection | None` (maior confiança) e `hand_codes(detections) -> frozenset[str]` (códigos únicos vistos); `draw_boxes(frame, detections) -> frame anotado`.

- [ ] **Step 1: Escrever testes da lógica pura — `tests/test_detector_logic.py`**

```python
from app.cards import Card
from app.detector import Detection, hand_codes, pick_top_card


def det(code, conf):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(0, 0, 10, 10))


def test_pick_top_card_highest_confidence():
    dets = [det("QS", 0.80), det("7D", 0.95), det("2C", 0.85)]
    assert pick_top_card(dets).card.code == "7D"


def test_pick_top_card_empty():
    assert pick_top_card([]) is None


def test_hand_codes_dedupes_corner_detections():
    # YOLO detecta os 2 cantos da mesma carta -> 2 detecções, 1 carta
    dets = [det("QS", 0.9), det("QS", 0.8), det("7D", 0.9)]
    assert hand_codes(dets) == frozenset({"QS", "7D"})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_detector_logic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.detector'`

- [ ] **Step 3: Implementar `app/detector.py`**

```python
from dataclasses import dataclass

import cv2

from app.cards import Card, InvalidCardLabel


@dataclass
class Detection:
    card: Card
    confidence: float
    box: tuple  # x1, y1, x2, y2


def pick_top_card(detections: list[Detection]) -> Detection | None:
    """Heurística p/ topo do lixo: a carta com maior confiança.

    A carta do topo é a mais visível; cartas soterradas aparecem como
    frestas com confiança menor. Ajustar aqui se o setup real mostrar outra coisa.
    """
    if not detections:
        return None
    return max(detections, key=lambda d: d.confidence)


def hand_codes(detections: list[Detection]) -> frozenset[str]:
    return frozenset(d.card.code for d in detections)


def draw_boxes(frame, detections: list[Detection]):
    out = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d.box
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, f"{d.card.code} {d.confidence:.2f}", (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out


class CardDetector:
    def __init__(self, model_path: str, min_confidence: float):
        from ultralytics import YOLO  # import tardio: pesado
        self.model = YOLO(model_path)
        self.min_confidence = min_confidence

    def detect(self, frame) -> list[Detection]:
        results = self.model.predict(frame, conf=self.min_confidence,
                                     verbose=False)
        detections = []
        for box in results[0].boxes:
            label = self.model.names[int(box.cls)]
            try:
                card = Card.from_label(label)
            except InvalidCardLabel:
                continue  # classe fora do baralho (ex.: joker do dataset)
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            detections.append(Detection(card=card,
                                        confidence=float(box.conf),
                                        box=(x1, y1, x2, y2)))
        return detections
```

- [ ] **Step 4: Implementar `app/capture.py`**

```python
import threading

import cv2


class CameraStream:
    """Lê a webcam numa thread própria e guarda só o frame mais recente."""

    def __init__(self, index: int, width: int, height: int):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)  # DSHOW: abre rápido no Windows
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._running = False
        self._thread.join(timeout=2)
        self.cap.release()
```

- [ ] **Step 5: Rodar testes**

Run: `pytest -v`
Expected: todos passam

- [ ] **Step 6: Criar `scripts/check_cams.py` e verificar o hardware**

```python
"""Mostra as duas webcams lado a lado para conferir índices/foco/enquadramento."""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402

cams = {
    "descarte": CameraStream(config.discard_cam_index,
                             config.frame_width, config.frame_height),
    "mao": CameraStream(config.hand_cam_index,
                        config.frame_width, config.frame_height),
}
print("q para sair. Se as câmeras estiverem trocadas, ajustar índices em app/config.py")
while True:
    for name, cam in cams.items():
        frame = cam.read()
        if frame is not None:
            cv2.imshow(name, frame)
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break
for cam in cams.values():
    cam.stop()
cv2.destroyAllWindows()
```

Run: `python scripts/check_cams.py`
Expected: duas janelas mostrando as webcams. Ajustar `discard_cam_index`/`hand_cam_index` em `app/config.py` se estiverem trocadas.

- [ ] **Step 7: Commit**

```powershell
git add app/capture.py app/detector.py scripts/check_cams.py tests/test_detector_logic.py
git commit -m "feat: captura das webcams e wrapper do detector yolo"
```

---

### Task 12: Treino do YOLO (dataset público)

**Files:**
- Create: `training/download_dataset.py`, `training/train.py`, `training/README.md`, `scripts/check_model.py`
- Create (gerado): `models/cards.pt` (ignorado pelo git)

**Interfaces:**
- Produces: `models/cards.pt` — pesos YOLO com classes de carta cujo nome `Card.from_label` consegue interpretar (ex. `10C`, `QS`; maiúsculas/minúsculas não importam; classes extras como joker são ignoradas pelo detector).

- [ ] **Step 1: Criar conta gratuita no Roboflow e obter API key**

Manual: criar conta em https://universe.roboflow.com, copiar a Private API Key (Settings → API Keys) e definir:

```powershell
$env:ROBOFLOW_API_KEY = "sua-chave-aqui"
```

- [ ] **Step 2: Criar `training/download_dataset.py`**

```python
"""Baixa o dataset público de cartas (52 classes + joker) do Roboflow Universe.

Dataset: "Playing Cards" (augmented-startups/playing-cards-ow27d) —
bounding boxes nos índices dos cantos, formato YOLO.
Requer: pip install roboflow, e ROBOFLOW_API_KEY no ambiente.
"""
import os
from pathlib import Path

from roboflow import Roboflow

OUT = Path(__file__).resolve().parent / "datasets"
OUT.mkdir(exist_ok=True)

rf = Roboflow(api_key=os.environ["ROBOFLOW_API_KEY"])
project = rf.workspace("augmented-startups").project("playing-cards-ow27d")
dataset = project.version(4).download("yolov8", location=str(OUT / "playing-cards"))
print(f"dataset em {dataset.location}")
print("conferir data.yaml: os nomes das classes devem ser tipo '10C', 'AS'...")
```

Run:
```powershell
pip install roboflow
python training/download_dataset.py
```
Expected: pasta `training/datasets/playing-cards/` com `data.yaml`, `train/`, `valid/`. Abrir `data.yaml` e conferir os nomes das classes — se o dataset/versão não existir mais, buscar "playing cards" no Roboflow Universe, escolher um dataset de 52/53 classes com índices de canto e ajustar workspace/project/version no script.

- [ ] **Step 3: Criar `training/train.py`**

```python
"""Treina o YOLO11-small no dataset de cartas e publica em models/cards.pt."""
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "datasets" / "playing-cards" / "data.yaml"

model = YOLO("yolo11s.pt")  # baixa o pré-treinado COCO automaticamente
results = model.train(
    data=str(DATA),
    epochs=50,
    imgsz=640,
    batch=16,       # reduzir se faltar VRAM
    project=str(ROOT / "runs"),
    name="cards",
    exist_ok=True,
)

best = ROOT / "runs" / "cards" / "weights" / "best.pt"
dest = ROOT.parent / "models" / "cards.pt"
dest.parent.mkdir(exist_ok=True)
shutil.copy(best, dest)
print(f"modelo publicado em {dest}")
```

Run: `python training/train.py` (demora — dezenas de minutos a algumas horas na GPU)
Expected: termina com `modelo publicado em ...models\cards.pt`; no log do treino, `mAP50` da última época acima de ~0.95 (esse dataset é "fácil").

- [ ] **Step 4: Smoke test do modelo com a webcam — criar `scripts/check_model.py`**

```python
"""Mostra a câmera do descarte com as detecções do modelo treinado."""
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402
from app.detector import CardDetector, draw_boxes  # noqa: E402

detector = CardDetector(config.model_path, min_confidence=0.5)
cam = CameraStream(config.discard_cam_index,
                   config.frame_width, config.frame_height)
print("mostre uma carta para a câmera; q para sair")
while True:
    frame = cam.read()
    if frame is not None:
        cv2.imshow("modelo", draw_boxes(frame, detector.detect(frame)))
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break
cam.stop()
cv2.destroyAllWindows()
```

Run: `python scripts/check_model.py`
Expected: segurando uma carta na frente da câmera, aparece a caixa com o código certo (ex. `QS 0.91`). Não precisa ser perfeito ainda — o fine-tuning (Task 14) resolve o resto.

- [ ] **Step 5: Criar `training/README.md`**

```markdown
# Treino

1. `pip install roboflow` e exportar `ROBOFLOW_API_KEY`
2. `python training/download_dataset.py` — baixa o dataset público
3. `python training/train.py` — treina e publica `models/cards.pt`
4. Fine-tuning com o setup real: ver `training/capture_frames.py` (Task 14)

Se trocar de dataset, conferir se os nomes das classes em `data.yaml`
são interpretáveis por `Card.from_label` (`10C`, `AS`, `qh`...).
```

- [ ] **Step 6: Commit**

```powershell
git add training/download_dataset.py training/train.py training/README.md scripts/check_model.py
git commit -m "feat: scripts de download do dataset e treino do yolo"
```

---

### Task 13: Fiação final — `app/main.py`

**Files:**
- Create: `app/main.py`
- Test: `tests/test_vision_loop.py` (lógica do laço com detector/câmeras fake)

**Interfaces:**
- Consumes: tudo das tasks anteriores.
- Produces: `python -m app.main` sobe o sistema completo; funções puras `make_filters(stable_frames: int) -> dict` e `process_frame(detections_discard, detections_hand, filters, tracker)` testáveis sem hardware. `filters` é `{"discard": StabilityFilter, "hand": StabilityFilter}`.

- [ ] **Step 1: Escrever teste do laço — `tests/test_vision_loop.py`**

```python
from app.cards import Card
from app.detector import Detection
from app.main import make_filters, process_frame
from app.tracker import GameTracker


def det(code, conf=0.9):
    return Detection(card=Card.from_label(code), confidence=conf,
                     box=(0, 0, 10, 10))


def hand(*codes):
    return [det(c) for c in codes]

HAND9 = ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"]


def test_full_turn_through_process_frame():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)

    # mão inicial estável (3 frames)
    for _ in range(3):
        process_frame([], hand(*HAND9), filters, tracker)
    assert tracker.events == []

    # compra: mão passa a ter 10 cartas estáveis
    for _ in range(3):
        process_frame([], hand(*HAND9, "KC"), filters, tracker)
    assert [e.type for e in tracker.events] == ["draw"]

    # descarte: QS aparece estável no lixo
    for _ in range(3):
        process_frame([det("QS")], hand(*HAND9, "KC"), filters, tracker)
    assert [e.type for e in tracker.events] == ["draw", "discard"]


def test_flicker_does_not_emit():
    tracker = GameTracker()
    filters = make_filters(stable_frames=3)
    process_frame([det("QS")], [], filters, tracker)
    process_frame([], [], filters, tracker)          # sumiu (mão na frente)
    process_frame([det("QS")], [], filters, tracker)
    assert tracker.events == []  # nunca ficou 3 frames estável
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/test_vision_loop.py -v`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` em `app.main`

- [ ] **Step 3: Implementar `app/main.py`**

```python
import threading

import uvicorn

from app.capture import CameraStream
from app.cards import Card
from app.config import config
from app.detector import CardDetector, draw_boxes, hand_codes, pick_top_card
from app.server import create_app
from app.stability import StabilityFilter
from app.tracker import GameTracker


def make_filters(stable_frames: int):
    return {"discard": StabilityFilter(stable_frames),
            "hand": StabilityFilter(stable_frames)}


def process_frame(detections_discard, detections_hand, filters, tracker):
    """Um passo do laço de visão. Puro: recebe detecções, atualiza o tracker."""
    top = pick_top_card(detections_discard)
    stable_top = filters["discard"].update(top.card.code if top else None)
    if stable_top:
        tracker.on_stable_top_card(Card.from_label(stable_top),
                                   confidence=top.confidence if top else 1.0)

    codes = hand_codes(detections_hand)
    stable_hand = filters["hand"].update(codes if codes else None)
    if stable_hand:
        tracker.on_stable_hand(frozenset(
            Card.from_label(c) for c in stable_hand))


def vision_loop(cams, detector, filters, tracker, annotated, running):
    while running.is_set():
        detections = {"discard": [], "hand": []}
        for name in detections:
            frame = cams[name].read()
            if frame is None:
                continue  # câmera ainda aquecendo; lista vazia vira None no filtro
            dets = detector.detect(frame)
            detections[name] = dets
            annotated[name] = draw_boxes(frame, dets)
        process_frame(detections["discard"], detections["hand"],
                      filters, tracker)


def main():
    tracker = GameTracker(hand_size=config.hand_size)
    filters = make_filters(config.stable_frames)
    annotated: dict = {}
    cams = {
        "discard": CameraStream(config.discard_cam_index,
                                config.frame_width, config.frame_height),
        "hand": CameraStream(config.hand_cam_index,
                             config.frame_width, config.frame_height),
    }
    detector = CardDetector(config.model_path, config.min_confidence)

    def reset_filters():
        filters["discard"].reset()
        filters["hand"].reset()

    app = create_app(tracker, annotated_frames=annotated,
                     on_new_round=reset_filters)

    running = threading.Event()
    running.set()
    thread = threading.Thread(
        target=vision_loop,
        args=(cams, detector, filters, tracker, annotated, running),
        daemon=True)
    thread.start()

    print(f"overlay: http://{config.server_host}:{config.server_port}/overlay")
    print(f"painel:  http://{config.server_host}:{config.server_port}/painel")
    try:
        uvicorn.run(app, host=config.server_host, port=config.server_port)
    finally:
        running.clear()
        for cam in cams.values():
            cam.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar TODOS os testes**

Run: `pytest -v`
Expected: todos passam

- [ ] **Step 5: Teste ponta a ponta manual**

Run: `python -m app.main`

Roteiro com cartas reais:
1. Abrir `/painel` — os dois previews mostram as câmeras com caixas verdes nas cartas.
2. Segurar 9 cartas em leque na câmera da mão por ~2s (referência criada, sem evento).
3. Adicionar uma 10ª carta → evento **compra (do monte)** aparece no painel e no overlay.
4. Colocar uma carta no campo da câmera do descarte → evento **descarte** aparece.
5. Clicar "corrigir" num evento e trocar a carta → overlay atualiza na hora.
6. "Nova rodada" → tudo zera.
7. No OBS: adicionar Browser Source com URL `http://127.0.0.1:8000/overlay`, largura 800, altura 400 → cartas aparecem com fundo transparente.

Expected: fluxo completo funciona. Anotar erros de reconhecimento para o fine-tuning (Task 14).

- [ ] **Step 6: Commit**

```powershell
git add app/main.py tests/test_vision_loop.py
git commit -m "feat: fiacao completa - camaras, yolo, tracker e servidor"
```

---

### Task 14: Fine-tuning com o setup real

**Files:**
- Create: `training/capture_frames.py`
- Modify: `training/README.md`

**Interfaces:**
- Consumes: `CameraStream` (Task 11), `config` (Task 1).
- Produces: frames em `training/datasets/meu-setup/` para anotação; modelo re-treinado sobrescreve `models/cards.pt`.

- [ ] **Step 1: Criar `training/capture_frames.py`**

```python
"""Captura frames das 2 webcams para montar o dataset de fine-tuning.

Espaço = salva frame das duas câmeras; q = sair.
Capturar ~100-200 frames variados por câmera: cartas diferentes, leque
aberto/fechado, mão em ângulos diferentes, com e sem oclusão parcial.
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.capture import CameraStream  # noqa: E402
from app.config import config  # noqa: E402

OUT = Path(__file__).resolve().parent / "datasets" / "meu-setup"
OUT.mkdir(parents=True, exist_ok=True)

cams = {
    "discard": CameraStream(config.discard_cam_index,
                            config.frame_width, config.frame_height),
    "hand": CameraStream(config.hand_cam_index,
                         config.frame_width, config.frame_height),
}
count = 0
print("espaço = capturar, q = sair")
while True:
    frames = {}
    for name, cam in cams.items():
        frame = cam.read()
        if frame is not None:
            frames[name] = frame
            cv2.imshow(name, frame)
    key = cv2.waitKey(30) & 0xFF
    if key == ord(" "):
        stamp = int(time.time() * 1000)
        for name, frame in frames.items():
            path = OUT / f"{name}_{stamp}.jpg"
            cv2.imwrite(str(path), frame)
        count += 1
        print(f"captura {count}")
    elif key == ord("q"):
        break
for cam in cams.values():
    cam.stop()
cv2.destroyAllWindows()
print(f"{count} capturas em {OUT}")
```

- [ ] **Step 2: Capturar e anotar**

Manual:
1. `python training/capture_frames.py` — capturar 100-200 frames variados por câmera durante uma partida simulada.
2. Subir os frames como novo projeto no Roboflow (ou Label Studio local).
3. Usar o modelo atual para pré-anotar (Roboflow "Auto Label" com upload do `models/cards.pt`, ou anotar os erros na mão) — corrigir apenas o que estiver errado.
4. Exportar em formato YOLO e mesclar com o dataset da Task 12 (mesmos nomes de classe).

- [ ] **Step 3: Re-treinar a partir do modelo atual**

Editar `training/train.py` trocando a linha do modelo base:

```python
model = YOLO(str(ROOT.parent / "models" / "cards.pt"))  # fine-tune do atual
```

E apontar `DATA` para o `data.yaml` do dataset mesclado. Rodar:

```powershell
python training/train.py
```

Expected: novo `models/cards.pt`. Repetir o roteiro ponta a ponta da Task 13 e medir: ≥95% dos descartes e ≥90% das compras detectados corretamente numa partida de teste (critério de aceite do spec). Se não bater, capturar mais frames dos casos que erram e repetir.

- [ ] **Step 4: Atualizar `training/README.md`**

Adicionar ao final:

```markdown
## Fine-tuning

1. `python training/capture_frames.py` durante uma partida simulada
2. Anotar no Roboflow/Label Studio (pré-anotar com o modelo atual)
3. Mesclar com o dataset base, editar `train.py` p/ partir de `models/cards.pt`
4. `python training/train.py` e repetir o teste ponta a ponta

Meta de aceite: ≥95% descartes, ≥90% compras numa partida de teste.
```

- [ ] **Step 5: Commit**

```powershell
git add training/capture_frames.py training/README.md
git commit -m "feat: fluxo de fine-tuning com frames do setup real"
```
