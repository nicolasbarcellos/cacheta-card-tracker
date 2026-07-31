# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Código, comentários, docstrings e mensagens de commit deste repositório são em **português**. Mantenha o padrão (Conventional Commits com corpo explicando o *porquê* e o que foi medido).

## Comandos

```powershell
# setup (PyTorch CUDA primeiro, senão o pip instala a versão CPU)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
python scripts/download_assets.py     # PNGs das 52 cartas em assets/cards/ (git-ignored)

python -m app.main                    # app real (precisa das 2 webcams livres)
python scripts/demo_server.py         # partida simulada, sem webcam — para mexer no overlay/painel

python -m pytest                      # suíte completa (rápida: só código puro)
python -m pytest tests/test_hand_reader.py::test_max_slots_caps_the_hand   # um teste
```

Diagnóstico de câmera/modelo (todos abrem janela do OpenCV, `q` encerra):
`scripts/check_cams.py` (índices/enquadramento) · `training/aim.py` (mirar) ·
`training/diagnose_live.py` (log ao vivo de carta + confiança) ·
`training/diagnose.py` (estabilidade em ~40 frames) · `training/dump_dets.py` (geometria das caixas).

Antes de culpar o modelo, rode `diagnose_live.py`: leque pequeno no quadro degrada muito o
reconhecimento — o pip do naipe é o menor detalhe do índice e é o primeiro a se perder.

## Arquitetura

Um único processo Python. A thread de visão (`app/main.py:vision_loop`) e o event loop do
uvicorn se comunicam apenas por: (a) o `GameTracker` mutado pela thread de visão, e (b)
`tracker.on_change` → `queue.Queue` → task assíncrona que colapsa rajadas e faz broadcast do
estado no WebSocket (`app/server.py:52`). Os frames anotados vão para o dict `annotated`, lido
pelo MJPEG em `/stream/{cam}` (encode em `asyncio.to_thread`, cache de 120 ms).

```
CameraStream(discard) → detect → pick_top_card → StabilityFilter → tracker.on_stable_top_card → evento "discard"
CameraStream(hand)    → detect ─┬→ hand_instances → FanReader → StableHand → tracker.set_hand_display  (overlay da mão)
                                └→ hand_codes     → StabilityFilter → tracker.on_stable_hand → evento "draw"
```

**A câmera da mão alimenta dois caminhos independentes** (`app/main.py:process_frame`), e essa é a
chave para entender o projeto:

- **Exibição** (leque no OBS) — `FanReader` + `StableHand`: prioriza estabilidade visual. Trava as
  9 cartas e não solta.
- **Eventos** (compra/descarte) — `StabilityFilter` + `GameTracker`: prioriza detectar a
  *transição* 9→10 cartas. Trabalha com `frozenset` de códigos, sem posição.

Não unifique os dois: eles têm requisitos opostos (segurar × reagir).

### Camadas de filtragem da mão

1. `hand_instances` (`app/detector.py`) — deduplica por **posição**, nunca por rótulo. Duas
   detecções quase coincidentes = mesmo canto lido duas vezes → fica a mais confiante. Posições
   distintas = cartas distintas **mesmo com rótulo igual**: cacheta usa 2 baralhos e gêmeas na
   mão são legítimas. Qualquer mudança aqui precisa preservar isso.
2. `FanReader` (`app/hand_reader.py`) — votação temporal por "vaga" (posição estável na imagem).
   O voto é **ponderado pela confiança**, não por contagem: medido no setup real, quando o modelo
   troca o naipe dentro da mesma cor (♠↔♣, ♥↔♦) erra com ~0.34 e acerta com ~0.85, então por
   maioria simples o errado venceria. Teto de vagas = `hand_size`: vaga sobrando é espúria, e o
   corte ordena por `misses` antes de peso (depois de o leque se mover, a vaga velha ainda é
   "forte" mas está ausente — quem tem de ganhar é a nova).
