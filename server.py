"""Servidor do GOSSIP DETECTIVE: arquivos estáticos + API + transmissão SSE das investigações.

Uso:  python server.py   →   http://127.0.0.1:8765
"""

import gzip
import json
import mimetypes
import queue
import sys
import threading
import time
import traceback
import webbrowser
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from gossip import VERSAO, config

# Consoles do Windows podem estar em cp1252; os logs usam acentos e símbolos.
for _saida in (sys.stdout, sys.stderr):
    if hasattr(_saida, "reconfigure"):
        _saida.reconfigure(encoding="utf-8", errors="replace")

if config.TRUSTSTORE:
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

from gossip import arquivo, avaliacoes, contas, tendencias  # noqa: E402

COOKIE = "gd_sessao"
from gossip.investigador import investigar  # noqa: E402

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("font/ttf", ".ttf")

_vagas = threading.BoundedSemaphore(config.INVESTIGACOES_SIMULTANEAS)

# O console do Windows bloqueia escritas (ex.: modo QuickEdit ao clicar na janela);
# o log sai por uma thread própria para nunca travar uma requisição.
_fila_log: queue.SimpleQueue[str] = queue.SimpleQueue()


def _escrever_log() -> None:
    while True:
        linha = _fila_log.get()
        try:
            sys.stderr.write(linha)
            sys.stderr.flush()
        except OSError:
            pass


threading.Thread(target=_escrever_log, name="log", daemon=True).start()

_cache_gzip: dict[Path, tuple[float, bytes]] = {}


def _gzip(alvo: Path) -> bytes:
    """Versão gzip de um arquivo estático, guardada em memória até o arquivo mudar (o atlas cai de ~750 KB para ~200 KB)."""
    mtime = alvo.stat().st_mtime
    guardado = _cache_gzip.get(alvo)
    if not guardado or guardado[0] != mtime:
        guardado = (mtime, gzip.compress(alvo.read_bytes(), compresslevel=6, mtime=0))
        _cache_gzip[alvo] = guardado
    return guardado[1]


