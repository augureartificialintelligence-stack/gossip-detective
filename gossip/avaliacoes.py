"""Avaliações e comentários dos usuários sobre cada investigação, guardados em JSON local.

Uma avaliação por usuário e por caso (reenviar atualiza a anterior).
"""

import json
import threading

from . import config
from .esquema import agora_iso

ARQUIVO = config.DADOS / "avaliacoes.json"
LIMITE_COMENTARIO = 1000
_trava = threading.Lock()


def _ler() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def avaliar(caso_id: str, usuario: dict, nota, comentario) -> None:
    if isinstance(nota, bool) or not isinstance(nota, int) or not 1 <= nota <= 5:
        raise ValueError("Escolha uma nota de 1 a 5 estrelas.")
    comentario = " ".join(str(comentario or "").split())
    if len(comentario) > LIMITE_COMENTARIO:
        raise ValueError(f"O comentário pode ter até {LIMITE_COMENTARIO} caracteres.")
    with _trava:
        dados = _ler()
        dados.setdefault(caso_id, {})[usuario["id"]] = {
            "nome": usuario["nome"].split(" ")[0], "nota": nota, "comentario": comentario, "data": agora_iso(),
        }
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        temporario = ARQUIVO.with_suffix(".tmp")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        temporario.replace(ARQUIVO)


def resumo(caso_id: str, usuario_id: str | None) -> dict:
    """Média, total, a avaliação do próprio usuário e os comentários (mais recentes primeiro)."""
    avaliacoes = _ler().get(caso_id, {})
    notas = [a["nota"] for a in avaliacoes.values()]
    minha = avaliacoes.get(usuario_id) if usuario_id else None
    comentarios = sorted(
        ({"nome": a["nome"], "nota": a["nota"], "comentario": a["comentario"], "data": a["data"], "meu": uid == usuario_id}
         for uid, a in avaliacoes.items() if a["comentario"]),
        key=lambda c: c["data"], reverse=True,
    )
    return {
        "media": round(sum(notas) / len(notas), 1) if notas else None,
        "total": len(notas),
        "minha": {"nota": minha["nota"], "comentario": minha["comentario"]} if minha else None,
        "comentarios": comentarios,
    }
