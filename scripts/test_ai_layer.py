"""Tests for the AI provider layer, runner (retry, cache, logging), fit analysis and endpoint.

Uses a fake provider and a temporary database: no Ollama, no network, never jobpilot.db.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_ai_layer.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.ai import providers  # noqa: E402
from app.ai.fit_analysis import deterministic_fit, make_validator, merge_fit  # noqa: E402
from app.ai.providers import ProviderModelMissing, ProviderResponseError, ProviderUnavailable  # noqa: E402
from app.ai.runner import INVALID, MODEL_MISSING, OK, UNAVAILABLE, run_structured  # noqa: E402
from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.db.models import AiCacheEntry  # noqa: E402
from scripts.test_structured_job_matching import build_candidate_profile  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeProvider:
    name = "fake"

    def __init__(self, steps):
        self.steps = list(steps)  # each: str (returned) or Exception (raised)
        self.calls = 0
        self.model = "fake-model-1"

    def model_name(self):
        return self.model

    def status(self):
        return {"provider": self.name, "available": True}

    def generate_structured(self, prompt, schema, *, system=None, timeout=None):
        self.calls += 1
        step = self.steps[min(self.calls - 1, len(self.steps) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


def _validate(raw):
    payload = json.loads(raw)
    if "answer" not in payload:
        raise ValueError("no answer")
    return {"answer": str(payload["answer"])}


def _run(provider, session=None, **overrides):
    sleeps = overrides.pop("sleeps", [])
    args = dict(task="t", prompt_version="v1", prompt="PROMPT", schema={}, system=None, validate=_validate,
                cache_parts={"x": 1}, session=session, provider=provider, backoff_seconds=0.5, sleep=sleeps.append)
    args.update(overrides)
    return run_structured(**args)


def _fresh():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_provider_selection() -> None:
    os.environ.pop("JOBPILOT_AI_PROVIDER", None)
    check(providers.get_provider().name == "ollama", "local Ollama is the default")
    check(set(providers._REGISTRY) == {"ollama", "none", "disabled"}, f"no external provider ships enabled: {set(providers._REGISTRY)}")
    check(providers.get_provider("none").status()["available"] is False, "none = AI off")
    try:
        providers.get_provider("openai")
    except ValueError as exc:
        check("explicitly" in str(exc), str(exc))
    else:
        raise AssertionError("an unregistered external provider must not be selectable")
    providers.register_provider("fake-x", lambda: FakeProvider(['{"answer": 1}']))
    check(providers.get_provider("fake-x").name == "fake", "an explicitly registered provider is selectable")
    os.environ["JOBPILOT_AI_PROVIDER"] = "none"
    try:
        check(providers.get_provider().name == "none", "environment variable selects the provider")
    finally:
        os.environ.pop("JOBPILOT_AI_PROVIDER", None)


def test_runner_cache_and_versions() -> None:
    session = _fresh()
    try:
        provider = FakeProvider(['{"answer": "hello", "junk": "dropped"}'])
        first = _run(provider, session)
        check(first.status == OK and first.result == {"answer": "hello"} and not first.cached, f"{first}")
        second = _run(provider, session)
        check(second.cached and provider.calls == 1, "same question is answered from the cache")
        check(_run(provider, session, prompt_version="v2").cached is False and provider.calls == 2, "a new prompt version asks again")
        provider.model = "fake-model-2"
        check(_run(provider, session).cached is False and provider.calls == 3, "a different model asks again")
        provider.model = "fake-model-1"
        check(_run(provider, session, cache_parts={"x": 2}).cached is False, "different inputs ask again")
        before = provider.calls
        check(_run(provider, session, use_cache=False).cached is False and provider.calls == before + 1, "refresh bypasses the cache")
        rows = session.scalars(select(AiCacheEntry)).all()
        check(all("PROMPT" not in r.result_json and "junk" not in r.result_json for r in rows), "only the validated result is stored")
    finally:
        session.close()


def test_runner_failures_and_retries() -> None:
    session = _fresh()
    try:
        sleeps: list[float] = []
        down = FakeProvider([ProviderUnavailable("connection refused")])
        run = _run(down, session, sleeps=sleeps, cache_parts={"x": "down"})
        check(run.status == UNAVAILABLE and run.attempts == 3 and down.calls == 3, f"{run}")
        check(sleeps == [0.5, 1.0], f"exponential backoff between attempts: {sleeps}")
        check(session.scalars(select(AiCacheEntry)).all() == [], "failures are never cached")

        flaky = FakeProvider([ProviderUnavailable("blip"), '{"answer": "ok"}'])
        recovered = _run(flaky, session, sleeps=[], cache_parts={"x": "flaky"})
        check(recovered.status == OK and recovered.attempts == 2, "a transient failure is retried")

        missing = FakeProvider([ProviderModelMissing("model not installed")])
        run = _run(missing, session, cache_parts={"x": "missing"})
        check(run.status == MODEL_MISSING and missing.calls == 1, "a missing model is not retried")

        junk = FakeProvider(["not json", '{"nope": 1}'])
        run = _run(junk, session, cache_parts={"x": "junk"})
        check(run.status == INVALID and run.result is None and junk.calls == 2, f"unusable output: one retry then give up: {run}")

        broken = FakeProvider([ProviderResponseError("empty response")])
        check(_run(broken, session, cache_parts={"x": "broken"}).status == INVALID, "provider response errors surface as invalid output")
    finally:
        session.close()


def test_logging_has_metadata_only() -> None:
    session = _fresh()
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    logger = logging.getLogger("jobpilot.ai")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        _run(FakeProvider(['{"answer": "SECRET-ANSWER"}']), session, prompt="SECRET-PROMPT-TEXT with personal details")
    finally:
        logger.removeHandler(handler)
        session.close()
    joined = " ".join(records)
    check("task=t" in joined and "model=fake-model-1" in joined and "status=ok" in joined, joined)
    check("SECRET-PROMPT-TEXT" not in joined and "SECRET-ANSWER" not in joined and "personal details" not in joined, "logs must not contain prompt or answer text")


def test_fit_validation_and_merge() -> None:
    job_text = "Backend Engineer. Minimum qualifications: 1 year with Java, Python and Docker. Kubernetes is a plus."
    profile = {"Java", "Python"}
    validate = make_validator(job_text=job_text, profile_skills=profile)
    good = validate(json.dumps({
        "overall_match_score": 250, "skills_matched": ["Java", "Python", "COBOL", "Docker"],
        "skills_missing": ["Docker", "Kubernetes", "Fortran", "Java"], "experience_fit": "nonsense",
        "strengths": ["Strong Java"], "weaknesses": [], "risks": [], "suggested_preparation": ["Learn Docker"],
        "application_recommendation": "maybe",
    }))
    check(good["skills_matched"] == ["Java", "Python"], f"only profile+job skills kept: {good['skills_matched']}")
    check(good["skills_missing"] == ["Docker", "Kubernetes"], f"only job skills the profile lacks: {good['skills_missing']}")
    check(good["ai_score"] == 100.0 and good["experience_fit"] == "unclear" and good["application_recommendation"] is None, f"{good}")
    for bad in ("not json", "[1, 2]"):
        try:
            validate(bad)
        except ProviderResponseError:
            continue
        raise AssertionError(f"accepted invalid output {bad!r}")

    excluded = {"score": 30.0, "recommendation": "low_match", "eligibility": {"status": "excluded", "reasons": ["senior_or_lead_title"]},
                "missing_required_skills": ["Docker"], "reasons": ["r"], "concerns": ["c"], "mismatches": {}}
    merged = merge_fit({**good, "application_recommendation": "apply_now", "ai_score": 95.0}, excluded)
    check(merged["application_recommendation"] == "skip" and merged["overall_match_score"] == 30.0, f"rules win: {merged}")
    check(any("rules win" in n for n in merged["notes"]) and any("differs a lot" in n for n in merged["notes"]), "both conflicts are explained")
    check(any("Excluded by the eligibility policy" in r for r in merged["risks"]), "deterministic risks are always included")

    good_match = {"score": 80.0, "recommendation": "strong_match", "eligibility": {"status": "eligible"}, "missing_required_skills": [],
                  "reasons": [], "concerns": [], "mismatches": {}}
    cautious = merge_fit({**good, "application_recommendation": "review_first", "ai_score": 78.0}, good_match)
    check(cautious["application_recommendation"] == "review_first", "the model may be more cautious than the rules")
    plain = merge_fit(None, good_match)
    check(plain["source"] == "deterministic" and plain["application_recommendation"] == "apply_now" and plain["overall_match_score"] == 80.0, f"{plain}")
    check(deterministic_fit({**good_match, "missing_required_skills": ["Docker"]})["application_recommendation"] == "prepare_missing_skills", "gaps -> prepare")


def test_fit_endpoint() -> None:
    session = _fresh()
    try:
        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        long_text = ("Minimum qualifications: 1 year of experience with software development using Java, Python, Docker, Kubernetes. "
                     "You will build backend services.")
        ids = {}
        for key, title, desc in (("ok", "Backend Engineer", long_text), ("short", "Frontend Engineer", "Short."),
                                 ("senior", "Senior Staff Backend Engineer", long_text)):
            ids[key] = repo.upsert_job_detailed(company, {"source": "lever:acme", "external_id": key, "title": title,
                                                           "location": ["Hyderabad, India"], "url": f"https://acme.example/{key}",
                                                           "description": desc}).job.id
        session.commit()
    finally:
        session.close()

    api_main._candidate_profile = lambda: build_candidate_profile()
    fake = FakeProvider([json.dumps({
        "overall_match_score": 92, "skills_matched": ["Java", "Python"], "skills_missing": ["Docker", "Kubernetes", "Haskell"],
        "experience_fit": "good", "strengths": ["Core languages match"], "weaknesses": ["No container experience"],
        "risks": [], "suggested_preparation": ["Practise Docker"], "application_recommendation": "apply_now"})])
    providers.register_provider("fake", lambda: fake)
    client = TestClient(api_main.app)
    os.environ["JOBPILOT_AI_PROVIDER"] = "fake"
    try:
        body = client.post(f"/api/jobs/{ids['ok']}/ai-fit").json()
        check(body["ai"]["status"] == "ok" and body["fit"]["source"] == "ai" and not body["ai"]["cached"], f"{body}")
        check("Haskell" not in body["fit"]["skills_missing"] and "Docker" in body["fit"]["skills_missing"], "hallucinated skill dropped")
        check(body["fit"]["overall_match_score"] <= 100 and body["fit"]["overall_match_score"] != 92, "the rule-based score is the score shown")
        again = client.post(f"/api/jobs/{ids['ok']}/ai-fit").json()
        check(again["ai"]["cached"] and fake.calls == 1, "second request is served from the cache")
        client.post(f"/api/jobs/{ids['ok']}/ai-fit", params={"refresh": "true"})
        check(fake.calls == 2, "refresh asks the model again")

        senior = client.post(f"/api/jobs/{ids['senior']}/ai-fit").json()
        check(senior["fit"]["application_recommendation"] == "skip", f"an excluded job is never 'apply_now': {senior['fit']['application_recommendation']}")

        short = client.post(f"/api/jobs/{ids['short']}/ai-fit").json()
        check(short["ai"]["status"] == "skipped" and short["fit"]["source"] == "deterministic", "a too-short description skips the model")

        os.environ["JOBPILOT_AI_PROVIDER"] = "none"
        off = client.post(f"/api/jobs/{ids['ok']}/ai-fit").json()
        check(off["ai"]["status"] == "unavailable" and off["fit"]["source"] == "deterministic", f"works with AI off: {off['ai']}")
        check(client.get("/api/ai/status").json()["provider"] == "none", "status reports the selected provider")
        os.environ["JOBPILOT_AI_PROVIDER"] = "does-not-exist"
        broken = client.post(f"/api/jobs/{ids['ok']}/ai-fit").json()
        check(broken["fit"]["source"] == "deterministic" and "Unknown AI provider" in broken["ai"]["error"], "a bad provider setting degrades gracefully")
        check(client.post("/api/jobs/99999/ai-fit").status_code == 404, "unknown job -> 404")
    finally:
        os.environ.pop("JOBPILOT_AI_PROVIDER", None)


TESTS = [
    ("Provider selection and defaults", test_provider_selection),
    ("Runner cache keys and prompt versions", test_runner_cache_and_versions),
    ("Runner retries and failure statuses", test_runner_failures_and_retries),
    ("Logging contains metadata only", test_logging_has_metadata_only),
    ("Fit validation and rule-based authority", test_fit_validation_and_merge),
    ("POST /api/jobs/{id}/ai-fit end to end", test_fit_endpoint),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    engine.dispose()
    api_main.engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
