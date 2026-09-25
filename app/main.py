import argparse
import threading
import time

import uvicorn

from app.capture import CameraStream
from app.cards import Card
from app.config import config
from app.detector import CardDetector, draw_boxes, hand_instances
from app.hand_reader import FanReader
from app.recorder import SessionRecorder
from app.server import create_app
from app.stable_hand import StableHand
from app.tracker import GameTracker


class FpsMeter:
    """Taxa real do laço de visão.

    Não é vaidade de benchmark: TODOS os parâmetros de tempo do pipeline são
    contados em FRAMES (`lock_frames=30`, `fan_window=30`, `fan_expire=24`), e
    a taxa do laço é o fator de conversão para segundos. Ela varia com a carga
    da GPU e com o que mais estiver aberto na máquina — sem medir, "2 s para
    trocar a mão" é chute, e um parâmetro afinado numa sessão pode significar
    outra coisa na seguinte.
    """

    def __init__(self, intervalo=5.0, agora=time.time):
        self.intervalo = intervalo
        self._agora = agora        # injetável: é o que torna isto testável
        self._n = 0
        self._novos = 0
        self._t = agora()
        self.fps = 0.0
        self.fps_distintos = 0.0

    def tick(self, novo=True):
        """Uma volta do laço. `novo` diz se a câmera entregou imagem NOVA.

        Publicar só a taxa do laço escondia um terço do trabalho da GPU: o
        `CameraStream` guarda o frame mais recente e o laço lê o que estiver
        lá, então quando o laço corre mais que a câmera ele re-infere a MESMA
        imagem. Medido em 2026-09-03 nas dez gravações: 1-37% de repetições, e
        a taxa DISTINTA batendo em 28-32 em todas, girasse o laço a 29 ou a 48.
        A câmera é o teto, não a GPU — e por meses o número publicado aqui foi
        lido como se fosse a taxa de imagens.
        """
        self._n += 1
        self._novos += 1 if novo else 0
        dt = self._agora() - self._t
        if dt >= self.intervalo:
            self.fps = self._n / dt
            self.fps_distintos = self._novos / dt
            repetidos = 100 * (1 - self._novos / self._n) if self._n else 0.0
            # lock_frames é contado em VOLTAS DO LAÇO, e desde 2026-09-16 só a
            # imagem NOVA conta volta — então as duas taxas saem iguais e
            # "repetidos" fica em 0%. Se voltarem a divergir, a volta repetida
            # está de novo alimentando o pipeline de graça.
            print(f"[fps] laço {self.fps:.1f} | câmera {self.fps_distintos:.1f} "
                  f"({repetidos:.0f}% repetidos)  "
                  f"(lock_frames={config.lock_frames} ~ "
                  f"{config.lock_frames / self.fps:.1f}s)", flush=True)
            self._n = 0
            self._novos = 0
            self._t = self._agora()


def log_lock(hand_view, hand_lock):
    """Imprime o que o leitor viu quando a mão exibida mudou.

    Só imprime na mudança, então não polui a saída — e é o único jeito de
    saber, depois do fato, POR QUE uma carta saiu errada: rótulo repetido em
    posições distintas (o modelo leu duas cartas como a mesma) x duas vagas
    no mesmo lugar (o casamento por posição se perdeu).
    """
    print(f"\n=== mão do jogador: {' '.join(hand_lock.cards)}", flush=True)
    for i, s in enumerate(hand_view.slots_debug()):
        top = "  ".join(f"{code}={peso}" for code, peso in s["top"])
        print(f"  vaga {i}: x={s['x']:4d} y={s['y']:4d} "
              f"n={s['n']:3d} miss={s['misses']:2d}  {top}", flush=True)


