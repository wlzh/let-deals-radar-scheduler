from datetime import datetime, timezone
import unittest

from tools.controller import check_delay, queue_next, next_slot, schedule_inputs, wait_for_slot


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
        self.assertEqual(calls[1][1]["inputs"]["mode"], "auto")
        self.assertEqual(calls[1][1]["inputs"]["parent_run_id"], "1")
        self.assertIn("scheduled_at", calls[1][1]["inputs"])

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

    def test_next_beijing_slots_and_day_rollover(self):
        for source, target in [
            ("2026-10-29T03:30:00+00:00", "2026-10-29T21:00:00+00:00"),
            ("2026-10-29T09:00:00+00:00", "2026-10-29T21:00:00+00:00"),
            ("2026-10-29T21:01:00+00:00", "2026-10-30T21:00:00+00:00"),
            ("2026-10-29T21:00:00+00:00", "2026-10-30T21:00:00+00:00"),
        ]:
            self.assertEqual(next_slot(datetime.fromisoformat(source)).isoformat(), target)

    def test_hour_bucket_leaves_less_than_one_hour(self):
        inputs = schedule_inputs(datetime(2026, 10, 29, 3, 30, tzinfo=timezone.utc))
        self.assertEqual(inputs, {"scheduled_at": "2026-10-29T21:00:00+00:00", "timer_hours": "17"})

    def test_wait_reaches_slot(self):
        sleeps = []
        wait_for_slot("2026-10-29T03:30:00Z", "2026-10-29T21:00:00Z", 17,
                      datetime(2026, 10, 29, 20, 30, tzinfo=timezone.utc), sleeps.append)
        self.assertEqual(sleeps, [1800])

    def test_early_release_and_wrong_slot_fail_closed(self):
        with self.assertRaises(RuntimeError):
            wait_for_slot("2026-10-29T03:30:00Z", "2026-10-29T21:00:00Z", 17,
                          datetime(2026, 10, 29, 20, 29, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            wait_for_slot("2026-10-29T03:30:00Z", "2026-10-29T10:00:00Z", 5)


if __name__ == "__main__":
    unittest.main()