3. `StableHand` (`app/stable_hand.py`) — score de presença por *instância*; **acompanha** a mão:
   qualquer conjunto que fique estável por `lock_frames` substitui o exibido, automaticamente e
   de **qualquer tamanho**. O `hand_size` não é exigido — a mão passa por 10 cartas no instante
   da compra e o jogador espera ver as 10. `force_relock()` (botão "Reler mão") virou só um
   reset manual.

   Até 2026-07-30 ele **travava** a primeira mão de exatamente 9 e segurava até o botão, para o
   overlay nunca oscilar numa live. Trocado a pedido do usuário: o custo era clicar a cada carta
   comprada e conviver com mão exibida velha. A estabilidade agora vem só da histerese — se a
   exibição ficar inquieta demais numa gravação, o ajuste é aumentar `lock_frames`, não voltar
   ao botão. O teto de vagas do `FanReader` acompanhou: `hand_size + 1`.

Invariante em todas as camadas: **frame sem nenhuma detecção significa "mão fora do quadro" e
congela o estado**, não zera. Só ausência *relativa* (outras cartas visíveis, esta não) expira.

### Estado do jogo (`app/tracker.py`)

Código puro, sem OpenCV/YOLO — é onde ficam os testes. `on_stable_hand` só aceita conjuntos de
`hand_size` ou `hand_size + 1`; qualquer outro tamanho é detecção ruim e é ignorado sem corromper
a referência. Compra do lixo × do monte sai de `_discard_history`: se a carta nova na mão já
passou pelo topo do lixo, `source = "lixo"` (overlay mostra o selo). `undo_last` e `correct_event`
desfazem também o efeito no histórico do lixo, para a mesma carta poder ser detectada de novo.

## Detecção: limiar baixo é de propósito

`config.min_confidence = 0.30`. Quem filtra ruído é a votação temporal, não o limiar — limiar alto
cortava cartas reais de confiança média. `confirm_confidence = 0.85` só marca o evento como
"confirmar?" no painel (amarelo). Os parâmetros do leque foram **medidos neste setup**: jitter da
mesma carta entre frames = 3 px (p95 8 px), espaçamento mínimo entre cantos vizinhos = 47 px →
`fan_match_dist = 30` (folga de 3.7× sobre o jitter, 1.6× de margem contra casar na vaga do
vizinho). Ao mexer nesses números, meça de novo com `dump_dets.py` e registre no commit.

`hand_cam_index = 1`, `discard_cam_index = 0` — trocá-los faz o leque ser consumido pelo pipeline
de descarte (que só extrai a carta mais confiante) e a mão exibida nunca recebe nada.

### `agnostic_nms` fica desligado — não religue

Medido em 2026-07-29 com um leque adversarial (4♠4♥4♦4♣ + A♠A♥A♦A♣ + 5♠, os dois ranks que o
modelo erra mais, nos quatro naipes). Com `agnostic_nms=True` a mão travada saía com **A♥ e A♠
duplicados e sem o 4♥ e o 4♣**. Rodando o modelo com o NMS agnóstico desligado e `conf=0.10`, o
4♥ aparece em **695 frames com confiança média 0.74** — o modelo sempre soube; o pipeline é que
jogava fora.

Motivo: NMS agnóstico funde caixas sobrepostas de **classes diferentes** por frame e mantém só a
mais confiante. Isso (a) antecipa, sem volta e sem contexto temporal, a decisão que o `FanReader`
existe para tomar votando por confiança acumulada, e (b) num leque apertado suprime a carta
**vizinha** legítima, cuja caixa se sobrepõe à do vizinho. Com ele desligado, o rótulo certo venceu
o voto em 8 das 9 vagas na medição, e a mão saiu 9/9 correta no teste ao vivo.

Para diagnosticar candidatos concorrentes, rode o modelo com `agnostic_nms=False` **e** confiança
baixa (~0.10) e agrupe as caixas por posição: é o único jeito de ver que o rótulo certo existia.

### O raio de fusão do `hand_instances` sai da MENOR dimensão da caixa

