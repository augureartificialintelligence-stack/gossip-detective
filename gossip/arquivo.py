"""Arquivo de casos: dossiês verificados por curadoria e investigações salvas da IA."""

import json
import re
import threading
import unicodedata
from datetime import datetime, timedelta, timezone

from . import config

_ID_VALIDO = re.compile(r"^[a-z0-9-]{3,40}$")
_trava = threading.Lock()


def casos_verificados() -> list[dict]:
    caminho = config.DADOS / "casos_verificados.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def salvar_investigacao(caso: dict) -> None:
    config.INVESTIGACOES.mkdir(parents=True, exist_ok=True)
    destino = config.INVESTIGACOES / f"{caso['id']}.json"
    with _trava:
        destino.write_text(json.dumps(caso, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_caso(caso_id: str) -> dict | None:
    for caso in casos_verificados():
        if caso["id"] == caso_id:
            return caso
    if not _ID_VALIDO.match(caso_id):
        return None
    caminho = config.INVESTIGACOES / f"{caso_id}.json"
    if not caminho.is_file():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def _investigacoes():
    """Investigações salvas, da mais recente para a mais antiga."""
    if not config.INVESTIGACOES.is_dir():
        return
    for caminho in sorted(config.INVESTIGACOES.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            yield json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue


def investigacoes_recentes(limite: int = 12, usuario_id: str | None = None) -> list[dict]:
    """Histórico do usuário. Missões anteriores ao login (sem dono) aparecem para todos."""
    resumo = []
    for caso in _investigacoes():
        if caso.get("usuario") not in (None, usuario_id):
            continue
        resumo.append({
            "id": caso["id"], "pergunta": caso["pergunta"], "titulo": caso["titulo"],
            "classificacao": caso["classificacao"], "criado_em": caso["criado_em"],
        })
        if len(resumo) >= limite:
            break
    return resumo


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", texto).split())


def mais_investigadas(dias: int = 7, limite: int = 20, minimo: int = 6) -> list[dict]:
    """Pesquisas feitas na central (todos os usuários) nos últimos dias: as mais repetidas primeiro e,
    no empate, as mais recentes. Toda pesquisa concluída entra; cada item aponta para a investigação
    mais recente daquela pergunta. Com menos de `minimo` itens, completa com os dossiês verificados.
    """
    corte = datetime.now(timezone.utc) - timedelta(days=dias)
    grupos: dict[str, dict] = {}
    for caso in _investigacoes():
        try:
            if datetime.fromisoformat(caso["criado_em"]) < corte:
                continue
        except (KeyError, ValueError):
            continue
        chave = _normalizar(caso["pergunta"])
        grupo = grupos.setdefault(chave, {"pergunta": caso["pergunta"], "total": 0, "caso_id": caso["id"], "origem": "investigada"})
        grupo["total"] += 1
    ranking = sorted(grupos.values(), key=lambda g: -g["total"])[:limite]
    vistos = set(grupos)
    for caso in casos_verificados():
        if len(ranking) >= minimo:
            break
        if _normalizar(caso["pergunta"]) not in vistos:
            ranking.append({"pergunta": caso["pergunta"], "total": 0, "caso_id": caso["id"], "origem": "sugestao"})
    return ranking
