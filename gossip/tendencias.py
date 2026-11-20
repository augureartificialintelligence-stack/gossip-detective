"""Radar de tendências: alegações duvidosas em circulação, levantadas em agências de checagem.

Não há dado público de volume de buscas por boato. Por isso o radar parte das checagens publicadas
nos últimos dias e ordena pela repercussão: quantas checagens distintas trataram da mesma alegação.
Com a chave do Google, as checagens vêm de graça da Fact Check Tools API e a IA só agrupa e ordena
(sem busca na web). Sem a chave, ou se a base vier rala, a IA levanta tudo com web_search.
Cada item precisa citar uma URL efetivamente obtida, como os marcos das investigações.
O resultado fica em cache em disco e é renovado em segundo plano.
"""

import json
import threading
import time
from datetime import date, datetime, timedelta

import anthropic

from . import checagens, config
from .esquema import _DATA, _opcao, _texto, agora_iso, coletar_urls, normalizar_url
from .investigador import _mensagem_erro_api, cliente

ARQUIVO = config.DADOS / "tendencias.json"
LIMITE_ITENS = 8
MINIMO_CHECAGENS_BASE = 6  # abaixo disso a base do Google não sustenta um ranking; usa a busca na web
INTERVALO_MINIMO_S = 300  # atualização manual no máximo a cada 5 min
VEREDITOS = ["falso", "enganoso", "fora_de_contexto", "sem_comprovacao", "satira", "verdadeiro", "em_apuracao"]

SISTEMA_BASE = """Você é o radar de tendências do GOSSIP DETECTIVE, uma central de verificação de informações.

Você recebe a lista de checagens publicadas nos últimos 7 dias por agências de verificação, obtida da base de checagens
do Google. Tarefa: agrupar as checagens que tratam da mesma alegação e apontar as alegações duvidosas que mais
repercutiram. Use somente a lista recebida: não acrescente nada de fora dela.

Regras:
- Cada item usa a URL de uma checagem da lista, copiada exatamente. Prefira a checagem mais recente do grupo; "agencia"
  e "data" são dessa checagem.
- "repercussao" é o número de checagens da lista sobre a mesma alegação (agências diferentes, ou textos diferentes da
  mesma agência). Ordene da maior para a menor repercussão; em empate, a mais recente vem antes.
- "veredito": traduza o rótulo da agência para a opção mais próxima (Falso → falso; Enganoso/Distorcido/Exagerado →
  enganoso; Fora de contexto/Descontextualizado → fora_de_contexto; Sem evidências/Insustentável → sem_comprovacao;
  Sátira → satira; Verdadeiro/Correto → verdadeiro).
- Escreva "alegacao" em português, como a alegação que circula, em tom neutro e em uma frase curta. Não reproduza
  ofensas nem conteúdo sexual explícito.
- Exclua boatos sobre pessoas comuns ou privadas; figuras públicas e instituições podem aparecer.
- Entre 5 e 8 itens, sem repetir a mesma alegação.
- Termine chamando registrar_tendencias uma única vez."""

SISTEMA_BUSCA = """Você é o radar de tendências do GOSSIP DETECTIVE, uma central de verificação de informações.

Tarefa: levantar as alegações duvidosas (boatos, notícias falsas, conteúdos enganosos ou fora de contexto) que mais
circularam nos últimos 7 dias, a partir de checagens publicadas por agências de verificação. Dê prioridade ao Brasil
(Lupa, Aos Fatos, Estadão Verifica, UOL Confere, AFP Checamos, Projeto Comprova, g1 Fato ou Fake, Boatos.org) e inclua
casos internacionais de grande repercussão.

Regras:
- Use web_search para encontrar checagens recentes. Registre somente itens cuja URL de checagem apareceu nos
  resultados da busca, copiada exatamente. Nunca invente URL, data, agência ou veredito.
- Ordene da maior para a menor repercussão: a mesma alegação checada por várias agências ou veículos vem antes;
  em caso de empate, a mais recente vem antes. "repercussao" é o número de checagens distintas que você viu.
- Escreva "alegacao" em português, como a alegação que circula, em tom neutro e em uma frase curta. Não reproduza
  ofensas nem conteúdo sexual explícito.
- Exclua boatos sobre pessoas comuns ou privadas; figuras públicas e instituições podem aparecer.
- Entre 5 e 8 itens, sem repetir a mesma alegação.
- Termine chamando registrar_tendencias uma única vez."""

