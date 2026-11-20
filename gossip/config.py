"""Configuração lida do ambiente e de um arquivo .env opcional na raiz do projeto."""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PUBLICO = RAIZ / "public"
DADOS = RAIZ / "dados"
INVESTIGACOES = DADOS / "investigacoes"


def _carregar_env(caminho: Path) -> None:
    """Lê pares CHAVE=valor sem sobrescrever variáveis já definidas no ambiente."""
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.split(" #", 1)[0].strip().strip('"').strip("'")
        if valor:
            os.environ.setdefault(chave.strip(), valor)


_carregar_env(RAIZ / ".env")

HOST = os.environ.get("GD_HOST", "127.0.0.1")
PORTA = int(os.environ.get("GD_PORTA", "8765"))
MODELO = os.environ.get("GD_MODELO", "claude-opus-5-5")
ESFORCO = os.environ.get("GD_ESFORCO", "high")
MAX_BUSCAS = int(os.environ.get("GD_MAX_BUSCAS", "15"))
MAX_LEITURAS = int(os.environ.get("GD_MAX_LEITURAS", "8"))
MAX_TURNOS = int(os.environ.get("GD_MAX_TURNOS", "16"))
INVESTIGACOES_SIMULTANEAS = int(os.environ.get("GD_SIMULTANEAS", "2"))
# Google Fact Check Tools API (checagens publicadas; gratuita). Sem a chave, tudo segue só com a busca da IA.
GOOGLE_FACTCHECK_KEY = os.environ.get("GOOGLE_FACTCHECK_KEY", "")
# Radar de tendências: validade do cache, buscas por atualização e atualização automática ao abrir a central.
TENDENCIAS_HORAS = float(os.environ.get("GD_TENDENCIAS_HORAS", "6"))
TENDENCIAS_BUSCAS = int(os.environ.get("GD_TENDENCIAS_BUSCAS", "4"))
TENDENCIAS_AUTO = os.environ.get("GD_TENDENCIAS_AUTO", "1") == "1"
# Fallback no servidor quando o classificador de segurança recusa: só para modelos que o aceitam.
FALLBACK = os.environ.get("GD_FALLBACK", "1") == "1" and MODELO in {
    "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5",
}
# Usa o repositório de certificados do sistema (útil atrás de antivírus/proxy que inspeciona TLS).
TRUSTSTORE = os.environ.get("GD_TRUSTSTORE", "1") == "1"


def credenciais_presentes() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # Perfil criado por `ant auth login`
    return (Path.home() / ".config" / "anthropic").is_dir()