def process_frame(detections_hand, tracker, hand_view, hand_lock,
                  recorder=None, i=0, verbose=True):
    """Um passo do laço de visão. Puro: recebe detecções, atualiza o tracker.

    Compra e descarte saem os DOIS da câmera da mão, pela mudança do leque:
    cresceu uma carta = compra, encolheu uma = descarte. A câmera do monte não
    gera evento — se gerasse, o descarte sairia duplicado (uma vez pela mão,
    outra pelo monte).

    `recorder` e `i` são só instrumentação: é aqui que a mão exibida e os
    eventos ficam amarrados ao frame que os produziu, que é o que permite ao
    `scripts/revisar_partida.py` mostrar a imagem do instante do erro.
    `scripts/replay.py` chama esta mesma função — por isso o pipeline offline
    é o pipeline de verdade, e não uma reimplementação que pode divergir.
    """
    hand_view.update(hand_instances(detections_hand))
    trocou = hand_lock.update(hand_view.cards, calmo=hand_view.calmo)
    exibida = hand_lock.cards
    cards = [Card.from_label(c) for c in exibida]

    # A saída deste modelo é UMA só: a mão do jogador na tela, atualizada todo
    # frame. Compra e descarte deixaram de ser responsabilidade dele em
    # 2026-08-19 (viram outros modelos, com outras câmeras), então
    # `tracker.on_hand_changed` NÃO é mais chamado aqui — o método continua no
    # tracker, testado, para quem for construir aquilo.
    #
    # `set_hand_display` não faz nada quando a lista é igual à anterior, então
    # chamar a cada frame é barato — e é o que permite a ORDEM do leque
    # acompanhar o que se vê agora, em vez de congelar no instante da trava.
    antes_exibida = list(tracker.hand_view)
    tracker.set_hand_display(cards)
    if trocou and verbose:
        log_lock(hand_view, hand_lock)
    if recorder is not None:
        # grava toda mudança do que está NA TELA, inclusive a de ordem
        if [c.code for c in tracker.hand_view] != [c.code for c in antes_exibida]:
            recorder.mao(i, list(exibida))


def vision_loop(cams, detector, tracker, annotated, running,
                hand_view, hand_lock, recorder=None):
    fps = FpsMeter()
    ultimo_seq = -1
    while running.is_set():
        frame, seq = cams["hand"].read_seq()
        novo = seq != ultimo_seq
        ultimo_seq = seq
        if frame is None:
            # SEM IMAGEM não é "mão fora do quadro". A câmera devolve None
            # enquanto aquece e quando cai, e alimentar o pipeline com lista
            # vazia nesses instantes faria as vagas expirarem por um problema
            # de USB, não por o jogador ter abaixado as cartas. Medido em
            # 2026-08-11: os ~20 s de aquecimento produziram 122 mil voltas
            # vazias (o laço gira a 6000/s sem inferência), que entulhavam a
            # gravação e faziam o FPS médio sair 253 em vez de 35.
            continue
        if not novo:
            # IMAGEM REPETIDA: a volta NÃO conta. Todo parâmetro do pipeline
            # (`lock_frames`, `fan_min_appear`, `fan_expire`...) é contado em
            # VOLTAS DO LAÇO, e elas só valem tempo se custarem alguma coisa.
            #
            # O conserto de 2026-09-14 tirou a inferência da volta repetida e
            # manteve o `process_frame` nela — e com isso a volta repetida
            # passou a custar ZERO. Enquanto a câmera deu 45,8 fps a GPU
            # continuou sendo o teto e ninguém viu. Em 2026-09-16 a câmera caiu
            # para 30 (pouca luz) e o laço disparou a 280-570 voltas/s:
            # `lock_frames=20` passou a valer MENOS DE 0,1 s, e o `min_appear`
            # aceitava vaga de um vulto em ~20 ms. O usuário viu antes do log:
            # "quando eu puxo um leque e a câmera pega um vulto, ela já está
            # lendo as cartas".
            #
            # Contar só imagem NOVA amarra a volta à câmera (30-46/s), que é a
            # faixa em que todos os parâmetros foram medidos (laço de 29-48 nas
            # gravações). E o teste em disco de 2026-09-15 já tinha mostrado
            # que tirar as repetições não move a nota da tela.
            time.sleep(0.002)
            continue
        dets_hand = detector.detect(frame)
        annotated["hand"] = draw_boxes(frame, dets_hand)

        # o índice vem ANTES do processamento: é ele que amarra a mão e os
        # eventos ao frame exato que os gerou
        i = recorder.frame(dets_hand, frame) if recorder is not None else 0
        if recorder is not None:
            recorder.exposicao(i, getattr(cams["hand"], "exposicao_lida", None))
        process_frame(dets_hand, tracker, hand_view, hand_lock,
                      recorder=recorder, i=i)
        fps.tick(True)


