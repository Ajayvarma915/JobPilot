import requests

from app.config import OLLAMA_MODEL, OLLAMA_URL


def generate(
    prompt: str,
    model: str = OLLAMA_MODEL,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    data = response.json()

    return data["response"]