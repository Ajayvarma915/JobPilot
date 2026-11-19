"""Runs the job update steps one after another and writes progress markers to stdout.

Started by the app's "Update jobs now" button (app/services/sync_runner.py) as its own process, so a
restart of the web server does not stop it. Usage: python -m scripts.run_job_update <steps.json>
where the file holds [[name, [python args...]], ...].
"""
from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as handle:
        steps = json.load(handle)
    for name, args in steps:
        print(f"=== STEP {name} ===", flush=True)
        code = subprocess.call([sys.executable, "-u", *args])
        print(f"=== STEP {name} EXIT {code} ===", flush=True)
    print("=== DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
