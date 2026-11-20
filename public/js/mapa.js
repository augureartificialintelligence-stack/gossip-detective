/* GOSSIP DETECTIVE — mapa estrutural (D3 + TopoJSON).
   Desenha o mapa-múndi, os marcos como pontos vermelhos piscantes, os arcos que ligam
   os marcos em ordem cronológica e o destaque do ponto final do rastro. Durante a busca,
   sinais de varredura piscam sobre o mapa (legendados como tais: não são registros). */
(function () {
  "use strict";

  const W = 1000, H = 560;
  const RAIO_AREA = { regiao: 14, pais: 22, continente: 34 };
  const reduzMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  let svg, camadaMapa, camadaRota, camadaVarredura, camadaMarcos, projecao, caminho, zoom, wrap, tooltip, leitura;
  let transformacao = d3.zoomIdentity;
  let lista = [];          // marcos mapeáveis em ordem cronológica
  let estado = { finalId: null, origemId: null, ativoId: null };
  let aoSelecionar = () => {};
  let terras = [];         // países com limites projetados e peso cumulativo, para sortear sinais em terra
  let varredura = null;

  const fmtCoord = (v, pos, neg) => `${Math.abs(v).toFixed(4)}°${v >= 0 ? pos : neg}`;

  async function iniciar(opcoes) {
    aoSelecionar = opcoes.aoSelecionar || aoSelecionar;
    wrap = document.getElementById("mapaWrap");
    tooltip = document.getElementById("tooltip");
    leitura = document.getElementById("leitura");
    svg = d3.select("#mapaSvg");
    camadaMapa = d3.select("#camadaMapa");
    camadaRota = d3.select("#camadaRota");
    camadaVarredura = d3.select("#camadaVarredura");
    camadaMarcos = d3.select("#camadaMarcos");

    projecao = d3.geoMercator().fitExtent([[0, 0], [W, H]], {
      type: "MultiPoint", coordinates: [[-180, -57], [180, 78]],
    });
    caminho = d3.geoPath(projecao);

    camadaMapa.append("rect").attr("class", "oceano").attr("width", W).attr("height", H);
    camadaMapa.append("path").attr("class", "graticula").attr("d", caminho(d3.geoGraticule().step([15, 15])()));
    const camadaPaises = camadaMapa.append("g");

    zoom = d3.zoom().scaleExtent([1, 16]).translateExtent([[0, 0], [W, H]])
      .on("zoom", (e) => {
        transformacao = e.transform;
        camadaMapa.attr("transform", transformacao);
        posicionar();
      });
    svg.call(zoom).on("dblclick.zoom", null);

    svg.on("mousemove", (e) => {
      if (!leitura) return;
      const [x, y] = transformacao.invert(d3.pointer(e, svg.node()));
      const geo = projecao.invert([x, y]);
      if (geo && Number.isFinite(geo[1])) {
        leitura.textContent = `LAT ${fmtCoord(geo[1], "N", "S")} · LON ${fmtCoord(geo[0], "L", "O")}`;
      }
    });

    document.getElementById("zoomMais").onclick = () => svg.transition().duration(350).call(zoom.scaleBy, 1.8);
    document.getElementById("zoomMenos").onclick = () => svg.transition().duration(350).call(zoom.scaleBy, 1 / 1.8);
    document.getElementById("zoomTudo").onclick = () => enquadrar();

    // O atlas chega depois; a interface e os marcadores já funcionam sem ele.
    try {
      const topo = await baixarAtlas();
      const paises = topojson.feature(topo, topo.objects.countries).features;
      camadaPaises.selectAll("path").data(paises).join("path")
        .attr("class", "pais").attr("d", caminho)
        .append("title").text((d) => d.properties.name);
      let acumulado = 0;
      terras = paises.filter((f) => f.properties.name !== "Antarctica").map((f) => {
        acumulado += Math.sqrt(caminho.area(f));
        return { f, limites: caminho.bounds(f), acumulado };
      });
    } catch (erro) {
      console.error("Falha ao carregar o atlas", erro);
    }
  }

  /** Baixa o atlas com tempo-limite e novas tentativas: um download travado não deixa o mapa sem países. */
  async function baixarAtlas(tentativas = 4) {
    for (let i = 1; ; i++) {
      const controle = new AbortController();
      const limite = setTimeout(() => controle.abort(), 4000 * i);
      try {
        const resp = await fetch(i === 1 ? "vendor/countries-50m.json" : `vendor/countries-50m.json?tentativa=${i}`,
          { signal: controle.signal });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
      } catch (erro) {
        if (i >= tentativas) throw erro;
      } finally {
        clearTimeout(limite);
      }
    }
  }

  // ------------------------------------------------------------ geometria

  function base(m) { return projecao([m.lon, m.lat]); }

  /** Posição em tela de cada marco, afastando levemente marcos sobrepostos. */
  function posicoes() {
    const grupos = new Map();
    const res = new Map();
    for (const m of lista) {
      const [x, y] = transformacao.apply(base(m));
      const chave = `${Math.round(x / 6)}:${Math.round(y / 6)}`;
      if (!grupos.has(chave)) grupos.set(chave, []);
      grupos.get(chave).push({ m, x, y });
    }
    for (const grupo of grupos.values()) {
      grupo.forEach(({ m, x, y }, i) => {
        if (grupo.length === 1) return res.set(m.id, [x, y]);
        const ang = (2 * Math.PI * i) / grupo.length - Math.PI / 2;
        res.set(m.id, [x + Math.cos(ang) * 11, y + Math.sin(ang) * 11]);
      });
    }
    return res;
  }

  /** Curva quadrática entre dois pontos, sempre arqueada para cima (estilo trajetória). */
  function arco([x1, y1], [x2, y2]) {
    const dx = x2 - x1, dy = y2 - y1;
    const dist = Math.hypot(dx, dy) || 1;
    const curva = Math.min(dist * 0.25, 140);
    let nx = -dy / dist, ny = dx / dist;
    if (ny > 0) { nx = -nx; ny = -ny; }
    const cx = (x1 + x2) / 2 + nx * curva, cy = (y1 + y2) / 2 + ny * curva;
    return `M${x1.toFixed(1)},${y1.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
  }

  // ------------------------------------------------------------ desenho

  function classes(m) {
    const c = ["mk"];
    if (RAIO_AREA[m.grau_geografico]) c.push("aproximado");
    if (m.id === estado.finalId) c.push("final");
    else if (m.id === estado.origemId) c.push("origem");
    if (estado.finalId && m.id !== estado.finalId) c.push("assentado"); // fim da busca: só o ponto final segue piscando
    if (m.id === estado.ativoId) c.push("ativo");
    return c.join(" ");
  }

  function montarMarcador(g, m, ordem) {
    const final = m.id === estado.finalId;
    const origem = !final && m.id === estado.origemId;
    g.selectAll("*").remove();
    const raioArea = RAIO_AREA[m.grau_geografico];
    if (raioArea) g.append("circle").attr("class", "area").attr("r", raioArea);
    if (final) {
      g.append("circle").attr("class", "halo").attr("r", 30);
      g.append("path").attr("class", "mira")
        .attr("d", "M-18,-10V-18H-10 M10,-18H18V-10 M18,10V18H10 M-10,18H-18V10");
      g.append("circle").attr("class", "pulso p2").attr("r", 5);
    }
    g.append("circle").attr("class", "pulso").attr("r", final ? 5 : 4);
    if (origem) g.append("circle").attr("class", "anel-origem").attr("r", 10);
    g.append("circle").attr("class", "nucleo").attr("r", final ? 6.5 : 4.2);
    g.append("text").attr("class", "num").attr("x", 8).attr("y", -8).text(String(ordem).padStart(2, "0"));
  }

  function posicionar() {
    if (!projecao) return;
    const pos = posicoes();
    camadaMarcos.selectAll("g.mk").attr("transform", (m) => {
      const [x, y] = pos.get(m.id);
      return `translate(${x.toFixed(1)},${y.toFixed(1)})`;
    });
    const pares = lista.slice(1).map((m, i) => ({ de: lista[i], para: m }));
    camadaRota.selectAll("path.rota").data(pares, (p) => `${p.de.id}>${p.para.id}`)
      .attr("d", (p) => arco(pos.get(p.de.id), pos.get(p.para.id)));
    camadaVarredura.selectAll("g.sinal").attr("transform", (d) => {
      const [x, y] = transformacao.apply(d.p);
      return `translate(${x.toFixed(1)},${y.toFixed(1)})`;
    });
  }

  // ------------------------------------------------------------ varredura (sinais de busca)

  const visivel = ([x, y]) => x >= 0 && x <= W && y >= 0 && y <= H;

  /** Ponto projetado aleatório em terra firme e dentro da área visível. */
  function pontoTerrestre() {
    const total = terras.length ? terras[terras.length - 1].acumulado : 0;
    for (let tentativa = 0; total && tentativa < 10; tentativa++) {
      const sorteio = Math.random() * total;
      const { f, limites: [[x0, y0], [x1, y1]] } = terras.find((t) => t.acumulado >= sorteio);
      const p = [x0 + Math.random() * (x1 - x0), y0 + Math.random() * (y1 - y0)];
      if (visivel(transformacao.apply(p)) && d3.geoContains(f, projecao.invert(p))) return p;
    }
    return transformacao.invert([W * (0.08 + Math.random() * 0.84), H * (0.12 + Math.random() * 0.7)]);
  }

  function criarSinal(p, dx = 0, dy = 0) {
    const [x, y] = transformacao.apply(p);
    const g = camadaVarredura.append("g").datum({ p }).attr("class", "sinal")
      .attr("transform", `translate(${x.toFixed(1)},${y.toFixed(1)})`);
    const desloc = g.append("g").attr("class", "desloc").attr("transform", `translate(${dx.toFixed(1)},${dy.toFixed(1)})`);
    desloc.append("circle").attr("class", "s-pulso").attr("r", 3)
      .style("animation-delay", `${(-Math.random() * 1.4).toFixed(2)}s`);
    desloc.append("circle").attr("class", "s-nucleo").attr("r", 2.4)
      .style("animation-duration", `${(0.45 + Math.random() * 0.5).toFixed(2)}s`);
    return g;
  }

  function emitir() {
    const vida = 1100 + Math.random() * 1500;
    criarSinal(pontoTerrestre()).transition().delay(vida).duration(350).style("opacity", 0).remove();
  }

  /** Liga/desliga os sinais de varredura. Ao desligar, eles se apagam e só os registros ficam. */
  function varrer(ativo) {
    clearInterval(varredura);
    varredura = null;
    if (ativo && !reduzMovimento) {
      varredura = setInterval(() => { emitir(); if (Math.random() < 0.5) emitir(); }, 230);
    } else if (camadaVarredura) {
      camadaVarredura.selectAll("g.sinal").transition().duration(500).style("opacity", 0).remove();
    }
  }

  /** Rajada de sinais (uma nova consulta de busca foi disparada). */
  function rajada(n) {
    if (varredura) for (let i = 0; i < n; i++) emitir();
  }

  /** Sinais convergem para o ponto onde um registro acaba de ser localizado. */
  function convergir(id) {
    const m = lista.find((x) => x.id === id);
    if (!m || reduzMovimento) return;
    const p = base(m);
    for (let i = 0; i < 9; i++) {
      const ang = (2 * Math.PI * i) / 9 + Math.random() * 0.5;
      const raio = 70 + Math.random() * 60;
      const g = criarSinal(p, Math.cos(ang) * raio, Math.sin(ang) * raio).classed("convergindo", true);
      g.select(".desloc").transition().delay(i * 30).duration(800).ease(d3.easeCubicIn).attr("transform", "translate(0,0)");
      g.transition().delay(820 + i * 30).duration(250).style("opacity", 0).remove();
    }
  }

  /** Centro do marcador em coordenadas da janela, ou null se estiver fora da área visível do mapa. */
  function pontoNaTela(id) {
    const no = camadaMarcos.selectAll("g.mk").filter((m) => m.id === id).select(".nucleo").node();
    if (!no) return null;
    const r = no.getBoundingClientRect(), c = wrap.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    return x < c.left || x > c.right || y < c.top || y > c.bottom ? null : { x, y };
  }

  /** Redesenha a partir da lista cronológica de marcos com coordenadas. */
  function desenhar(marcosCronologicos, novoEstado) {
    lista = marcosCronologicos.filter((m) => m.lat != null && m.lon != null);
    estado = { ...estado, ...novoEstado };
    const pos = posicoes();
    const ordem = new Map(marcosCronologicos.map((m, i) => [m.id, i + 1]));

    // Arcos entre registros consecutivos (a cor/traço vem da relação declarada no destino).
    const pares = lista.slice(1).map((m, i) => ({ de: lista[i], para: m }))
      .filter((p) => { const a = pos.get(p.de.id), b = pos.get(p.para.id); return Math.hypot(a[0] - b[0], a[1] - b[1]) > 4; });
    camadaRota.selectAll("path.rota").data(pares, (p) => `${p.de.id}>${p.para.id}`).join(
      (entra) => entra.append("path")
        .attr("class", (p) => `rota ${p.para.relacao_com_anterior} desenhando`)
        .attr("d", (p) => arco(pos.get(p.de.id), pos.get(p.para.id)))
        .each(function () {
          const comp = this.getTotalLength();
          this.style.setProperty("--comprimento", comp);
          this.style.strokeDasharray = comp;
          this.addEventListener("animationend", () => {
            this.classList.remove("desenhando");
            this.style.strokeDasharray = "";
          }, { once: true });
        }),
      (atual) => atual.attr("d", (p) => arco(pos.get(p.de.id), pos.get(p.para.id))),
      (sai) => sai.remove(),
    );

    camadaMarcos.selectAll("g.mk").data(lista, (m) => m.id).join(
      (entra) => entra.append("g")
        .attr("class", (m) => `${classes(m)} novo`)
        .attr("tabindex", 0)
        .attr("role", "button")
        .on("mouseenter", mostrarDica)
        .on("mouseleave", esconderDica)
        .on("click", (e, m) => aoSelecionar(m.id))
        .on("keydown", (e, m) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); aoSelecionar(m.id); } }),
      (atual) => atual,
      (sai) => sai.remove(),
    ).each(function (m) {
      const g = d3.select(this);
      const assinatura = `${classes(m)}|${ordem.get(m.id)}`;
      if (this.dataset.assinatura !== assinatura) {
        const eraNovo = !this.dataset.assinatura;
        this.dataset.assinatura = assinatura;
        g.attr("class", classes(m) + (eraNovo ? " novo" : ""));
        montarMarcador(g, m, ordem.get(m.id));
      }
      g.attr("aria-label", `Registro ${ordem.get(m.id)}: ${m.titulo}, ${m.data_exibicao}, ${m.local}`);
    });

    // O ponto final fica por cima de todos.
    camadaMarcos.selectAll("g.mk.final").raise();
    posicionar();
  }

  function mostrarDica(e, m) {
    const caixa = wrap.getBoundingClientRect();
    tooltip.innerHTML = "";
    const data = Object.assign(document.createElement("span"), { className: "t-data", textContent: m.data_exibicao });
    const titulo = Object.assign(document.createElement("b"), { textContent: m.titulo });
    const meta = Object.assign(document.createElement("span"), {
      className: "t-meta", textContent: `${m.local} · ${m.fonte.entidade}`,
    });
    tooltip.append(data, titulo, meta);
    tooltip.classList.remove("hidden");
    const x = Math.min(e.clientX - caixa.left + 14, caixa.width - 290);
    const y = Math.max(e.clientY - caixa.top - 70, 8);
    tooltip.style.left = `${Math.max(8, x)}px`;
    tooltip.style.top = `${y}px`;
  }

  function esconderDica() { tooltip.classList.add("hidden"); }

  // ------------------------------------------------------------ câmera

  function enquadrar(ids, duracao = 1300) {
    const alvos = (ids ? lista.filter((m) => ids.includes(m.id)) : lista).map(base);
    let destino = d3.zoomIdentity;
    if (alvos.length) {
      const xs = alvos.map((p) => p[0]), ys = alvos.map((p) => p[1]);
      const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
      const dx = Math.max(x1 - x0, 1), dy = Math.max(y1 - y0, 1);
      const k = alvos.length === 1 ? 4 : Math.max(1, Math.min(14, 0.62 * Math.min(W / dx, H / dy)));
      destino = d3.zoomIdentity.translate(W / 2, H / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    }
    svg.transition().duration(duracao).ease(d3.easeCubicInOut).call(zoom.transform, destino);
  }

  function focar(id) {
    const m = lista.find((x) => x.id === id);
    if (!m) return;
    const [x, y] = base(m);
    const k = Math.max(transformacao.k, 4);
    svg.transition().duration(900).ease(d3.easeCubicInOut)
      .call(zoom.transform, d3.zoomIdentity.translate(W / 2, H / 2).scale(k).translate(-x, -y));
  }

  function limpar() {
    lista = [];
    estado = { finalId: null, origemId: null, ativoId: null };
    varrer(false);
    camadaRota.selectAll("*").remove();
    camadaVarredura.selectAll("*").interrupt().remove();
    camadaMarcos.selectAll("*").remove();
    esconderDica();
    if (svg) svg.transition().duration(800).call(zoom.transform, d3.zoomIdentity);
  }

  window.Mapa = { iniciar, desenhar, enquadrar, focar, limpar, varrer, rajada, convergir, pontoNaTela };
})();
