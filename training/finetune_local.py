"""Fine-tuning local: re-treina models/cards.pt só com as suas fotos.

Usa os frames de training/datasets/local/ que sobreviveram à revisão
(review/), separa treino/validação, monta o data.yaml com as classes na
ordem do modelo e treina POUCAS épocas com lr baixo a partir dos pesos
atuais — especializa no seu baralho sem esquecer o que já sabe.

O modelo antigo fica salvo em models/cards_backup_N.pt.
"""
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ultralytics import YOLO  # noqa: E402

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / "datasets" / "local"
TRAINSET = ROOT / "datasets" / "local-split"
MODEL = Path("models/cards.pt")

# só entram frames cuja imagem de review não foi apagada
kept = [p for p in sorted((LOCAL / "images").glob("*.jpg"))
        if (LOCAL / "review" / p.name).exists()]
if len(kept) < 30:
    sys.exit(f"só {len(kept)} frames aprovados — capture/anote mais "
             "(mínimo recomendado: 30, ideal: 100+)")

random.seed(42)
random.shuffle(kept)
n_val = max(5, len(kept) // 6)
splits = {"val": kept[:n_val], "train": kept[n_val:]}

if TRAINSET.exists():
    shutil.rmtree(TRAINSET)
for split, files in splits.items():
    (TRAINSET / "images" / split).mkdir(parents=True)
    (TRAINSET / "labels" / split).mkdir(parents=True)
    for img in files:
        shutil.copy(img, TRAINSET / "images" / split / img.name)
        label = LOCAL / "labels" / f"{img.stem}.txt"
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
    epochs=20,
    imgsz=960,        # cantos são pequenos: resolução maior ajuda
    lr0=0.0005,       # lr baixo: ajuste fino, não treino do zero
    batch=8,
    project=str(ROOT / "runs"),
    name="finetune-local",
    exist_ok=True,
)

best = ROOT / "runs" / "finetune-local" / "weights" / "best.pt"
shutil.copy(best, MODEL)
print(f"\nnovo modelo publicado em {MODEL}")
print(f"se piorar, volte com: copy {backup} {MODEL}")
