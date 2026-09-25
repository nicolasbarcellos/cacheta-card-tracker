# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Código, comentários, docstrings e mensagens de commit deste repositório são em **português**. Mantenha o padrão (Conventional Commits com corpo explicando o *porquê* e o que foi medido).

## O objetivo mudou em 2026-08-19 — leia isto antes de qualquer coisa

Este projeto agora tem **uma responsabilidade só: LER AS CARTAS DA MÃO**, com o menor erro possível
e o menor atraso possível. Decisão do cliente: o produto vai ter vários modelos, cada câmera lendo
uma coisa, e **compra e descarte serão de OUTROS modelos**, com outras câmeras.

Três consequências que invalidam parte grande do que está escrito abaixo:

1. **Nada de assumir o jogo.** O mesmo leitor vai servir a pôquer (2 cartas), truco (3), pif-paf e
   cacheta (9). Sumiram o teto de vagas do `FanReader` (`max_slots`) e o filtro de tamanho
   plausível do `StableHand` — os dois só funcionavam sabendo que a mão tinha 9.
2. **Uma câmera só**, a webcam da mão. A câmera do monte de descarte saiu do app, do painel e da
   config.
3. **A métrica mudou.** Não é mais "acertou a compra": é **a mão na tela ser a mão real, agora**.
   Três números, todos medidos por replay contra uma partida gravada:
   - *atraso* — segundos entre a leitura viva mudar e a tela mudar;
   - *contradição* — % de frames em que uma carta lida com confiança ≥ 0,80 não está na tela;
   - *trocas* — quantas vezes a mão exibida mudou (acima do número de jogadas = tremor);
   - *excesso* — % de frames em que a TELA mostra carta que o quadro não mostrou. **Faltava até
     2026-08-20, e a falta era grave**: contradição só cobra carta FALTANDO na tela e ordem só
     compara quando os conjuntos batem, então um leitor que mostrasse TUDO o que já viu tirava nota
     ótima. Foi assim que 44,5% de frames exibindo 17 cartas passaram despercebidos.

   O instrumento é `scripts/mede_leitura.py` (núcleo em `app/leitura.py`, testado). Ele é o
   irmão do `scripts/replay.py`: aquele dá a nota de compra/descarte e precisa de gabarito
   revisado à mão; este dá a nota da TELA e não precisa de gabarito nenhum, porque a verdade de
   referência é o próprio quadro. Roda em qualquer gravação, inclusive nas que ninguém revisou.

Medido na partida de 19/08 (5 min, 27 fps), antes e depois desta virada:

| | antes | agora |
|---|---|---|
| atraso até a tela | 2,57 s | **0,86 s** |
| ordem errada | 16,9% | **1,9%** |
| carta vista fora da tela | 13,3% | **7,5%** |

O que veio de graça: **o atraso era quase todo seguro para o EVENTO**. Um evento errado fica no
histórico para sempre, uma mão exibida errada se corrige no frame seguinte — por isso o
`lock_frames` podia cair de 60 para 20 sem custar acerto (a varredura está no `config.py`).

### Próximo alvo (2026-08-25): o buraco é do MODELO, e o dado para tapá-lo já está em disco

O alvo que estava aqui — *"o `hand_instances` descarta carta que o modelo ENTREGOU"* — foi
**implementado, medido nas seis gravações e REPROVADO**. O fato continua verdadeiro; o conserto
proposto não move a nota. Mecanismo e números: "Deixar os dois palpites do mesmo canto votarem".

O que sobra é o outro pedaço da mesma medição, agora nas seis gravações e com o leitor VIVO:
**64% a 89% das cartas que a TELA mostra e o LEQUE não tem são carta que o modelo não entregou
naquele frame** — nem no leque, nem fora dele, nem como palpite perdedor da fusão. É a cegueira
que este arquivo já descreve em "Onde o modelo perde a carta": buracos de 1,6 s (mediana) a 5 s,
60-88% deles nas PONTAS do leque, sempre precedidos de confiança já degradada (p10 0,34-0,47
contra 0,82-0,88 da base).

**O extrator para isso já existe** (`training/extrai_dificeis.py`, feito no mesmo dia): ele pega os
frames em que UMA vaga do leitor perdeu a detecção, re-detecta do vídeo a 0,05 e só rotula quando o
índice está mesmo visível — 70 frames auditados nas quatro gravações com vídeo. Ver "Dado DIFÍCIL".

**Feito e medido em 25/08**: a perda de detecção caiu **5,69% → 4,97%** (19/08 16:22) e
**4,20% → 3,98%** (11/08), as duas gravações fora do treino, sem custar classe nem carta inventada.
Ver "Retreino de 2026-08-25".

**REFINADO em 2026-09-03, e o alvo agora tem número próprio.** A perda não está espalhada: ela é
**3 a 8 vezes maior no índice muito deitado** do que no índice em pé, e isso se manteve em duas
gravações e três modelos. Antes de tentar consertar de novo, leia "A perda é do índice DEITADO" —
lá estão o instrumento novo (`training/eval_rotacao.py`), as **três hipóteses reprovadas no mesmo
dia** (baixar o limiar, desligar o espelhamento, e a leitura antiga da abertura do gerador) e o
**piso de ruído recalibrado: ~1 ponto, não 0,3**.

### O que a métrica diz hoje, e o número que ninguém tinha medido (2026-08-20)

As duas partidas gravadas em 19/08 (12,8 min e 23,0 min, ~29 fps), medidas pelo `mede_leitura.py`
com a config atual — as detecções são gravadas brutas, então valem para o `lock_frames=20` de
hoje mesmo tendo sido gravadas com 60:

| | 19/08 16:22 | 19/08 15:50 |
|---|---|---|
| atraso até a tela (mediana) | 0,88 s | 0,83 s |
| contradição | 7,3% | 13,8% |
| ordem errada | 0,7% | 0,2% |
| trocas da mão exibida | 17 | 45 |
| cobertura (dos frames COM carta no quadro) | 98,2% | 94,4% |
| atividade (frames com carta / gravação) | 16,5% | 18,5% |

**Linha de base de 2026-08-20**, depois do retreino com negativos, do teto por código e da fração
de oclusão — duas partidas novas, gravadas no dia, com a câmera na parede branca:

| | 20/08 17:42 (antes do teto por código) | 20/08 19:43 (depois) |
|---|---|---|
| atraso até a tela | 0,54 s | **0,52 s** |
| contradição | 39,1% | **12,8%** |
| **excesso** | **48,6%** | **7,8%** |
| ordem errada | 0,6% | 1,0% |
| maior mão exibida | **17 cartas** | **11** (0,3% dos frames) |
| frames com carta repetida | 43,9% | **0** |
| cobertura | 99,4% | 99,2% |

A segunda partida foi jogada **de propósito com muito movimento** (o leque atravessando o quadro,
fechando e reabrindo), que é o que produz vaga órfã. Zero duplicatas em 10.103 frames.

O que sobra da contradição é **erro de modelo que o pipeline conserta**: a maior fatia (`AS`, 314
frames) é a confusão A↔4 — o modelo lê o 4♠ como A♠ com 0,85 ao lado da leitura certa, e a votação
temporal fica com a certa. Some com transição (carta da mão não detectada por um instante). Ou
seja: a TELA esteve certa; a contradição está medindo o modelo, não a exibição.

**O denominador da cobertura é a lição, e eu errei nele primeiro.** Contada sobre todos os frames
da gravação, ela dá 16,6% e 19,4%, e a leitura óbvia — "o leque passa 82% do tempo fora do quadro"
— está errada: a gravação é que ficou rodando com ninguém na frente da câmera. A linha do tempo
mostra na hora (na de 12,8 min o jogo inteiro cabe nos 3 primeiros minutos; na de 23 min o jogo
vem em blocos, com pausas de 100% vazio entre eles). Contada sobre os frames em que HÁ carta no
quadro, a cobertura é 98,2% e 94,4%: quando há o que ler, a tela mostra mão. Por isso o
instrumento publica os dois números separados — *cobertura* e *atividade*.

**O enquadramento, esse, está bom durante o jogo** (medido nos frames com 3+ cartas da partida de
16:22): leque a 631 px da esquerda e 392 px do topo, com folga de 648 px à direita e 399 px
embaixo; índice de 109×152 px, leque ocupando 43% da largura do quadro; e só 0,7% dos frames
encostando na zona morta da borda. Não há aqui o que consertar.

A contradição quase dobra entre as duas partidas (7,3% × 13,8%) e é concentrada em poucas cartas
(na de 23 min, `10S` e `3S` respondem por metade). 97% das ocorrências são de cartas que *foram*
da mão em algum momento — ou seja, é atraso e transição, não carta estranha.

### De que é feito o EXCESSO que sobra, e o que ele mede de verdade (2026-08-24)

Medido nas seis gravações em disco, sem jogar nada. A pergunta era se valia endurecer o teto por
código agora que se sabe que **o usuário joga com UM baralho** (e aí carta repetida na tela é
sempre erro). **A medição reprovou a ideia**, e o que ela achou no lugar é mais útil.

**O excesso não é duplicata.** Separando os frames de excesso em "a tela repete um código" ×
"a tela mostra carta que sumiu do quadro":

| gravação | excesso | só duplicata | só carta parada | código repetido na tela |
|---|---|---|---|---|
| 20/08 19:43 | 7,8% | **0,0%** | 7,8% | 0 |
| 20/08 17:42 | 5,7% | 1,2% (+0,4% misto) | 4,1% | 2,5% |
| 19/08 16:22 | 3,9% | **0,0%** | 3,9% | 0 |
| 19/08 15:50 | 8,4% | **0,0%** | 8,4% | 0 |
| 11/08 | 7,6% | **0,0%** | 7,6% | 0 |
| 12/08 | 6,5% | 0,3% | 6,2% | 1,9% |

Endurecer o teto para um baralho compraria **~1,6 ponto numa gravação de seis** e nada em quatro
delas — enquanto custaria a única proteção que sobra se um dia entrarem dois baralhos. Não foi
feito.

**Um sexto a metade do excesso é comportamento PEDIDO.** Classificando cada frame de excesso pelo
estado do leitor: 16-51% acontecem com o leitor CONGELADO por oclusão (leque fechado, mão na
frente) ou com o quadro VAZIO — os dois casos em que o invariante do projeto manda segurar a mão,
não zerá-la. Cobrar isso é medir a feature como defeito, que é o erro que a contradição já cometeu
com a carta segurada à parte.

**Hipótese refutada na mesma medição:** montar o teto do excesso com o QUADRO inteiro (todas as
detecções) em vez do LEQUE (`ultimo_leque`) quase não muda nada — 3,5% → 3,4% em 11/08, 3,2% →
3,1% em 15:50, 3,3% → 3,3% em 16:22. A carta segurada à parte não infla o excesso como inflava a
contradição.

**O que sobra é o `StableHand`, e ele está CERTO.** Dos frames de excesso em estado normal,
**95-100% são a tela travada**, não vaga viva no `FanReader` (que já expirou a dela). E o buraco
de detecção por trás é enorme: a carta fica **1,6 s (mediana) a 5 s** sem ser detectada, com a mão
inteira no quadro. Na partida de 20/08 19:43, cuja mão real é conhecida (`9S 4S 8H AH 2S KC 7D 5D
JH`), a carta cobrada como sobrando é o `9S` — que **é** da mão. A tela estava certa; quem falhou
foi a detecção, e a memória do pipeline é o que salvou a exibição.

Ou seja: **as duas notas residuais medem o MODELO, não a tela.** O último commit já tinha dito
isso da contradição (a fatia `AS` é a confusão A↔4); agora vale também para o excesso.

**Onde o modelo perde a carta** (buracos de ≥30 frames, as quatro gravações):

| | buracos | na PONTA do leque | base de todas as detecções | confiança no último frame visto | base |
|---|---|---|---|---|---|
| 20/08 19:43 | 45 | 60% | 44% | 0,83 | 0,93 |
| 19/08 16:22 | 8 | 88% | 44% | 0,72 | 0,94 |
| 19/08 15:50 | 19 | 74% | 46% | 0,79 | 0,95 |
| 11/08 | 37 | 70% | 43% | 0,59 | 0,94 |

A perda é ~1,6× mais provável nas PONTAS, e vem sempre precedida de **confiança já degradada** (o
p10 dessas cartas fica em 0,34-0,47, contra 0,82-0,88 da base). Duas explicações medidas e
DESCARTADAS: não é tamanho (caixa de 115 px contra 118 px da base) e não é a carta estar girada no
instante da perda (proporção largura/altura 0,71-0,75, contra base 0,69-0,77).

**Qual ponta NÃO ficou decidido**, e o dado é fraco de propósito para não virar conclusão: no
total dá esquerda 44% × direita 24%, mas numa das gravações inverte (75% à direita) e cada
gravação tem 8-45 buracos. Não separa "dedo cobrindo o índice" de "índice girado no extremo do
arco".

O que ficou medido de sobra, e é geometria pura do setup: **as caixas das pontas são muito mais
gordas que as do meio** — proporção largura/altura 0,82-0,99 na ponta contra 0,61-0,69 no meio, em
todas as gravações. O índice das cartas extremas chega mesmo girado ao modelo; só não é isso que
explica o instante da perda.

O instrumento passou a publicar essa repartição (`mede_leitura.py`, com teste conferido por
mutação). Quem diz que o leitor congelou é o LEITOR (`FanReader.congelado`), não uma cópia da regra
dentro da métrica — a mesma decisão do `ultimo_leque`. Os números de hoje:

| gravação | excesso total | com o leitor congelado | **com o leitor vivo** |
|---|---|---|---|
| 20/08 19:43 | 7,8% | 281 frames | **5,0%** |
| 19/08 16:22 | 3,9% | 22 frames | **3,3%** |
| 19/08 15:50 | 8,4% | 407 frames | **3,2%** |
| 11/08 | 7,6% | 460 frames | **3,5%** |

O total NÃO foi descontado de propósito: mudar o denominador em silêncio esconde, e foi
exatamente o excesso cru que denunciou os 17 cartas. Publicar os dois deixa escolher.

**Quem perde a carta, exatamente** (2026-08-24, sem vídeo — o `sessao.jsonl` guarda as detecções
BRUTAS, que são o que o modelo entregou AO VIVO, então comparar com `ultimo_leque` responde sem
depender do `mao.avi` MJPG). Dos pares "a tela mostra / o leque não tem", com o leitor vivo:

| gravação | pares | o MODELO não entregou | cortada no `hand_instances` | cortada no `_so_o_leque` |
|---|---|---|---|---|
| 20/08 19:43 | 6.776 | 83% | **17%** | 0% |
| 19/08 16:22 | 2.096 | 64% | **36%** | 0% |
| 19/08 15:50 | 4.095 | 67% | **30%** | 2% |
| 11/08 | 5.060 | 89% | **8%** | 3% |

Ou seja: de 8% a 36% das vezes **o modelo entregou a carta acima do limiar e o pipeline a
descartou**. E em **100%** desses casos quem a absorveu tinha rótulo DIFERENTE — são dois palpites
para o mesmo lugar, e o `hand_instances` fica com o mais confiante. A vantagem de quem sobrevive é
mínima: mediana +0,07 de confiança, p10 +0,01.

**A conclusão que estava aqui — "é uma decisão de UM frame, tomada por moeda, antecipando o voto
ponderado no tempo" — foi medida em 2026-08-25 e é FALSA.** Os +0,07 são viés sistemático, não
sorteio: deixar os dois palpites votarem dá o mesmo campeão e a mesma tela. Ver "Deixar os dois
palpites do mesmo canto votarem: REPROVADO". Os números acima continuam valendo; o que caiu foi a
leitura deles.

Confirmado por caminho independente: re-detectando do vídeo só os frames do buraco, a conta deu 18%
"o modelo viu e o pipeline cortou" contra os 17% medidos nas detecções gravadas. E ali também se
mediu que **69% das perdas são cegueira real** — a carta não aparece nem baixando o limiar a 0,05,
que é oclusão física (dedo, carta atrás de carta), não erro de classe.

**Hipótese REFUTADA na mesma medição: o raio de fusão NÃO está comendo a vizinha.** A suspeita era
boa — `MERGE_FACTOR = 0,35` foi calibrado com caixa de 44 px (raio ~15 px) e hoje a menor dimensão
da caixa é de 86-108 px, o que dá raio de 30-38 px. Mas o espaçamento entre vizinhas subiu junto
(p05 de 44 a 59 px): só **0,0-0,3%** dos pares de vizinhas cai dentro do raio mediano. O leque
aproximou-se da câmera e ampliou as duas grandezas na mesma proporção.

**Fica em aberto, e é o próximo fio:** a distância entre a carta cortada e quem a absorveu é
BIMODAL — p50 de 2,0-2,7 px em 20/08 e 11/08 (mesmo canto mesmo, e aí a fusão está certa e o erro
é de classe) contra p50 de 46-48 px em 19/08 16:22 e 15:50, que é a borda do raio das caixas
grandes e já encosta no p05 do espaçamento. As duas populações pedem consertos diferentes e a
medição atual não as separa por causa, só por distância.

Alvo que isto aponta, e que não custa tempo de jogo: os frames em que a carta da ponta é detectada
com **0,34-0,59 de confiança** logo antes de sumir são exatamente o dado difícil que o modelo
precisa, e o rótulo deles sai da POSIÇÃO no leque como no `extrai_gravacao.py`. Hoje aquele script
seleciona frames em que a conta fecha; o que falta é selecionar os frames em que ela quase não
fecha.

#### Deixar os dois palpites do mesmo canto votarem: REPROVADO (2026-08-25)

Era o "próximo alvo" desde 24/08. Foi implementado inteiro e medido: o `hand_instances` passou a
guardar o palpite perdedor da fusão como `alternativas` do canto, e o `FanReader` passou a somar
o FRAME inteiro no total de cada rótulo, em vez de só o vencedor. A regra de "UMA detecção por
vaga" ficou intacta — o que muda não é quem casa com a vaga, é quanto do frame chega à votação.

Antes de medir a nota, a conta de quem some, agora nas SEIS gravações e reproduzindo os números de
24/08 por outro caminho (a carta exibida que falta no leque, com o leitor vivo):

| gravação | pares | **era palpite perdedor da fusão** | estava no quadro, fora do leque | o modelo não entregou |
|---|---|---|---|---|
| 11/08 | 5.027 | 7,7% | 3,3% | **89,0%** |
| 12/08 | 12.709 | 17,5% | 4,7% | **77,9%** |
| 19/08 15:50 | 4.101 | 30,3% | 2,2% | **67,5%** |
| 19/08 16:22 | 2.096 | 36,3% | 0,0% | **63,6%** |
| 20/08 17:42 | 9.490 | 27,8% | 4,1% | **68,1%** |
| 20/08 19:43 | 6.776 | 16,9% | 0,0% | **83,1%** |

E a nota, com esses 8-36% chegando à votação:

| gravação | contradição | excesso |
|---|---|---|
| 11/08 | 10,0% → 10,0% | 7,6% → 7,6% |
| 12/08 | 14,5% → **15,0%** | 6,5% → **7,1%** |
| 19/08 15:50 | 10,9% → 10,9% | 8,4% → 8,4% |
| 19/08 16:22 | 8,0% → 8,0% | 3,9% → 3,9% |
| 20/08 17:42 | 13,9% → **14,7%** | 5,7% → **6,0%** |
| 20/08 19:43 | 12,8% → 12,8% | 7,8% → 7,8% |

Nada em quatro, um pouco PIOR em duas. Foi retirado do código.

**Por que não funciona, e é aqui que o diagnóstico de 24/08 estava errado.** Ele dizia que a fusão
é "uma decisão de UM frame, tomada por moeda". Não é moeda: é viés SISTEMÁTICO. O vencedor ganha
por +0,07 na mediana **em todo frame**, então somar os dois ao longo da janela dá o mesmo campeão
que somar só os vencedores — a votação temporal reproduz a decisão que ela deveria arbitrar. E
quando a disputa é de fato apertada, o vencedor ALTERNA entre frames, e aí os dois rótulos já
chegavam à votação pelo caminho antigo, um frame de cada vez. O que a fusão descartava era só a
MARGEM, e a margem não decide nada.

O custo aparece nas duas gravações que pioraram: com a alternativa votando, o rótulo já
estabelecido na vaga é sustentado por mais tempo (a histerese de `win_margin` protege quem tem
votos), e a tela demora mais a aceitar a leitura nova — que é exatamente o que a contradição
cobra.

Corolário que vale para o `agnostic_nms`: a crítica a ele continua de pé pelo outro motivo (num
leque apertado ele suprime a carta VIZINHA legítima, que é outra posição), mas o argumento "ele
antecipa o voto temporal" acabou de ser medido no estágio seguinte e não se sustentou.

#### O raio de fusão é um QUADRADO, e trocá-lo por um círculo é indiferente

