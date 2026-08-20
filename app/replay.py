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


def aplica_overrides(pares: list[str]) -> dict:
    """`--set nome=valor`, com o tipo vindo do valor atual da config.

    Mora aqui, e não no `scripts/replay.py` onde nasceu, porque desde
    2026-08-20 há DOIS instrumentos que varrem parâmetros contra uma gravação
    (a nota de compra/descarte e a nota de leitura da mão). Duas cópias desta
    conversão divergiriam em silêncio, e o sintoma seria o pior possível: duas
    medições do mesmo parâmetro discordando sem motivo aparente.

    `merge_factor` é caso especial: mora em `detector.MERGE_FACTOR`, não na
    config. Deixá-lo de fora só porque está em outro módulo esconderia um dos
    experimentos mais baratos — foi o parâmetro do bug mais caro do projeto.
    """
    from app import detector as detector_mod

    aplicados = {}
    for par in pares:
        nome, _, valor = par.partition("=")
        nome = nome.strip()
        if nome == "merge_factor":
            detector_mod.MERGE_FACTOR = float(valor)
            aplicados[nome] = float(valor)
            continue
        if not hasattr(config, nome):
            raise SystemExit(f"config não tem '{nome}'")
        atual = getattr(config, nome)
        if isinstance(atual, bool):
            convertido = valor.lower() in ("1", "true", "sim")
        else:
            convertido = type(atual)(valor)
        setattr(config, nome, convertido)
        aplicados[nome] = convertido
    return aplicados


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
    com_imagem = 0
    ultimo_ts = 0.0

    for rec in registros:
        if rec["t"] != "frame":
            continue
        frames += 1
        if rec.get("v", -1) >= 0:
            com_imagem += 1
        i, ts = rec["i"], rec.get("ts", 0.0)
        ultimo_ts = max(ultimo_ts, ts)
        antes = len(tracker.events)
        process_frame(detections_do_registro(rec, config.min_confidence),
                      tracker, hand_view, hand_lock, verbose=False)
        # registra toda mudança do que está NA TELA, inclusive de ORDEM e o
        # esvaziamento — tem de bater exatamente com o que o `SessionRecorder`
        # grava ao vivo, senão a checagem de fidelidade não vale nada
        atual = list(hand_lock.cards)
        if (atual if not maos else maos[-1]["cards"] != atual):
            maos.append({"i": i, "ts": ts, "cards": atual})
        for ev in tracker.events[antes:]:
            eventos.append({"i": i, "ts": ts, "ev_id": ev.id, "tipo": ev.type,
                            "carta": ev.card.code, "fonte": ev.source})

    # O FPS que importa é o das voltas COM IMAGEM: é ele que converte os
    # parâmetros contados em frames para segundos. Contar as voltas vazias
    # (câmera aquecendo ou caída, quando o laço gira a milhares por segundo
    # sem inferência) reportava 253 fps numa partida que rodou a 35, e a
    # tradução de `lock_frames` saía dez vezes menor que a real.
    uteis = com_imagem or frames
    return {"frames": frames, "com_imagem": com_imagem, "duracao": ultimo_ts,
            "fps": uteis / ultimo_ts if ultimo_ts else 0.0,
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
