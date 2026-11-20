"""Modelo de dados (Case, Moment, Citation, Perspective) e validação das entradas da IA.

Segue a "estrutura de dados mínima" de docs/ARQUITETURA_E_ROTEIRO.md. Toda entrada vinda
do modelo é tratada como não confiável: validada, normalizada e, se preciso, rejeitada
com uma mensagem que o modelo consegue corrigir.
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

LIMITE_MARCOS = 9

TIPOS_REGISTRO = [
    "primeiro_registro_localizado", "publicacao", "documento_primario", "fato_historico",
    "amplificacao", "reproducao_documentada", "alteracao", "contestacao", "verificacao",
    "interpretacao_retrospectiva", "memoria_historica",
]
PRECISOES = ["dia", "mes", "ano", "decada", "seculo", "intervalo", "aproximada"]
GRAUS_GEO = ["ponto_exato", "cidade", "regiao", "pais", "continente", "desconhecido"]
RELACOES = ["cronologia", "reproducao_documentada", "hipotese"]
TIPOS_FONTE = ["primaria", "institucional", "academica", "jornalistica", "checagem", "arquivo_web", "secundaria"]
TIPOS_ALEGACAO = ["rumor", "fato_historico", "origem_de_palavra", "conflito_de_narrativas", "citacao", "noticia_recente"]
CLASSIFICACOES = [
    "confirmada", "bem_documentada", "parcialmente_verdadeira", "disputada",
    "refutada", "inconclusiva", "sem_registros_suficientes",
]
SUSTENTACOES = ["documentada", "parcial", "sem_sustentacao"]

_DATA = re.compile(r"^(-?\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?$")
_URL_SOLTA = re.compile(r"https?://[^\s\"'<>()\]\[{}|\\^`]+")


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- datas


def _ano_fracionario(data: str, fim_do_periodo: bool = False) -> float | None:
    m = _DATA.match(data or "")
    if not m:
        return None
    ano, mes, dia = int(m.group(1)), m.group(2), m.group(3)
    if mes is None:
        return ano + (1.0 if fim_do_periodo else 0.0)
    mes_i = int(mes)
    if not 1 <= mes_i <= 12:
        return None
    if dia is None:
        return ano + (mes_i - (0 if fim_do_periodo else 1)) / 12
    dia_i = int(dia)
    if not 1 <= dia_i <= 31:
        return None
    return ano + (mes_i - 1) / 12 + (dia_i - 1) / 372


def chave_cronologica(data_inicio: str, data_fim: str | None) -> float:
    """Ponto médio do período indicado; datas imprecisas caem no meio do seu intervalo."""
    ini = _ano_fracionario(data_inicio)
    if ini is None:
        return float("inf")
    fim = _ano_fracionario(data_fim, fim_do_periodo=True) if data_fim else None
    if fim is None:
        fim = _ano_fracionario(data_inicio, fim_do_periodo=True)
        if fim is None or fim == ini:  # data com dia: ponto exato
            return ini
    return (ini + fim) / 2


def ordenar_marcos(marcos: list[dict]) -> list[dict]:
    return sorted(marcos, key=lambda m: (chave_cronologica(m["data_inicio"], m.get("data_fim")), m["seq"]))


# ---------------------------------------------------------------- URLs


def normalizar_url(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    caminho = p.path.rstrip("/") or "/"
    return urlunsplit(("https", p.netloc.lower().removeprefix("www."), caminho, p.query, ""))


def coletar_urls(obj, destino: dict[str, str]) -> None:
    """Percorre um bloco de resultado de ferramenta e registra URLs (com título quando houver)."""
    if isinstance(obj, dict):
        url = obj.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            chave = normalizar_url(url)
            if chave and (chave not in destino or not destino[chave]):
                destino[chave] = (obj.get("title") or "")[:200]
        for valor in obj.values():
            coletar_urls(valor, destino)
    elif isinstance(obj, list):
        for item in obj:
            coletar_urls(item, destino)
    elif isinstance(obj, str) and "http" in obj:
        # Resultados filtrados por código (filtragem dinâmica) chegam como texto.
        for achado in _URL_SOLTA.findall(obj):
            chave = normalizar_url(achado.rstrip(".,;:"))
            if chave:
                destino.setdefault(chave, "")


# ---------------------------------------------------------------- validação


def _texto(entrada: dict, campo: str, limite: int, obrigatorio: bool = True) -> str:
    valor = entrada.get(campo)
    if valor is None and not obrigatorio:
        return ""
    if not isinstance(valor, str) or (obrigatorio and not valor.strip()):
        raise ValueError(f"campo '{campo}' ausente ou vazio")
    return " ".join(valor.split())[:limite]


def _opcao(entrada: dict, campo: str, opcoes: list[str]) -> str:
    valor = entrada.get(campo)
    if valor not in opcoes:
        raise ValueError(f"campo '{campo}' deve ser um de: {', '.join(opcoes)}")
    return valor


def validar_marco(entrada: dict, urls_vistas: dict[str, str], seq: int) -> dict:
    """Converte a chamada `registrar_marco` num Moment + Citation. Levanta ValueError se inválida."""
    if not isinstance(entrada, dict):
        raise ValueError("entrada não é um objeto JSON")
    fonte_in = entrada.get("fonte")
    if not isinstance(fonte_in, dict):
        raise ValueError("campo 'fonte' ausente")

    url = _texto(fonte_in, "url", 2000)
    chave_url = normalizar_url(url)
    if not chave_url:
        raise ValueError("a URL da fonte precisa começar com http:// ou https://")
    if chave_url not in urls_vistas:
        raise ValueError(
            "esta URL não apareceu nos resultados de web_search/web_fetch desta investigação. "
            "Registre somente fontes efetivamente recuperadas; se precisar dela, pesquise ou leia a página antes."
        )

    data_inicio = _texto(entrada, "data_inicio", 11)
    if _ano_fracionario(data_inicio) is None:
        raise ValueError("data_inicio deve seguir AAAA, AAAA-MM ou AAAA-MM-DD (anos a.C. com sinal negativo)")
    data_fim = entrada.get("data_fim") or None
    if data_fim is not None:
        data_fim = _texto(entrada, "data_fim", 11)
        if _ano_fracionario(data_fim) is None:
            raise ValueError("data_fim deve seguir AAAA, AAAA-MM ou AAAA-MM-DD, ou ser null")

    grau = _opcao(entrada, "grau_geografico", GRAUS_GEO)
    lat, lon = entrada.get("lat"), entrada.get("lon")
    if grau == "desconhecido" or lat is None or lon is None:
        lat = lon = None
        grau = "desconhecido"
    else:
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            raise ValueError("lat e lon devem ser números ou null")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("coordenadas fora do intervalo válido")
        lat, lon = round(float(lat), 4), round(float(lon), 4)

    return {
        "id": f"m{seq:02d}",
        "seq": seq,
        "titulo": _texto(entrada, "titulo", 140),
        "texto": _texto(entrada, "texto", 600),
        "tipo_registro": _opcao(entrada, "tipo_registro", TIPOS_REGISTRO),
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "precisao_temporal": _opcao(entrada, "precisao_temporal", PRECISOES),
        "data_exibicao": _texto(entrada, "data_exibicao", 40),
        "local": _texto(entrada, "local", 120, obrigatorio=False) or "Local não identificado",
        "lat": lat,
        "lon": lon,
        "grau_geografico": grau,
        "relacao_com_anterior": _opcao(entrada, "relacao_com_anterior", RELACOES),
        "fonte": {
            "titulo": _texto(fonte_in, "titulo", 200),
            "entidade": _texto(fonte_in, "entidade", 120),
            "url": url,
            "tipo_fonte": _opcao(fonte_in, "tipo_fonte", TIPOS_FONTE),
            "data_documento": (fonte_in.get("data_documento") or None)
            and _texto(fonte_in, "data_documento", 40),
            "trecho_de_suporte": _texto(fonte_in, "trecho_de_suporte", 500),
            "data_acesso": agora_iso(),
        },
    }


def validar_conclusao(entrada: dict, total_marcos: int) -> dict:
    if not isinstance(entrada, dict):
        raise ValueError("entrada não é um objeto JSON")
    classificacao = _opcao(entrada, "classificacao", CLASSIFICACOES)
    if total_marcos == 0 and classificacao != "sem_registros_suficientes":
        raise ValueError(
            "nenhum marco foi registrado. Registre marcos com registrar_marco "
            "ou conclua com classificacao 'sem_registros_suficientes'."
        )
    perspectivas_in = entrada.get("perspectivas")
    if not isinstance(perspectivas_in, list):
        raise ValueError("campo 'perspectivas' deve ser uma lista")
    perspectivas = []
    for p in perspectivas_in[:4]:
        if not isinstance(p, dict):
            raise ValueError("cada perspectiva deve ser um objeto")
        perspectivas.append({
            "titulo": _texto(p, "titulo", 80),
            "texto": _texto(p, "texto", 400),
            "sustentacao": _opcao(p, "sustentacao", SUSTENTACOES),
        })
    return {
        "titulo": _texto(entrada, "titulo_caso", 140),
        "tipo_alegacao": _opcao(entrada, "tipo_alegacao", TIPOS_ALEGACAO),
        "classificacao": classificacao,
        "veredito": _texto(entrada, "veredito", 160),
        "sintese": _texto(entrada, "sintese", 1200),
        "limites": _texto(entrada, "limites", 600),
        "perspectivas": perspectivas,
    }