FERRAMENTA = {
    "name": "registrar_tendencias",
    "description": "Registra a lista final de alegações em alta, da mais para a menos repercutida. Chame uma única vez, ao final.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["itens"],
        "properties": {
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["alegacao", "veredito", "agencia", "url", "data", "tema", "repercussao"],
                    "properties": {
                        "alegacao": {"type": "string", "description": "A alegação que circula, frase curta e neutra (até 160 caracteres)."},
                        "veredito": {"type": "string", "enum": VEREDITOS, "description": "Conclusão da checagem."},
                        "agencia": {"type": "string", "description": "Agência ou veículo que publicou a checagem."},
                        "url": {"type": "string", "description": "URL da checagem, exatamente como apareceu nos resultados de busca."},
                        "data": {"type": "string", "description": "Data de publicação da checagem, AAAA-MM-DD."},
                        "tema": {"type": "string", "description": "Tema em 1 a 3 palavras (ex.: saúde, eleições, clima)."},
                        "repercussao": {"type": "integer", "description": "Número de checagens distintas vistas sobre a mesma alegação."},
                    },
                },
            },
        },
    },
}

LEMBRETE = "Encerre agora chamando registrar_tendencias com os itens que você já confirmou nas buscas."

_trava = threading.Lock()
_estado = {"atualizando": False, "erro": None, "ultimo_pedido": 0.0}


def _validar(entrada: dict, urls_vistas: dict[str, str]) -> tuple[list[dict], list[str]]:
    itens, erros = [], []
    limite_antigo = date.today() - timedelta(days=45)
    for i, bruto in enumerate((entrada or {}).get("itens") or [], start=1):
        try:
            if not isinstance(bruto, dict):
                raise ValueError("item não é um objeto")
            url = _texto(bruto, "url", 2000)
            if normalizar_url(url) not in urls_vistas:
                raise ValueError("URL não apareceu nos resultados da busca")
            data = _texto(bruto, "data", 10)
            m = _DATA.match(data)
            if not m or not m.group(3):
                raise ValueError("data deve ser AAAA-MM-DD")
            if not limite_antigo <= date.fromisoformat(data) <= date.today():
                raise ValueError("checagem fora da janela recente")
            if any(normalizar_url(url) == normalizar_url(x["url"]) for x in itens):
                raise ValueError("checagem repetida")
            itens.append({
                "alegacao": _texto(bruto, "alegacao", 200),
                "veredito": _opcao(bruto, "veredito", VEREDITOS),
                "agencia": _texto(bruto, "agencia", 80),
                "url": url,
                "data": data,
                "tema": _texto(bruto, "tema", 40).lower(),
                "repercussao": max(1, min(int(bruto.get("repercussao") or 1), 99)),
            })
        except (ValueError, TypeError) as erro:
            erros.append(f"item {i}: {erro}")
    return itens[:LIMITE_ITENS], erros


def _checagens_da_base() -> list[dict]:
    """Checagens recentes da base do Google; lista vazia se não houver chave ou a base falhar."""
    if not checagens.disponivel():
        return []
    try:
        return [c for c in checagens.recentes(dias=7) if c["data"]]  # sem data não dá para ordenar nem exibir
    except checagens.ErroChecagens:
        return []


def _gerar() -> dict:
    base = _checagens_da_base()
    if len(base) >= MINIMO_CHECAGENS_BASE:
        urls = {normalizar_url(c["url"]): c["titulo"] for c in base if normalizar_url(c["url"])}
        lista = "\n".join(
            f"{i}. [{c['classificacao'] or 'sem rótulo'}] {c['alegacao']} | {c['agencia']} | {c['data'] or 'sem data'}"
            f" | {c['titulo']} | {c['url']}"
            for i, c in enumerate(base, start=1)
        )
        conteudo = f"Data de hoje: {date.today():%Y-%m-%d}.\n\nChecagens publicadas nos últimos 7 dias ({len(base)}):\n{lista}"
        # Só agrupar e ordenar uma lista pronta: sem busca na web e com esforço baixo.
        dados = _executar_ia(SISTEMA_BASE, [FERRAMENTA], conteudo, urls, "low")
        return {**dados, "fonte": "google_factcheck", "checagens_lidas": len(base)}
    ferramentas = [{"type": "web_search_20260209", "name": "web_search", "max_uses": config.TENDENCIAS_BUSCAS}, FERRAMENTA]
    conteudo = f"Data de hoje: {date.today():%Y-%m-%d}. Levante as tendências agora."
    return {**_executar_ia(SISTEMA_BUSCA, ferramentas, conteudo, {}, config.ESFORCO), "fonte": "busca_web"}


