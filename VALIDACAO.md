# Validação da etapa 1

Executada em 30/09/2026 com Python 3.13.7 no Windows.

- Instalação editável com dependências de desenvolvimento: concluída.
- `pytest`: 19 testes passaram, sem acessar a Riot.
- `ruff check`: passou.
- `docker compose config --no-env-resolution`: configuração validada.
- Contêiner Docker e chamada à Riot com chave real: não executados.

Versões principais resolvidas: FastAPI 0.142.2, HTTPX 0.28.1,
Pydantic Settings 2.15.0, pytest 9.1.1 e Ruff 0.16.9.

O TestClient do Starlette 1.7.0 emitiu um aviso de depreciação sobre seu uso de
HTTPX, sugerindo HTTPX2. Os testes passaram; a atualização do transporte de
testes deve ser avaliada ao fixar as dependências em um lockfile.
