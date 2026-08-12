"""Núcleo do replay: refaz o pipeline sobre uma partida gravada.

Fica em `app/` e não em `scripts/` porque é código puro (sem câmera, sem
janela) e porque a promessa que ele carrega precisa de teste: se o replay não
reproduzir exatamente o que saiu ao vivo, existe estado que a gravação não
captura, e nenhuma conclusão tirada offline vale para a partida real.

`tests/test_replay_fidelity.py` é quem guarda essa promessa.
"""

import json
from pathlib import Path

from app.cards import Card
from app.config import config
from app.detector import Detection
from app.main import build_pipeline, process_frame
from app.tracker import GameTracker


def carrega(caminho: Path) -> list[dict]:
    registros = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                registros.append(json.loads(linha))
    return registros


def detections_do_registro(rec: dict, min_conf: float) -> list[Detection]:
    """Reconstrói as detecções de um frame gravado.

    O filtro por confiança aqui é o que permite SUBIR o `min_confidence` no
    replay. Baixá-lo é impossível: o que ficou abaixo do limiar da partida
    nunca foi gravado. Para isso é preciso re-detectar a partir do vídeo.
    """
    out = []
    for code, conf, x1, y1, x2, y2 in rec["dets"]:
        if conf < min_conf:
            continue
        out.append(Detection(card=Card.from_label(code), confidence=conf,
                             box=(x1, y1, x2, y2)))
    return out


def roda(registros: list[dict]) -> dict:
    """Passa os frames gravados pelo pipeline e devolve o que saiu.

    Ignora os registros de `mao` e `evento` da gravação de propósito: eles são
    o RESULTADO da partida, e são justamente o que se quer regerar para
    comparar. Usá-los seria copiar o gabarito da prova.
    """
    tracker = GameTracker(hand_size=config.hand_size)
    hand_view, hand_lock = build_pipeline()
    eventos: list[dict] = []
    maos: list[dict] = []
    frames = 0
    ultimo_ts = 0.0

    for rec in registros:
        if rec["t"] != "frame":
            continue
        frames += 1
        i, ts = rec["i"], rec.get("ts", 0.0)
        ultimo_ts = max(ultimo_ts, ts)
        antes = len(tracker.events)
        process_frame(detections_do_registro(rec, config.min_confidence),
                      tracker, hand_view, hand_lock, verbose=False)
        if hand_lock.cards and (not maos or maos[-1]["cards"] != hand_lock.cards):
            maos.append({"i": i, "ts": ts, "cards": list(hand_lock.cards)})
        for ev in tracker.events[antes:]:
            eventos.append({"i": i, "ts": ts, "ev_id": ev.id, "tipo": ev.type,
                            "carta": ev.card.code, "fonte": ev.source})

    return {"frames": frames, "duracao": ultimo_ts,
            "fps": frames / ultimo_ts if ultimo_ts else 0.0,
            "eventos": eventos, "maos": maos}


def consistencia(eventos: list[dict]) -> dict:
    """Erros que aparecem SEM gabarito, só pela estrutura do jogo.

    Na cacheta o turno é compra→descarte, sempre nessa ordem e sempre
    alternado. Duas compras seguidas significam, portanto, que ou saiu uma
    compra fantasma ou um descarte foi perdido — dá para achar erro antes de
    revisar frame nenhum, e é o que permite comparar duas configurações numa
    partida ainda não revisada.

    Não é medida de ACERTO: uma compra alternada e com a carta errada passa
    limpa por aqui. Serve para triagem, não para a meta de aceite.
    """
    seq = [e["tipo"] for e in eventos]
    violacoes = [{"pos": n + 1, "tipo": b, "carta": eventos[n + 1]["carta"],
                  "ts": eventos[n + 1].get("ts", 0.0)}
                 for n, (a, b) in enumerate(zip(seq, seq[1:])) if a == b]
    turnos = sum(1 for a, b in zip(seq, seq[1:])
                 if a == "draw" and b == "discard")
    return {"eventos": len(eventos), "compras": seq.count("draw"),
            "descartes": seq.count("discard"), "turnos_completos": turnos,
            "violacoes": violacoes}
