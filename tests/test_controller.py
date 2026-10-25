from datetime import datetime, timezone
import unittest

from tools.controller import check_delay, queue_next


def run(run_id, title="", status="queued"):
    return {"id": run_id, "display_title": title, "status": status, "html_url": f"https://github.com/example/runs/{run_id}"}


class ControllerTests(unittest.TestCase):
    def test_five_minute_delay(self):
        self.assertEqual(check_delay("2026-10-25T00:00:00Z", "probe", datetime(2026, 10, 25, 0, 5, tzinfo=timezone.utc)), 300)

    def test_daily_delay(self):
        self.assertEqual(check_delay("2026-10-25T00:00:00Z", "auto", datetime(2026, 10, 26, tzinfo=timezone.utc)), 86400)

    def test_deleted_or_shortened_environment_fails_closed(self):
        for mode in ("probe", "auto"):
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                check_delay("2026-10-25T00:00:00Z", mode, datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc))

    def test_invalid_mode_fails_closed(self):
        with self.assertRaises(KeyError):
            check_delay("2026-10-25T00:00:00Z", "unknown")

    def test_creates_once_and_confirms_run(self):
        calls = []
        next_run = run(2, "Daily refresh after 1")

        def api(method, path, payload=None):
            calls.append((method, payload))
            return {"workflow_runs": [] if len(calls) == 1 else [next_run]}

        self.assertEqual(queue_next(api, "example/repo", 1, sleep=lambda _: None), next_run)
        self.assertEqual([c[0] for c in calls].count("POST"), 1)
        self.assertEqual(calls[1][1]["inputs"], {"mode": "auto", "parent_run_id": "1"})

    def test_existing_link_prevents_duplicate_even_if_completed(self):
        next_run = run(2, "Daily refresh after 1", "completed")

        def api(method, path, payload=None):
            self.assertEqual(method, "GET")
            return {"workflow_runs": [next_run]}

        self.assertEqual(queue_next(api, "example/repo", 1), next_run)

    def test_other_active_chain_prevents_duplicate(self):
        next_run = run(3, "5m probe after operator", "waiting")

        def api(method, path, payload=None):
            self.assertEqual(method, "GET")
            return {"workflow_runs": [run(1, status="in_progress"), next_run]}

        self.assertEqual(queue_next(api, "example/repo", 1), next_run)

    def test_ambiguous_post_is_observed_not_retried(self):
        calls = []
        next_run = run(2, "Daily refresh after 1")

        def api(method, path, payload=None):
            calls.append(method)
            if method == "POST":
                raise TimeoutError("response lost")
            return {"workflow_runs": [] if len(calls) == 1 else [next_run]}

        self.assertEqual(queue_next(api, "example/repo", 1, sleep=lambda _: None), next_run)
        self.assertEqual(calls.count("POST"), 1)

    def test_unconfirmed_dispatch_does_not_retry_post(self):
        calls = []

        def api(method, path, payload=None):
            calls.append(method)
            return {"workflow_runs": []}

        with self.assertRaises(RuntimeError):
            queue_next(api, "example/repo", 1, sleep=lambda _: None)
        self.assertEqual(calls.count("POST"), 1)


if __name__ == "__main__":
    unittest.main()
