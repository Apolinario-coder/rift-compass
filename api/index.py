import sys
from pathlib import Path

# Adiciona os módulos do monorepo ao sys.path para execução serverless
root = Path(__file__).resolve().parent.parent
for pkg in ["api-gateway", "shared", "riot-integration-service", "match-history-service", "recommendation-service"]:
    p = str(root / pkg / "src")
    if p not in sys.path:
        sys.path.insert(0, p)

from gateway.main import app
