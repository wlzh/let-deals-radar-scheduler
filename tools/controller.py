"""Auditable, bounded Actions continuation without cron or a personal token."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}
DELAYS = {"probe": 5, "auto": 1440}


def check_delay(created_at, mode, now=None):
    expected = DELAYS[mode] * 60
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    elapsed = ((now or datetime.now(timezone.utc)) - created).total_seconds()
    if elapsed < expected:
        raise RuntimeError("Timer released early; refusing refresh and continuation")
    return elapsed


def github_api(token):
    if not token:
        raise ValueError("GH_TOKEN is required")

    def request(method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request("https://api.github.com" + path, data=data, method=method, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        for attempt in range(2 if method == "GET" else 1):
            try:
                with urlopen(req, timeout=10) as response:
                    body = response.read()
                return json.loads(body) if body else None
            except HTTPError as exc:
                if method != "GET" or exc.code < 500 or attempt:
                    raise
            except (URLError, TimeoutError, OSError):
                if method != "GET" or attempt:
                    raise
            time.sleep(2)

    return request


def queue_next(api, repo, current_id, sleep=time.sleep):
    path = f"/repos/{repo}/actions/workflows/refresh.yml"
    title = f"Daily refresh after {current_id}"

    def existing():
        runs = api("GET", path + "/runs?per_page=100&event=workflow_dispatch")["workflow_runs"]
        linked = [r for r in runs if r["id"] != current_id and r.get("display_title") == title]
        if linked:
            return max(linked, key=lambda r: r["id"])
        active = [r for r in runs if r["id"] != current_id and r["status"] in ACTIVE]
        return max(active, key=lambda r: r["id"]) if active else None

    run = existing()
    if run:
        return run
    error = None
    try:
        api("POST", path + "/dispatches", {
            "ref": "main", "inputs": {"mode": "auto", "parent_run_id": str(current_id)},
        })
    except HTTPError as exc:
        if exc.code < 500:
            raise
        error = exc
    except (URLError, TimeoutError, OSError) as exc:
        error = exc
    # Never blindly retry a POST after an ambiguous response.
    for _ in range(10):
        sleep(2)
        run = existing()
        if run:
            return run
    raise RuntimeError("Cannot confirm next run; inspect Actions before starting a new chain") from error


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository")
    current_id = int(os.environ["GITHUB_RUN_ID"])
    api = github_api(os.environ.get("GH_TOKEN"))
    if sys.argv[1] == "check-delay":
        run = api("GET", f"/repos/{repo}/actions/runs/{current_id}")
        elapsed = check_delay(run["created_at"], os.environ["TIMER_MODE"])
        print(f"Minimum delay verified: {elapsed:.0f} seconds")
    elif sys.argv[1] == "queue-next":
        run = queue_next(api, repo, current_id)
        record = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "parent_run_id": current_id,
            "next_run_id": run["id"],
            "next_run_url": run["html_url"],
            "observed_status": run["status"],
            "delay_minutes": 1440,
        }
        Path(".next-run.json").write_text(json.dumps(record, indent=2) + "\n")
        print("Confirmed continuation: " + run["html_url"])
    else:
        raise ValueError("Expected check-delay or queue-next")


if __name__ == "__main__":
    main()