Este foi o bug mais caro do projeto e sobreviveu meses porque **os testes usavam
caixas quadradas de 20×20 px**. Um índice de canto real é ~44×84 px: estreito e alto.
O raio de fusão usava `max(largura, altura)` → `0.55 × 84 = 46 px`, **maior que o
espaçamento entre cantos vizinhos** (19 px no pior caso, 34 px mediano no sintético;
47 px no setup real). Resultado: cada carta apagava a vizinha como se fosse o mesmo
canto lido duas vezes.

Medido em 60 imagens de validação: a regra antiga preservava **51,7%** das cartas da
mão; pela menor dimensão sobe para **91,9%**. Ou seja, quase metade da mão era
descartada *antes* de qualquer votação — o `FanReader` e o `StableHand` decidiam com
metade da informação. É a explicação de "carta desaparece e a vizinha aparece
duplicada", sintoma que se confundia facilmente com erro de modelo.

`MERGE_FACTOR = 0.35` é a ponta segura de um platô (0.45, 0.35 e 0.25 dão resultado
idêntico): raio de ~15 px, abaixo dos 19 px do pior espaçamento, e ainda funde de
sobra os dois palpites do mesmo canto, que ficam a poucos pixels um do outro.

Ao mexer aqui, os testes de regressão a manter verdes são os
`test_tall_index_*` em `tests/test_detector_logic.py` — eles usam a geometria real.
**Qualquer teste novo de `hand_instances` deve usar caixa estreita e alta**, não
quadrada, senão não exercita o caso que importa.

### Quando a detecção COLAPSA, suspeite da geometria do gerador

O erro mais caro da sessão de 2026-07-30 não estava no modelo, no tremor nem no
casamento de vagas: o gerador produzia leques de **28-52° de abertura** e um leque
de 9 cartas na mão abre **150-180°** (com 9 cartas ninguém abre 40 — você abre para
enxergar os índices). As cartas das pontas chegavam com o índice deitado ou de cabeça
para baixo, orientação ausente do treino. Medido no frame ao vivo: **5 detecções brutas
para 9 cartas**, 3 no limiar do app, e as únicas certas eram as duas do MEIO do leque.

Sintoma que engana: parece erro de modelo ou de leitor, porque a mão sai errada. Mas
não havia detecção para o leitor casar. **Se a mão não trava e o log de trava não
imprime, olhe o `/stream/hand` e conte as caixas antes de mexer em qualquer parâmetro.**

Três parâmetros do `generate_fans.py` que precisam corresponder à câmera real, e que
falham em silêncio quando não correspondem:

- **abertura** (`total_spread`): hoje 25-150°.
- **escala**: o leque precisa PREENCHER o quadro como preenche ao vivo (~16% da largura
  do frame na câmera real). Encolher o leque para ele "caber" no canvas afasta o
  sintético do real — o certo é recortar o rótulo na borda.
- **passo** entre cartas: é ele que EXPÕE o índice. Abaixo de ~0.18 da largura da carta,
  a carta seguinte cobre o índice da anterior. Com 0.03-0.06, **60,6% dos índices ficavam
  sem rótulo** e cada imagem rendia 3,4 rótulos em vez de 8,5.

Use o contador `DROP_STATS` do gerador para verificar: ele separa "coberto" de "fora do
quadro" e de "pequeno". Três tentativas de deduzir a causa olhando as imagens geradas
falharam; o contador resolveu na primeira. **Meça, não deduza** — vale para o gerador
tanto quanto para o modelo.

Rótulo é o outro cuidado: um índice **visível na imagem e sem rótulo** ensina o modelo
que aquele padrão é fundo. Por isso a caixa que passa da borda é recortada, não
descartada — descartar era pior que perder a amostra.

### Leque parado vale mais que qualquer parâmetro

Medido em 2026-07-30 com o leque grande no quadro e segurado na mão: jitter da mesma
carta de **29,5 px médio, 66 px p95** — contra 3 px / p95 8 px do setup antigo. O leque
perto da câmera amplia o tremor da mão na mesma proporção em que amplia a carta.

Duas consequências, ambas observadas:

