"""Executa as missões dos catálogos editoriais com a IA e publica os dossiês em dados/colecoes/.

Cada ficha (dados/catalogos.json) vira uma investigação completa, no mesmo motor da central, com a matriz de
fontes REVELATIO e a orientação editorial da ficha. Os dossiês saem marcados como "gerado por IA, revisão
editorial pendente". Retoma de onde parou (fichas já publicadas são puladas), roda em paralelo, registra o custo
estimado de cada missão em dados/colecoes/_relatorio.json e para de iniciar missões ao atingir o orçamento.

Uso:
  python ferramentas/missoes_catalogo.py --ids D005,H003
  python ferramentas/missoes_catalogo.py --colecao hoaxes --limite 10 --orcamento 5
  python ferramentas/missoes_catalogo.py --todas --paralelo 3 --orcamento 80
Opções: --buscas N, --leituras N e --esforco NIVEL valem só nesta execução (sobrescrevem o .env); --refazer
reinvestiga fichas já publicadas.
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Missões dos catálogos REVELATIO")
    alvo = p.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--ids", help="fichas separadas por vírgula, ex.: D005,H003")
    alvo.add_argument("--colecao", choices=["desinformacao", "hoaxes"])
    alvo.add_argument("--todas", action="store_true")
    p.add_argument("--limite", type=int, default=0, help="no máximo N missões nesta execução")
    p.add_argument("--paralelo", type=int, default=2)
    p.add_argument("--orcamento", type=float, default=0, help="US$; para de iniciar missões ao atingir (0 = sem teto)")
    p.add_argument("--buscas", type=int)
    p.add_argument("--leituras", type=int)
    p.add_argument("--esforco", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--refazer", action="store_true")
    return p.parse_args()


def main() -> None:
    a = _argumentos()
    # Precisa valer antes de importar o motor: as ferramentas e o esforço são lidos na importação.
    for opcao, variavel in ((a.buscas, "GD_MAX_BUSCAS"), (a.leituras, "GD_MAX_LEITURAS"), (a.esforco, "GD_ESFORCO")):
        if opcao:
            os.environ[variavel] = str(opcao)

    from gossip import arquivo, config
    from gossip.investigador import investigar

    if config.TRUSTSTORE:
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
    if not config.credenciais_presentes():
        sys.exit("IA não configurada: defina ANTHROPIC_API_KEY no .env.")

    fichas = [(c, f) for c in arquivo.catalogos() for f in c["itens"]]
    if a.ids:
        pedidos = {i.strip().upper() for i in a.ids.split(",") if i.strip()}
        fichas = [(c, f) for c, f in fichas if f["id"] in pedidos]
    elif a.colecao:
        fichas = [(c, f) for c, f in fichas if c["id"] == a.colecao]
    if not a.refazer:
        fichas = [(c, f) for c, f in fichas if not (config.COLECOES / f"{f['id'].lower()}.json").is_file()]
    if a.limite:
        fichas = fichas[: a.limite]
    if not fichas:
        print("Nada a fazer: as fichas pedidas já estão publicadas (use --refazer para reinvestigar).")
        return

    relatorio_caminho = config.COLECOES / "_relatorio.json"
    config.COLECOES.mkdir(parents=True, exist_ok=True)
    try:
        relatorio = json.loads(relatorio_caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        relatorio = {}
    trava = threading.Lock()
    gasto = 0.0

    def executar(colecao: dict, ficha: dict) -> dict:
        pergunta = f"{ficha['caso']} ({ficha['epoca']}, {ficha['regiao']})"
        inicio = time.monotonic()
        caso, problema = None, None
        try:
            for evento, dados in investigar(pergunta, ficha["orientacao"], caso_id=ficha["id"].lower()):
                if evento == "conclusao":
                    caso = dados
                elif evento == "erro":
                    problema = dados["mensagem"]
                elif evento == "recusa":
                    problema = "recusada: " + dados["motivo"]
        except Exception as erro:  # noqa: BLE001 - registra e segue para a próxima ficha
            problema = f"falha: {erro}"
        registro = {"id": ficha["id"], "colecao": colecao["id"], "duracao_s": round(time.monotonic() - inicio, 1)}
        if caso:
            caso.update(
                origem="catalogo", colecao=colecao["id"], catalogo_id=ficha["id"], classe_preliminar=ficha["classe"],
                epoca=ficha["epoca"], regiao=ficha["regiao"], status_editorial="ia_revisao_pendente",
            )
            arquivo.salvar_colecao(caso)
            e = caso["estatisticas"]
            registro.update(status="publicado", classificacao=caso["classificacao"], marcos=e["marcos"],
                            marcos_matriz=e.get("marcos_matriz", 0), buscas=e["buscas"], custo_usd=config.custo_estimado(e))
        else:
            registro.update(status="falhou", motivo=problema or "sem conclusão", custo_usd=None)
        return registro

    print(f"{len(fichas)} missões · paralelo {a.paralelo} · esforço {config.ESFORCO} · buscas {config.MAX_BUSCAS} · "
          f"leituras {config.MAX_LEITURAS} · orçamento {'US$ %.2f' % a.orcamento if a.orcamento else 'sem teto'}")
    pendentes = list(fichas)
    feitas = 0
    with ThreadPoolExecutor(max_workers=max(1, a.paralelo)) as grupo:
        em_curso = set()
        while pendentes or em_curso:
            while pendentes and len(em_curso) < a.paralelo and not (a.orcamento and gasto >= a.orcamento):
                em_curso.add(grupo.submit(executar, *pendentes.pop(0)))
            if not em_curso:
                break
            prontas, em_curso = wait(em_curso, return_when=FIRST_COMPLETED)
            for futuro in prontas:
                r = futuro.result()
                feitas += 1
                with trava:
                    gasto += r.get("custo_usd") or 0
                    relatorio[r["id"]] = {**r, "quando": time.strftime("%Y-%m-%d %H:%M:%S")}
                    relatorio_caminho.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
                detalhe = (f"{r['classificacao']} · {r['marcos']} marcos ({r['marcos_matriz']} da matriz) · {r['buscas']} buscas · "
                           f"US$ {r['custo_usd']:.3f}") if r["status"] == "publicado" else r["motivo"]
                print(f"[{feitas}/{len(fichas)}] {r['id']} {r['status']} · {r['duracao_s']} s · {detalhe} · acumulado US$ {gasto:.2f}",
                      flush=True)
    if pendentes:
        print(f"Orçamento atingido: {len(pendentes)} fichas ficaram para a próxima execução.")
    print(f"Fim: {feitas} missões nesta execução · custo estimado US$ {gasto:.2f}")


if __name__ == "__main__":
    main()
