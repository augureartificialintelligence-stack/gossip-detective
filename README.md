# ◈ GOSSIP DETECTIVE 1.0 — Central de Comando

*Toda história deixa rastros. Investigue antes de compartilhar.*

Central de verificação com cara de sala de operações. Você digita uma frase, rumor, palavra ou notícia; enquanto a IA pesquisa
na web, **sinais de varredura** piscam pelo mapa (**Cronograma da Informação**). Cada registro confirmado acende um **ponto
vermelho** no lugar e na data em que aparece, e um pacote de dados voa do mapa até o **Cronograma Documental**, à direita, onde
o registro entra em ordem cronológica: data e título, que se expandem para o texto e o link da fonte. Ao final, os sinais se
apagam, os demais pontos param de piscar e só o **ponto final do rastro** segue em alerta. Em seguida o **relatório da missão**
sobe para a vista principal e o mapa desce; o botão **⇅** no título do mapa alterna as duas disposições.

O relatório mostra sempre um **?** no lugar do veredito. A síntese é curta e termina com a conclusão: **comprovado**,
**tendencioso**, **refutado** ou, quando faltam registros, **inconclusivo**. Limites e fontes consultadas ficam recolhidos.
A legenda do mapa fica no botão **?** do canto do mapa.

### Matriz de fontes REVELATIO

As pesquisas da IA partem da matriz editorial `docs/REVELATIO_MATRIZ_FONTES_V1.md` (70 fontes: agências de checagem,
arquivos nacionais, bibliotecas, órgãos científicos e de pesquisa). Ela é convertida para `dados/matriz_fontes.json` por
`ferramentas/importar_matriz.py` e entra nas instruções da IA como **prioridade de pesquisa**, com as regras de uso da matriz
(alegação exata, documento de origem, fontes independentes, datas separadas, fato x autoria x intenção). Fontes fora da matriz
continuam permitidas quando forem o documento original ou a melhor evidência. Todo marco cuja fonte pertence à matriz recebe o
código dela (`fonte.matriz_id`, de F001 a F070), exibido no Cronograma Documental. Ao revisar a matriz, rode o importador de novo.

### Arquivo REVELATIO (catálogos editoriais)

Os catálogos `docs/GOSSIP_100_DESINFORMACAO_V1.md` e `docs/GOSSIP_100_HOAXES_V1.md` (200 fichas) são convertidos para
`dados/catalogos.json` por `ferramentas/importar_catalogos.py`, cada ficha com a orientação editorial do próprio documento
(significado da classe preliminar e cuidados específicos). `ferramentas/missoes_catalogo.py` investiga as fichas com a IA e
publica os dossiês em `dados/colecoes/`, marcados como **gerados por IA, revisão editorial pendente**:

```
.venv\Scripts\python ferramentas\missoes_catalogo.py --ids D005,H003
.venv\Scripts\python ferramentas\missoes_catalogo.py --todas --paralelo 3 --orcamento 110
.venv\Scripts\python ferramentas\missoes_catalogo.py --ids H099 --refazer --buscas 10 --leituras 6 --esforco high
```

O executor retoma de onde parou, registra custo e resultado de cada ficha em `dados/colecoes/_relatorio.json` (fora do
repositório) e para de iniciar missões ao atingir o orçamento. Os dossiês aparecem para todos na seção **ARQUIVO** da central
(abas 100 Desinformação e 100 Hoaxes, com filtro) e na demonstração do GitHub Pages.

### Versão de demonstração (GitHub Pages)

**Link:** https://augureartificialintelligence-stack.github.io/gossip-detective/

O GitHub Pages só hospeda arquivos estáticos, então a demonstração roda sem servidor: não há pesquisa ao vivo por IA, login
nem avaliações, e nenhuma chave de API é publicada. Ela reproduz os dossiês verificados e as investigações já feitas (com
mapa, cronograma, síntese e relatório) e mostra as faixas Trends e Bombando a partir de um retrato estático em `public/demo/`.
Quando a página não encontra o servidor, entra sozinha nesse modo e exibe a faixa "VERSÃO DE DEMONSTRAÇÃO".

