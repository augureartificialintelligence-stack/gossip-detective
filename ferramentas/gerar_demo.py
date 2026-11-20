"""Gera o retrato estático usado pela versão de demonstração (GitHub Pages), em public/demo/.

O GitHub Pages só serve arquivos estáticos: sem servidor, sem IA ao vivo, sem login e sem chaves.
A demonstração reproduz os dossiês verificados e as investigações já feitas, e mostra os Trends e o
Bombando do momento em que este script rodou. Nada de contas, sessões ou avaliações é exportado.

Uso:  python ferramentas/gerar_demo.py
"""

import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from gossip import VERSAO, arquivo, config  # noqa: E402

DESTINO = config.PUBLICO / "demo"


def _gravar(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    verificados = arquivo.casos_verificados()
    investigacoes = []
    for caso in arquivo._investigacoes():
        caso = {k: v for k, v in caso.items() if k != "usuario"}  # sem o identificador de quem pesquisou
        investigacoes.append(caso)
        _gravar(DESTINO / "casos" / f"{caso['id']}.json", caso)
    for caso in verificados:
        _gravar(DESTINO / "casos" / f"{caso['id']}.json", caso)

    _gravar(DESTINO / "status.json", {"ia_disponivel": False, "versao": VERSAO, "checagens_google": False, "demo": True})
    _gravar(DESTINO / "casos.json", {
        "verificados": verificados,
        "recentes": [{"id": c["id"], "pergunta": c["pergunta"], "titulo": c["titulo"],
                      "classificacao": c["classificacao"], "criado_em": c["criado_em"]} for c in investigacoes],
    })
    _gravar(DESTINO / "bombando.json", {"itens": arquivo.mais_investigadas(dias=36500)})
    trends = {"itens": [], "atualizado_em": None, "fonte": "busca_web"}
    if (config.DADOS / "tendencias.json").is_file():
        trends.update(json.loads((config.DADOS / "tendencias.json").read_text(encoding="utf-8")))
    _gravar(DESTINO / "tendencias.json", {
        "itens": trends["itens"], "atualizado_em": trends.get("atualizado_em"), "fonte": trends.get("fonte", "busca_web"),
        "atualizando": False, "erro": None, "ia_disponivel": False, "validade_horas": config.TENDENCIAS_HORAS,
    })
    print(f"Demonstração gerada em {DESTINO}: {len(verificados)} dossiês verificados, {len(investigacoes)} investigações, "
          f"{len(trends['itens'])} trends.")


if __name__ == "__main__":
    main()
