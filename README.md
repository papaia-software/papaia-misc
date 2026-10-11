# Papaia Misc — Marketing & Market Intelligence

MVP interno com React/TypeScript e FastAPI, persistência relacional e coleta RSS real. Integra prospecção de influenciadores, CRM de parcerias e acompanhamento competitivo. A instalação começa vazia: não presume concorrentes ou inventa métricas.

## Início rápido com Docker

Requisitos: Docker Engine/Desktop com Compose v2, Python 3 para gerar a configuração local, portas 5173 e 8000 disponíveis.

```bash
python3 scripts/init_env.py
# Defina a senha de administrador quando solicitado (mínimo 12 caracteres).
docker compose up --build
```

O script cria `.env` a partir do exemplo, gera `SECRET_KEY`, protege as permissões do arquivo e preserva qualquer `.env` existente. Alternativa: copie `.env.example` para `.env` e configure `SECRET_KEY` (32+ caracteres) e `ADMIN_PASSWORD` (12+ caracteres). A API recusa iniciar sem essas configurações.

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- OpenAPI/Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Login: `ADMIN_EMAIL` (padrão `admin@papaia.local`) e a senha definida no `.env`.

O Compose cria PostgreSQL 16 com volume persistente, aguarda a saúde do banco, executa `alembic upgrade head` e inicia a API. O frontend é compilado e servido por Nginx com proxy `/api` para o backend. Serviços web são vinculados ao loopback; o banco não expõe porta ao host.

```bash
docker compose logs -f backend
docker compose exec backend alembic current
docker compose exec backend alembic upgrade head
docker compose down            # preserva o volume de dados
```

`docker compose down -v` apaga o banco; use apenas se desejar descartar todos os registros locais. O password de PostgreSQL do exemplo é somente para ambiente local; personalize em instalações compartilhadas.

## Execução sem Docker

Requisitos: Python 3.12+ e Node 22+; macOS/Linux ou WSL para o lock SQLite.

```bash
python3 scripts/init_env.py
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.lock
backend/.venv/bin/pip install --no-deps -e 'backend[test]'
npm ci --prefix frontend
```

