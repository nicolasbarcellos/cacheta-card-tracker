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
python -m app.main --gravar           # idem, gravando a partida para medir depois
python scripts/demo_server.py         # partida simulada, sem webcam — para mexer no overlay/painel

python -m pytest                      # suíte completa (rápida: só código puro)
python -m pytest tests/test_hand_reader.py::test_max_slots_caps_the_hand   # um teste
```

Diagnóstico de câmera/modelo (todos abrem janela do OpenCV, `q` encerra):
`scripts/check_cams.py` (índices/enquadramento) · `training/aim.py` (mirar) ·
`training/diagnose_live.py` (log ao vivo de carta + confiança) ·
`training/diagnose.py` (estabilidade em ~40 frames) · `training/dump_dets.py` (geometria das caixas).

Comparação entre modelos (sem câmera, roda em disco):

```powershell
python training/eval_classes.py models/cards.pt 150
python training/eval_classes.py models/cards_backup_4.pt 150   # o anterior, MESMO conjunto
```

`eval_classes.py` é o instrumento de aceite de um retreino — não confie no mAP do Ultralytics, que
mede o modelo contra o dataset que o treinou e sempre parece ótimo. Ele mede acerto de CLASSE por
índice e separa o erro por tipo (naipe na mesma cor × valor), que é o que diz onde atacar. Duas
decisões de medição que não são óbvias: o casamento é **invertido** (cada predição vai para a
verdade mais próxima, não o contrário — senão, num leque apertado, cada verdade rouba a predição da
vizinha e a métrica mede ruído) e **não usa IoU** (mudar a caixa do índice alteraria o IoU sem
alterar a classificação). O viés de centro é reportado à parte e virou diagnóstico próprio.
**Compare sempre no MESMO conjunto de validação.**

Antes de culpar o modelo, rode `diagnose_live.py`: leque pequeno no quadro degrada muito o
reconhecimento — o pip do naipe é o menor detalhe do índice e é o primeiro a se perder.

## Arquitetura

Um único processo Python. A thread de visão (`app/main.py:vision_loop`) e o event loop do
uvicorn se comunicam apenas por: (a) o `GameTracker` mutado pela thread de visão, e (b)
`tracker.on_change` → `queue.Queue` → task assíncrona que colapsa rajadas e faz broadcast do
estado no WebSocket (`app/server.py:52`). Os frames anotados vão para o dict `annotated`, lido
pelo MJPEG em `/stream/{cam}` (encode em `asyncio.to_thread`, cache de 120 ms).

```
CameraStream(hand)    → detect → hand_instances → FanReader → StableHand ─┬→ tracker.set_hand_display  (overlay da mão)
                                                                          └→ tracker.on_hand_changed  (eventos draw/discard)
