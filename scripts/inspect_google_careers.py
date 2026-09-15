import re

import requests


URL = "https://www.google.com/about/careers/applications/jobs/results/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    )
}


def main() -> None:
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    html = response.text

    print(f"HTML length: {len(html):,}")

    patterns = [
        r'"jobId"',
        r'"title"',
        r'"locations"',
        r'"description"',
        r'"Software Engineer"',
        r'job-results',
    ]

    print("\nPattern counts:")

    for pattern in patterns:
        matches = re.findall(pattern, html, flags=re.IGNORECASE)
        print(f"{pattern:25} -> {len(matches)}")

    print("\nPossible job IDs:")

    job_ids = re.findall(
        r'"jobId"\s*:\s*"([^"]+)"',
        html,
    )

    for job_id in job_ids[:10]:
        print(job_id)


if __name__ == "__main__":
    main()