class Manipulador(BaseHTTPRequestHandler):
    server_version = f"GossipDetective/{VERSAO}"

    def log_message(self, formato, *args):
        _fila_log.put(f"[{self.log_date_time_string()}] {formato % args}\n")

    # ------------------------------------------------------------ respostas

    def _json(self, dados, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _estatico(self, caminho: str) -> None:
        relativo = caminho.lstrip("/") or "index.html"
        alvo = (config.PUBLICO / relativo).resolve()
        if not alvo.is_relative_to(config.PUBLICO) or not alvo.is_file():
            self._json({"erro": "não encontrado"}, 404)
            return
        corpo = alvo.read_bytes()
        tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        textual = tipo.startswith("text/") or tipo in ("application/javascript", "application/json")
        if textual:
            tipo += "; charset=utf-8"
        comprimir = textual and len(corpo) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "")
        if comprimir:
            corpo = _gzip(alvo)
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        if comprimir:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(corpo)

    def _sse(self, evento: str, dados) -> None:
        bloco = f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"
        self.wfile.write(bloco.encode("utf-8"))
        self.wfile.flush()

    # ------------------------------------------------------------ sessão

    def _token(self) -> str | None:
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        return cookies[COOKIE].value if COOKIE in cookies else None

    def _cookie_sessao(self, token: str, max_age: int) -> str:
        return f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"

    def _json_com_cookie(self, dados, cookie: str, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo_json(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if not 0 < tamanho <= 10_000:
            return {}
        try:
            dados = json.loads(self.rfile.read(tamanho))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return dados if isinstance(dados, dict) else {}

    # ------------------------------------------------------------ rotas

    def do_POST(self):
        rota = urlsplit(self.path).path
        if rota == "/api/cadastro":
            dados = self._corpo_json()
            try:
                usuario = contas.cadastrar(dados.get("nome"), dados.get("email"), dados.get("senha"))
            except ValueError as erro:
                self._json({"erro": str(erro)}, 400)
                return
            self._json_com_cookie({"usuario": usuario}, self._cookie_sessao(contas.criar_sessao(usuario), contas.DURACAO_SESSAO_S))
        elif rota == "/api/login":
            dados = self._corpo_json()
            usuario = contas.autenticar(dados.get("email"), dados.get("senha"))
            if not usuario:
                time.sleep(0.6)  # freia tentativas em sequência
                self._json({"erro": "E-mail ou senha incorretos."}, 401)
                return
            self._json_com_cookie({"usuario": usuario}, self._cookie_sessao(contas.criar_sessao(usuario), contas.DURACAO_SESSAO_S))
        elif rota == "/api/logout":
            contas.encerrar_sessao(self._token())
            self._json_com_cookie({"ok": True}, self._cookie_sessao("", 0))
        elif rota == "/api/avaliacoes":
            usuario = contas.usuario_da_sessao(self._token())
            if not usuario:
                self._json({"erro": "Entre na sua conta para avaliar."}, 401)
                return
            dados = self._corpo_json()
            caso_id = str(dados.get("caso") or "")
            if not arquivo.carregar_caso(caso_id):
                self._json({"erro": "Investigação não encontrada."}, 404)
                return
            try:
                avaliacoes.avaliar(caso_id, usuario, dados.get("nota"), dados.get("comentario"))
            except ValueError as erro:
                self._json({"erro": str(erro)}, 400)
                return
            self._json(avaliacoes.resumo(caso_id, usuario["id"]))
        else:
            self._json({"erro": "rota desconhecida"}, 404)

    def do_GET(self):
        url = urlsplit(self.path)
        rota = url.path
        if rota == "/api/status":
            self._json({
                "ia_disponivel": config.credenciais_presentes(),
                "versao": VERSAO,
                "checagens_google": bool(config.GOOGLE_FACTCHECK_KEY),
            })
            return
        if not rota.startswith("/api/"):
            self._estatico(rota)
            return
        usuario = contas.usuario_da_sessao(self._token())
        if rota == "/api/sessao":
            self._json({"usuario": usuario})
        elif not usuario:
            self._json({"erro": "Entre na sua conta para continuar."}, 401)
        elif rota == "/api/casos":
            self._json({"verificados": arquivo.casos_verificados(), "recentes": arquivo.investigacoes_recentes(60, usuario["id"])})
        elif rota == "/api/bombando":
            self._json({"itens": arquivo.mais_investigadas()})
        elif rota == "/api/avaliacoes":
            self._json(avaliacoes.resumo(parse_qs(url.query).get("caso", [""])[0], usuario["id"]))
        elif rota == "/api/tendencias":
            self._json(tendencias.obter(forcar=parse_qs(url.query).get("atualizar") == ["1"]))
        elif rota.startswith("/api/casos/"):
            caso = arquivo.carregar_caso(rota.removeprefix("/api/casos/"))
            if caso:
                self._json(caso)
            else:
                self._json({"erro": "caso não encontrado"}, 404)
        elif rota == "/api/investigar":
            pergunta = " ".join(parse_qs(url.query).get("q", [""])[0].split())
            self._investigar(pergunta, usuario)
        else:
            self._json({"erro": "rota desconhecida"}, 404)

    def _investigar(self, pergunta: str, usuario: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        if not 3 <= len(pergunta) <= 300:
            self._sse("erro", {"mensagem": "A pergunta deve ter entre 3 e 300 caracteres."})
            return
        if not config.credenciais_presentes():
            self._sse("erro", {"mensagem": "IA não configurada: defina ANTHROPIC_API_KEY no arquivo .env e reinicie."})
            return
        if not _vagas.acquire(blocking=False):
            self._sse("erro", {"mensagem": "A central já está processando o máximo de missões. Tente em instantes."})
            return

        gerador = investigar(pergunta)
        try:
            for evento, dados in gerador:
                if evento == "conclusao":
                    dados["usuario"] = usuario["id"]
                    arquivo.salvar_investigacao(dados)
                self._sse(evento, dados)
            self._sse("fim", {})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.log_message("cliente desconectou; missão abortada")
        except Exception:  # noqa: BLE001 — qualquer falha vira mensagem para o operador
            _fila_log.put(traceback.format_exc())
            try:
                self._sse("erro", {"mensagem": "Falha interna no motor de investigação. Veja o terminal do servidor."})
            except OSError:
                pass
        finally:
            gerador.close()
            _vagas.release()


def main() -> None:
    servidor = ThreadingHTTPServer((config.HOST, config.PORTA), Manipulador)
    servidor.daemon_threads = True
    endereco = f"http://{config.HOST}:{config.PORTA}"
    print(f"\n  ◈ GOSSIP DETECTIVE {VERSAO}")
    print(f"  Central de comando: {endereco}")
    print(f"  IA: {'ONLINE · ' + config.MODELO if config.credenciais_presentes() else 'OFFLINE (defina ANTHROPIC_API_KEY no .env)'}")
    print("  Ctrl+C para encerrar.\n")
    if "--abrir" in sys.argv:
        webbrowser.open(endereco)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Central encerrada.")


if __name__ == "__main__":
    main()