CameraStream(discard) → detect → draw_boxes → annotated["discard"]        (só preview do painel)
```

**UMA câmera gera tudo** (`app/main.py:process_frame`) — desde `f5fdf64`. Compra e descarte saem
os dois da MUDANÇA do leque: cresceu uma carta = compra (a que entrou), encolheu uma = descarte
(a que saiu). Não é preciso ver o monte, que é o que exigia a segunda câmera.

A câmera do descarte continua sendo lida e anotada para o preview do painel, **mas não gera evento
nenhum**. Se gerasse, o descarte sairia duplicado (uma vez pela mão, outra pelo monte).

O caminho é único e sequencial, não são dois pipelines paralelos: a mesma leitura estável
(`StableHand`) alimenta a exibição e os eventos. Estabilidade e reação deixaram de ter requisitos
opostos porque o evento agora depende da mesma mão que é exibida — o preço é a latência do
`lock_frames` (~2 s) valer também para o evento.

`tracker.on_hand_changed` só reage a mudança de **exatamente uma** carta. Salto maior é leitura
instável, e a mão indo a zero (jogador abaixou as cartas) não pode virar nove descartes.

### Camadas de filtragem da mão

1. `hand_instances` (`app/detector.py`) — deduplica por **posição**, nunca por rótulo. Duas
   detecções quase coincidentes = mesmo canto lido duas vezes → fica a mais confiante. Posições
   distintas = cartas distintas **mesmo com rótulo igual**: cacheta usa 2 baralhos e gêmeas na
   mão são legítimas. Qualquer mudança aqui precisa preservar isso.
2. `FanReader` (`app/hand_reader.py`) — votação temporal por "vaga" (posição estável na imagem).
   O voto é **ponderado pela confiança**, não por contagem: medido no setup real, quando o modelo
   troca o naipe dentro da mesma cor (♠↔♣, ♥↔♦) erra com ~0.34 e acerta com ~0.85, então por
   maioria simples o errado venceria. Teto de vagas = `hand_size + 1`: vaga sobrando é espúria, e o
   corte ordena por `misses` antes de peso (depois de o leque se mover, a vaga velha ainda é
   "forte" mas está ausente — quem tem de ganhar é a nova).

   Duas proteções que vieram depois e não são óbvias:

   - **Histerese de rótulo** (`fan_win_margin = 2.5`): para TROCAR a carta de uma vaga já
     estabelecida, a concorrente precisa ganhar por essa margem. Sem isso, alguns frames borrados
     viravam o rótulo e a mudança gerava compra e descarte fantasmas. Estabelecer um rótulo
     continua fácil; derrubar um já estabelecido é que ficou difícil. Custo: uma troca REAL de
     carta demora ~22 frames (~1,5 s) para aparecer. Margem só funciona porque, depois do retreino,
     o erro virou rajada curta — com o modelo velho o errado ganhava por 2,28× **sustentado**, e
     margem nenhuma filtraria aquilo.
   - **Queda brusca = oclusão, não jogada** (`146ae94`): ver 1 carta onde havia 9 é o leque
     fechando (as outras ficam atrás da primeira) ou a mão passando na frente. Como na cacheta a
     mão muda de UMA carta por vez, uma queda de duas ou mais **congela** o leitor: não expira vaga
     e não mexe na exibição. Antes disso, fechar o leque expirava as 8 vagas ocultas e ao reabrir
     elas nasciam sem histórico de votos — o leitor "esquecia" o que já tinha acertado.
   - **A DURAÇÃO da oclusão decide se as vagas ainda valem** (2026-08-04). Oclusão curta (a mão
     passando na frente) não mexe no leque: preservar os votos é o que faz a leitura certa voltar
     no primeiro frame. Oclusão longa é o leque FECHADO — e na cacheta fecha-se o leque justamente
     para encaixar a carta comprada, então ao reabrir nada está onde estava. Casar o leque novo nas
     vagas velhas fazia cada vaga teimar com o rótulo antigo (30 votos acumulados contra os poucos
     da carta que chegou, mais a margem de histerese): a mão saía remontada nas posições erradas,
     estável o bastante para ser aceita, e a "carta nova" do diff era qualquer uma. Passando de
     `expire` frames de oclusão, as vagas são descartadas e o leque é relido do zero. Custo: ~1 s
     a mais para a mão aparecer depois de reabrir. **Validado ao vivo**: o gesto de fechar com as
     duas mãos, encaixar a carta no meio e reabrir passou a registrar a compra certa.
   - **UMA detecção por vaga** (2026-08-04). Duas cartas não ocupam a mesma posição física, mas o
     casamento por proximidade permitia isso: num leque apertado as duas caíam dentro do raio da
     MESMA vaga e as duas votavam nela. A vaga virava empate técnico entre dois rótulos — medido ao
     vivo, `9S=13.86` contra `7C=13.34` — e a perdedora sumia da mão. O leitor entregava 9 cartas
     onde havia 10, o tracker via "entrou uma e saiu outra" (que ele ignora de propósito) e a
     compra nunca registrava. Fica com a vaga a detecção MAIS PRÓXIMA dela, não a primeira da
     lista: por ordem, o resultado dependia da ordem em que o modelo devolveu as caixas, e a carta
     legítima podia perder a própria vaga — com os votos acumulados — para a intrusa. Quem perde a
     disputa abre vaga nova, que é o que ela é de fato: uma carta a mais. É a explicação estrutural
     do sintoma antigo **"carta some e a vizinha duplica"**.

   Efeito colateral assumido do congelamento: com o leque fechado o sistema fica cego a mudanças
   reais — trocar carta com o leque fechado só é percebido ao reabrir.
3. `StableHand` (`app/stable_hand.py`) — score de presença por *instância*; **acompanha** a mão:
   um conjunto que fique estável por `lock_frames` substitui o exibido, automaticamente.
   `force_relock()` (botão "Reler mão") virou só um reset manual.

   Só aceita **mão plausível**: `0` (jogador abaixou as cartas), `hand_size` ou `hand_size + 1`
   (instante da compra). Qualquer outro tamanho é bagunça de transição — no ato físico de pôr ou
   tirar uma carta a mão passa na frente, cartas ficam ocultas e os frames borram, e a leitura
   desce a 6, 7, 8 por um segundo. Sem esse filtro a tela mostrava essa bagunça, que era a
   sensação de "ele fica trocando as cartas sozinho". Custo: se a leitura estabilizar num tamanho
   inesperado, a tela segura a mão anterior em vez de mostrar uma mão incompleta.

   A ESTABILIDADE olha o conjunto, não a ordem (duas cartas trocando de lugar por um tremor não é
   mão nova); a ORDEM, essa, é preservada na exibição — é a ordem física do leque, da esquerda
   para a direita.

   `lock_frames = 30` (~2 s), era 12. Com 12 (~0,8 s) uma leitura errada durante a organização das
   cartas durava tempo suficiente para entrar — o jogador ainda estava acomodando o leque, com os
   dedos por cima do índice, e o sistema já aceitava. Os 2 s usam a estabilidade como sinal de
   "terminei de organizar": não dá para exigir 9 ou 10 cartas, porque nem sempre o leque está todo
   aberto, mas enquanto a mão se mexe a leitura muda o tempo todo e não estabiliza. Custo: compra e
   descarte demoram ~1,2 s a mais para aparecer.

   Até 2026-07-30 ele **travava** a primeira mão de exatamente 9 e segurava até o botão, para o
   overlay nunca oscilar numa live. Trocado a pedido do usuário: o custo era clicar a cada carta
   comprada e conviver com mão exibida velha. A estabilidade agora vem só da histerese — se a
   exibição ficar inquieta demais numa gravação, o ajuste é aumentar `lock_frames`, não voltar
   ao botão. O teto de vagas do `FanReader` acompanhou: `hand_size + 1`.

Invariante em todas as camadas: **frame sem nenhuma detecção significa "mão fora do quadro" e
congela o estado**, não zera. Só ausência *relativa* (outras cartas visíveis, esta não) expira.

### Estado do jogo (`app/tracker.py`)

Código puro, sem OpenCV/YOLO — é onde ficam os testes.

A entrada em uso é **`on_hand_changed`**: compara a mão atual com a anterior (`Counter`, não
`frozenset` — gêmeas dos 2 baralhos contam duas vezes) e emite `draw` se entrou exatamente uma
carta, `discard` se saiu exatamente uma. Troca simultânea ou salto de várias cartas é leitura
instável: a referência é atualizada e nenhum evento sai. Mão vazia zera a referência sem emitir
nada — quando ela voltar, a primeira leitura vira a nova base.

Compra do lixo × do monte sai de `_discard_history`: se a carta nova na mão já passou pelo topo do
lixo, `source = "lixo"` (overlay mostra o selo). `undo_last` e `correct_event` desfazem também o
efeito no histórico do lixo, para a mesma carta poder ser detectada de novo.

`on_stable_hand` e `on_stable_top_card` são o modelo ANTIGO, de duas câmeras, e **não são mais
chamados pelo app** — só por `scripts/demo_server.py` e pelos testes. Ver "Código morto" nas notas.

## Detecção: limiar baixo é de propósito

`config.min_confidence = 0.30`. Quem filtra ruído é a votação temporal, não o limiar — limiar alto
cortava cartas reais de confiança média.

`fan_match_dist = 50`, **re-medido em 2026-07-30** com o leque grande no quadro e segurado na mão:
jitter da mesma carta = 29,5 px médio / 66 px p95; espaçamento entre vizinhas = 44 px mín, 69 px
p05, 111 px p50. (Os 30 px de antes vinham do setup antigo, com o leque longe: jitter de 3 px,
p95 8 px, espaçamento 47 px.) 50 px atende o caso típico — acima do jitter médio e abaixo do
espaçamento p05. Não existe valor que atenda os dois EXTREMOS; ver "Leque parado vale mais que
qualquer parâmetro". Ao mexer nesses números, meça de novo com `dump_dets.py` e registre no commit.

`confirm_confidence = 0.85` marcaria o evento como "confirmar?" no painel (amarelo), mas hoje é
**letra morta**: `on_hand_changed` emite sempre com confiança 1.0, então nenhum evento sai
pendente. Quem carregava a confiança era `on_stable_top_card`, do modelo de duas câmeras.

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
cartas (p05 = 69 px) — não existe `fan_match_dist` que atenda os dois extremos.

O conserto estrutural — compensar a translação GLOBAL do leque antes de casar as vagas
— **já existe** desde `a542f75` (2026-07-30): `FanReader._estimate_shift`, chamado em
`hand_reader.py:196`, mede o deslocamento comum por VOTAÇÃO (cada par detecção/vaga
propõe um deslocamento; vence o mais votado, e só com suporte de metade das vagas) e
desloca todas as vagas antes do casamento. Este parágrafo dizia o contrário até
2026-08-12; o comentário do `config.py` também. Ao ler qualquer conselho de "apoiar a
mão para reduzir o jitter", lembre que o tremor GLOBAL já é compensado — o que sobra
é o movimento relativo entre cartas.

### Enquadramento é metade do resultado

Na mesma sessão, com o leque a ~1,5-2 m da câmera ele ocupava ~450×370 px de um frame 1920×1080 →
o índice de canto chegava ao modelo com ~20×30 px após o resize para `imgsz=1280`. Nessa condição o
4♣ saía com confiança média 0.32 (contra 0.74 do 4♥) e o 5♠ era lido como J♠ (peso 160 × 76).
Aproximar o leque até preencher boa parte do quadro corrigiu ambos. **Antes de culpar o modelo ou
retreinar, confira o tamanho do índice no quadro.**

### O leque tem de estar em ARCO, não enfileirado

Medido em 2026-08-04, comparando as leituras que falharam com a que fechou um turno inteiro certo.
Nas que falharam, os 9 índices vinham quase na mesma altura (`y` variando ~50 px) e espremidos em
645 px de largura — um terço do quadro, com os cantos vizinhos a ~70 px. Na que funcionou, o `y`
descrevia um arco de ~290 px: pontas embaixo, meio no alto.

O motivo é geométrico, não de modelo: **num arco, duas cartas vizinhas se separam na horizontal E
na vertical**; enfileiradas, só na horizontal, e aí basta um tremor para uma cobrir a outra e as
duas caírem na mesma vaga. Foi assim três vezes na mesma sessão (7♣ com 9♠ duas vezes, 10♦ com 9♠
uma). Todas com **10 cartas** — é no instante da compra que o leque aperta e o leitor fica frágil.

Critério prático para conferir sem medir nada: no `/stream/hand`, **as caixas verdes não podem se
encostar**. Duas coladas indicam onde vai falhar.

Cuidado com esse critério, porém: "caixas encostando" é um PROXY visual, e pessimista. Quem casa
vaga é a distância EUCLIDIANA entre centros contra `fan_match_dist` (`hand_reader.py:93`) — duas
caixas podem se encostar com os centros a 70 px, que é folgado. Ao medir de verdade, meça centros.

### Comparar o aperto do leque: sintético × real (e como errei a medição duas vezes)

Em 2026-08-12 tentei explicar o erro de valor do modelo por "o leque real é mais apertado do que
qualquer coisa que o gerador produziu". **A hipótese não se sustentou**, mas a medição ficou — e
as duas armadilhas em que caí valem mais que a hipótese.

A grandeza que compara sintético e real apesar de canvas e câmera diferentes é **adimensional**:
distância entre índices vizinhos ÷ largura do índice. Abaixo de 1, os índices se sobrepõem.

| | sintético | 2026-08-11 | 2026-08-12 |
|---|---|---|---|
| mediana | 0,89 | 0,78 | 0,74 |
| p05 | 0,67 | 0,50 | 0,50 |
| pares sobrepostos | 72,9% | 77,8% | 79,6% |
| (px: dist / largura) | — | 79,6 / 102 | 81,1 / 109 |

O sintético é **modestamente mais frouxo** que o real — ~15% na mediana, e a cauda vai a 0,67 em
vez de 0,50. Existe uma lacuna, mas é bem menor do que parecia.

**Duas armadilhas de medição, ambas caídas em 2026-08-12, e as duas inflaram a conclusão:**

1. **Deduzir do parâmetro em vez de medir o rótulo.** Olhando só `generate_fans.py` (passo de
   0,20-0,32 da largura da carta contra 0,18 de índice) parece que o sintético NUNCA sobrepõe
   índices. Falso: 66-73% dos pares se sobrepõem, porque rotação e perspectiva mexem no
   espaçamento tanto quanto o passo. Corolário prático: **mexer no passo quase não move a
   distribuição** — baixar o mínimo de 0,20 para 0,12 mudou a mediana de 0,92 para 0,89.
2. **Medir distância entre vizinhas SEM deduplicar.** As detecções do `sessao.jsonl` são gravadas
   brutas de propósito, então "duas detecções a 20 px" quase sempre é o MESMO canto lido duas
   vezes, não duas cartas. Sem passar pelo `hand_instances` antes, a partida de 2026-08-12 parecia
   ter uma cauda muito mais apertada que a de 11/08 (p05 19,6 px contra 46,5 px) e isso virou
   explicação para a queda dos descartes. Deduplicando, as duas partidas ficam **idênticas**
   (p05 0,50 nas duas). A explicação era um artefato.

**Portanto: a diferença de geometria NÃO explica a diferença de nota entre as duas partidas.**
Fica em aberto o que explica.

### O erro que SOBREVIVE a tudo isto: K♠ lido como A♠

Independente da geometria, este é o fato medido em 2026-08-12 e é o que derrubou os descartes.

Na posição de UMA carta (a mesma vaga, raio de 28 px), o modelo devolveu **A♠ em 471 frames com
confiança média 0,723** contra **K♠ em 149 frames a 0,587**. O rótulo errado venceu em frequência
E em confiança — a votação ponderada do `FanReader` não tinha o que fazer, ele só escolhe entre o
que recebe, e o `hand_instances` fica com a mais confiante de duas leituras do mesmo canto. Na
partida inteira, o A♠ — que **nunca existiu**, não aparece em nenhuma jogada do gabarito — rendeu
**1.949 detecções** contra 6.431 do K♠ real.

O descarte real morreu junto: quando a carta saiu da mão, a vaga já estava rotulada como A♠, e o
diff não fechou. É erro de MODELO, não de pipeline — e um erro que nenhum parâmetro conserta.

**E o instrumento de aceite é cego para ele.** No mesmo dia, com os mesmos pesos,
`eval_classes.py` deu **K = 100% (n=62)** e naipe na mesma cor em 0,7%: o modelo parece excelente.
Já estava escrito que `eval_classes.py` não mede ganho de dado real; agora há um caso em que ele
dá **100% exatamente na classe que falha ao vivo**. Enquanto a validação for só sintética, ela vai
continuar aprovando modelos que erram na mesa.

Consequência prática, e é a lição de método:

- **Erro de classe que só aparece ao vivo pede DADO REAL, não mais sintético.** É para isso que
  `capture_rotulado.py` existe (rotula pela ORDEM, não pelo palpite do modelo, quebrando a
  circularidade do `auto_annotate.py`). Sobre-amostrar rank fraco no gerador já foi tentado em
  30/07 e o K nem estava na lista — e mexer no passo do gerador quase não move a distribuição
  (ver a seção anterior).
- **Um conjunto de validação REAL é o que falta no projeto.** Sem ele, não há como saber se um
  retreino melhorou ou piorou o que importa. A gravação de uma partida + o gabarito revisado é
  matéria-prima para construí-lo.

**RESOLVIDO em 2026-08-18**, e as duas conclusões acima foram o caminho. `extrai_gravacao.py`
transformou as gravações em dado real rotulado; o retreino com ele **zerou as três cartas erradas
da partida**, o A♠ incluído (ver "Retreino de 2026-08-18"). O conjunto de validação real também
existe agora: `eval_classes.py <modelo> <n> training/datasets/real/<partida do holdout>`.
O texto acima fica como está porque o diagnóstico continua correto — e porque a lição de método
(erro que só aparece ao vivo pede dado REAL) é o que produziu o conserto.

### Na BORDA do quadro não nasce carta

Medido na primeira partida gravada (2026-08-11, 9,3 min, 23 jogadas reais). A leitura acertou
**100% das compras e 100% dos descartes** — nenhuma carta errada, nenhuma jogada perdida. Todo o
erro foi **fantasma**: 5 eventos que não aconteceram, e os 5 vindos da mesma causa.

Uma carta que desce abaixo do enquadramento chega ao modelo com o índice **amputado** pela borda,
e ele palpita sobre meio glifo. As caixas do 4♦ fantasma saíam com `y2` exatamente 1080 (a altura
do frame) e confiança mediana **0,43**, contra 0,93 das cartas inteiras. Só **2,0%** das detecções
da partida ficavam coladas na borda, mas **34%** das do fantasma ficavam — 17× a taxa base.

Dois sintomas opostos, mesma origem:

- **Carta que nasce na borda** (4♦): vira vaga espúria. Numa mão de 9, vaga espúria é a décima —
  e a décima é exatamente a que o teto `hand_size + 1` existe para PERMITIR, no instante da
  compra. Rendeu quatro eventos falsos em cadeia (compra, descarte, compra "do lixo", descarte),
  porque o descarte fantasma alimenta o `_discard_history`.
- **Carta que sai pela borda** (3♦): o leque encolhe uma carta e sai um descarte que não houve.
  A carta saiu do QUADRO, não da mão.

`fan_borda = 8` px resolve o primeiro: detecção que encosta na zona morta **não pode criar vaga**,
mas continua **votando em vaga existente** — suprimir o voto mataria a vaga mais rápido, que é o
segundo sintoma. Medido contra a partida: 2 a 14 px dão resultado idêntico (4 dos 5 fantasmas
somem, 100%/100% preservados); em 18 px começa a cortar carta legítima e um descarte sai errado.
8 é o meio do platô. Custo assumido e testado: carta que **salta** para a borda (mais que
`match_dist` de uma vez) some da mão em vez de criar vaga.

**Revisto em 2026-08-12, e o segundo sintoma NÃO estava aberto — estava mal medido.** O 3♦ tinha
sido revisado como fantasma puro, mas a checagem de alternância do gabarito (ver "O erro de revisão
que INFLA a nota") revelou que **faltava um descarte real de 3♦** logo depois. Os dois são o MESMO
3♦ em sequência: o evento saiu cedo, quando a carta deixou o QUADRO; quando ela saiu de fato da
MÃO, o leitor já a tinha dado por ausente e nenhum evento saiu. Um fantasma e uma jogada perdida
pela mesma causa, e a revisão original contou só metade.

Com o gabarito corrigido e `fan_borda = 8`, a partida de 2026-08-11 fica em **12/12 compras e 12/12
descartes, zero fantasmas**: a regra não só matou o fantasma como **recuperou o descarte real**.
É a validação de verdade do `fan_borda`, agora contra um gabarito correto — antes ela media 100%
num denominador que estava faltando uma jogada.

O conserto de fundo continua sendo **enquadramento**: o leque não pode encostar na borda de baixo.

**Hipótese refutada na mesma medição**: subir o `min_confidence` não resolve. Varrido contra a
partida real, 0,50 mata fantasma mas derruba os descartes de 100% para 81,8% (carta legítima de
confiança média vira carta errada). Confirma com número o que o projeto já dizia. Fica em 0,30.

### A câmera da mão não pode pegar cartas na mesa

Ela conta tudo o que vê. Um 10♣ largado no canto superior direito do quadro entrou na mão exibida
como décima carta (confiança ~0.5, metade da das cartas do leque, porque estava longe) e travou o
teste: a mão já estava em 10, e a compra levaria a 11 — tamanho implausível, que o `StableHand`
congela. Tirar a carta do quadro gerou ainda um descarte fantasma dela.

### Os índices de câmera do Windows não são estáveis

Em 2026-08-04 a webcam USB externa (a da MÃO) saiu do índice 1 para o 0 sozinha, e o app passou a
tratar a interna do notebook como mão. O Windows renumera ao desconectar/reconectar o USB ou
reiniciar. Sintoma: o preview "Câmera da mão" do painel mostra a câmera errada; conserto: trocar
`hand_cam_index` e `discard_cam_index` (ou conferir com `scripts/check_cams.py`).

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

#### As guardas do `capture_rotulado.py` NÃO bastam — confira a imagem

Medido em 2026-08-04: uma captura de 63 frames passou por todas as guardas com os **quatro
oitos rotulados errados** (a mão informada tinha os naipes numa ordem, a mão física em outra).
`MIN_CONCORDA = 0.5` deixou passar porque 5 das 9 cartas batiam — as outras cinco estavam certas.
Treinar com aquilo teria ensinado exatamente a confusão de naipe que a captura existia para
consertar. Foram rejeitadas apagando as imagens de `review/`, que é o mecanismo previsto.

Duas assinaturas que denunciam ordem trocada, e valem como regra de leitura do log:

- **Concordância CONSTANTE** ("sempre 5/9") = um conjunto FIXO de cartas não bate. Modelo errando
  de verdade oscila (7/9, 9/9, 8/9) porque depende do ângulo e do foco. Constante é rótulo.
- **Concordância alta com um par vizinho trocado** (7/9) passa fácil na guarda. Acontece quando o
  leque abre para CIMA em vez de para os lados: medido, as três primeiras cartas saíram a 3 e 9 px
  de distância horizontal uma da outra, e a ordenação por x que dá o rótulo vira sorteio a cada
  tremor. Antes de gravar, exija dezenas de px entre cantos vizinhos.

Procedimento que fecha o buraco: **antes da captura longa, rode `training/ver_ordem.py` e OLHE a
imagem** — ele numera as detecções da esquerda para a direita, avisa quando o menor gap entre
cantos fica abaixo de 25 px e já imprime a linha de comando do `capture_rotulado.py` com a ordem
lida. Custa 10 s e é a única verificação que não depende do que o modelo acha.

### Dado real SEM jogar de novo: `extrai_gravacao.py` (2026-08-18)

O `capture_rotulado.py` resolve a circularidade, mas cobra uma sessão inteira segurando o baralho —
e o usuário já disse que não consegue ficar 20 min nisso. As partidas gravadas já estão no disco
com vídeo cru e gabarito revisado, e isso basta:

```
mão inicial  +  compras e descartes do gabarito  =  mão verdadeira em cada instante
```

O rótulo de cada detecção vem da POSIÇÃO dela no leque, como no fluxo ao vivo, mas a verdade vem
do gabarito. Custo para o jogador: **zero**.

A mão inicial é o único elo frouxo: o gabarito só PROVA as cartas que foram descartadas sem terem
sido compradas (4 de 9 em 11/08, 5 de 9 em 12/08). O script recusa a partida se houver
contradição, e imprime quais cartas vêm da leitura do modelo — **as duas mãos iniciais foram
conferidas OLHANDO o frame** (batem exatamente com a mão exibida).

**A ordem física do leque não está no gabarito, e é aí que mora todo o risco.** O gabarito dá o
CONJUNTO; casar conjunto com posições é o que pode sair errado — e sai. Três coisas medidas, todas
descobertas auditando as imagens, nenhuma delas óbvia no código:

- **A ordem muda DENTRO do turno.** Resolver uma ordem só por segmento (o trecho entre duas
  jogadas) rotula deslocado a partir do instante em que o jogador reorganiza o leque. A assinatura
  é inconfundível: as correções formam um CICLO entre cartas vizinhas (medido em 12/08:
  `AD->AH`, `AH->7S`, `7S->AD`). Vendo bloco a bloco dá para ver o jogador **deslizando o 7♠** pelo
  leque entre 66,6 s e 74,6 s. Por isso a ordem é votada por BLOCO de 50 frames, não por segmento.
- **Detecção fora da fileira do leque.** O canto de BAIXO de uma carta virada, e uma carta largada
  na MESA dentro do quadro, entram na contagem e a ordenação por x mete a intrusa no meio: 8♠ saiu
  rotulado A♥. Guarda: salto vertical entre índices vizinhos, em alturas de caixa — medido,
  mediana 0,28 e p99 1,25, depois um vão até uma cauda de 3,5-4,3. **Qualquer limiar de 1,5 a 3,0
  corta os mesmos 3,7% dos frames** (platô, como no `MERGE_FACTOR`), então 2,0.
- **Deslocamento de uma casa** por detecção sobrando ou faltando. Contagem, buraco e concordância
  NÃO pegam esse caso (metade dos rótulos continua batendo). Guarda: se a leitura do frame é
  explicada igual de bem por um deslocamento a partir de qualquer ponto de corte, o frame cai.
  O empate tem de reprovar: com a comparação estrita (só reprovar se o deslocado for MELHOR), o
  `KS->9S` que a auditoria provou errado volta para o dataset.

Resultado com as três guardas: **721 frames, ~6.750 rótulos** (403 de 11/08 e 318 de 12/08), taxa
de correção 1,4% (12/08) e 0,8% (11/08). As correções são as confusões que o projeto já conhecia — `AS->KS` (a falha que
derrubou os descartes), `7C->7S` (naipe na mesma cor), `AH->4H` (o A↔4).

**A auditoria não é opcional, e é o método**: monte uma folha de contato só com os recortes
CORRIGIDOS e olhe. Na primeira rodada, 4 de 6 correções amostradas estavam erradas — as guardas
vieram todas de olhar essas imagens, não de raciocinar sobre o código. Mesmo na versão final
sobraram 3 rótulos ruins em 11/08, rejeitados apagando a imagem de `review/` (o mesmo mecanismo do
fluxo local; o `finetune_local.py` respeita).

`finetune_local.py --holdout <partida>` deixa uma partida FORA do treino. Sem isso não sobra
gravação com que medir: `replay.py --redetectar` contra a partida que treinou o modelo mede
decoreba, não acerto.

### Hipótese refutada: nitidez do frame não separa acerto de erro

O erro A↔4 aparecia mais com a câmera balançando, o que sugeria filtrar frames borrados
antes da detecção. **Medido e descartado**: variância do Laplaciano de 2121 (mediana) nos
frames certos contra 2096 nos errados — 1% de diferença, distribuições sobrepostas.
Cortar no p10 dos certos descartaria 17% dos erros e 10% dos acertos. Não é filtro, é
moeda. Não reimplemente isso sem medir de novo num setup diferente.

Fluxo local de fine-tuning (sem nuvem), detalhes em `training/README.md`:
`capture_deck.py` → `generate_fans.py` → `capture_auto.py` → `auto_annotate.py` →
**revisão manual** → `finetune_local.py`.

Havendo partida gravada com gabarito revisado, `extrai_gravacao.py` substitui `capture_auto.py` +
`auto_annotate.py` com vantagem: o rótulo vem do gabarito em vez do palpite do modelo, e não custa
tempo de jogo nenhum.

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

**Retreinos de 2026-07-30** (duas rodadas, backups `cards_backup_3.pt` e `cards_backup_4.pt`):

1. *Peso nos ranks fracos.* `generate_fans.py` sorteava as 52 cartas por igual; passou a dar
   `PESO_RANK_FRACO = 2.5` aos ranks que a medição apontou como piores (A, 3, 4, 5, 8), que eram
   também os das confusões dominantes (5→3, A↔4, 8→6). Medido no MESMO conjunto de validação:
   classe correta 96,6% → **97,9%**; naipe na mesma cor 1,5% → 1,1%; leque aberto 92,9% → 95,3%.
   Os cinco alvos subiram (A +2,1, 4 +1,9, 3 +1,9, 5 +1,6, 8 +1,0). **Custo mecânico de
   sobre-amostrar: alguém paga a conta** — o J caiu de 95,3% para 94,2% e virou o pior rank.
2. *30% de dado real rotulado pela ORDEM* (213 frames, contra 6% antes). Sem número offline para
   essa: `eval_classes.py` roda em sintético e não mede ganho de dado real. Validada ao vivo — a
   confusão A↔4, que sobreviveu a tudo antes, "quase não confunde mais".

Cuidado ao retreinar: `finetune_local.py` passa `lr0=0.0003`, mas o Ultralytics usa
`optimizer='auto'` e **ignora esse valor** ("optimizer=auto found, ignoring 'lr0'"),
escolhendo AdamW com lr≈0.00018. A intenção do código não é honrada; se o lr importar,
passe `optimizer='AdamW'` explicitamente.

Em `generate_fans.py`, a caixa do índice é **medida em cada molde** (`detect_corner_tl`), não fixa:
os moldes não saem todos alinhados do `capture_deck.py` e a caixa fixa caía na mesa em vez de no
glifo (cobria 71% do índice no 4C, 76% no AC — justamente A e 4, os valores que o modelo mais
errava).

Meta de aceite do projeto: ≥95% dos descartes e ≥90% das compras corretos numa partida de teste.

**Onde a meta está (2026-08-12, gabaritos corrigidos, config atual):**

| partida | compras | descartes |
|---|---|---|
| 2026-08-11 (9,3 min) | 12/12 = 100% | 12/12 = 100% |
| 2026-08-12 (14,8 min) | 20/20 = 100% | 13/19 = 68,4% |
| **acumulado** | **32/32 = 100%** ✅ | **25/31 = 80,6%** ❌ |

Compras batem a meta com folga e **nunca erraram uma carta** em 32 jogadas. Descartes não batem, e
o erro é concentrado: em 2026-08-12 foram 6 descartes perdidos, com a causa rastreada até o leque
apertado (ver "O leque real é mais APERTADO que qualquer coisa que o gerador produziu").

Ao comparar as duas partidas, note que 12/12 contra 13/19 dá p ≈ 0,06 num teste exato: é
**sugestivo, não conclusivo**, de que a segunda foi genuinamente pior. Com denominadores de 12 e 19
cada jogada vale 5 a 8 pontos percentuais, e nenhuma conclusão fina sobrevive a isso. Provar ≥95%
com confiança exige ~60 descartes, ou seja ~1 h de jogo acumulada — mas **não precisa ser de uma
vez**: a nota conta jogadas, então partidas curtas somam.

### Retreino de 2026-08-18: o A♠ morreu (dado real vindo das gravações)

Primeiro treino a usar `extrai_gravacao.py`: 2.000 sintéticas novas + 734 frames locais + **294
frames reais de 12/08 rotulados pelo gabarito**, 12 épocas, 1280 px, batch 3, ~25 min. A partida de
11/08 ficou **fora** (`--holdout`), para sobrar com que medir.

Medido com `--redetectar` nas duas partidas, os dois modelos lendo o **MESMO vídeo** — comparação
só vale assim, ver a armadilha logo abaixo:

| | antigo (`cards_backup_7.pt`) | novo |
|---|---|---|
| 11/08 holdout — compras · descartes | 12/12 · 12/12 | 12/12 · 12/12 |
| 12/08 — compras | 17/20 = 85,0% (1 carta errada) | 17/20 = 85,0% (**0 errada**) |
| 12/08 — descartes | 14/19 = 73,7% (2 cartas erradas) | **16/19 = 84,2%** (**0 errada**) |
| acumulado descartes | 26/31 = 83,9% | **28/31 = 90,3%** |
| **cartas erradas** | **3** | **0** |
| fantasmas | 5 | 11 |

**O ganho é exatamente o que se foi buscar**: as três leituras erradas (`draw QS→AS`,
`discard 5D→AS`, `discard QH→8S`) sumiram. O A♠ que nunca existiu na partida — o "erro que
sobrevive a tudo isto" — não aparece mais. Classe correta no conjunto REAL do holdout, com
`eval_classes.py ... training/datasets/real/20260811-211614`: 99,2% → **99,5%** (31 erros → 18).

**O que PIOROU: fantasmas dobraram (5 → 11)**, e é o que fica aberto. Fantasma não baixa a nota (a
conta é sobre jogadas que aconteceram) mas suja o overlay e alimenta o `_discard_history`. Repare
que em `t=148,2s` o fantasma novo é um `discard KS` no mesmo ponto em que o modelo velho dava
`carta_errada 5D→AS`: a carta agora é lida CERTA, mas some do leque por um instante — o que sobrou
ali é instabilidade de PIPELINE, não erro de classe. Suspeita a investigar: nos frames reais só a
MÃO é rotulada, então carta na mesa e monte entram como região visível **sem rótulo**, e este
arquivo já ensina que isso treina o modelo a chamar aquele padrão de fundo.

#### `--redetectar` NÃO é comparável com o número ao vivo

Descoberto ao medir este retreino, e invalida qualquer comparação ingênua entre uma nota antiga e
uma re-detectada. Em 12/08 as compras deram **100% ao vivo** e **85% re-detectadas do vídeo** — e
deram 85% com os DOIS modelos, o velho inclusive. A perda não é do modelo: é do `mao.avi`, que é
MJPG comprimido e não devolve o mesmo pixel que a câmera entregou ao pipeline.

Consequência prática: `--redetectar` compara **modelo com modelo** (mesmo vídeo, mesmo pipeline) e
para isso é ótimo. Não serve para dizer "o sistema está em X%" — esse número só sai ao vivo ou das
detecções gravadas. Ao anotar uma medição, registre SEMPRE por qual caminho ela veio.

## Medir a partida: gravar, repetir, dar nota

O que travava a meta de aceite não era a precisão — era o **custo de cada tentativa**. Testar uma
mudança de parâmetro exigia jogar outra partida de 20 minutos, e a partida seguinte é outra
partida: a comparação misturava "parâmetro novo" com "jogo diferente". Sem gravação, um erro no
minuto 12 deixava como único rastro o `print` do `log_lock`, que some com o terminal.

```powershell
python -m app.main --gravar                              # joga gravando
python scripts/revisar_partida.py gravacoes/<data>       # gabarito (evento a evento)
python scripts/replay.py gravacoes/<data> --gabarito     # a nota
python scripts/replay.py gravacoes/<data> --varre lock_frames=20,30,45 --gabarito
python scripts/replay.py gravacoes/<data> --redetectar models/cards_novo.pt
python training/extrai_gravacao.py gravacoes/<data>       # vira DADO DE TREINO rotulado
```

A gravação (`app/recorder.py`) guarda três coisas, cada uma habilitando um nível de experimento:

| arquivo | permite | custo |
|---|---|---|
| `sessao.jsonl` (detecções **brutas**, antes do `hand_instances`) | mexer em qualquer parâmetro do pipeline, inclusive `MERGE_FACTOR` | ~dezenas de MB |
| `mao.avi` (vídeo cru 1080p) | rodar um **modelo novo** contra a mesma partida | ~7 GB / 20 min |
| `meta.json` (config vigente) | saber quais parâmetros produziram aqueles eventos | nada |

As detecções são gravadas **brutas** de propósito: gravar as já deduplicadas consumiria o
`MERGE_FACTOR` antes do replay, justamente o parâmetro do bug mais caro do projeto. E o vídeo é o
frame **cru**, não o anotado — caixa verde desenhada em cima estraga a re-detecção, que é a razão
de o vídeo existir.

O vídeo é escrito numa thread com fila limitada e escrita **bloqueante**. Bloquear é escolha: se o
disco não acompanhar, o FPS cai à vista e fica nos timestamps, em vez de o vídeo dessincronizar do
JSONL em silêncio — o que estragaria a revisão sem dar sinal nenhum.

### Fidelidade é a promessa que sustenta tudo

`scripts/replay.py` chama o **próprio** `app.main.process_frame`, não uma reimplementação, e o
núcleo mora em `app/replay.py` para ter teste. Sem override, o replay tem de reproduzir os eventos
que saíram ao vivo — ele confere e imprime `fidelidade: OK`. Se divergir, existe estado que a
gravação não captura e **nenhuma conclusão offline vale**. É o que `tests/test_replay_fidelity.py`
guarda: qualquer entrada nova no `process_frame` que não seja gravada quebra esse teste.

Limite que não é óbvio: as detecções gravadas já passaram pelo `min_confidence` da partida (0.30).
O replay pode **subir** esse limiar (filtra o que foi gravado), nunca baixá-lo — para isso é
preciso `--redetectar` a partir do vídeo.

### A nota é sobre as JOGADAS, não sobre os eventos emitidos

`app/scoring.py` (código puro, testado). A conta é

```
acerto = acertos / (acertos + carta_errada + perdidos)
```

O denominador são as jogadas que **aconteceram**. Se fosse "corretos entre os emitidos", um sistema
que emitisse um único descarte na partida e acertasse aquele teria 100% e seria inútil — é o
`test_evento_nenhum_e_zero_por_cento_e_nao_cem`. Fantasmas (evento sem jogada) saem em contagem
própria: não baixam o acerto, mas sujam o overlay.

O casamento com o gabarito é por **subsequência comum máxima**, não posição a posição: perder a
terceira jogada desloca todas as seguintes, e uma comparação posicional marcaria a partida inteira
como errada dali em diante — mediria o deslocamento, não o acerto. Nos buracos, uma jogada real e
um evento do mesmo tipo lado a lado viram `carta_errada`; só o que sobra é perda ou fantasma.

#### O erro de revisão que INFLA a nota: esquecer a tecla `p`

Medido em 2026-08-12, e vale para **todo gabarito já revisado**. O revisor pede um veredito por
EVENTO EMITIDO. Uma jogada que o sistema **não emitiu** não tem evento, logo não aparece na tela e
só entra no gabarito se o revisor apertar `p` ("faltou jogada antes"). Esquecer o `p` não é um erro
neutro: a jogada perdida some do **denominador**, e o acerto sobe.

Aconteceu nas duas partidas revisadas, e a distorção foi grande:

| partida | nota revisada | nota real |
|---|---|---|
| 2026-08-12 | descartes 100,0% (12/12) | **68,4%** (13/19) — 7 descartes faltavam |
| 2026-08-11 | descartes 100,0% (11/11) | 91,7% (11/12) — 1 faltava |

A verificação é **automática e não precisa do vídeo**: na cacheta o turno é compra→descarte, então
**duas compras seguidas no GABARITO são impossíveis**. Cada par `CC` é uma jogada real que faltou
marcar. É a mesma lógica da triagem por alternância da seção seguinte, só que aplicada ao gabarito
em vez de aos eventos — e ali ela vira prova, não triagem, porque o gabarito deveria ser a verdade.

Qual carta era também sai sem o vídeo: a mão exibida é gravada no `sessao.jsonl`, e na janela entre
as duas compras sumiu exatamente uma carta. Nos 8 buracos das duas partidas, os 8 saíram sem
ambiguidade. **Ao revisar uma partida nova, rode essa checagem antes de confiar na nota.**

### Triagem sem gabarito: a alternância

Na cacheta o turno é compra→descarte, sempre alternado. Duas compras seguidas significam ou compra
fantasma ou descarte perdido — dá para achar erro **antes de revisar frame nenhum**, e é o que
permite comparar duas configurações numa partida ainda não revisada. Não é medida de acerto: uma
compra alternada e com a carta errada passa limpa. Serve para triagem.

### FPS é variável escondida, não vaidade de benchmark

**Todos** os parâmetros de tempo do pipeline são contados em FRAMES (`lock_frames=30`,
`fan_window=30`, `fan_expire=24`), então a taxa do laço é o fator de conversão para segundos — e
varia com a carga da GPU. Sem medir, "2 s para trocar a mão" é chute, e um parâmetro afinado numa
sessão significa outra coisa na seguinte. O `FpsMeter` imprime a taxa e a tradução de `lock_frames`
para segundos a cada 5 s; o replay recalcula a taxa exata pelos timestamps gravados.

Na mesma linha, `detect_discard_cam = False` (2026-08-11): a câmera do monte é só preview do painel
e não gera evento desde `f5fdf64`, mas o laço rodava o modelo nela a cada volta — metade da
inferência gasta em nada, o que **dobrava a duração real de cada janela de votação**. Ligue apenas
para diagnosticar aquela câmera.

## Notas

- A webcam não pode estar em uso pelo OBS/navegador. `CameraStream` reabre sozinha a cada 2 s se
  a câmera estiver ocupada ou cair; usa `CAP_DSHOW` + MJPG (YUY2 satura o USB em 1080p+).
- **Código morto** (nada disto é chamado por `app/main.py`; a suíte fica verde porque os testes o
  importam direto, o que esconde que morreu). Antes de "consertar" qualquer um deles, confira se
  está no caminho de verdade:

  | símbolo | substituído por | ainda usado em |
  |---|---|---|
  | `app/hand_view.py` (`HandView`) | `FanReader` + `StableHand` | `tests/test_hand_view.py` |
  | `detector.hand_card_instances` | `hand_instances` | testes |
  | `detector.pick_top_card`, `detector.hand_codes` | — (eram do pipeline do monte) | testes |
  | `app/stability.py` (`StabilityFilter`) | `StableHand` | `tests/test_stability.py` |
  | `tracker.on_stable_top_card`, `tracker.on_stable_hand` | `tracker.on_hand_changed` | `scripts/demo_server.py`, testes |
  | `config.stable_frames`, `config.hand_absent_frames` | — | `tests/test_config.py` |

  Os cinco últimos morreram junto com a segunda câmera em `f5fdf64`. `scripts/demo_server.py`
  (partida simulada) ainda fala a API velha e por isso continua funcionando — mas exercita um
  caminho que o app real não usa mais.
- `assets/cards/` é git-ignored; sem rodar `scripts/download_assets.py` os overlays ficam com
  imagens quebradas.
- Docs de origem em `docs/superpowers/`: o spec (`specs/`) descreve a intenção aprovada; o plano
  (`plans/`) é histórico da implementação e já divergiu do código (ex.: limiar 0.75, um baralho só).