def _executar_ia(sistema: str, ferramentas: list, conteudo: str, urls_vistas: dict[str, str], esforco: str) -> dict:
    inicio = time.monotonic()
    extras = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if config.FALLBACK else {}
    parametros = {
        "model": config.MODELO,
        "max_tokens": 16000,
        "system": sistema,
        "tools": ferramentas,
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": esforco},
        "cache_control": {"type": "ephemeral"},
        **extras,
    }
    messages = [{"role": "user", "content": conteudo}]
    lembrete_enviado = segunda_chance = False
    descartados = 0

    for _turno in range(6):
        with cliente().beta.messages.stream(messages=messages, **parametros) as stream:
            resposta = stream.get_final_message()
        if resposta.stop_reason == "refusal":
            raise RuntimeError("O serviço de IA recusou o levantamento de tendências.")
        for bloco in resposta.content:
            if bloco.type.endswith("_tool_result"):
                coletar_urls(bloco.model_dump(), urls_vistas)
        messages.append({"role": "assistant", "content": resposta.content})

        chamada = next((b for b in resposta.content if b.type == "tool_use" and b.name == FERRAMENTA["name"]), None)
        if chamada:
            itens, erros = _validar(chamada.input, urls_vistas)
            descartados += len(erros)
            if itens or segunda_chance:
                return {
                    "itens": itens,
                    "atualizado_em": agora_iso(),
                    "modelo": config.MODELO,
                    "descartados": descartados,
                    "duracao_s": round(time.monotonic() - inicio, 1),
                }
            segunda_chance = True
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": chamada.id, "is_error": True,
                "content": "Nenhum item válido. " + "; ".join(erros)[:1500] + ". Corrija e chame registrar_tendencias de novo.",
            }]})
            continue
        if resposta.stop_reason == "pause_turn":
            continue
        if lembrete_enviado:
            break
        lembrete_enviado = True
        messages.append({"role": "user", "content": LEMBRETE})
    raise RuntimeError("A IA não concluiu o levantamento de tendências.")


def _ler() -> dict | None:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _executar() -> None:
    try:
        dados = _gerar()
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        _estado["erro"] = None
    except anthropic.APIError as erro:
        _estado["erro"] = _mensagem_erro_api(erro)
    except Exception as erro:  # noqa: BLE001 - o erro vai para a interface, não derruba o servidor
        _estado["erro"] = str(erro) or "Falha ao levantar tendências."
    finally:
        _estado["atualizando"] = False


def _disparar() -> None:
    with _trava:
        if _estado["atualizando"]:
            return
        _estado.update(atualizando=True, ultimo_pedido=time.time())
    threading.Thread(target=_executar, name="tendencias", daemon=True).start()


def _idade_s(dados: dict | None) -> float:
    try:
        return time.time() - datetime.fromisoformat(dados["atualizado_em"]).timestamp()
    except (TypeError, KeyError, ValueError):
        return float("inf")


def obter(forcar: bool = False) -> dict:
    """Devolve o cache atual e, se estiver vencido (ou se pedido), renova em segundo plano."""
    dados = _ler()
    ia = config.credenciais_presentes()
    vencido = _idade_s(dados) > config.TENDENCIAS_HORAS * 3600
    pode_forcar = forcar and time.time() - _estado["ultimo_pedido"] > INTERVALO_MINIMO_S
    if ia and (pode_forcar or (vencido and config.TENDENCIAS_AUTO and not _estado["erro"])):
        _disparar()
    return {
        "itens": (dados or {}).get("itens", []),
        "atualizado_em": (dados or {}).get("atualizado_em"),
        "fonte": (dados or {}).get("fonte", "busca_web"),
        "atualizando": _estado["atualizando"],
        "erro": _estado["erro"],
        "ia_disponivel": ia,
        "validade_horas": config.TENDENCIAS_HORAS,
    }
