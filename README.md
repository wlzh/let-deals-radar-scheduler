# Deal Refresh Scheduler

Independent, non-fork GitHub Actions scheduler for
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

The temporary five-minute cron is for acceptance only; restore daily UTC 01:23
(09:23 Asia/Shanghai) after a real `schedule` event completes successfully.
Manual runs prove the pipeline but not the timer. GitHub scheduling is best-effort,
so timing is not guaranteed to the minute. After verified success, the scheduler
commits `last-success.json` here with the source revision and run URL. This provides
an audit trail and repository activity; source-project commits alone do not keep
this separate repository active. If runs stop, check the workflow's enabled state
and GitHub's public-repository inactivity policy.

The original fork also accepts source `push` and manual runs. Concurrent source
updates cause stale builds to fail without overwriting newer code; start a fresh
run rather than force-pushing. Generated-data commits do not create refresh loops.