Para atualizar o conteúdo da demonstração com as investigações e trends mais recentes desta máquina:

```
.venv\Scripts\python ferramentas\gerar_demo.py
```

e envie as mudanças (`git add public/demo && git commit && git push`); o workflow `.github/workflows/pages.yml` publica sozinho.
O retrato não inclui contas, sessões, avaliações nem o identificador de quem pesquisou.

### Identidade visual

Tema de portal de investigação: fundo preto, texto branco e destaque ouro, tipografia única **Rajdhani** (SIL Open Font
License, arquivos em `public/vendor/fonts/`, sem depender de internet), etiquetas douradas tracejadas com cantos marcados,
faixas cinzas e rodapé em faixa cinza. O **logo oficial** é o "G" de Gossip desenhado como uma lupa (anel aberto do G, barra
interna e cabo), definido uma vez como símbolo SVG em `index.html` e usado no topo, no login e no ícone da aba. A linguagem
visual foi inspirada em portais institucionais de investigação, sem usar selos, nomes ou marcas de nenhum órgão real.

### Contas (login local)

A central abre com a tela de **Entrar / Criar conta**. Por enquanto tudo roda neste computador, sem banco de dados: as contas
ficam em `dados/usuarios.json` (senhas com scrypt e sal, nunca em texto) e as sessões em `dados/sessoes.json` (só o hash do
token; cookie HttpOnly válido por 30 dias). Toda a API, exceto `/api/status`, exige sessão. Cada missão nova fica no histórico
de quem a fez; as missões anteriores ao login aparecem para todos.

### Faixas: Trends e Bombando no Gossip Detective

Abaixo da barra de pesquisa, duas faixas rolam sem parar da direita para a esquerda, como cotação de bolsa, repetindo a lista
em laço. Elas pausam só com o mouse em cima (ou com foco de teclado), para o usuário clicar; rolam mesmo com "reduzir
movimento" ligado no sistema, por requisito de produto.

- **TRENDS:** as 3 alegações que mais repercutiram nas agências de checagem nos últimos dias. Não existe dado público de
  volume de buscas por boato; a ordem é por repercussão (quantas checagens trataram da mesma alegação). Cada item só entra se
  a URL da checagem veio de fato da base ou da busca. O levantamento fica em cache por 6 horas (`dados/tendencias.json`);
  clicar no rótulo TRENDS atualiza.
- **BOMBANDO NO GOSSIP DETECTIVE:** toda pesquisa concluída por qualquer usuário nos últimos 7 dias entra na faixa (até 20;
  as mais repetidas primeiro, depois as mais recentes). A faixa se atualiza a cada minuto e logo após cada investigação.
  Clicar abre a investigação já feita (reprodução, sem custo). Com pouco uso, completa com os dossiês verificados.

Clicar num item de TRENDS carrega a alegação na barra de pesquisa; a investigação só começa ao apertar RASTREAR.

### Avaliações e comentários

No fim de cada relatório, o usuário dá de 1 a 5 estrelas e pode comentar. Cada usuário tem uma avaliação por investigação
(reenviar atualiza). A média e os comentários de todos aparecem ali, só com o primeiro nome. Ficam em `dados/avaliacoes.json`.

### Base de checagens do Google (opcional, gratuita)

Com `GOOGLE_FACTCHECK_KEY` no `.env` (chave do Google Cloud com a **Fact Check Tools API** ativada), a central passa a usar a
base de checagens publicadas por agências no formato ClaimReview (Aos Fatos, Estadão Verifica, UOL Confere, AFP Checamos,
Comprova e outras):

- **Radar de tendências:** as checagens dos últimos 7 dias vêm de graça da base; a IA só agrupa e ordena, sem busca na web
  (mais rápido e bem mais barato). Se a base trouxer menos de 6 checagens, o radar volta à busca na web.
