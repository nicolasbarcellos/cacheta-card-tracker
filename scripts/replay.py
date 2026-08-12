"""Repete uma partida gravada pelo pipeline, offline e em segundos.

É o instrumento que quebra o custo de iteração: antes, testar uma mudança de
parâmetro exigia jogar OUTRA partida de 20 minutos, e nem assim era comparável
(a partida seguinte é outra partida). Com a gravação, a mesma sequência de
detecções passa por quantas configurações se queira, e a diferença nos eventos
é atribuível só ao parâmetro.

O núcleo mora em `app/replay.py` e usa `app.main.process_frame` de propósito,
e não uma reimplementação: o pipeline medido aqui é literalmente o que roda na
partida. Por isso o modo padrão confere a FIDELIDADE — um replay sem override
tem de reproduzir os eventos que saíram ao vivo.

    python scripts/replay.py gravacoes/20260811-201500
    python scripts/replay.py gravacoes/... --gabarito
    python scripts/replay.py gravacoes/... --set lock_frames=20 --set fan_win_margin=2.0
    python scripts/replay.py gravacoes/... --varre lock_frames=15,20,25,30,40 --gabarito
    python scripts/replay.py gravacoes/... --eventos --json eventos.json

    # testar um MODELO novo contra a mesma partida (roda o modelo no vídeo)
    python scripts/replay.py gravacoes/... --redetectar models/cards_novo.pt
    python scripts/replay.py gravacoes/... --dets sessao-cards_novo.jsonl --gabarito

LIMITE que não é óbvio: as detecções gravadas já passaram pelo `min_confidence`
da partida (0.30). O replay pode SUBIR esse limiar — que só filtra o que foi
gravado — mas nunca baixá-lo. Para isso é preciso re-detectar do vídeo.
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import detector as detector_mod      # noqa: E402
from app.config import config                 # noqa: E402
from app.replay import carrega, consistencia, roda   # noqa: E402
from app.scoring import imprime, nota         # noqa: E402


def aplica_overrides(pares: list[str]) -> dict:
    """`--set nome=valor`, com o tipo vindo do valor atual da config.

    `merge_factor` é caso especial: mora em `detector.MERGE_FACTOR`, não na
    config. Deixá-lo de fora só porque está em outro módulo esconderia um dos
    experimentos mais baratos — foi o parâmetro do bug mais caro do projeto.
    """
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


def diferencas_de_config(gravacao: Path, aplicados: dict) -> dict:
    """O que mudou entre a config da gravação e a de agora.

    A gravação carrega no `meta.json` a config que a produziu. Sem comparar,
    a checagem de fidelidade acusaria divergência toda vez que um parâmetro
    fosse afinado no `config.py` — e um aviso que grita sempre deixa de ser
    lido, justamente o que não pode acontecer com este.
    """
    meta = gravacao / "meta.json"
    if not meta.exists():
        return dict(aplicados)
    antiga = json.loads(meta.read_text(encoding="utf-8")).get("config") or {}
    atual = asdict(config)
    # Os dois sentidos: um parâmetro NOVO (ausente na gravação) muda o
    # comportamento tanto quanto um alterado, e foi o que escapou na primeira
    # versão — `fan_borda` nem existia quando a partida foi gravada, então
    # comparar só as chaves antigas dizia "nada mudou".
    mudou = {k: f"{antiga[k]} -> {v}" for k, v in atual.items()
             if k in antiga and antiga[k] != v}
    mudou.update({k: f"(novo) {v}" for k, v in atual.items() if k not in antiga})
    mudou.update({k: f"-> {v}" for k, v in aplicados.items() if k not in mudou})
    return mudou


def carrega_gabarito(gravacao: Path, arg) -> list[dict] | None:
    """As jogadas reais, revisadas à mão por `scripts/revisar_partida.py`."""
    if not arg:
        return None
    caminho = gravacao / "gabarito.json" if arg is True else Path(arg)
    if not caminho.exists():
        raise SystemExit(f"sem gabarito em {caminho} — rode antes:\n"
                         f"  python scripts/revisar_partida.py {gravacao}")
    return json.loads(caminho.read_text(encoding="utf-8"))["jogadas"]


def redetecta(gravacao: Path, registros: list[dict], modelo: str,
              passo: int = 1) -> Path:
    """Roda OUTRO modelo sobre o vídeo gravado e salva um novo sessao.jsonl.

    É a razão de o vídeo cru ser gravado. As detecções do `sessao.jsonl`
    original já SÃO a saída do modelo antigo; sem o vídeo, avaliar um retreino
    exigiria jogar outra partida — e aí a comparação mistura "modelo novo" com
    "partida diferente", que é exatamente o que impede concluir qualquer coisa.

    Custo: roda o modelo em todos os frames. Numa partida de 20 min a ~15 fps
    são ~18 mil inferências, dezenas de minutos — desatendido, mas não rápido.
    O resultado fica em disco para não se pagar duas vezes.
    """
    import cv2
    from app.detector import CardDetector

    destino = gravacao / f"sessao-{Path(modelo).stem}.jsonl"
    cap = cv2.VideoCapture(str(gravacao / "mao.avi"))
    if not cap.isOpened():
        raise SystemExit(f"não abriu o vídeo em {gravacao} — a partida foi "
                         f"gravada com --sem-video?")
    det = CardDetector(modelo, config.min_confidence,
                       imgsz=config.detect_imgsz,
                       agnostic_nms=config.agnostic_nms)

    total = sum(1 for r in registros if r["t"] == "frame" and r.get("v", -1) >= 0)
    t0, feitos = time.time(), 0
    with open(destino, "w", encoding="utf-8", buffering=1) as saida:
        for rec in registros:
            if rec["t"] != "frame" or rec.get("v", -1) < 0:
                saida.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue
            ok, frame = cap.read()      # leitura SEQUENCIAL: o registro v=N é
            if not ok:                  # o N-ésimo frame do vídeo, em ordem
                break
            feitos += 1
            if feitos % passo:
                # frame pulado vira "sem detecção", o que o pipeline entende
                # como mão fora do quadro — use --passo só para prova rápida
                rec = {**rec, "dets": []}
            else:
                rec = {**rec, "dets": [
                    [d.card.code, round(d.confidence, 4),
                     *(round(float(x), 1) for x in d.box)]
                    for d in det.detect(frame)]}
            saida.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if feitos % 200 == 0:
                falta = (total - feitos) * (time.time() - t0) / feitos
                print(f"  redetectando {feitos}/{total} "
                      f"(~{falta / 60:.0f} min restantes)", flush=True)
    cap.release()
    print(f"detecções do modelo novo em {destino}")
    return destino


def resumo(res: dict, cons: dict, rotulo: str = ""):
    print(f"--- {rotulo}" if rotulo else "---")
    if res["fps"]:
        # sem caracteres fora do cp1252: o terminal do Windows quebra a saída
        # inteira num UnicodeEncodeError quando o stdout é redirecionado
        vazios = res["frames"] - res["com_imagem"] if res["com_imagem"] else 0
        nota_vazios = f" (+{vazios} voltas sem imagem)" if vazios else ""
        print(f"  {res['com_imagem'] or res['frames']} frames em "
              f"{res['duracao']:.0f}s = {res['fps']:.1f} fps{nota_vazios} | "
              f"lock_frames={config.lock_frames} ~ "
              f"{config.lock_frames / res['fps']:.1f}s")
    print(f"  {cons['compras']} compras · {cons['descartes']} descartes · "
          f"{cons['turnos_completos']} turnos completos")
    if cons["violacoes"]:
        print(f"  {len(cons['violacoes'])} quebras de alternância:")
        for v in cons["violacoes"][:15]:
            print(f"    t={v['ts']:7.1f}s  {v['tipo']} {v['carta']} "
                  f"repetido (evento #{v['pos'] + 1})")
        if len(cons["violacoes"]) > 15:
            print(f"    ... e mais {len(cons['violacoes']) - 15}")
    else:
        print("  alternância compra/descarte perfeita")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gravacao", type=Path)
    ap.add_argument("--set", action="append", default=[], metavar="NOME=VALOR",
                    help="sobrescreve um parâmetro da config (ou merge_factor)")
    ap.add_argument("--varre", metavar="NOME=v1,v2,v3",
                    help="roda um replay por valor e compara os resultados")
    ap.add_argument("--dets", type=Path,
                    help="usa outro arquivo de detecções (ex.: de --redetectar)")
    ap.add_argument("--redetectar", metavar="MODELO.pt",
                    help="roda outro modelo sobre o vídeo antes do replay")
    ap.add_argument("--passo", type=int, default=1,
                    help="com --redetectar, detecta 1 frame a cada N (prova rápida)")
    ap.add_argument("--gabarito", nargs="?", const=True, default=None,
                    metavar="ARQUIVO",
                    help="dá a NOTA contra as jogadas reais (padrão: "
                         "gabarito.json da própria gravação)")
    ap.add_argument("--json", type=Path, help="salva os eventos num arquivo")
    ap.add_argument("--eventos", action="store_true",
                    help="lista todos os eventos, um por linha")
    args = ap.parse_args()

    origem = args.gravacao / "sessao.jsonl"
    if args.dets:
        origem = args.dets if args.dets.exists() else args.gravacao / args.dets
    registros = carrega(origem)
    if args.redetectar:
        registros = carrega(redetecta(args.gravacao, registros,
                                      args.redetectar, args.passo))
    gravados = [r for r in registros if r["t"] == "evento"]
    gabarito = carrega_gabarito(args.gravacao, args.gabarito)

    if args.varre:
        nome, _, valores = args.varre.partition("=")
        for valor in valores.split(","):
            aplica_overrides(args.set + [f"{nome}={valor}"])
            res = roda(registros)
            resumo(res, consistencia(res["eventos"]), f"{nome}={valor}")
            if gabarito:
                # detalhe desligado: numa varredura o que interessa é a curva
                # do acerto, não a lista de erros de cada configuração
                imprime(nota(gabarito, res["eventos"]), detalhar=False)
        return

    aplicados = aplica_overrides(args.set)
    if aplicados:
        print(f"config: {aplicados}")
    res = roda(registros)
    resumo(res, consistencia(res["eventos"]), f"replay de {args.gravacao.name}")

    if gravados and not args.redetectar:
        mudou = diferencas_de_config(args.gravacao, aplicados)
        if mudou:
            # Divergir é o ESPERADO quando a config mudou — foi para isso que
            # o replay existe. Chamar isso de falha de fidelidade treinaria a
            # ignorar o aviso, que é justamente o que não pode acontecer com
            # ele: fora desse caso, divergência significa estado não gravado.
            print(f"  config mudou desde a gravação, fidelidade não se "
                  f"aplica: {mudou}")
        else:
            iguais = ([(e["tipo"], e["carta"]) for e in res["eventos"]]
                      == [(e["tipo"], e["carta"]) for e in gravados])
            print(f"  fidelidade: {'OK' if iguais else 'DIVERGIU'} "
                  f"({len(res['eventos'])} no replay × {len(gravados)} ao vivo)")

    if gabarito:
        print(f"\nnota contra {len(gabarito)} jogadas reais:")
        imprime(nota(gabarito, res["eventos"]))

    if args.eventos:
        print()
        for n, e in enumerate(res["eventos"], 1):
            fonte = f" ({e['fonte']})" if e["fonte"] else ""
            print(f"  {n:3d}  t={e['ts']:7.1f}s  frame={e['i']:6d}  "
                  f"{e['tipo']:8s} {e['carta']}{fonte}")

    if args.json:
        args.json.write_text(json.dumps(res, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        print(f"\neventos salvos em {args.json}")


if __name__ == "__main__":
    main()
