from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_JOBS_DIR = DATA_DIR / "raw_jobs"
GENERATED_RESUMES_DIR = DATA_DIR / "generated_resumes"
GENERATED_COVER_LETTERS_DIR = DATA_DIR / "generated_cover_letters"
MASTER_RESUME_DIR = DATA_DIR / "master_resume"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b"