- **Investigações:** a IA ganha a ferramenta gratuita `consultar_checagens` e a usa antes da busca paga em boatos e notícias
  atuais. As URLs devolvidas contam como fontes recuperadas. Temas históricos e origem de palavras continuam na busca na web.

Lupa, Boatos.org e g1 não aparecem nessa base; o radar pela busca na web os alcança. A API está em versão alpha no Google.

O botão **☰** abre o menu lateral com o **histórico de missões da IA** e os **dossiês verificados**. Abrir um item reproduz a
pesquisa já feita, sem custo.

## Como rodar (Windows)

1. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele cria o ambiente Python e instala as dependências.
2. Para ativar a pesquisa por IA, abra o arquivo **`.env`** (criado automaticamente) e preencha `ANTHROPIC_API_KEY`.
   Reinicie o `iniciar.bat`.
3. O navegador abre em `http://127.0.0.1:8765`.

Sem a chave, a central funciona em **modo Arquivo** com os três dossiês verificados (Farsa Lunar, palavra “robô”,
vitória na Europa em 1945).

Manualmente: `python -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`, `.venv\Scripts\python server.py`.
Requer Python 3.11 ou superior. Não há etapa de build nem dependências de frontend para instalar: D3, TopoJSON e o atlas
mundial já estão em `public/vendor/`.

**Se a página às vezes fica carregando para sempre ou o mapa aparece sem países:** antivírus com proteção web (Avast, AVG e
similares) interceptam o tráfego do navegador e podem travar respostas do servidor local. Recarregue a página ou adicione
`http://127.0.0.1:8765` às exceções da proteção web. O mapa tenta baixar o atlas de novo sozinho se o download travar.

## Os dois modos

| | Pesquisa ao vivo · IA | Arquivos verificados |
|---|---|---|
| Fonte | Claude (`claude-opus-5-5`) com busca e leitura na web | Dossiês de curadoria em `dados/casos_verificados.json` e missões salvas da IA |
| Animação | Real: um ponto surge somente quando um marco é validado | Reprodução de 12 s, anunciada como tal no mapa (“REPRODUÇÃO DE ARQUIVO VERIFICADO”) |
| Pergunta inédita | Investigada na hora | Mensagem honesta de “sem dossiê”; nada é inventado |

As investigações da IA ficam salvas em `dados/investigacoes/` e aparecem no **histórico do menu ☰**. Cada missão tem link
próprio (`?caso=<id>`).

## Como a IA é mantida honesta

O conceito fundador proíbe fabricar fontes, datas, coordenadas e elos. O motor (`gossip/investigador.py`) aplica isso em código,
não só no prompt:

- **Só entram URLs efetivamente recuperadas.** Todo resultado de `web_search` e `web_fetch` é varrido e suas URLs vão para uma
  lista. Um marco cuja fonte não está na lista é **rejeitado**, e o motivo volta para a IA corrigir. A rejeição aparece no
  contador REJEITADOS e no log.
- **Esquema estrito.** As ferramentas `registrar_marco`, `concluir_investigacao` e `recusar_investigacao` usam `strict: true`, e o
  servidor revalida cada campo (datas `AAAA[-MM[-DD]]`, coordenadas válidas, enumerações) em `gossip/esquema.py`.
- **Precisão explícita.** Cada marco declara a precisão temporal e o grau geográfico. País, região e continente aparecem como
  área tracejada, não como ponto exato. Marcos sem lugar ficam fora do mapa.
- **Linha não é rota.** Os arcos mostram sequência cronológica. O traço muda conforme a relação declarada: tracejado para
  cronologia, contínuo para reprodução documentada, pontilhado para hipótese.
- **“Primeiro registro localizado”**, nunca “origem absoluta”.
- **Recusa** pedidos sobre vida privada de pessoas comuns, assédio ou acusações sem interesse público.
- **Limite de 3 a 9 marcos** e conclusão obrigatória com classificação, limites e perspectivas.

## Arquitetura

