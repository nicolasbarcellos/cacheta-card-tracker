"""Extrai o frame em que o modelo erra o NAIPE de uma carta que ele vê bem.

Irmão do `extrai_dificeis.py`, e com a mesma fonte de verdade — a vaga do
`FanReader` — mas atacando o outro defeito. Lá a carta some e o rótulo diz qual
era; aqui a carta está bem visível, o modelo a lê com confiança ALTA e erra o
naipe dentro da mesma cor.

Medido em 2026-08-26, nas oito gravações com vídeo: é o que sobra da contradição
depois de descontar a transição. Na partida das 14:12, o `A♣` foi lido como `A♠`
com 0,85-0,91 em 76 frames, com o índice inteiro e bem iluminado — e a votação
temporal do leitor corrigiu. **A tela estava certa; o modelo é que erra.**

## Por que só a troca de naipe na MESMA COR

Porque é a única família em que a discordância entre o frame e a vaga é
confiável. Sem esse filtro saem 8.448 pares, dominados por coisas impossíveis
(`2S->AH`, `KC->5D`): o leque sendo REARRANJADO, com a vaga herdando a posição
de outra carta. Três filtros geométricos foram tentados contra isso e nenhum
separou — a vaga certa e a vaga velha ficam a poucos px uma da outra. O que
separa é a plausibilidade do par, e depois o olho.

Com o filtro, sobram ~118 candidatos, e a auditoria aprova a grande maioria:
`J♣` lido J♠, `A♣` lido A♠, `6♣` lido 6♠, `2♥` lido 2♦, `9♥` lido 9♦.

## As guardas, e por que o frame INTEIRO é rotulado

Rotular só a carta corrigida deixaria os outros índices visíveis SEM rótulo, que
é o envenenamento que este repositório documenta (o modelo aprende que índice é
fundo). Então todas as vagas casadas entram no arquivo, cada uma com o rótulo
que a votação estabeleceu — e o frame é recusado se alguma detecção forte não
corresponder a vaga nenhuma (carta na mesa, canto invertido).

Uso:
    python training/extrai_classe.py gravacoes/<data> --so-analise
    python training/extrai_classe.py gravacoes/<data>
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import config  # noqa: E402
from app.detector import hand_instances  # noqa: E402
from app.main import build_pipeline, process_frame  # noqa: E402
from app.replay import carrega, detections_do_registro  # noqa: E402
from app.tracker import GameTracker  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extrai_dificeis import casa_vagas, contato  # noqa: E402

ROOT = Path(__file__).resolve().parent
COR = {"S": "p", "C": "p", "H": "v", "D": "v"}

CONF_ERRO = 0.80       # o modelo tem de estar CONFIANTE — senão não é este defeito
CONF_FORTE = 0.30      # o limiar do app: detecção que TEM de casar com vaga
DIST_MAX = 12          # px: casamento inequívoco entre detecção e vaga
FOLGA = 3.0            # a segunda vaga tem de estar tantas vezes mais longe
POR_PAR = 12           # teto por par de cartas, para um erro não dominar
INTERVALO = 1.0        # s entre amostras do mesmo par


def mesma_cor(a: str, b: str) -> bool:
    """`a` e `b` são a mesma carta com naipe trocado DENTRO da mesma cor."""
    return a[:-1] == b[:-1] and a[-1] != b[-1] and COR[a[-1]] == COR[b[-1]]


def acha_candidatos(registros, por_par, intervalo):
    """Frames em que o modelo erra o naipe de uma carta que a vaga já sabe.

    A vaga só vale como verdade se estiver VIVA (`misses == 0`, ou seja alguma
    detecção votou nela neste frame) e NA TELA — sem isso entram vagas com
    rótulo velho, que foi o que envenenou as três primeiras tentativas.
    """
    tracker = GameTracker(hand_size=config.hand_size)
    leitor, trava = build_pipeline()
    candidatos, pares = [], Counter()
    ultimo: dict = {}
    for rec in registros:
        if rec.get("t") != "frame":
            continue
        dets = detections_do_registro(rec, config.min_confidence)
        process_frame(dets, tracker, leitor, trava, verbose=False)
        if leitor.congelado or rec.get("v", -1) < 0:
            continue
        na_tela = set(c.code for c in tracker.hand_view)
        vagas = [v for v in leitor.slots_debug()
                 if v["label"] and v["misses"] == 0 and v["label"] in na_tela
                 and v["n"] >= config.fan_window // 2]
        if len(vagas) < 4:
            continue
        for d in leitor.ultimo_leque:
            if d.confidence < CONF_ERRO:
                continue
            cx = (d.box[0] + d.box[2]) / 2
            ds = sorted(vagas, key=lambda s: abs(s["x"] - cx))
            d1 = abs(ds[0]["x"] - cx)
            d2 = abs(ds[1]["x"] - cx) if len(ds) > 1 else 9e9
            if d1 >= DIST_MAX or d2 <= FOLGA * max(d1, 5):
                continue
            if not mesma_cor(d.card.code, ds[0]["label"]):
                continue
            par = f"{d.card.code}->{ds[0]['label']}"
            if (pares[par] >= por_par
                    or rec["ts"] - ultimo.get(par, -9e9) < intervalo):
                continue
            pares[par] += 1
            ultimo[par] = rec["ts"]
            candidatos.append({
                "v": rec["v"], "ts": rec["ts"], "par": par,
                "certo": ds[0]["label"], "lido": d.card.code,
                "conf": round(d.confidence, 3),
                "box": [int(b) for b in d.box],
                "vagas": [(v["x"], v["y"], v["label"]) for v in vagas],
            })
            break          # um por frame: o resto do frame já vai no rótulo
    return candidatos, pares


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--por-par", type=int, default=POR_PAR)
    ap.add_argument("--intervalo", type=float, default=INTERVALO)
    ap.add_argument("--so-analise", action="store_true")
    args = ap.parse_args()

    registros = carrega(args.gravacao / "sessao.jsonl")
    candidatos, pares = acha_candidatos(registros, args.por_par, args.intervalo)
    print(f"{args.gravacao.name}: {len(candidatos)} candidatos "
          f"(troca de naipe na MESMA COR, o modelo a >= {CONF_ERRO})")
    for par, n in pares.most_common(8):
        print(f"  {par}: {n}")
    if args.so_analise or not candidatos:
        return
    video = args.gravacao / "mao.avi"
    if not video.exists():
        raise SystemExit(f"sem video em {video}")

    from ultralytics import YOLO  # import tardio: pesado
    nomes = YOLO(config.model_path).names
    name_to_id = {nome: i for i, nome in nomes.items()}
    from app.detector import CardDetector
    det = CardDetector(config.model_path, config.min_confidence,
                       imgsz=config.detect_imgsz)

    dst = args.saida or (ROOT / "datasets" / "real"
                         / f"{args.gravacao.name}-classe")
    for sub in ("images", "labels", "review"):
        (dst / sub).mkdir(parents=True, exist_ok=True)

    motivos: Counter = Counter()
    corrigidas: Counter = Counter()
    recortes, salvos = [], 0
    cap = cv2.VideoCapture(str(video))
    v = 0
    for c in candidatos:
        while v < c["v"]:
            if not cap.grab():
                break
            v += 1
        ok, frame = cap.read()
        if not ok:
            break
        v += 1
        h, w = frame.shape[:2]
        fortes = hand_instances([d for d in det.detect(frame)
                                 if d.confidence >= CONF_FORTE])
        casado = casa_vagas(fortes, c["vagas"], config.fan_match_dist)
        if casado is None:
            motivos["deteccao forte sem vaga (carta na mesa?)"] += 1
            continue
        if len(casado) != len(c["vagas"]):
            motivos["vaga sem deteccao no video (MJPG != ao vivo)"] += 1
            continue
        linhas, view = [], frame.copy()
        achou = False
        for i, d in casado.items():
            code = c["vagas"][i][2]
            x1, y1, x2, y2 = (int(b) for b in d.box)
            linhas.append(f"{name_to_id[code]} {(x1 + x2) / 2 / w:.6f} "
                          f"{(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} "
                          f"{(y2 - y1) / h:.6f}")
            corrige = d.card.code != code
            achou |= corrige and mesma_cor(d.card.code, code)
            cor = (255, 0, 255) if corrige else (0, 255, 0)
            cv2.rectangle(view, (x1, y1), (x2, y2), cor, 2 + 1 * corrige)
            cv2.putText(view, f"{code}{'<-' + d.card.code if corrige else ''}",
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 2)
            if corrige:
                corrigidas[f"{d.card.code}->{code}"] += 1
                m = 45
                rx1, ry1 = max(0, x1 - m), max(0, y1 - m)
                rec = frame[ry1:min(h, y2 + m), rx1:min(w, x2 + m)].copy()
                cv2.rectangle(rec, (x1 - rx1, y1 - ry1),
                              (x2 - rx1, y2 - ry1), (255, 0, 255), 2)
                if rec.size:
                    recortes.append((f"{args.gravacao.name}_{c['v']:06d}",
                                     code, d, rec))
        if not achou:
            # o erro sumiu na re-detecção do vídeo: não é mais amostra difícil
            motivos["o video nao reproduz o erro (MJPG)"] += 1
            continue
        nome = f"{args.gravacao.name}_{c['v']:06d}"
        cv2.imwrite(str(dst / "images" / f"{nome}.jpg"), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        (dst / "labels" / f"{nome}.txt").write_text("\n".join(linhas))
        cv2.imwrite(str(dst / "review" / f"{nome}.jpg"), view,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])
        salvos += 1
    cap.release()

    print(f"\n{salvos} frames salvos em {dst}")
    total = salvos + sum(motivos.values())
    for motivo, n in motivos.most_common():
        print(f"  descartados por {motivo}: {n} ({100 * n / max(total, 1):.0f}%)")
    print("\ncorrecoes (o modelo lia -> o rotulo correto):")
    for k, n in corrigidas.most_common(12):
        print(f"  {k}: {n}")
    if recortes:
        cv2.imwrite(str(dst / "contato.jpg"), contato(recortes),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"\nfolha de contato: {dst / 'contato.jpg'} — OLHE antes de treinar")
    (dst / "classe.json").write_text(json.dumps(
        {n: {"rotulo": lb, "modelo_viu": d.card.code,
             "confianca": round(d.confidence, 3)}
         for n, lb, d, _r in recortes}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
