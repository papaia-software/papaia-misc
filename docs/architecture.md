# Arquitetura e decisões do MVP

O Papaia Misc é um workspace interno compartilhado. A API é a fonte de verdade; o frontend usa TanStack Query e não armazena registros comerciais nem credenciais de provedores no navegador. PostgreSQL é o banco principal. SQLite é suportado para testes e desenvolvimento em um único host Unix.

## Organização

- `backend/app/models.py`: 22 entidades relacionais, FKs indexadas, timestamps, unicidade de perfis por plataforma/username e constraints de pipeline, métricas e scores.
- `backend/app/schemas.py`: contratos de entrada Pydantic, limites, validação de URLs e enumerações.
- `backend/app/main.py`: API REST autenticada e documentação OpenAPI em `/docs`.
- `backend/app/services.py`: persistência, deduplicação, classificação, coletas e locks.
- `backend/app/scoring.py`: heurística conservadora explicável, sem estimativas de métricas.
- `backend/app/providers.py`: interfaces `InfluencerProvider` / `NewsProvider`, RSS e Apify dataset.
- `backend/app/network.py`: rede pública com validação DNS e conexão ao IP validado; Host/SNI preservados. Cada redirecionamento é revalidado. Proxies de ambiente são desativados.
- `backend/app/scheduler.py`: APScheduler 3, execução diária em UTC, intervalos persistidos e claim sob lock.
- `frontend/src`: React Router, TanStack Query, Recharts, Tailwind 4 e componentes no padrão shadcn/ui com Radix.

## Persistência e identidades

Uma pessoa possui vários perfis e várias observações de métricas. Importações repetidas deduplicam pelo par normalizado `platform, username`, preservando os campos do CRM e acrescentando observações. Não associamos pessoas de plataformas diferentes só pelo nome: a rota `POST /api/influencers/{id}/profiles` permite vínculo explícito. Alteração manual de dados públicos gera uma nova observação de métricas e muda a procedência para `manual`.

Notícias deduplicam pela URL sem fragmento, parâmetros UTM, fbclid e gclid; outros parâmetros são preservados. Similaridade de título >= 94% é considerada apenas para a mesma fonte e registros coletados nos últimos 30 dias (até 500 candidatos). Uma notícia pode se relacionar a vários concorrentes e influenciadores. Vínculos com influenciadores exigem confirmação humana auditada. Não há extração automática de vínculos a partir de menções.

Migrations versionadas têm operações explícitas e downgrade. A aplicação nunca cria tabelas automaticamente. O bootstrap cria somente o administrador e os jobs após as migrations.

## Fit Score

Pesos padrão: tema 30, audiência 25, engajamento 20, credibilidade 15 e potencial comercial 10. Todos podem ser configurados por avaliação, somando 100. Pesos e evidências ficam persistidos por versão do score.

- Tema: até 30 pontos para dois temas do catálogo presentes nos nichos ou na biografia declarada.
- Audiência: até 25 pontos quando o público declarado corresponde ao objetivo B2B ou B2C. Sem inferência de atributos privados ou sensíveis.
- Engajamento: até 20 pontos; taxa fornecida / referência configurada no código de 5%, limitada a 1. Essa regra não verifica autenticidade.
- Credibilidade: zero automático. Só revisão humana pode avaliar segurança e evidências; nenhum score atesta registro profissional.
- Potencial comercial: metade do peso para afinidade profissional B2B ou audiência B2C declarada. Sem bônus por seguidores.

Ausência recebe zero, sem redistribuir pesos. Confiança significa cobertura ponderada dos dados, não veracidade. Avaliação manual exige justificativa e links públicos e é identificada como humana. Scores antigos permanecem disponíveis na API. Não se deve usar o score como verificação de habilitação profissional.

## Rede, coletas e agendamento

RSS usa HTTPX para acesso controlado e feedparser apenas sobre bytes obtidos, nunca sobre URLs. HTML é convertido em texto; a interface não injeta HTML externo. O coletor limita payloads a 2 MB, até 100 itens por feed e quatro saltos. Requisições públicas fazem até três tentativas com backoff em falhas HTTP. Apify não repete automaticamente requisições em rate limit.

