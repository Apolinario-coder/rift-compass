import sys
from pathlib import Path

# Configura caminhos do monorepo para importação unificada
ROOT = Path(__file__).resolve().parent
for pkg in ["api-gateway", "shared", "riot-integration-service", "match-history-service", "recommendation-service"]:
    p = str(ROOT / pkg / "src")
    if p not in sys.path:
        sys.path.insert(0, p)

from gateway.main import app

if __name__ == "__main__":
    import os
    if os.environ.get("VERCEL"):
        print("Vercel build verification: FastAPI app successfully initialized.")
        sys.exit(0)
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=True)

