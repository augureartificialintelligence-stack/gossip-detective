"""Matriz editorial de fontes REVELATIO (dados/matriz_fontes.json, importada de docs/ por ferramentas/importar_matriz.py).

Serve a dois propósitos: orientar a IA sobre onde pesquisar primeiro (texto injetado no prompt) e marcar a
proveniência de cada marco com o código da fonte (F001–F070) quando a URL citada pertence a uma delas.
Estar na matriz não certifica a fonte: a regra de só aceitar URLs efetivamente recuperadas continua valendo.
"""

import json
from functools import lru_cache
from urllib.parse import urlsplit

from . import config

FUNCOES = {"D": "descoberta", "C": "contexto", "P": "documento primário", "V": "verificação", "M": "metodologia"}


@lru_cache(maxsize=1)
def carregar() -> tuple[dict, ...]:
    try:
        return tuple(json.loads((config.DADOS / "matriz_fontes.json").read_text(encoding="utf-8"))["fontes"])
    except (OSError, ValueError, KeyError):
        return ()


def identificar(url: str) -> dict | None:
    """Fonte da matriz a que a URL pertence. Entradas com caminho (ex.: uma lista da Wikipédia) exigem o
    prefixo exato; entradas de site inteiro aceitam o domínio e seus subdomínios. Vence o prefixo mais longo."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return None
    host = partes.netloc.lower().removeprefix("www.")
    alvo = host + partes.path
    melhor = None
    for fonte in carregar():
        dominio, prefixo = fonte["dominio"], fonte["prefixo"]
        if prefixo != dominio:
            casa = alvo.startswith(prefixo)
        else:
            casa = host == dominio or host.endswith("." + dominio)
        if casa and (melhor is None or len(prefixo) > len(melhor["prefixo"])):
            melhor = fonte
    return melhor


def texto_prompt() -> str:
    """Trecho estático para o prompt de sistema (estável entre missões, para o cache de prompt)."""
    fontes = carregar()
    if not fontes:
        return ""
    linhas = "\n".join(
        f"{f['id']} · {f['nome']} · {f['dominio']} · {'/'.join(f['funcoes'])} · {f['cuidado']}" for f in fontes
    )
    return f"""

Matriz de fontes REVELATIO (prioridade de pesquisa):
Comece por estas fontes e prefira-as ao decidir onde buscar (inclua o nome da fonte ou "site:domínio" na consulta) e quais registrar. Funções: D descoberta, C contexto, P documento primário, V verificação, M metodologia. Uma fonte de descoberta (D) aponta caminhos mas não comprova sozinha: procure o documento primário (P) que ela cita. Estar na matriz não certifica toda afirmação da fonte. Fontes fora da matriz continuam permitidas quando forem o documento original ou a melhor evidência disponível.
Regras da matriz:
1. Identifique a alegação exata: uma matéria pode provar que uma declaração foi feita sem provar o conteúdo dela.
2. Quando possível, chegue ao documento de origem (edição, página, ata, DOI, dataset).
3. Cruze fontes realmente independentes; republicações e citações circulares não contam como confirmação adicional.
4. Registre a data do evento (data_inicio) e a da publicação do documento (data_documento) separadamente.
5. Fonte oficial é primária sobre o que a instituição declarou, não necessariamente imparcial na interpretação.
6. Separe fato, autoria e intenção: provar que um conteúdo é falso não prova quem o criou nem por quê.
Fontes (ID · nome · domínio · funções · cuidado):
{linhas}"""
