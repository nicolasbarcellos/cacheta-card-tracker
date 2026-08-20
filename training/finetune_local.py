"""Fine-tuning local: re-treina models/cards.pt com leques sintéticos + reais.

Consome três fontes e mistura todas:

- training/datasets/synthetic/ — gerado por generate_fans.py a partir dos
  moldes do seu baralho. Muitas imagens, variedade fácil, mas é simulação.
- training/datasets/local/     — frames REAIS da sua câmera, capturados por
  capture_auto.py e pré-anotados por auto_annotate.py. Poucas imagens, porém
  é a distribuição que o modelo vai encontrar de verdade.
- training/datasets/real/<partida>/ — frames REAIS de uma partida GRAVADA,
  rotulados pelo gabarito revisado (`extrai_gravacao.py`). Custam zero tempo
  de jogo, e é a única fonte que traz a condição em que o modelo erra ao vivo.
- training/datasets/negativos/<partida>/ — frames SEM carta nenhuma, de rótulo
  vazio (`extrai_negativos.py`). Ensinam o que NÃO é carta: o modelo lia o logo
  da parede da sala como `10C`/`QC` e textura de reboco como `5S 4D KS`, e
  desde 19/08 essas cartas inventadas chegavam à tela.

Uma partida pode ser DEIXADA DE FORA com `--holdout <nome>`: sem isso, medir o
modelo com `replay.py` contra a mesma partida que o treinou é medir decoreba.

Do dataset real só entram os frames cuja imagem em local/review/ sobreviveu:
apagar a foto de revisão é como você rejeita uma anotação errada.

Como o sintético é muito mais numeroso, os frames reais são repetidos algumas
vezes (REAL_TARGET_SHARE) — senão eles se diluem e o treino ignora justamente
o dado que importa.

O modelo antigo fica salvo em models/cards_backup_N.pt.
"""
import argparse
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ultralytics import YOLO  # noqa: E402

ROOT = Path(__file__).resolve().parent
SYNTH = ROOT / "datasets" / "synthetic"
LOCAL = ROOT / "datasets" / "local"
GRAVADAS = ROOT / "datasets" / "real"
NEGATIVOS = ROOT / "datasets" / "negativos"
TRAINSET = ROOT / "datasets" / "fans-split"
MODEL = Path("models/cards.pt")

REAL_TARGET_SHARE = 0.30   # fatia do treino que os frames reais devem ocupar
REAL_MAX_REPEAT = 6        # teto: repetir demais decora o pouco dado real

