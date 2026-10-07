from __future__ import annotations

from app.profile.candidate_profile import (
    CandidateProfile,
    get_candidate_profile,
)


def validate_profile(
    profile: CandidateProfile,
) -> None:
    required_fields = {
        "education": profile.education,
        "degrees": profile.degrees,
        "technical_skills": profile.technical_skills,
        "programming_languages": profile.programming_languages,
        "frontend_skills": profile.frontend_skills,
        "frameworks": profile.frameworks,
        "tools": profile.tools,
        "concepts": profile.concepts,
        "project_skills": profile.project_skills,
        "internship_skills": profile.internship_skills,
        "certifications": profile.certifications,
        "target_role_families": profile.target_role_families,
        "target_seniority": profile.target_seniority,
        "target_locations": profile.target_locations,
    }

    for field_name, value in required_fields.items():
        if not value:
            raise AssertionError(
                f"Profile field '{field_name}' is empty."
            )

    if profile.years_of_experience < 0:
        raise AssertionError(
            "Years of experience cannot be negative."
        )

    if not isinstance(
        profile.internship_experience,
        bool,
    ):
        raise AssertionError(
            "internship_experience must be boolean."
        )


def main() -> None:
    profile = get_candidate_profile()

    print("========================================")
    print("Candidate Profile Test")
    print("========================================")

    validate_profile(profile)

    print(
        f"Education              : "
        f"{', '.join(profile.education)}"
    )

    print(
        f"Degrees                : "
        f"{', '.join(profile.degrees)}"
    )

    print(
        f"Programming Languages  : "
        f"{', '.join(profile.programming_languages)}"
    )

    print(
        f"Frontend Skills        : "
        f"{', '.join(profile.frontend_skills)}"
    )

    print(
        f"Frameworks             : "
        f"{', '.join(profile.frameworks)}"
    )

    print(
        f"Tools                  : "
        f"{', '.join(profile.tools)}"
    )

    print(
        f"Target Roles           : "
        f"{', '.join(profile.target_role_families)}"
    )

    print(
        f"Target Seniority       : "
        f"{', '.join(profile.target_seniority)}"
    )

    print(
        f"Target Locations       : "
        f"{', '.join(profile.target_locations)}"
    )

    print(
        f"Years of Experience    : "
        f"{profile.years_of_experience}"
    )

    print(
        f"Internship Experience  : "
        f"{profile.internship_experience}"
    )

    print(
        f"Technical Skills Count : "
        f"{len(profile.technical_skills)}"
    )

    print(
        f"Certifications Count   : "
        f"{len(profile.certifications)}"
    )

    print()
    print(
        "SUCCESS: Candidate profile "
        "is valid."
    )


if __name__ == "__main__":
    main()