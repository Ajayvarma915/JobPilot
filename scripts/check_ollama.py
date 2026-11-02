"""Check whether the locally configured Ollama service and model are ready."""
from __future__ import annotations

from app.ai.ollama_client import get_status


def main() -> int:
    status = get_status()
    print("JobPilot local AI preflight")
    print("=" * 64)
    print(f"Ollama available : {status['available']}")
    print(f"Configured model : {status['configured_model']}")
    print(f"Model installed  : {status['model_installed']}")
    print(f"Message          : {status['message']}")
    models = status.get("installed_models") or []
    if models:
        print("Installed models : " + ", ".join(models))
    print("=" * 64)
    if not status["available"]:
        print("Start Ollama and run this check again.")
        return 1
    if not status["model_installed"]:
        print(f"Install the configured model with: ollama pull {status['configured_model']}")
        return 1
    print("Local AI is ready for JobPilot's on-demand JD analysis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
