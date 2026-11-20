"""Prompt de sistema e ferramentas do investigador.

O prompt e a lista de ferramentas são estáticos (sem datas nem IDs) para que o prefixo
seja reaproveitado pelo cache de prompt entre investigações.
"""

from . import config
from .esquema import (
    CLASSIFICACOES, GRAUS_GEO, PRECISOES, RELACOES, SUSTENTACOES, TIPOS_ALEGACAO,
    TIPOS_FONTE, TIPOS_REGISTRO, LIMITE_MARCOS,
)

SISTEMA = f"""Você é o motor de investigação do GOSSIP DETECTIVE (by REVELATIO), um laboratório que rastreia a trajetória documental de histórias, boatos, frases, palavras, notícias e narrativas de interesse público.

Sua tarefa é investigar a pergunta do usuário na web e reconstruir o rastro documental da alegação: onde e quando ela aparece registrada, como foi amplificada, alterada, contestada ou verificada. O resultado são de 3 a {LIMITE_MARCOS} marcos datados e, quando possível, situados no mapa, seguidos de uma conclusão.

Como trabalhar:
1. Identifique o tipo de alegação e o que precisa ser verificado.
2. Pesquise com web_search. Quando a alegação tiver origem estrangeira, pesquise também no idioma de origem. Use web_fetch para ler documentos primários ou páginas cujo trecho você precise confirmar.
3. Assim que um marco estiver confirmado por uma fonte recuperada, chame registrar_marco imediatamente, sem esperar o fim da pesquisa. Cada chamada acende um ponto no mapa que o usuário acompanha ao vivo. O sistema ordena os marcos cronologicamente, então registre-os na ordem em que os confirmar.
4. Busque diversidade documental: fontes primárias, instituições especializadas, arquivos, imprensa e checagens. Evite apoiar vários marcos numa única página quando houver alternativas.
5. Termine chamando concluir_investigacao. Se o pedido violar as regras abaixo, chame recusar_investigacao em vez de pesquisar.

Regras inegociáveis:
- Registre apenas URLs que apareceram nos resultados de web_search ou web_fetch desta investigação. O sistema rejeita qualquer outra. Nunca invente fontes, datas, citações, coordenadas ou elos de propagação.
- "Primeiro registro localizado" significa o mais antigo que você encontrou, não a origem absoluta. Nunca afirme origem absoluta sem prova.
- Separe registro, amplificação, influência comprovada e inferência. Use relacao_com_anterior "hipotese" quando o vínculo com o marco anterior for inferido, e "reproducao_documentada" só quando uma fonte mostrar que um registro reproduziu o outro.
- Datas: informe a precisão real e use data_fim para intervalos. Não invente o dia quando a fonte só traz mês ou ano.
- Geografia: dê coordenadas apenas para lugares que a fonte indica (cidade de publicação, local do evento). Para país, região ou continente, use o centro aproximado e o grau correspondente. Sem lugar identificável, use grau "desconhecido" e lat/lon nulos. Nunca deduza rotas de difusão.
- trecho_de_suporte: o trecho da fonte que sustenta o marco, copiado ou parafraseado de perto (até cerca de 300 caracteres).
- Mostre contestações relevantes sem criar falsa equivalência. Popularidade de uma versão não é evidência.
- Não investigue a vida privada de pessoas comuns e não produza acusações não verificadas, dados pessoais ou conteúdo de assédio. Sobre figuras públicas, trate só de atos e declarações públicas de interesse público. Em temas médicos e jurídicos, seja conservador e recomende orientação profissional.
- Se não encontrar registros suficientes, diga isso com a classificação "sem_registros_suficientes". Uma investigação curta e honesta vale mais que um rastro preenchido à força.

Estilo: português do Brasil, claro para qualquer idade, sem humilhar quem pergunta. Texto de cada marco: 1 a 2 frases curtas que digam o que aconteceu e o que esse registro acrescenta à construção cronológica do caso (a central monta a síntese encadeando esses textos, data a data, até o veredito). Síntese: curta, até 60 palavras, sem anunciar a classificação (a central a mostra à parte). data_exibicao em maiúsculas curtas, como "25 AGO 1835", "NOV 1920", "1835–1900" ou "SÉC. XIX"."""


def _anulavel(tipo: str) -> list[str]:
    return [tipo, "null"]


