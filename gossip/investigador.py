"""Laço de investigação com Claude + busca na web, emitindo eventos em tempo real.

`investigar()` é um gerador de tuplas (evento, dados). O servidor repassa cada evento ao
navegador via SSE; por isso o mapa só acende um ponto quando um marco foi de fato
validado contra uma fonte recuperada (princípio 9 do conceito fundador).
"""

import time
import uuid
from datetime import date

import anthropic

from . import VERSAO, checagens, config, fontes
from .esquema import (
    LIMITE_MARCOS, agora_iso, coletar_urls, normalizar_url, ordenar_marcos, validar_conclusao, validar_marco,
)
from .prompts import FERRAMENTAS, LEMBRETE_CONCLUSAO, SISTEMA

_cliente: anthropic.Anthropic | None = None


def cliente() -> anthropic.Anthropic:
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic()
    return _cliente


def _resumo(texto: str, limite: int = 260) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _parametros_modelo() -> dict:
    extras = {}
    if config.FALLBACK:
        extras = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return {
        "model": config.MODELO,
        "max_tokens": 32000,
        "system": SISTEMA,
        "tools": FERRAMENTAS,
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": config.ESFORCO},
        "cache_control": {"type": "ephemeral"},
        **extras,
    }


def _texto_checagens(achados: list[dict]) -> str:
    if not achados:
        return "Nenhuma checagem encontrada para essa consulta. Tente outras palavras-chave ou siga com web_search."
    linhas = [
        f"- [{a['classificacao'] or 'sem rótulo'}] {a['alegacao']} | {a['agencia']}, {a['data'] or 'data não informada'}"
        f" | {a['titulo']} | {a['url']}"
        for a in achados
    ]
    return f"{len(achados)} checagens publicadas:\n" + "\n".join(linhas)


def _mensagem_erro_api(erro: Exception) -> str:
    if isinstance(erro, anthropic.AuthenticationError):
        return "Credencial da API recusada. Verifique ANTHROPIC_API_KEY no arquivo .env."
    if isinstance(erro, anthropic.PermissionDeniedError):
        return "A chave da API não tem permissão para este modelo ou para a busca na web."
    if isinstance(erro, anthropic.NotFoundError):
        return f"Modelo '{config.MODELO}' não encontrado para esta conta."
    if isinstance(erro, anthropic.RateLimitError):
        return "Limite de requisições atingido. Aguarde um minuto e tente de novo."
    if isinstance(erro, anthropic.BadRequestError):
        return f"Requisição recusada pela API: {getattr(erro, 'message', erro)}"
    if isinstance(erro, anthropic.APIStatusError):
        return f"Erro no serviço de IA ({erro.status_code}). Tente novamente em instantes."
    if isinstance(erro, anthropic.APIConnectionError):
        return "Sem conexão com o serviço de IA. Verifique a internet ou o proxy/antivírus."
    return f"Falha inesperada: {erro}"


