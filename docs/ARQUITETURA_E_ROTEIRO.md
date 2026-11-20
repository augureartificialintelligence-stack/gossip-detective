# GOSSIP DETECTIVE — Arquitetura, roadmap e validação v0.1

## Jornada do usuário
Entrada (tema / texto / link) → classificação do tipo de alegação → busca de registros → extração de afirmações e citações → cruzamento de fontes → identificação de conflitos e lacunas → ordenação por tempo e geografia → 3–9 marcos → síntese e links → feedback / contestação.

## Fluxo de produção futura (não implementado no MVP)
1. **Ingestão:** página, texto, link e metadados; detecção de entidade e idioma.
2. **Recuperação:** fontes primárias + instituições especializadas por domínio + arquivos web. Registrar URL, timestamp, data do documento e data de acesso.
3. **Verificação:** cada alegação vinculada a trechos auditáveis; classificar cada vínculo como suporte, contradiz, contextualiza ou não sustenta.
4. **Temporalidade:** distinguir data do fato, publicação, revisão e primeiro registro localizado.
5. **Geografia:** geolocalizar apenas os eventos e publicações explicitamente situados; jamais inventar rotas de propagação.
6. **Síntese:** seleção de 3–9 marcos com diversidade documental e cobertura das divergências; não é um mero resumo de resultados de busca.
7. **Segurança:** limitar vida privada, acusações não verificadas, dados pessoais, assédio; exigir revisão especial de temas médico-jurídicos e reputacionais.
8. **Observabilidade:** registrar qualidade das evidências, links quebrados, correções, denúncias e auditoria editorial.

## Estrutura de dados mínima
Case: id, pergunta, tipo, escopo, resposta, limites, versão, última revisão.
Moment: id, título, data_início, data_fim, precisão_temporal, local, grau_geográfico, texto, tipo_de_registro, citation_ids.
Citation: título, entidade, url, tipo_fonte, data_documento, trecho_de_suporte, data_acesso, hash opcional.
Perspective: afirmação, fontes_de_suporte, objeções, consenso/desacordo.
Relationship: origem_momento, destino_momento, tipo (cronologia, reprodução documentada, hipótese), evidência.

## MVP entregue
- Página HTML única, responsiva e sem bibliotecas externas.
- Três casos: Grande Farsa Lunar, palavra robô e rendição alemã em 1945.
- Animação de 12 s com opção de pular; marcador geográfico aproximado e data/local por registro.
- Linha cronológica com links, perspectivas e ressalvas.
- Busca de exemplos por seleção; entradas inéditas recebem uma mensagem honesta de não cobertura.
- Feedback copiável, sem transmissão ou armazenamento no servidor.

## Teste com pessoas conhecidas
Envie a página sem explicação detalhada. Peça que a pessoa explore um caso e responda ao formulário copiável. Observe: entendeu o propósito? Fonte abriu corretamente? Animação foi útil? Sentiu confiança sem aceitar cegamente? Qual tema gostaria de investigar? O que achou das divergências?

**Critérios iniciais de aceitação:** funcionamento em desktop/celular; nenhuma fonte inventada; 100% dos marcos com referência; alegações qualificadas; sem coleta oculta de dados; ao menos 5 testes qualitativos antes de estabelecer prioridades.

## Roteiro de evolução
**Fase 1:** validar narrativa e compreensão com usuários.
**Fase 2:** ferramenta de curadoria editorial de novos casos, fonte por afirmação e revisão de links.
**Fase 3:** busca real assistida por IA, indexação, deduplicação e auditoria automática + humana.
**Fase 4:** fórum mediado e extensão do navegador, controles de denúncia e moderação.

## Duração
12 s é uma hipótese de UX, não uma medida de processamento real. No produto com recuperação dinâmica, o tempo dependerá da consulta e da qualidade das fontes; oferecer resposta progressiva e opção de pular a dramatização.

## Publicação
O `index.html` pode ser aberto localmente. Para produzir um URL compartilhável em navegador, publicar o arquivo em hospedagem estática (GitHub Pages, Netlify, Cloudflare Pages). Não há serviço de publicação automatizado neste pacote. Compartilhe o link publicado ou envie o HTML diretamente.
