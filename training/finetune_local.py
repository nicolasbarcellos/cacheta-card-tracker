"""Fine-tuning local: re-treina models/cards.pt com os leques sintéticos.

Consome training/datasets/synthetic/ (gerado por generate_fans.py a partir
dos moldes do seu baralho), separa treino/validação, monta o data.yaml com
as classes na ordem do modelo e treina a partir dos pesos atuais.

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
TRAINSET = ROOT / "datasets" / "fans-split"
MODEL = Path("models/cards.pt")


def main():
    kept = sorted((SYNTH / "images").glob("*.jpg"))
    if len(kept) < 200:
        sys.exit(f"só {len(kept)} imagens em {SYNTH} — rode generate_fans.py")

    random.seed(42)
    random.shuffle(kept)
    n_val = max(50, len(kept) // 10)
    splits = {"val": kept[:n_val], "train": kept[n_val:]}

    if TRAINSET.exists():
        shutil.rmtree(TRAINSET)
    for split, files in splits.items():
        (TRAINSET / "images" / split).mkdir(parents=True)
        (TRAINSET / "labels" / split).mkdir(parents=True)
        for img in files:
            shutil.copy(img, TRAINSET / "images" / split / img.name)
            label = SYNTH / "labels" / f"{img.stem}.txt"
            shutil.copy(label, TRAINSET / "labels" / split / label.name)

    names = YOLO(str(MODEL)).names
    yaml = [f"path: {TRAINSET.resolve().as_posix()}",
            "train: images/train", "val: images/val", "names:"]
    yaml += [f"  {i}: {name}" for i, name in names.items()]
    (TRAINSET / "data.yaml").write_text("\n".join(yaml))
    print(f"{len(splits['train'])} treino / {len(splits['val'])} validação")

    # backup do modelo atual antes de sobrescrever
    n = 1
    while (backup := MODEL.with_name(f"cards_backup_{n}.pt")).exists():
        n += 1
    shutil.copy(MODEL, backup)
    print(f"backup: {backup}")

    model = YOLO(str(MODEL))
    model.train(
        data=str(TRAINSET / "data.yaml"),
        epochs=12,        # menos épocas: evita fixar demais no sintético
        imgsz=1280,       # índices de canto são pequenos: resolução alta
        lr0=0.0003,       # lr baixo: ajuste fino
        freeze=10,        # congela o "miolo" (backbone) — não esquece o real
        batch=6,          # imgsz maior consome mais VRAM
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
