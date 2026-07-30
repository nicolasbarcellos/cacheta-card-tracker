"""Fine-tuning local: re-treina models/cards.pt com leques sintéticos + reais.

Consome duas fontes e mistura as duas:

- training/datasets/synthetic/ — gerado por generate_fans.py a partir dos
  moldes do seu baralho. Muitas imagens, variedade fácil, mas é simulação.
- training/datasets/local/     — frames REAIS da sua câmera, capturados por
  capture_auto.py e pré-anotados por auto_annotate.py. Poucas imagens, porém
  é a distribuição que o modelo vai encontrar de verdade.

Do dataset real só entram os frames cuja imagem em local/review/ sobreviveu:
apagar a foto de revisão é como você rejeita uma anotação errada.

Como o sintético é muito mais numeroso, os frames reais são repetidos algumas
vezes (REAL_TARGET_SHARE) — senão eles se diluem e o treino ignora justamente
o dado que importa.

O modelo antigo fica salvo em models/cards_backup_N.pt.
"""
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ultralytics import YOLO  # noqa: E402

ROOT = Path(__file__).resolve().parent
SYNTH = ROOT / "datasets" / "synthetic"
LOCAL = ROOT / "datasets" / "local"
TRAINSET = ROOT / "datasets" / "fans-split"
MODEL = Path("models/cards.pt")

REAL_TARGET_SHARE = 0.30   # fatia do treino que os frames reais devem ocupar
REAL_MAX_REPEAT = 6        # teto: repetir demais decora o pouco dado real

# Ajustáveis na linha de comando: epochs imgsz batch.
# imgsz alto é necessário (o índice de canto é pequeno e o pip do naipe é o
# primeiro detalhe a se perder), mas 1280 com batch 6 NÃO cabe em 4 GB de VRAM
# — num RTX 3050 Laptop é preciso baixar o batch. Ex.: `... 12 1280 3`.
EPOCHS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
IMGSZ = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
BATCH = int(sys.argv[3]) if len(sys.argv) > 3 else 6


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
    if len(synthetic) + len(real) < 200:
        sys.exit("dados insuficientes — rode generate_fans.py e/ou "
                 "capture_auto.py + auto_annotate.py")
    if not real:
        print("AVISO: nenhum frame real. O modelo vai treinar só em simulação, "
              "que é o que costuma falhar no setup de verdade.")

    syn_train, syn_val = split_pairs(synthetic, seed=42)
    real_train, real_val = split_pairs(real, seed=43)

    # repete o real até ele pesar REAL_TARGET_SHARE do treino
    repeat = 1
    if real_train:
        alvo = REAL_TARGET_SHARE * len(syn_train) / (1 - REAL_TARGET_SHARE)
        repeat = max(1, min(REAL_MAX_REPEAT, round(alvo / len(real_train))))
        if repeat > 1:
            print(f"repetindo os {len(real_train)} frames reais {repeat}x "
                  f"para não diluí-los em {len(syn_train)} sintéticos")

    splits = {"train": syn_train + real_train * repeat,
              "val": syn_val + real_val}

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
