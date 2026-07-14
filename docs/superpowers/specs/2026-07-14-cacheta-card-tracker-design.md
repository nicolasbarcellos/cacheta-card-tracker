# Cacheta Card Tracker — Design

**Data:** 2026-07-14
**Status:** Aprovado

## Objetivo

Sistema local que, durante uma partida de cacheta com cartas físicas, reconhece automaticamente qual carta o jogador **descartou** e qual **comprou**, e exibe os PNGs correspondentes num overlay web usado como Browser Source no OBS (para gravação/edição de vídeo). Não é um conselheiro de jogo — apenas rastreia e exibe.

## Contexto e restrições

- 2 webcams: uma apontada para o monte de descarte (mesa), outra para a mão do jogador.
- Baralho padrão de 52 cartas (estilo Copag), **sem coringa**, baralho único (sem cartas repetidas).
- Reconhecimento com **YOLO local** rodando em GPU NVIDIA (sem dependência de nuvem).
- Detecção automática com **painel de correção manual**.
- Overlay mostra **compra + descarte** do jogador, atualizado em tempo real.

## Arquitetura

Um único app Python com FastAPI (abordagem escolhida entre: app único ✅, detector/overlay separados, reconhecimento em nuvem).

```
Webcam mesa (descarte)      Webcam mão (snapshot)
        │      OpenCV captura      │
        ▼                          ▼
   detector (YOLO na GPU) — identifica cartas por frame
        ▼
   tracker (estado do jogo) — descarte novo, diff da mão, turno
        ▼ eventos via WebSocket
   server (FastAPI)
     /overlay → OBS Browser Source (compra + descarte em PNG)
     /painel  → controle: preview das cams, corrigir, desfazer,
                nova rodada, pausar
```

### Estrutura de pastas

```
vision-llm/
├── app/
│   ├── capture.py      # threads de captura das 2 webcams
│   ├── detector.py     # wrapper do YOLO (Ultralytics)
│   ├── tracker.py      # lógica de estado: descarte, diff da mão, turno
│   ├── server.py       # FastAPI + WebSocket
│   └── config.py       # índices das câmeras, thresholds, etc.
├── web/
│   ├── overlay/        # página do OBS (fundo transparente)
│   └── painel/         # página de controle/correção
├── assets/cards/       # PNGs das 52 cartas (pack open-source)
├── models/             # pesos do YOLO treinado
└── training/           # scripts e notas do fine-tuning
```

**Stack:** Python 3.11+, Ultralytics (YOLO11 nano/small), OpenCV, FastAPI + uvicorn. Overlay e painel em HTML/JS puro.

## Lógica de detecção

### Descarte (câmera da mesa)

1. YOLO roda continuamente; só a carta do **topo** do lixo importa.
2. Registra descarte quando detecta rótulo diferente do último registrado.
3. **Filtro de estabilidade:** mesma carta em ~10 frames consecutivos (≈1s) com confiança ≥ 0.75 — elimina falsos positivos (mão na frente, carta caindo/torta, borrão).

### Compra (câmera da mão)

1. YOLO detecta os **índices dos cantos** (número + naipe), visíveis mesmo com cartas em leque.
2. Tracker mantém o conjunto da mão do turno anterior (9 cartas).
3. Conjunto estável com 10 cartas → diff de conjuntos identifica a carta nova → evento de compra. Baralho único torna o diff exato.
4. Após o descarte, a mão volta a 9 → vira referência do próximo turno.

### Modelo de turno

`mão estável com 10` → compra → `carta nova no lixo` + `mão volta a 9` → descarte → fim do turno. Eventos fora de ordem são registrados parcialmente e corrigidos no painel.

### Casos tratados

- **Compra do lixo vs. do monte:** se a carta do topo do lixo sumiu e apareceu na mão, foi do lixo (overlay indica com selo); senão, do monte.
- **Confiança baixa / carta desconhecida:** painel mostra o frame capturado e pede correção (seletor valor + naipe).
- **Nova rodada:** botão no painel zera o estado (lixo vazio, mão nova).
- **Pausa:** botão para embaralhar/distribuir sem gerar eventos espúrios.

## Overlay (`/overlay`)

- Fundo transparente, Browser Source no OBS.
- Duas áreas: **COMPRA** e **DESCARTE**, com PNG da carta (deck open-source, ex.: Vector Playing Cards, domínio público).
- Atualização via WebSocket com animação de entrada (slide/flip); selo "do lixo" quando aplicável.
- Tamanho/posição via CSS; posicionamento final no próprio OBS.

## Painel (`/painel`)

- Preview ao vivo das 2 câmeras com bounding boxes do YOLO.
- Lista dos últimos eventos com **corrigir** (seletor valor+naipe) e **desfazer**.
- Botões **nova rodada** e **pausar detecção**.
- Eventos de baixa confiança destacados em amarelo pedindo confirmação.
- Correções refletem no overlay imediatamente.

## Treino do YOLO

1. **Base:** dataset público de cartas (Roboflow Universe, 52 classes, índices de canto); treinar YOLO11-nano/small na GPU local, ou partir de modelo público já treinado.
2. **Fine-tuning:** gravar 2-3 min de cada câmera no setup real, extrair ~200-400 frames, pré-anotar com o modelo base, corrigir e re-treinar.
3. **Aceite:** ≥95% de acerto no descarte e ≥90% no diff da mão em partida de teste; escapes corrigidos no painel.

## Testes

- **tracker:** código puro, sem câmera — testes unitários com sequências simuladas de detecções, incluindo cenários bagunçados (mão na frente, carta torta, eventos fora de ordem).
- **Visão:** validação offline com vídeos gravados das câmeras reais.
- **Ponta a ponta:** partida de teste medindo as métricas de aceite.
