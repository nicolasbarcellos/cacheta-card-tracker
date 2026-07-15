# Treino

1. `pip install roboflow` e exportar `ROBOFLOW_API_KEY`
2. `python training/download_dataset.py` — baixa o dataset público
3. `python training/train.py` — treina e publica `models/cards.pt`
4. Fine-tuning com o setup real: ver `training/capture_frames.py` (Task 14)

Se trocar de dataset, conferir se os nomes das classes em `data.yaml`
são interpretáveis por `Card.from_label` (`10C`, `AS`, `qh`...).

## Fine-tuning

1. `python training/capture_frames.py` durante uma partida simulada
2. Anotar no Roboflow/Label Studio (pré-anotar com o modelo atual)
3. Mesclar com o dataset base, editar `train.py` p/ partir de `models/cards.pt`
4. `python training/train.py` e repetir o teste ponta a ponta

Meta de aceite: ≥95% descartes, ≥90% compras numa partida de teste.