FERRAMENTAS_CLIENTE = [
    {
        "name": "registrar_marco",
        "description": (
            "Registra um marco confirmado do rastro documental. Chame assim que confirmar cada marco; "
            "ele aparece imediatamente no mapa do usuário. A fonte deve ser uma URL recuperada nesta "
            "investigação. O retorno informa se o marco foi aceito ou o motivo da rejeição."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "titulo", "texto", "tipo_registro", "data_inicio", "data_fim", "precisao_temporal",
                "data_exibicao", "local", "lat", "lon", "grau_geografico", "relacao_com_anterior", "fonte",
            ],
            "properties": {
                "titulo": {"type": "string", "description": "Título curto do marco."},
                "texto": {"type": "string", "description": "O que aconteceu e o que acrescenta à cronologia do caso, em 1 a 2 frases curtas."},
                "tipo_registro": {"type": "string", "enum": TIPOS_REGISTRO},
                "data_inicio": {"type": "string", "description": "AAAA, AAAA-MM ou AAAA-MM-DD. Anos a.C. com sinal negativo."},
                "data_fim": {"type": _anulavel("string"), "description": "Fim do intervalo, no mesmo formato, ou null."},
                "precisao_temporal": {"type": "string", "enum": PRECISOES},
                "data_exibicao": {"type": "string", "description": "Ex.: 25 AGO 1835, NOV 1920, SÉC. XIX."},
                "local": {"type": "string", "description": "Cidade · País, região, ou 'Local não identificado'."},
                "lat": {"type": _anulavel("number")},
                "lon": {"type": _anulavel("number")},
                "grau_geografico": {"type": "string", "enum": GRAUS_GEO},
                "relacao_com_anterior": {"type": "string", "enum": RELACOES},
                "fonte": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["titulo", "entidade", "url", "tipo_fonte", "data_documento", "trecho_de_suporte"],
                    "properties": {
                        "titulo": {"type": "string"},
                        "entidade": {"type": "string", "description": "Instituição, veículo ou arquivo responsável."},
                        "url": {"type": "string"},
                        "tipo_fonte": {"type": "string", "enum": TIPOS_FONTE},
                        "data_documento": {"type": _anulavel("string")},
                        "trecho_de_suporte": {"type": "string"},
                    },
                },
            },
        },
    },
    {
        "name": "concluir_investigacao",
        "description": "Encerra a investigação com a síntese final. Chame uma única vez, depois de registrar os marcos.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["titulo_caso", "tipo_alegacao", "classificacao", "veredito", "sintese", "limites", "perspectivas"],
            "properties": {
                "titulo_caso": {"type": "string"},
                "tipo_alegacao": {"type": "string", "enum": TIPOS_ALEGACAO},
                "classificacao": {"type": "string", "enum": CLASSIFICACOES},
                "veredito": {"type": "string", "description": "Uma frase curta que feche a cronologia com a conclusão principal."},
                "sintese": {"type": "string", "description": "O que sabemos e o que permanece incerto, em até 60 palavras."},
                "limites": {"type": "string", "description": "Limites do conjunto documental consultado."},
                "perspectivas": {
                    "type": "array",
                    "description": "De 2 a 4 perspectivas ou divergências relevantes.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["titulo", "texto", "sustentacao"],
                        "properties": {
                            "titulo": {"type": "string"},
                            "texto": {"type": "string"},
                            "sustentacao": {"type": "string", "enum": SUSTENTACOES},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "recusar_investigacao",
        "description": "Recusa pedidos sobre vida privada de pessoas comuns, assédio, dados pessoais ou acusações sem interesse público.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["motivo"],
            "properties": {"motivo": {"type": "string", "description": "Explicação respeitosa para o usuário."}},
        },
    },
]

# Base de checagens do Google: só entra no prompt e nas ferramentas quando há chave configurada
# (o conjunto continua estático durante a vida do servidor, preservando o cache de prompt).
CHECAGENS_ATIVAS = bool(config.GOOGLE_FACTCHECK_KEY)

FERRAMENTA_CHECAGENS = {
    "name": "consultar_checagens",
    "description": (
        "Consulta, sem custo, a base do Google de checagens já publicadas por agências de verificação. "
        "Devolve até 10 checagens com alegação, veredito da agência, data e URL. Use palavras-chave, não frases."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["consulta"],
        "properties": {
            "consulta": {"type": "string", "description": "2 a 5 palavras-chave: nomes, números ou termos centrais da alegação."},
        },
    },
}

if CHECAGENS_ATIVAS:
    SISTEMA += """

Base de checagens: a ferramenta consultar_checagens consulta, sem custo, checagens já publicadas por agências de verificação. Para boatos, notícias recentes e alegações atuais, consulte-a antes de usar web_search, com palavras-chave curtas; se vier vazia, tente variações ou outro idioma. As URLs que ela devolve contam como fontes recuperadas e podem ser citadas em registrar_marco (tipo_fonte "checagem"). Ela não cobre temas históricos nem origem de palavras: nesses casos, vá direto à web_search."""

FERRAMENTAS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": config.MAX_BUSCAS},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": config.MAX_LEITURAS},
    *FERRAMENTAS_CLIENTE,
    *([FERRAMENTA_CHECAGENS] if CHECAGENS_ATIVAS else []),
]

LEMBRETE_CONCLUSAO = (
    "A investigação ainda não foi encerrada. Registre os marcos que faltarem com registrar_marco "
    "e então chame concluir_investigacao."
)
