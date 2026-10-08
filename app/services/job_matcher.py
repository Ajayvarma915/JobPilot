from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable

from app.services.jd_analyzer import (
    JobAnalysis,
    JobDescriptionAnalyzer,
)


@dataclass
class JobMatchResult:
    """
    Final candidate-to-job relevance result.

    All component scores are normalized to the weights below:

        Role        : 25
        Seniority   : 20
        Experience  : 20
        Skills      : 20
        Education   : 10
        Location    : 5

    Total          : 100
    """

    score: float

    recommendation: str

    role_score: float
    seniority_score: float
    experience_score: float
    skills_score: float
    education_score: float
    location_score: float

    matched_skills: list[str] = field(default_factory=list)

    required_skills: list[str] = field(default_factory=list)
    missing_required_skills: list[str] = field(default_factory=list)

    preferred_skills: list[str] = field(default_factory=list)
    matched_preferred_skills: list[str] = field(default_factory=list)

    required_years: float | None = None

    required_education: list[str] = field(default_factory=list)

    hard_constraints: list[str] = field(default_factory=list)

    reasons: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)

    analysis_confidence: str = "low"

    role_family: str = "other"
    seniority: str = "unknown"

    @property
    def skills_matched(self) -> list[str]:
        """
        Backward-compatible alias for earlier matcher output.
        """
        return self.matched_skills

    @property
    def total_score(self) -> float:
        return self.score


