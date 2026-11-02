from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_JOBS_DIR = DATA_DIR / "raw_jobs"
GENERATED_RESUMES_DIR = DATA_DIR / "generated_resumes"
GENERATED_COVER_LETTERS_DIR = DATA_DIR / "generated_cover_letters"
MASTER_RESUME_DIR = DATA_DIR / "master_resume"

# Local Ollama configuration. Override these with environment variables when
# using a different host, model, or timeout; no cloud API key is required.
OLLAMA_API_BASE = os.getenv("JOBPILOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_URL = os.getenv(
    "JOBPILOT_OLLAMA_GENERATE_URL",
    f"{OLLAMA_API_BASE}/api/generate",
)
OLLAMA_MODEL = os.getenv("JOBPILOT_OLLAMA_MODEL", "gemma3:4b")
try:
    OLLAMA_TIMEOUT_SECONDS = max(10, int(os.getenv("JOBPILOT_OLLAMA_TIMEOUT", "180")))
except ValueError:
    OLLAMA_TIMEOUT_SECONDS = 180
