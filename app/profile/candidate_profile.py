from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CandidateProfile:
    """
    Structured representation of the candidate's resume.

    This profile contains only information supported by the
    current resume. It is intentionally deterministic so that
    later scoring can be audited.
    """

    education: Tuple[str, ...]
    degrees: Tuple[str, ...]
    technical_skills: Tuple[str, ...]
    programming_languages: Tuple[str, ...]
    frontend_skills: Tuple[str, ...]
    frameworks: Tuple[str, ...]
    tools: Tuple[str, ...]
    concepts: Tuple[str, ...]
    project_skills: Tuple[str, ...]
    internship_skills: Tuple[str, ...]
    certifications: Tuple[str, ...]
    target_role_families: Tuple[str, ...]
    target_seniority: Tuple[str, ...]
    target_locations: Tuple[str, ...]
    years_of_experience: float
    internship_experience: bool


CANDIDATE_PROFILE = CandidateProfile(
    education=(
        "BTech - Internet of Things (IoT)",
        "KL University",
    ),

    degrees=(
        "BTech",
    ),

    technical_skills=(
        "Java",
        "Python",
        "Data Structures and Algorithms",
        "Object Oriented Programming",
        "HTML",
        "CSS",
        "JavaScript",
        "Git",
        "GitHub",
        "React.js",
        "Tailwind CSS",
        "Next.js",
        "Chart.js",
        "Firebase",
        "Auth.js",
        "PyWhatKit",
        "NLP",
        "Machine Learning",
    ),

    programming_languages=(
        "Java",
        "Python",
        "JavaScript",
    ),

    frontend_skills=(
        "HTML",
        "CSS",
        "JavaScript",
        "React.js",
        "Tailwind CSS",
        "Next.js",
        "Chart.js",
    ),

    frameworks=(
        "React.js",
        "Next.js",
        "Tailwind CSS",
        "Auth.js",
    ),

    tools=(
        "Git",
        "GitHub",
        "Firebase",
        "Chart.js",
        "PyWhatKit",
    ),

    concepts=(
        "Data Structures and Algorithms",
        "Object Oriented Programming",
        "NLP",
        "Machine Learning",
        "Authentication",
        "Session Management",
        "CRUD",
    ),

    project_skills=(
        "React.js",
        "Next.js",
        "JavaScript",
        "Python",
        "Firebase",
        "Auth.js",
        "Chart.js",
        "NLP",
        "Machine Learning",
        "HTML",
        "CSS",
    ),

    internship_skills=(
        "HTML",
        "CSS",
        "JavaScript",
        "Frontend Development",
    ),

    certifications=(
        "AWS Cloud Practitioner",
        "Python - HackerRank",
        "Microsoft Azure Fundamentals (AZ900)",
        "React (Basic) - HackerRank",
        "Java - HackerRank",
        "Programming in Java - NPTEL",
    ),

    target_role_families=(
        "software_engineering",
        "frontend",
        "full_stack",
    ),

    target_seniority=(
        "entry",
        "mid",
    ),

    target_locations=(
        "Hyderabad, Telangana, India",
        "Bengaluru, Karnataka, India",
    ),

    years_of_experience=0.0,

    internship_experience=True,
)


def get_candidate_profile() -> CandidateProfile:
    """
    Return the application's candidate profile.
    """

    return CANDIDATE_PROFILE