1. O casamento por posição quebra. Com `fan_match_dist` menor que o jitter, a mesma
   carta sai da própria vaga e cria vaga nova — a sonda rastreou **10 trilhas para 9
   cartas**, com uma delas em três. É a origem de "carta some / vizinha duplica" e da
   variação entre travas sucessivas (a MESMA mão deu 9/9, 7/9 e 9/9).
2. O borrão come os traços finos. As piores classes por rank (8: 82,4% · 5: 86,7% ·
   3: 89,0% · K: 92,8%) são justamente as de glifo fino, e as confusões dominantes são
   5♠→3♠, K♠→A♠, 8♣→6♣. **Com as cartas apoiadas na mesa, a mesma mão que dava 7/9
   passou a dar 9/9, incluindo essas classes.** O que parecia viés de classe era
   sensibilidade a imagem degradada.

Antes de culpar o modelo por erro de VALOR, verifique se o leque estava parado.
E note o limite físico: o jitter p95 (66 px) empata com o menor espaçamento entre
cartas (p05 = 69 px) — não existe `fan_match_dist` que atenda os dois extremos. O
conserto estrutural é compensar a translação GLOBAL do leque antes de casar as vagas
(a mão move o leque inteiro junto), já que numa partida de verdade o jogador segura
as cartas e não pode apoiá-las.

### Enquadramento é metade do resultado

Na mesma sessão, com o leque a ~1,5-2 m da câmera ele ocupava ~450×370 px de um frame 1920×1080 →
o índice de canto chegava ao modelo com ~20×30 px após o resize para `imgsz=1280`. Nessa condição o
4♣ saía com confiança média 0.32 (contra 0.74 do 4♥) e o 5♠ era lido como J♠ (peso 160 × 76).
Aproximar o leque até preencher boa parte do quadro corrigiu ambos. **Antes de culpar o modelo ou
retreinar, confira o tamanho do índice no quadro.**

## Modelo e treino (`training/`)

`models/cards.pt` (versionado, ~6 MB) detecta **só o índice do canto superior-esquerdo**, 52
classes nomeadas `AS`/`10C`/`QH` (parseáveis por `Card.from_label`), sem coringa. O canto de baixo
nunca é rotulado no dataset sintético — é assim que o modelo aprende a não contar a mesma carta
duas vezes.

### O ciclo de pseudo-anotação não conserta o que o modelo erra

`auto_annotate.py` rotula com o modelo atual e depende de revisão manual. Isso tem um
limite **circular** e fatal: nas cartas que o modelo erra, o rótulo sai errado, a foto é
apagada na revisão, e a carta nunca aprende. Foi por isso que a confusão A↔4 sobreviveu
a duas rodadas de retreino.

`capture_rotulado.py` quebra a circularidade: você informa a mão **na ordem da esquerda
para a direita**, e cada detecção recebe o código da sua posição — o palpite do modelo é
ignorado. O resultado é dado correto exatamente onde ele erra. Medido: em boa parte dos
frames o modelo acertava só 5 de 9, e os 4 errados viraram rótulo correto.

Guardas obrigatórias (alinhamento torto envenena o dataset inteiro): contagem exata de
detecções, sem buraco no espaçamento entre cantos (buraco = carta não detectada, que
desloca todos os rótulos seguintes) e maioria dos rótulos do modelo já batendo com a
posição. **Sempre confira algumas imagens de `review/` antes de treinar** — verde é
acerto do modelo, laranja é correção pela ordem.

Capture ao menos **duas ordens diferentes** das mesmas cartas, senão o modelo pode
associar posição a rótulo em vez de aprender o glifo.

### Hipótese refutada: nitidez do frame não separa acerto de erro

O erro A↔4 aparecia mais com a câmera balançando, o que sugeria filtrar frames borrados
antes da detecção. **Medido e descartado**: variância do Laplaciano de 2121 (mediana) nos
frames certos contra 2096 nos errados — 1% de diferença, distribuições sobrepostas.
Cortar no p10 dos certos descartaria 17% dos erros e 10% dos acertos. Não é filtro, é
moeda. Não reimplemente isso sem medir de novo num setup diferente.

