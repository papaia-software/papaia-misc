# Entregas e validação por etapa

As cinco etapas foram implementadas no mesmo checkout e verificadas cumulativamente com testes unitários, de integração e de interface. Nenhuma credencial de integração externa foi habilitada e nenhuma mensagem foi enviada a terceiros.

## Etapa 1 — base executável

Entregue: monorepo, configurações por ambiente, PostgreSQL no Compose, SQLite local, 22 modelos relacionais, migration Alembic explícita, bootstrap seguro, login, layout responsivo e navegação.

Validado: migration SQLite `upgrade head → downgrade base → upgrade head`; `alembic check` sem divergências. SQL PostgreSQL gerado em modo offline com sucesso. Build TypeScript/Vite passou. Docker e PostgreSQL não foram executados localmente porque seus binários não estavam instalados. Workflow CI preparado com PostgreSQL 16/Python 3.12, ainda não executado nesta sessão.

Como validar: gerar `.env`, executar `docker compose up --build`, conferir `/health`, acessar localhost:5173 e autenticar. Consulte o README para execução sem Docker.

Credenciais: somente administrador local obrigatório; nenhum provedor necessário.

## Etapa 2 — influenciadores e CRM

Entregue: cadastro/edição/exclusão, múltiplos perfis vinculados explicitamente, importação CSV atômica, deduplicação de identidade, histórico de métricas, score B2B/B2C com pesos e evidências, revisão manual, pipeline Kanban e seletor acessível, contatos, follow-up, responsável, campanhas, negociações e rascunho editável de proposta.

Validado: pytest cobre CRUD, cascade, CSV duplicado/inválido, métricas ausentes, score/objetivos/pesos, ausência de bônus por seguidores, estágios e proposta sem envio. Vitest cobre cadastro, métricas ausentes e movimentação de pipeline. Chrome headless percorreu cadastro → score → contato → etapa → rascunho, contra API e SQLite reais.

Como validar: seguir os passos 1–5 do primeiro fluxo no README. Cadastro e CSV não dependem de credenciais externas. Dados demonstrativos são opcionais e explicitamente marcados.

## Etapa 3 — concorrência e RSS

Entregue: concorrentes escolhidos pelo usuário, fontes RSS/Atom e páginas, coleta HTTP real, notícias manuais com fonte/URL, filtros e acompanhamento, deduplicação por URL/título, classificação por regras, relevância, análise separando fatos de hipóteses, alertas configuráveis e snapshots/diffs opcionais.

Validado: RSS simulado nos testes para conteúdo, erros, deduplicação e alertas; teste live com BBC News recebeu 21 registros sem persistência na base de uso. O navegador também cadastrou uma fonte técnica demonstrativa em banco temporário e executou coleta RSS real pela interface. Snapshot/diff, permissão e bloqueio de redirecionamento de domínio cobertos em pytest.

Como validar: cadastrar concorrente real escolhido pela equipe, adicionar seu RSS autorizado, coletar e abrir notícias. Conferir histórico de execução. Para páginas, confirmar termos e checar robots.txt.

Credenciais: RSS público não exige; Google Alerts depende da configuração do feed na conta do usuário.

## Etapa 4 — provedores e agendamentos

Entregue: interfaces independentes, integração Apify lendo dataset existente, mapeamento configurável sem presumir schema de Actor, confirmação de consulta, status pendente/não implementado, quota, intervalo, cache HTTP local limitado, backoff, histórico e agendamento diário com lock/claim compartilhado no banco.

Validado: HTTPX MockTransport para sucesso e rate limit Apify, schema inválido e ausência de credenciais sem geração de mocks. Lock concorrente, cache, DNS público/privado/misto, IP/SNI e redirects testados. Scheduler testado para não repetir um job já reivindicado no intervalo. Execução de Apify real não foi possível sem credenciais e dataset autorizados. Não há execução de Actor pago.

Como validar: consultar Configurações, configurar o dataset no servidor seguindo `integrations.md`, reiniciar, revisar e confirmar importação. Agendamentos e coletas RSS não dependem de Apify.

Credenciais: APIFY_TOKEN + APIFY_DATASET_ID e, conforme a fonte, APIFY_FIELD_MAP.

## Etapa 5 — integração, segurança e documentação

Entregue: dashboard derivado do banco, notícias relacionadas a concorrentes, vínculo humano auditado com influenciadores/contexto de CRM, busca de perfis relacionada a um tema, auditoria, erros padronizados, login/Origin/rate limits, exclusão física, documentação, scripts de configuração e CI.

Validações finais:

- pytest: 40 casos cobrindo API, serviços, provedores, segurança e agendamento.
- Vitest/Testing Library: 6 fluxos aprovados.
- TypeScript + build Vite: aprovados.
- `npm audit`: zero vulnerabilidades na árvore instalada.
- Alembic: upgrade/downgrade/check SQLite aprovados; SQL PostgreSQL offline gerado.
- Chrome headless: 12 fluxos principais e 5 verificações adicionais (campanha, alertas, negociação e mobile) com API real aprovados; nenhum erro de JavaScript; navegação mobile de 390 px sem overflow horizontal.
- `git diff --check`: sem erros de whitespace.

O ambiente usou Python 3.14 e Node 24; Docker e CI estão configurados para Python 3.12 e Node 22. A versão atual de Starlette emitiu aviso de depreciação sobre HTTPX no TestClient; a suíte passou. O build informa um chunk de aproximadamente 869 KB antes de gzip; divisão de rotas é uma melhoria de desempenho futura, sem impedir execução.

As capturas usadas na inspeção visual foram produzidas em `/tmp`, sem adicionar dados reais ou credenciais ao repositório. O banco temporário de QA é separado da base local de uso. A documentação de arquitetura explicita os limites: workspace único, sem RBAC/SSO, sem fila durável, sem busca geral da web/LLM, sem notificações externas e seletores limitados aos primeiros 100 registros. Esses recursos não são apresentados como implementados.

## Extensão: aquisição de assinantes

Entregue o módulo **Potenciais clientes**, independente do CRM de parcerias, com cadastro/edição/exclusão, etapas comerciais, notas, responsável, follow-up, score explicado, evidências, busca manual assistida por descrição/@, importação e exportação CSV. Um influenciador pode ser copiado explicitamente para avaliação comercial. Não foram configurados nem acionados provedores pagos. Pesquisa assistida fornece links públicos e correspondências locais; não é extração automática de seguidores ou descoberta automática de novos leads.

Validação: 46 testes backend, 9 frontend e build de produção passaram. Migração adicional validada com upgrade/downgrade/upgrade em SQLite separado e aplicada à base local preservada. QA em Chrome confirmou criação, score, mudança de etapa, pesquisa e layouts desktop/mobile; o registro fictício temporário foi removido. PostgreSQL/Docker continuam dependentes do ambiente descrito acima. O build mantém o aviso de tamanho do bundle já existente.

Como validar: abrir `http://localhost:5173/customers`, cadastrar um perfil real com URL pública, declarar profissão/nicho, conferir score, registrar sinais apenas com evidências, avançar etapas e exportar CSV filtrado. Para pesquisa sem custo, abrir **Encontrar perfis**, descrever o profissional desejado e revisar os resultados das pesquisas públicas. Nenhuma credencial externa é necessária nesse fluxo.