class JobMatcher:
    """
    Match a candidate profile against a Job + structured JobAnalysis.

    This matcher is deterministic and does not call an external API.
    """

    ROLE_WEIGHT = 25.0
    SENIORITY_WEIGHT = 20.0
    EXPERIENCE_WEIGHT = 20.0
    SKILLS_WEIGHT = 20.0
    EDUCATION_WEIGHT = 10.0
    LOCATION_WEIGHT = 5.0

    STRONG_MATCH_THRESHOLD = 75.0
    GOOD_MATCH_THRESHOLD = 60.0
    REVIEW_THRESHOLD = 45.0

    ROLE_SCORES = {
        "software_engineering": 25.0,
        "frontend": 25.0,
        "full_stack": 25.0,
        "backend": 25.0,
        "cloud_devops": 18.0,
        "systems": 18.0,
        "security": 18.0,
        "data": 15.0,
        "ai_ml": 15.0,
        "engineering_other": 10.0,
        "internship": 8.0,
        "other": 5.0,
        "management": 0.0,
        "product": 0.0,
        "program_management": 0.0,
    }

    SENIORITY_SCORES = {
        "entry": 20.0,
        "mid": 16.0,
        "intern": 8.0,
        "senior": 6.0,
        "staff": 2.0,
        "principal": 1.0,
        "manager": 0.0,
        "executive": 0.0,
        "unknown": 8.0,
    }

    ROLE_COMPATIBILITY: dict[str, set[str]] = {
        "software_engineering": {
            "software_engineering",
            "backend",
            "frontend",
            "full_stack",
        },
        "frontend": {
            "frontend",
            "full_stack",
            "software_engineering",
        },
        "full_stack": {
            "full_stack",
            "frontend",
            "backend",
            "software_engineering",
        },
        "backend": {
            "backend",
            "full_stack",
            "software_engineering",
        },
        "cloud_devops": {
            "cloud_devops",
            "systems",
            "software_engineering",
        },
        "systems": {
            "systems",
            "cloud_devops",
            "software_engineering",
        },
        "security": {
            "security",
            "software_engineering",
            "systems",
        },
        "data": {
            "data",
            "software_engineering",
            "ai_ml",
        },
        "ai_ml": {
            "ai_ml",
            "software_engineering",
            "data",
        },
        "engineering_other": {
            "engineering_other",
            "software_engineering",
            "systems",
            "cloud_devops",
        },
    }

    SKILL_ALIASES: dict[str, set[str]] = {
        "Java": {
            "java",
        },
        "Python": {
            "python",
        },
        "JavaScript": {
            "javascript",
            "js",
            "ecmascript",
        },
        "TypeScript": {
            "typescript",
            "ts",
        },
        "C++": {
            "c++",
            "cpp",
        },
        "C#": {
            "c#",
            "c sharp",
            "csharp",
        },
        "Go": {
            "go",
            "golang",
        },
        "Kotlin": {
            "kotlin",
        },
        "Swift": {
            "swift",
        },
        "HTML": {
            "html",
            "html5",
        },
        "CSS": {
            "css",
            "css3",
        },
        "React.js": {
            "react",
            "react.js",
            "reactjs",
        },
        "Next.js": {
            "next",
            "next.js",
            "nextjs",
        },
        "Node.js": {
            "node",
            "node.js",
            "nodejs",
        },
        "Express.js": {
            "express",
            "express.js",
            "expressjs",
        },
        "Angular": {
            "angular",
        },
        "Vue.js": {
            "vue",
            "vue.js",
            "vuejs",
        },
        "Spring": {
            "spring",
            "spring boot",
        },
        ".NET": {
            ".net",
            "dotnet",
            "asp.net",
        },
        "Django": {
            "django",
        },
        "Flask": {
            "flask",
        },
        "FastAPI": {
            "fastapi",
        },
        "SQL": {
            "sql",
        },
        "MySQL": {
            "mysql",
        },
        "PostgreSQL": {
            "postgresql",
            "postgres",
        },
        "MongoDB": {
            "mongodb",
            "mongo",
            "mongo db",
        },
        "Redis": {
            "redis",
        },
        "Kafka": {
            "kafka",
        },
        "GraphQL": {
            "graphql",
        },
        "REST APIs": {
            "rest",
            "rest api",
            "rest apis",
            "restful api",
            "restful apis",
        },
        "Git": {
            "git",
        },
        "GitHub": {
            "github",
        },
        "Linux": {
            "linux",
        },
        "Docker": {
            "docker",
        },
        "Kubernetes": {
            "kubernetes",
            "k8s",
        },
        "Terraform": {
            "terraform",
        },
        "AWS": {
            "aws",
            "amazon web services",
        },
        "Azure": {
            "azure",
            "microsoft azure",
        },
        "Google Cloud": {
            "google cloud",
            "gcp",
        },
        "Data Structures and Algorithms": {
            "data structures and algorithms",
            "data structures & algorithms",
            "dsa",
            "algorithms",
        },
        "Machine Learning": {
            "machine learning",
            "ml",
        },
        "Deep Learning": {
            "deep learning",
            "dl",
        },
        "Artificial Intelligence": {
            "artificial intelligence",
            "ai",
        },
        "NLP": {
            "nlp",
            "natural language processing",
        },
        "LLM": {
            "llm",
            "llms",
            "large language model",
            "large language models",
        },
        "RAG": {
            "rag",
            "retrieval augmented generation",
        },
        "LangChain": {
            "langchain",
        },
        "TensorFlow": {
            "tensorflow",
        },
        "PyTorch": {
            "pytorch",
        },
        "Spark": {
            "spark",
            "apache spark",
        },
        "Hadoop": {
            "hadoop",
        },
        "Databricks": {
            "databricks",
        },
        "Snowflake": {
            "snowflake",
        },
    }

    def __init__(
        self,
        candidate_profile: Any,
        analyzer: JobDescriptionAnalyzer | None = None,
    ) -> None:
        self.candidate_profile = candidate_profile
        self.analyzer = (
            analyzer
            if analyzer is not None
            else JobDescriptionAnalyzer()
        )

    def match(
        self,
        job: Any,
        analysis: JobAnalysis | None = None,
    ) -> JobMatchResult:
        """
        Match one job against the candidate profile.

        When analysis is omitted, the JD Analyzer runs automatically.
        """

        if analysis is None:
            analysis = self.analyzer.analyze_job(job)

        role_family = self._infer_role_family(
            analysis.title
        )

        seniority = self._infer_seniority(
            analysis.title
        )

        candidate_skills = self._candidate_skills()

        role_score = self._score_role(
            role_family
        )

        seniority_score = self._score_seniority(
            seniority
        )

        experience_score = self._score_experience(
            analysis.required_years_min
        )

        (
            skills_score,
            matched_required,
            missing_required,
            matched_preferred,
        ) = self._score_skills(
            analysis=analysis,
            candidate_skills=candidate_skills,
        )

        education_score = self._score_education(
            analysis
        )

        location_score = self._score_location(
            job=job,
            analysis=analysis,
        )

        raw_score = (
            role_score
            + seniority_score
            + experience_score
            + skills_score
            + education_score
            + location_score
        )

        score = self._apply_caps(
            raw_score=raw_score,
            analysis=analysis,
            role_family=role_family,
            seniority=seniority,
        )

        recommendation = self._recommendation(
            score
        )

        reasons = self._build_reasons(
            role_family=role_family,
            seniority=seniority,
            required_years=analysis.required_years_min,
            matched_required=matched_required,
            matched_preferred=matched_preferred,
            education_score=education_score,
            location_score=location_score,
        )

        concerns = self._build_concerns(
            analysis=analysis,
            missing_required=missing_required,
            role_family=role_family,
            seniority=seniority,
        )

        return JobMatchResult(
            score=round(score, 2),
            recommendation=recommendation,
            role_score=round(
                role_score,
                2,
            ),
            seniority_score=round(
                seniority_score,
                2,
            ),
            experience_score=round(
                experience_score,
                2,
            ),
            skills_score=round(
                skills_score,
                2,
            ),
            education_score=round(
                education_score,
                2,
            ),
            location_score=round(
                location_score,
                2,
            ),
            matched_skills=matched_required,
            required_skills=list(
                analysis.required_skills
            ),
            missing_required_skills=missing_required,
            preferred_skills=list(
                analysis.preferred_skills
            ),
            matched_preferred_skills=matched_preferred,
            required_years=analysis.required_years_min,
            required_education=list(
                analysis.required_education
            ),
            hard_constraints=list(
                analysis.hard_constraints
            ),
            reasons=reasons,
            concerns=concerns,
            analysis_confidence=analysis.confidence,
            role_family=role_family,
            seniority=seniority,
        )

    def match_job(
        self,
        job: Any,
        analysis: JobAnalysis | None = None,
    ) -> JobMatchResult:
        """
        Explicit job-oriented alias.
        """
        return self.match(
            job=job,
            analysis=analysis,
        )

    def score_job(
        self,
        job: Any,
        analysis: JobAnalysis | None = None,
    ) -> JobMatchResult:
        """
        Compatibility alias for callers that use score_job().
        """
        return self.match(
            job=job,
            analysis=analysis,
        )

    def match_jobs(
        self,
        jobs: Iterable[Any],
    ) -> list[JobMatchResult]:
        """
        Match multiple jobs.
        """
        results = [
            self.match(job)
            for job in jobs
        ]

        return sorted(
            results,
            key=lambda result: result.score,
            reverse=True,
        )

    def _candidate_skills(self) -> set[str]:
        """
        Collect skills from the candidate profile.

        The implementation supports both dataclass/object profiles
        and dictionaries so the matcher remains loosely coupled to
        the profile representation.
        """

        fields = (
            "technical_skills",
            "programming_languages",
            "frontend_skills",
            "frameworks",
            "tools",
            "concepts",
            "project_skills",
            "internship_skills",
            "skills",
        )

        raw_values: list[Any] = []

        for field_name in fields:
            value = self._get(
                self.candidate_profile,
                field_name,
                None,
            )

            if value is None:
                continue

            if isinstance(value, str):
                raw_values.append(value)
            elif isinstance(value, Iterable):
                raw_values.extend(
                    value
                )

        canonical_skills: set[str] = set()

        for value in raw_values:
            canonical = self._canonical_skill(
                str(value)
            )

            if canonical is not None:
                canonical_skills.add(
                    canonical
                )

        return canonical_skills

    def _score_role(
        self,
        role_family: str,
    ) -> float:
        target_families = self._candidate_target_roles()

        if not target_families:
            return self.ROLE_SCORES.get(
                role_family,
                5.0,
            )

        if role_family in target_families:
            return 25.0

        for target_family in target_families:
            compatible = self.ROLE_COMPATIBILITY.get(
                target_family,
                set(),
            )

            if role_family in compatible:
                return 20.0

        return self.ROLE_SCORES.get(
            role_family,
            5.0,
        )

    def _score_seniority(
        self,
        seniority: str,
    ) -> float:
        target_seniorities = (
            self._candidate_target_seniority()
        )

        if (
            target_seniorities
            and seniority in target_seniorities
        ):
            return 20.0

        return self.SENIORITY_SCORES.get(
            seniority,
            8.0,
        )

    def _score_experience(
        self,
        required_years: float | None,
    ) -> float:
        candidate_years = self._candidate_years()

        if required_years is None:
            return 20.0

        if required_years <= candidate_years:
            return 20.0

        gap = required_years - candidate_years

        # A one-year requirement is treated as a small,
        # entry-level gap rather than an automatic rejection.
        if gap <= 1.0:
            return 14.0

        if gap <= 2.0:
            return 8.0

        if gap <= 3.0:
            return 4.0

        return 0.0

    def _score_skills(
        self,
        analysis: JobAnalysis,
        candidate_skills: set[str],
    ) -> tuple[
        float,
        list[str],
        list[str],
        list[str],
    ]:
        required = [
            self._canonical_skill(skill)
            or skill
            for skill in analysis.required_skills
        ]

        preferred = [
            self._canonical_skill(skill)
            or skill
            for skill in analysis.preferred_skills
        ]

        technologies = [
            self._canonical_skill(skill)
            or skill
            for skill in analysis.technologies
        ]

        required = self._unique(
            required
        )

        preferred = self._unique(
            preferred
        )

        technologies = self._unique(
            technologies
        )

        matched_required = [
            skill
            for skill in required
            if skill in candidate_skills
        ]

        missing_required = [
            skill
            for skill in required
            if skill not in candidate_skills
        ]

        matched_preferred = [
            skill
            for skill in preferred
            if skill in candidate_skills
        ]

        # Main path: explicit required + preferred skill sets.
        if required:
            required_ratio = (
                len(matched_required)
                / len(required)
            )

            required_score = (
                required_ratio * 15.0
            )

            if preferred:
                preferred_ratio = (
                    len(matched_preferred)
                    / len(preferred)
                )

                preferred_score = (
                    preferred_ratio * 5.0
                )
            else:
                preferred_score = 0.0

            return (
                min(
                    20.0,
                    required_score
                    + preferred_score,
                ),
                matched_required,
                missing_required,
                matched_preferred,
            )

        # When the analyzer cannot determine explicit required skills,
        # use preferred skills first and technologies as secondary
        # evidence. This prevents an empty required-skill field from
        # incorrectly producing a zero score.
        if preferred:
            preferred_ratio = (
                len(matched_preferred)
                / len(preferred)
            )

            preferred_score = (
                preferred_ratio * 12.0
            )

            tech_matches = [
                skill
                for skill in technologies
                if skill in candidate_skills
                and skill not in matched_preferred
            ]

            technology_ratio = (
                len(tech_matches)
                / len(technologies)
                if technologies
                else 0.0
            )

            technology_score = (
                technology_ratio * 8.0
            )

            return (
                min(
                    20.0,
                    preferred_score
                    + technology_score,
                ),
                [],
                [],
                matched_preferred,
            )

        if technologies:
            matched_technologies = [
                skill
                for skill in technologies
                if skill in candidate_skills
            ]

            technology_ratio = (
                len(matched_technologies)
                / len(technologies)
            )

            technology_score = (
                technology_ratio * 12.0
            )

            return (
                min(
                    12.0,
                    technology_score,
                ),
                matched_technologies,
                [],
                [],
            )

        return (
            0.0,
            [],
            [],
            [],
        )

    def _score_education(
        self,
        analysis: JobAnalysis,
    ) -> float:
        required = {
            value.lower()
            for value in analysis.required_education
        }

        preferred = {
            value.lower()
            for value in analysis.preferred_education
        }

        candidate_education = (
            self._candidate_degree()
        )

        if not required and not preferred:
            return 10.0

        if "phd" in required:
            return (
                10.0
                if candidate_education == "phd"
                else 0.0
            )

        if "master" in required:
            if candidate_education in {
                "master",
                "phd",
            }:
                return 10.0

            return 0.0

        if "bachelor" in required:
            if candidate_education in {
                "bachelor",
                "master",
                "phd",
            }:
                return 10.0

            return 5.0

        if preferred:
            if candidate_education in preferred:
                return 10.0

            return 8.0

        return 10.0

    def _score_location(
        self,
        job: Any,
        analysis: JobAnalysis,
    ) -> float:
        target_locations = (
            self._candidate_locations()
        )

        if not target_locations:
            return 3.0

        job_location = self._get(
            job,
            "location",
            None,
        )

        values: list[str] = []

        if job_location:
            if isinstance(
                job_location,
                str,
            ):
                values.extend(
                    re.split(
                        r"[;|]+",
                        job_location,
                    )
                )
            else:
                values.extend(
                    str(item)
                    for item in job_location
                )

        values.extend(
            analysis.location_requirements
        )

        text = " ".join(
            str(value)
            for value in values
        ).lower()

        for location in target_locations:
            if location.lower() in text:
                return 5.0

        return 0.0

    def _apply_caps(
        self,
        raw_score: float,
        analysis: JobAnalysis,
        role_family: str,
        seniority: str,
    ) -> float:
        score = min(
            100.0,
            max(0.0, raw_score),
        )

        # A direct PhD requirement is a hard education blocker
        # for this candidate profile.
        if "phd" in {
            value.lower()
            for value in analysis.required_education
        }:
            score = min(
                score,
                35.0,
            )

        # Explicit managerial/leadership roles should not surface
        # as realistic matches for a fresher engineering candidate.
        if role_family in {
            "management",
            "product",
            "program_management",
        }:
            score = min(
                score,
                35.0,
            )

        # Substantial experience requirements should keep senior/staff
        # positions out of the top recommendations.
        required_years = (
            analysis.required_years_min
        )

        candidate_years = (
            self._candidate_years()
        )

        if (
            required_years is not None
            and required_years
            > candidate_years + 3.0
        ):
            score = min(
                score,
                59.0,
            )

        # Additional protection for staff/principal/executive roles.
        if seniority in {
            "staff",
            "principal",
            "executive",
        }:
            score = min(
                score,
                59.0,
            )

        return score

    def _recommendation(
        self,
        score: float,
    ) -> str:
        if score >= self.STRONG_MATCH_THRESHOLD:
            return "strong_match"

        if score >= self.GOOD_MATCH_THRESHOLD:
            return "good_match"

        if score >= self.REVIEW_THRESHOLD:
            return "review"

        return "low_match"

    def _build_reasons(
        self,
        role_family: str,
        seniority: str,
        required_years: float | None,
        matched_required: list[str],
        matched_preferred: list[str],
        education_score: float,
        location_score: float,
    ) -> list[str]:
        reasons: list[str] = []

        if self._candidate_target_roles():
            target_roles = (
                self._candidate_target_roles()
            )

            if role_family in target_roles:
                reasons.append(
                    "Role family matches a target role."
                )
            elif role_family in {
                "frontend",
                "backend",
                "full_stack",
                "software_engineering",
            }:
                reasons.append(
                    "Engineering role is closely related "
                    "to the candidate's target roles."
                )

        if seniority in {
            "entry",
            "mid",
        }:
            reasons.append(
                f"Seniority is {seniority}-level."
            )

        if required_years is None:
            reasons.append(
                "No explicit minimum years requirement "
                "was detected."
            )
        elif required_years <= 1:
            reasons.append(
                "Experience requirement is close to "
                "entry-level."
            )

        if matched_required:
            reasons.append(
                "Required skill overlap: "
                + ", ".join(
                    matched_required
                )
                + "."
            )

        if matched_preferred:
            reasons.append(
                "Preferred skill overlap: "
                + ", ".join(
                    matched_preferred
                )
                + "."
            )

        if education_score >= 10.0:
            reasons.append(
                "Education requirement is satisfied."
            )

        if location_score >= 5.0:
            reasons.append(
                "Target location is supported."
            )

        return reasons

    def _build_concerns(
        self,
        analysis: JobAnalysis,
        missing_required: list[str],
        role_family: str,
        seniority: str,
    ) -> list[str]:
        concerns: list[str] = []

        if missing_required:
            concerns.append(
                "Missing required skills: "
                + ", ".join(
                    missing_required
                )
                + "."
            )

        required_years = (
            analysis.required_years_min
        )

        candidate_years = (
            self._candidate_years()
        )

        if (
            required_years is not None
            and required_years > candidate_years
        ):
            concerns.append(
                f"JD requests {required_years:g}+ years "
                f"while the candidate profile contains "
                f"{candidate_years:g} years."
            )

        if "phd" in {
            value.lower()
            for value in analysis.required_education
        }:
            concerns.append(
                "PhD/doctorate is an explicit requirement."
            )

        if role_family in {
            "management",
            "product",
            "program_management",
        }:
            concerns.append(
                "Role is outside the candidate's "
                "software-engineering target."
            )

        if seniority in {
            "senior",
            "staff",
            "principal",
            "manager",
            "executive",
        }:
            concerns.append(
                f"Role seniority is {seniority}, "
                "which is above the candidate's primary target."
            )

        if (
            analysis.hard_constraints
            and not any(
                "PhD" in constraint
                for constraint
                in analysis.hard_constraints
            )
        ):
            concerns.extend(
                analysis.hard_constraints
            )

        return self._unique(
            concerns
        )

    def _candidate_target_roles(
        self,
    ) -> set[str]:
        value = self._get(
            self.candidate_profile,
            "target_role_families",
            [],
        )

        if value is None:
            return set()

        if isinstance(
            value,
            str,
        ):
            return {
                value.lower().strip()
            }

        return {
            str(item).lower().strip()
            for item in value
            if str(item).strip()
        }

    def _candidate_target_seniority(
        self,
    ) -> set[str]:
        value = self._get(
            self.candidate_profile,
            "target_seniority",
            None,
        )

        if value is None:
            value = self._get(
                self.candidate_profile,
                "target_seniorities",
                [],
            )

        if value is None:
            return set()

        if isinstance(
            value,
            str,
        ):
            return {
                value.lower().strip()
            }

        return {
            str(item).lower().strip()
            for item in value
            if str(item).strip()
        }

    def _candidate_locations(
        self,
    ) -> list[str]:
        value = self._get(
            self.candidate_profile,
            "target_locations",
            [],
        )

        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            return [value.strip()]

        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    def _candidate_years(
        self,
    ) -> float:
        value = self._get(
            self.candidate_profile,
            "years_of_experience",
            0.0,
        )

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

    def _candidate_degree(
        self,
    ) -> str:
        value = self._get(
            self.candidate_profile,
            "degree",
            None,
        )

        if value is None:
            education = self._get(
                self.candidate_profile,
                "education",
                "",
            )

            value = education

        text = str(
            value or ""
        ).lower()

        if (
            "phd" in text
            or "doctor" in text
        ):
            return "phd"

        if (
            "master" in text
            or "m.tech" in text
            or "mtech" in text
            or "m.s." in text
        ):
            return "master"

        if (
            "bachelor" in text
            or "b.tech" in text
            or "btech" in text
            or "b.e." in text
        ):
            return "bachelor"

        return "unknown"

    def _infer_role_family(
        self,
        title: str,
    ) -> str:
        text = title.lower().strip()

        # Highest-priority exclusions first.
        if re.search(
            r"\b(?:engineering|software)\s+manager\b"
            r"|\bmanager\b"
            r"|\bdirector\b"
            r"|\bhead\b",
            text,
        ):
            return "management"

        if re.search(
            r"\bproduct\s+manager\b",
            text,
        ):
            return "product"

        if re.search(
            r"\btechnical\s+program\s+manager\b"
            r"|\bprogram\s+manager\b",
            text,
        ):
            return "program_management"

        if re.search(
            r"\bintern\b"
            r"|\binternship\b"
            r"|\bphd\s+intern\b",
            text,
        ):
            return "internship"

        if re.search(
            r"\bfront[\s-]?end\b"
            r"|\bfrontend\b"
            r"|\bui\s+engineer\b"
            r"|\bweb\s+engineer\b",
            text,
        ):
            return "frontend"

        if re.search(
            r"\bfull[\s-]?stack\b",
            text,
        ):
            return "full_stack"

        if re.search(
            r"\bback[\s-]?end\b"
            r"|\bbackend\b",
            text,
        ):
            return "backend"

        if re.search(
            r"\bcloud\b"
            r"|\bdevops\b"
            r"|\bdeployment\b"
            r"|\bsre\b"
            r"|\bsite reliability\b",
            text,
        ):
            return "cloud_devops"

        if re.search(
            r"\bsecurity\b"
            r"|\bprivacy\b"
            r"|\bcyber\b"
            r"|\bidentity\b"
            r"|\biam\b",
            text,
        ):
            return "security"

        if re.search(
            r"\bsystems?\b"
            r"|\binfrastructure\b"
            r"|\bplatform\b",
            text,
        ):
            return "systems"

        if re.search(
            r"\bdata\b"
            r"|\banalytics\b"
            r"|\bdata\s+engineer\b",
            text,
        ):
            return "data"

        if re.search(
            r"\bai\b"
            r"|\bmachine\s+learning\b"
            r"|\bml\b"
            r"|\bllm\b"
            r"|\bgenai\b"
            r"|\bartificial intelligence\b",
            text,
        ):
            return "ai_ml"

        if re.search(
            r"\bengineer\b"
            r"|\bdeveloper\b"
            r"|\bprogrammer\b",
            text,
        ):
            return "software_engineering"

        return "other"

    def _infer_seniority(
        self,
        title: str,
    ) -> str:
        text = title.lower()

        if re.search(
            r"\bintern\b"
            r"|\binternship\b",
            text,
        ):
            return "intern"

        if re.search(
            r"\bmanager\b"
            r"|\bdirector\b",
            text,
        ):
            return "manager"

        if re.search(
            r"\bhead\b"
            r"|\bvice president\b"
            r"|\bvp\b"
            r"|\bchief\b",
            text,
        ):
            return "executive"

        if re.search(
            r"\bprincipal\b",
            text,
        ):
            return "principal"

        if re.search(
            r"\bstaff\b"
            r"|\bsenior staff\b",
            text,
        ):
            return "staff"

        if re.search(
            r"\bsenior\b"
            r"|\bsr\.\b"
            r"|\bsr\b",
            text,
        ):
            return "senior"

        if re.search(
            r"\biii\b"
            r"|\b3\b",
            text,
        ):
            return "mid"

        if re.search(
            r"\bii\b"
            r"|\b2\b"
            r"|\bsoftware engineer i\b"
            r"|\bengineer i\b",
            text,
        ):
            return "entry"

        if re.search(
            r"\bentry\b"
            r"|\bjunior\b"
            r"|\bassociate\b"
            r"|\bearly career\b"
            r"|\bnew grad\b"
            r"|\bgraduate\b",
            text,
        ):
            return "entry"

        return "unknown"

    def _canonical_skill(
        self,
        value: str,
    ) -> str | None:
        normalized = self._normalize_skill_text(
            value
        )

        if not normalized:
            return None

        for canonical, aliases in self.SKILL_ALIASES.items():
            if normalized == self._normalize_skill_text(
                canonical
            ):
                return canonical

            if normalized in {
                self._normalize_skill_text(alias)
                for alias in aliases
            }:
                return canonical

        return None

    def _normalize_skill_text(
        self,
        value: str,
    ) -> str:
        text = str(value).lower().strip()

        text = text.replace(
            "–",
            "-",
        )

        text = re.sub(
            r"[.\-_/]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    def _get(
        self,
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if obj is None:
            return default

        if isinstance(
            obj,
            dict,
        ):
            return obj.get(
                key,
                default,
            )

        return getattr(
            obj,
            key,
            default,
        )

    def _unique(
        self,
        values: Iterable[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            cleaned = str(
                value
            ).strip()

            if not cleaned:
                continue

            key = cleaned.lower()

            if key in seen:
                continue

            seen.add(key)
            result.append(cleaned)

        return result


__all__ = [
    "JobMatchResult",
    "JobMatcher",
]