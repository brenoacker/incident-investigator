# Incident Investigation Harness

Base local e reproduzível do Incident Investigation Harness. Neste estágio, o
serviço somente expõe uma verificação de saúde; API de tickets, worker, MCPs e
infraestrutura externa serão adicionados em etapas posteriores.

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

## Ambiente com Docker Compose

Suba o serviço local:

```sh
docker compose up --build -d
```

Confirme a disponibilidade pelo healthcheck do Compose ou pelo endpoint:

```sh
docker compose ps
curl http://localhost:8000/health
```

O serviço deve ficar `healthy` e o endpoint deve responder `{"status":"ok"}`.

Para encerrar o ambiente:

```sh
docker compose down
```
