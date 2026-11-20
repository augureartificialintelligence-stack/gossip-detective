"""Importa os catálogos editoriais (docs/GOSSIP_100_*.md) para dados/catalogos.json.

Cada ficha leva a orientação editorial do próprio documento: o que significa a classe preliminar e os cuidados
específicos (engano militar não é "fake news", uma afirmação falsificável por ficha, proteção de vítimas,
"hoax" no nome não implica fraude etc.). A IA recebe essa orientação ao investigar a ficha.
Uso:  python ferramentas/importar_catalogos.py
"""

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_LINHA = re.compile(r"^\|\s*([DH]\d{3})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def _faixa(prefixo: str, inicio: int, fim: int) -> list[str]:
    return [f"{prefixo}{n:03d}" for n in range(inicio, fim + 1)]


ORIENTACAO = {
    "desinformacao": (
        "Ficha {id} do catálogo REVELATIO de desinformação, propaganda e engano estratégico. É uma pauta candidata, "
        "não uma atribuição de culpa já provada. Classe preliminar: {classe} (D = desinformação deliberada "
        "alegada/documentada; P = propaganda ou manipulação narrativa; M = engano militar estratégico; B = boato viral "
        "de autoria incerta; C = controvérsia a investigar). Época: {epoca}. Região: {regiao}. Investigue uma afirmação "
        "falsificável específica dentro do tema e reconstrua a cronologia documentada; com menos de três marcos "
        "confiáveis, publique menos em vez de inventar. Autoria e intenção exigem evidência própria: assinale a diferença "
        "de padrão probatório e distinga atribuição técnica de pesquisadores, sanções governamentais, processos judiciais "
        "e autoria juridicamente estabelecida. Mostre as versões divergentes, separando o que é sustentado, contestado ou refutado."
    ),
    "hoaxes": (
        "Ficha {id} do catálogo REVELATIO de hoaxes, fraudes e mistificações. É uma pauta candidata, não uma fraude "
        "comprovada: o nome do catálogo não implica conclusão. Tipo preliminar: {classe}. Janela aproximada: {epoca} "
        "(não é data certificada do primeiro registro). Região: {regiao}. Verifique primeiro se o episódio existiu como "
        "descrito; se a documentação não o sustentar, diga isso (sem_registros_suficientes ou refutada, conforme o caso). "
        "Reconstrua a cronologia com o documento original sempre que possível e não preencha datas, locais, autores ou "
        "intenções por inferência."
    ),
}

CUIDADOS = [
    (_faixa("D", 5, 23), "Engano de guerra dirigido a um adversário militar, não necessariamente falsidade cívica contra a "
     "população: não o trate como fake news."),
    (["D031", "D033", "D042", *_faixa("D", 44, 51), "D055", *_faixa("D", 57, 64), "D069", "D092", "D095", "D099", "D100"],
     "O tema mistura interpretações, eventos reais e alegações públicas distintas: investigue uma afirmação falsificável, "
     "sem rotular o assunto inteiro como falso."),
    (["D067"], "Proteja as pessoas afetadas: nunca reproduza boatos difamatórios como dúvidas abertas e não exponha "
     "vítimas ou familiares além do estritamente necessário."),
    (["D002", "D076"], "Ângulo relacionado (D002/D076, origem do boato sobre o HIV): concentre-se no recorte desta ficha."),
    (["D001", "D084", "D085", "D086"], "Ângulo relacionado da Operação Doppelganger (D001/D084–D086): concentre-se no recorte desta ficha."),
    (["D080", "D083"], "Ângulo relacionado da Ghostwriter (D080/D083): concentre-se no recorte desta ficha."),
    (["D094", "H089"], "Mesmo tema em outro catálogo (D094/H089, Fantasma de Kiev): concentre-se no recorte desta ficha."),
    (["D095", "H090"], "Mesmo tema em outro catálogo (D095/H090, Ilha das Cobras): concentre-se no recorte desta ficha."),
    (["H013", "H019", "H030", "H033", "H039", "H041", "H054", "H062", "H068", "H076", "H092", "H099"],
     "Entrada potencialmente sobreposta ou de delimitação incerta, talvez uma hipótese de pauta ainda não confirmada: "
     "confirme primeiro que o episódio existe."),
    (["H038", "H042", "H046", "H061", "H071", "H088"],
     "A palavra hoax não implica conclusão de fraude: classifique somente depois da análise."),
    (["H075", "H082", "H083", "H084"], "Risco científico, reputacional ou de pânico moral: seja conservador, não amplifique "
     "a alegação e trate as pessoas citadas com cuidado."),
    (["H059", "D004"], "Texto de ódio antissemita: não reproduza trechos ofensivos; trate da falsificação e da difusão."),
]

COLECOES = [
    ("desinformacao", "GOSSIP_100_DESINFORMACAO", "100 casos de desinformação, propaganda e engano estratégico"),
    ("hoaxes", "GOSSIP_100_HOAXES", "100 grandes hoaxes, fraudes e mistificações"),
]


def _limpar(texto: str) -> str:
    return " ".join(texto.replace("*", "").replace("“", "\"").replace("”", "\"").split())


def main() -> None:
    cuidados: dict[str, list[str]] = {}
    for ids, texto in CUIDADOS:
        for i in ids:
            cuidados.setdefault(i, []).append(texto)
    saida = []
    for colecao_id, prefixo, titulo in COLECOES:
        origem = max((RAIZ / "docs").glob(f"{prefixo}*.md"))
        itens = []
        for linha in origem.read_text(encoding="utf-8").splitlines():
            m = _LINHA.match(linha.strip())
            if not m:
                continue
            fid, caso, epoca, regiao, classe = (_limpar(g) for g in m.groups())
            item = {"id": fid, "caso": caso, "epoca": epoca, "regiao": regiao, "classe": classe}
            orientacao = ORIENTACAO[colecao_id].format(**item)
            if fid in cuidados:
                orientacao += " Cuidado específico: " + " ".join(cuidados[fid])
            item["orientacao"] = orientacao
            itens.append(item)
        saida.append({"id": colecao_id, "titulo": titulo, "origem": origem.name, "itens": itens})
        print(f"{colecao_id}: {len(itens)} fichas de {origem.name}")
    (RAIZ / "dados" / "catalogos.json").write_text(json.dumps({"colecoes": saida}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
