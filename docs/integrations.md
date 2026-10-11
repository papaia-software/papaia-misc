# Integrações reais

## RSS e Google Alerts

1. Cadastre um concorrente em **Concorrentes** com nome e website informados por sua equipe.
2. Em **Fontes & histórico**, adicione um RSS/Atom público. Para Google Alerts, configure o alerta na sua conta e copie o RSS disponibilizado pelo próprio serviço.
3. Clique **Coletar RSS** ou **Atualizar notícias**. Consulte contagem, falhas e horário em **Configurações → Histórico de coletas**.
4. Abra uma notícia, consulte sua URL original e gere a análise por regras. Fatos atribuídos à fonte e interpretações aparecem separados.

Para testar somente conectividade com uma fonte pública (não representa indicação de concorrente Papaia):

```bash
cd backend
.venv/bin/python -c "from app.providers import RSSProvider; print(len(RSSProvider().collect('https://feeds.bbci.co.uk/news/technology/rss.xml')))"
```

O smoke test foi executado nesta sessão: 21 itens recebidos da fonte BBC News. Não inseriu notícias ou concorrentes presumidos na base de uso.

## Apify: dataset existente, sem execução paga

Documentação oficial consultada:

- [Referência da API v2](https://docs.apify.com/api/v2)
- [Get dataset items](https://docs.apify.com/api/v2/dataset-items-get)
- [Run task (para extensão futura)](https://docs.apify.com/api/v2/actor-task-runs-post)

A integração implementada faz `GET https://api.apify.com/v2/datasets/{datasetId}/items` com `format=json`, `clean=true`, `limit=100` e `Authorization: Bearer <token>`. Não cria tasks, executa Actors ou assume schemas universais de scrapers. O dataset deve ser adquirido por meio autorizado e conter apenas dados públicos apropriados à finalidade.

Configure no `.env` e reinicie o backend:

```dotenv
APIFY_TOKEN=<token com acesso ao dataset>
APIFY_DATASET_ID=<id do dataset existente>
APIFY_FIELD_MAP='{"name":"fullName","username":"handle","platform":"network","url":"profileUrl","followers":"followersCount","engagement":"engagementRate"}'
```

Esse mapeamento é **um exemplo de contrato**, não o schema de um Actor específico. Cada chave é um campo da API Papaia; cada valor é uma chave top-level realmente presente no seu dataset. Ajuste após inspecionar a documentação e a saída da sua fonte. Campos não mapeados não são importados. Sem mapeamento, cada item deve seguir exatamente `InfluencerCreate` em `/docs` (campos extras são rejeitados).

Campos obrigatórios: `name`, `username`, `platform` (`Instagram`, `TikTok` ou `YouTube`), `url` pública HTTP(S). `engagement` representa porcentagem entre 0 e 100 (4 significa 4%, não 0,04); não convertemos automaticamente escalas desconhecidas. `niches`, `evidence_urls`, `relevant_posts`, `previous_collaborations` são listas. Métricas ausentes permanecem nulas. Fotos, biografias e contatos precisam vir de fontes legítimas e identificadas.

Em **Influenciadores → Prospectar**, revise a busca e confirme a consulta/importação. A confirmação e o limite diário protegem chamadas externas. Se faltar configuração, o botão fica desabilitado e a integração aparece pendente. HTTP 429, credenciais inválidas ou schemas incompatíveis são registrados como falha; não existe fallback para perfis fictícios. Importações de um mesmo perfil acrescentam observações e preservam o CRM.

Limites: até 100 itens, sem paginação externa nesta versão, sem schema aninhado, sem busca geral fora do dataset. O token nunca é enviado ao frontend. Não habilite Actors pagos sem implementar também orçamento máximo enforced pelo provedor, controle idempotente de execução e confirmação explícita.

## Monitoramento textual de páginas

Adicione uma fonte do tipo página e confirme a permissão após revisar termos. O coletor consulta robots.txt, falha fechado se inacessível e não coleta páginas bloqueadas. Clique **Monitorar páginas agora**, ou habilite o job diário. O histórico exibe conteúdo inicial e diffs das alterações posteriores. Scripts, navegação e rodapé são removidos. Não executa JavaScript ou contorna bloqueios. Redirecionamentos para outro domínio exigem recadastro para revisão da fonte.

## Outras interfaces

`InfluencerProvider.discover()` retorna contratos validados. `NewsProvider.collect(url)` retorna título, fonte, URL, resumo em texto e data pública quando disponível. Novos adaptadores devem respeitar `network.py`, limites e proveniência; a lógica do CRM não precisa conhecer o fornecedor.

Referências de implementação: [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [SQLAlchemy 2](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html), [APScheduler 3](https://apscheduler.readthedocs.io/en/3.x/userguide.html), [HTTPX transports](https://www.python-httpx.org/advanced/transports/), [feedparser](https://feedparser.readthedocs.io/en/latest/), [Vite](https://vite.dev/guide/), [shadcn/ui Vite](https://ui.shadcn.com/docs/installation/vite).