```
navegador (public/)                      servidor (server.py, só biblioteca padrão)
 ├─ index.html   console, mapa, HUD       ├─ GET /api/status        IA online/offline
 ├─ js/app.js    estado, eventos, dossiê  ├─ GET /api/casos         verificados + recentes
 ├─ js/mapa.js   D3: mapa, pontos, arcos  ├─ GET /api/casos/<id>    um dossiê
 └─ css/app.css  tema sala de operações   ├─ GET /api/investigar?q= SSE em tempo real
                                          └─ GET /api/tendencias    radar (cache; ?atualizar=1)
                                                 │
                                    gossip/investigador.py  laço Claude + web_search/web_fetch
                                    gossip/tendencias.py    radar de alegações em alta nas checagens
                                    gossip/checagens.py     cliente da Google Fact Check Tools API
                                    gossip/contas.py        cadastro, login e sessões (JSON local)
                                    gossip/avaliacoes.py    notas e comentários por investigação
                                    gossip/esquema.py       Case/Moment/Citation + validação
                                    gossip/prompts.py       prompt de sistema e ferramentas
                                    gossip/arquivo.py       leitura/gravação de dossiês
```

Eventos SSE: `fase`, `log`, `busca`, `fontes`, `marco`, `rejeitado`, `conclusao`, `recusa`, `erro`, `fim`. A reprodução de
arquivo emite os mesmos eventos, então os dois modos usam o mesmo código de interface.

## Configuração (`.env`)

| Variável | Padrão | Para quê |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Ativa a pesquisa por IA |
| `GOOGLE_FACTCHECK_KEY` | — | Opcional: base de checagens do Google (gratuita) no radar e nas investigações |
| `GD_MODELO` | `claude-opus-5-5` | Modelo |
| `GD_ESFORCO` | `high` | Profundidade de raciocínio (`low`…`max`); menor = mais rápido e barato |
| `GD_MAX_BUSCAS` / `GD_MAX_LEITURAS` | 15 / 8 | Teto de buscas e leituras de página por missão |
| `GD_SIMULTANEAS` | 2 | Missões ao mesmo tempo |
| `GD_HOST` / `GD_PORTA` | `127.0.0.1` / `8765` | Use `0.0.0.0` para abrir no celular pela rede local |
| `GD_FALLBACK` | `1` | Se o classificador de segurança recusar, um modelo de contingência continua |
| `GD_TENDENCIAS_HORAS` | `6` | Validade do radar de tendências antes de renovar |
| `GD_TENDENCIAS_BUSCAS` | `4` | Buscas na web por atualização do radar |
| `GD_TENDENCIAS_AUTO` | `1` | `0` desliga a renovação automática (só o botão ⟳ atualiza) |

**Custos:** cada missão faz várias chamadas ao modelo e até 15 buscas na web, cobradas na sua conta da Anthropic, e pode levar
alguns minutos. Para baratear e acelerar, reduza `GD_ESFORCO` e `GD_MAX_BUSCAS`.

## Privacidade

Tudo roda neste computador. As perguntas vão para a API da Anthropic (que executa as buscas); os dossiês ficam só em
`dados/investigacoes/`. Nada é enviado a outros servidores. O `.env` contém sua chave: não o compartilhe.

## Situação no roteiro (docs/ARQUITETURA_E_ROTEIRO.md)

- **Fase 1 (validar narrativa):** pronta para testes. Formulário de feedback e de contestação copiáveis no dossiê.
- **Fase 3 (busca real assistida por IA):** implementada, com auditoria automática de URLs. A revisão humana continua necessária.
- **Fase 2 (curadoria editorial)** e **Fase 4 (fórum, extensão, moderação):** ainda não implementadas.

Os dossiês verificados da versão 0.1 foram migrados para o esquema documentado. Eles ainda não têm trechos de suporte
transcritos, e o caso da Farsa Lunar se apoia numa única fonte secundária. Ambos os pontos estão indicados no próprio dossiê.
