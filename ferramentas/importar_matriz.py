"""Importa a matriz editorial de fontes (docs/REVELATIO_MATRIZ_FONTES_*.md) para dados/matriz_fontes.json.

O Markdown continua sendo o documento editorial; o JSON é o que o motor carrega. Rode de novo sempre que a
matriz for revisada.  Uso:  python ferramentas/importar_matriz.py [caminho_do_md]
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
FUNCOES = {"D": "descoberta", "C": "contexto", "P": "documento primário", "V": "verificação", "M": "metodologia"}
_LINHA = re.compile(r"^\|\s*(F\d{3})\s*\|\s*(.+?)\s*\|\s*(https?://\S+?)\s*\|\s*([A-Z,\s]+?)\s*\|\s*(.+?)\s*\|\s*$")


def importar(origem: Path) -> list[dict]:
    fontes = []
    for linha in origem.read_text(encoding="utf-8").splitlines():
        m = _LINHA.match(linha.strip())
        if not m:
            continue
        fid, nome, url, funcoes, cuidado = m.groups()
        partes = urlsplit(url)
        fontes.append({
            "id": fid,
            "nome": nome.strip(),
            "url": url,
            "dominio": partes.netloc.lower().removeprefix("www."),
            "prefixo": (partes.netloc.lower().removeprefix("www.") + partes.path.rstrip("/")),
            "funcoes": [f.strip() for f in funcoes.split(",") if f.strip() in FUNCOES],
            "cuidado": " ".join(cuidado.split()),
        })
    return fontes


def main() -> None:
    origem = Path(sys.argv[1]) if len(sys.argv) > 1 else max(RAIZ.glob("docs/REVELATIO_MATRIZ_FONTES_*.md"))
    fontes = importar(origem)
    if not fontes:
        sys.exit(f"Nenhuma fonte reconhecida em {origem}")
    destino = RAIZ / "dados" / "matriz_fontes.json"
    destino.write_text(json.dumps({"origem": origem.name, "fontes": fontes}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(fontes)} fontes importadas de {origem.name} para {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
