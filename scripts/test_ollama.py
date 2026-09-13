from app.ai.ollama_client import generate


def main() -> None:
    prompt = """
    You are JobPilot's AI assistant.

    Explain what a software engineer does in exactly 3 sentences.
    """

    answer = generate(prompt)

    print("\n--- Ollama Response ---\n")
    print(answer)


if __name__ == "__main__":
    main()