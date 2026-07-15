"""Baixa o dataset público de cartas (52 classes + joker) do Roboflow Universe.

Dataset: "Playing Cards" (augmented-startups/playing-cards-ow27d) —
bounding boxes nos índices dos cantos, formato YOLO.
Requer: pip install roboflow, e ROBOFLOW_API_KEY no ambiente.
"""
import os
from pathlib import Path

from roboflow import Roboflow

OUT = Path(__file__).resolve().parent / "datasets"
OUT.mkdir(exist_ok=True)

rf = Roboflow(api_key=os.environ["ROBOFLOW_API_KEY"])
project = rf.workspace("augmented-startups").project("playing-cards-ow27d")
dataset = project.version(4).download("yolov8", location=str(OUT / "playing-cards"))
print(f"dataset em {dataset.location}")
print("conferir data.yaml: os nomes das classes devem ser tipo '10C', 'AS'...")