def investigar(pergunta: str, orientacao: str | None = None, caso_id: str | None = None):
    """`orientacao`: contexto editorial opcional (ex.: ficha de um catálogo) anexado à pergunta."""
    inicio = time.monotonic()
    caso_id = caso_id or f"{date.today():%Y%m%d}-{uuid.uuid4().hex[:6]}"
    urls_vistas: dict[str, str] = {}
    marcos: list[dict] = []
    rejeitados = 0
    buscas: list[str] = []
    leituras = 0
    consultas_checagem = 0
    tokens = {"entrada": 0, "saida": 0, "cache": 0, "cache_gravado": 0}
    conclusao: dict | None = None
    recusa: str | None = None
    lembrete_enviado = False

    conteudo = f"Pergunta a investigar: {pergunta}\n\nData de hoje: {date.today():%Y-%m-%d}"
    if orientacao:
        conteudo += f"\n\nOrientação editorial para este caso:\n{orientacao}"
    messages = [{"role": "user", "content": conteudo}]

    yield "fase", {"fase": "ingestao"}
    yield "log", {"tipo": "sistema", "texto": f"Missão {caso_id} aberta · modelo {config.MODELO}"}

    def processar_ferramenta(bloco) -> tuple[dict, bool]:
        """Valida uma chamada de ferramenta do cliente. Retorna (tool_result, encerra?)."""
        nonlocal rejeitados, conclusao, recusa
        resultado = {"type": "tool_result", "tool_use_id": bloco.id}
        try:
            if bloco.name == "registrar_marco":
                if len(marcos) >= LIMITE_MARCOS:
                    raise ValueError(f"limite de {LIMITE_MARCOS} marcos atingido; chame concluir_investigacao.")
                marco = validar_marco(bloco.input, urls_vistas, len(marcos) + 1)
                referencia = fontes.identificar(marco["fonte"]["url"])
                if referencia:  # proveniência na matriz REVELATIO (F001–F070)
                    marco["fonte"]["matriz_id"] = referencia["id"]
                    marco["fonte"]["matriz_funcoes"] = referencia["funcoes"]
                marcos.append(marco)
                resultado["content"] = f"Marco {marco['id']} aceito ({len(marcos)}/{LIMITE_MARCOS})."
                return resultado, False
            if bloco.name == "concluir_investigacao":
                conclusao = validar_conclusao(bloco.input, len(marcos))
                resultado["content"] = "Investigação encerrada."
                return resultado, True
            if bloco.name == "recusar_investigacao":
                recusa = " ".join(str((bloco.input or {}).get("motivo", "")).split())[:500] or "Pedido fora do escopo."
                resultado["content"] = "Recusa registrada."
                return resultado, True
            raise ValueError(f"ferramenta desconhecida: {bloco.name}")
        except ValueError as erro:
            rejeitados += 1
            resultado.update(is_error=True, content=f"Rejeitado: {erro}")
            return resultado, False

    try:
        for _turno in range(config.MAX_TURNOS):
            resultados_pendentes: dict[str, dict] = {}
            encerrar = False

            with cliente().beta.messages.stream(messages=messages, **_parametros_modelo()) as stream:
                for evento in stream:
                    if evento.type != "content_block_stop":
                        continue
                    bloco = evento.content_block
                    tipo = bloco.type

                    if tipo == "server_tool_use":
                        entrada = bloco.input if isinstance(bloco.input, dict) else {}
                        if bloco.name == "web_search" and entrada.get("query"):
                            buscas.append(entrada["query"])
                            if len(buscas) == 1:
                                yield "fase", {"fase": "recuperacao"}
                            yield "busca", {"consulta": entrada["query"], "total": len(buscas)}
                        elif bloco.name == "web_fetch" and entrada.get("url"):
                            leituras += 1
                            yield "log", {"tipo": "leitura", "texto": f"Lendo documento: {entrada['url']}"}

                    elif tipo.endswith("_tool_result"):
                        antes = set(urls_vistas)
                        coletar_urls(bloco.model_dump(), urls_vistas)
                        novas = [u for u in urls_vistas if u not in antes]
                        if novas:
                            yield "fontes", {
                                "total": len(urls_vistas),
                                "novas": [{"url": u, "titulo": urls_vistas[u]} for u in novas[:8]],
                            }

                    elif tipo == "thinking" and getattr(bloco, "thinking", ""):
                        yield "log", {"tipo": "analise", "texto": _resumo(bloco.thinking)}

                    elif tipo == "text" and bloco.text.strip():
                        yield "log", {"tipo": "analise", "texto": _resumo(bloco.text)}

                    elif tipo == "fallback":
                        yield "log", {"tipo": "sistema", "texto": "Modelo de contingência assumiu esta etapa."}

                    elif tipo == "tool_use" and bloco.name == "consultar_checagens":
                        # Consulta gratuita à base de checagens do Google; as URLs devolvidas viram fontes válidas.
                        consulta = " ".join(str((bloco.input or {}).get("consulta", "")).split())[:200]
                        consultas_checagem += 1
                        try:
                            achados = checagens.buscar(consulta)
                            conteudo = _texto_checagens(achados)
                        except checagens.ErroChecagens as erro:
                            achados, conteudo = [], f"Base de checagens indisponível ({erro}). Siga com web_search."
                        resultados_pendentes[bloco.id] = {"type": "tool_result", "tool_use_id": bloco.id, "content": conteudo}
                        if consultas_checagem == 1 and not buscas:
                            yield "fase", {"fase": "recuperacao"}
                        yield "log", {"tipo": "checagem", "texto": f"Base de checagens: “{consulta}” → {len(achados)} resultado(s)"}
                        for a in achados[:3]:
                            yield "log", {"tipo": "checagem", "texto": f"[{a['classificacao']}] {a['agencia']}: {_resumo(a['alegacao'], 140)}"}
                        antes = set(urls_vistas)
                        for a in achados:
                            chave = normalizar_url(a["url"])
                            if chave:
                                urls_vistas.setdefault(chave, a["titulo"])
                        novas = [u for u in urls_vistas if u not in antes]
                        if novas:
                            yield "fontes", {
                                "total": len(urls_vistas),
                                "novas": [{"url": u, "titulo": urls_vistas[u]} for u in novas[:8]],
                            }

                    elif tipo == "tool_use":
                        resultado, fim = processar_ferramenta(bloco)
                        resultados_pendentes[bloco.id] = resultado
                        encerrar = encerrar or fim
                        if bloco.name == "registrar_marco":
                            if resultado.get("is_error"):
                                yield "rejeitado", {"motivo": resultado["content"], "total": rejeitados}
                            else:
                                if len(marcos) == 1:
                                    yield "fase", {"fase": "verificacao"}
                                if len(marcos) == 2:
                                    yield "fase", {"fase": "cronologia"}
                                yield "marco", marcos[-1]
                        elif resultado.get("is_error"):
                            yield "log", {"tipo": "rejeitado", "texto": resultado["content"]}

                resposta = stream.get_final_message()

            uso = resposta.usage
            tokens["entrada"] += uso.input_tokens or 0
            tokens["saida"] += uso.output_tokens or 0
            tokens["cache"] += getattr(uso, "cache_read_input_tokens", 0) or 0
            tokens["cache_gravado"] += getattr(uso, "cache_creation_input_tokens", 0) or 0

            if resposta.stop_reason == "refusal":
                yield "erro", {"mensagem": "O serviço de IA recusou este pedido por política de segurança."}
                return
            if encerrar:
                break

            messages.append({"role": "assistant", "content": resposta.content})
            if resposta.stop_reason == "pause_turn":
                continue

            chamadas = [b for b in resposta.content if b.type == "tool_use"]
            if chamadas:
                if resposta.stop_reason == "max_tokens":
                    for b in chamadas:
                        resultados_pendentes[b.id] = {
                            "type": "tool_result", "tool_use_id": b.id, "is_error": True,
                            "content": "Entrada truncada pelo limite de tokens; reenvie a chamada.",
                        }
                messages.append({"role": "user", "content": [resultados_pendentes[b.id] for b in chamadas]})
                continue

            # Terminou sem concluir: um lembrete, já que tool_choice forçado não existe neste modelo.
            if lembrete_enviado:
                break
            lembrete_enviado = True
            messages.append({"role": "user", "content": LEMBRETE_CONCLUSAO})

    except anthropic.APIError as erro:
        yield "erro", {"mensagem": _mensagem_erro_api(erro)}
        return

    if recusa:
        yield "recusa", {"motivo": recusa}
        return
    if conclusao is None:
        if not marcos:
            yield "erro", {"mensagem": "A investigação terminou sem marcos nem conclusão. Reformule a pergunta e tente de novo."}
            return
        conclusao = {
            "titulo": pergunta[:140], "tipo_alegacao": "rumor", "classificacao": "inconclusiva",
            "veredito": "Investigação interrompida antes da síntese final.",
            "sintese": "Os marcos abaixo foram validados, mas a IA não concluiu a análise dentro do limite de etapas.",
            "limites": "Síntese não produzida; trate os marcos como material bruto de verificação.",
            "perspectivas": [],
        }

    yield "fase", {"fase": "sintese"}
    caso = {
        "id": caso_id,
        "origem": "ia",
        "versao": 1,
        "pergunta": pergunta,
        **conclusao,
        "marcos": ordenar_marcos(marcos),
        "fontes_consultadas": [{"url": u, "titulo": t} for u, t in list(urls_vistas.items())[:80]],
        "estatisticas": {
            "buscas": len(buscas),
            "leituras": leituras,
            "consultas_checagem": consultas_checagem,
            "fontes": len(urls_vistas),
            "marcos": len(marcos),
            "marcos_matriz": sum(1 for m in marcos if m["fonte"].get("matriz_id")),
            "rejeitados": rejeitados,
            "duracao_s": round(time.monotonic() - inicio, 1),
            "tokens": tokens,
        },
        "modelo": config.MODELO,
        "motor": f"GOSSIP DETECTIVE {VERSAO}",
        "criado_em": agora_iso(),
        "ultima_revisao": agora_iso(),
    }
    yield "conclusao", caso