Terminal 1:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
npm run dev --prefix frontend
```

O `.env` é lido pelo backend quando executado a partir de `backend/`. SQLite usa `backend/papaia.db` por padrão. Para PostgreSQL externo, configure `DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco`. No Compose a URL é montada com `POSTGRES_*` e substitui o valor local.

## Primeiro fluxo completo

1. Entre com o administrador e abra **Influenciadores → Novo influenciador**. Cadastre um perfil público autorizado; deixe métricas desconhecidas vazias.
2. Abra o perfil e **Calcular score**. Escolha B2B/B2C, confira justificativa, cobertura e evidências. Pesos configuráveis e avaliação manual ficam no mesmo painel.
3. Atualize dados públicos/métricas, registre um contato já realizado e defina responsável, observações e follow-up. Vincule outra plataforma apenas após confirmar que é a mesma pessoa.
4. Arraste o card em **Negociações** ou use seu seletor acessível. Cadastre campanhas em **Configurações** e negociações com valores, entregáveis, datas e resultados no perfil.
5. Gere uma proposta de contato, revise e baixe o rascunho. A aplicação não envia mensagens.
6. Cadastre concorrentes escolhidos por sua equipe, adicione feeds em **Fontes & histórico** e clique **Coletar RSS**.
7. Abra **Notícias**, filtre, acompanhe registros, gere análise por regras e confirme vínculos com influenciadores somente com evidência. Alertas e dashboard refletem o banco.
8. Consulte **Configurações → Histórico de coletas** para contagens e erros. Falhas nunca geram substituição por dados demonstrativos.

## CSV

Baixe o modelo vazio pela interface ou use [influencers-template.csv](frontend/public/influencers-template.csv). UTF-8, até 1.000 linhas e 2 MB. Obrigatórios: `name,username,platform,url`; plataformas aceitas: Instagram, TikTok, YouTube. Nichos e links usam separador `|`; campos desconhecidos ficam vazios. `engagement` é porcentagem (4 = 4%). Importação valida o arquivo inteiro antes de gravar e deduplica plataforma/username.

## Integrações e agendamentos

RSS/Atom funciona sem credenciais; Google Alerts requer um RSS obtido legitimamente na sua conta. Apify requer `APIFY_TOKEN`, `APIFY_DATASET_ID` e possivelmente `APIFY_FIELD_MAP`; somente importa dataset existente autorizado, sem executar Actors pagos. Consulte [configuração e coleta real](docs/integrations.md).

`SCHEDULER_ENABLED=true` habilita a execução diária às `SCHEDULE_HOUR` UTC (padrão 6). Jobs de RSS e páginas podem ser pausados e ter seu intervalo mínimo alterado na interface. Postgres usa advisory lock compartilhado e timestamps persistidos para evitar execução duplicada entre réplicas. `PROVIDER_DAILY_LIMIT` limita execuções por integração; ações sob demanda respeitam cinco minutos entre tentativas.

Monitoramento de página é opcional, exige permissão confirmada e robots.txt permissivo/acessível. Mostra snapshots, hash e diff. Tokens e credenciais são configurados apenas no servidor.

Modash, HypeAuditor, YouTube Data API, busca ampla da web, classificação LLM e e-mail **não estão implementados**; o status das integrações informa isso. Métricas externas atualizam por CSV, edição manual ou nova importação Apify, sem chamadas pagas automáticas. [Arquitetura e limites operacionais](docs/architecture.md) detalha cache, agendamento, autenticação e escala.

## Dados demonstrativos opcionais

```bash
cd backend
DEMO_ENABLED=true .venv/bin/python ../scripts/seed_demo.py
```

Cria somente registros com prefixo **DEMO**, marcação na base/interface e domínio `example.org`. Não inventa métricas ou notícias. A execução é idempotente e desativada por padrão; registros podem ser excluídos na interface.

## Testes e validação

```bash
backend/.venv/bin/pytest backend/tests -q
npm test --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend --audit-level=high
cd backend
.venv/bin/alembic check
```

Testes cobrem autenticação, rate limit, CRUD/cascade, pipeline, CSV atômico, dados ausentes, scores/pesos, deduplicação, RSS, classificação, alertas, proposta sem envio, integração Apify simulada, SSRF/DNS/redirects, snapshots e scheduler. Frontend cobre login, cadastro, estados ausentes, pipeline, integração pendente e falha RSS.

Para PostgreSQL, use um **banco exclusivo de testes**:

```bash
TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/papaia_test backend/.venv/bin/pytest backend/tests -q
```

**A suíte remove e recria as tabelas do banco de teste a cada caso. Nunca aponte para um banco de uso.** CI está configurada em `.github/workflows/ci.yml` com PostgreSQL 16/Python 3.12, migrations de ida/volta, pytest, Vitest, build e auditoria npm.

Validação local desta entrega e evidências por etapa: [implementation.md](docs/implementation.md). Docker/Postgres não estavam instalados no ambiente de desenvolvimento; o Compose e a suíte Postgres foram preparados, mas sua execução precisa ser confirmada em ambiente com esses serviços.

## Estrutura

```text
frontend/       React, páginas conectadas, UI, testes Vitest
backend/        FastAPI, SQLAlchemy, Alembic, providers, scheduler, pytest
docs/           Arquitetura, integrações, etapas e limitações
scripts/        Configuração local e seed demonstrativo explícito
docker-compose.yml
.env.example
AGENTS.md
```

## Proteção e operação

Um workspace interno compartilhado, com administrador bootstrap; sem cadastro público ou papéis por usuário. Credenciais iniciais do ambiente são usadas só na criação do administrador, não redefinem senhas existentes. Para uso compartilhado, configure TLS, `COOKIE_SECURE=true`, `ALLOWED_ORIGIN`, senha de banco própria e política de backup/retenção. Não exponha os serviços de desenvolvimento diretamente à internet.

A aplicação trabalha com dados públicos necessários, procedência e exclusão. Scores não verificam habilitação profissional. Contatos privados, atributos sensíveis, contorno de bloqueios e envio automático de mensagens não fazem parte do sistema.

### Prospecção de potenciais assinantes (sem provedores pagos)

Acesse **Potenciais clientes** (`/customers`) para prospectar profissionais que possam utilizar o Papaia em seus atendimentos. Esse CRM é separado das parcerias de divulgação: Novo → Em análise → Qualificado → Contato pendente → Contatado → Demonstração → Em teste → Assinante, com descarte disponível. As etapas são atualizadas manualmente; não há integração com cobrança.

- Cadastro manual, importação CSV (modelo para baixar na tela), filtros por etapa, texto e score, exportação filtrada para Excel/Google Sheets, responsável, notas e follow-up.
- **Encontrar perfis** transforma uma descrição e um @ opcional em links de pesquisas públicas e mostra correspondências já cadastradas. A pesquisa é manual assistida: não extrai seguidores, não retorna novos perfis coletados e não usa APIs pagas. Revise região e requisitos na fonte antes do cadastro.
- Score independente: profissão declarada compatível (40), temas materno-infantis (30), atendimento com evidência (20), interesse explícito com evidência (10). Dados ausentes recebem zero; confiança mede cobertura, não veracidade. Seguidores não influenciam a nota. O score não comprova registro profissional nem intenção de compra.
- Sinais manuais de atendimento/interesse exigem URLs de evidência. Nenhuma mensagem é enviada pelo módulo.
- No detalhe de um influenciador, **Avaliar como cliente** copia explicitamente seu perfil para o CRM de clientes, mantendo o relacionamento e os pipelines independentes.
- CSV: UTF-8, listas separadas por `|`, booleanos `true`/`false` ou vazios. Limites: 1.000 linhas/2 MB por importação, 10.000 registros por exportação. Duplicados por plataforma/username são preservados sem sobrescrever etapas. Exportação protege contra fórmulas em planilhas.

API autenticada: `/api/customer-leads` (GET/POST), `/{id}` (GET/PATCH/DELETE), `/summary`, `/export`, `/import`, `/search-plan` e `/from-influencer/{id}`. A migration `9e9d9f1f0e9d` adiciona apenas a tabela de potenciais clientes. Execute `alembic upgrade head` antes de iniciar uma versão atualizada.
