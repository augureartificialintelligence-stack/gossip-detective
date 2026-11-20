/* GOSSIP DETECTIVE — controlador da central de comando.
   Os dois modos (IA ao vivo e reprodução de arquivo) alimentam os mesmos manipuladores
   de evento, então mapa, telemetria, cronograma e relatório se comportam igual nos dois. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const FASES = ["ingestao", "recuperacao", "verificacao", "cronologia", "sintese"];
  const DURACAO_REPRODUCAO = 12000; // hipótese de UX do documento de arquitetura (12 s)
  const CLASSIFICACAO = {
    confirmada: "CONFIRMADA", bem_documentada: "BEM DOCUMENTADA", parcialmente_verdadeira: "PARCIALMENTE VERDADEIRA",
    disputada: "DISPUTADA", refutada: "REFUTADA", inconclusiva: "INCONCLUSIVA", sem_registros_suficientes: "SEM REGISTROS SUFICIENTES",
  };
  // O relatório mostra sempre "?" no selo; a conclusão aparece só no fim da síntese, nestes quatro termos.
  const CONCLUSAO = {
    confirmada: "comprovado", bem_documentada: "comprovado", parcialmente_verdadeira: "tendencioso", disputada: "tendencioso",
    refutada: "refutado", inconclusiva: "inconclusivo", sem_registros_suficientes: "inconclusivo",
  };

  const S = {
    modo: "arquivo", iaDisponivel: false, usuario: null, verificados: [], recentes: [],
    fonte: null, reproducao: null, emCurso: false, tipoMissao: null,
    inicio: 0, cronometro: null, marcos: [], caso: null, ativoId: null,
    destaque: { finalId: null, origemId: null, ativoId: null }, timers: new Set(),
    trends: null, bombando: null, modoAcesso: "entrar",
  };
  const cartoes = new Map(); // id do marco -> cartão no cronograma documental
  const reduzMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------ cronologia (espelha gossip/esquema.py)

  function anoFracionario(data, fimDoPeriodo) {
    const m = /^(-?\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?$/.exec(data || "");
    if (!m) return null;
    const ano = +m[1];
    if (m[2] === undefined) return ano + (fimDoPeriodo ? 1 : 0);
    const mes = +m[2];
    if (m[3] === undefined) return ano + (mes - (fimDoPeriodo ? 0 : 1)) / 12;
    return ano + (mes - 1) / 12 + (+m[3] - 1) / 372;
  }
  function chaveCronologica(m) {
    const ini = anoFracionario(m.data_inicio, false);
    if (ini === null) return Infinity;
    let fim = m.data_fim ? anoFracionario(m.data_fim, true) : null;
    if (fim === null) {
      fim = anoFracionario(m.data_inicio, true);
      if (fim === null || fim === ini) return ini;
    }
    return (ini + fim) / 2;
  }
  const ordenar = (marcos) => [...marcos].sort((a, b) => chaveCronologica(a) - chaveCronologica(b) || a.seq - b.seq);
  const mapeavel = (m) => m.lat != null && m.lon != null;

  // ------------------------------------------------------------ utilidades de interface

  function el(tag, props = {}, ...filhos) {
    const n = Object.assign(document.createElement(tag), props);
    for (const f of filhos) if (f != null) n.append(f);
    return n;
  }
  function linkSeguro(url, texto) {
    try {
      const u = new URL(url);
      if (u.protocol === "http:" || u.protocol === "https:") {
        return el("a", { href: u.href, target: "_blank", rel: "noopener noreferrer", textContent: texto });
      }
    } catch (_) { /* URL inválida: mostra só o texto */ }
    return el("span", { textContent: texto });
  }
  function decifrar(alvo, texto) {
    if (reduzMovimento) { alvo.textContent = texto; return; }
    const glifos = "0123456789#%&@$*+=/<>ABCDEFGHJKLMNPQRSTUVXZ";
    let quadro = 0;
    clearInterval(alvo._decifrando);
    alvo._decifrando = setInterval(() => {
      quadro++;
      const revelados = Math.floor((quadro / 14) * texto.length);
      alvo.textContent = texto.split("").map((c, i) =>
        i < revelados || c === " " ? c : glifos[Math.floor(Math.random() * glifos.length)]).join("");
      if (revelados >= texto.length) clearInterval(alvo._decifrando);
    }, 32);
  }
  function salto(id, valor) {
    const n = $(id);
    n.textContent = valor;
    n.classList.remove("salto"); void n.offsetWidth; n.classList.add("salto");
  }
  const doisDigitos = (n) => String(n).padStart(2, "0");
  function tempoMissao() {
    const s = Math.floor((Date.now() - S.inicio) / 1000);
    return `${doisDigitos(Math.floor(s / 60))}:${doisDigitos(s % 60)}`;
  }
  const dataCurta = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(+d) ? "" : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).replace(/\./g, "");
  };
  const normalizar = (t) => (t || "").toLocaleLowerCase("pt-BR").normalize("NFD")
    .replace(/[̀-ͯ]/g, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();

  /** fetch para a API; uma resposta 401 (sessão ausente ou vencida) devolve o usuário à tela de acesso. */
  async function api(caminho, opcoes) {
    if (S.demo) return respostaDemo(caminho);
    const resp = await fetch(caminho, opcoes);
    if (resp.status === 401) {
      mostrarAcesso("entrar", "Sua sessão terminou. Entre de novo para continuar.");
      throw new Error("sessão");
    }
    return resp;
  }

  // ------------------------------------------------------------ versão de demonstração (GitHub Pages, sem servidor)

  /** Sem servidor, as rotas de leitura vêm do retrato estático em demo/ (gerado por ferramentas/gerar_demo.py). */
  function respostaDemo(caminho) {
    const rota = caminho.split("?")[0];
    if (rota === "api/avaliacoes") {
      return new Response(JSON.stringify({ media: null, total: 0, minha: null, comentarios: [] }),
        { headers: { "Content-Type": "application/json" } });
    }
    return fetch(rota.startsWith("api/casos/") ? `demo/casos/${rota.slice("api/casos/".length)}.json` : `demo/${rota.slice(4)}.json`);
  }

  async function detectarDemo() {
    try { if ((await fetch("api/status")).ok) return false; } catch (_) { /* sem servidor */ }
    try { return (await fetch("demo/status.json")).ok; } catch (_) { return false; }
  }

  // ------------------------------------------------------------ acesso (cadastro e login locais)

  function bloquearFundo(bloquear) {
    document.querySelectorAll("body > header, body > main, body > footer").forEach((n) => (n.inert = bloquear));
  }

  function modoAcesso(modo) {
    S.modoAcesso = modo;
    const cadastro = modo === "cadastrar";
    $("abaEntrar").setAttribute("aria-selected", String(!cadastro));
    $("abaCadastrar").setAttribute("aria-selected", String(cadastro));
    $("campoNome").classList.toggle("hidden", !cadastro);
    $("acSenha").autocomplete = cadastro ? "new-password" : "current-password";
    $("acSenha").placeholder = cadastro ? "mínimo de 8 caracteres" : "";
    $("btnAcesso").textContent = cadastro ? "CRIAR CONTA" : "ENTRAR";
    $("acessoErro").textContent = "";
  }

  function mostrarAcesso(modo, mensagem = "") {
    fecharMenu();
    modoAcesso(modo);
    $("acessoErro").textContent = mensagem;
    $("acesso").classList.remove("hidden");
    bloquearFundo(true);
    (modo === "cadastrar" ? $("acNome") : $("acEmail")).focus();
  }

  async function enviarAcesso(e) {
    e.preventDefault();
    const cadastro = S.modoAcesso === "cadastrar";
    const corpo = { email: $("acEmail").value.trim(), senha: $("acSenha").value };
    if (cadastro) corpo.nome = $("acNome").value.trim();
    const botao = $("btnAcesso");
    botao.disabled = true;
    try {
      const resp = await fetch(cadastro ? "api/cadastro" : "api/login", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo),
      });
      const dados = await resp.json();
      if (!resp.ok) { $("acessoErro").textContent = dados.erro || "Não foi possível entrar."; return; }
      $("acSenha").value = "";
      await entrarNaCentral(dados.usuario);
    } catch (_) {
      $("acessoErro").textContent = "Servidor indisponível. Abra a central pelo iniciar.bat.";
    } finally {
      botao.disabled = false;
    }
  }

  async function entrarNaCentral(usuario) {
    S.usuario = usuario;
    $("acesso").classList.add("hidden");
    bloquearFundo(false);
    $("contaNome").textContent = usuario.nome.split(" ")[0];
    $("contaAvatar").textContent = usuario.nome.trim().charAt(0).toUpperCase();
    $("conta").title = usuario.email;
    $("conta").classList.remove("hidden");
    $("btnSair").classList.toggle("hidden", S.demo);
    await Promise.all([carregarCasos(), carregarBombando(), S.mapaPronto]);
    carregarTendencias();
    clearInterval(S.bombandoTimer);
    S.bombandoTimer = setInterval(carregarBombando, 60000); // traz as pesquisas novas de outros usuários
    const id = new URLSearchParams(location.search).get("caso");
    if (id && !S.emCurso) abrirCaso(id);
  }

  async function sair() {
    try { await fetch("api/logout", { method: "POST" }); } catch (_) { /* recarrega mesmo assim */ }
    location.replace(location.pathname);
  }

  // ------------------------------------------------------------ status, histórico e modo

  async function carregarStatus() {
    const sys = $("sysStatus");
    try {
      const st = await (await fetch(S.demo ? "demo/status.json" : "api/status")).json();
      S.iaDisponivel = st.ia_disponivel;
      sys.className = `sys ${st.ia_disponivel || S.demo ? "on" : "off"}`;
      sys.title = S.demo ? "Versão de demonstração"
        : st.ia_disponivel ? "Sistemas online" : "IA offline: só arquivos (configure ANTHROPIC_API_KEY no .env)";
      if (!st.ia_disponivel) document.querySelector('.mode[data-modo="ia"]').title = "Indisponível: configure ANTHROPIC_API_KEY no .env";
    } catch (_) {
      sys.className = "sys off";
      sys.title = "Servidor não encontrado";
      $("avisoModo").textContent = "Abra a central pelo servidor local (iniciar.bat ou python server.py), não pelo arquivo HTML direto.";
    }
    document.querySelector('.mode[data-modo="ia"]').disabled = !S.iaDisponivel;
    definirModo(S.iaDisponivel ? "ia" : "arquivo");
  }

  async function carregarCasos() {
    try {
      const dados = await (await api("api/casos")).json();
      S.verificados = dados.verificados;
      S.recentes = dados.recentes;
    } catch (_) { return; }
    const item = (titulo, detalhe, dica, abrir) => {
      const b = el("button", { type: "button", className: "ml-item", title: dica },
        el("span", { className: "ml-titulo", textContent: titulo }),
        detalhe ? el("span", { className: "ml-meta", textContent: detalhe }) : null);
      b.dataset.busca = normalizar(`${titulo} ${dica}`);
      b.onclick = () => { fecharMenu(); abrir(); };
      b.disabled = S.emCurso;
      return el("li", {}, b);
    };
    const vazio = (texto) => el("li", { className: "ml-vazio", textContent: texto });
    $("listaRecentes").replaceChildren(...(S.recentes.length
      ? S.recentes.map((r) => item(r.titulo, dataCurta(r.criado_em), r.pergunta, () => abrirCaso(r.id)))
      : [vazio("Nenhuma missão ainda.")]));
    $("listaVerificados").replaceChildren(...S.verificados.map((c) => item(c.rotulo, "", c.pergunta,
      () => { definirModo("arquivo"); $("pergunta").value = c.rotulo; reproduzir(c); })));
    $("historicoN").textContent = String(S.recentes.length);
    $("verificadosN").textContent = String(S.verificados.length);
    $("menuN").textContent = String(S.recentes.length);
    $("menuN").classList.toggle("hidden", !S.recentes.length);
    filtrarMenu();
  }

  function definirModo(modo) {
    if (S.emCurso) return;
    S.modo = modo;
    document.querySelectorAll(".mode").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.modo === modo)));
    $("avisoModo").textContent = "";
  }

  // ------------------------------------------------------------ menu lateral (histórico e dossiês)

  function abrirMenu() {
    const menu = $("menuLateral");
    menu.inert = false;
    menu.classList.add("aberto");
    $("veu").classList.remove("hidden");
    $("btnMenu").setAttribute("aria-expanded", "true");
    $("filtroMenu").focus();
  }

  function fecharMenu() {
    const menu = $("menuLateral");
    if (!menu.classList.contains("aberto")) return;
    menu.classList.remove("aberto");
    menu.inert = true;
    $("veu").classList.add("hidden");
    $("btnMenu").setAttribute("aria-expanded", "false");
    $("btnMenu").focus();
  }

  function filtrarMenu() {
    const q = normalizar($("filtroMenu").value);
    document.querySelectorAll("#menuLateral .ml-item").forEach((b) => {
      b.parentElement.classList.toggle("hidden", Boolean(q) && !b.dataset.busca.includes(q));
    });
  }

  // ------------------------------------------------------------ faixas rolantes: Trends e Bombando

  /** Monta uma faixa em rolagem contínua da direita para a esquerda (estilo cotação). A lista é repetida até
      cobrir a largura e duplicada para o laço não ter emenda. Pausa só com o mouse em cima ou foco de teclado. */
  function montarTicker(alvo, criarItens) {
    const grupo = el("div", { className: "ticker-grupo" }, ...criarItens(false));
    const trilho = el("div", { className: "ticker-trilho" }, grupo);
    alvo.replaceChildren(trilho);
    for (let i = 0; i < 8 && grupo.offsetWidth < alvo.clientWidth * 1.2; i++) grupo.append(...criarItens(true));
    const copia = el("div", { className: "ticker-grupo" }, ...criarItens(true));
    while (copia.childElementCount < grupo.childElementCount) copia.append(...criarItens(true));
    copia.setAttribute("aria-hidden", "true");
    trilho.append(copia);
    trilho.style.setProperty("--duracao", `${Math.max(14, grupo.offsetWidth / 60).toFixed(1)}s`); // ~60 px/s
    trilho.classList.add("rolando");
  }

  function itemFaixa(texto, dica, repetido, aoClicar, prefixo) {
    const b = el("button", { type: "button", className: "ticker-item", title: dica },
      prefixo ? el("b", { textContent: prefixo }) : null, texto);
    if (repetido) b.tabIndex = -1;
    b.disabled = S.emCurso;
    b.onclick = aoClicar;
    return b;
  }

  function carregarNaBarra(texto) {
    if (S.emCurso) return;
    $("pergunta").value = texto;
    if (S.iaDisponivel) definirModo("ia");
    if (S.demo) $("avisoModo").textContent = "Na demonstração a pesquisa ao vivo por IA está desativada; esta alegação pode ser investigada na versão completa.";
    $("pergunta").focus();
  }

  const mensagemFaixa = (alvo, texto, pulsando) =>
    alvo.replaceChildren(el("span", { className: `ticker-msg${pulsando ? " pulsando" : ""}`, textContent: texto }));

  async function carregarTendencias(forcar = false) {
    clearTimeout(S.trendsTimer);
    let d;
    try {
      d = await (await api(`api/tendencias${forcar ? "?atualizar=1" : ""}`)).json();
    } catch (_) { return; }
    S.trends = d;
    renderizarTendencias();
    if (d.atualizando) S.trendsTimer = setTimeout(() => carregarTendencias(), 5000);
  }

  function renderizarTendencias() {
    const d = S.trends;
    if (!d) return;
    const alvo = $("tickerTrends");
    $("btnTrends").classList.toggle("girando", d.atualizando);
    $("btnTrends").disabled = d.atualizando || !d.ia_disponivel;
    const top = d.itens.slice(0, 3);
    if (!top.length) {
      mensagemFaixa(alvo, d.atualizando ? "VARRENDO AGÊNCIAS DE CHECAGEM…"
        : d.erro ? "Trends indisponíveis no momento."
        : !d.ia_disponivel ? "Configure a IA para ativar os trends." : "Clique em TRENDS para atualizar.", d.atualizando);
      return;
    }
    montarTicker(alvo, (repetido) => top.map((t, i) =>
      itemFaixa(t.alegacao, `${t.agencia} · ${dataCurta(t.data + "T12:00:00")}`, repetido, () => carregarNaBarra(t.alegacao), `#${i + 1}`)));
  }

  /** Pesquisas feitas na central. Só remonta a faixa quando a lista muda, para a rolagem não dar saltos. */
  async function carregarBombando() {
    let itens;
    try {
      itens = (await (await api("api/bombando")).json()).itens;
    } catch (_) { return; }
    if (JSON.stringify(itens) === JSON.stringify(S.bombando)) return;
    S.bombando = itens;
    renderizarBombando();
  }

  function renderizarBombando() {
    const itens = S.bombando || [];
    const alvo = $("tickerBombando");
    if (!itens.length) { mensagemFaixa(alvo, "As pesquisas feitas na central aparecem aqui."); return; }
    // Abrir uma pesquisa do Bombando reproduz a investigação já feita: sem custo e com as avaliações dela.
    montarTicker(alvo, (repetido) => itens.map((b) => itemFaixa(b.pergunta,
      b.origem === "sugestao" ? "Abrir dossiê verificado" : `Abrir investigação${b.total > 1 ? ` · pesquisada ${b.total} vezes nos últimos 7 dias` : ""}`,
      repetido, () => !S.emCurso && abrirCaso(b.caso_id), b.total > 1 ? `${b.total}×` : "")));
  }

  // ------------------------------------------------------------ ciclo da missão

  function prepararMissao(tipo, pergunta) {
    encerrarFluxos();
    S.emCurso = true;
    S.tipoMissao = tipo;
    S.marcos = [];
    S.caso = null;
    S.ativoId = null;
    S.destaque = { finalId: null, origemId: null, ativoId: null };
    ["tBuscas", "tFontes", "tMarcos", "tRejeitados"].forEach((id) => ($(id).textContent = "0"));
    limparCatalogo("Varredura em curso…");
    $("dossie").classList.add("hidden");
    $("btnAlternar").classList.add("hidden");
    disporVista(false);
    $("dataAtual").textContent = "-- --- ----";
    $("localAtual").textContent = "Rastreando…";
    Mapa.limpar();
    Mapa.varrer(true);
    fase(null);

    $("radar").classList.add("ativo");
    const hud = $("hudModo");
    hud.className = `hud-modo ${tipo === "ia" ? "" : "reproducao"}`;
    hud.textContent = tipo === "ia" ? "● AO VIVO" : "▶ REPRODUÇÃO";
    $("mapaEstado").textContent = "RASTREANDO";
    $("mapaEstado").className = "tag ativo";
    const barra = $("barra");
    barra.classList.toggle("indeterminada", tipo === "ia");
    barra.firstElementChild.style.width = "0%";

    $("btnIniciar").classList.add("hidden");
    $("btnAbortar").classList.remove("hidden");
    $("btnPular").classList.toggle("hidden", tipo === "ia");
    $("pergunta").disabled = true;
    document.querySelectorAll(".mode, .ml-item, .ticker-item").forEach((b) => (b.disabled = true));

    S.inicio = Date.now();
    clearInterval(S.cronometro);
    S.cronometro = setInterval(() => ($("cronometro").textContent = `T+${tempoMissao()}`), 500);
    status(tipo === "ia" ? `Missão aberta: “${pergunta}”` : "Abrindo dossiê verificado…");
  }

  function encerrarMissao(estadoMapa, classeTag) {
    S.emCurso = false;
    encerrarFluxos();
    clearInterval(S.cronometro);
    Mapa.varrer(false);
    if (!cartoes.size) limparCatalogo("Nenhum registro nesta missão.");
    $("radar").classList.remove("ativo");
    $("hudModo").classList.add("hidden");
    $("mapaEstado").textContent = estadoMapa;
    $("mapaEstado").className = `tag ${classeTag}`;
    $("barra").classList.remove("indeterminada");
    $("btnIniciar").classList.remove("hidden");
    $("btnAbortar").classList.add("hidden");
    $("btnPular").classList.add("hidden");
    $("pergunta").disabled = false;
    document.querySelectorAll(".ml-item, .ticker-item").forEach((b) => (b.disabled = false));
    document.querySelectorAll(".mode").forEach((b) => (b.disabled = b.dataset.modo === "ia" && !S.iaDisponivel));
  }

  function encerrarFluxos() {
    if (S.fonte) { S.fonte.close(); S.fonte = null; }
    if (S.reproducao) { S.reproducao.forEach(clearTimeout); S.reproducao = null; }
  }

  function status(texto) { $("statusLinha").textContent = texto; }

  function fase(nome) {
    const idx = FASES.indexOf(nome);
    document.querySelectorAll("#fases li").forEach((li, i) => {
      li.classList.toggle("feita", idx >= 0 && i < idx);
      li.classList.toggle("atual", idx >= 0 && i === idx);
    });
  }

  // ------------------------------------------------------------ manipuladores de evento (IA e arquivo)

  const manipular = {
    fase: (d) => fase(d.fase),
    busca: (d) => {
      salto("tBuscas", d.total);
      Mapa.rajada(8);
      status(`Varredura: ${d.consulta}`);
    },
    fontes: (d) => salto("tFontes", d.total),
    rejeitado: (d) => salto("tRejeitados", d.total),
    marco: (m) => {
      S.marcos.push(m);
      salto("tMarcos", S.marcos.length);
      status(`Registro validado: ${m.titulo}`);
      mostrarTemporal(m);
      redesenhar({ ativoId: m.id });
      Mapa.convergir(m.id);
      Mapa.enquadrar(null, 1100);
      catalogar(m, true);
      if (S.tipoMissao !== "ia") {
        const total = S.reproducaoTotal || 1;
        $("barra").firstElementChild.style.width = `${Math.round((S.marcos.length / total) * 100)}%`;
      }
    },
    conclusao: (caso) => concluir(caso),
    recusa: (d) => {
      status("Pedido fora do escopo do GOSSIP DETECTIVE.");
      fase(null);
      encerrarMissao("MISSÃO RECUSADA", "alerta");
      $("avisoModo").textContent = d.motivo;
    },
    erro: (d) => {
      status(d.mensagem);
      encerrarMissao(S.marcos.length ? "MISSÃO INTERROMPIDA" : "FALHA NA MISSÃO", "alerta");
      if (S.marcos.length) finalizarMapa();
    },
    fim: () => { if (S.emCurso) encerrarMissao("MISSÃO ENCERRADA", "ok"); },
  };

  function redesenhar(extra = {}) {
    Object.assign(S.destaque, extra);
    Mapa.desenhar(ordenar(S.marcos), extra);
    atualizarCatalogo();
  }

  function extremos() {
    const mapeados = ordenar(S.marcos).filter(mapeavel);
    return {
      origemId: mapeados.length > 1 ? mapeados[0].id : null,
      finalId: mapeados.length ? mapeados[mapeados.length - 1].id : null,
    };
  }

  function finalizarMapa() {
    const ext = extremos();
    S.ativoId = ext.finalId;
    redesenhar({ ...ext, ativoId: ext.finalId });
    Mapa.enquadrar(null, 1500);
    const final = S.marcos.find((m) => m.id === ext.finalId);
    if (final) {
      mostrarTemporal(final);
      const hud = $("hudModo");
      hud.classList.remove("hidden", "reproducao");
      hud.textContent = `◉ ALVO FINAL · ${final.local.toUpperCase()}`;
    }
  }

  function concluir(caso) {
    S.caso = caso;
    S.marcos = caso.marcos.slice();
    // Rastros ainda em voo terminam a animação; os que faltarem entram direto no cronograma.
    for (const m of S.marcos) catalogar(m, false);
    fase("sintese");
    $("barra").firstElementChild.style.width = "100%";
    status(S.tipoMissao === "ia" ? "Investigação concluída." : "Reprodução concluída.");
    encerrarMissao("CASO REVELADO", "ok");
    finalizarMapa(); // depois de encerrar a missão, que esconde o HUD de "ao vivo"
    renderizarDossie(caso);
    // O alvo final fica alguns segundos travado na tela antes de o relatório assumir a vista principal.
    agendar(promoverRelatorio, reduzMovimento ? 0 : 2600);
    if (caso.origem === "ia") {
      history.replaceState(null, "", `?caso=${encodeURIComponent(caso.id)}`);
      carregarCasos();
      carregarBombando();
    }
  }

  function mostrarTemporal(m) {
    decifrar($("dataAtual"), m.data_exibicao);
    $("localAtual").textContent = m.local;
  }

  function selecionar(id) {
    const m = S.marcos.find((x) => x.id === id);
    if (!m) return;
    S.ativoId = id;
    const ext = S.caso ? extremos() : {};
    redesenhar({ ...ext, ativoId: id });
    mostrarTemporal(m);
    if (mapeavel(m)) Mapa.focar(id);
    const cartao = cartoes.get(id);
    if (cartao) {
      rolarCatalogo(cartao);
      cartao.animate([{ background: "#ff343430" }, { background: "#030a0e" }], { duration: 1200 });
    }
  }

  // ------------------------------------------------------------ disposição da tela (mapa ou relatório na vista principal)

  /** Reorganiza a grade; cada painel desliza da posição antiga para a nova (FLIP). Rola até `foco`, se houver. */
  function disporVista(relatorioNoTopo, foco) {
    const principal = document.querySelector("main.console");
    $("btnAlternar").textContent = relatorioNoTopo ? "⇅ MAPA EM DESTAQUE" : "⇅ RELATÓRIO EM DESTAQUE";
    if (principal.classList.contains("concluida") === relatorioNoTopo) return;
    const paineis = [...principal.children].filter((p) => p.offsetParent);
    const antes = paineis.map((p) => p.getBoundingClientRect());
    principal.classList.toggle("concluida", relatorioNoTopo);
    const depois = paineis.map((p) => p.getBoundingClientRect());
    if (foco) {
      window.scrollTo({ top: foco.getBoundingClientRect().top + scrollY - 16, behavior: reduzMovimento ? "auto" : "smooth" });
    }
    if (reduzMovimento) return;
    paineis.forEach((p, i) => {
      const dx = antes[i].left - depois[i].left, dy = antes[i].top - depois[i].top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      p.animate([{ transform: `translate(${dx}px,${dy}px)` }, { transform: "none" }],
        { duration: 750, easing: "cubic-bezier(.3,0,.2,1)" });
    });
  }

  function promoverRelatorio() {
    // Rastros ainda em voo pousam no cronograma antes de a tela se reorganizar.
    if ([...cartoes.values()].some((li) => li.classList.contains("pendente"))) { agendar(promoverRelatorio, 400); return; }
    disporVista(true, $("dossie"));
    $("btnAlternar").classList.remove("hidden");
    $("catalogo").scrollTo({ top: 0, behavior: reduzMovimento ? "auto" : "smooth" }); // leitura começa no registro 01
  }

  // ------------------------------------------------------------ cronograma documental (painel à direita do mapa)

  function agendar(fn, ms) {
    const t = setTimeout(() => { S.timers.delete(t); fn(); }, ms);
    S.timers.add(t);
  }

  function cancelarVoos() {
    S.timers.forEach(clearTimeout);
    S.timers.clear();
    document.querySelectorAll(".pacote, .feixe").forEach((n) => n.remove());
  }

  function limparCatalogo(textoVazio) {
    cancelarVoos();
    cartoes.clear();
    $("catalogo").replaceChildren(el("li", { className: "vazio", textContent: textoVazio }));
  }

  /** Cartão recolhido: número, data e título. O título expande o texto do registro e o link da fonte. */
  function criarCartao(m) {
    const corpo = el("div", { className: "r-corpo" },
      m.texto ? el("p", { textContent: m.texto }) : null,
      el("div", { className: "r-fonte" }, linkSeguro(m.fonte.url, `${m.fonte.entidade} ↗`)));
    corpo.hidden = true;
    const cab = el("button", { type: "button", className: "r-cab" },
      el("span", { className: "r-num" }),
      el("span", { className: "r-data", textContent: m.data_exibicao }),
      el("span", { className: "r-titulo", textContent: m.titulo }),
      el("i", { className: "r-seta", textContent: "▸", ariaHidden: "true" }));
    cab.setAttribute("aria-expanded", "false");
    const li = el("li", { className: "rastro pendente" },
      el("div", { className: "r-recebendo", textContent: "◇ RECEBENDO RASTRO DO MAPA…" }), cab, corpo);
    cab.onclick = () => {
      const abrir = corpo.hidden;
      corpo.hidden = !abrir;
      cab.setAttribute("aria-expanded", String(abrir));
      li.classList.toggle("aberto", abrir);
      selecionar(m.id);
    };
    li.dataset.id = m.id;
    return li;
  }

  /** Insere o registro na posição cronológica. Com animação, ele espera o voo vindo do mapa. */
  function catalogar(m, animar) {
    if (cartoes.has(m.id)) return;
    const lista = $("catalogo");
    lista.querySelector(".vazio")?.remove();
    const li = criarCartao(m);
    cartoes.set(m.id, li);
    const ids = ordenar(S.marcos).map((x) => x.id).filter((id) => cartoes.has(id));
    const proximo = ids[ids.indexOf(m.id) + 1];
    lista.insertBefore(li, proximo ? cartoes.get(proximo) : null);
    numerar();
    atualizarCatalogo();
    if (!animar || reduzMovimento) { revelar(li); return; }
    rolarCatalogo(li);
    // Espera a câmera do mapa terminar de enquadrar o novo ponto antes do voo.
    agendar(() => voar(m, li), mapeavel(m) ? 1150 : 250);
  }

  function numerar() {
    const ordem = new Map(ordenar(S.marcos).map((m, i) => [m.id, i + 1]));
    cartoes.forEach((li, id) => (li.querySelector(".r-num").textContent = doisDigitos(ordem.get(id) || 0)));
  }

  function rolarCatalogo(li) {
    const lista = $("catalogo");
    const topo = li.offsetTop, base = topo + li.offsetHeight;
    if (topo < lista.scrollTop || base > lista.scrollTop + lista.clientHeight) {
      lista.scrollTo({ top: Math.max(0, topo - 8), behavior: reduzMovimento ? "auto" : "smooth" });
    }
  }

  /** Pacote de dados voa do ponto no mapa até o cartão, que então se revela. */
  function voar(m, li) {
    if (!li.isConnected) return;
    const alvo = li.getBoundingClientRect();
    const origem = mapeavel(m) ? Mapa.pontoNaTela(m.id) : null;
    const alvoVisivel = alvo.bottom > 0 && alvo.top < innerHeight && alvo.right > 0 && alvo.left < innerWidth;
    if (!origem || !alvoVisivel) { revelar(li); return; }

    const x1 = alvo.left + 22, y1 = alvo.top + 16;
    const cx = (origem.x + x1) / 2, cy = Math.min(origem.y, y1) - 90;
    const NS = "http://www.w3.org/2000/svg";
    const feixe = document.createElementNS(NS, "svg");
    feixe.setAttribute("class", "feixe");
    feixe.setAttribute("aria-hidden", "true");
    const trilha = document.createElementNS(NS, "path");
    trilha.setAttribute("d", `M${origem.x},${origem.y} Q${cx},${cy} ${x1},${y1}`);
    feixe.append(trilha);
    const pacote = el("div", { className: "pacote" }, el("i"), el("span", { textContent: li.querySelector(".r-num").textContent }));
    pacote.setAttribute("aria-hidden", "true");
    document.body.append(feixe, pacote);

    const comprimento = trilha.getTotalLength();
    trilha.style.strokeDasharray = comprimento;
    const DURACAO = 950;
    trilha.animate([{ strokeDashoffset: comprimento }, { strokeDashoffset: 0 }],
      { duration: DURACAO, easing: "cubic-bezier(.45,0,.25,1)", fill: "forwards" });
    const quadros = [];
    for (let i = 0; i <= 16; i++) {
      const t = i / 16, u = 1 - t;
      const x = u * u * origem.x + 2 * u * t * cx + t * t * x1;
      const y = u * u * origem.y + 2 * u * t * cy + t * t * y1;
      quadros.push({ transform: `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) scale(${(1 + Math.sin(Math.PI * t) * 0.4).toFixed(2)})` });
    }
    li.classList.add("mirando");
    pacote.animate(quadros, { duration: DURACAO, easing: "cubic-bezier(.45,0,.25,1)" }).onfinish = () => {
      pacote.remove();
      feixe.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 600 }).onfinish = () => feixe.remove();
      revelar(li);
    };
  }

  function revelar(li) {
    if (!li.classList.contains("pendente")) return;
    li.classList.remove("pendente", "mirando");
    li.classList.add("catalogado");
    const data = li.querySelector(".r-data");
    decifrar(data, data.textContent);
  }

  function revelarTodos() {
    cancelarVoos();
    cartoes.forEach(revelar);
  }

  function atualizarCatalogo() {
    const { finalId, origemId, ativoId } = S.destaque;
    cartoes.forEach((li, id) => {
      li.classList.toggle("final", id === finalId);
      li.classList.toggle("origem", id === origemId && id !== finalId);
      li.classList.toggle("ativo", id === ativoId);
    });
  }

  // ------------------------------------------------------------ modo IA

  function iniciarIA(pergunta) {
    prepararMissao("ia", pergunta);
    const fonte = new EventSource(`api/investigar?q=${encodeURIComponent(pergunta)}`);
    S.fonte = fonte;
    for (const nome of Object.keys(manipular)) {
      fonte.addEventListener(nome, (e) => {
        let dados = {};
        try { dados = JSON.parse(e.data || "{}"); } catch (_) { return; }
        manipular[nome](dados);
      });
    }
    // EventSource tenta reconectar sozinho; aqui isso reiniciaria a missão, então fechamos.
    fonte.onerror = async () => {
      if (S.fonte !== fonte) return;
      fonte.close();
      S.fonte = null;
      if (S.emCurso) manipular.erro({ mensagem: "Conexão com a central perdida." });
      try { await api("api/casos"); } catch (_) { /* api() já reabre a tela de acesso se a sessão caiu */ }
    };
  }

  // ------------------------------------------------------------ modo arquivo (reprodução)

  function reproduzir(caso) {
    prepararMissao("reproducao", caso.pergunta);
    const marcos = [...caso.marcos].sort((a, b) => a.seq - b.seq);
    S.reproducaoTotal = marcos.length;
    const passo = DURACAO_REPRODUCAO / (marcos.length + 1);
    const eventos = [[0, "fase", { fase: "ingestao" }], [600, "fase", { fase: "recuperacao" }]];
    marcos.forEach((m, i) => {
      const t = passo * (i + 0.6);
      if (i === 0) eventos.push([t + 200, "fase", { fase: "verificacao" }]);
      if (i === 1) eventos.push([t + 200, "fase", { fase: "cronologia" }]);
      eventos.push([t + passo * 0.4, "marco", m]);
    });
    eventos.push([DURACAO_REPRODUCAO, "conclusao", caso]);

    S.reproducao = eventos.map(([t, nome, dados]) => setTimeout(() => manipular[nome](dados), t));
    S.pular = () => {
      encerrarFluxos();
      revelarTodos();
      concluir(caso);
    };
  }

  async function abrirCaso(id) {
    try {
      const resp = await api(`api/casos/${encodeURIComponent(id)}`);
      if (!resp.ok) throw new Error();
      const caso = await resp.json();
      definirModo("arquivo");
      $("pergunta").value = caso.pergunta;
      reproduzir(caso);
    } catch (erro) {
      if (erro.message !== "sessão") $("avisoModo").textContent = "Dossiê não encontrado neste computador.";
    }
  }

  function iniciarArquivo(pergunta) {
    const q = normalizar(pergunta);
    const achado = S.verificados.find((c) => [c.rotulo, c.pergunta, c.titulo].some((t) => normalizar(t) === q));
    if (achado) { reproduzir(achado); return; }
    $("avisoModo").textContent = S.demo
      ? "Na demonstração a pesquisa ao vivo por IA está desativada. Abra um dossiê pelo Bombando ou pelo menu ☰."
      : S.iaDisponivel
      ? `Não há dossiê verificado para “${pergunta}”. Mude para IA AO VIVO para investigar agora.`
      : `Não há dossiê verificado para “${pergunta}”, e a IA não está configurada. Nenhum rastro foi inventado.`;
  }

  // ------------------------------------------------------------ relatório

  function renderizarDossie(c) {
    $("dossie").classList.remove("hidden");
    $("vPergunta").textContent = c.pergunta;
    $("vTitulo").textContent = c.titulo;
    renderizarLinhaSintese(c);
    $("vPerspectivas").replaceChildren(...(c.perspectivas || []).map((p) =>
      el("div", {}, el("h4", { textContent: p.titulo }), el("p", { textContent: p.texto }))));
    $("vLimites").textContent = c.limites;
    $("vConsultadas").replaceChildren(...(c.fontes_consultadas || []).map((f) => el("li", {}, linkSeguro(f.url, f.titulo || f.url))));
    $("vConsultadasBox").open = false;
    $("acaoStatus").textContent = "";
    S.avalCaso = c.id;
    S.avalNota = 0;
    $("avalComentario").value = "";
    $("avalStatus").textContent = "";
    $("btnAvaliar").textContent = "ENVIAR AVALIAÇÃO";
    pintarEstrelas(0);
    $("avalMedia").textContent = "";
    $("comentarios").replaceChildren();
    carregarAvaliacoes(c.id);
  }

  /** Síntese em linha do tempo: cada data do cronograma vira um pequeno título com o texto do registro,
      e o último passo é a conclusão do caso (veredito + classificação). Clicar numa data localiza o registro. */
  function renderizarLinhaSintese(c) {
    const conclusao = CONCLUSAO[c.classificacao] || "inconclusivo";
    const fecho = ((c.marcos.length ? c.veredito : c.sintese) || "").trim();
    const passos = ordenar(c.marcos).map((m) => {
      const data = el("button", { type: "button", className: "ls-data", textContent: m.data_exibicao, title: "Localizar no mapa" });
      data.onclick = () => selecionar(m.id);
      return el("li", {}, el("h4", {}, data), el("p", { textContent: m.texto || m.titulo }));
    });
    const fim = el("li", { className: "ls-fim" },
      el("h4", {}, el("span", { className: "ls-data", textContent: "CONCLUSÃO" })),
      el("p", {}, fecho ? `${fecho}${/[.!?…]$/.test(fecho) ? "" : "."} ` : "",
        el("b", { className: `conclusao conc-${conclusao}`, textContent: `Conclusão: ${conclusao}.` })));
    $("vLinha").replaceChildren(...passos, fim);
  }

  // ------------------------------------------------------------ avaliação e comentários

  function pintarEstrelas(nota) {
    document.querySelectorAll("#estrelas button").forEach((b) => {
      b.classList.toggle("acesa", +b.dataset.nota <= nota);
      b.setAttribute("aria-checked", String(+b.dataset.nota === S.avalNota));
    });
  }

  async function carregarAvaliacoes(casoId) {
    try {
      const d = await (await api(`api/avaliacoes?caso=${encodeURIComponent(casoId)}`)).json();
      if (S.avalCaso === casoId) renderizarAvaliacoes(d);
    } catch (_) { /* sem avaliações visíveis */ }
  }

  function renderizarAvaliacoes(d) {
    $("formAvaliacao").hidden = S.demo;
    if (S.demo) { $("avalMedia").textContent = "Avaliações e comentários funcionam na versão completa, com login."; return; }
    $("avalMedia").textContent = d.total
      ? `★ ${d.media.toLocaleString("pt-BR")} · ${d.total} ${d.total === 1 ? "avaliação" : "avaliações"}`
      : "Seja o primeiro a avaliar";
    if (d.minha) {
      S.avalNota = d.minha.nota;
      $("avalComentario").value = d.minha.comentario;
      $("btnAvaliar").textContent = "ATUALIZAR AVALIAÇÃO";
    }
    pintarEstrelas(S.avalNota);
    $("comentarios").replaceChildren(...d.comentarios.map((c) => el("li", { className: c.meu ? "meu" : "" },
      el("div", { className: "com-cab" },
        el("b", { textContent: c.meu ? `${c.nome} (você)` : c.nome }),
        el("span", { className: "com-nota", textContent: "★".repeat(c.nota) + "☆".repeat(5 - c.nota), ariaLabel: `${c.nota} de 5` }),
        el("span", { className: "com-data", textContent: dataCurta(c.data) })),
      el("p", { textContent: c.comentario }))));
  }

  async function enviarAvaliacao(e) {
    e.preventDefault();
    if (!S.avalCaso) return;
    if (!S.avalNota) { $("avalStatus").textContent = "Escolha de 1 a 5 estrelas."; return; }
    $("btnAvaliar").disabled = true;
    try {
      const resp = await api("api/avaliacoes", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caso: S.avalCaso, nota: S.avalNota, comentario: $("avalComentario").value }),
      });
      const d = await resp.json();
      if (!resp.ok) { $("avalStatus").textContent = d.erro || "Não foi possível enviar."; return; }
      renderizarAvaliacoes(d);
      $("avalStatus").textContent = "Obrigado! Sua avaliação foi registrada.";
    } catch (_) {
      /* api() já trata sessão vencida */
    } finally {
      $("btnAvaliar").disabled = false;
    }
  }

  function ligarAvaliacao() {
    document.querySelectorAll("#estrelas button").forEach((b) => {
      b.onclick = () => { S.avalNota = +b.dataset.nota; pintarEstrelas(S.avalNota); $("avalStatus").textContent = ""; };
      b.onmouseenter = () => pintarEstrelas(+b.dataset.nota);
    });
    $("estrelas").onmouseleave = () => pintarEstrelas(S.avalNota);
    $("formAvaliacao").onsubmit = enviarAvaliacao;
  }

  // ------------------------------------------------------------ ações do relatório

  async function copiar(texto) {
    try {
      await navigator.clipboard.writeText(texto);
      $("acaoStatus").textContent = "Copiado para a área de transferência.";
    } catch (_) {
      const area = el("textarea", { value: texto });
      document.body.append(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      $("acaoStatus").textContent = ok ? "Copiado para a área de transferência." : "O navegador bloqueou a cópia.";
    }
  }

  function resumoTexto(c) {
    const linhas = ordenar(c.marcos).map((m, i) => `${doisDigitos(i + 1)}. ${m.data_exibicao} — ${m.titulo}\n    ${m.fonte.url}`);
    return `${c.titulo}\n\n${c.sintese} Conclusão: ${CONCLUSAO[c.classificacao] || "inconclusivo"}.\n\nLimites: ${c.limites}\n\n${linhas.join("\n")}\n\nGOSSIP DETECTIVE · caso ${c.id}`;
  }

  function ligarAcoes() {
    $("btnCopiar").onclick = () => S.caso && copiar(resumoTexto(S.caso));
    $("btnExportar").onclick = () => {
      if (!S.caso) return;
      const blob = new Blob([JSON.stringify(S.caso, null, 2)], { type: "application/json" });
      const a = el("a", { href: URL.createObjectURL(blob), download: `gossip-detective-${S.caso.id}.json` });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      $("acaoStatus").textContent = "Arquivo JSON exportado.";
    };
    $("btnFeedback").onclick = () => S.caso && copiar(
      `FEEDBACK — GOSSIP DETECTIVE\nCaso explorado: ${S.caso.titulo} (${S.caso.id})\n` +
      "1. Entendi o que foi verificado? (0-5): \n2. As fontes pareceram claras? (0-5): \n" +
      "3. A animação do mapa ajudou ou atrapalhou? \n4. Senti respeito pelas perspectivas divergentes? \n" +
      "5. Que pergunta gostaria de investigar? \n6. O que mudaria?");
    $("btnContestar").onclick = () => S.caso && copiar(
      `CONTESTAÇÃO / CORREÇÃO — GOSSIP DETECTIVE\nCaso: ${S.caso.titulo} (${S.caso.id}, versão ${S.caso.versao})\n` +
      "Registro contestado (número): \nO que está incorreto: \nFonte que sustenta a correção (URL): \nContato (opcional): ");
  }

  // ------------------------------------------------------------ inicialização

  async function iniciar() {
    document.querySelectorAll(".mode").forEach((b) => (b.onclick = () => {
      definirModo(b.dataset.modo);
      if (b.dataset.modo === "arquivo") $("avisoModo").textContent = "Modo arquivo: abra um dossiê pelo menu ☰.";
    }));
    $("formBusca").onsubmit = (e) => {
      e.preventDefault();
      if (S.emCurso) return;
      const pergunta = $("pergunta").value.replace(/\s+/g, " ").trim();
      $("avisoModo").textContent = "";
      if (pergunta.length < 3) { $("avisoModo").textContent = "Digite uma pergunta com pelo menos 3 caracteres."; return; }
      if (S.modo === "ia") iniciarIA(pergunta); else iniciarArquivo(pergunta);
    };
    $("btnAbortar").onclick = () => {
      status("Missão abortada. Os registros já validados permanecem no mapa.");
      encerrarMissao("MISSÃO ABORTADA", "alerta");
      if (S.marcos.length) finalizarMapa();
    };
    $("btnPular").onclick = () => S.pular && S.pular();
    $("btnAlternar").onclick = () => {
      const relatorioNoTopo = !document.querySelector("main.console").classList.contains("concluida");
      disporVista(relatorioNoTopo, relatorioNoTopo ? $("dossie") : document.querySelector(".map-panel"));
    };
    $("btnMenu").onclick = () => ($("menuLateral").classList.contains("aberto") ? fecharMenu() : abrirMenu());
    $("navHistorico").onclick = abrirMenu;
    $("btnTopo").onclick = () => scrollTo({ top: 0, behavior: reduzMovimento ? "auto" : "smooth" });
    addEventListener("scroll", () => $("btnTopo").classList.toggle("hidden", scrollY < 500), { passive: true });
    $("btnFecharMenu").onclick = fecharMenu;
    $("veu").onclick = fecharMenu;
    $("filtroMenu").oninput = filtrarMenu;
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharMenu(); });
    $("btnTrends").onclick = () => carregarTendencias(true);
    $("btnLegenda").onclick = () => {
      const aberta = $("legenda").classList.toggle("hidden") === false;
      $("btnLegenda").setAttribute("aria-expanded", String(aberta));
    };
    $("abaEntrar").onclick = () => modoAcesso("entrar");
    $("abaCadastrar").onclick = () => modoAcesso("cadastrar");
    $("formAcesso").onsubmit = enviarAcesso;
    $("btnSair").onclick = sair;
    let espera;
    addEventListener("resize", () => {
      clearTimeout(espera);
      espera = setTimeout(() => { renderizarTendencias(); renderizarBombando(); }, 250);
    });
    limparCatalogo("Os registros localizados no mapa aparecem aqui, em ordem cronológica.");
    ligarAcoes();
    ligarAvaliacao();

    S.mapaPronto = Mapa.iniciar({ aoSelecionar: selecionar });
    S.demo = await detectarDemo();
    await carregarStatus();
    if (S.demo) {
      $("demoFaixa").classList.remove("hidden");
      await entrarNaCentral({ id: "demo", nome: "Visitante", email: "Versão de demonstração" });
      return;
    }
    let usuario = null;
    try { usuario = (await (await fetch("api/sessao")).json()).usuario; } catch (_) { /* servidor fora do ar */ }
    if (usuario) await entrarNaCentral(usuario);
    else mostrarAcesso("entrar");
  }

  iniciar();
})();