Fluxo local de fine-tuning (sem nuvem), detalhes em `training/README.md`:
`capture_deck.py` → `generate_fans.py` → `capture_auto.py` → `auto_annotate.py` →
**revisão manual** → `finetune_local.py`.

O passo manual é o que dá qualidade: apagar as fotos erradas em `datasets/local/review/` é como
se rejeita uma anotação — `finetune_local.py` só usa frames cuja imagem de revisão sobreviveu.
O treino mistura sintético + real, separa validação *dentro de cada fonte* (senão a validação
mediria só simulação) e repete os frames reais até ~30% do treino. `freeze=10`, `imgsz=1280`,
`mosaic=0.0` (mosaico descaracteriza o layout de leque). O modelo antigo vai para
`models/cards_backup_N.pt` e o script imprime o comando de rollback.

**Retreino de 2026-07-29** (o primeiro a usar a caixa corrigida). Os pesos anteriores
vinham de `870407c`, *antes* do fix `a8321af`, e tinham sido treinados só em sintético
com o **pip do naipe truncado** — cobertura média de 65,7% do índice, pior caso 49,7%
no 4♣. Como o pip é a única diferença entre ♠/♣ e ♥/♦, era a causa raiz da confusão de
naipe na mesma cor (o voto ponderado por confiança do `FanReader` é um remendo para
esse defeito, não a solução).

12 épocas, 1280 px, `batch=3`, `freeze=10`, partindo dos pesos antigos, ~18 min num
RTX 3050 Laptop (VRAM usada: 1,2 GB de 4 — dava para usar batch 8-12). Medido em 1122
índices de um conjunto de validação separado:

| métrica | antes | depois |
|---|---|---|
| classe correta | 83,3% | **92,5%** |
| troca de naipe na mesma cor | 8,8% | **3,5%** |
| viés de centro (dy) | −12,0 px | **+0,1 px** |

O viés de centro zerando é a confirmação direta de que o modelo aprendeu a caixa com o
pip inteiro. Q♣→Q♠ (100% de acerto depois, era o erro reproduzível ao vivo) sumiu.
O erro dominante passou a ser de **valor**, não de naipe — pior classe hoje: 5♠ (68,2%).

Cuidado ao retreinar: `finetune_local.py` passa `lr0=0.0003`, mas o Ultralytics usa
`optimizer='auto'` e **ignora esse valor** ("optimizer=auto found, ignoring 'lr0'"),
escolhendo AdamW com lr≈0.00018. A intenção do código não é honrada; se o lr importar,
passe `optimizer='AdamW'` explicitamente.

Em `generate_fans.py`, a caixa do índice é **medida em cada molde** (`detect_corner_tl`), não fixa:
os moldes não saem todos alinhados do `capture_deck.py` e a caixa fixa caía na mesa em vez de no
glifo (cobria 71% do índice no 4C, 76% no AC — justamente A e 4, os valores que o modelo mais
errava).

Meta de aceite do projeto: ≥95% dos descartes e ≥90% das compras corretos numa partida de teste.

## Notas

- A webcam não pode estar em uso pelo OBS/navegador. `CameraStream` reabre sozinha a cada 2 s se
  a câmera estiver ocupada ou cair; usa `CAP_DSHOW` + MJPG (YUY2 satura o USB em 1080p+).
- `app/hand_view.py` (`HandView`, histerese por carta) e `detector.hand_card_instances` são
  **código morto**: substituídos por `FanReader` + `StableHand`, importados só pelos próprios
  testes. O docstring de `tracker.set_hand_display` ainda cita `HandView` — desatualizado.
- `assets/cards/` é git-ignored; sem rodar `scripts/download_assets.py` os overlays ficam com
  imagens quebradas.
- Docs de origem em `docs/superpowers/`: o spec (`specs/`) descreve a intenção aprovada; o plano
  (`plans/`) é histórico da implementação e já divergiu do código (ex.: limiar 0.75, um baralho só).