def build_pipeline():
    """Monta leitor + histerese com a config vigente.

    Existe para o replay offline montar EXATAMENTE o mesmo pipeline do app —
    duplicar essa montagem em `scripts/replay.py` faria a medição offline
    divergir do que roda na partida sem ninguém perceber.
    """
    hand_view = FanReader(match_dist=config.fan_match_dist,
                          window=config.fan_window,
                          min_appear=config.fan_min_appear,
                          expire=config.fan_expire,
                          # SEM teto de vagas desde 2026-08-19: o leitor não
                          # sabe quantas cartas a mão tem — o mesmo modelo vai
                          # servir a pôquer (2), truco (3), pif-paf e cacheta
                          # (9). O teto matava vaga espúria de graça, e o que
                          # sobrou no lugar dele são as guardas que não
                          # dependem do jogo: `min_appear`, `fan_expire`,
                          # `fan_borda` e o piso de peso da carta duplicada.
                          max_slots=None,
                          win_margin=config.fan_win_margin,
                          frame_w=config.frame_width,
                          frame_h=config.frame_height,
                          borda=config.fan_borda,
                          peso_min=config.fan_peso_min,
                          vao_grupo=config.fan_vao_grupo,
                          ordem_margem=config.fan_ordem_margem,
                          exibe_misses=config.fan_exibe_misses,
                          calmo_max=config.fan_calmo_max)
    hand_lock = StableHand(lock_frames=config.lock_frames)
    return hand_view, hand_lock


def main():
    ap = argparse.ArgumentParser(description="Cacheta card tracker")
    ap.add_argument("--gravar", action="store_true",
                    help="grava a partida em gravacoes/<data> para replay "
                         "offline e medição da meta de aceite")
    ap.add_argument("--sem-video", action="store_true",
                    help="com --gravar, salva só as detecções (~5 MB) em vez "
                         "do vídeo (~7 GB). Barato, mas impede testar um "
                         "MODELO novo contra a partida gravada")
    args = ap.parse_args()

    tracker = GameTracker(hand_size=config.hand_size)
    hand_view, hand_lock = build_pipeline()
    annotated: dict = {}
    # UMA câmera só. A do monte de descarte saiu em 2026-08-19: o projeto
    # passou a ser LER A MÃO, e compra/descarte viraram responsabilidade de
    # outros modelos, com outras câmeras. Ela já não gerava evento desde
    # f5fdf64 — era só preview, e ainda assim consumia USB e uma thread.
    cams = {
        "hand": CameraStream(config.hand_cam_index,
                             config.frame_width, config.frame_height,
                             fps=config.cam_fps,
                             foco=config.cam_foco,
                             exposicao=config.cam_exposicao),
    }
    detector = CardDetector(config.model_path, config.min_confidence,
                            imgsz=config.detect_imgsz,
                            agnostic_nms=config.agnostic_nms)

    recorder = None
    if args.gravar:
        recorder = SessionRecorder(gravar_video=not args.sem_video,
                                   config=config)
        print(f"gravando em {recorder.dir}", flush=True)

    def reset_filters():
        hand_view.reset()
        hand_lock.reset()

    app = create_app(tracker, annotated_frames=annotated,
                     on_new_round=reset_filters,
                     on_relock=hand_lock.force_relock)

    running = threading.Event()
    running.set()
    thread = threading.Thread(
        target=vision_loop,
        args=(cams, detector, tracker, annotated, running,
              hand_view, hand_lock, recorder),
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
        if recorder is not None:
            recorder.close()


if __name__ == "__main__":
    main()
