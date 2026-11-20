"""Contas de usuário locais: cadastro, login e sessões, guardados em arquivos JSON (sem banco de dados).

Senhas com scrypt e sal aleatório; a sessão é um token aleatório entregue num cookie HttpOnly e
guardado em disco só como hash, para sobreviver ao reinício do servidor.
"""

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid

from . import config
from .esquema import agora_iso

USUARIOS = config.DADOS / "usuarios.json"
SESSOES = config.DADOS / "sessoes.json"
DURACAO_SESSAO_S = 30 * 24 * 3600
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_trava = threading.Lock()


def _ler(caminho) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _gravar(caminho, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


def _hash_senha(senha: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    chave = hashlib.scrypt(senha.encode("utf-8"), salt=sal, dklen=32, **_SCRYPT)
    return f"scrypt${sal.hex()}${chave.hex()}"


def _confere(senha: str, guardada: str) -> bool:
    try:
        _, sal_hex, _ = guardada.split("$")
        return hmac.compare_digest(_hash_senha(senha, bytes.fromhex(sal_hex)), guardada)
    except ValueError:
        return False


def _publico(usuario: dict) -> dict:
    return {"id": usuario["id"], "nome": usuario["nome"], "email": usuario["email"]}


def cadastrar(nome: str, email: str, senha: str) -> dict:
    nome = " ".join(str(nome or "").split())
    email = str(email or "").strip().lower()
    senha = str(senha or "")
    if not 2 <= len(nome) <= 60:
        raise ValueError("Informe um nome entre 2 e 60 caracteres.")
    if not _EMAIL.match(email):
        raise ValueError("Informe um e-mail válido.")
    if not 8 <= len(senha) <= 128:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    with _trava:
        usuarios = _ler(USUARIOS)
        if email in usuarios:
            raise ValueError("Já existe uma conta com este e-mail. Entre com sua senha.")
        usuario = {"id": uuid.uuid4().hex[:12], "nome": nome, "email": email, "senha": _hash_senha(senha), "criado_em": agora_iso()}
        usuarios[email] = usuario
        _gravar(USUARIOS, usuarios)
    return _publico(usuario)


def autenticar(email: str, senha: str) -> dict | None:
    usuario = _ler(USUARIOS).get(str(email or "").strip().lower())
    if usuario and _confere(str(senha or ""), usuario["senha"]):
        return _publico(usuario)
    # Mesmo custo quando o e-mail não existe, para não revelar quais contas existem.
    _hash_senha(str(senha or ""))
    return None


def _chave(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_sessao(usuario: dict) -> str:
    token = secrets.token_urlsafe(32)
    agora = time.time()
    with _trava:
        sessoes = {k: s for k, s in _ler(SESSOES).items() if s["expira"] > agora}
        sessoes[_chave(token)] = {"email": usuario["email"], "expira": agora + DURACAO_SESSAO_S}
        _gravar(SESSOES, sessoes)
    return token


def usuario_da_sessao(token: str | None) -> dict | None:
    if not token:
        return None
    sessao = _ler(SESSOES).get(_chave(token))
    if not sessao or sessao["expira"] < time.time():
        return None
    usuario = _ler(USUARIOS).get(sessao["email"])
    return _publico(usuario) if usuario else None


def encerrar_sessao(token: str | None) -> None:
    if not token:
        return
    with _trava:
        sessoes = _ler(SESSOES)
        if sessoes.pop(_chave(token), None) is not None:
            _gravar(SESSOES, sessoes)