Medido junto, e é um defeito real de implementação que simplesmente não custa nada hoje. O
`MERGE_FACTOR` foi calibrado como RAIO ("dá raio de ~15 px, abaixo dos 19 px do pior
espaçamento"), mas o código compara `abs(dx) < thr and abs(dy) < thr` — um quadrado, cuja diagonal
alcança `thr × 1,41`. Já na calibração original isso passava dos 19 px; hoje, com caixa de
86-108 px, o `thr` mediano vai a 24-45 px e a quina do quadrado chega a 34-63 px, dentro da
distribuição do espaçamento entre vizinhas (p05 44-59 px).

O perfil das detecções que a fusão mata, nas seis gravações, mostra as duas populações separadas:

- **84-97% delas têm rótulo DIFERENTE** do vencedor, e a distância é bimodal — p50 de 0,5 a 3,5 px
  em quatro gravações (mesmo canto, dois palpites) contra p50 de 47 px em 19/08 16:22 (a quina do
  quadrado);
- as de rótulo IGUAL — o caso que a fusão existe para tratar — estão **97,5-100% dentro do
  círculo**. Ou seja, trocar o quadrado pelo círculo não desfaz nada do que a regra faz de
  propósito; ela só deixa de matar de 4,6% a 67,8% das de rótulo diferente, conforme a gravação.

Só que a nota fica igual: contradição 10,0/14,5/10,9/8,0/13,9/12,8% → 10,1/14,7/10,3/8,1/12,9/12,8%
e excesso 7,6/6,5/8,4/3,9/5,7/7,8% → 7,6/6,9/7,9/3,1/4,7/7,7% — melhora em três gravações, piora em
duas. **Não foi trocado**: mudar comportamento sem ganho medido é risco puro. Fica registrado
porque o risco é latente — se o leque se aproximar mais da câmera, ou o espaçamento apertar, a
quina do quadrado volta a comer vizinha e o comentário do `MERGE_FACTOR` vai continuar dizendo
"raio".

### O modelo inventa cartas no AMBIENTE, e desde 19/08 elas chegam à tela

O que a investigação do enquadramento achou de verdade. Na partida de 15:50, **os primeiros 37 s
mostram na tela uma mão de duas cartas (`10C QC`) sem que exista carta nenhuma no quadro**: a
câmera está apontada para a sala, e o modelo lê o logo *"10COC ... LEAGUE"* pintado na parede como
índices de carta. Em outro trecho, a câmera pega uma parede lisa e saem três cartas (`5S 4D KS`)
de textura de reboco. São 9 exibições e ~30 s de tela mostrando mão que não existe.

Não é um fantasma qualquer: é consequência direta da virada de escopo. Até 19/08 o `StableHand` só
aceitava tamanhos `0`, `hand_size` e `hand_size + 1`, e uma "mão" de 2 cartas era descartada de
graça. Agora **qualquer tamanho estável é aceito** — e uma parede é o objeto mais estável que
existe, mais estável que uma mão de verdade. O custo assumido naquele commit ("uma leitura
incompleta mas estável passa a ser exibida") saiu pior do que o previsto: não é leitura incompleta
de uma mão real, é mão que não existe.

Medido, comparando o trecho fantasma (0-37 s) com um trecho de mão real na mesma gravação:

| | fantasma (parede) | mão de verdade |
|---|---|---|
| confiança p50 | 0,40 | 0,94 |
| confiança p95 | 0,94 | 0,98 |
| deslocamento entre frames | p50 1,2 px | p50 1,8 px |

**A hipótese "a parede não se mexe, a mão sim" está REFUTADA**: o leque é segurado firme e anda
1,8 px entre frames, contra 1,2 px do fantasma — não separa nada. A confiança separa na mediana,
mas o p95 do fantasma é 0,94: o logo da parede é lido com a mesma convicção de uma carta boa, e
por isso limiar sozinho também não resolve.

**Subir o `min_confidence` está REFUTADO de novo, agora por um mecanismo NOVO.** Varrido com o
`mede_leitura.py` na partida de 16:22: em 0,45 e acima, a contradição salta de 7,3% para **50%** e
as trocas caem de 17 para 8 — a tela CONGELA numa mão de **12 cartas** por 1.991 dos 3.682 frames.
A causa é a regra de oclusão: com menos detecções por frame, cada frame parece "sumiram cartas", o
leitor congela, as vagas velhas não expiram e a mão exibida cresce e trava. (Na partida de 15:50 o
mesmo limiar até melhora a nota — 13,8% para 11,1% — porque lá ele mata o fantasma da parede. Uma
partida só teria dado a conclusão oposta.)

Fica então o conserto estrutural, que é o do método do projeto: **dado real negativo**. As
gravações já têm ~33 mil frames de sala vazia em disco, de graça, e nenhum deles esteve no treino.
Frame sem carta nenhuma rotulado como fundo é exatamente o que ensina o modelo a não disparar no
logo da parede — e não custa tempo de jogo. Cuidado conhecido: só entram frames em que NÃO HÁ
carta alguma no quadro (índice visível e sem rótulo ensina o contrário do que se quer), o que pede
a auditoria por folha de contato que o `extrai_gravacao.py` já usa.

Duas decisões de medição que mudam o resultado e não são óbvias (as duas estão em `app/leitura.py`,
com teste):

- **A contradição só cobra carta que está NO LEQUE.** A carta segurada à parte fica visível de
  propósito fora da tela desde 19/08; cobrá-la é medir a feature como defeito — vale 9,2% contra
  7,3% na mesma partida. Quem diz o que é leque é o leitor (`FanReader.ultimo_leque`), não uma
  cópia da regra dentro da métrica: cópia diverge em silêncio.
- **O atraso conta a partir da PRIMEIRA vez que a leitura viva mostrou aquele conjunto**, não da
  última vez que ela mudou. A leitura viva pisca (vai a B e volta a A); medindo da última mudança,
  se a tela já mostrava A o atraso saía 0,00 s e entrava na conta. Eram 4 zeros em 20 medidas na
  partida de 16:22, e a correção mexeu na mediana só de 0,86 s para 0,88 s — o defeito era pequeno
  em efeito, mas fabricava medidas que não correspondiam a espera nenhuma.

**O código de compra/descarte continua no repositório** (`tracker.on_hand_changed`, `app/scoring.py`,
`scripts/revisar_partida.py`, o gabarito das gravações). Não foi apagado de propósito: é história
medida e pode servir aos outros modelos. Só não é mais o alvo — as seções sobre nota de compra e
descarte, meta de aceite e gabarito ficam como REGISTRO, não como objetivo.

### Sessão AO VIVO de 2026-09-16: três consertos que o usuário viu na mesa

Sessão com o painel e cinco gravações curtas (`gravacoes/20260916-*`). Os três consertos saíram de
defeitos que o usuário relatou jogando, e os três foram aprovados por ele ao vivo ("está ótimo").

**1. A volta repetida do laço voltou a não contar (`app/main.py`).** Relato: *"a IA está lendo as
cartas muito rápido... quando puxo o leque e a câmera pega um vulto, ela já está lendo"*. Não era
`lock_frames` baixo: o `7c00b8d` (14/09) tirou a inferência da volta repetida e MANTEVE o
`process_frame` nela, e com isso a volta repetida passou a custar zero. Enquanto a câmera deu 45,8
fps ninguém viu; neste dia ela entregou 30 (pedimos 60 — provável pouca luz) e o laço disparou a
**280-570 voltas/s**, `lock_frames=20` virando **<0,1 s** e `fan_min_appear` aceitando vaga de vulto
em ~20 ms. Agora só imagem NOVA avança o pipeline: o laço anda na taxa da câmera (30-46), que é a
faixa em que todo parâmetro foi medido. **O prognóstico da seção do FPS ("a janela foi de 0,48 s
para 0,44 s") só vale com a câmera acima da GPU** — abaixo dela, sem este conserto, a janela desaba.
Lição: ao ouvir "esperar mais", confira primeiro no `[fps]` se a espera em SEGUNDOS ainda é a medida.

**2. O raio de fusão do `hand_instances` virou CÍRCULO (`app/detector.py`).** O risco latente
registrado em 25/08 ("o raio é um QUADRADO") custou na tela: com o A♠ colado no 4♣, a quina fez o 4♣
apagar a leitura CERTA do A♠ **60 vezes em 10 s**, e o A♣ (a caixa inchando e engolindo o pip de
paus do vizinho, o mecanismo do 9♠ de 26/08) ficou votando sozinho — **102 frames de A♣ na tela →
0** no replay da mesma gravação. Nas 11 gravações antigas: contradição melhora em 6, piora em 3 (até
+0,7), excesso/atraso/cobertura iguais, ordem piora ~1 ponto em duas — tudo na faixa do ruído. Ao
vivo, com o mesmo leque, sobrou UM A♣ de 1,1 s, e esse é erro de MODELO puro (A♣ a 0,80-0,91 acima
do A♠ no mesmo canto), não de fusão. Guardado por `test_vizinha_na_DIAGONAL_nao_apaga_a_carta_colada`
(caixas reais do frame 6646), conferido por mutação.

**3. Trava de AGITAÇÃO: com mão mexendo no leque, a tela segura a mão anterior.** Pedido explícito:
*"enquanto ele perceber que tem uma mão mexendo no leque e bagunçando, é para manter as cartas que
já estavam mostrando"*. O `FanReader` publica `agitacao` (mediana do deslocamento das cartas entre
frames, em larguras de caixa, suavizada com alfa 0,3) e `calmo`; o `StableHand.update(calmo=)` zera
a contagem de estabilidade e não reordena enquanto agitado. Medido na partida das 15:47: leque
parado p50 **0,007**, mão arrumando p50 **0,059**, jogo normal 0,021. **Mão VAZIA entra mesmo
agitada** — o quadro vazio conta como agitado, e sem a exceção a tela ficou 60 s exibindo 9 cartas
com a câmera vazia (achado na primeira varredura). No trecho da bagunça daquela partida a tela
mostrava 1 carta, depois 8♦ duplicado, depois um 8♠ inexistente (5 mãos em 6 s); com a trava, segura
e vai direto às 9 certas.

`fan_calmo_max` varrido nas 14 gravações (mãos exibidas por < 2 s, somadas: 132 sem trava):

| limite | mãos < 2 s | atraso típico | pior atraso | pior cobertura |
|---|---|---|---|---|
| 0,05 | ~60 | +0,1-0,2 s | **1,91 s** | 88,8% (era 96,2%) |
| **0,08** | **74** | **~+0,1 s** | 1,20 s | 89,3% |
| 0,12 | ~95 | ~0 | 0,92 s | 90,3% |

Ficou 0,08. Guardado por 8 testes (`test_stable_hand.py`, `test_hand_reader.py`), com as três
metades conferidas por mutação (sem trava, sem a exceção da mão vazia, reordenando agitado).
**Ressalva: a trava ainda não foi exercitada numa bagunça AO VIVO** — a partida das 16:07 não teve
nenhuma, e ali ela só custou +0,2 s de atraso.

#### Carta EMBAIXO de carta: investigado e NÃO consertado

Partida das 15:47, t=107-124 s: tela com **8 cartas por 17 s**, leque parado, sem o 5♠. Mecanismo:
o 5♠ ficou a 38 px do 3♠ (vizinhas normais: ≥ 69 px), com o glifo meio coberto, e **o modelo o lê
como "3S" em ~metade dos frames**. Duas leituras "3S" a < 50 px são o "mesmo canto lido duas vezes"
(regra de 04/08, real), a vaga fica com votos empatados (5S 25 × 3S 23) e a outra carta é descartada
ou fundida como gêmea. Três variações MEDIDAS e REPROVADAS, não repita:

- regra de gêmeas pelo líder ATUAL dos votos em vez do rótulo guardado → igual, 8 cartas;
- aceitar par de leituras fortes (≥ 0,7) coladas como duas cartas → igual, 8 cartas (o `fan_peso_min`
  corta a nova como duplicata fraca);
- isso mais `fan_peso_min` desligado → 9 cartas, **mas "3S 3S"** — e desligar o piso já foi medido em
  19/08 levando a contradição de 7,5% a 32,7%.

A informação "é um 5♠" não chega ao pipeline; qualquer regra só escolhe QUAL erro exibir. O conserto
é físico (índice de cada carta visível) ou de modelo (índice parcialmente coberto).

#### A perda de detecção é do MOVIMENTO, e a rotação a multiplica

Pergunta: por que o leque aberto e PARADO (15:40) perdeu 0,26% no índice muito deitado, contra
12-15% das partidas de 26/08 e 28/08? Não é câmera nem luz nem código: a partida de 15:47, mesmo
dia e mesma câmera, perdeu **12,4%**. Repartindo a perda pela `agitacao` do leitor:

| perda de detecção | parado (< 0,02) | leve | mexendo (≥ 0,08) |
|---|---|---|---|
| partida 16/09 15:47 — global | **2,6%** | 6,0% | **21%** |
| partida 28/08 — global | **3,0%** | 7,1% | **23%** |
| 16/09 — em pé / muito deitado | 0,4% / 6,6% | 4,3% / 16% | 19% / 38% |
| teste posado 16/09 15:40 — global | 0,08% | 0,4% | 9% |

Duas partidas com três semanas de distância dão os mesmos números. O posado ficou parado 84% do
tempo; a partida, 48%. **A nitidez (variância do Laplaciano no retângulo do leque) cai pela metade
com movimento**: 4.499 parado, 3.276 leve, 2.349 mexendo — com a câmera a 30 fps por pouca luz, a
exposição longa borra. Hipótese NÃO testada ainda: mais luz → exposição curta → menos borrão e 60 fps
de volta. Parado, sobra pouco (5 inícios de perda em índice muito deitado na partida): 3 são o
POLEGAR sobre a carta da ponta (no posado o leque era segurado pela base) e 2 são índice girado ~90°
totalmente visível que o modelo não lê — a fraqueza de rotação já conhecida. Na tela o efeito é
menor do que a perda sugere, porque a trava de agitação segura a mão justamente nesses momentos.

#### A NOTA das cinco gravações de 16/09, e o que ela fecha (2026-09-17)

Medidas pela primeira vez, com o código de hoje (as detecções são gravadas brutas, então a nota vale
para os três consertos do `bf0f3fe` mesmo nas quatro gravações feitas antes deles):

| | atraso | contradição | excesso (leitor vivo) | vaivém | cobertura | perda detecção |
|---|---|---|---|---|---|---|
| 15:10 | 0,68 s | 9,3% | 11,9% (2,3%) | 0 | 85,0% | 1,28% |
| 15:30 | 0,89 s | 4,9% | 6,6% (0,2%) | 0 | 85,7% | 0,50% |
| 15:40 posado | 0,83 s | 2,5% | 3,9% (0,0%) | 0 | 92,9% | **0,32%** |
| 15:47 bagunça | 0,68 s | 20,8% | 22,3% (2,2%) | 2 | 96,9% | **5,31%** |
| 16:07 (pós-consertos) | 0,90 s | 22,7% | 9,5% (**0,0%**) | 0 | **60,2%** | sem vídeo |

**A obrigação registrada em "o voto duplicado NÃO estava atrapalhando" — *olhar a ordem na próxima
partida gravada* — está cumprida: o vaivém é ZERO em quatro das cinco e 2 na outra**, e a ordem
errada com folga fica em 0,0-0,1%. A histerese de ordem (26/08) e o raio circular (16/09) seguram.
O excesso com o leitor VIVO ficou em 0,0-2,3%, que é a faixa boa desde 26/08.

**A trava de agitação está no valor certo, e agora há número do outro lado.** Varrendo
`fan_calmo_max` nas três gravações mais movimentadas:

| | 0,02 | **0,08 (hoje)** | 1000 (desligada) |
|---|---|---|---|
| 16:07 — cobertura | 53,9% | **60,2%** | 60,4% |
| 16:07 — atraso | 1,56 s | **0,90 s** | 0,67 s |
| 15:10 — cobertura | 77,8% | **85,0%** | 86,5% |
| 15:47 — cobertura | 92,5% | **96,9%** | 96,9% |

Desligá-la custa 0,0-1,5 ponto de cobertura e devolve 0,2 s de atraso; apertá-la para 0,02 cobra
caro (cobertura 60,2% → 53,9%, atraso quase dobra). Ou seja, **a cobertura ruim de 16:07 NÃO é da
trava** — 0,08 já está no platô.

**O que 16/09 mede de verdade é a LUZ.** No mesmo dia, mesma câmera e mesmo baralho, o leque posado
perde 0,32% das detecções e a partida com movimento perde 5,31% — **16×**. É o maior fator já medido
neste projeto, e o conserto é físico. A hipótese do topo desta seção (mais luz → exposição curta →
menos borrão → 60 fps de volta) continua sendo o próximo passo, e continua dependendo de uma
gravação nova.

#### Ensinar o modelo a ler carta BORRADA: refutado antes de treinar (2026-09-17)

A ideia vinha direto da medição acima — se a perda é do movimento e o movimento borra, então falta
borrão no treino. **Falso, e ao contrário.** Nitidez medida como variância do Laplaciano no
retângulo do leque, com tudo reduzido a 1280 como o modelo vê (sem isso, mede-se o resize):

| | p10 | p50 | p90 |
|---|---|---|---|
| **sintético (treino)** | **205** | **2.575** | 4.746 |
| real 16/09 15:40 posado | 3.024 | 6.082 | 6.369 |
| real 16/09 15:47 movimento | 1.975 | 4.766 | 7.710 |
| real 26/08 14:12 | 1.372 | 3.074 | 5.326 |
| real 28/08 | 1.572 | 3.780 | 5.336 |

**As imagens de treino já são mais borradas que as reais em toda a distribuição**, e a cauda delas
(p10 = 205) é um borrão que nenhuma partida produz — o `generate_fans.py` já aplica desfoque em 40%
das imagens (`k` 3 ou 5) mais granulado em 50%. Não há vão a fechar, e teria sido a terceira
tentativa de "dar mais da condição ao modelo" a falhar pelo mesmo motivo das outras duas.

Custo da refutação: 4 minutos de disco contra ~2 h de treino. **Meça, não deduza** — de novo.

#### `imgsz` 1600: REPROVADO, e a triagem sintética errou o palpite (2026-09-17)

Era **a última porta nomeada** por "as portas que continuam abertas atacam a representação". A
aposta tinha um mecanismo novo, achado ao conferir as resoluções do dataset: os **789 frames reais**
são 1920×1080 e o Ultralytics reduz o lado maior a `imgsz`, então **hoje eles entram no treino
encolhidos a 1280 — perdem 33% linear** antes de o modelo os ver, enquanto o sintético (1280×720)
entra inteiro. E o índice muito deitado é o mais BAIXO de todas as faixas (59-67 px de altura),
justamente onde a classe desaba.

A/B com a receita do `backup_11` reproduzida número a número (2.988 imagens, 1.133 reais = 38%, 55
negativos, holdouts de sempre), **e com o controle a 1280 treinado no mesmo dia** — o
`ab-fliplr05` não serve mais de controle porque viu os 75 frames que o `NAO_TREINAR` de 14/09 tirou.

**Critério 1 — triagem sintética: APROVOU, e com folga.**

| faixa | controle 1280 | braço 1600 |
|---|---|---|
| em pé | 98,4% | 98,2% |
| quase deitado | 98,9% | 100,0% |
| deitado (1,0-1,2) | 98,7% | **96,1%** |
| **muito deitado (≥1,2)** | **89,2%** | **93,7%** |
| deitado total (≥1,0) | 93,9% | 94,8% |

+4,5 pontos na faixa alvo — o maior movimento que qualquer tentativa já produziu ali (as duas de
"mais dado deitado" moveram 0 e −1,2). O controle reproduziu o 89,2% histórico, o que valida a
comparação.

**Critério 2 — `eval_rotacao` ao vivo: REPROVOU nas DUAS gravações**, e não por pouco:

| faixa | 28/08 ctrl → 1600 | 26/08 14:12 ctrl → 1600 |
|---|---|---|
| em pé | 4,35% → 4,44% | 0,86% → 0,85% |
| deitado (1,0-1,2) | 4,57% → **6,32%** | 2,23% → **3,17%** |
| **muito deitado** | 14,31% → **16,96%** | 11,86% → **13,64%** |
| GLOBAL | 6,16% → **7,05%** | 2,31% → **2,56%** |

E a TELA piora junto, que é o que decide: contradição **13,7% → 19,3%** em 28/08 e 10,1% → 11,6% em
26/08, ordem 0,6% → 1,2% em 28/08. Atraso, excesso e cobertura ficam iguais.

**Reprovado.** O modelo em produção continua o `cards_backup_11`. Pesos em
`training/runs/ab-imgsz1600/weights/best.pt` e `models/ab_imgsz1600.pt` (não publicados), com o
controle em `ab-ctrl1280`.

**O achado de método é maior que o resultado: a triagem sintética NÃO serve como previsor.** Ela
tinha sido introduzida em 14/09 como "triagem rápida de qualquer retreino que ataque rotação", e o
`degrees=10` foi o primeiro teste — ela reprovou e o decisor confirmou. Este é o segundo, e ela
**aprovou com +4,5 pontos exatamente a faixa em que o modelo depois perdeu 1,8-2,7 pontos ao vivo**.
Uma concordância e uma discordância: ela mede sensibilidade ao defeito, não generalização, e **não
pode decidir nada sozinha**. Quem decide continua sendo `eval_rotacao.py` nas gravações.

Hipótese do porquê, **NÃO medida**: a validação sintética é 1280×720 ampliada para 1600, ou seja
in-distribution para o braço (que treinou nessas mesmas imagens ampliadas), enquanto o frame real
vem de vídeo MJPG reduzido de 1920 para 1600 em vez de 1280 — menos redução, menos supressão do
artefato de compressão.

**O que isto fecha:** com o `imgsz` reprovado, as três famílias de ataque à rotação estão esgotadas
— mais dado deitado (duas tentativas), augment de rotação (`degrees`, reprovado pelo rótulo) e
resolução. **Sobra só a arquitetura maior**, que custa todo o fine-tuning desde julho (o `s` tem
outra forma de tensor e partiria do COCO) e empata com a taxa da câmera. Antes de pagar isso, note
o que a medição de 16/09 diz: a perda é **16× maior com a mão mexendo** do que com o leque parado,
no mesmo dia e mesma câmera. O maior ganho disponível não está no modelo.

### Retreino de 2026-09-17: o 5♦ lido como 3♦, achado pelo USUÁRIO e morto com 15 min dele

**O modelo em produção mudou: `cards.pt` agora é este retreino.** Rollback:
`copy models\cards_backup_14.pt models\cards.pt`.

Relato ao vivo, jogando: *"ele está confundindo o 5 de ouros com 3 de ouros e duplicando o 3 de
ouros"*. Nenhuma métrica tinha apontado isso — a nota dizia só "contradição 30,3%", a pior já
medida, e eu teria caçado o pipeline. **É a segunda vez que o usuário acha jogando o que o número
não mostra** (a primeira foi o vaivém de ordem em 26/08).

**O que a medição achou, e três conclusões minhas que caíram no caminho:**

| hipótese | veredito |
|---|---|
| "é carta na mesa entrando no leque" | **falso** — 8.759 de 8.759 casos dentro da corrente do leque |
| "é o índice deitado" (o alvo do dia) | **falso** — caixa do 5♦ certo e do 3♦ inventado têm a MESMA proporção (0,79, ~25% deitadas nas duas) |
| "nos frames abertos ele lê os dois certo, então não é 5↔3" | **falso** — é sim, em 23% dos frames |

O que sobrou: o modelo entrega **três ou mais `3D` em 39,4% dos frames**, e em 945 deles (23%) não
há nenhum `5D`. A mão tinha **duas 3♦ de verdade** (dois baralhos — confirmado pelo usuário, e o
pipeline deixa gêmeas passarem de propósito), então a terceira é invenção. Confusão de glifo fino,
a família 5→3 que este arquivo registra desde julho.

**O dado saiu da própria gravação, sem custar sessão.** A mão ficou CONSTANTE nos 3,5 min, então a
verdade é o operador quem diz e o rótulo vem da POSIÇÃO no leque — o `capture_rotulado.py` sem
sessão ao vivo. Foi o que o `--mao-fixa` passou a permitir (ver `extrai_gravacao.py`). Duas tomadas,
**ordens diferentes das mesmas 9 cartas** (o 5♦ saiu da 7ª posição para a ponta), que é o que o
repositório exige para o modelo aprender o glifo e não a posição. 140 frames, ~1.260 rótulos, 30
correções 3D↔5D — **todas conferidas na folha de contato, com o glifo legível dentro da caixa**.

**A ordem foi conferida A OLHO nas duas tomadas, e isso não é zelo: eu a tinha tirado da leitura
dominante do MODELO, que contém o erro.**

Os dois comandos, para a extração ser reproduzível (a mão é a verdade dita pelo operador, e o
`gabarito_corrigido.json` de zero jogadas está versionado junto):

```powershell
python training/extrai_gravacao.py gravacoes/20260917-172356 --mao-fixa `
    --mao-inicial "7C JS 9S 3D AS 7H 5D 3D 4C" --por-segmento 120 --intervalo 0.8
python training/extrai_gravacao.py gravacoes/20260917-174349 --mao-fixa `
    --mao-inicial "7C 3D JS 3D 7H 9S AS 4C 5D" --por-segmento 120 --intervalo 0.8
``` Rotular por uma ordem vinda do palpite do modelo é a
circularidade que o `auto_annotate.py` tem e que o `capture_rotulado.py` existe para quebrar.

**A nota, medida na tomada 2 que ficou FORA do treino** (ordem diferente, sessão diferente):

| | `cards_backup_14` (antes) | **novo** |
|---|---|---|
| frames em que o 5♦ SOME (vira 3♦) | 7,4% | **1,0%** |
| frames inventando 3+ × 3♦ | 22,0% | **6,0%** |
| contradição na tela | 17,3% | **8,9%** |
| ordem errada | 0,8% | **0,3%** |

Sem regressão em nada: classe 99,5% → 99,5% no holdout real de 11/08, 98,6% → **98,7%** no
`holdout-ranks`, cartas inventadas **0 → 0**. E melhora nas duas gravações antigas de teste:

| | 26/08 14:12 | 28/08 |
|---|---|---|
| contradição | 10,2% → **9,5%** | 13,3% → **12,3%** |
| excesso | 2,3% → 2,2% | 8,7% → **7,9%** |
| ordem errada | 0,7% → 0,8% | 1,7% → **0,5%** |
| vaivém | 12 → 12 | 22 → **2** |
| cobertura | 96,7% → 96,7% | 94,8% → **95,3%** |
| perda de detecção (global) | 2,16% → 2,38% | 6,32% → **5,42%** |

A perda anda em direções opostas nas duas e as duas cabem no piso de ruído de ~1 ponto: sem sinal.
Tudo o mais melhora ou empata.

**A lição de método, e ela vale mais que o retreino.** No MESMO dia gastei duas rodadas de treino e
várias horas no `imgsz` 1600 atacando o índice deitado — reprovado. **Quinze minutos do usuário
segurando cartas renderam um ganho maior**, porque o dado real, rotulado pela posição, ataca o erro
que existe de verdade em vez do erro que a métrica sugere. É a mesma lição do A♠ em 18/08, e é a
terceira vez que ela aparece.

### O FOCO estava no AUTOMÁTICO, e era o maior fator já medido (2026-09-18)

Sessão ao vivo, em estúdio, para fazer o **teste da luz** que estava pendente desde 16/09. A
hipótese era a que este arquivo registrava: *mais luz → exposição curta → menos borrão → menos
perda*. **Ela está REFUTADA**, e o que apareceu no lugar vale muito mais.

**A refutação, e o sinal que a denuncia.** Com luz de estúdio — brilho **185** dentro do índice e
só **0,7%** de pixel estourado, ou seja luz de sobra e nada queimado — a primeira gravação saiu com
nitidez **2.679 no leque PARADO**, contra 4.579 de 16/09 e 5.269 do leque posado. **Borrão com o
objeto parado e luz de sobra não é exposição nem movimento: é FOCO.** Esse é o sinal que manda
parar de mexer na luz.

**O mecanismo é geométrico, não da câmera: o autofoco mira o que PREENCHE o quadro.** Com a câmera
sobre a mesa, o que preenche é o feltro — e o leque fica mais perto, fora daquele plano. A câmera
abriu com o foco em **14**. Varrendo o foco com o leque parado na posição de jogo
(`scripts/afina_foco.py`, nitidez do Laplaciano no retângulo do leque, com o quadro reduzido a
1280):

| foco | 0 | 30 | 60 | **85-105** | 120 | 180 | 255 |
|---|---|---|---|---|---|---|---|
| nitidez no leque | 501 | 1.138 | 3.234 | **~4.000** | 1.025 | 505 | 97 |

Pico estreito, platô de 85 a 105. `config.cam_foco = 95` (0 devolve ao automático).

**O A/B controlado — mesma mesa, mesma luz, mesmo baralho, mesmo modelo, mesma pessoa, 20 minutos
de diferença.** A perda repartida pela `agitacao` do leitor, que é o controle que impede "ele mexeu
menos" de explicar o resultado:

| perda de detecção | parado | leve | mexendo | global |
|---|---|---|---|---|
| autofoco (14:43) | 3,41% | 14,19% | 27,19% | **15,18%** |
| **foco fixo 95 (15:50)** | **1,55%** | **4,89%** | **17,69%** | **3,75%** |

Cai em TODAS as faixas, e por muito mais que o piso de ruído de ~1 ponto. O global cai mais que as
faixas porque ele também mexeu menos na segunda (4,8% do tempo agitado contra 25,4%) — por isso a
conclusão sai das faixas, não do global. Controle independente: a gravação de foco fixo bate também
a de 16/09 em todas as faixas (2,57 / 5,98 / 21,25).

E a TELA, que é o produto:

| | autofoco | **foco fixo** | melhor anterior (26/08 14:12) |
|---|---|---|---|
| atraso | 0,95 s | 0,92 s | 0,57 s |
| contradição | 13,5% | **9,3%** | 9,2% |
| excesso (leitor vivo) | 16,2% (3,6%) | **0,3% (0,1%)** | 1,6% (0,0%) |
| ordem errada | 2,9% | **0,0%** | 0,5% |
| vaivém de ordem | 33 | **4** | 2 |
| cobertura | 94,4% | **99,7%** | 97,3% |

A nitidez confirma o mecanismo pela repartição: com o leque **parado** ela sobe 2.679 → **3.335**, e
nas faixas com movimento fica igual (1.987 → 1.902 e 1.281 → 1.192). Foco conserta borrão ESTÁTICO;
o de movimento continua sendo da exposição — e o `fan_calmo_max` é quem protege a tela ali.

**Três armadilhas de medição desta sessão, todas caídas antes de virarem conclusão:**

- **Não julgue foco pela contagem de cartas.** No A/B com o leque na mão, **quem rodava PRIMEIRO
  ganhava** — nas duas ordens. O braço desce alguns milímetros a cada dezena de segundos e isso
  mexe mais na contagem do que o foco. Só a nitidez decide; está escrito no docstring do
  `afina_foco.py`.
- **A primeira medição de nitidez estava contaminada.** Ela montava o "retângulo do leque" com
  QUALQUER frame que tivesse detecção — inclusive os que só tinham o fantasma da mesa, e aí o
  retângulo caía no feltro liso e puxava a mediana para baixo. Medir só em frames com **mão de
  verdade** (≥7 detecções) é o conserto.
- **A perda NÃO era do fantasma da mesa.** Repartida por vaga, ela está espalhada pelas 9 cartas
  reais (pior na ponta direita: 4♣ 27,1% e 7♥ 21,2%); as vagas fantasmas valem 1,5% do total.

**Bônus medido: a mesa de estúdio tem cartas IMPRESSAS no feltro** (J♥ Q♥ K♥ A♥ de um lado, J♠ Q♠
K♠ do outro) e **o modelo não morde a isca** — 791 frames de mesa vazia, **zero detecções**. O
retreino com negativos de 20/08 segura o caso que era o pesadelo do logo da parede. Sobra um
fantasma fraco (`10H` a 0,30-0,40 em ~500 frames), do mesmo tamanho do que 16/09 já tinha (`KD`,
541 frames).

**Nota operacional que custou uma gravação:** o `python.exe` do venv é um LANÇADOR — ele sobe o app
num processo FILHO. Mandar `CTRL_BREAK` para o processo que se lançou desliga o uvicorn mas não
chega ao `recorder.close()`, e o índice do AVI sai quebrado (o mesmo sintoma de 28/08: contagem do
AVI muito menor que a do `sessao.jsonl`). Para encerrar de fora é preciso achar o filho; de dentro,
`Ctrl+C` na janela do app continua sendo o caminho. O vídeo quebrado continua utilizável lendo
SEQUENCIALMENTE, que é o que os scripts de medição fazem.

**Ressalva honesta:** é UM par de gravações. O efeito é de 3-4× e o mecanismo está medido por dois
caminhos independentes (a varredura de foco e o A/B), mas a regra do repositório — exigir ganho em
duas gravações — só estará cumprida na próxima partida.

#### Exposição curta: o mecanismo é REAL e o saldo NÃO paga (2026-09-18)

Feita na mesma sessão, logo depois de travar o foco, porque o que sobrou de perda é **borrão de
MOVIMENTO** (parado 1,55%, mexendo 17,69% — 11×). Exposição curta congela movimento; a ideia tinha
sido refutada em 17/09, mas na SALA ESCURA, onde 1/128 s só escurecia. Com luz de estúdio a conta
muda — e mesmo assim não fecha.

**A varredura, com o leque EM MOVIMENTO** (nitidez do Laplaciano no leque, a 1280): automática
2.823 · 1/64 s **4.104** · 1/128 s **4.481** · 1/256 s 4.041 · 1/512 s 2.940. Parecia ganho de 59%.

**E a gravação de 3,1 min desmentiu o saldo**, porque a varredura só mediu o caso em movimento:

| nitidez no leque | parado | leve | mexendo |
|---|---|---|---|
| automática | **3.335** | 1.902 | 1.192 |
| 1/128 s | 2.862 | **2.275** | **1.567** |

Ela ganha 20-31% COM movimento e **perde 14% com o leque parado** — ali não há borrão para congelar
e sobra só o custo de entrar menos luz. A perda de detecção segue o mesmo desenho (parado 1,37% →
1,89%, mexendo 17,19% → 14,34%), e como o jogador fica **parado ~58% do tempo e mexendo ~7%**, o
global PIORA (3,48% → 3,79%) e o excesso na tela sobe de 0,3% para 3,6%.

**Não foi publicado** (`cam_exposicao = None`), pela mesma regra que manteve o `MERGE_FACTOR`
quadrado em 25/08: mudar comportamento sem ganho medido é risco puro. O botão fica no `config.py`,
com os números.

**Quando voltar a isto:** a penalidade do "parado" é falta de luz, não da ideia. Com o leque **mais
iluminado**, a exposição automática escolhe sozinha um tempo curto e não se paga nada — é por aí
que se ataca o borrão de movimento, não por este parâmetro. Valor fixo é amarrado à luz DAQUELE
lugar e, com pouca luz, cega o modelo em silêncio.

**Armadilha de medição, e é a mesma de sempre:** a varredura mediu só a condição que a mudança
ataca (leque em movimento) e por isso aprovou; quem decidiu foi a gravação inteira, que contém as
duas condições. É o mesmo padrão da triagem sintética que aprovou o `imgsz` 1600 em 17/09.

#### A thread do vídeo morta travava o app inteiro

Descoberto do jeito difícil: abri a câmera num script de medição **com o app gravando**, e dois
processos não dividem a mesma câmera. A thread de escrita do vídeo caiu, a fila (30) encheu, o
`frame()` ficou preso no `put` — o laço de visão parou de vez, o `mao.avi` ficou com **0 byte** e
nem o `Ctrl+C` encerrava, porque o `close()` espera na MESMA fila.

Bloquear quando o DISCO não acompanha continua sendo a escolha do projeto. Travar por thread MORTA
não é: agora o `frame()` desiste do vídeo e avisa, e o `close()` tem prazo na fila. Guardado por
`tests/test_recorder_trava.py`, com as duas mutações conferidas — e os testes rodam o trabalho numa
thread com `join(timeout)` de propósito, porque o defeito é uma TRAVA e **teste que trava sob
mutação não prova nada** (a mesma armadilha da âncora do atraso, em 28/08).

**Regra operacional que vale registrar:** enquanto o app estiver gravando, não abra a câmera em
outro processo. Medir pelo `/stream/hand` (HTTP) é seguro; `cv2.VideoCapture` não é.

#### MAIS LUZ NO LEQUE: o jeito certo de atacar o borrão de movimento (2026-09-18)

A conclusão que a exposição fixa apontou, testada em seguida: **iluminar o leque** em vez de forçar
o tempo curto no driver. Aí a exposição automática escolhe o tempo curto sozinha, e sem o custo que
a manual cobrava no leque parado.

Mesma mesa, mesmo foco (95), mesma exposição (automática), ~6 min de jogo em cada:

| nitidez no leque | parado | leve | mexendo |
|---|---|---|---|
| luz de antes | 3.335 | 1.902 | 1.192 |
| **mais luz no leque** | **4.126** | **3.496** | **2.713** |

+24%, +84% e **+127%**. É de longe o maior movimento de nitidez já medido — e some com o borrão de
movimento, que era o fator de 11× que sobrou depois do foco.

**Na perda de detecção das cartas DA MÃO** (separando as vagas transientes, que são carta entrando
e saindo do leque):

| perda de detecção | parado | leve | mexendo | total |
|---|---|---|---|---|
| luz de antes | 1,42% | 4,71% | **17,22%** | 3,56% |
| **mais luz** | 2,15% | **3,04%** | **7,06%** | **2,45%** |

Com a mão mexendo, **−59%**; no total, **−31%**. O "parado" anda para o outro lado (+0,7 ponto) e
está dominado por UMA carta na ponta do leque (`KC`, 15,2% de perda, 47% de toda a perda da
gravação) — é a fraqueza de ponta/índice deitado de sempre, não a luz.

**A hipótese de custo foi medida e REFUTADA: a mesa não vira carta.** A suspeita era que a luz
forte fizesse o modelo ler as cartas IMPRESSAS no feltro do estúdio. Nos trechos ociosos: **0
detecções em 14.661 frames** com a luz nova, e 4 em 14.421 com a luz de antes. (A gravação de 16:25
parece ter 13,5%, mas ali havia cartas DE VERDADE largadas na mesa, lidas a 0,81-0,91.) Os
negativos de 20/08 seguram este cenário — nenhuma extração nova foi feita, e fazer teria sido
trabalho contra defeito inexistente.

**Ressalva:** é um par de gravações, com mãos diferentes. O que sustenta a conclusão é a nitidez
(grandeza física, medida na mesma faixa de agitação) mais a queda da perda na faixa que o mecanismo
ataca. O "parado" fica em aberto.

**A regravação de 25/09, com a MESMA luz, NÃO repetiu o ganho** — ver "A regravação de 2026-09-25".
Com o leque parado ela empata; com movimento, fica no nível da "luz de antes".

**Armadilha operacional desta sessão, e ela contaminou três medições antes de eu notar:** o app
CONTINUOU gravando depois do `Ctrl+C` — o arquivo de 16:48 tinha 3.757 frames quando medi e 20.084
no fim, e o de 15:50 foi de 8.100 a 23.891. Sinal de alerta: a linha do tempo de atividade mostra o
jogo nos primeiros minutos e o resto vazio. **Meça sempre depois de conferir que o processo morreu**
(`Get-CimInstance Win32_Process -Filter "name='python.exe'"`), e note que o `python.exe` do venv é
um lançador: o app roda no processo FILHO. Eventos de console (`CTRL_C`/`CTRL_BREAK`) mandados de
outro processo NÃO o encerram — testados os dois, nas duas formas de grupo.

#### As seis gravações de 2026-09-18, e o que cada uma vale

Todas no estúdio, mesma mesa verde e mesmo baralho. O `meta.json` guarda foco e exposição; **a LUZ
não fica registrada em lugar nenhum**, por isso esta tabela.

| gravação | foco | exposição | luz | serve para |
|---|---|---|---|---|
| `143921` | auto | auto | de antes | teste de desligamento; vídeo com índice quebrado |
| `144344` | **auto** | auto | de antes | **o "antes" do foco** — perda 15,18% |
| `155050` | **95** | auto | de antes | **o "depois" do foco** — perda 3,75%; e o "antes" da luz |
| `161417` | 95 | **−7** | de antes | CONTAMINADA (abri a câmera por fora); `mao.avi` com 0 byte |
| `162550` | 95 | **−7** | de antes | **o teste da exposição fixa** — ~1,5 min de jogo só |
| `164241` | 95 | −7 | **mais luz** | INÚTIL: a câmera engasgou, 1 fps, nenhuma carta |
| `164804` | 95 | auto | **mais luz** | **o "depois" da luz** — perda 2,45% nas cartas da mão |

**Os pares que valem como A/B são `144344 × 155050` (foco) e `155050 × 164804` (luz).** As duas
comparações têm a ressalva de serem UM par cada, com mãos diferentes — o que as sustenta é a
nitidez, que é grandeza física medida na mesma faixa de agitação.

**Cuidado ao usar qualquer uma delas:** o app continuou gravando depois que o jogo acabou, então
cada arquivo tem 8-14 minutos de mesa vazia no fim. Isso não atrapalha a perda (sem carta não há
vaga), mas afunda a *atividade* e muda o denominador da *cobertura*. A linha do tempo de atividade
mostra o corte na hora.

### A gravação de 2026-09-24: o ENQUADRAMENTO custou a medição, e agora tem instrumento

Gravação de 5 min feita para ser a SEGUNDA gravação que confirma o ganho da luz de 18/09 — a
ressalva que aquela sessão deixou aberta ("é UM par de gravações"). **Ela não serviu para isso**, e
o motivo não é a luz: o leque ficou mais LONGE da câmera.

| | 18/09 luz antes | 18/09 mais luz | **24/09** |
|---|---|---|---|
| atraso | 0,92 s | 0,90 s | **0,89 s** |
| contradição | 9,3% | 9,4% | 10,9% |
| excesso (leitor vivo) | 0,3% (0,1%) | 1,6% (1,3%) | 7,7% (3,8%) |
| ordem errada | 0,0% | 0,0% | 0,5% |
| vaivém | 4 | 0 | 16 |
| cobertura | 99,6% | 99,5% | 99,0% |
| **atividade** | 38,3% | 40,4% | **89,9%** |
| **perda de detecção** | **3,48%** | **3,19%** | **5,53%** |

As três medidas com o código de hoje. A gravação de 24/09 é a de **jogo mais real do projeto** —
89,9% dos frames com carta no quadro, contra 38-40% das de 18/09, que ficaram minutos com a mesa
vazia. Isso sozinho infla excesso e vaivém e torna a comparação de TELA fraca; quem decide é a
perda.

**O defeito, e ele é físico:** o índice chegou ao modelo com 97 px de altura (área mediana 6.916 a
1280) contra 105 px (9.055) e 127 px (11.940) das duas de 18/09 — **24% a 42% menor**. A perda cai
fortemente com o tamanho, medido DENTRO de cada gravação, que é o controle que separa "o leque
estava longe" de "a imagem estava pior":

| altura do índice a 1280 | 24/09 | 18/09 mais luz | 18/09 luz antes |
|---|---|---|---|
| < 80 px | 11,60% (**22,8%** do leque) | 7,35% (14,7%) | 19,43% (1,4%) |
| 80-100 | 5,38% (39,8%) | 1,52% (19,7%) | 8,73% (10,2%) |
| 100-120 | 1,90% (37,2%) | 1,04% (51,0%) | 3,18% (22,7%) |
| >= 120 | amostra fina | 8,78% (14,7%) | 2,42% (**65,8%**) |

**Abaixo de 100 px a perda cresce nas TRÊS**, e é a parte firme. Acima de 120 o dado é ambíguo
(8,78% numa, 2,42% na outra) e o modelo é preso à escala — por isso o alvo é uma FAIXA, não um
piso.

**O instrumento que faltava:** `scripts/confere_enquadramento.py`, com o núcleo testado em
`app/enquadramento.py`. Ele é o irmão do `afina_foco.py` e a divisão é clara — aquele acha o foco
da DISTÂNCIA, este confere se a distância é a certa. **Rode os dois, nessa ordem, antes de
gravar.** Foi exatamente o passo que faltou em 24/09: eu conferi o foco e a nitidez e não conferi o
tamanho do índice, que é o primeiro item que este arquivo manda checar desde "Enquadramento é
metade do resultado".

**O que NÃO explica a gravação de 24/09** (tudo medido no mesmo dia, não repetir):

| hipótese | veredito |
|---|---|
| foco errado para a distância | **falso** — nitidez no leque parado **3.990**, empata com a melhor do projeto |
| a luz não estava ligada | **falso** — nitidez com movimento 3.017/2.232, muito acima dos 2.384/1.689 da luz antiga |
| o leque chegou mais deitado | **falso, e ao contrário** — 52,2% em pé contra 43,9% e 46,7% |
| classe errada contando como miss | **falso** — 12,9% da perda, igual aos 13,2% de 18/09 16:48 |
| atribuição por rótulo no meu script | **falso** — refeito pela IDENTIDADE da vaga, deu 1,68% contra 1,61% |

**O que sobra, e fica ABERTO:** controlando tamanho **e** rotação ao mesmo tempo (só índice em pé,
faixa 100-120 px, a única em que as três se sobrepõem), 24/09 perde **1,68%** contra **0,02% e
0,07%**. Nem tamanho, nem rotação, nem nitidez, nem agitação (a mistura de 24/09 é quase a de
15:50), nem classe errada explicam isso. O modo dominante da perda de 24/09 é **classe certa
abaixo do limiar** (38,9%, contra 30,1% de 28/08), que é a assinatura de índice pequeno — mas a
célula casada diz que não é só tamanho.

**O VAIVÉM de 16 não é regressão, e olhar o vídeo resolveu em dois frames.** Catorze dos 16 não são
troca de par: são **6 posições mudando de uma vez**, em duas rajadas, e sempre o mesmo
movimento — `8D 9D 10D [9C] 7D 7H 7S 3H 5D` ⟷ `8D 9D 10D 7D 7H 7S 3H 5D [9C]`, dez vezes em 5,5 s.
No vídeo, o jogador está **tirando o 9♣ do meio do leque e encaixando-o na ponta direita** (e ele
acaba de cabeça para baixo). A tela alterna entre a vaga velha, que leva `fan_expire` ~1,6 s para
morrer, e a nova. É a família "carta tirada do leque e recolocada" que este arquivo registra como
ABERTA desde 19/08 — **não** é o empate de x de 26/08, e a histerese de ordem não tem o que fazer
ali (as duas vagas estão a centenas de px uma da outra).

**A MX Brio saiu do USB durante a sessão**, depois da gravação. O Windows passou a enxergar só a
webcam interna, o índice 0 virou ela e a câmera passou a abrir em **1280x720 com o foco em -1**
(pedindo 95). A gravação não foi afetada — o log dela diz `aberta 1920x1080 | foco FIXO 95` — mas
**a falha é silenciosa** e valeria a sessão seguinte inteira. O `confere_enquadramento.py` avisa
nos dois casos (foco que não pegou, resolução diferente da pedida), e pegou este na primeira
execução. Lição operacional: **o pedido de foco NÃO é garantido**, e foco no automático vale 15,18%
de perda contra 3,75%.

`slots_debug` passou a expor o **`seq` da vaga** (a identidade), porque quem mede precisa
acompanhar UMA vaga entre frames e por rótulo não dá — o rótulo repete (gêmeas dos dois baralhos) e
troca de vaga quando a mão muda. Guardado por `test_slots_debug_expoe_a_IDENTIDADE_da_vaga`,
conferido por mutação nas duas direções (ids colidindo e id que muda a cada frame).

### A regravação de 2026-09-25: o ganho da LUZ não se repetiu

A segunda gravação que a luz de 18/09 pedia (`20260925-150920`, 3,2 min). Desta vez o preparo foi
feito inteiro: `afina_foco.py` (pico em 80-90, ficou o 95 de 18/09 para não misturar duas mudanças)
e `confere_enquadramento.py` (índice a 103 px, OK). **O usuário confirmou que a luz era a mesma** do
"mais luz" de 18/09, e o brilho medido concorda: leque 176 contra 181, índice 185 contra 196,
estouro 0,9% contra 2,4%.

| | 18/09 luz antes | 18/09 mais luz | **25/09 mesma luz** |
|---|---|---|---|
| perda global | 3,48% | 3,19% | **8,22%** |
| perda — cartas da MÃO | 3,56% | 2,45% | **5,97%** |
| mão parado / leve / mexendo | 1,42 / 4,71 / 17,22% | 2,15 / 3,04 / 7,06% | **2,33 / 5,69 / 25,53%** |
| nitidez parado / leve / mexendo¹ | — | 3.093 / 3.274 / 2.738 | **3.247 / 2.485 / 1.464** |
| tempo parado / leve / mexendo | — | 73 / 25 / 2% | **40 / 51 / 9%** |
| altura do índice p50 (< 100 px) | — | 105 px (34%) | **111 px (21%)** |

¹ Nitidez medida pelo script de 16/09, com agitação calculada das próprias caixas. Não é o mesmo
número da seção "MAIS LUZ NO LEQUE", que usou a agitação do leitor; compare só dentro da coluna.

**O que ficou firme:** parado EMPATA (perda 2,33 × 2,15%, nitidez 3.247 × 3.093). Foco e distância
estão resolvidos, e o `confere_enquadramento.py` fez o trabalho: o enquadramento é o melhor dos
quatro.

**O que caiu:** na faixa LEVE a comparação é justa — a agitação mediana é a MESMA (0,033 × 0,032) —
e mesmo assim a nitidez cai 24% e a perda quase dobra, voltando ao nível da "luz de antes" (4,71%).
Com a mesma luz e o mesmo brilho, isso não é luz. **O ganho de 18/09 com movimento está, portanto,
NÃO confirmado**: a mesma luz deu uma vez 3,04% e outra 5,69% na mesma faixa.

**Duas explicações descartadas na hora:** não é rotação (hoje o leque veio MAIS em pé, 51,6% contra
43,9%, e o índice em pé perdeu 5,19% contra 0,53% — a perda está espalhada por todas as faixas) e
não é taxa de quadros (~30 fps nas quatro gravações, 0% repetidos).

**Fica ABERTO:** o que torna a mesma agitação mais borrada num dia que no outro. A agitação é
translação mediana das caixas; ela não vê GIRO de punho nem velocidade DENTRO do intervalo de
exposição, e a exposição automática escolhida não fica gravada (`meta.json` só guarda o pedido).
Gravar o valor de exposição que a câmera usou é o que tornaria isto medível.

"Mexendo" não compara: hoje o movimento foi muito mais forte (p90 da agitação 1,00 contra 0,22) e a
mão ficou parada 40% do tempo contra 73%. É isso que leva a contradição a 23,7% e o global a 8,22%.

## Comandos

```powershell
# setup (PyTorch CUDA primeiro, senão o pip instala a versão CPU)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
python scripts/download_assets.py     # PNGs das 52 cartas em assets/cards/ (git-ignored)

python -m app.main                    # app real (precisa da webcam da mão livre)
python -m app.main --gravar           # idem, gravando a partida para medir depois
python scripts/demo_server.py         # partida simulada, sem webcam — para mexer no overlay/painel

python scripts/mede_leitura.py gravacoes/<data>   # a NOTA: atraso, contradição, trocas

python -m pytest                      # suíte completa (rápida: só código puro)
python -m pytest tests/test_hand_reader.py::test_carta_duplicada_e_FRACA_nao_entra_na_mao
```

**ANTES DE GRAVAR, rode os dois, nesta ordem** (nenhum abre janela; os dois pedem o app FECHADO e
o leque parado na posição de jogo):

```powershell
python scripts/afina_foco.py              # 1. o FOCO da distância
python scripts/confere_enquadramento.py   # 2. a distância está certa?
```

`afina_foco.py` acha o FOCO fixo da câmera. O autofoco mira o feltro, que preenche o quadro, e não
o leque, que fica mais perto — medido em 18/09: perda de detecção **15,18% → 3,75%** só com o foco
travado. Reafira ao mudar a câmera de lugar ou a altura da mesa.

`confere_enquadramento.py` mede a ALTURA do índice na escala do modelo e reprova fora de
100-130 px. Existe porque essa conferência faltou em 24/09 e **custou uma gravação inteira**: foco
certo, nitidez a melhor do projeto, e o índice 24-42% menor que o de 18/09 — perda 5,53% contra
3,19%. Ele também avisa quando o **foco pedido não pegou** ou a câmera abriu noutra resolução; as
duas coisas são falhas silenciosas e a segunda pegou a MX Brio fora do USB na primeira execução.

Diagnóstico de câmera/modelo (todos abrem janela do OpenCV, `q` encerra):
`scripts/check_cams.py` (índices/enquadramento) · `training/aim.py` (mirar) ·
`training/diagnose_live.py` (log ao vivo de carta + confiança) ·
`training/diagnose.py` (estabilidade em ~40 frames) · `training/dump_dets.py` (geometria das caixas).

Comparação entre modelos (sem câmera, roda em disco):

```powershell
python training/eval_classes.py models/cards.pt 150
python training/eval_classes.py models/cards_backup_4.pt 150   # o anterior, MESMO conjunto

# quantas cartas o modelo INVENTA onde nao ha carta (o eval_classes e cego p/ isso)
python training/eval_negativos.py models/cards.pt training/datasets/negativos-holdout

# ONDE o modelo perde: perda de deteccao por ROTACAO do indice, modelo x modelo
# no MESMO video. Os outros tres instrumentos sao cegos a isto -- ver
# "A perda e do indice DEITADO".
python training/eval_rotacao.py gravacoes/<data> sessao-cards.jsonl sessao-cards_novo.jsonl
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
CameraStream(hand) → detect → hand_instances → FanReader → StableHand ─┬→ tracker.set_hand_display  (a MÃO na tela: o produto)
                                                                       └→ tracker.on_hand_changed  (eventos draw/discard: fora de escopo)
```

**UMA câmera, e agora é a única** (`app/main.py:process_frame`). A do monte saiu em 2026-08-19; já
não gerava evento desde `f5fdf64`, quando compra e descarte passaram a sair da MUDANÇA do leque.

A EXIBIÇÃO é atualizada a cada frame e o EVENTO só quando o conjunto muda. Os dois têm requisitos
opostos e é por isso que estão separados: a ordem do leque precisa acompanhar o que se vê AGORA (o
jogador encaixa a carta comprada no meio, e a tela tem de mostrar ali), enquanto o evento precisa
de estabilidade para não disparar em leitura tremida.

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
   maioria simples o errado venceria.

   **O teto de vagas (`max_slots = hand_size + 1`) foi DESLIGADO em 2026-08-19**, junto com a
   virada para ler qualquer jogo: ele só sabia matar vaga espúria porque sabia que a mão tinha 9.
   Quem ficou no lugar dele são as guardas que não dependem do jogo — `min_appear`, `fan_expire`,
   `fan_borda` e, principalmente, o **piso de peso da carta duplicada** (`fan_peso_min`), que
   passou a ser a proteção central: medido, desligá-lo leva a contradição de 7,5% para **32,7%**.
   O corte por `misses` antes de peso continua no `_corta`, e vale se o teto voltar.

   **A carta segurada À PARTE não é da mão** (`_so_o_leque`, 2026-08-19). O jogador pega a carta
   com a outra mão e fica com ela fora do leque enquanto decide onde encaixar; o leitor já a
   mostrava como carta da mão, antes de ela chegar lá. O leque é uma CORRENTE de cartas que se
   encostam, então basta ligar as vizinhas em x que estejam perto e ficar com o maior grupo.

   Duas coisas que a medição ensinou e que não são óbvias:

   - **A distância sozinha não separa.** O leque também se parte quando as cartas do meio deixam
     de ser detectadas, e as duas populações se sobrepõem: nos vãos acima de 1,5 largura de caixa,
     o pedaço de leque tem p50 1,6 e p90 4,0, a carta à parte tem p50 1,9 e p90 5,2. O que separa
     de verdade é a **vaga**: o pedaço do leque tem vaga estabelecida, com votos e posição; a carta
     recém-pega não tem nada. Por isso só cai o grupo que está longe **e** não casa com vaga.
   - **A ordem importa dentro do `update`.** Aplicar o corte ANTES da checagem de oclusão fazia um
     leque momentaneamente partido virar "sumiram 3 cartas", disparar o congelamento e travar a
     tela: medido, a contradição ia de 7,5% para **76%** e a mão exibida mudava 4 vezes numa
     partida inteira. O corte tem de vir depois.

   Duas proteções que vieram antes e também não são óbvias:

   - **Histerese de rótulo** (`fan_win_margin = 2.5`): para TROCAR a carta de uma vaga já
     estabelecida, a concorrente precisa ganhar por essa margem. Sem isso, alguns frames borrados
     viravam o rótulo e a mudança gerava compra e descarte fantasmas. Estabelecer um rótulo
     continua fácil; derrubar um já estabelecido é que ficou difícil. Custo: uma troca REAL de
     carta demora ~22 frames (~1,5 s) para aparecer. Margem só funciona porque, depois do retreino,
     o erro virou rajada curta — com o modelo velho o errado ganhava por 2,28× **sustentado**, e
     margem nenhuma filtraria aquilo.
   - **Queda brusca = oclusão, não jogada** (`146ae94`): ver 1 carta onde havia 9 é o leque
     fechando (as outras ficam atrás da primeira) ou a mão passando na frente. Uma queda GRANDE
     **congela** o leitor: não expira vaga e não mexe na exibição. Antes disso, fechar o leque
     expirava as 8 vagas ocultas e ao reabrir elas nasciam sem histórico de votos — o leitor
     "esquecia" o que já tinha acertado.

     **"Grande" passou a ser uma FRAÇÃO em 2026-08-20 (`FRACAO_OCLUSAO = 0,6`), e a regra antiga
     tinha um estado ABSORVENTE.** Ela era "queda de duas ou mais cartas", o que vinha de a cacheta
     trocar uma carta por vez — premissa que caiu com a virada de escopo. O problema: se a mão
     exibida incha para 12 (vaga velha que ainda não expirou somada à nova) e o quadro mostra as 9
     de verdade, então `9 < 12-1` em TODO frame e o leitor congela **para sempre** — o código que
     reabre (`_occluded >= expire`) só roda num frame NÃO congelado, que nunca chega. Medido na
     partida de 19/08 16:22 re-detectada: uma trava única de **1.936 frames (~78 s)** exibindo 12
     cartas, com a contradição da partida em **50%**. Ao vivo o mesmo estado aparece menor (175
     frames seguidos, 184 frames com 12 cartas na tela), mas aparece.

     A fração separa as duas situações pelo que elas são: leque fechado é 1 de 9 visíveis (11%),
     mão na frente é ~3 de 9 (33%), e mão exibida inchada é 9 de 12 (75%) — que não é oclusão
     nenhuma, é um leque inteiro no quadro com a TELA errada. Efeito medido (o mesmo vídeo, o mesmo
     modelo): contradição **50% → 7,8%** no stream re-detectado, e nos streams ao vivo 7,3% → 6,9%
     e 13,8% → 10,7%. O que a fração relaxa é o caso de duas cartas sumirem de uma vez num leque
     pequeno; ali quem protege a tela continua sendo o `lock_frames`, que exige a leitura nova
     parada por ~0,7 s. Regressão guardada por
     `test_mao_exibida_inchada_nao_congela_o_leitor_para_sempre` — e o outro lado, o leque fechado
     que NÃO pode bagunçar a mão, por `test_closing_the_fan_does_not_scramble_the_hand`.
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
   - **TETO POR CÓDIGO: a carta não está em três lugares se nunca foi vista em
     três lugares** (2026-08-20). O buraco que a remoção do `max_slots` abriu, e
     ele só apareceu na primeira partida gravada DEPOIS daquela remoção: **44,5%
     dos frames exibiam 17 cartas**, com a mesma carta repetida três vezes
     (`5D 5D`, `KC KC KC`, `7D 7D 7D`). Todas as quatro gravações anteriores
     param em 10 — que era exatamente o teto antigo (`hand_size + 1`).

     O mecanismo é o que o próprio `max_slots` existia para matar: o leque se
     move, a carta cria vaga nova e a velha ainda não expirou. E a órfã é
     **forte** — carrega os votos de quando a carta estava ali — então o
     `fan_peso_min`, que só mata duplicata FRACA, não a pega.

     O teto novo continua não sabendo que jogo é este, que era o requisito da
     virada de escopo: ele não diz quantas cartas a mão tem, diz que um CÓDIGO
     não pode aparecer mais vezes do que apareceu num único frame da janela
     recente. Gêmeas legítimas dos dois baralhos aparecem juntas em algum frame
     e sobrevivem; a órfã, não. O desempate usa `misses` antes do peso, pelo
     mesmo motivo do `_corta`: no empate de peso, quem tem de cair é a vaga que
     não corresponde a carta nenhuma no quadro.

     Medido na partida de 20/08: **excesso 48,6% → 5,6%** e contradição 39,1% →
     13,9%. Nas gravações antigas o custo é ~1 ponto de contradição. Guardado
     por `test_carta_nao_aparece_duas_vezes_se_nunca_foi_vista_duas_vezes` e,
     do lado oposto, por `test_gemeas_de_verdade_sobrevivem_ao_teto_por_codigo`.

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

   **Aceita QUALQUER tamanho desde 2026-08-19.** Antes só passavam `0`, `hand_size` e
   `hand_size + 1`, para não exibir a bagunça da transição (no ato de pôr ou tirar uma carta a mão
   passa na frente e a leitura desce a 6, 7, 8 por um segundo). Isso caiu junto com a premissa de
   que o jogo é cacheta. Quem faz esse trabalho agora é só a ESTABILIDADE: a bagunça muda de
   tamanho a cada frame e não sobrevive a `lock_frames`. Custo assumido: uma leitura incompleta
   **mas estável** passa a ser exibida — inevitável, porque "incompleta" só existe quando se sabe
   o tamanho certo.

   A ESTABILIDADE olha o conjunto, não a ordem (duas cartas trocando de lugar por um tremor não é
   mão nova). A ORDEM é tratada à parte, e desde 2026-08-19 ela **acompanha a leitura viva a cada
   frame**, não fica congelada no instante da trava: a carta ausente naquele frame não tinha
   posição conhecida e ia para o FIM da lista, onde ficava mesmo depois de reaparecer no lugar
   certo. Era o que o jogador via ao encaixar a carta comprada no meio do leque — medido, **16,9%
   dos frames com a mão certa tinham a ordem errada; caiu para 1,9%**. A ordem só é atualizada
   quando a leitura viva bate em CONJUNTO com a exibida, senão o overlay remexeria as cartas a
   cada frame borrado.

   `lock_frames = 20` (~0,7 s). Foi 12, depois 30, depois 60 — todos escolhidos para proteger o
   EVENTO de compra/descarte. Com o evento fora de escopo, a varredura mostrou que a espera não
   comprava acerto nenhum: de 60 para 20 o atraso caiu de 2,57 s para 0,86 s e a contradição caiu
   de 13,5% para 7,5%. Abaixo de 20 a tela começa a tremer. Tabela completa no `config.py`.

   Até 2026-07-30 ele **travava** a primeira mão de exatamente 9 e segurava até o botão, para o
   overlay nunca oscilar numa live. Trocado a pedido do usuário: o custo era clicar a cada carta
   comprada e conviver com mão exibida velha. A estabilidade agora vem só da histerese — se a
   exibição ficar inquieta demais numa gravação, o ajuste é aumentar `lock_frames`, não voltar
   ao botão.

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

`confirm_confidence = 0.85` é letra morta duas vezes: marcaria o EVENTO como "confirmar?" no
painel, e evento saiu de escopo em 2026-08-19.

`hand_cam_index` é a webcam da mão — a única câmera do app. O índice não é fixo no Windows; se o
preview mostrar outra coisa, `scripts/check_cams.py` mostra o que cada índice está vendo.

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
reiniciar. Sintoma: o preview "Câmera da mão" do painel mostra a câmera errada; conserto: ajustar
`hand_cam_index` depois de rodar `scripts/check_cams.py`, que mostra o que cada índice está vendo.

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

### Dado NEGATIVO: ensinar o que não é carta (`extrai_negativos.py`, 2026-08-20)

O outro lado do treino, e que faltava por inteiro. O modelo lia o logo *"10COC ... LEAGUE"* da
parede da sala como `10C`/`QC` e textura de reboco como `5S 4D KS` — e desde 19/08 essas cartas
inventadas chegavam à TELA (ver a seção do fantasma de ambiente). O usuário descreveu o setup que
produz isso: câmera na sala aberta pegando o logo ao fundo e, no uso normal, virada para uma
parede branca e lisa.

Frame sem carta nenhuma é dado de treino de **rótulo vazio**, e é ainda mais barato que o do
`extrai_gravacao.py`: não precisa nem de gabarito. Toda gravação tem minutos de sala vazia.

O risco é o INVERSO do risco daquele script — incluir um frame que TEM carta ensina o modelo que
índice é fundo, que é o tiro no pé que este arquivo já documenta. Três guardas: bloco de jogo com
margem de 20 s para os dois lados (nada perto de jogo vira negativo), espaçamento entre amostras
(frames vizinhos a 30 fps são a mesma imagem) e **auditoria por folha de contato** — as imagens de
`review/` trazem em vermelho o que o modelo detectou de errado, e apagar a imagem rejeita o frame.

`training/eval_negativos.py` é o instrumento de aceite, e existe porque **o `eval_classes.py` é
cego para este defeito**: ele só olha imagens que TÊM carta, então um modelo que enxerga cartas na
parede tira 100% nele. É a segunda vez que o instrumento de aceite aprova um erro que aparece ao
vivo (a primeira foi o K♠→A♠ em 12/08). A conta aqui é trivial porque a verdade é conhecida por
construção: nestas imagens o número certo de detecções é **zero**.

**Os 12 fundos do gerador eram todos a MESMA superfície** — brilho médio 117 nos 12. O treino
sintético inteiro viu praticamente um fundo só, e cenário com quinquilharia nunca apareceu; o que
nunca apareceu não tem como ser aprendido como fundo. Entraram 7 frames de sala vazia como
`bg_sala_*.jpg` (com logo e quadro-negro), e o leque passa a ser composto POR CIMA deles — ver o
distrator e a carta na MESMA imagem é mais forte do que ver só o distrator sozinho num negativo.
A cor chapada de reserva foi de 20-110 para **20-235**, com gradiente e tom neutro: parede branca é
o setup normal, e carta branca sobre parede branca é o menor contraste que existe — o gerador só
sabia produzir fundo escuro.

`finetune_local.py` consome `datasets/negativos/` **sem repetir** (a repetição existe para o dado
real não se diluir; negativo repetido só ensina o modelo a ter medo) e avisa acima de ~10% do
treino, porque passar disso troca fantasma por carta perdida — e essa troca não aparece no mAP.

### Dado DIFÍCIL: os frames em que o modelo PERDE a carta (`extrai_dificeis.py`, 2026-08-25)

O `extrai_gravacao.py` exige contagem exata (`alinhado`), e com razão — carta não detectada desloca
todos os rótulos seguintes. O efeito colateral é que **todo frame em que o modelo perdeu uma carta
era descartado inteiro**, e são justamente esses que carregam o dado difícil. É o alvo que a
medição de 25/08 apontou: 64-89% do que a tela mostra e o leque não tem é carta que o modelo não
entregou.

**Não precisa de gabarito**, e é o que faz o script rodar nas quatro gravações que ainda têm vídeo
(as duas com gabarito estão fora: 11/08 é o conjunto de validação real e 12/08 já não tem
`mao.avi`). Quem diz que carta é aquela é o **leitor**: a vaga do `FanReader` que ficou sem
detecção tem rótulo estabelecido pela votação dos frames em que a carta FOI vista, e posição
atualizada pelo `_estimate_shift` mesmo nos frames em que ela sumiu. Não é a circularidade do
`auto_annotate.py`: lá o rótulo vinha do palpite do modelo NAQUELE frame; aqui o defeito que se
conserta é PERDA DE DETECÇÃO, e o rótulo vem dos frames vizinhos.

**A guarda que decide tudo: a caixa NÃO é interpolada.** Metade dos buracos é oclusão física
(medido aqui: 50% dos candidatos; por outro caminho, em 24/08, 69% das perdas), e rotular isso
ensinaria o modelo a enxergar índice que não está na imagem — o envenenamento que reprovou o
`extrai_fantasmas.py` duas vezes. O frame é re-detectado a **0,05** e só entra se o modelo
responder alguma coisa na posição prevista: aí o índice está visível, a caixa é real, e o que
faltou foi confiança ou classe.

De quebra, isso resolve um problema que não era óbvio: **as amostras são difíceis para o modelo de
HOJE**, não para o que gravou a sessão. Um dos descartes é "o vídeo detectou a carta" (12% dos
candidatos) — se o modelo atual acha a carta acima de 0,30 ali, o frame não é mais difícil e sai.

Rendimento e auditoria nas quatro gravações:

| gravação | buracos | candidatos | recuperados | sobrevivem à auditoria |
|---|---|---|---|---|
| 20/08 19:43 | 236 | 135 | 28 | **22** |
| 20/08 17:42 | 296 | 154 | 41 | **28** |
| 19/08 15:50 | 201 | 117 | 21 | **14** |
| 19/08 16:22 | 188 | 99 | 8 | **6** |

**A auditoria reprovou 29% (28 de 98), e todos os reprovados têm a MESMA assinatura**: a caixa
contém **pip sem glifo** — dedo por cima, carta vizinha cobrindo, ou a caixa caiu no meio da carta
(dois pips de ouros seguidos parecem índice). Duas tentativas de reduzir isso a número, ambas
**MEDIDAS E REFUTADAS** nos mesmos 31 recortes:

- **perguntar ao modelo com o recorte AMPLIADO** ("se há índice, ele o lê com folga a 4×"): em 28
  dos 31 o modelo não detectou NADA, incluindo os que a auditoria aprovou. **O modelo é preso à
  escala** — ampliar tira o índice da escala em que ele foi treinado. É um fato novo sobre o
  modelo, e vale para qualquer ideia de "recortar e reclassificar".
- **fração de PELE na metade do glifo**: não separa — os APROVADOS tinham 0,50-0,67 de pele contra
  0,26-0,55 dos reprovados.

O que virou guarda foi só o que a medição sustentou: **tinta na metade de cima da caixa**, relativa
às vizinhas do mesmo frame (o pip fica embaixo e sobrevive ao estouro de luz; o glifo, não).
Medido: 0,27, 0,33 e 0,27 contra 0,80 do próximo — vão limpo, e os três eram ilegíveis na
auditoria. Mais o **teto por carta**: com a mão parada, 9 dos 21 recortes de 15:50 eram o MESMO J♥
na mesma pose, e o `finetune_local.py` ainda repete o real até ~30% do treino.

A folha de contato precisou de três correções para a auditoria ser possível, todas descobertas
olhando: **entorno** (sem as vizinhas não se distingue "glifo coberto" de "glifo fora do recorte"),
**proporção preservada** (o índice é estreito e alto; esticar para quadrado deforma o glifo) e **a
caixa marcada dentro do recorte** (senão lê-se o glifo da vizinha e aprova-se rótulo errado).

Saída em `training/datasets/real/<gravação>-dificeis/`, que é onde o `finetune_local.py` já olha —
com a repetição do real e o `--holdout` por nome de pasta, sem mudar uma linha lá.

**Treinado em 2026-08-25**, com os 70 frames auditados (~630 rótulos, 70 deles a carta
recuperada): a perda de detecção caiu 5,69% → 4,97% e 4,20% → 3,98% nas duas gravações fora do
treino, sem regressão em classe nem em carta inventada. Ver "Retreino de 2026-08-25".

### Retreino de 2026-08-25: a carta perdida volta ~13% mais depressa

Primeiro treino com o dado difícil (`extrai_dificeis.py`): 2.988 imagens, 1.133 amostras reais
(38%), 55 negativos (1,8%), 12 épocas, 1280 px, batch 3. Holdouts escolhidos para sobrar com que
medir: **11/08** (o conjunto de validação real) e **19/08 16:22-dificeis** — como as gravações de
19-20/08 nunca entraram por outra via, 16:22 ficou **inteira** fora do treino.

**A nota do alvo é a TAXA DE PERDA DE DETECÇÃO**: das vagas já estabelecidas no leitor, quantas
ficam sem detecção no frame. Publicada pelo `extrai_dificeis.py --so-analise --dets`.

| gravação (fora do treino) | perda — antigo | perda — novo | detecções/frame |
|---|---|---|---|
| 19/08 16:22 | 5,69% | **4,97%** | 8,87 → 8,86 |
| 11/08 | 4,20% | **3,98%** | 8,84 → 8,85 |

Cai nas duas (−13% e −5% relativos) **sem detectar mais nada**: as detecções por frame ficam
iguais, então não é o modelo ficando solto e enchendo o quadro de caixa.

Sem regressão em nada que já se media:

| | antigo (`cards_backup_10.pt`) | novo |
|---|---|---|
| classe correta — holdout real 11/08 | 99,4% | **99,5%** |
| índices detectados — 11/08 | 100,0% | 100,0% |
| classe correta — `holdout-ranks` | 98,0% | **98,6%** |
| naipe na MESMA COR — `holdout-ranks` | 1,2% (16) | **0,8% (10)** |
| cartas inventadas — `negativos-holdout` | 0 | **0** |

**A nota da TELA quase não se move** — 16:22 contradição 10,3% → 9,5%, 11/08 8,7% → 8,9%, excesso e
cobertura iguais nas duas. E isso é o esperado, não decepção: a medição de 24/08 já tinha mostrado
que **a tela estava certa enquanto o modelo falhava**, porque o `StableHand` segura a carta durante
o buraco. Consertar o modelo aparece na perda de detecção, não na tela — e a tela é o que o usuário
vê.

**Instrumento que este retreino REPROVOU: a contagem de BURACOS.** Ela exige EXATAMENTE uma vaga
perdida, então melhorar as outras vagas a faz SUBIR. Nas duas gravações ela foi 190→202 e 197→167 —
direções opostas — enquanto a taxa de perda caiu nas duas. Serve para dimensionar o rendimento da
extração; não serve para dizer se o modelo melhorou. Está escrito no docstring de
`acha_candidatos`, onde quem for usá-la vai ler.

**Ressalva honesta**: os ganhos de CLASSE (+0,1 e +0,6 pontos) não são separáveis de variação entre
rodadas de treino — separá-los exigiria retreinar sem o dado difícil, e não foi feito. O que a
medição sustenta é a queda da PERDA, que é o alvo e foi medida em duas gravações independentes.

Rollback: `copy models\cards_backup_10.pt models\cards.pt`. (Este é o modelo em produção —
`cards_backup_11.pt` é cópia dele; ver "Três coisas que NÃO melhoraram o modelo".)

### O VAIVÉM DE ORDEM: o usuário viu antes de qualquer número (2026-08-26)

Jogando a partida de 26/08 ele relatou dois defeitos que nenhuma métrica pegava. O primeiro:
*"o 7 tava trocando de lugar com o 10"*. Está inteiro nos dados: das **41 mudanças do que estava na
tela, 16 foram só de ORDEM** — mesmo conjunto, cartas trocadas de lugar — e **12 delas são o mesmo
par `10S ↔ 7D`**. Um par só respondia por 29% de tudo que a tela fazia.

**Por que nada via isso.** As `trocas` da métrica comparam conjuntos ORDENADOS (`tuple(sorted(...))`)
e são cegas a troca de posição; a `ordem errada` pergunta outra coisa (se a ordem bate com o quadro
AGORA), e fica em 1,0% enquanto isso acontece. O instrumento ganhou o número que faltava —
**vaivém**: quantas vezes a tela trocou duas cartas de lugar sem o conjunto mudar.

**A causa, medida.** Num leque em ARCO duas cartas podem ter praticamente o mesmo x — uma acima da
outra —, e a ordem sai do x das vagas. Medido nas 16 trocas daquela partida: **14 aconteceram com
as duas vagas a 0-2 px uma da outra**; as outras duas, a 94 e 108 px, eram reordenação de verdade
(o jogador mexendo no leque). Cartas VIZINHAS ficam a 44-111 px (p05 = 69). Ou seja: são duas
populações separadas por duas ordens de grandeza, e a ordenação por x estava decidindo o empate por
arredondamento, a cada frame.

**"Esperar mais" NÃO é o conserto, e o usuário propôs isso** (*"tem que esperar um pouco mais para
ler as mudanças"*). Varrido na própria partida, `lock_frames` de 20 a 48: o vaivém não se move
(25 → 22 trocas) e todo o resto piora — atraso 0,73 → 1,52 s, excesso 6,0% → 13,1%. O motivo é
estrutural: **a ordem não passa pelo `lock_frames`**, ela acompanha a leitura viva a cada frame de
propósito, e é isso que faz a carta comprada aparecer no lugar certo (derrubou a ordem errada de
16,9% para 1,9% em 19/08). O que ele viu era real; o botão é que era outro.

**O conserto é histerese de ORDEM** (`FanReader._ordena`, `fan_ordem_margem = 0,05`): partindo da
ordem já exibida, duas cartas só trocam de lugar se uma passar a outra por mais que a margem. A
margem é adimensional, em **larguras de caixa**, pelo mesmo motivo do `_so_o_leque` — em px, 15
levava a ordem errada de 1,6% para 10,0% na partida em que o leque está mais longe da câmera, e não
mexia na de perto.

| gravação | vaivém antes | depois |
|---|---|---|
| 11/08 | 50 | **26** |
| 12/08 | 50 | **18** |
| 19/08 15:50 | 12 | 10 |
| 19/08 16:22 | 28 | **6** |
| 20/08 17:42 | 30 | 26 |
| 20/08 19:43 | 20 | **8** |
| 25/08 | 2 | 2 |
| **26/08 (a partida do relato)** | **16** | **8** |

**O custo é PEQUENO, e descobri-lo exigiu consertar o instrumento — mas não é zero.** Com a
histerese, a `ordem errada` crua SOBE (2,1% → 5,0% em 11/08). Só que ela cobra como erro o EMPATE:
quando duas cartas estão no mesmo x, a ordem "física" de referência é o mesmo sorteio que se está
tentando eliminar. A métrica passou a publicar também a **ordem errada com folga**, que só conta
inversão entre cartas de fato separadas (mais de 0,05 largura de caixa) — e nas seis gravações
antigas essa não se move:

| | crua, sem histerese | crua, com | **com folga, sem** | **com folga, com** |
|---|---|---|---|---|
| 11/08 | 2,1% | 5,0% | **1,6%** | **1,6%** |
| 12/08 | 1,6% | 2,0% | **1,0%** | **1,0%** |
| 26/08 | 1,0% | 2,0% | **0,8%** | **0,9%** |

Contradição, excesso, atraso e cobertura ficam idênticos nas oito gravações: a histerese só toca a
ordem, que é o que ela deve fazer.

**Ressalva medida em 2026-08-26 14:12, e ela qualifica o "custo zero" acima.** Numa partida em que o
usuário NÃO produziu o empate (vaivém 2 com e sem histerese), o teste controlado — a mesma gravação
com o conserto ligado e desligado — mostrou a ordem errada COM FOLGA subindo de **0,0% para 0,5%**
(17 frames). Não é empate cobrado à toa: é a histerese segurando a ordem antiga por um instante
depois de uma reordenação de verdade. Ou seja, a histerese é seguro contra um defeito que só
acontece em certas montagens de leque, e cobra um prêmio pequeno nas outras. O prêmio é da ordem de
0,1-0,5 ponto; o defeito que ela evita valia 12 das 41 mudanças da tela.

**A lição de método**: o defeito foi visto por quem usa, não pelo número — e a primeira reação
(mexer no `lock_frames`) era a errada. Quando o usuário descreve um sintoma, o trabalho é achar
QUAL mecanismo o produz, não aplicar o botão que soa parecido.

### De que é feita a CONTRADIÇÃO que sobra, e o retreino de classe que foi REPROVADO (2026-08-26)

Com a tela já consertada (vaivém e fantasma), a contradição ficou em 9,2-9,5% ao vivo. Medido nas
duas partidas de 26/08, frame a frame, perguntando se a carta cobrada aparece na tela a menos de
1,5 s:

- **85% é TRANSIÇÃO** — a tela a caminho. É o preço do `lock_frames`, e subir esse botão só piora
  (varrido: 20→48 leva o atraso de 0,73 s a 1,52 s e o excesso de 6,0% a 13,1%).
- **15% é a tela sem mostrar a carta.** E o topo desse resíduo é um erro de MODELO: na partida das
  14:12, o `A♣` foi lido como `A♠` com **0,85-0,91 em 76 frames**, com o índice inteiro e bem
  iluminado. Os recortes do vídeo não deixam dúvida: a carta é um A♣, e **a votação temporal do
  leitor corrigiu**. A tela estava certa; a métrica cobrou dela um erro do modelo — o mesmo padrão
  já registrado no excesso com o leitor congelado e na ordem com empate.

**A tentativa de consertar isso com dado, e por que ela foi reprovada.** `training/extrai_classe.py`
extrai justamente esses frames: o modelo lê X com confiança alta onde a vaga (já estabelecida, viva
e na tela) diz Y, restrito à família *troca de naipe na MESMA COR*. O rótulo do frame INTEIRO sai
das vagas, senão os outros índices virariam fundo.

O filtro por família é o que torna isso possível, e não é preciosismo: sem ele saem **8.448 pares**,
dominados por coisas impossíveis (`2S->AH`, `KC->5D`) que são o leque sendo REARRANJADO, com a vaga
herdando a posição de outra carta. **Três filtros geométricos foram tentados e nenhum separou** — a
vaga certa e a velha ficam a poucos px uma da outra. Com a família, sobram 118 candidatos; a
auditoria a olho aprova a grande maioria (`J♣` lido J♠, `A♣` lido A♠, `2♥` lido 2♦, `9♥` lido 9♦), e
um filtro automático que rejeita o frame com qualquer correção FORA da família deixa **53 frames**.

Retreinado com eles (3.043 imagens, 39% real), holdouts de sempre. **O resultado é uma troca ruim:**

| | `cards_backup_11` (publicado) | com o dado de classe |
|---|---|---|
| perda de detecção — 19/08 16:22 | **4,97%** | 6,46% |
| perda de detecção — 11/08 | **3,97%** | 4,25% |
| naipe na mesma cor — 11/08 + `teste-9S` | 7 erros | **2 erros** |
| classe correta — `holdout-ranks` | 98,6% | 98,5% |

Ganhou 5 erros de naipe em números de UM DÍGITO e perdeu **0,9 ponto de perda de detecção na
média**, com 1,5 ponto numa das gravações — muito acima do ruído de rodada (~0,3) medido no mesmo
dia. **Rollback para o `cards_backup_11`.**

A hipótese de por que piorou, e ela NÃO foi medida: 53 frames de erro de classe são 53 frames em que
o modelo é empurrado a mudar de opinião sobre um índice que ele lia com 0,85-0,91 — e nada garante
que o empurrão fique restrito ao naipe. O script fica no repositório porque a extração é correta e
a auditoria passou; o que não se sustentou foi o proveito.

### O `9♠→9♣` NÃO era confusão de naipe — era a captura (2026-08-26)

O último erro de classe aberto do projeto, e o único que não respondia a retreino nenhum
(`9S→9C`: 9 erros antes do retreino de 20/08, 9 depois). O CLAUDE.md registrava a medição como
**CONFUNDIDA**, porque nos dois leques capturados o 9♠ tinha paus dos dois lados. Resolvido com
~15 min do usuário e quatro arranjos controlados, todos na mesma sessão, mesma luz, mesmo baralho.

**As três hipóteses, e as três caíram:**

| conjunto | 9♣ no leque | vizinho | aperto (vão/largura) | **erro no 9♠** |
|---|---|---|---|---|
| holdout antigo | sim | paus | 0,91 | **11,3%** (7/62) |
| hoje **C** | não | **paus** | **0,87** | **0,0%** (0/52) |
| hoje **D** | **sim** | **paus** | **0,91** | **0,0%** (0/53) |
| hoje A | não | copas | 0,53 | 2,0% (1/51) |
| hoje B | não | copas | 0,48 | 0,0% (0/53) |

O arranjo C reproduziu a condição antiga (paus colado, mesmo aperto) e o D acrescentou o 9♣ no
mesmo leque — a hipótese da gêmea. **Zero erro nos dois.** Em 209 frames de hoje o 9♠ foi lido
errado UMA vez (0,5%), e essa uma tinha um COPAS ao lado, não um paus.

**O que está medido, e o que NÃO está.** A largura da caixa do índice do 9♠, dividida pela mediana
das vizinhas do mesmo frame, é 0,73 (p10 0,64) no holdout contra 1,12-1,33 hoje — o índice dele
naquela captura estava mesmo mais coberto. **Mas isso sozinho NÃO explica o erro**, e a tentativa
de transformar essa observação em guarda foi refutada três vezes (ver abaixo): hoje o `Q♥` saiu a
0,71 e o `3♥` a 0,68, tão estreitos quanto aquele 9♠, em capturas com ~0% de erro.

O que fica medido dentro do próprio conjunto antigo é que os erros são o subconjunto em que a caixa
**incha**:

| 9♠ no holdout antigo | largura relativa |
|---|---|
| lido certo (55 frames) | 0,73 |
| lido **errado** (7 frames) | **0,98** (p90 1,08) |

Ou seja: naquele leque a caixa ora pega só o 9♠ (estreita, lê certo), ora **invade a vizinha**
(larga) — e aí sai `9C` ou `2C`, que são exatamente os dois rótulos contidos no recorte. Confirmado
a olho na folha de contato: nos frames com erro o "9" aparece mutilado, com um pip de paus dentro
do mesmo recorte.

**Fica em aberto o que torna AQUELA captura propensa ao inchaço**, já que outras com índices igualmente
estreitos não erram. O que está provado é a localização do defeito (aquela captura), não o mecanismo
que o gera.

**Três guardas de captura propostas e REFUTADAS na mesma sessão** (não reimplemente):

| guarda candidata | por que caiu |
|---|---|
| índice estreito em relação às vizinhas | capturas boas de hoje descem a 0,68-0,71, e o `datasets/local` inteiro a 0,49 |
| caixas de índice se ENCOSTANDO | **100% dos frames de TODOS os conjuntos** têm sobreposição; as capturas boas se sobrepõem MAIS (-0,48 e -0,85 contra -0,39 da ruim) |
| carta persistentemente estreita na captura | hoje A tem `QH=0,71` e B tem `3H=0,68`, com ~0% de erro |

A terceira é a mais instrutiva: o critério visual que este arquivo recomenda — *"as caixas verdes não
podem se encostar"* — **não é verificável como número**, porque num leque real elas sempre se
encostam. Ele continua útil como sinal grosseiro para o olho; como gate automático, não existe.

**Três consequências:**

1. **O modelo não tem defeito no 9♠.** Em captura bem formada ele acerta 99,5%, inclusive com paus
   colado dos dois lados. O alvo "9♠→9♣" está encerrado, e não custou retreino nenhum.
2. **O `holdout-ranks` mede errado nessa carta.** Ele é o conjunto de validação real do projeto, e
   as 62 amostras do 9♠ dele estão com o índice 27% coberto — a "troca de naipe na mesma cor" que
   ele publica está inflada por um defeito de captura, não de modelo. Ao julgar um retreino por
   ele, desconte essa linha.
3. **Não há guarda automática de captura para isto** — três candidatas foram medidas e reprovadas
   (tabela acima). O `ver_ordem.py` fica como está: o que ele já faz (mostrar a ordem lida, os vãos
   e a imagem para o olho) é o que se sabe verificar.

Os 209 frames dos quatro arranjos ficaram em `training/datasets/teste-9S/{A,B,C,D}` — dado real,
rotulado pela ORDEM, e um conjunto de validação do 9♠ muito melhor que o antigo.

### A validação dos dois consertos, ao vivo e controlada (2026-08-26 14:12)

Partida curta gravada logo depois dos dois consertos, 3,6 min a 41,8 fps, com **59,6% dos frames
tendo carta no quadro**. É a melhor medição ao vivo do projeto:

| | 26/08 13:24 (antes dos consertos) | **26/08 14:12** |
|---|---|---|
| atraso até a tela | 0,73 s | **0,57 s** |
| contradição | 9,5% | **9,2%** |
| excesso | 6,0% | **1,6%** |
| ordem errada | 2,0% | **0,5%** |
| vaivém de ordem | 16 | **2** |
| perda de detecção | 3,78% | **2,51%** |
| cobertura | 97,4% | 97,3% |

Mas partidas diferentes não provam conserto. O que prova é o **teste controlado — a MESMA gravação,
com os consertos ligados e desligados**:

| | consertos OFF | consertos ON |
|---|---|---|
| excesso | 5,0% | **1,6%** |
| excesso **com o leitor vivo** | 3,4% | **0,0%** |
| vaivém | 2 | 2 |
| ordem errada (cartas separadas) | 0,0% | 0,5% |

**O `fan_exibe_misses` ganhou o lugar dele**: o excesso com o leitor VIVO foi a zero — tudo o que
sobra acontece com o leitor congelado, que é o comportamento pedido. A mão anterior não fica mais
no ar.

**A histerese de ordem não foi exercitada nesta partida** (vaivém 2 nos dois casos: o usuário não
montou o leque com duas cartas quase uma sobre a outra), e aí só apareceu o custo dela — ver a
ressalva na seção do vaivém. É seguro contra um defeito que depende da montagem do leque.

O caso isolado de **6,07 s** de atraso que ficou em aberto aqui foi investigado em 2026-08-28 e
**não era atraso** — era defeito do instrumento. Ver a seção seguinte.

### O atraso máximo era do INSTRUMENTO, não do pipeline (2026-08-28)

O caso de 6,07 s da partida acima, reconstruído frame a frame. A tela adotou
`3H 5D 6C 7H 8C AC KH` (sem o `9H`) em t=116,8 s:

| t | o que a leitura VIVA fez |
|---|---|
| 110,7 s | pisca para o conjunto alvo por **UM frame** — e é esse frame que arma o cronômetro |
| 110,9-116,0 s | **202 frames (5,1 s)** com o `9H` de volta: o conjunto alvo não existe |
| 116,1 s | o `9H` sai de verdade, e fica |
| 116,8 s | a tela adota — **0,7 s depois**, em linha com a mediana de 0,57 s |

Não é um caso raro nem uma partida azarada: o mesmo mecanismo produziu **25,38 s** em 20/08 17:42 e
**7,73 s** em 12/08. Nas nove gravações, **14 das 416 medidas** de atraso passavam de 2 s, e o p99
saía em 5,22 s.

**A origem é o conserto de 2026-08-19**, que trocou um defeito pelo outro. Ele mudou a âncora para
"a PRIMEIRA vez que a leitura viva mostrou aquele conjunto" e matou zeros falsos; o preço, não
percebido na época, é que um piscar de um frame passa a ancorar o cronômetro arbitrariamente longe.
**As duas âncoras óbvias erram, cada uma para um lado** — e é por isso que o conserto não é voltar
atrás:

- ancorar na PRIMEIRA aparição → o piscar isolado vira 6 ou 25 segundos;
- ancorar na corrida CONTÍGUA → quando a leitura viva oscila na transição e a tela adota no frame de
  uma piscada, a corrida final tem 1 frame e o atraso sai **0,00 s**. Nas nove gravações isso
  aconteceria 24 vezes.

O que separa as duas populações é que elas são separadas na natureza: a oscilação de transição é
**densa** (vai e volta a cada poucos frames) e o piscar espúrio é **isolado**, com centenas de
frames de outro conjunto em volta. A âncora (`app/leitura.py:_ancora`) anda de trás para frente a
partir do frame em que a tela adotou, tolerando até `TOLERANCIA_ANCORA` frames SEGUIDOS fora do
conjunto. Varrido nas nove gravações (416 medidas), com platô como no `fan_borda`:

| tol | n | mediana | p99 | max | zeros | > 2 s | medidas perdidas |
|---|---|---|---|---|---|---|---|
| 0 (contígua) | 389 | 0,59 | 1,17 | 1,24 | **2** | 0 | **27** |
| 8 | 415 | 0,60 | 1,17 | 1,58 | 0 | 0 | 1 |
| **10** | 416 | 0,61 | 1,17 | 1,58 | **0** | **0** | **0** |
| **16** | 416 | 0,61 | 1,18 | 1,58 | **0** | **0** | **0** |
| **22** | 416 | 0,61 | 1,18 | 1,58 | **0** | **0** | **0** |
| 25 | 416 | 0,61 | 1,58 | 2,96 | 0 | 3 | 0 |
| antigo (∞) | 416 | 0,62 | **5,22** | **25,38** | 0 | **14** | 0 |

De 10 a 22 nada se move, e o `n` é o mesmo do código antigo — ou seja, o conserto **não descarta
medida nenhuma**, só as ancora certo. **16 é o meio do platô.**

**A constante é FIXA de propósito, e não `config.lock_frames`** (que cairia dentro do platô): o
`--varre lock_frames=...` existe justamente para medir o efeito daquele parâmetro no atraso, e uma
âncora que andasse junto com ele mediria o instrumento em vez do pipeline.

**O que muda na nota das nove gravações: só o máximo.** Mediana e p90 não se movem (0,57 s e 0,73 s
continuam 0,57 s e 0,73 s em 26/08 14:12), e contradição, excesso, ordem, vaivém e cobertura ficam
**idênticos** em todas — a mudança toca só o atraso, que é o que ela deve fazer.

| gravação | max antes | max agora |
|---|---|---|
| 20/08 17:42 | **25,38 s** | **1,27 s** |
| 12/08 | 7,73 s | 0,83 s |
| 26/08 14:12 | 6,07 s | 0,74 s |
| 19/08 16:22 | 5,63 s | 1,24 s |
| 19/08 15:50 | 2,96 s | 1,58 s |

Guardado por três testes, **conferidos por mutação nas duas direções**: com a tolerância no valor
antigo (∞) cai o `test_piscar_isolado_da_leitura_viva_nao_arma_o_cronometro_do_atraso`, e com ela em
0 cai o `test_oscilacao_de_transicao_NAO_vira_atraso_zero`. Sem o segundo, consertar o primeiro
reintroduz em silêncio o defeito de 19/08.

**Armadilha de método que quase passou por boa, e vale mais que o conserto:** a primeira versão do
terceiro teste dimensionava o histórico sintético com a própria constante
(`TOLERANCIA_ANCORA + 40` frames). Sob a mutação para o valor antigo isso alocava **um bilhão de
frames** e a suíte TRAVAVA em vez de falhar. Um teste que trava sob mutação não prova nada — e a
trava era fácil de ler como "o mutante passou". O vão do teste agora é fixo, com a tolerância
conferida contra ele.

**A lição, e é a terceira vez que este arquivo a registra:** o número residual acusava o pipeline e
o culpado era o instrumento. Já tinha acontecido com a contradição (que cobrava a carta segurada à
parte, comportamento pedido), com o excesso (que cobrava o leitor congelado) e com a ordem (que
cobrava o empate de x). **Antes de investigar um resíduo da métrica, confira se a métrica está
medindo o que diz medir.**

### As CARTAS FANTASMAS ao encaixar: a mão anterior ainda no ar (2026-08-26)

O segundo defeito que o usuário relatou na mesma partida: *"quando eu ia colocar a carta no leque,
ele já lia e criava várias cartas fantasmas e bugava"*. Achado na gravação, e o mecanismo é exato.

**Primeiro, o que NÃO era.** A tela ficou 11,1 s exibindo 11 cartas, e o caso maior (10,3 s
mostrando `10C` e `9C` juntos) **não era fantasma**: o `10C` foi detectado no quadro em 70% daqueles
frames e passou pelo `_so_o_leque`. A tela estava certa. Perseguir isso teria sido conserto de
defeito inexistente.

**O fantasma de verdade é curto e é outro.** No instante em que a tela mostrou **12 cartas** (0,75 s),
as três a mais — `10H`, `8D`, `JS` — foram detectadas em **ZERO frames** ali, com 17 a 47 *misses*.
Eram vagas da mão ANTERIOR, ainda vivas porque `fan_expire = 48`. Numa troca de mão, as 9 velhas
saem e as 9 novas entram, e por até 1,3 s a tela pode mostrar as duas.

**O conserto separa duas coisas que estavam presas uma na outra**: `fan_expire` decide quando a vaga
MORRE — e precisa continuar generoso, senão uma oclusão curta apaga a carta e o leque é relido do
zero (é a regra de 2026-08-04) — mas até morrer a vaga era EXIBIDA. `fan_exibe_misses = 24` (metade
do expire) tira da tela a vaga que sumiu há muito **sem matá-la**: os votos ficam, e a carta volta
no primeiro frame em que reaparecer. Segurar a exibição é seguro porque quem protege contra piscada
é o `StableHand`.

| gravação | excesso antes | depois | contradição antes | depois | cobertura |
|---|---|---|---|---|---|
| 11/08 | 7,6% | **5,8%** | 10,0% | 10,1% | igual |
| 12/08 | 6,5% | **3,1%** | 14,5% | 16,3% | igual |
| 19/08 15:50 | 8,4% | **6,9%** | 10,9% | 12,3% | igual |
| 19/08 16:22 | 3,9% | **1,4%** | 8,0% | 8,2% | igual |
| 20/08 17:42 | 5,7% | **3,0%** | 13,9% | 14,6% | igual |
| 20/08 19:43 | 7,8% | **4,7%** | 12,8% | 13,8% | igual |
| 25/08 | 6,4% | **2,0%** | 7,9% | 8,6% | igual |
| **26/08 (a do relato)** | 6,0% | **2,2%** | 9,5% | 9,5% | igual |

Excesso cai em TODAS (6,5% → 3,6% na média, −45%) e a cobertura é idêntica em todas. O custo é a
contradição subir ~0,8 ponto na média: a carta que pisca por mais de 24 frames demora ~0,5 s a mais
para voltar, porque precisa reconquistar o `lock_frames`. 24 é o fundo da varredura — 32 acha menos
fantasma, 16 já começa a piscar a tela (trocas 25 → 29).

**As duas hipóteses do usuário sobre o CONSERTO foram testadas e recusadas** (a observação estava
certa, o botão é que era outro): `lock_frames` de 20 a 48 não mexe no vaivém e piora tudo;
`fan_min_appear` de 10 a 25 troca 0,5 ponto de excesso por 2,4 de contradição.

Guardado por `test_vaga_que_sumiu_ha_muito_sai_da_TELA_sem_morrer` — que verifica os dois lados: a
carta sai da tela E volta no primeiro frame em que reaparece.

### O ÍNDICE DEITADO é o que o modelo perde — e a partida de 28/08 é a única que tem a condição

Partida de teste gravada em 2026-08-28 (7,8 min, 45,7% dos frames com carta), a pedido do usuário,
que ainda não tem o baralho oficial da live. Ela é **a pior de todas as notas recentes**, e vale
como caso de estudo porque a causa foi rastreada até o fim e quase todas as suspeitas caíram.

| | 26/08 14:12 | **28/08** |
|---|---|---|
| atraso até a tela | 0,57 s | 0,80 s |
| contradição | 9,2% | 14,5% |
| excesso (leitor vivo) | 1,6% (0,0%) | 4,4% (1,6%) |
| ordem errada | 0,5% | 1,8% |
| cobertura | 97,3% | 95,3% |
| **perda de detecção** | **2,51%** | **6,06%** |

**O sintoma, medido do jeito que se vê na tela:** a tela ficou sem alguma carta do leque **22,6% do
tempo com leque**, contra 9,5% em 26/08 e 10,2% em 25/08. Não é que cada falha dure mais — a
mediana é 0,03 s nas três — é que elas acontecem **2× mais**: 498 trechos contra 186. Os piores
(2,4 s) caem no instante em que o jogador **encaixa** uma carta.

**A cadeia é: o modelo perde a detecção → o leque pisca → a tela fica para trás.** E a perda NÃO é
oclusão: re-detectando do vídeo, só **12-17%** dos casos são carta fisicamente tapada, contra ~50%
medidos em 25/08 e 69% em 24/08. Na maioria a carta está visível e o modelo responde — a
**0,05-0,29**, logo abaixo do limiar de 0,30.

**A causa que sobrevive à medição: o índice chega GIRADO.** A proporção largura/altura da caixa é o
proxy de rotação que este arquivo já usa (índice em pé ~0,6; deitado ~1,2). Medido DENTRO de cada
gravação, que é o controle que importa — mesmo baralho, mesma luz, mesma pessoa:

| proporção da caixa | 26/08 — perda | **28/08 — perda** |
|---|---|---|
| 0,6-0,7 (em pé) | 0,96% | 1,82% |
| 0,9-1,0 | 0,97% | 3,79% |
| ≥1,2 (deitado) | 2,42% | **6,49%** |
| **fração do leque nessa faixa** | **9,2%** | **22,9%** |

Duas coisas se somam: **2,5× mais índices deitados** e **cada um falha 2-3× mais**. O usuário abriu
o leque mais achatado nesta partida.

**Sete hipóteses medidas e DESCARTADAS na mesma sessão** (nenhuma delas explica, não repetir):

| hipótese | o que a medição deu |
|---|---|
| enquadramento | o índice está 33% MAIOR (120×146 px contra 90×116) |
| confiança degradada | p50 = 0,95 nas duas |
| tremor / casamento de vaga | 0,6% dos deslocamentos acima do raio de 50 px |
| leque apertado | controle dentro do frame: vão 0,49 na perdida contra 0,54 na base |
| estouro de luz | fundo mais escuro (78 contra 112) e carta mais clara (160 contra 128), mas o **contraste dentro do índice SUBIU** (58,6 contra 53) |
| escala (leque perto demais) | na MESMA faixa de tamanho de índice, 28/08 perde 2-4× mais |
| leque enfileirado, sem arco | arco 1,54 alturas de índice, dentro da faixa normal (1,36-1,89) |

**Fica em aberto, e é honesto dizer:** mesmo faixa a faixa de rotação, 28/08 perde ~2× mais que
26/08. A rotação explica parte, não tudo.

**O dado difícil desta gravação NÃO serve para treinar, e a auditoria é que salvou.** Das 25
amostras extraídas pelo `extrai_dificeis.py`, **só 8 sobreviveram** — e duas das reprovadas
(`10D` rotulado sobre um índice que é claramente o `2♦`) teriam ensinado rótulo errado. O resto são
caixas caídas sobre **pips no meio da carta**, sem glifo. E as 8 boas são o mesmo `J♥`, o mesmo
`2♦` e um `3♦` quase na mesma pose — 3 situações distintas, não um conjunto. Abaixo do ruído de
rodada (~0,3 ponto). **Não foi treinado.**

**O que esta gravação vale, e é muito: ela é o conjunto de teste que faltava.** A tentativa de
25/08 de abrir o leque do gerador (`ABERTURA` 150→180, o `cards_backup_12`) foi reprovada por não
mexer na perda — mas foi medida em gravações onde só ~9% do leque chegava deitado, ou seja, num
conjunto que quase não tinha a condição que a mudança atacava. Guarde esta gravação para testar
qualquer conserto de ROTAÇÃO.

**O teste que essa gravação permitiu, e o veredito (2026-08-28).** Com os dois modelos lendo o
MESMO vídeo (`replay.py --redetectar`, que só vale modelo contra modelo), a perda de detecção:

| gravação | leque deitado (≥1,0) | `cards_backup_11` (produção) | `cards_backup_12` (abertura 180) |
|---|---|---|---|
| 28/08 | **33,7%** | 6,51% | **5,98%** |
| 11/08 | 30,0% | 3,98% | **3,68%** |
| 19/08 16:22 | 23,9% | **4,97%** | 6,00% |
| 26/08 14:12 | 20,2% | **2,47%** | 2,52% (empate) |

O `backup_12` ganha nas DUAS gravações com mais índice deitado e não ganha nas duas com menos — a
previsão feita antes de medir 26/08 se confirmou (empate ali). **Mas a história não é limpa**: em
19/08 16:22, com 23,9% de rotação, ele perde por 1,03 ponto, o que não cabe numa curva monotônica.
(Ressalva: os números de 11/08 e 19/08 vêm da sessão de 25/08, não foram re-medidos hoje.)

**E o que decide é a TELA, onde ele não ganha.** Na própria 28/08, com os dois modelos:
contradição **11,9% → 13,1%**, ordem 1,8% → 2,1%, excesso igual, cobertura 94,9% → 95,4%, atraso
0,79 → 0,75 s. Ou seja: o `backup_12` acha mais carta e a tela fica igual ou pior — que é
exatamente o que este arquivo já registra ("consertar o modelo aparece na perda de detecção, não na
tela — e a tela é o que o usuário vê").

**O modelo em produção continua o `cards_backup_11`.** O que muda é o conhecimento: a reprovação de
25/08 valia, mas agora se sabe que o efeito da abertura do gerador é **condicional à rotação**, e
que existe uma gravação com a condição para testar.

**Duas notas operacionais desta sessão:**

- **Gravar corta a taxa de quadros pela metade** — 50-57 fps sem gravar, 29-36 gravando (medido no
  perfil por bloco de 30 s: começa em 41-47 e assenta). Como todo parâmetro é contado em QUADROS, a
  tela passa a trocar em 0,65 s em vez de 0,35 s, o que infla atraso e contradição. Ao comparar uma
  partida gravada com uma não gravada, desconte isto.
- **Matar o app sem encerrá-lo quebra o índice do AVI.** Os dados continuam todos no arquivo (3,66
  GB ÷ 15.843 frames = 231 KB/frame, que fecha), mas `CAP_PROP_FRAME_COUNT` passa a mentir (disse
  5.143) e **`CAP_PROP_POS_FRAMES` devolve o quadro errado** — as caixas anotadas saem deslocadas e
  a leitura visual engana. Conserto: ler o vídeo SEQUENCIALMENTE. Sintoma que denuncia: contagem de
  frames do AVI muito menor que a do `sessao.jsonl`.

### A perda é do índice DEITADO, e os instrumentos de aceite eram cegos a isso (2026-09-03)

Sessão inteira em disco, sem webcam. O alvo era a perda de detecção de 28/08. O que mudou não foi
o modelo — foi saber **onde** ele perde, e descobrir que nenhum instrumento do projeto enxergava
aquilo.

#### O gradiente, que é o achado durável

`training/eval_rotacao.py` reparte a taxa de perda por proporção largura/altura da caixa (o proxy
de rotação que este arquivo já usa: em pé ~0,6, deitado ≥1,0). Nas duas gravações com vídeo
recente, com **três** modelos diferentes lendo o mesmo vídeo:

| faixa | 28/08 (3 modelos) | 26/08 14:12 (3 modelos) | fatia do leque |
|---|---|---|---|
| em pé (<0,7) | 3,4-4,4% | 1,4-1,6% | ~40% |
| inclinado (0,7-0,9) | 2,4-5,0% | 1,3-1,7% | 24-30% |
| quase deitado (0,9-1,0) | 3,5-5,3% | 2,6-3,6% | 4-9% |
| deitado (1,0-1,2) | 5,3-7,4% | 2,3-2,8% | 12% |
| **muito deitado (≥1,2)** | **13,5-14,2%** | **11,1-11,8%** | **8-19%** |

O gradiente é de 3× a 8× e **não se move com o modelo** — os três modelos concordam faixa a faixa.
É a caracterização que faltava: não é "a partida de 28/08 foi ruim", é que 28/08 tinha 18,6% do
leque na faixa que perde 14%, contra 8,1% em 26/08.

Confirmado por um caminho independente, nas **dez** gravações em disco: a caixa da carta que some é
sistematicamente mais deitada que a base (28/08: 65,2% deitada contra 30,3%; 11/08: 54,1% contra
29,8%). A direção **nunca se inverte**, embora em três gravações ela seja plana.

#### Os três instrumentos de aceite são cegos a este defeito

É a terceira vez que isto acontece no projeto (as outras: o K♠→A♠ aprovado pelo sintético em 12/08,
e a carta inventada, que só o `eval_negativos.py` vê). Aqui são três de uma vez:

- **`eval_classes.py` num `datasets/real/<partida>` dá 100,0% de detecção POR CONSTRUÇÃO.** O
  `extrai_gravacao.py` só guarda frame em que `alinhado()` passa, ou seja **em que todas as cartas
  foram detectadas** — o conjunto de validação real é purgado exatamente da falha que deveria
  medir. Este arquivo publica "índices detectados: 100,0%" desde 20/08 como se fosse um resultado.
  Medido de novo hoje no `cards_backup_11`: 100,0% de detecção E 100,0% de classe em 1.082 índices,
  incluindo os 36,4% deitados. Não é um modelo perfeito, é um conjunto que não pode reprovar.
- **`holdout-ranks` tem 0,7% de índice deitado**, contra 30,2% dos rótulos das partidas reais. Ele
  não contém a condição. (Distribuição pixel-equivalente dos rótulos: `real/*` p50 0,78 e 30,2%
  deitado — igual ao leque ao vivo; `synthetic` 0,64 e 18,4%; `local` 0,63 e 15,1%.)
- **A taxa global do `extrai_dificeis --so-analise` mistura as faixas**, e o alvo está em ~⅕ da
  amostra.

`eval_classes.py` passou a publicar acerto **por faixa de rotação** (detecção e classe), e avisa
quando o conjunto tem menos de 5% de índice deitado — isto é, quando ele não pode ver o alvo.

**ARMADILHA DE UNIDADE, e eu caí nela primeiro:** o rótulo YOLO guarda largura e altura
NORMALIZADAS pelo quadro, então a razão larg/alt de um rótulo já vem multiplicada por (H/W) = 9/16.
A razão medida na caixa em px (`app/detector`) não é a mesma grandeza. Comparar as duas direto
exagera a diferença em 1,78× — foi assim que "o treino quase não tem índice deitado" (2,2%) virou,
depois da conversão, "o treino tem 18,4%, e quem não tem é a validação".

#### A leitura da abertura do gerador estava errada

O `cards_backup_12` (gerador com `ABERTURA` 180) ganha da produção no global de 28/08 (5,98% contra
6,51%) e isso vinha sendo lido como "a abertura ajuda onde há rotação". A repartição diz o
contrário: ele melhora **em pé** (4,37 → 3,78) e **inclinado** (4,95 → 2,51) e **PIORA as duas
faixas deitadas** (5,95 → 6,65 e 14,24 → 14,99). O ganho nunca veio da rotação. A conclusão de
25/08 ("o efeito da abertura é condicional à rotação") **cai**; o `backup_12` continua não
publicado, agora pelo motivo certo.

#### Três hipóteses medidas e REPROVADAS (não repetir)

**1. Baixar o `min_confidence`.** A medição de 28/08 dizia que nas perdas o modelo responde a
0,05-0,29, logo abaixo do limiar — o que sugeria que baixar o limiar recuperaria a carta. Nunca
tinha sido testável, porque as gravações já vêm filtradas em 0,30; foi preciso re-detectar o vídeo
a 0,05. Varrido de 0,05 a 0,30 na mesma gravação:

| conf | perda | contradição | excesso | ordem | cobertura |
|---|---|---|---|---|---|
| 0,05 | 8,16% | 11,4% | 7,1% | 0,4% | 92,9% |
| 0,20 | 7,06% | 11,2% | 6,4% | 1,7% | 95,4% |
| **0,30 (hoje)** | **6,51%** | 11,9% | 5,2% | 1,8% | 94,9% |

Nenhum limiar bate 0,30, e a perda até **sobe** ao baixar — detecção fraca cria vaga espúria, que
depois falta. Corolário de método: **a taxa de perda não é comparável entre limiares**, só entre
modelos no mesmo limiar. É o mesmo defeito já registrado na contagem de buracos.

**2. Desligar o espelhamento (`fliplr`).** O `finetune_local.py` nunca definiu `fliplr`, então valia
o padrão do Ultralytics — **`fliplr=0.5`, metade das imagens de treino de todos os modelos já
publicados entrou espelhada**. O argumento contra era forte: o glifo do valor é QUIRAL (um "5"
espelhado não é um 5), enquanto os pips dos quatro naipes são simétricos, e nenhuma carta real
aparece espelhada — 50% do treino vem de uma distribuição que não existe na inferência.
A/B com o MESMO dado e os MESMOS pesos de partida (`--fliplr`, `--nome` e `--nao-publicar` foram
acrescentados ao script para isso):

| | 28/08 | 26/08 14:12 |
|---|---|---|
| produção (`cards_backup_11`) | 6,51% | **2,47%** |
| A — `fliplr=0.5` (controle) | **5,45%** | 2,62% |
| B — `fliplr=0.0` | 6,03% | 2,66% |

B perde para o controle nas duas. **Reprovado** — provavelmente o espelhamento age como
regularizador com só 1.133 amostras reais, e o custo teórico não se materializa. O
`fliplr` fica no padrão, agora explícito e comentado no script.

**3. Publicar o braço A.** Ele ganha 1,06 ponto em 28/08 — e perde 0,15 em 26/08. Direções opostas,
que é a assinatura de ruído. Pela regra do próprio repositório ("o único que melhorou nas DUAS
gravações"), não substitui nada. **O modelo em produção continua o `cards_backup_11`.**

#### A perda NÃO é de detecção: é de CLASSE, e o alvo estava mal nomeado (2026-09-14)

Investigação em disco, sem GPU de treino. A pergunta era por que acrescentar índice deitado ao
treino (o `cards_backup_12`) PIOROU as duas faixas deitadas — mais amostra da condição deixando a
condição pior é assinatura de rótulo errado, não de dado insuficiente.

**Hipótese principal REFUTADA: a caixa deitada do sintético não tem defeito.** A suspeita era que a
caixa do YOLO, alinhada aos eixos, inchasse ao girar um índice estreito e alto e ensinasse geometria
errada. Duas medições derrubam isso:

- o gerador calcula a caixa como o *bounding box* do polígono do índice **já transformado**
  (`bbox_of(templates[code][1], mats[i])`) — a geometria está certa por construção;
- e o TAMANHO EFETIVO (depois do resize para `imgsz=1280`) bate faixa a faixa entre sintético e
  real, o que importa porque este modelo é preso à escala:

| faixa | sintético (larg × alt) | real, reduzido a 1280 |
|---|---|---|
| em pé | 45 × 91 | 47 × 87 |
| inclinado | 73 × 89 | 73 × 87 |
| deitado | 85 × 78 | 85 × 79 |
| muito deitado | 89 × 59 | 94 × 67 |

O único vão que sobra é de QUANTIDADE — 18,4% de índice deitado no sintético contra 31,0% no real —
e foi exatamente esse vão que o `backup_12` tentou fechar, sem sucesso.

**O que a medição achou no lugar, e reescreve o alvo.** Rodando o modelo na validação SINTÉTICA (a
própria distribuição que o treinou, onde nada foi purgado):

| faixa | detectados | **classe correta** |
|---|---|---|
| em pé | 99,9% | **98,3%** |
| inclinado | 99,7% | 98,7% |
| quase deitado | 100,0% | 98,9% |
| deitado | 100,0% | 98,0% |
| **muito deitado** | **99,4%** | **89,2%** |

**A detecção não se move; quem desaba é a CLASSE** — 9 pontos, dentro da distribuição de treino. E o
erro não é de um tipo só: em pé × deitado, *naipe na mesma cor* vai de 0,6% a 2,9%, *valor* de 0,6%
a 2,3% e *valor+naipe* de 0,2% a 1,0%. **Tudo multiplica por ~4-5×** — não é o pip que se perde nem
o glifo, é o índice inteiro que fica mais difícil girado.

Isso casa com a composição da perda medida ao vivo em 03/09 (44,9% classe ERRADA, 30,1% classe
certa abaixo do limiar) e explica o nome errado: **ao vivo, classe errada numa vaga conta como
MISS**, porque a vaga tem rótulo estabelecido e a detecção que chega com outro rótulo não casa. O
pipeline reporta "perda de detecção" onde o modelo entregou uma caixa com a classe trocada.

**Por que mais dado deitado não resolve**: o modelo já vê 18% de índice deitado no treino e ainda
assim erra a classe 4-5× mais neles. A dificuldade não é escassez — é invariância à rotação, que é
propriedade do modelo, não do dataset. Todas as tentativas de 25/08 e 03/09 atacaram a escassez.

**O ganho concreto desta sessão é um INSTRUMENTO que enxerga o alvo.** Era o problema central
registrado em "Os três instrumentos de aceite são cegos": o `eval_classes` num
`datasets/real/<partida>` dá 100% de detecção por construção, e **agora se sabe que ele também dá
99,4-99,7% de CLASSE em todas as faixas** (11/08 e 12/08 medidos hoje) — o `extrai_gravacao.py` só
guarda frame em que tudo foi detectado, então o conjunto é purgado da falha duas vezes. Já a
validação SINTÉTICA mostra o gradiente inteiro, roda em minutos e não precisa de gravação nenhuma.

`eval_classes.py` passou a publicar o TIPO do erro repartido em pé × deitado, que é o que diz se
quem se perde é o pip ou o glifo. Use a validação sintética como triagem rápida de qualquer
retreino que ataque rotação — com a ressalva de sempre: é in-distribution, então prova sensibilidade
ao defeito, não generalização. Confirmar continua sendo com `eval_rotacao.py` nas gravações.

#### Rotação no AUGMENT (`degrees=10`): REPROVADO, e o motivo é o RÓTULO (2026-09-14)

Primeira tentativa de atacar o alvo reescrito (invariância à rotação). A/B com a receita do
`backup_11` reproduzida número a número (2.988 imagens, 1.133 reais = 38%, 55 negativos = 1,8%,
holdouts `20260811-211614` e `20260819-162252-dificeis`), contra o controle `ab-fliplr05` treinado
em 03/09 com a mesma receita.

**Critério 1 — triagem no sintético** (classe por faixa; é o instrumento que enxerga o alvo):

| faixa | controle | `degrees=10` |
|---|---|---|
| em pé | 98,4% | 98,5% |
| deitado | 98,7% | 97,4% |
| **muito deitado** | **89,2%** | **86,7%** |
| deitado (≥1,0) total | 93,9% | **91,9%** |

**Critério 2 — `eval_rotacao` ao vivo**, os dois modelos lendo o MESMO vídeo:

| faixa | 28/08 controle → braço | 26/08 14:12 controle → braço |
|---|---|---|
| **muito deitado** | 13,62% → **13,48%** | 11,78% → **13,87%** |
| GLOBAL | 5,45% → 5,16% | 2,62% → **3,09%** |

Plano no 28/08 (0,14 ponto, fundo do ruído) e **pior no 26/08** (2,1 pontos na faixa alvo, acima do
piso). Pela regra do repositório — ganho nas DUAS gravações e acima de ~1 ponto — está reprovado.

**O mecanismo estava escrito no comentário do próprio parâmetro, e agora tem número.** A caixa do
YOLO é alinhada aos eixos, então o augment gira a imagem e recalcula a caixa a partir dos CANTOS DA
CAIXA ANTIGA, não do glifo. Numa caixa de 45×91 (a mediana do índice em pé), girar 10° dá
60×97: **+33% de largura e +43% de área**. O modelo é treinado com caixa frouxa, e a diversidade de
rotação que ele ganha não paga isso.

**A lição que generaliza: rotação no AUGMENT e rotação no GERADOR não são a mesma coisa, e a
diferença é o rótulo.** O gerador gira a carta e calcula a caixa do polígono do índice **já
transformado** (`bbox_of(templates[code][1], mats[i])`) — exata em qualquer ângulo. O `degrees` não
tem como fazer isso, porque no momento do augment o polígono já virou caixa. Qualquer ataque futuro
à rotação tem de vir do gerador, **não** do `degrees`. Ele fica no script, documentado e em 0.

**A triagem acertou o veredito, e este foi o primeiro teste dela como PREVISOR**: reprovou no
sintético (89,2 → 86,7) e o decisor ao vivo confirmou. Uma concordância não a valida — mas já é
mais do que os três instrumentos antigos conseguiam, que era não ver nada.

**Achado operacional da mesma sessão:** o treino quebrava no meio com `Couldn't open shared event` /
`Pin memory thread exited unexpectedly`. É memória compartilhada entre processos do Windows, **não**
VRAM (sobravam 8,7 GB de RAM e 3 GB de VRAM). Causa: o `workers=8` padrão do Ultralytics com
`imgsz=1280`. O `finetune_local.py` ganhou `--workers`, com padrão **2**, que atravessa.

Pesos do braço reprovado em `training/runs/ab-degrees10/weights/best.pt` (não publicado).

#### TTA não extrai nada: o vão não é de inferência, é da representação (2026-09-14)

Diagnóstico barato, sem treino nenhum. Se o TTA do Ultralytics (`augment=True`: multi-escala mais
espelho) fechasse o vão de 9 pontos do índice deitado, o defeito seria de EXTRAÇÃO e existiria
conserto mais barato que retreinar.

| faixa | normal | TTA |
|---|---|---|
| em pé | 98,5% | 98,7% |
| **muito deitado** | **92,9%** | **92,9%** |

**Zero.** O que o modelo não lê num índice girado, ele não passa a ler consultando-o de várias
formas — o vão está na representação aprendida. Fecha a família inteira de ideias de "mudar como se
pergunta ao modelo" (e o TTA custaria ~3× de inferência, que hoje não há: a GPU é o gargalo desde
que a câmera foi a 60 fps).

**Ressalva que evita concluir demais:** o TTA do Ultralytics testa escalas MENORES (1 / 0,83 /
0,67). Ele não diz nada sobre subir o `imgsz` para 1600, que vai na direção oposta — essa porta
continua aberta.

#### Dois braços não podem montar o dataset na MESMA pasta

Defeito exposto durante o A/B de rotação, e o modo de falha é traiçoeiro. Todo treino montava o
dataset em `datasets/fans-split/`, apagando-a com `rmtree` na entrada. Lançar o segundo braço
enquanto o primeiro ainda lia dela (validação final) matou o primeiro com `Image Not Found` — e
esse foi o caso BARULHENTO. Se a cópia do segundo tivesse começado um pouco mais tarde, o primeiro
teria terminado tendo lido, sem erro nenhum, imagens do OUTRO braço: dois modelos comparados sem se
saber o que cada um viu.

Agora cada rodada monta em `fans-split-<nome>`, e o `--nome` já existia exatamente para os braços
não colidirem.

#### Reamostrar a imagem rica em índice deitado (`--peso-deitado 3`): REPROVADO (2026-09-15)

A segunda tentativa contra o alvo reescrito, e a primeira sem mexer em rótulo nenhum: repetir 3× as
567 imagens sintéticas com 30%+ dos índices deitados, o que sobe a fatia deitada de 18,6% para ~27%.
O controle certo não é o `ab-fliplr05`, e sim o `--peso-aleatorio` (`ab-random3`): o mesmo número de
imagens repetidas, só que sorteadas. Os dois braços foram conferidos pelo tamanho: **4.122 treino /
331 validação, 1.133 reais = 27%** nos dois. A única diferença entre eles é o critério de seleção.

O primeiro braço deitado (`ab-deitado3`, 14/09) morreu na época 11 de 12 com a colisão de pasta da
seção anterior, e a redetecção dele parou em 78% do vídeo. Por isso foi **retreinado inteiro**
(`ab-deitado3b`): um braço com uma época a menos que o controle não serve para medir a ~1 ponto de
ruído. Os arquivos parciais (`models/ab_deitado3.pt`, `gravacoes/20260828-144911/sessao-ab_deitado3.jsonl`)
**não valem como medida**.

**Triagem sintética** (200 imagens, 158 índices muito deitados):

| faixa | controle `fliplr05` | aleatório ×3 | **deitado ×3** |
|---|---|---|---|
| em pé | 98,4% | 98,5% | 98,6% |
| muito deitado | 89,2% | 89,2% | **88,0%** |
| todo deitado (≥1,0) | 93,9% | 93,9% | **93,2%** |

**Ao vivo, com `eval_rotacao`** (perda de detecção, os modelos lendo o MESMO vídeo):

| faixa | 28/08 aleatório → **deitado** | 26/08 14:12 aleatório → **deitado** |
|---|---|---|
| deitado (1,0-1,2) | 5,63% → **7,83%** | 2,74% → 2,25% |
| **muito deitado** | 14,64% → **13,63%** | 13,03% → **13,08%** |
| GLOBAL | 6,16% → 6,33% | 2,82% → 2,81% |

Na faixa-alvo, o braço deitado ganha 1,0 ponto numa gravação (no piso de ruído) e empata na outra;
na faixa vizinha, perde 2,2 pontos numa e ganha 0,5 na outra. Não há ganho nas duas gravações,
e a triagem concorda. **Reprovado.** O modelo em produção continua o `cards_backup_11`, que é,
aliás, o melhor dos quatro na faixa muito deitada de 26/08 (11,07%).

**O que isto fecha:** somado ao `backup_12` (abertura 180 do gerador), são **duas** tentativas de
dar ao modelo mais índice deitado, e as duas sem efeito. Com o rótulo exato do gerador e sem mudar
nenhuma imagem, a ênfase na condição não move a classe. Isso confirma o diagnóstico de 14/09: **o
problema não é escassez, é invariância à rotação.** Não tente outra variação de "mais dado deitado".
As portas que continuam abertas atacam a representação: `imgsz` 1600 (o índice deitado chega com
59-67 px de altura a 1280) ou uma arquitetura maior. **O `imgsz` 1600 foi medido em 2026-09-17 e
REPROVADO** — ver "`imgsz` 1600: REPROVADO, e a triagem sintética errou o palpite".

**Achado operacional: o treino é morto por falta de RAM na etapa FINAL.** O `ab-deitado3b` terminou as
12 épocas e foi derrubado durante a validação final do Ultralytics, antes de compactar o `best.pt`
(ficou com 16,9 MB contra 6,3 MB). O `ab_deitado3.pt` de 14/09 tem o mesmo tamanho, então a queda
daquela noite provavelmente foi a mesma coisa. Os pesos salvos a cada época sobrevivem. Para igualar
ao controle, basta `strip_optimizer` (de `ultralytics.utils.torch_utils`). Feche o navegador antes de
treinar: com o Chrome aberto sobram ~5 GB livres de 15,3.

#### O piso de ruído é ~1 ponto, não 0,3

E este é o corolário que recalibra as conclusões anteriores. O braço A é a **mesma receita** do
`cards_backup_11` — conferida número a número: 2.988 imagens, 1.133 reais (38%), 55 negativos
(1,8%) — e mesmo assim mexeu **1,06 ponto** de perda global numa gravação. O CLAUDE.md estimava
0,3 ponto a partir de duas rodadas que diferiam só na amostra sintética. Com 1 ponto de ruído,
vários "resultados" de 25/08 (as diferenças de 0,2-0,3 entre `backup_10`, `11` e `12`) **não são
resultado**. Exija ganho nas duas gravações, e desconfie de qualquer coisa abaixo de 1 ponto numa
gravação só.

#### De que é feita a perda, agora com a resposta abaixo do limiar em disco

Com o vídeo re-detectado a 0,05 dá para perguntar o que o modelo responde onde a vaga previu a
carta. Na previsão mais fresca (`misses == 1`, 399 vagas-frame de 28/08):

| | | caixa larg/alt | deitada |
|---|---|---|---|
| CEGO — nada ali nem a 0,05 | 24,1% | — | — |
| PIPELINE descartou (entregue ≥ 0,30) | 1,0% | 0,88 | 0% |
| **SÓ LIMIAR** — classe certa, < 0,30 | **30,1%** | **1,90** | **69%** |
| **CLASSE errada no lugar** | **44,9%** | **1,42** | **68%** |

**75% da perda é o modelo respondendo a um índice deitado** — e a maior fatia é classe ERRADA, não
confiança baixa, que é a razão de fundo de baixar o limiar não funcionar. Isto **corrige** o
"12-17% de oclusão" que este arquivo registrava para 28/08: aquele número veio da população já
filtrada do `extrai_dificeis` (uma vaga perdida, código único, `misses` ≤ 12), não de todas as
perdas. Sobre todas, a oclusão é 24%.

#### Uma armadilha em disco, deixada por uma sessão anterior — FECHADA em 2026-09-14

`training/datasets/real/20260828-144911-dificeis` tinha **25 imagens com `review/` intacto**,
enquanto este arquivo registrava que só 8 passaram na auditoria e que a pasta NÃO foi treinada — as
17 rejeitadas nunca tinham sido apagadas de `review/`, que é o mecanismo de rejeição que o
`finetune_local.py` respeita. Um treino rodado sem `--holdout` a puxava em silêncio, incluindo as
duas que rotulam `10D` sobre um `2♦`. **Rejeitar uma amostra é apagar a imagem de `review/` —
auditar sem apagar não rejeita nada.**

As 17 foram apagadas em 2026-09-14, depois de reauditar a folha de contato do zero. O veredito novo
bate carta a carta com o antigo: sobrevivem os cinco `J♥` (0-4), o `3♦` (16) e os dois `2♦`
(19-20), e `collect(..., needs_review=True)` agora devolve **8**. As 17 reprovadas têm as
assinaturas que este arquivo já descreve — caixa sobre **pip sem glifo** no meio da carta (índices
10-13, 23), **glifo coberto pelo dedo** (7, 18), caixa que **invade a vizinha** e contém dois
índices (8, 9, 15), o rótulo `10D` sobre um `2♦` legível (21, 22) e recortes estourados/borrados
sem glifo legível (5, 6, 14, 17, 24).

**A pasta continua não valendo como treino** — as 8 são o mesmo `J♥`, o mesmo `2♦` e um `3♦` quase
na mesma pose, três situações distintas, abaixo do piso de ruído de ~1 ponto. O que mudou é que ela
deixou de poder envenenar um treino distraído.

### O primeiro número AO VIVO do modelo novo (2026-08-25 19:30)

Partida gravada no dia com o modelo publicado, 12,1 min a **37 fps** — e é a única medição desta
sessão que não vem de vídeo MJPG re-detectado.

| | hoje | 11/08 | 12/08 | 19/08 15:50 | 19/08 16:22 | 20/08 17:42 | 20/08 19:43 |
|---|---|---|---|---|---|---|---|
| atraso até a tela | 0,84 s | 0,70 | 0,54 | 0,86 | 0,88 | 0,51 | 0,52 |
| **contradição** | **7,9%** | 10,0% | 14,5% | 10,9% | 8,0% | 13,9% | 12,8% |
| excesso | 6,4% | 7,6% | 6,5% | 8,4% | 3,9% | 5,7% | 7,8% |
| ordem errada | **0,3%** | 2,1% | 1,6% | 0,1% | 0,4% | 0,5% | 1,0% |
| cobertura | 96,2% | 99,5% | 99,4% | 94,6% | 98,2% | 99,4% | 99,2% |

Contradição é a **segunda menor já medida ao vivo** (só 16:22 é menor) e a menor entre as partidas
"normais"; a ordem está entre as melhores. Perda de detecção: **2,90%**.

**Três ressalvas, e a primeira é séria:**

- **A amostra é fina.** Só **15,3% da gravação tem carta no quadro** — 4.126 frames, ~111 s de
  jogo em 12 min de gravação, com 26 trocas de mão. As outras partidas têm 4-16 mil frames com
  carta. Nenhuma conclusão fina sobrevive a isso.
- **Comparar partidas diferentes é fraco**: leque diferente, luz diferente, jogo diferente. A
  tabela é contexto, não prova.
- **Os 2,90% de perda NÃO se comparam** com os 3,98% e 4,97% medidos nos holdouts: aqueles vieram
  de vídeo re-detectado e de OUTRAS partidas. O repositório já avisa que os dois caminhos não são
  comparáveis; aqui vale a mesma regra.

A cobertura de 96,2% é a segunda pior da tabela: 158 frames com carta no quadro e nada na tela.
Vale olhar se um dia isso incomodar.

E o velho conhecido continua: **24 dos 42 buracos de detecção são do 4♠** — a mesma carta que
dominou as perdas em 20/08, e a mesma família A↔4 que o projeto persegue desde julho.

### Três coisas que NÃO melhoraram o modelo em 2026-08-25, e a variância que as explica

Depois do retreino que funcionou, tentei mais três coisas em disco, sem webcam. **Nenhuma passou**,
e o motivo da última vale mais que as três.

**(a) Segunda rodada de dado difícil: +14 frames, e o poço secou.** Afrouxando os filtros (uma
amostra a cada 0,3 s, 12 por carta), os candidatos foram de 281 para 662 — mas só 14 sobreviveram à
auditoria, contra 70 da primeira rodada. A razão está no próprio contador: o descarte "o vídeo
detectou a carta" saltou de 12% para **30-46%** dos candidatos. É o modelo novo já achando o que o
velho perdia — a extração se auto-limita, o que é bom sinal e mau rendimento.

**(b) A PONTA do leque no gerador: o vão existia e fechá-lo não muda nada.** Medido nos rótulos, a
proporção largura/altura da caixa do índice da PONTA (normalizada; os dois canvas são 16:9):

| | ponta p50 | ponta > 0,80 |
|---|---|---|
| sintético `ABERTURA=(25,150)` | 0,54 | 15,3% |
| sintético `ABERTURA=(25,180)` | **0,60** | **26,6%** |
| REAL, partidas gravadas | 0,59-0,69 | 18-38% |

O gerador produzia a ponta MENOS girada do que ela chega ao vivo, e é na ponta que o modelo perde a
carta (60-88% dos buracos). A hipótese era boa e o parâmetro fechou o vão na medida certa, sem
custar rótulo por imagem (8,7 → 8,5; 97,4% dos índices rotulados). **E não mudou a perda de
detecção**: com a abertura nova, 6,00% e 3,68%; com a antiga, 6,21% e 3,67% — a mesma coisa. A
`ABERTURA` ficou como constante de módulo (era número solto no meio da função), com os números no
comentário, para a próxima pessoa não refazer a varredura.

**(c) O fantasma do canto invertido: REPROVADO pela terceira vez, agora com o diagnóstico certo.**
O CLAUDE.md dizia que o conserto do `extrai_fantasmas.py` era **geometria** — o canto invertido fica
fora da fileira de índices, a leitura errada de uma carta real cai em cima dela. A geometria de
fato separa (nas sobras, 25-30% caem na fileira e o resto fora, e o sinal inverte junto com o leque
de cabeça para baixo de 19/08 16:22, que é o que se espera do mecanismo). Só que **olhando os
recortes, a população de fora da fileira não é canto invertido**: são (i) pips e arte no MEIO de uma
carta virada — o 4♦ que o modelo lê na figura do K♦ — e (ii) **cartas de verdade fora do leque**,
sendo compradas, descartadas ou na mesa, cujo índice é legítimo. Deixar (ii) sem rótulo é
exatamente o envenenamento que este arquivo documenta. Não foi extraído nada.

O que separaria as duas, e não foi feito: margem de tempo em volta das jogadas (a carta fora do
leque aparece perto de uma jogada) mais um discriminador de "pip no meio da carta" × "índice no
canto". Sem isso, não use aquele script.

**A lição de método, e ela recalibra tudo o que veio antes: a VARIÂNCIA entre rodadas de treino é
do tamanho dos efeitos que se está caçando.** Duas rodadas que diferem só na AMOSTRA sintética
(mesma distribuição, mesmo dado real) deram 6,00% e 6,21% de perda na mesma gravação — 0,21 ponto
de diferença sem nenhuma mudança de conteúdo. Por isso:

| modelo | 19/08 16:22 | 11/08 | média |
|---|---|---|---|
| `cards_backup_10` (antes do dado difícil) | 5,69% | 4,20% | 4,95% |
| **`cards_backup_11` (+70 difíceis) — PUBLICADO** | **4,97%** | **3,98%** | **4,47%** |
| `cards_backup_12` (+14, abertura 180) | 6,00% | 3,68% | 4,84% |
| rodada 4 (+14, abertura 150) | 6,21% | 3,67% | 4,94% |

As três últimas têm classe idêntica (99,5% em 11/08, 98,5-98,6% no `holdout-ranks`, 0 carta
inventada), então o critério é a perda — e o `backup_11` é o único que melhorou nas DUAS gravações,
que é o teste que este repositório já exige de qualquer conclusão ("uma partida só teria dado a
conclusão oposta"). **Foi para ele que o modelo voltou.**

Corolário para a próxima sessão: **diferença de menos de ~0,3 ponto de perda entre dois retreinos
não é resultado**, é ruído de rodada. Para afirmar um ganho menor que isso são precisas várias
sementes, ou gravações novas.

### O conjunto de validação real era CEGO a 5 dos 13 valores (2026-08-20)

Descoberto ao perguntar "onde o modelo ainda erra?". O conjunto real de holdout
(`datasets/real/20260811-211614`) sai de uma partida gravada — e uma partida só tem as cartas que
foram jogadas. Ranks presentes: **7, 5, 6, J, 3, Q, K, 10**. Ausentes: **A, 2, 4, 8 e 9** — que
incluem justamente o A e o 4 (o par de confusão mais antigo do projeto) e o 8 (o pior rank já
medido). Não havia como saber se o modelo lia bem essas cartas.

`training/datasets/holdout-ranks/` fecha esse buraco: 133 frames, 1.330 índices, A/2/4/8/9 nos
quatro naipes, capturados com `capture_rotulado.py` (rótulo pela ORDEM, não pelo palpite do
modelo). São dois leques de 10 cartas, cada um gravado em DUAS ordens — a primeira vai para o
treino, a segunda vira validação. Custo: ~10 min do usuário, uma vez.

**E ele achou na primeira medição o que o conjunto antigo não via:**

| | conjunto antigo (11/08) | conjunto novo |
|---|---|---|
| classe correta | 99,3% | **97,0%** |
| troca de naipe na MESMA COR | **0,0%** | **2,3%** |

As confusões dominantes são `4S→4C` (11×), `9S→9C` (9×), `8H→8D` (4×) — ♠ lido como ♣. A confusão
de naipe da mesma cor, que o projeto tratava como resolvida desde o retreino de 29/07, **nunca
tinha sido medida nestas cartas**.

Retreino com os 142 frames novos (12 épocas, 2.930 imagens, 37% real): classe correta **97,0% →
98,0%**, naipe na mesma cor **2,3% → 1,2%**, `4S→4C` de 11 para 4, `8H→8D` de 4 para 1, `9H→9D` de
3 para 0. Sem regressão: 11/08 foi de 99,3% para 99,4%, detecção seguiu em 100% e as cartas
inventadas seguiram em 0.

**Duas ressalvas que valem mais que o ganho:**

- **O holdout é das MESMAS cartas físicas, na mesma sessão e na mesma luz** — só a arrumação do
  leque muda. Parte do ganho é reconhecer *aquele* 4♠ naquela iluminação, não "quatro de espadas"
  em geral. Para medir de verdade falta capturar noutro dia, noutra luz, com outro baralho.
- **`9S→9C` não se mexeu**: 9 erros antes, 9 depois, enquanto os vizinhos caíram pela metade ou
  zeraram. Erro que não responde a dado novo tem outra causa — provavelmente o pip daquele molde
  ou daquela carta física. É o próximo alvo, e a investigação começa comparando os recortes do 9♠
  e do 9♣ que o modelo vê.

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

#### `NAO_TREINAR`: a pasta reprovada sai do treino sozinha (2026-09-14)

Rejeitar um RÓTULO é apagar a imagem de `review/`. Faltava o outro nível: rejeitar uma PASTA
inteira. `finetune_local.main` varre **todas** as pastas de `datasets/real/` e só pula as do
`--holdout` — ou seja, a seleção era **opt-out e dependia da memória de quem digita a linha de
comando**. Os dados auditados que foram MEDIDOS e pioram o modelo (os `-classe`, os `-dificeis2`)
entravam por omissão: **75 frames**, em 12 pastas.

Um arquivo `NAO_TREINAR` dentro da pasta tira ela do treino para sempre, e a primeira linha dele é
o motivo, impresso na seleção. A decisão passa a morar **junto do dado**, que é o mesmo princípio
do `review/`. O marcador é consultado ANTES do `--holdout`: o marcador é permanente, o holdout é
da rodada.

**O marcador VAZIO ainda tira a pasta** — o arquivo é a decisão, o texto é só para quem for ler
depois. É o caso que a implementação ingênua (`return texto.strip() or None`) erraria em silêncio,
e é por isso que ele tem teste próprio, conferido por mutação nas duas direções.

As 12 pastas marcadas, e o que a medição disse de cada família:

| pastas | frames | por quê |
|---|---|---|
| 8 × `*-classe` | 53 | 0,9 ponto de perda de detecção a mais (1,5 em 19/08 16:22) por 5 erros de naipe a menos |
| 3 × `*-dificeis2` | 14 | segunda rodada de dado difícil: só 14 sobreviveram à auditoria, abaixo do ruído |
| `20260828-144911-dificeis` | 8 | 3 poses distintas (o mesmo `J♥`, o mesmo `2♦`, um `3♦`) |

Sobram **789 frames reais** revisados entrando no treino. Guardado por
`tests/test_finetune_selecao.py`.

Efeito colateral do teste, e é ganho: `finetune_local.py` deixou de importar o `ultralytics` no
topo (agora é dentro do `main`), então importá-lo custa milissegundos em vez de arrastar o torch —
que é o que mantém a suíte rápida. O `parse_args()` foi junto para dentro do `main`, senão
importar o módulo num teste tentaria parsear o argv do pytest.

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

**Onde a meta está (2026-08-19, modelo de 18/08 + `fan_peso_min`, as duas partidas re-detectadas
do vídeo):** compras **32/32 = 100%** ✅ e descartes **31/31 = 100%** ✅ — a meta bate pela
primeira vez. Com três ressalvas que valem mais que o número: o `fan_peso_min` foi afinado NESTAS
duas partidas, uma delas entrou no treino do modelo, e 31 descartes não provam ≥95% (fazem falta
~60). O teste que valeria é uma partida NOVA e curta.

A tabela abaixo é a medição anterior, ao vivo, e fica como registro do ponto de partida:

**Onde a meta estava (2026-08-12, gabaritos corrigidos):**

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

**Os fantasmas dobraram (5 → 11)** — atacados no dia seguinte, ver "Os fantasmas: duas famílias".
Com o `fan_peso_min = 0,6`, as duas partidas passaram a fechar em **100% de compras e 100% de
descartes** (32/32 e 31/31 acumulado), e sobraram 8 fantasmas, todos da família "carta tirada do
leque e recolocada". O parágrafo abaixo é o diagnóstico original, que continua valendo como
descrição do sintoma: Fantasma não baixa a nota (a
conta é sobre jogadas que aconteceram) mas suja o overlay e alimenta o `_discard_history`. Repare
que em `t=148,2s` o fantasma novo é um `discard KS` no mesmo ponto em que o modelo velho dava
`carta_errada 5D→AS`: a carta agora é lida CERTA, mas some do leque por um instante — o que sobrou
ali é instabilidade de PIPELINE, não erro de classe. Suspeita a investigar: nos frames reais só a
MÃO é rotulada, então carta na mesa e monte entram como região visível **sem rótulo**, e este
arquivo já ensina que isso treina o modelo a chamar aquele padrão de fundo.

#### Os fantasmas: duas famílias, e o que separa uma da outra (2026-08-19)

Fantasma nunca vem sozinho: são PARES (`draw X` seguido de `discard X`, ou o inverso), cada par uma
carta que entrou e saiu da mão exibida. Diagnosticados um a um, com as vagas do `FanReader` na tela
— e são dois mecanismos diferentes, com causas diferentes.

**Família 1 — carta DUPLICADA por erro de classe.** O modelo lê o A♥ como A♦ por meio segundo. A
vaga do A♥ não expira nesse tempo (é o que faz o leitor aguentar oclusão) e nasce uma vaga nova a
61 px dela — perto demais para ser outra carta, longe demais para o casamento de 50 px fundir, e
com rótulo DIFERENTE, que é o caso em que a regra de uma-detecção-por-vaga manda abrir vaga nova.
A mão sai com **A♥ mais dois A♦: dez cartas que nunca estiveram juntas em frame nenhum**. O
`StableHand` piora: com `decay = 0,06` a carta que sumiu leva ~10 frames para cair do conjunto,
então a mão exibida é uma UNIÃO no tempo, e duas leituras que se excluem coexistem nela.

A intrusa se denuncia por duas marcas JUNTAS — e é preciso as duas: **duplica** uma carta que já
está na mão, e é muito mais **fraca** (medido: 11,25 de confiança acumulada contra ~50 das
vizinhas). É o `fan_peso_min`. Resultado nas duas partidas re-detectadas: **12/08 foi de
85%/84,2% para 100%/100%** e 11/08 ficou em 100%/100%. Os dois pares de A♦ fantasma morreram.

**Família 2 — carta tirada do leque e recolocada.** O jogador levanta uma carta para descartar,
segura fora do leque, muda de ideia e recoloca. Medido: o 5♦ saiu de `y=500` para `y=58` com o
leque inteiro em `y≈510-644`, e voltou lido como 4♦. Sai um descarte quando ela deixa a fileira e
uma compra quando volta. **Continua aberta**: são os 3 pares que sobram em 12/08. Não é bem um erro
de leitura — a carta realmente saiu da mão.

Duas tentativas MEDIDAS E REFUTADAS, para não repetir:

- **Teto pelo pico visto** ("a mão não pode ter mais cartas do que o modelo viu de uma vez").
  Separa bem em 12/08, mas em 11/08 o modelo nunca vê as 10 juntas em algumas compras, e o corte
  derruba justamente a carta RECÉM-COMPRADA (é a de menor peso): duas compras passaram a sair com
  a carta errada.
- **Piso de peso sem exigir rótulo duplicado.** Mesma falha, pela mesma razão: a carta comprada
  também nasce fraca. É por isso que o `fan_peso_min` só se aplica a rótulo repetido.
- **Guarda de "fora do arco do leque"** (vaga cuja vizinha em x está a mais de N alturas de caixa
  em y). O mecanismo EXISTE — as vagas fantasmas do 4♦ e do 6♦ estavam mesmo a 350 px do leque — e
  sozinha ela até recuperava 2 compras, mas trocava 3 descartes perdidos por 3 com carta errada; e
  combinada com o `fan_peso_min` ela PIORA (2 descartes errados). Foi retirada do código.

**Cuidado ao mexer no `fan_peso_min`**: o platô de 100%/100% é estreito (0,6-0,7) e cada jogada
vale 5 pontos numa amostra de 19. O mecanismo é sólido, o número é fraco — confirme com partida
nova antes de tratar 0,6 como verdade.

### Retreino de 2026-08-20: o logo da parede deixou de ser carta

Primeiro treino com **dado negativo** (`extrai_negativos.py`) e com fundos de sala no gerador.
2.802 imagens de treino: 1.800 sintéticas novas + 947 reais + **55 negativos (2,0%)**, 12 épocas,
1280 px, batch 3. Holdouts de propósito: **11/08** (medir classe) e **19/08 15:50** (medir o
fantasma) ficaram inteiras fora do treino.

| | antigo (`cards_backup_8.pt`) | novo |
|---|---|---|
| imagens sem carta COM carta inventada (holdout) | 25,9% | **0,0%** |
| cartas inventadas | 35 (sempre `10C`/`QC`) | **0** |
| índices detectados (holdout real 11/08) | 100,0% | **100,0%** |
| classe correta (holdout real 11/08) | 99,2% | **99,3%** |

O ganho não custou detecção — que era o risco real de treinar com negativo (passar de ~10% do
treino faz o modelo PERDER carta de verdade, e isso não aparece no mAP).

**Teste de ponta a ponta**, os dois modelos lendo o MESMO vídeo nos 40 s do fantasma de 15:50:

| | antigo | novo |
|---|---|---|
| tela mostrando mão que não existe | 940 frames (~30 s) | **0** |
| a mão real de 9 no mesmo trecho | saía com **11 cartas** (9 + as 2 do logo) | **9** |

O bônus é a segunda linha: o logo não só criava mão do nada, ele também **contaminava a mão de
verdade**, colando duas cartas a mais no leque real.

Ressalva honesta: na partida de 19/08 16:22 re-detectada, a contradição do modelo novo saiu
**10,8% contra 7,8%** do antigo — mesmas cartas de sempre (`QH`, `5H`, `7S`), frames de transição,
com o novo trocando a tela mais vezes (21 × 18). São ~85 frames em 3.682 numa amostra de UMA
partida; não invalida o retreino, mas registra que essa métrica não melhorou junto.

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

# a nota DE HOJE (a mão na tela) — não precisa de gabarito
python scripts/mede_leitura.py gravacoes/<data>
python scripts/mede_leitura.py gravacoes/<data> --varre lock_frames=10,20,30

# a nota ANTIGA (compra/descarte), que precisa de gabarito revisado à mão
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

### O FPS que o `FpsMeter` imprime NÃO é a taxa de quadros distintos (2026-09-03)

E a diferença chega a um terço do trabalho da GPU. O `CameraStream` guarda só o frame mais recente
e o laço lê o que estiver lá: quando o laço gira mais rápido que a câmera, ele processa **a mesma
imagem** várias vezes. Medido nas dez gravações comparando detecções byte-idênticas em frames
consecutivos (a mão treme — duas capturas distintas nunca dão as mesmas caixas):

| gravação | taxa do laço | frames repetidos | **taxa DISTINTA** |
|---|---|---|---|
| 20/08 17:42 | 47,8 | 36,8% | **30,2** |
| 20/08 19:43 | 45,3 | 34,5% | **29,7** |
| 26/08 14:12 | 41,8 | 24,8% | **31,4** |
| 12/08 | 40,0 | 24,0% | **30,4** |
| 28/08 | 34,0 | 6,2% | **31,9** |
| 19/08 16:22 | 29,0 | 1,1% | **28,7** |

A taxa distinta bate em **28-32 em TODAS**, não importa se o laço girou a 29 ou a 48. **A câmera é
o teto, não a GPU** — medido nesta máquina, a inferência a 1280 px leva 19-22 ms (45-52 fps).

Três consequências:

1. **Computador melhor não compra FPS nenhum hoje.** A folga da GPU já está sendo desperdiçada
   reprocessando imagem repetida.
2. **O `CameraStream` nunca pede `CAP_PROP_FPS`** — define FOURCC, largura e altura e aceita o
   padrão do DirectShow (30). **FEITO e CONFIRMADO em 2026-09-14**: a câmera aceitou 60 e a taxa
   distinta foi de ~30 para 45,8, com os repetidos a 0%. A previsão que estava escrita aqui —
   "`lock_frames=20` passa a valer 0,33 s em vez de 0,67 s" — **está ERRADA**: `lock_frames` conta
   VOLTAS DO LAÇO, que são limitadas pela inferência (19,8 ms), não pela câmera; a janela foi de
   0,48 s para 0,44 s e só. Ver "CONFIRMADO na câmera no mesmo dia".
3. **Mais FPS não conserta detecção.** A perda é do índice deitado (erro de classe), e ver a mesma
   cena mais vezes por segundo não muda o palpite.

#### O que foi feito com isso em 2026-09-14 (os três consertos são em disco)

**(a) O instrumento passou a publicar as DUAS taxas.** `FpsMeter.tick(novo)` conta voltas do laço e
capturas distintas, e imprime `[fps] laço 47.8 | câmera 30.2 (37% repetidos)`. Quem diz o que é
captura nova é o `CameraStream`, por um contador de capturas (`read_seq`), não uma comparação de
pixels dentro da métrica — é a mesma decisão do `ultimo_leque` na contradição. A conversão de
`lock_frames` para segundos continua usando a taxa do LAÇO, que é a correta: `process_frame` roda a
cada volta, repetida ou não.

**(b) A volta repetida deixou de pagar inferência.** Se a captura não mudou, a detecção anterior é
reaproveitada. **Não muda nada do que o pipeline vê**, e a premissa foi verificada em vez de
suposta: 5 inferências em cada um de 3 frames com carta (8-10 detecções) saem byte a byte iguais —
é por isso que a medição de 03/09 conseguiu contar repetições comparando detecções. Devolve 19,8 ms
de GPU em cada volta repetida, que eram 1-37% delas conforme a gravação.

`process_frame` continua rodando na volta repetida **de propósito**: todo parâmetro é contado em
VOLTAS DO LAÇO e foi afinado assim, então pular a volta inteira mudaria o significado de
`lock_frames`, `fan_window` e `fan_expire` de uma vez. Isso é outra mudança e precisa da própria
medição.

**(c) `config.cam_fps = 60`: a câmera finalmente é PEDIDA.** Era o ganho mais barato do projeto e
ninguém o pedia — o DirectShow entregava o padrão. Pedir não é obter, então o `CameraStream`
anuncia o que foi NEGOCIADO ao abrir e avisa quando a câmera dá menos. E há uma guarda para o caso
que não dá para testar sem o hardware: se a câmera abrir e **não entregar o primeiro frame** com a
taxa pedida, o pedido é desligado e ela é reaberta no padrão — um modo não suportado não pode
deixar o app cego.

#### CONFIRMADO na câmera no mesmo dia — e o gargalo trocou de lugar

A câmera aceitou: `câmera 0: aberta 1920x1080 @ 60.0002 fps (pedimos 60)`. Com o leque no quadro,
depois de assentar:

    [fps] laço 45.8 | câmera 45.8 (0% repetidos)  (lock_frames=20 ~ 0.4s)

| | antes | agora |
|---|---|---|
| imagens DISTINTAS por segundo | ~30 | **45,8** (+53%) |
| frames repetidos | 25-37% | **0%** |
| taxa do laço | 41,8 | 45,8 |
| `lock_frames=20` vale | 0,48 s | 0,44 s |

**O PROGNÓSTICO DE ATRASO ESTAVA ERRADO, e o erro é instrutivo.** Esta seção previa que a tela
passaria a reagir "~2× mais rápido" — a nota de memória e o `config.py` diziam o mesmo desde 03/09.
Não acontece: `lock_frames` conta **VOLTAS DO LAÇO**, e a taxa do laço é limitada pela INFERÊNCIA
(19,8 ms ≈ 50 voltas/s), não pela câmera. Ela já era 41,8 e foi para 45,8; a janela de tempo quase
não se mexeu. Quem previu 2× confundiu as duas taxas — exatamente o erro que o conserto (a) existe
para tornar impossível.

**Os `0% repetidos` são a prova de que o gargalo MUDOU DE LUGAR**: era a câmera, agora é a GPU, e
ela já estava perto do teto. Não há mais folga escondida no laço.

**O ganho real é na QUALIDADE DO VOTO, não no tempo.** Antes, das 20 voltas de uma janela de trava,
~15 eram imagens distintas e o resto eram cópias da mesma imagem — e cópia não traz informação
nova, mas VOTA: um erro de classe num quadro capturado entrava com peso 2 na votação ponderada do
`FanReader`. Agora todo voto é evidência independente, na mesma janela de ~0,44 s. **Se isso move a
nota medida, ninguém sabe** — só aparece numa partida gravada nova, e é o que falta medir.

**Consequência para o `imgsz`:** subir de 1280 para 1600 agora tem preço explícito. 27,8 ms por
inferência derruba o laço para ~36 voltas/s e `lock_frames=20` sobe de 0,44 s para 0,55 s. É troca
direta entre resolução e tempo de reação — antes havia folga escondida para pagar isso, e não há
mais.

#### O voto duplicado NÃO estava atrapalhando: medido em disco, e a nota não se move

A pergunta que o conserto do FPS deixou em aberto — "a votação sem cópias melhora a tela?" — foi
respondida **sem gravar partida nova**, e de propósito: partida nova é leque diferente, luz
diferente e jogo diferente, e este arquivo repete que comparar partidas diferentes é prova fraca. O
que existe em disco é melhor: as gravações guardam as detecções **por volta do laço**, repetições
inclusive, então dá para removê-las e re-medir A MESMA partida.

**Duas decisões de método, e sem a segunda o teste mede outra coisa:**

1. **Repetição só é detectável em frame COM detecção.** Duas capturas distintas da mão nunca dão as
   mesmas caixas (a mão treme) — mas duas capturas de sala vazia dão as duas listas vazias. Cobrar
   repetição no quadro vazio seria inventar. O detector reproduz a tabela de 03/09 número a número
   (36,8% / 34,5% / 24,8% / 24,0% / 6,2% / 1,1%), o que o valida.
2. **Todo parâmetro contado em frames foi reescalado pelo mesmo fator** (`lock_frames`,
   `fan_window`, `fan_min_appear`, `fan_expire`, `fan_exibe_misses`), para a janela em SEGUNDOS
   ficar igual nos dois braços. Sem isso, tirar 37% dos frames faria `lock_frames=20` durar 37% mais
   e o teste mediria duração de janela, não voto duplicado. Conferido: A tem janela de 0,418 s com
   ~12,6 imagens distintas, B tem 0,43 s com 13 — casados.

| gravação | contradição | excesso | ordem errada | vaivém | atraso | cobertura |
|---|---|---|---|---|---|---|
| 20/08 17:42 (37% rep.) | 14,6 → 14,8 | 3,0 → 3,6 | 0,4 → 1,0 | 16 → 34 | 0,49 → 0,46 | igual |
| 20/08 19:43 (35%) | 13,8 → 14,3 | 4,7 → 5,0 | 0,4 → 0,9 | 12 → 12 | 0,49 → 0,45 | igual |
| 26/08 14:12 (25%) | 9,2 → 9,3 | 1,6 → 1,6 | 0,5 → 0,4 | 2 → 2 | 0,57 → 0,53 | igual |
| 12/08 (24%) | 16,3 → 16,1 | 3,1 → 3,3 | 1,4 → 1,6 | 22 → 32 | 0,55 → 0,52 | igual |

**O piso de ruído desta comparação foi medido junto**, varrendo `lock_frames` em ±10% na mesma
gravação: contradição 14,2-14,9, excesso 2,8-3,4, ordem 0,3-0,4, vaivém 16-18. Ou seja: **contradição,
excesso e cobertura não se movem** — as diferenças cabem dentro do que um empurrão de 10% num
parâmetro produz. O atraso melhora 0,03-0,04 s nas quatro, o que é consistente em direção mas está
na borda do arredondamento do reescalonamento.

**Conclusão: tirar o voto duplicado não melhora a tela.** O ganho de hoje é real no mecanismo (a
votação passou a decidir com evidência independente) e **invisível no produto** — que é o mesmo
padrão já registrado no retreino de 25/08 ("consertar o modelo aparece na perda de detecção, não na
tela").

**O que ficou EM ABERTO, e é honesto não fechar:** o vaivém dobra em duas das quatro gravações
(16→34 e 22→32), muito fora do piso de 16-18. Duas explicações foram testadas e **nenhuma se
sustentou**:

- *"a margem de ordem precisa subir agora"* — varrida em 0,05/0,10/0,15 no braço B: 34 → 32 → 34,
  plana. A margem não é o botão.
- *"foram as repetições que sumiram"* — o controle derruba isso: o stream ORIGINAL (com as
  repetições) rodado com os MESMOS parâmetros do braço B dá vaivém **36**, acima dos 34 de B. Quem
  move o vaivém é a duração da janela, não a cópia.

Então o vaivém de B não é atribuível às repetições, e o efeito residual não tem mecanismo
identificado. **O que isso obriga a fazer: olhar a ordem na próxima partida gravada.** É o defeito
que o usuário relatou em 26/08 ("o 7 tava trocando de lugar com o 10"), e é a métrica mais sensível
do conjunto.

**Limite que este teste NÃO vence:** ele não reproduz a condição de hoje (45,8 distintas/s), porque
as câmeras das gravações antigas só entregavam ~30 distintas/s. Ele responde "o voto duplicado
atrapalha?", não "qual é a nota a 60 fps". Essa segunda só sai de gravação nova.

Os streams filtrados ficaram em `gravacoes/<data>/sessao-semrepetidos.jsonl` (o `--dets` do
`mede_leitura.py` os lê), para o teste poder ser refeito sem recomeçar.

Guardado por `tests/test_fps_e_camera.py` (7 testes, conferidos por mutação: ignorar o `novo`
derruba três, tirar a guarda do FPS derruba um, contar leituras em vez de capturas derruba um, e
re-inferir sempre **ou** pular a volta inteira derrubam o sétimo — ele prende as duas metades do
contrato).

#### O custo de trocar a ARQUITETURA, medido (e a estimativa antiga estava errada)

O `cards.pt` é um YOLOv8 **nano: 3,02 M de parâmetros**, o menor da família. Medido nesta GPU
(RTX 3050 Laptop, 4 GB) a 1280 px, construindo do YAML — velocidade depende da arquitetura, não
dos pesos:

| arquitetura | params | ms/frame | fps | contra a câmera (~30) |
|---|---|---|---|---|
| **`cards.pt` (v8n, hoje)** | 3,02 M | 22,0 | **45** | 50% de folga |
| yolo11s | 9,46 M | 31,8 | 31,5 | empata |
| yolov8s | 11,17 M | 33,6 | 30 | empata |
| yolov8m | 25,9 M | 65,2 | 15 | vira o gargalo |

A nota do projeto dizia "o laço cai de 41 fps para ~15-20" — **esse é o número do `m`, não do `s`**.
O `s` cai em cima da taxa da câmera, ou seja custa ~10% de quadros distintos, não metade.

O que a troca cobra, e o item 1 é o que mata: **o `s` tem outra forma de tensor, então não parte
dos pesos atuais** — começaria do COCO, jogando fora ~10 rodadas de fine-tuning desde julho (o pip
do naipe, os negativos, o dado difícil, o dado real das partidas). Mais: treino a batch 1-2 nestes
4 GB, 1-2 h por rodada; a folga de FPS que hoje permite gravar some; e todos os parâmetros contados
em quadros mudam de significado.

**Alavanca mais barata a testar antes**: subir o `imgsz` de 1280 para 1600 custa quase o mesmo em
FPS (27,8 ms contra 33,6 do `s`), ataca o índice pequeno/girado e **preserva o fine-tuning**. Custo
do `imgsz` nesta GPU: 640 → 18,1 ms · 960 → 16,1 · 1280 → 19,0 · 1600 → 27,8 · 1920 → 31,1.
Exige retreinar na mesma resolução: este modelo é **preso à escala**, e isso está medido em
"Dado DIFÍCIL" (ampliar o recorte 4× fez o modelo não detectar nada em 28 de 31 casos).

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
  | `tracker.on_hand_changed`, `undo_last`, `correct_event`, `_discard_history` | — (compra/descarte saiu de escopo) | `tests/test_tracker_*`, `scripts/demo_server.py` |
  | `app/scoring.py`, `scripts/revisar_partida.py`, `--gabarito` do replay | — (medem compra/descarte) | `tests/test_scoring.py` |
  | `config.confirm_confidence`, `config.hand_size` | — | `tests/test_config.py`, `GameTracker` |
  | `/api/undo`, `/api/correct` (servidor) | — (o painel não chama mais) | `tests/test_server.py` |

  Os cinco primeiros morreram junto com a segunda câmera em `f5fdf64`. Os de baixo morreram em
  2026-08-19, com a virada de escopo — e foram MANTIDOS de propósito: são história medida e o
  material de partida de quem for construir os modelos de compra e descarte. `scripts/demo_server.py`
  (partida simulada) ainda fala a API velha e por isso continua funcionando — mas exercita um
  caminho que o app real não usa mais.
- `assets/cards/` é git-ignored; sem rodar `scripts/download_assets.py` os overlays ficam com
  imagens quebradas.
- Docs de origem em `docs/superpowers/`: o spec (`specs/`) descreve a intenção aprovada; o plano
  (`plans/`) é histórico da implementação e já divergiu do código (ex.: limiar 0.75, um baralho só).
