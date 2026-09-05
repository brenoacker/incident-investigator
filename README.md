# Incident Investigation Harness

Base local e reproduzível do Incident Investigation Harness. O serviço expõe a
API de tickets e persiste os registros em PostgreSQL local; worker, MCPs e os
demais fluxos serão adicionados em etapas posteriores.

## Pré-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/)
- Docker Compose v2 (para executar o ambiente em contêiner)

## Ciclo local

Instale todas as dependências, incluindo as de desenvolvimento:

```sh
uv sync
```

Execute os testes e a checagem estática:

```sh
uv run pytest
uv run mypy
```

### Testes de integração

O teste `tests/test_postgres_integration.py` verifica que um ticket continua
disponível depois do reinício da API. Ele precisa de um PostgreSQL acessível e
da variável `DATABASE_URL` configurada. No PowerShell, usando o ambiente
virtual local:

```powershell
$env:DATABASE_URL = "postgresql://ticketing:ticketing@localhost:5432/ticketing"
.\.venv\Scripts\python.exe -m pytest -m integration
```

O exemplo acima pressupõe um PostgreSQL acessível em `localhost:5432`. O
serviço `db` do Compose não publica essa porta para o host; nesse caso, use um
PostgreSQL local ou publique a porta antes de executar o teste.

Para executar todos os testes com a integração habilitada:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Sem `DATABASE_URL`, o teste de integração é marcado como `skipped`; os testes
rápidos com `InMemoryTicketRepository` continuam sendo executados.

## Ambiente com Docker Compose

Suba a API e o PostgreSQL local:

```sh
docker compose up --build -d
```

Confirme a disponibilidade pelo healthcheck do Compose ou pelos endpoints:

```sh
docker compose ps
curl http://localhost:8000/health
```

O serviço deve ficar `healthy` e o endpoint deve responder `{"status":"ok"}`.

Crie e consulte um ticket:

```sh
curl -X POST http://localhost:8000/tickets \
  -H 'content-type: application/json' \
  -d '{"title":"Notification delayed","description":"Delivery latency increased.","requester_email":"oncall@example.com"}'
curl http://localhost:8000/tickets/{ticket-id}
```

Solicite a notificação do ticket. O pedido usa o `requester_email`, começa com
status `pending` e é publicado na lista Redis `notification_requests`:

```sh
curl -X POST http://localhost:8000/tickets/{ticket-id}/notifications
curl http://localhost:8000/notification-requests/{request-id}
```

Os tickets ficam no volume Docker `ticketing-data` e continuam disponíveis após
reiniciar o processo da API.

Para encerrar o ambiente:

```sh
docker compose down
```
