"""Cliente da Google Fact Check Tools API: checagens publicadas por agências (formato ClaimReview).

Gratuita com uma chave de API do Google Cloud. Cobre só o que alguma agência já checou e marcou
na própria página, então serve de atalho barato antes da busca na web, não de substituto.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config

ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
# Agências lusófonas consultadas pelo radar de tendências (as que não publicam no formato ClaimReview voltam vazias).
AGENCIAS = (
    "aosfatos.org", "estadao.com.br", "noticias.uol.com.br", "checamos.afp.com", "projetocomprova.com.br",
    "agencialupa.org", "lupa.uol.com.br", "g1.globo.com", "boatos.org", "e-farsas.com", "observador.pt", "poligrafo.sapo.pt",
)


class ErroChecagens(Exception):
    pass


def disponivel() -> bool:
    return bool(config.GOOGLE_FACTCHECK_KEY)


def _chamar(parametros: dict) -> dict:
    # A chave vai na URL; os erros são relançados sem a URL para ela nunca aparecer em log ou na interface.
    url = f"{ENDPOINT}?{urllib.parse.urlencode({**parametros, 'key': config.GOOGLE_FACTCHECK_KEY})}"
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as resposta:
                return json.load(resposta)
        except urllib.error.HTTPError as erro:
            if erro.code in (429, 500, 502, 503, 504) and tentativa < 2:
                time.sleep(1.5 * (tentativa + 1))
                continue
            if erro.code in (401, 403):
                raise ErroChecagens("chave do Google recusada ou Fact Check Tools API não ativada no projeto") from None
            raise ErroChecagens(f"a Fact Check API respondeu {erro.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            if tentativa < 2:
                time.sleep(1.5)
                continue
            raise ErroChecagens("sem conexão com a Fact Check API") from None
    raise ErroChecagens("a Fact Check API não respondeu")


def _registros(dados: dict) -> list[dict]:
    """Achata alegação + checagens num registro por checagem."""
    saida = []
    for alegacao in dados.get("claims") or []:
        for revisao in alegacao.get("claimReview") or []:
            url = revisao.get("url")
            if not url:
                continue
            editor = revisao.get("publisher") or {}
            saida.append({
                "alegacao": " ".join((alegacao.get("text") or revisao.get("title") or "").split())[:300],
                "autor_alegacao": (alegacao.get("claimant") or "")[:120],
                "titulo": " ".join((revisao.get("title") or "").split())[:200],
                "agencia": editor.get("name") or editor.get("site") or "",
                "site": editor.get("site") or "",
                "url": url,
                "data": (revisao.get("reviewDate") or alegacao.get("claimDate") or "")[:10],
                "classificacao": (revisao.get("textualRating") or "")[:80],
                "idioma": revisao.get("languageCode") or "",
            })
    return saida


def buscar(consulta: str, limite: int = 10) -> list[dict]:
    """Checagens que mencionam a consulta (palavras-chave funcionam melhor que frases longas)."""
    consulta = " ".join(consulta.split())[:200]
    if not consulta:
        return []
    return _registros(_chamar({"query": consulta, "pageSize": limite}))[:limite]


def recentes(dias: int = 7) -> list[dict]:
    """Checagens publicadas nos últimos dias pelas agências de AGENCIAS, sem repetição de URL."""
    def da_agencia(site: str):
        try:
            return _registros(_chamar({"reviewPublisherSiteFilter": site, "maxAgeDays": dias, "pageSize": 50}))
        except ErroChecagens as erro:
            return erro

    with ThreadPoolExecutor(max_workers=6) as grupo:
        resultados = list(grupo.map(da_agencia, AGENCIAS))
    falhas = [r for r in resultados if isinstance(r, ErroChecagens)]
    if len(falhas) == len(resultados):
        raise falhas[0]
    vistos, saida = set(), []
    for lote in resultados:
        if isinstance(lote, ErroChecagens):
            continue
        for registro in lote:
            if registro["url"] not in vistos:
                vistos.add(registro["url"])
                saida.append(registro)
    return saida
