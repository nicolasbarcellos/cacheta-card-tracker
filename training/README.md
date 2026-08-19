# Treino

O modelo em `models/cards.pt` reconhece o **índice do canto superior-esquerdo**
de cada carta — é o que fica visível num leque apertado. 52 classes, sem
coringa, nomes no formato `AS`, `10C`, `QH` (interpretáveis por `Card.from_label`).

## Fluxo local (sem nuvem) — o que se usa hoje

```powershell
python training/capture_deck.py      # 1. molde das 52 cartas do SEU baralho
python training/generate_fans.py     # 2. leques sintéticos a partir dos moldes
python training/capture_auto.py      # 3. frames REAIS da sua câmera
python training/auto_annotate.py     # 4. o modelo atual pré-anota os frames
#    5. revisar: apagar as fotos erradas em training/datasets/local/review/
python training/finetune_local.py    # 6. treina com sintético + real e publica
```

O passo 5 é o único manual e o mais importante: abra `datasets/local/review/`
no Explorer e **apague as fotos onde o modelo errou** (carta com rótulo errado
ou carta sem caixa). O `finetune_local.py` só usa os frames cuja imagem de
revisão sobreviveu.

Se quiser só regenerar o sintético e re-treinar, os passos 3-5 são opcionais —
mas aí o treino vira simulação pura, que é justamente o que costuma falhar no
setup real.

### O que cada script produz

| Script | Saída |
|---|---|
| `capture_deck.py` | `training/templates/*.png` (52 moldes) |
| `generate_fans.py` | `training/datasets/synthetic/{images,labels}/` |
| `capture_auto.py` | `training/datasets/meu-setup/*.jpg` |
| `auto_annotate.py` | `training/datasets/local/{images,labels,review}/` |
| `extrai_gravacao.py` | `training/datasets/real/<partida>/{images,labels,review}/` |
| `finetune_local.py` | `models/cards.pt` (backup do antigo em `cards_backup_N.pt`) |

## Dado real de graça: a partida já gravada

Se existe gravação em `gravacoes/` com gabarito revisado, ela vale mais que uma
captura nova — e não custa nenhum minuto seu segurando o baralho:

```powershell
python training/extrai_gravacao.py gravacoes/20260812-154737 --so-analise   # confere sem salvar
python training/extrai_gravacao.py gravacoes/20260812-154737                # extrai
python training/finetune_local.py 12 1280 3 --holdout 20260811-211614       # treina deixando uma fora
```

O rótulo sai do **gabarito**, não do palpite do modelo, então o dado é correto
exatamente onde ele erra. Antes de treinar, **olhe as imagens de `review/` dos
frames listados em `correcoes.json`** — são as amostras que ensinam algo novo e
também onde um erro de reconstrução apareceria. Apagar a imagem de `review/`
rejeita o frame, igual ao fluxo local.

Guarde SEMPRE uma partida no `--holdout`: medir o modelo novo com
`replay.py --redetectar` contra a partida que o treinou mede decoreba.

O `finetune_local.py` mistura as duas fontes e **repete os frames reais** até
eles ocuparem ~30% do treino — sem isso os poucos frames reais se diluem entre
milhares de sintéticos e o treino ignora o dado que mais importa.

Se o resultado piorar, o script imprime o comando para voltar ao backup.

## Diagnóstico

| Script | Para quê |
|---|---|
| `aim.py` | mirar a câmera: leque dentro do retângulo, contagem ao vivo |
| `diagnose_live.py` | janela ao vivo + log de quais cartas e com que confiança |
| `diagnose.py` | mede estabilidade em ~40 frames com o leque parado |
| `dump_dets.py` | despeja todas as detecções com coordenadas e tamanho |

Use `diagnose_live.py` antes de culpar o modelo: leque pequeno no quadro
degrada muito o reconhecimento, porque o pip do naipe é o menor detalhe do
índice e é o primeiro a se perder.

## Fluxo antigo (Roboflow) — só para treinar do zero

```powershell
pip install roboflow            # e exportar ROBOFLOW_API_KEY
python training/download_dataset.py
python training/train.py        # YOLO11s do zero, 50 épocas
```

Serve para gerar um modelo base quando não há nenhum. Para ajustar um modelo
que já existe ao seu baralho e à sua iluminação, use o fluxo local acima.

## Meta de aceite

≥95% dos descartes e ≥90% das compras corretos numa partida de teste.
