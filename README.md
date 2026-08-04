# Cacheta Card Tracker

Sistema local de visão computacional para partidas de **cacheta** com cartas físicas: uma webcam aponta para a mão do jogador, um modelo YOLO reconhece as cartas em tempo real e um overlay web (usado como Browser Source no OBS) mostra as cartas em PNG — para gravação e edição de vídeo.

## Como funciona

```
webcam → YOLO (GPU) → tracker (estado do jogo) → FastAPI + WebSocket
                                                    ├── /overlay/mao  → leque da mão (OBS)
                                                    ├── /overlay      → compra + descarte (OBS)
                                                    └── /painel       → controle e correção
```

- **Mão ao vivo:** leque com as cartas detectadas, na ordem física da esquerda para a direita, com votação temporal por posição (fantasmas expiram, mão abaixada congela) e suporte a **2 baralhos** (gêmeas separadas pela geometria dos cantos).
- **Compra/descarte:** eventos de turno pela **mudança da mão**, com uma câmera só — o leque que cresce uma carta é uma compra, o que encolhe uma é um descarte. A câmera do descarte é opcional e serve só de preview no painel.
- **Painel:** preview das câmeras com as detecções, correção manual, desfazer, pausa e nova rodada.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
python scripts/download_assets.py   # PNGs das 52 cartas
```

**Modelo:** baixar os pesos prontos para `models/cards.pt`:

```powershell
curl -L -o models/cards.pt "https://huggingface.co/mustafakemal0146/playing-cards-yolov8/resolve/main/playing_cards_model_0_playing-cards-colab.pt"
```

## Rodar

```powershell
python -m app.main
```

- Painel: http://127.0.0.1:8000/painel
- Overlay da mão: http://127.0.0.1:8000/overlay/mao (Browser Source no OBS, fundo transparente)

> ⚠️ A webcam não pode estar em uso pelo OBS/navegador — o app abre a câmera e o OBS consome o overlay (e opcionalmente `/stream/hand`) via Browser Source. Se a câmera estiver ocupada, o app tenta de novo a cada 2s até conseguir.

Índices de câmera, resolução e thresholds: `app/config.py`.

## Fine-tuning local (sem Roboflow)

Se o reconhecimento falhar com suas cartas/iluminação:

```powershell
python training/capture_deck.py     # 1. molde das 52 cartas do seu baralho
python training/generate_fans.py    # 2. gera leques sintéticos a partir deles
python training/capture_auto.py     # 3. captura frames reais da câmera (2 min)
python training/auto_annotate.py    # 4. o modelo atual anota sozinho
# 5. revisar: apagar fotos erradas em training/datasets/local/review/
python training/finetune_local.py   # 6. treina com sintético + real e publica
```

O treino mistura as duas fontes: os leques sintéticos dão volume e variedade,
os frames reais ancoram o modelo na sua câmera e iluminação. Detalhes e
scripts de diagnóstico em [`training/README.md`](training/README.md).

**Se uma carta específica erra sempre**, o passo 4 não resolve: o modelo anota
com o próprio erro, você apaga a foto na revisão e a carta nunca aprende. Use
`capture_rotulado.py`, que rotula pela ORDEM em que você informa a mão em vez
de perguntar ao modelo:

```powershell
python training/capture_rotulado.py "AS 4S AH 4H AD 4D AC 4C KS" 60
```

Para comparar o modelo novo com o anterior (no mesmo conjunto de validação):

```powershell
python training/eval_classes.py models/cards.pt 150
```

## Testes

```powershell
python -m pytest
```

Toda a lógica de jogo (tracker, histerese, geometria de cantos, servidor) é código puro coberto por testes — câmera e modelo são as únicas partes com verificação manual.
