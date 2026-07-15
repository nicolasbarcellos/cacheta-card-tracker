"""Treina o YOLO11-small no dataset de cartas e publica em models/cards.pt."""
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "datasets" / "playing-cards" / "data.yaml"

model = YOLO("yolo11s.pt")  # baixa o pré-treinado COCO automaticamente
results = model.train(
    data=str(DATA),
    epochs=50,
    imgsz=640,
    batch=16,       # reduzir se faltar VRAM
    project=str(ROOT / "runs"),
    name="cards",
    exist_ok=True,
)

best = ROOT / "runs" / "cards" / "weights" / "best.pt"
dest = ROOT.parent / "models" / "cards.pt"
dest.parent.mkdir(exist_ok=True)
shutil.copy(best, dest)
print(f"modelo publicado em {dest}")
