"""Revisa os eventos de uma partida gravada e produz o GABARITO.

O gabarito é a lista das jogadas que de fato aconteceram. Sem ele não existe
meta de aceite: ">=95% dos descartes corretos" precisa de um denominador, e o
denominador é o que o jogador fez, não o que o sistema emitiu.

Revisar frame a frame uma partida de 20 min seria inviável; revisar EVENTO a
evento não é. Cada evento é um clique, e o que a tela mostra é o frame exato em
que ele saiu, com a mão antes e depois — a diferença entre as duas É a jogada
que o sistema entendeu, então dá para julgar sem reconstruir nada de cabeça.

    python scripts/revisar_partida.py gravacoes/20260811-201500

Teclas:
    c        a jogada esta certa
    e        carta errada -> digite o codigo certo (ex.: 10C) e Enter
    f        fantasma: nao houve jogada nenhuma aqui
    p        faltou uma jogada ANTES desta -> tipo e carta
    , .      andar 5 frames para tras / para frente (para enxergar melhor)
    z        voltar ao evento anterior
    q        salvar e sair

Salva `gabarito.json` na pasta da gravação e imprime a nota na hora.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cards import Card, InvalidCardLabel   # noqa: E402
from app.scoring import imprime, nota          # noqa: E402

JANELA = "revisao"
FONTE = cv2.FONT_HERSHEY_SIMPLEX


def carrega(gravacao: Path) -> list[dict]:
    registros = []
    with open(gravacao / "sessao.jsonl", encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                registros.append(json.loads(linha))
    return registros


class Filme:
    """Acesso ao frame de um índice do JSONL.

    Se a partida foi gravada com `--sem-video`, cai para um desenho das caixas
    detectadas sobre fundo preto: perde-se a carta real, mas o que o modelo
    leu — que é metade do diagnóstico — continua visível.
    """

    def __init__(self, gravacao: Path, registros: list[dict]):
        self.frames = {r["i"]: r for r in registros if r["t"] == "frame"}
        self.cap = None
        caminho = gravacao / "mao.avi"
        if caminho.exists():
            cap = cv2.VideoCapture(str(caminho))
            self.cap = cap if cap.isOpened() else None
        if self.cap is None:
            print("sem vídeo na gravação: mostrando só as caixas detectadas")

    def imagem(self, i: int):
        rec = self.frames.get(i)
        if rec is None:
            return None, []
        dets = rec.get("dets", [])
        if self.cap is not None and rec.get("v", -1) >= 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, rec["v"])
            ok, frame = self.cap.read()
            if ok:
                return frame, dets
        import numpy as np
        return np.zeros((1080, 1920, 3), dtype="uint8"), dets


def desenha(frame, dets, cabecalho: list[str], rodape: list[str]):
    img = frame.copy()
    for code, conf, x1, y1, x2, y2 in dets:
        p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
        cv2.rectangle(img, p1, p2, (0, 220, 0), 2)
        cv2.putText(img, f"{code} {conf:.2f}", (p1[0], max(14, p1[1] - 6)),
                    FONTE, 0.5, (0, 220, 0), 1, cv2.LINE_AA)
    escala = 1280 / img.shape[1]
    img = cv2.resize(img, None, fx=escala, fy=escala)

    alto = 22 * len(cabecalho) + 16
    painel = img.copy()
    cv2.rectangle(painel, (0, 0), (img.shape[1], alto), (0, 0, 0), -1)
    img = cv2.addWeighted(painel, 0.65, img, 0.35, 0)
    for n, linha in enumerate(cabecalho):
        cv2.putText(img, linha, (12, 24 + n * 22), FONTE, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
    base = img.shape[0] - 22 * len(rodape) - 10
    for n, linha in enumerate(rodape):
        cv2.putText(img, linha, (12, base + n * 22), FONTE, 0.55,
                    (0, 255, 255), 1, cv2.LINE_AA)
    return img


def digita(desenhar, prompt: str) -> str | None:
    """Entrada de texto DENTRO da janela do OpenCV.

    Perguntar no terminal congelaria a janela no Windows (sem `waitKey` o
    OpenCV não repinta), e o frame é justamente o que se precisa olhar para
    responder. Esc cancela.
    """
    buffer = ""
    while True:
        cv2.imshow(JANELA, desenhar(f"{prompt}: {buffer}_"))
        k = cv2.waitKey(30) & 0xFF
        if k in (13, 10):
            return buffer.strip()
        if k == 27:
            return None
        if k == 8:
            buffer = buffer[:-1]
        elif 32 <= k < 127:
            buffer += chr(k).upper()


def pede_carta(desenhar, prompt: str) -> str | None:
    while True:
        texto = digita(desenhar, prompt)
        if texto is None:
            return None
        try:
            return Card.from_label(texto).code
        except (InvalidCardLabel, IndexError):
            continue


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    args = ap.parse_args()

    registros = carrega(args.gravacao)
    eventos = [r for r in registros if r["t"] == "evento"]
    maos = [r for r in registros if r["t"] == "mao"]
    ts_de = {r["i"]: r.get("ts", 0.0) for r in registros if r["t"] == "frame"}
    if not eventos:
        raise SystemExit("a gravação não tem evento nenhum para revisar")

    filme = Filme(args.gravacao, registros)
    cv2.namedWindow(JANELA, cv2.WINDOW_NORMAL)

    def mao_ate(i, antes=False):
        anteriores = [m for m in maos if m["i"] <= i]
        if antes:
            anteriores = anteriores[:-1]
        return anteriores[-1]["cards"] if anteriores else []

    veredito: list[dict | None] = [None] * len(eventos)
    perdidos: list[list[dict]] = [[] for _ in eventos]
    n = 0
    while 0 <= n < len(eventos):
        ev = eventos[n]
        i = ev["i"]
        offset = 0
        while True:
            frame, dets = filme.imagem(i + offset)
            if frame is None:
                frame, dets = filme.imagem(i)
                offset = 0
            marca = f"  [frame {offset:+d}]" if offset else ""
            tipo_pt = "COMPRA " if ev["tipo"] == "draw" else "DESCARTE"
            cab = [
                f"evento {n + 1}/{len(eventos)}   t={ts_de.get(i, 0):.1f}s"
                f"   {tipo_pt} {ev['carta']}"
                + (f" ({ev['fonte']})" if ev.get("fonte") else "") + marca,
                f"mao antes:  {' '.join(mao_ate(i, antes=True))}",
                f"mao depois: {' '.join(mao_ate(i))}",
            ]
            if perdidos[n]:
                cab.append("perdidas marcadas antes deste: "
                           + ", ".join(f"{p['tipo']} {p['carta']}"
                                       for p in perdidos[n]))
            rod = ["c certo   e carta errada   f fantasma   "
                   "p faltou jogada antes", ", . andar frames   z voltar   "
                   "q salvar e sair"]

            def desenhar(extra=None, _f=frame, _d=dets, _c=cab, _r=rod):
                return desenha(_f, _d, _c, _r + ([extra] if extra else []))

            cv2.imshow(JANELA, desenhar())
            k = cv2.waitKey(0) & 0xFF
            if k == ord(","):
                offset -= 5
                continue
            if k == ord("."):
                offset += 5
                continue
            if k == ord("c"):
                veredito[n] = {"situacao": "acerto", "tipo": ev["tipo"],
                               "carta": ev["carta"], "ts": ts_de.get(i, 0.0),
                               "i": i}
                n += 1
                break
            if k == ord("e"):
                certa = pede_carta(desenhar, "carta certa")
                if certa:
                    veredito[n] = {"situacao": "carta_errada",
                                   "tipo": ev["tipo"], "carta": certa,
                                   "ts": ts_de.get(i, 0.0), "i": i}
                    n += 1
                    break
                continue
            if k == ord("f"):
                veredito[n] = {"situacao": "fantasma", "tipo": ev["tipo"],
                               "carta": ev["carta"], "ts": ts_de.get(i, 0.0),
                               "i": i}
                n += 1
                break
            if k == ord("p"):
                resp = digita(desenhar, "faltou (c=compra / d=descarte)")
                tipo = "draw" if (resp or "").startswith("C") else "discard"
                carta = pede_carta(desenhar, "carta da jogada perdida")
                if carta:
                    perdidos[n].append({"tipo": tipo, "carta": carta,
                                        "ts": ts_de.get(i, 0.0), "i": i})
                continue
            if k == ord("z"):
                n = max(0, n - 1)
                veredito[n] = None
                break
            if k == ord("q"):
                n = len(eventos)
                break

    cv2.destroyAllWindows()

    # O gabarito é a verdade do campo: as jogadas que aconteceram, em ordem.
    # Fantasma não entra (não houve jogada); carta errada entra com a carta
    # CERTA; perdida entra na posição em que foi marcada.
    gabarito: list[dict] = []
    for n, v in enumerate(veredito):
        for p in perdidos[n]:
            gabarito.append({"tipo": p["tipo"], "carta": p["carta"],
                             "ts": p["ts"], "i": p["i"]})
        if v and v["situacao"] != "fantasma":
            gabarito.append({"tipo": v["tipo"], "carta": v["carta"],
                             "ts": v["ts"], "i": v["i"]})

    revisados = sum(1 for v in veredito if v is not None)
    destino = args.gravacao / "gabarito.json"
    destino.write_text(json.dumps(
        {"revisados": revisados, "total_eventos": len(eventos),
         "jogadas": gabarito}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\ngabarito salvo em {destino} "
          f"({revisados}/{len(eventos)} eventos revisados, "
          f"{len(gabarito)} jogadas reais)")

    if revisados:
        emitidos = [{"tipo": e["tipo"], "carta": e["carta"],
                     "ts": ts_de.get(e["i"], 0.0), "i": e["i"]}
                    for e in eventos[:revisados]]
        print("\nnota da partida como ela saiu ao vivo:")
        imprime(nota(gabarito, emitidos))
        print(f"\nagora dá para iterar offline:\n"
              f"  python scripts/replay.py {args.gravacao} "
              f"--gabarito --set lock_frames=20")


if __name__ == "__main__":
    main()
