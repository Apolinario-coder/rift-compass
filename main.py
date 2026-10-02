import sys
from pathlib import Path

# Configura caminhos do monorepo para importação unificada
ROOT = Path(__file__).resolve().parent
for pkg in ["api-gateway", "shared", "riot-integration-service", "match-history-service", "recommendation-service"]:
    p = str(ROOT / pkg / "src")
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

if __name__ == "__main__":
    import os
    if os.environ.get("VERCEL"):
        print("Vercel build verification: FastAPI app successfully initialized.")
        sys.exit(0)
    port = int(os.environ.get("PORT", 8010))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
