import sys
from pathlib import Path

# Adiciona os módulos do monorepo ao sys.path para execução serverless
root = Path(__file__).resolve().parent.parent
for pkg in ["api-gateway", "shared", "riot-integration-service", "match-history-service", "recommendation-service"]:
    p = str(root / pkg / "src")
    if p not in sys.path:
        sys.path.insert(0, p)

from gateway.main import app as gateway_app

async def app(scope, receive, send):
    """Normaliza o caminho da requisição para compatibilidade com o roteamento serverless da Vercel."""
    if scope.get("type") == "http":
        path = scope.get("path", "")
        for prefix in ["/api/index.py", "/api/index"]:
            if path.startswith(prefix):
                new_path = path[len(prefix):] or "/"
                scope = dict(scope)
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode("utf-8")
                break
    await gateway_app(scope, receive, send)
