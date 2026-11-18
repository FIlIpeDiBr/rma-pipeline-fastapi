# RMA Pipeline (FastAPI)

[![CI](https://github.com/FIlIpeDiBr/rma-pipeline-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/FIlIpeDiBr/rma-pipeline-fastapi/actions/workflows/ci.yml)

Sistema web que recebe balancetes e DREs por upload ou por e-mail, extrai os dados com um LLM, calcula indicadores financeiros e gera o Relatório Mensal de Atividades (RMA) de cada empresa em `.docx`.

É a segunda versão do [rma-pipeline-apps-script](https://github.com/FIlIpeDiBr/rma-pipeline-apps-script). A primeira rodava em Google Apps Script com uma planilha como banco de dados; esta foi reescrita para sair desses limites. Foi construída para um escritório de contabilidade e está aqui sem dados de clientes.

*[English version](README.en.md)*

## Arquitetura

```mermaid
flowchart LR
    U["Portal<br/>React + Vite"] -->|"REST + SSE"| W["API<br/>FastAPI"]
    M["Caixa de e-mail<br/>Microsoft Graph"] --> K
    W -->|"enfileira"| Q[("PostgreSQL<br/>dados + fila")]
    Q --> K["Worker<br/>Procrastinate"]
    K -->|"triagem e extração"| C["Claude<br/>API da Anthropic"]
    K --> S[("Storage S3<br/>documentos e relatórios")]
    W --> S
    K -->|"progresso"| Q
    E["Microsoft Entra ID<br/>OIDC"] -.->|"login"| W
```

Uma única imagem Docker serve os dois papéis: a variável `SERVICE_ROLE` decide se o contêiner sobe a API ou o worker. A fila fica no próprio Postgres, então não há Redis nem outro serviço para operar.

| Camada | Tecnologia |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Fila | Procrastinate (jobs no PostgreSQL), tarefa periódica para a caixa de e-mail |
| IA | Claude: um modelo barato na triagem, um maior na extração e nos textos de análise |
| Relatórios | docxtpl (modelos `.docx` com Jinja) e matplotlib |
| Autenticação | Microsoft Entra ID (OIDC), sessão em cookie assinado |
| Frontend | React 18, TypeScript, Vite |
| Operação | Docker, Render (web + worker), Sentry, logs estruturados (structlog) |

## Do documento ao relatório

1. **Recepção.** O documento chega por upload ou pela caixa de e-mail. Os e-mails não entram direto: caem em uma fila de revisão, e uma pessoa escolhe quais anexos importar.
2. **Triagem.** Um modelo barato identifica empresa, período e tipo do documento.
3. **Conversão.** PDF com texto, planilha e CSV viram texto. PDF escaneado e imagem vão para o modelo como documento.
4. **Extração.** O modelo devolve JSON, que é reconciliado com um plano fixo de categorias sintéticas e gravado em uma transação.
5. **Cálculo.** Análise vertical e horizontal, e 23 indicadores definidos por fórmula. Empresas de um mesmo grupo são consolidadas.
6. **Relatório.** Um job monta o `.docx` a partir de um modelo, com tabelas, gráficos e parágrafos de análise escritos pelo modelo de linguagem.

O portal acompanha cada etapa do processamento em tempo real por SSE.

## Decisões de engenharia

**Jobs idempotentes e retomáveis.** Processar o mesmo documento duas vezes substitui os dados, não duplica. Documentos com a mesma chave de negócio (empresa, mês, ano e tipo) são deduplicados, e o mais recente vence. Uma falha marca o documento com erro e mensagem acionável, e o job é reexecutado.

**Custo de IA auditável.** Cada chamada ao modelo grava modelo, tokens, custo estimado, duração, prompt e resposta na tabela `ai_calls`. A triagem usa um modelo mais barato que a extração. Modelos e tabela de preços são configuráveis por variável de ambiente.

**Indicadores como dados.** As 23 definições ficam em tabela, e cada organização pode sobrepor uma fórmula sem mexer no código. As fórmulas passam por um avaliador próprio, sem `eval`, que só entende aritmética e os valores do período.

**Revisão humana na entrada por e-mail.** O sistema lê a caixa a cada 5 minutos, mas nenhum anexo entra no pipeline sem alguém aprovar. Um e-mail é um canal aberto; a fila de revisão impede que um remetente qualquer injete documentos.

**Isolamento por organização.** Toda tabela carrega `org_id` e toda consulta filtra por ele. Um teste percorre as rotas e falha se alguma rota de `/api` não exigir autenticação.

**Modelos de relatório em ambiente restrito.** Um modelo `.docx` é código Jinja. Os modelos enviados pelo portal são renderizados em um ambiente que bloqueia o acesso aos internos do Python e escapa os valores, de modo que quem sobe um modelo não executa código no worker.

**Falhar cedo.** Em produção, a aplicação não sobe com a chave de sessão padrão. A conexão com o banco tem tempo limite, para o health check responder mesmo quando o banco não responde. O upload é lido em blocos e recusado assim que passa do limite, sem carregar o arquivo inteiro na memória.

**Progresso por aviso, não por consulta.** Cada evento de progresso emite um `NOTIFY` na mesma transação em que é gravado. A API mantém uma conexão em `LISTEN` por processo e acorda só as conexões SSE da organização avisada. O aviso não carrega dados: a tabela de eventos continua sendo a fonte, e perder um aviso custa um atraso, não um evento. Se o `LISTEN` cai, o stream volta a consultar o banco em intervalo curto até a conexão voltar.

**Migrations como fonte do esquema.** Um teste de integração compara o que os modelos do ORM declaram com o que as migrations criam em um Postgres vazio (tabelas, colunas, tipos, chaves e índices) e falha se os dois lados divergirem. Ao ser escrito, ele encontrou índices declarados de um jeito nos modelos e criados de outro nas migrations; os modelos foram alinhados.

## Rodando localmente

Pré-requisitos: Python 3.12+, Node 22+ e Docker.

```bash
# 1. Banco
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # no Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../.env.example ../.env                          # preencha o necessário
alembic upgrade head
procrastinate --app=app.jobs.job_app schema --apply
uvicorn app.main:app --reload                       # http://localhost:8000

# 3. Worker (outro terminal, mesma venv)
procrastinate --app=app.jobs.job_app worker

# 4. Frontend (outro terminal)
cd frontend
npm ci
npm run dev                                         # http://localhost:5173
```

As variáveis estão em [`.env.example`](.env.example). Sem `ANTHROPIC_API_KEY` e `STORAGE_*` a API sobe, mas o pipeline não processa documentos.

## Testes

```bash
# Backend: lint e testes de unidade (sem banco, sem rede, sem chave de API)
cd backend
ruff check .
pytest

# Backend: testes de integração, no Postgres do docker compose
docker compose exec db createdb -U postgres rma_teste
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/rma_teste \
  RMA_TESTE_INTEGRACAO=1 pytest -m integracao

# Frontend
cd ../frontend
npm run lint && npm run typecheck && npm test
```

**Unidade (68 testes).** SQLite em memória e dublês para storage, e-mail e IA. Cobrem a normalização de categorias, o reparo de JSON, a persistência e a deduplicação, o motor de indicadores, a consolidação de grupos, a montagem do relatório, as regras de segurança, a leitura do upload com limite e o barramento de eventos do progresso em tempo real.

**Integração (12 testes).** A API sobre um Postgres de verdade, com o esquema criado pelas migrations e pela fila do Procrastinate, como em produção. Cobrem as migrations até a última revisão, a comparação entre modelos e migrations, o caminho upload → job na fila → pipeline → indicadores, a DRE real substituindo a derivada do balancete, a deduplicação no reenvio, a exclusão em cascata pelas chaves estrangeiras, o relatório do pedido ao download, o isolamento entre organizações e o `NOTIFY` acordando o stream. Só rodam quando pedidos e contra um banco cujo nome termine em `_teste`, porque esvaziam as tabelas a cada teste.

**Frontend (23 testes).** Vitest sobre as funções puras de formatação, busca e ordenação. ESLint (regras recomendadas, TypeScript e hooks) e `tsc` completam a checagem.

O CI roda tudo isso a cada push, em quatro jobs: backend, integração (com um Postgres 16 de serviço), frontend e build da imagem Docker.

## Deploy

O [`render.yaml`](render.yaml) descreve os dois serviços (web e worker) a partir da mesma imagem. As migrações rodam na subida do serviço web.

## Limitações conhecidas

- Na prática há uma organização só, criada pelo nome configurado no primeiro login. O isolamento por `org_id` existe e é testado, mas não há cadastro nem administração de organizações.
- Os testes de integração não sobem o worker nem chamam a IA: o job enfileirado é conferido na tabela da fila e executado em linha, e a IA e o storage são dublês. A qualidade da extração depende do modelo e não é medida por teste automatizado.
- Os componentes React não têm teste; só as funções puras têm. Os componentes maiores concentram estado e chamadas de API.
- O `LISTEN/NOTIFY` cobre o progresso dos documentos. A tela de relatórios ainda consulta a lista a cada 4 s enquanto está aberta.
- O custo de IA registrado é uma estimativa a partir de uma tabela de preços configurável, não o valor faturado.
- As dependências do frontend estão nas versões da época do projeto (React 18, Vite 5).

## Autor

Filipe Dias Brandão · [github.com/FIlIpeDiBr](https://github.com/FIlIpeDiBr)

Código publicado para fins de portfólio. Todos os direitos reservados.
