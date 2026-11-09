from app.api.main import _is_target_software_role
from app.services.target_role_policy import is_target_software_role


def main() -> None:
    cloud_description = (
        "You should apply if you have: 2–6 years of experience in information security. "
        "Strong programming skills in Python, Go, or Bash; experience building and "
        "automating custom security tools and cloud security platforms."
    )
    threat_description = (
        "You should apply if you have: 2 to 6 years of experience in information security "
        "with a strong focus on threat detection and response. Proficiency in Python, Go, "
        "or Bash; ability to build high-fidelity detection pipelines and automate response."
    )

    for title, description in [
        ("Cloud Security Engineer", cloud_description),
        ("Threat Detection Engineer", threat_description),
    ]:
        eligible, reason = is_target_software_role(title, description, maximum_required_years=2)
        assert eligible, f"{title} should pass the technical security title policy; got {reason}"
        assert _is_target_software_role(title), f"API title filter does not match {title}"

    for title in ("Security Analyst", "SOC Analyst", "Security Operations Analyst"):
        eligible, _ = is_target_software_role(title, "2 years of experience")
        assert not eligible, f"Generic security analyst title must remain excluded: {title}"
        assert not _is_target_software_role(title), f"API feed must exclude generic security analyst: {title}"

    # Regression guard: a malformed regex alternation once made the API title
    # filter match every title that was not explicitly blocked.
    for title in ("Head Chef", "Warehouse Operator", "Senior Commissions Analyst"):
        assert not _is_target_software_role(title), f"API feed must not admit unrelated title: {title}"

    print("PASS - Cloud Security Engineer is included")
    print("PASS - Threat Detection Engineer is included")
    print("PASS - Generic security analyst/SOC titles remain excluded")


if __name__ == "__main__":
    main()
