# JMU Countdown

Unofficial fan countdown to the release of the 2027 American Conference football schedule, JMU's first as a member.

Two parts:

- **Live page** (`docs/`): a clock counting down days, hours, minutes and seconds to the hundredth, hosted free on GitHub Pages at https://bastein-collab.github.io/jmu-countdown/. It also links to the official sources: the American Conference, JMU Football, JMU Sports and JMU's university accounts. Those links are in `docs/index.html` under "Official sources".
- **Bot** (`bot/countdown.py`): every morning at 6:00 a.m. ET it renders a purple-and-gold countdown graphic and posts it to Bluesky and X. A GitLab scheduled pipeline runs it (`ci/gitlab-ci.yml`), because GitHub Actions is disabled on this account.

All settings live in one file: **`docs/config.json`**. The page and the bot both read it. This GitHub repo is the single source of truth: the GitLab run clones it fresh every morning, so any change committed here is what posts the next day.

## Projected date

Thu., Feb. 25, 2027, early afternoon ET (the clock targets 2:00 p.m. ET). The basis is the league's last two releases: Fri., Feb. 28, 2025 and Thu., Feb. 26, 2026, both early afternoon. JMU's addition makes 2027 a 15-team football schedule, so a later date is possible.

**When the American announces the real date**, edit `docs/config.json` on GitHub (pencil icon) and change, in the first countdown:

- `target` to the announced date and time, e.g. `"2027-02-24T13:00:00-05:00"`
- `date_label` to match, e.g. `"Wed., Feb. 24, 2027"`
- `time_label_official` to the announced time, e.g. `"1:00 p.m. ET"`
- `status` from `"projected"` to `"official"`

Commit. The page updates within a minute, and the next morning's post says "Set" in place of "Projected."

## How the daily post runs

- **Where:** GitLab project for @CountdownJMU. Its only file is `.gitlab-ci.yml`, a copy of `ci/gitlab-ci.yml` in this repo.
- **When:** GitLab **Build → Pipeline schedules**, cron `0 6 * * *`, time zone America/New_York. GitLab handles daylight saving time.
- **Keys:** GitLab **Settings → CI/CD → Variables**, all masked: `BSKY_HANDLE`, `BSKY_APP_PASSWORD`, `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`. A platform without keys is skipped.
- **If a run fails:** GitLab emails the schedule's owner. Fix the cause, then **Build → Pipelines → Run pipeline** with `MODE` = `post`. The rerun skips any platform that already posted that day.
- **Test without posting:** **Run pipeline** with `MODE` = `preview`. The graphic is attached to the job as a download.

### Double-post guard

Each run starts from a fresh copy, so it checks the platforms themselves:

- **Bluesky:** skips if the account already has a post that day starting with that day's countdown line.
- **X:** X refuses a post whose text matches an earlier one, and the bot treats that refusal as "already posted."

Set `FORCE` to `true` on a manual run to post anyway.

### Posts

- **X:** countdown text, the live-clock link (`Live clock: bastein-collab.github.io/jmu-countdown`), #GoDukes, and the graphic with alt text.
- **Bluesky:** the same, except the words "Watch the live clock" carry the link, so no web address shows.

### Link preview

`docs/latest.png` is the picture that X, Bluesky and texts show when someone shares the page link. It has no day count, so it never goes stale. The bot writes each day's graphic to `out/today.png` and leaves `docs/latest.png` alone.

### GitHub Actions (backup only)

`.github/workflows/countdown.yml` has no schedule, so it can never double-post if GitHub turns Actions back on. It can still be run by hand from the Actions tab. Its secrets are set in **Settings → Secrets and variables → Actions**.

## One-time setup (done)

1. **GitHub Pages:** Settings → Pages → Deploy from a branch, `main`, `/docs`.
2. **Bluesky:** account @countdownjmu.bsky.social, email confirmed, app password in the GitLab variables.
3. **X:** account @CountdownJMU, labeled "Fan account", name starting with "Fan Account". Developer app "CountdownJMU Daily Post" with Read and write. Keys in the GitLab variables. Spend cap $10 per billing cycle, auto recharge off.
4. **GitLab:** project with `.gitlab-ci.yml`, the six variables, and the 6:00 a.m. ET schedule.

## Costs

- GitHub Pages: free.
- GitLab: free tier, 400 compute minutes a month. Each run takes about 1.5 minutes.
- Bluesky: free.
- X: about $0.20 per post with the link, plus about $0.005 for alt text. Roughly $6.40 a month. The X spend cap is $10 per billing cycle. Top up credits in the X developer console before the balance runs out.

## Sponsor line

To credit a sponsor on the page and in every post, set in `docs/config.json`:

```json
"sponsor": { "name": "Business Name", "url": "https://example.com", "disclosure": "#ad" }
```

Posts then end with "Presented by Business Name #ad". Keep the disclosure: paid posts must be labeled.

## After schedule day

The second countdown in `docs/config.json` (season kickoff) is off. Once the 2027 schedule confirms JMU's opener, update its date and time and set `"enabled": true`. The bot moves to it automatically the day after the schedule release.

## Run locally

```bash
pip install -r requirements.txt
python bot/countdown.py --dry-run                    # today
python bot/countdown.py --dry-run --date 2027-02-24  # any day
```

## Not affiliated

Unofficial fan project. Not affiliated with or endorsed by James Madison University or the American Conference. No university or conference logos are used.
