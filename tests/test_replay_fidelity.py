"""A gravação tem de capturar TUDO o que o pipeline precisa para se repetir.

Este teste guarda a única promessa que sustenta a medição offline: replay sem
override reproduz a partida ao pé da letra. Se um dia alguém acrescentar ao
`process_frame` uma entrada que a gravação não registra (a hora, um frame de
outra câmera, um contador global), o replay vai divergir e toda conclusão
tirada dele passa a ser ficção — é aqui que isso aparece.

Usa o pipeline montado pela CONFIG REAL (`build_pipeline`), não parâmetros de
teste: o que se está afirmando é sobre a partida de verdade. Por isso os
contadores de frames são generosos — `lock_frames=30` mais `fan_expire=24`
mais o decaimento do `StableHand` somam bem mais que os 4 frames dos testes
rápidos.
"""

from app.cards import Card
from app.config import config
from app.detector import Detection
from app.main import build_pipeline, process_frame
from app.recorder import SessionRecorder
from app.replay import carrega, roda
from app.tracker import GameTracker

HAND9 = ["AS", "2S", "3S", "4H", "5H", "6H", "7D", "8D", "9D"]
BASE = list(zip(HAND9, range(0, 900, 100)))


def mao(pares):
    """Detecções com a geometria REAL do índice de canto: 44x84, estreito e alto.

    Caixa quadrada aqui não exercitaria o raio de fusão do `hand_instances`,
    que sai da MENOR dimensão — foi exatamente o que escondeu por meses o bug
    mais caro do projeto.
    """
    return [Detection(card=Card.from_label(code), confidence=0.9,
                      box=(x, 100, x + 44, 184)) for code, x in pares]


def test_replay_reproduz_a_partida_gravada(tmp_path):
    rec = SessionRecorder(base_dir=tmp_path, gravar_video=False, config=config)
    tracker = GameTracker(hand_size=config.hand_size)
    hand_view, hand_lock = build_pipeline()

    def alimenta(pares, n):
        dets = mao(pares)
        for _ in range(n):
            i = rec.frame(dets)
            process_frame(dets, tracker, hand_view, hand_lock,
                          recorder=rec, i=i, verbose=False)

    compra = BASE + [("KC", 900)]
    # descarta o 9D; as outras cartas NÃO mudam de lugar, para o teste medir
    # a fidelidade do replay e não a reacomodação das vagas
    descarte = [p for p in BASE if p[0] != "9D"] + [("KC", 900)]

    alimenta(BASE, 60)
    alimenta(compra, 60)
    alimenta(descarte, 120)     # a vaga do 9D precisa expirar antes de sair
    rec.close()

    ao_vivo = [(e.type, e.card.code) for e in tracker.events]
    assert ao_vivo == [("draw", "KC"), ("discard", "9D")]

    res = roda(carrega(rec.dir / "sessao.jsonl"))
    assert [(e["tipo"], e["carta"]) for e in res["eventos"]] == ao_vivo
    assert res["frames"] == 240


def test_gravacao_guarda_as_deteccoes_brutas(tmp_path):
    """Brutas, antes do `hand_instances`.

    Se gravasse as deduplicadas, o `MERGE_FACTOR` já estaria consumido e o
    replay não poderia mexer nele — justamente o parâmetro do bug que sobreviveu
    meses por não ser mensurável.
    """
    rec = SessionRecorder(base_dir=tmp_path, gravar_video=False, config=config)
    # duas leituras do MESMO canto (a 3 px), que o hand_instances funde em uma
    dets = mao([("AS", 0)]) + mao([("AS", 3)])
    rec.frame(dets)
    rec.close()

    registros = carrega(rec.dir / "sessao.jsonl")
    frames = [r for r in registros if r["t"] == "frame"]
    assert len(frames[0]["dets"]) == 2


def test_gravacao_amarra_o_evento_ao_frame_que_o_gerou(tmp_path):
    """Sem o índice do frame, a revisão não teria imagem para mostrar."""
    rec = SessionRecorder(base_dir=tmp_path, gravar_video=False, config=config)
    tracker = GameTracker(hand_size=config.hand_size)
    hand_view, hand_lock = build_pipeline()
    for n in range(120):
        pares = BASE if n < 60 else BASE + [("KC", 900)]
        dets = mao(pares)
        i = rec.frame(dets)
        process_frame(dets, tracker, hand_view, hand_lock,
                      recorder=rec, i=i, verbose=False)
    rec.close()

    registros = carrega(rec.dir / "sessao.jsonl")
    eventos = [r for r in registros if r["t"] == "evento"]
    indices = {r["i"] for r in registros if r["t"] == "frame"}
    assert eventos and eventos[0]["carta"] == "KC"
    assert eventos[0]["i"] in indices
