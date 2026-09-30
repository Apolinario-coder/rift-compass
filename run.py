"""Inicia os quatro serviços com SQLite para desenvolvimento sem Docker."""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime"
SERVICES = [
    ("riot_integration", 8011),
    ("match_history", 8012),
    ("recommendation", 8013),
    ("gateway", 8010),
]


def main():
    RUNTIME.mkdir(exist_ok=True)
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "riot-integration-service" / ".env")
    env = os.environ.copy()
    env.update(
        {
            "HISTORY_DATABASE_URL": "sqlite:///" + (RUNTIME / "history.db").as_posix(),
            "RECOMMENDATION_DATABASE_URL": "sqlite:///"
            + (RUNTIME / "recommendations.db").as_posix(),
            "HISTORY_RIOT_URL": "http://127.0.0.1:8011",
            "RECOMMENDATION_HISTORY_URL": "http://127.0.0.1:8012",
            "GATEWAY_RIOT_URL": "http://127.0.0.1:8011",
            "GATEWAY_HISTORY_URL": "http://127.0.0.1:8012",
            "GATEWAY_RECOMMENDATION_URL": "http://127.0.0.1:8013",
        }
    )
    processes, logs = [], []
    try:
        for name, port in SERVICES:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    raise RuntimeError(
                        f"Porta {port} ocupada. Encerre a outra execução primeiro."
                    ) from None
            log = (RUNTIME / f"{name}.log").open("w", encoding="utf-8")
            logs.append(log)
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"{name}.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            processes.append(proc)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"{name} falhou. Consulte .runtime/{name}.log.")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"{name} não iniciou no prazo.")
        print("Rift Compass: http://127.0.0.1:8010  |  Ctrl+C para encerrar.", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        raise RuntimeError("Um serviço encerrou. Consulte os logs em .runtime/.")
    except KeyboardInterrupt:
        print("Encerrando serviços…", flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
