# Deal Refresh Scheduler

Independent, non-fork GitHub Actions timer controller for
[wlzh/let-deals-radar](https://github.com/wlzh/let-deals-radar).
The original fork, its code, affiliate mappings and Cloudflare Pages project remain in place.

The workflow calls the original project's reusable pipeline. It checks out that
project's latest `main`, runs tests, fetches deals, audits links, commits only generated
files back to the original repository and verifies its public deployment.
Artifacts and scheduled run logs belong to this scheduler repository.

## Credentials

`LDR_REPO_PUSH_KEY` is an Actions secret containing a dedicated write-enabled SSH
deploy key for `wlzh/let-deals-radar` only. No personal GitHub token is stored here.
The original repository's Settings / Deploy keys page can revoke it independently.
Never commit the private key or print it in workflow logs.

## Configuration

Repository variables are resolved in the caller (this repository), not the called
repository. `LDR_VERIFY_LIVE=true` enables the public deployment check and
`LDR_SITE_URL=https://vps.869hr.uk` selects the production site. Custom `LDR_SITE_*`
or `LDR_AFFILIATES` overrides must be configured here too. Affiliate defaults remain
in the original project's source code, so future source updates require no copy.

## Server-Side Timer Chain

Native cron did not create runs during the observed acceptance window, including
in this non-fork repository. The primary timer therefore does not depend on cron.
GitHub environment `refresh-delay-5m` has a 5-minute wait timer; environment
`refresh-delay-24h` has a 1440-minute wait timer. Waiting does not occupy a runner
or count as billable wait time. Runner allocation can still add delay.

Starting `mode=probe` creates a visible waiting run. After five minutes it runs the
original project's refresh, then dispatches one `mode=auto` continuation. Each auto
run waits 24 hours before refreshing and queuing its successor. This is a rolling
daily interval after completion, not a promise to execute at 09:23 each day.
Only the controller job has `actions: write` on this scheduler repository; it uses
the ephemeral `GITHUB_TOKEN`, not a stored personal token.

The controller confirms the successor's actual run ID before recording
`.next-run.json`. Existing continuations or other active chains prevent duplicate
dispatches. A lost POST response is observed rather than blindly retried. The
timer checks elapsed server time before refreshing: deleting or shortening an
environment timer fails closed instead of creating a rapid self-dispatch loop.
Refresh failure preserves the original site's prior data and still queues the
next daily retry. Explicit cancellation does not rearm the chain. Timer/controller
failure stops it and requires operator attention via the failed Actions run.

After verified refresh success, `last-success.json` records the source revision and
run URL. These audit commits provide activity in this repository, not just in the
source project. `.next-run.json` is continuation state, not evidence that the next
refresh has already succeeded.

## Start, Stop And Restart

```bash
# Start only when no existing chain is waiting or running.
gh workflow enable refresh.yml -R wlzh/let-deals-radar-scheduler
gh workflow run refresh.yml -R wlzh/let-deals-radar-scheduler -f mode=probe
gh run list -R wlzh/let-deals-radar-scheduler --workflow refresh.yml
```

To stop, disable `refresh.yml` and cancel all its nonterminal runs. Disabling a
workflow alone does not cancel a waiting run. To restart, first confirm the old
chain is stopped, enable the workflow and dispatch a fresh `probe`. Do not rerun
an old completed run to restart the chain: continuation IDs are idempotent.

This design intentionally keeps one waiting run visible. Do not rename or delete
the two timer environments; GitHub's wait timer configuration is part of runtime
configuration, not merely a YAML comment. Unit tests: `python3 -m unittest discover -s tests -v`.

References: [environment wait timers](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
and [GITHUB_TOKEN dispatch exceptions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

The original fork also accepts source `push` and manual runs. Concurrent source
updates cause stale builds to fail without overwriting newer code; start a fresh
run rather than force-pushing. Generated-data commits do not create refresh loops.