# Ajustáveis na linha de comando: epochs imgsz batch.
# imgsz alto é necessário (o índice de canto é pequeno e o pip do naipe é o
# primeiro detalhe a se perder), mas 1280 com batch 6 NÃO cabe em 4 GB de VRAM
# — num RTX 3050 Laptop é preciso baixar o batch. Ex.: `... 12 1280 3`.
ap = argparse.ArgumentParser(description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("epochs", nargs="?", type=int, default=12)
ap.add_argument("imgsz", nargs="?", type=int, default=1280)
ap.add_argument("batch", nargs="?", type=int, default=6)
ap.add_argument("--holdout", action="append", default=[], metavar="PARTIDA",
                help="partida de datasets/real/ a NÃO treinar (pode repetir)")
args = ap.parse_args()
EPOCHS, IMGSZ, BATCH = args.epochs, args.imgsz, args.batch


def collect(source, needs_review=False):
    """[(imagem, rótulo)] de um dataset no formato images/ + labels/."""
    pairs = []
    for img in sorted((source / "images").glob("*.jpg")):
        label = source / "labels" / f"{img.stem}.txt"
        if not label.exists():
            continue
        if needs_review and not (source / "review" / img.name).exists():
            continue  # revisão apagada = anotação rejeitada por você
        pairs.append((img, label))
    return pairs


def split_pairs(pairs, seed):
    """Separa validação de treino DENTRO de cada fonte.

    Estratificado de propósito: se sorteasse do bolo misturado, a validação
    poderia sair só de sintético e não mediria nada sobre o dado real.
    """
    pairs = list(pairs)
    random.Random(seed).shuffle(pairs)
    n_val = min(max(1, len(pairs) // 10), max(0, len(pairs) - 1)) if pairs else 0
    return pairs[n_val:], pairs[:n_val]


def main():
    synthetic = collect(SYNTH)
    real = collect(LOCAL, needs_review=True)
    print(f"sintético: {len(synthetic)} imagens ({SYNTH})")
    print(f"real:      {len(real)} imagens revisadas ({LOCAL})")
    # partidas gravadas: mesma regra de revisão (apagar a imagem de review/ é
    # como se rejeita um rótulo), e o holdout fica de fora para sobrar partida
    # com que MEDIR o modelo depois
    for pasta in sorted(p for p in GRAVADAS.glob("*") if p.is_dir()):
        if pasta.name in args.holdout:
            print(f"partida:   {pasta.name} FORA do treino (holdout)")
            continue
        desta = collect(pasta, needs_review=True)
        real += desta
        print(f"partida:   {len(desta)} imagens revisadas ({pasta.name})")
    if len(synthetic) + len(real) < 200:
        sys.exit("dados insuficientes — rode generate_fans.py e/ou "
                 "capture_auto.py + auto_annotate.py")
    if not real:
        print("AVISO: nenhum frame real. O modelo vai treinar só em simulação, "
              "que é o que costuma falhar no setup de verdade.")

    # NEGATIVOS: imagem sem carta nenhuma, rótulo vazio. Entram numa lista
    # própria e NÃO são repetidos como o dado real — a repetição existe para o
    # real não se diluir, e negativo repetido só ensina o modelo a ter medo.
    # A literatura do YOLO recomenda algo entre 0 e 10% de "background images";
    # o aviso abaixo existe porque passar disso troca fantasma por carta
    # perdida, e essa troca não aparece no mAP.
    negativos = []
    for pasta in sorted(p for p in NEGATIVOS.glob("*") if p.is_dir()):
        if pasta.name in args.holdout:
            print(f"negativos: {pasta.name} FORA do treino (holdout)")
            continue
        destes = collect(pasta, needs_review=True)
        negativos += destes
        print(f"negativos: {len(destes)} imagens sem carta ({pasta.name})")

    syn_train, syn_val = split_pairs(synthetic, seed=42)
    real_train, real_val = split_pairs(real, seed=43)
    neg_train, neg_val = split_pairs(negativos, seed=44)

    # repete o real até ele pesar REAL_TARGET_SHARE do treino
    repeat = 1
    if real_train:
        alvo = REAL_TARGET_SHARE * len(syn_train) / (1 - REAL_TARGET_SHARE)
        repeat = max(1, min(REAL_MAX_REPEAT, round(alvo / len(real_train))))
        if repeat > 1:
            print(f"repetindo os {len(real_train)} frames reais {repeat}x "
                  f"para não diluí-los em {len(syn_train)} sintéticos")

    splits = {"train": syn_train + real_train * repeat + neg_train,
              "val": syn_val + real_val + neg_val}
    if neg_train:
        fatia = 100 * len(neg_train) / len(splits["train"])
        print(f"negativos: {len(neg_train)} no treino = {fatia:.1f}% "
              f"(acima de ~10% o modelo passa a PERDER carta de verdade)")

    if TRAINSET.exists():
        shutil.rmtree(TRAINSET)
    for split, pairs in splits.items():
        (TRAINSET / "images" / split).mkdir(parents=True)
        (TRAINSET / "labels" / split).mkdir(parents=True)
        for i, (img, label) in enumerate(pairs):
            # índice no nome: as repetições do real não podem se sobrescrever
            stem = f"{i:06d}_{img.stem}"
            shutil.copy(img, TRAINSET / "images" / split / f"{stem}.jpg")
            shutil.copy(label, TRAINSET / "labels" / split / f"{stem}.txt")

    names = YOLO(str(MODEL)).names
    yaml = [f"path: {TRAINSET.resolve().as_posix()}",
            "train: images/train", "val: images/val", "names:"]
    yaml += [f"  {i}: {name}" for i, name in names.items()]
    (TRAINSET / "data.yaml").write_text("\n".join(yaml))
    n_real = len(real_train) * repeat
    share = 100 * n_real / len(splits["train"]) if splits["train"] else 0
    print(f"{len(splits['train'])} treino / {len(splits['val'])} validação "
          f"({n_real} amostras reais no treino = {share:.0f}%)")

    # backup do modelo atual antes de sobrescrever
    n = 1
    while (backup := MODEL.with_name(f"cards_backup_{n}.pt")).exists():
        n += 1
    shutil.copy(MODEL, backup)
    print(f"backup: {backup}")

    model = YOLO(str(MODEL))
    print(f"treino: epochs={EPOCHS} imgsz={IMGSZ} batch={BATCH}")
    model.train(
        data=str(TRAINSET / "data.yaml"),
        epochs=EPOCHS,    # menos épocas: evita fixar demais no sintético
        imgsz=IMGSZ,      # índices de canto são pequenos: resolução alta
        lr0=0.0003,       # lr baixo: ajuste fino
        freeze=10,        # congela o "miolo" (backbone) — não esquece o real
        batch=BATCH,      # imgsz maior consome mais VRAM
        mosaic=0.0,       # mosaico descaracteriza o layout de leque
        scale=0.2, translate=0.05,  # augment moderado
        project=str(ROOT / "runs"),
        name="finetune-fans",
        exist_ok=True,
    )

    best = ROOT / "runs" / "finetune-fans" / "weights" / "best.pt"
    shutil.copy(best, MODEL)
    print(f"\nnovo modelo publicado em {MODEL}")
    print(f"se piorar, volte com: copy {backup} {MODEL}")


if __name__ == "__main__":
    main()