Coletas manuais possuem limite diário por integração e intervalo mínimo de cinco minutos. Os dados já persistidos continuam disponíveis durante o intervalo, independentemente de indisponibilidade externa. Além do intervalo, respostas públicas bem-sucedidas possuem cache de bytes em memória por processo: TTL de cinco minutos e máximo de 16 entradas de até 2 MB. Falhas não são cacheadas; limites de domínio se mantêm nos hits. Não há cache distribuído nem validação condicional por ETags.

Postgres usa advisory lock de sessão, mantido em conexão dedicada até o fim da coleta. Isso serializa RSS, páginas e importações Apify entre workers e réplicas do mesmo banco. SQLite usa flock, portanto requer mesmo host. O scheduler reconsulta `last_run_at` sob o mesmo lock e grava o claim antes do IO. Um crash pode adiar o próximo job pelo intervalo configurado; não é uma fila durável. A retomada manual continua disponível após a liberação do lock.

Cada fonte é processada em savepoint. Uma falha não descarta as demais; `collection_runs` expõe success, partial, failed, contagem e mensagens. Atualizações de página exigem permissão confirmada e robots.txt acessível/permissivo; acesso inacessível falha fechado. Hash evita snapshot repetido; alterações têm diff textual. O operador deve avaliar termos e legitimidade da coleta; não existem mecanismos de contorno de autenticação ou CAPTCHA.

## Segurança e dados

- Login interno com senha scrypt, JWT de oito horas em cookie HttpOnly e SameSite Strict, validação de Origin em mutações com cookies e limitação persistida de tentativas. O logout remove o cookie, mas não revoga tokens já copiados até sua expiração.
- Não há cadastro público, gestão de usuários, papéis, MFA ou isolamento entre equipes. Uma instalação corresponde a um único workspace de confiança.
- `SECRET_KEY` e `ADMIN_PASSWORD` são obrigatórios e não têm defaults utilizáveis. Bootstrap não troca a senha de um usuário existente. Segredos de APIs só vêm do ambiente do backend.
- Exclusão física pela API/interface e cascade de dependências. Auditoria preserva apenas ação, entidade, id e usuário; não guarda conteúdo privado excluído. Backups exigem política própria de retenção.
- Apenas contatos comerciais públicos e informações necessárias; não existe coleta de telefone/e-mail privado nem disparo de mensagens.
- Use TLS e `COOKIE_SECURE=true` em ambientes compartilhados. Bind local dos serviços do Compose reduz exposição acidental; não representa configuração pronta para internet.

## Extensões e limites atuais

Implementados: manual, CSV, RSS/Atom/Google Alerts via RSS e leitura de dataset Apify. Modash, HypeAuditor e YouTube têm status explícito de não implementado, sem endpoints inventados. Não há execução paga de Actor, busca ampla da web, classificador LLM, notificações por e-mail ou atualização paga automática de métricas. O custo de execução de provedores pagos é zero porque essa execução está desabilitada, não porque é estimado por uma quota local.

Buscas em linguagem natural reconhecem temas conhecidos. Outros critérios exigem filtros explícitos; o texto não é tratado como comando de IA. Apify pesquisa somente o recorte de até 100 perfis do dataset configurado, não a internet inteira. Seletores de campanhas/concorrentes carregam os primeiros 100 registros; listagens principais e API têm paginação. Para escalas maiores, substituir seletores por busca paginada.

Não há fila de trabalhos assíncrona; coletas ocorrem na requisição ou no job dedicado do scheduler. Grandes quantidades de fontes podem exceder timeout do proxy; escalar para fila e workers antes desse cenário. Também permanecem como evolução: cache distribuído/ETags, RBAC/SSO e importação em lote acima de 1.000 linhas. Esses limites são explícitos; não são substituídos por mocks.

## Potenciais clientes

`customer_leads` acrescenta uma 23ª entidade ao esquema. Perfis de aquisição de assinantes têm identidade única por plataforma/username, pipeline e qualificação próprios, sem alterar a qualificação de influenciadores. A FK opcional `influencer_id` usa SET NULL e só é criada por ação explícita. O serviço `customer_scoring.py` usa dados públicos declarados e sinais avaliados com evidências; não usa seguidores, renda ou atributos sensíveis. A API `customer_api.py` mantém a pesquisa assistida local, sem chamar provedores. Não há descoberta automática de audiência nem sincronização de pagamentos.
