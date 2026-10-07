from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable


@dataclass
class JobAnalysis:
    """
    Structured representation of the important requirements
    extracted from a job description.
    """

    title: str
    sections: dict[str, str] = field(default_factory=dict)

    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)

    required_years_min: float | None = None
    preferred_years_min: float | None = None

    required_education: list[str] = field(default_factory=list)
    preferred_education: list[str] = field(default_factory=list)

    responsibilities: list[str] = field(default_factory=list)

    location_requirements: list[str] = field(default_factory=list)
    employment_type: str | None = None

    hard_constraints: list[str] = field(default_factory=list)

    confidence: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobDescriptionAnalyzer:
    """
    Deterministic job description analyzer.

    This analyzer intentionally does not call an external API or LLM.
    It provides an explainable baseline that can later be enriched
    with local AI.
    """

    SECTION_ALIASES: dict[str, set[str]] = {
        "about_job": {
            "about the job",
            "about this job",
            "job description",
            "description",
            "about the role",
            "role overview",
            "overview",
        },
        "minimum_qualifications": {
            "minimum qualifications",
            "minimum qualification",
            "basic qualifications",
            "basic qualification",
            "required qualifications",
            "required qualification",
            "qualifications",
            "requirements",
            "required requirements",
        },
        "preferred_qualifications": {
            "preferred qualifications",
            "preferred qualification",
            "preferred requirements",
            "preferred skills",
            "desired qualifications",
            "desired qualification",
            "nice to have",
            "nice-to-have",
            "additional qualifications",
        },
        "responsibilities": {
            "responsibilities",
            "responsibility",
            "duties",
            "key responsibilities",
            "what you'll do",
            "what you will do",
            "role responsibilities",
        },
    }

    REQUIRED_SECTION_NAMES = {
        "minimum_qualifications",
    }

    PREFERRED_SECTION_NAMES = {
        "preferred_qualifications",
    }

    REQUIRED_CUES = (
        "required",
        "must have",
        "must be",
        "minimum",
        "at least",
        "need to have",
        "should have",
        "strong proficiency",
        "proficiency in",
        "experience with",
        "experience in",
        "knowledge of",
        "expertise in",
        "hands-on experience",
        "hands on experience",
    )

    PREFERRED_CUES = (
        "preferred",
        "nice to have",
        "nice-to-have",
        "desired",
        "bonus",
        "plus",
        "familiarity with",
        "familiarity in",
        "would be a plus",
        "good to have",
    )

    SKILL_PATTERNS: dict[str, tuple[str, ...]] = {
        "Java": (
            r"(?<![A-Za-z])java(?![A-Za-z])",
        ),
        "Python": (
            r"(?<![A-Za-z])python(?![A-Za-z])",
        ),
        "JavaScript": (
            r"\bjavascript\b",
            r"\bjs\b",
        ),
        "TypeScript": (
            r"\btypescript\b",
            r"\bts\b",
        ),
        "C++": (
            r"c\+\+",
        ),
        "C#": (
            r"c#",
            r"c\s*sharp",
        ),
        "Go": (
            r"\bgolang\b",
            r"\bgo\s+programming\b",
            r"\bgo\s+language\b",
        ),
        "Kotlin": (
            r"\bkotlin\b",
        ),
        "Swift": (
            r"\bswift\b",
        ),
        "HTML": (
            r"\bhtml5?\b",
        ),
        "CSS": (
            r"\bcss3?\b",
            r"\bcascading style sheets\b",
        ),
        "React.js": (
            r"\breact(?:\.js)?\b",
            r"\breactjs\b",
        ),
        "Next.js": (
            r"\bnext(?:\.js)?\b",
            r"\bnextjs\b",
        ),
        "Node.js": (
            r"\bnode(?:\.js)?\b",
            r"\bnodejs\b",
        ),
        "Express.js": (
            r"\bexpress(?:\.js)?\b",
            r"\bexpressjs\b",
        ),
        "Angular": (
            r"\bangular(?:\.js)?\b",
        ),
        "Vue.js": (
            r"\bvue(?:\.js)?\b",
            r"\bvuejs\b",
        ),
        "Spring": (
            r"\bspring(?:\s+boot)?\b",
            r"\bspring boot\b",
        ),
        ".NET": (
            r"\.net\b",
            r"\basp\.net\b",
            r"\baspnet\b",
        ),
        "Django": (
            r"\bdjango\b",
        ),
        "Flask": (
            r"\bflask\b",
        ),
        "FastAPI": (
            r"\bfastapi\b",
        ),
        "SQL": (
            r"\bsql\b",
        ),
        "MySQL": (
            r"\bmysql\b",
        ),
        "PostgreSQL": (
            r"\bpostgresql\b",
            r"\bpostgres\b",
        ),
        "MongoDB": (
            r"\bmongodb\b",
            r"\bmongo\s*db\b",
        ),
        "Redis": (
            r"\bredis\b",
        ),
        "Kafka": (
            r"\bkafka\b",
        ),
        "GraphQL": (
            r"\bgraphql\b",
        ),
        "REST APIs": (
            r"\brestful?\s+apis?\b",
            r"\brest\s+apis?\b",
            r"\brestful\s+services?\b",
        ),
        "Git": (
            r"\bgit\b",
        ),
        "GitHub": (
            r"\bgithub\b",
        ),
        "Linux": (
            r"\blinux\b",
        ),
        "Docker": (
            r"\bdocker\b",
        ),
        "Kubernetes": (
            r"\bkubernetes\b",
            r"\bk8s\b",
        ),
        "Terraform": (
            r"\bterraform\b",
        ),
        "AWS": (
            r"\baws\b",
            r"\bamazon web services\b",
        ),
        "Azure": (
            r"\bazure\b",
            r"\bmicrosoft azure\b",
        ),
        "Google Cloud": (
            r"\bgoogle cloud\b",
            r"\bgcp\b",
        ),
        "Data Structures and Algorithms": (
            r"\bdata structures?\s+and\s+algorithms?\b",
            r"\bdata structures?\s*&\s*algorithms?\b",
        ),
        "Machine Learning": (
            r"\bmachine learning\b",
        ),
        "Deep Learning": (
            r"\bdeep learning\b",
        ),
        "Artificial Intelligence": (
            r"\bartificial intelligence\b",
        ),
        "NLP": (
            r"\bnatural language processing\b",
            r"\bnlp\b",
        ),
        "LLM": (
            r"\blarge language models?\b",
            r"\bllms?\b",
        ),
        "RAG": (
            r"\bretrieval[-\s]+augmented generation\b",
            r"\brag\b",
        ),
        "LangChain": (
            r"\blangchain\b",
        ),
        "TensorFlow": (
            r"\btensorflow\b",
        ),
        "PyTorch": (
            r"\bpytorch\b",
        ),
        "Spark": (
            r"\bapache spark\b",
            r"\bspark\b",
        ),
        "Hadoop": (
            r"\bhadoop\b",
        ),
        "Databricks": (
            r"\bdatabricks\b",
        ),
        "Snowflake": (
            r"\bsnowflake\b",
        ),
    }

    EDUCATION_PATTERNS: dict[str, tuple[str, ...]] = {
        "phd": (
            r"\bph\.?d\.?\b",
            r"\bdoctorate\b",
            r"\bdoctoral degree\b",
        ),
        "master": (
            r"\bmaster'?s?\b",
            r"\bmasters?\s+degree\b",
            r"\bm\.?s\.?\b",
            r"\bm\.?tech\b",
            r"\bm\.?e\.?\b",
            r"\bmba\b",
            r"\bmaster of science\b",
            r"\bmaster of technology\b",
        ),
        "bachelor": (
            r"\bbachelor'?s?\b",
            r"\bbachelors?\s+degree\b",
            r"\bb\.?s\.?\b",
            r"\bb\.?e\.?\b",
            r"\bb\.?tech\b",
            r"\bb\.?a\.?\b",
            r"\bbachelor of science\b",
            r"\bbachelor of engineering\b",
            r"\bbachelor of technology\b",
        ),
    }

    YEAR_PATTERN = re.compile(
        r"""
        (?:
            \b(?:at\s+least|minimum\s+of|minimum|more\s+than|over)\s*
        )?
        (\d+(?:\.\d+)?)
        \s*
        (?:\+|plus)?
        (?:
            \s*[-–]\s*
            (\d+(?:\.\d+)?)
        )?
        \s*
        years?
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    MONTH_PATTERN = re.compile(
        r"""
        (\d+(?:\.\d+)?)
        \s*
        months?
        \b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    def analyze(
        self,
        title: str,
        description: str | None,
        location: str | None = None,
        employment_type: str | None = None,
    ) -> JobAnalysis:
        clean_title = self._clean_text(title)
        clean_description = self._clean_text(description)

        sections = self.extract_sections(clean_description)

        technologies = self._extract_skills(
            f"{clean_title}\n{clean_description}"
        )

        required_skills = self._extract_required_skills(
            clean_description,
            sections,
        )

        preferred_skills = self._extract_preferred_skills(
            clean_description,
            sections,
        )

        # A requirement detected in a preferred section remains
        # preferred. Required section evidence takes precedence.
        preferred_skills = [
            skill
            for skill in preferred_skills
            if skill not in required_skills
        ]

        required_years_min = self._extract_required_years(
            clean_description,
            sections,
        )

        preferred_years_min = self._extract_preferred_years(
            clean_description,
            sections,
        )

        required_education = self._extract_education(
            self._combine_sections(
                sections,
                self.REQUIRED_SECTION_NAMES,
            )
        )

        preferred_education = self._extract_education(
            self._combine_sections(
                sections,
                self.PREFERRED_SECTION_NAMES,
            )
        )

        title_degree = self._extract_education(clean_title)

        if "phd" in title_degree and "phd" not in required_education:
            required_education.append("phd")

        preferred_education = [
            degree
            for degree in preferred_education
            if degree not in required_education
        ]

        responsibilities = self._extract_responsibilities(
            sections,
            clean_description,
        )

        location_requirements = self._extract_location_requirements(
            location,
            clean_description,
        )

        resolved_employment_type = self._infer_employment_type(
            employment_type,
            clean_title,
            clean_description,
        )

        hard_constraints = self._extract_hard_constraints(
            clean_title,
            clean_description,
            required_education,
            resolved_employment_type,
        )

        confidence = self._calculate_confidence(
            sections=sections,
            required_skills=required_skills,
            required_years_min=required_years_min,
            required_education=required_education,
        )

        return JobAnalysis(
            title=clean_title,
            sections=sections,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            technologies=technologies,
            required_years_min=required_years_min,
            preferred_years_min=preferred_years_min,
            required_education=required_education,
            preferred_education=preferred_education,
            responsibilities=responsibilities,
            location_requirements=location_requirements,
            employment_type=resolved_employment_type,
            hard_constraints=hard_constraints,
            confidence=confidence,
        )

    def analyze_job(self, job: Any) -> JobAnalysis:
        return self.analyze(
            title=getattr(job, "title", "") or "",
            description=getattr(job, "description", "") or "",
            location=getattr(job, "location", None),
            employment_type=getattr(job, "employment_type", None),
        )

    def extract_sections(self, description: str) -> dict[str, str]:
        if not description:
            return {
                "about_job": "",
                "minimum_qualifications": "",
                "preferred_qualifications": "",
                "responsibilities": "",
                "other": "",
            }

        sections: dict[str, list[str]] = {
            "about_job": [],
            "minimum_qualifications": [],
            "preferred_qualifications": [],
            "responsibilities": [],
            "other": [],
        }

        current_section = "other"
        recognized_heading_count = 0

        for raw_line in description.splitlines():
            line = self._clean_text(raw_line)

            if not line:
                continue

            heading = self._canonical_heading(line)

            if heading is not None:
                current_section = heading
                recognized_heading_count += 1
                continue

            sections[current_section].append(line)

        result = {
            name: "\n".join(lines).strip()
            for name, lines in sections.items()
        }

        if recognized_heading_count == 0:
            inline_result = self._extract_inline_sections(description)

            if inline_result is not None:
                result = inline_result

        return result

    def _extract_inline_sections(
        self,
        description: str,
    ) -> dict[str, str] | None:
        flat = self._flatten_text(description)

        if not flat:
            return None

        heading_to_section = {
            "about the job": "about_job",
            "minimum qualifications": "minimum_qualifications",
            "basic qualifications": "minimum_qualifications",
            "required qualifications": "minimum_qualifications",
            "preferred qualifications": "preferred_qualifications",
            "desired qualifications": "preferred_qualifications",
            "nice to have": "preferred_qualifications",
            "responsibilities": "responsibilities",
            "key responsibilities": "responsibilities",
        }

        alternatives = sorted(
            heading_to_section.keys(),
            key=len,
            reverse=True,
        )

        heading_regex = re.compile(
            r"\b("
            + "|".join(re.escape(item) for item in alternatives)
            + r")\b",
            re.IGNORECASE,
        )

        matches = list(heading_regex.finditer(flat))

        if len(matches) < 1:
            return None

        result = {
            "about_job": "",
            "minimum_qualifications": "",
            "preferred_qualifications": "",
            "responsibilities": "",
            "other": "",
        }

        prefix = flat[: matches[0].start()].strip()

        if prefix:
            result["other"] = prefix

        for index, match in enumerate(matches):
            heading = match.group(1).lower()
            section_name = heading_to_section.get(heading)

            if section_name is None:
                continue

            start = match.end()

            if index + 1 < len(matches):
                end = matches[index + 1].start()
            else:
                end = len(flat)

            content = flat[start:end].strip()

            if content:
                if result[section_name]:
                    result[section_name] += "\n" + content
                else:
                    result[section_name] = content

        if not any(
            result[name]
            for name in (
                "about_job",
                "minimum_qualifications",
                "preferred_qualifications",
                "responsibilities",
            )
        ):
            return None

        return result

    def _canonical_heading(self, line: str) -> str | None:
        cleaned = line.strip()

        cleaned = re.sub(
            r"^[\-\*\u2022\u25AA\u25E6\d\.\)\(:]+\s*",
            "",
            cleaned,
        )

        cleaned = cleaned.rstrip(":").strip().lower()

        for section_name, aliases in self.SECTION_ALIASES.items():
            if cleaned in aliases:
                return section_name

        return None

    def _extract_required_skills(
        self,
        description: str,
        sections: dict[str, str],
    ) -> list[str]:
        found: set[str] = set()

        required_section = self._combine_sections(
            sections,
            self.REQUIRED_SECTION_NAMES,
        )

        if required_section:
            found.update(
                self._extract_skills(required_section)
            )

        # Do not scan preferred qualifications as required.
        scan_text = self._remove_section_text(
            description,
            sections.get("preferred_qualifications", ""),
        )

        for sentence in self._split_sentences(scan_text):
            if self._is_required_context(sentence):
                found.update(
                    self._extract_skills(sentence)
                )

        return self._ordered_skills(found)

    def _extract_preferred_skills(
        self,
        description: str,
        sections: dict[str, str],
    ) -> list[str]:
        found: set[str] = set()

        preferred_section = self._combine_sections(
            sections,
            self.PREFERRED_SECTION_NAMES,
        )

        if preferred_section:
            found.update(
                self._extract_skills(preferred_section)
            )

        for sentence in self._split_sentences(description):
            if self._contains_any_cue(
                sentence,
                self.PREFERRED_CUES,
            ):
                found.update(
                    self._extract_skills(sentence)
                )

        return self._ordered_skills(found)

    def _is_required_context(self, sentence: str) -> bool:
        lower = sentence.lower()

        if self._contains_any_cue(
            sentence,
            self.REQUIRED_CUES,
        ):
            return True

        # "3+ years of experience building/using/developing..."
        # is strong evidence that the technologies in that sentence
        # are part of the required experience.
        if re.search(
            r"\byears?\s+of\s+experience\b",
            lower,
            re.IGNORECASE,
        ):
            return True

        # Explicit experience-duration formulations.
        if re.search(
            r"\bexperience\s+(?:building|developing|designing|using|"
            r"working\s+with|in)\b",
            lower,
            re.IGNORECASE,
        ):
            return True

        return False

    def _extract_skills(self, text: str) -> list[str]:
        if not text:
            return []

        found: list[str] = []

        for canonical_name, patterns in self.SKILL_PATTERNS.items():
            if any(
                re.search(pattern, text, re.IGNORECASE)
                for pattern in patterns
            ):
                found.append(canonical_name)

        return self._ordered_skills(found)

    def _ordered_skills(
        self,
        skills: Iterable[str],
    ) -> list[str]:
        skills_set = set(skills)

        return [
            skill
            for skill in self.SKILL_PATTERNS
            if skill in skills_set
        ]

    def _extract_required_years(
        self,
        description: str,
        sections: dict[str, str],
    ) -> float | None:
        required_section = self._combine_sections(
            sections,
            self.REQUIRED_SECTION_NAMES,
        )

        if required_section:
            values = self._extract_year_values(
                required_section
            )

            if values:
                return max(values)

        # Exclude preferred qualifications from required-year scanning.
        scan_text = self._remove_section_text(
            description,
            sections.get("preferred_qualifications", ""),
        )

        explicit_values: list[float] = []

        for sentence in self._split_sentences(scan_text):
            if self._is_required_context(sentence):
                explicit_values.extend(
                    self._extract_year_values(sentence)
                )

        if explicit_values:
            return max(explicit_values)

        return None

    def _extract_preferred_years(
        self,
        description: str,
        sections: dict[str, str],
    ) -> float | None:
        preferred_section = self._combine_sections(
            sections,
            self.PREFERRED_SECTION_NAMES,
        )

        if preferred_section:
            values = self._extract_year_values(
                preferred_section
            )

            if values:
                return max(values)

        explicit_values: list[float] = []

        for sentence in self._split_sentences(description):
            if self._contains_any_cue(
                sentence,
                self.PREFERRED_CUES,
            ):
                explicit_values.extend(
                    self._extract_year_values(sentence)
                )

        if explicit_values:
            return max(explicit_values)

        return None

    def _extract_year_values(
        self,
        text: str,
    ) -> list[float]:
        if not text:
            return []

        values: list[float] = []

        for match in self.YEAR_PATTERN.finditer(text):
            first = float(match.group(1))
            second_text = match.group(2)

            if second_text is not None:
                second = float(second_text)
                values.append(min(first, second))
            else:
                values.append(first)

        for match in self.MONTH_PATTERN.finditer(text):
            months = float(match.group(1))

            if 0 < months <= 24:
                values.append(
                    round(months / 12.0, 2)
                )

        return values

    def _extract_education(
        self,
        text: str,
    ) -> list[str]:
        if not text:
            return []

        found: list[str] = []

        for level in (
            "bachelor",
            "master",
            "phd",
        ):
            patterns = self.EDUCATION_PATTERNS[level]

            if any(
                re.search(pattern, text, re.IGNORECASE)
                for pattern in patterns
            ):
                found.append(level)

        return found

    def _extract_responsibilities(
        self,
        sections: dict[str, str],
        description: str,
    ) -> list[str]:
        responsibility_text = sections.get(
            "responsibilities",
            "",
        ).strip()

        if responsibility_text:
            bullets = self._extract_bullets(
                responsibility_text
            )

            if bullets:
                return self._dedupe_preserve_order(
                    bullets[:20]
                )

            sentences = self._split_sentences(
                responsibility_text
            )

            if sentences:
                return self._dedupe_preserve_order(
                    sentences[:20]
                )

        about_text = sections.get(
            "about_job",
            "",
        ).strip()

        if about_text:
            return self._dedupe_preserve_order(
                self._split_sentences(about_text)[:10]
            )

        return self._dedupe_preserve_order(
            self._split_sentences(description)[:10]
        )

    def _extract_bullets(
        self,
        text: str,
    ) -> list[str]:
        result: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()

            match = re.match(
                r"^(?:[-*•▪◦]|\d+[.)])\s+(.*)$",
                line,
            )

            if match:
                content = self._clean_text(
                    match.group(1)
                )

                if content:
                    result.append(content)

        return result

    def _extract_location_requirements(
        self,
        location: str | None,
        description: str,
    ) -> list[str]:
        values: list[str] = []

        if location:
            for item in re.split(
                r"[;|]+",
                str(location),
            ):
                cleaned = self._clean_text(item)

                if cleaned:
                    values.append(cleaned)

        arrangement_patterns = (
            ("remote", r"\bremote\b"),
            ("hybrid", r"\bhybrid\b"),
            ("on-site", r"\bon[- ]site\b"),
            ("onsite", r"\bonsite\b"),
        )

        for label, pattern in arrangement_patterns:
            if re.search(
                pattern,
                description,
                re.IGNORECASE,
            ):
                values.append(label)

        return self._dedupe_preserve_order(values)

    def _infer_employment_type(
        self,
        employment_type: str | None,
        title: str,
        description: str,
    ) -> str | None:
        if employment_type:
            return self._clean_text(
                str(employment_type)
            )

        combined = (
            f"{title}\n{description}"
        )

        if re.search(
            r"\bintern(?:ship)?\b",
            combined,
            re.IGNORECASE,
        ):
            return "internship"

        if re.search(
            r"\bfull[- ]time\b",
            combined,
            re.IGNORECASE,
        ):
            return "full-time"

        if re.search(
            r"\bpart[- ]time\b",
            combined,
            re.IGNORECASE,
        ):
            return "part-time"

        if re.search(
            r"\bcontract(?:or)?\b",
            combined,
            re.IGNORECASE,
        ):
            return "contract"

        return None

    def _extract_hard_constraints(
        self,
        title: str,
        description: str,
        required_education: list[str],
        employment_type: str | None,
    ) -> list[str]:
        constraints: list[str] = []

        if "phd" in required_education:
            constraints.append(
                "PhD/doctorate requirement"
            )

        if re.search(
            r"\bsecurity clearance\b",
            description,
            re.IGNORECASE,
        ):
            if re.search(
                r"\b(?:required|must|needs?|needed)\b.{0,50}"
                r"\bsecurity clearance\b",
                description,
                re.IGNORECASE | re.DOTALL,
            ):
                constraints.append(
                    "Security clearance requirement"
                )

        citizenship_pattern = re.compile(
            r"""
            \b(
                citizenship|
                citizen|
                work authorization|
                authorized to work|
                legally authorized to work
            )\b
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        if citizenship_pattern.search(description):
            constraints.append(
                "Citizenship/work-authorization requirement stated"
            )

        if employment_type == "internship":
            constraints.append("Internship role")

        if re.search(
            r"\bph\.?d\.?\b|\bdoctorate\b",
            title,
            re.IGNORECASE,
        ):
            if "PhD/doctorate requirement" not in constraints:
                constraints.append(
                    "PhD/doctorate requirement"
                )

        return self._dedupe_preserve_order(
            constraints
        )

    def _calculate_confidence(
        self,
        sections: dict[str, str],
        required_skills: list[str],
        required_years_min: float | None,
        required_education: list[str],
    ) -> str:
        recognized_sections = sum(
            1
            for name in (
                "about_job",
                "minimum_qualifications",
                "preferred_qualifications",
                "responsibilities",
            )
            if sections.get(name)
        )

        evidence_points = recognized_sections

        if required_skills:
            evidence_points += 1

        if required_years_min is not None:
            evidence_points += 1

        if required_education:
            evidence_points += 1

        if evidence_points >= 5:
            return "high"

        if evidence_points >= 3:
            return "medium"

        return "low"

    def _combine_sections(
        self,
        sections: dict[str, str],
        names: Iterable[str],
    ) -> str:
        values = [
            sections.get(name, "").strip()
            for name in names
            if sections.get(name, "").strip()
        ]

        return "\n".join(values)

    def _remove_section_text(
        self,
        description: str,
        section_text: str,
    ) -> str:
        if not section_text:
            return description

        if section_text in description:
            return description.replace(
                section_text,
                "",
            )

        # Fallback for whitespace-normalized comparisons.
        flat_description = self._flatten_text(
            description
        )

        flat_section = self._flatten_text(
            section_text
        )

        if flat_section and flat_section in flat_description:
            return flat_description.replace(
                flat_section,
                "",
            )

        return description

    def _split_sentences(
        self,
        text: str,
    ) -> list[str]:
        if not text:
            return []

        normalized = self._flatten_text(text)

        if not normalized:
            return []

        parts = re.split(
            r"(?<=[.!?])\s+(?=[A-Z0-9])",
            normalized,
        )

        result: list[str] = []

        for part in parts:
            cleaned = self._clean_text(part)

            if cleaned:
                result.append(cleaned)

        return result

    def _contains_any_cue(
        self,
        text: str,
        cues: Iterable[str],
    ) -> bool:
        lower = text.lower()

        return any(
            cue.lower() in lower
            for cue in cues
        )

    def _flatten_text(
        self,
        text: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            self._clean_text(text),
        ).strip()

    def _clean_text(
        self,
        value: str | None,
    ) -> str:
        if value is None:
            return ""

        text = str(value).replace(
            "\xa0",
            " ",
        )

        text = text.replace(
            "\r",
            "\n",
        )

        text = text.replace(
            "\u2022",
            "•",
        )

        text = text.replace(
            "\u25AA",
            "▪",
        )

        text = text.replace(
            "\u25E6",
            "◦",
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        return text.strip()

    def _dedupe_preserve_order(
        self,
        values: Iterable[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            cleaned = self._clean_text(value)

            if not cleaned:
                continue

            key = cleaned.casefold()

            if key in seen:
                continue

            seen.add(key)
            result.append(cleaned)

        return result


def analyze_job_description(
    title: str,
    description: str,
    location: str | None = None,
    employment_type: str | None = None,
) -> JobAnalysis:
    analyzer = JobDescriptionAnalyzer()

    return analyzer.analyze(
        title=title,
        description=description,
        location=location,
        employment_type=employment_type,
    )


__all__ = [
    "JobAnalysis",
    "JobDescriptionAnalyzer",
    "analyze_job_description",
]