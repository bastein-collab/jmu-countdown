# JMU Countdown

Unofficial fan countdown to the release of the 2027 American Conference football schedule, JMU's first as a member.

Two parts:

- **Live page** (`docs/`): a ticking clock hosted free on GitHub Pages at https://bastein-collab.github.io/jmu-countdown/
- **Bot** (`bot/countdown.py`): every morning at 9:07 a.m. ET it renders a purple-and-gold countdown graphic and posts it to Bluesky and X. GitHub Actions runs it (`.github/workflows/countdown.yml`).

All settings live in one file: **`docs/config.json`**. The page and the bot both read it.

## Projected date

Thu., Feb. 25, 2027, early afternoon ET (the clock targets 2:00 p.m. ET). The basis is the league's last two releases: Fri., Feb. 28, 2025 and Thu., Feb. 26, 2026, both early afternoon. JMU's addition makes 2027 a 15-team football schedule, so a later date is possible.

**When the American announces the real date**, edit `docs/config.json` on GitHub (pencil icon) and change, in the first countdown:

- `target` to the announced date and time, e.g. `"2027-02-24T13:00:00-05:00"`
- `date_label` to match, e.g. `"Wed., Feb. 24, 2027"`
- `time_label_official` to the announced time, e.g. `"1:00 p.m. ET"`
- `status` from `"projected"` to `"official"`

Commit. The page updates within a minute, and the next morning's post says "Set" in place of "Projected."

## One-time setup

### 1. GitHub Pages
Repo **Settings → Pages → Build and deployment**: Source "Deploy from a branch", Branch `main`, folder `/docs`. Save. The page goes live at the address above in a minute or two.

### 2. Bluesky (free)
1. Create the bot account in the Bluesky app.
2. In that account: **Settings → Privacy and security → App passwords → Add App Password**. Copy it.
3. In this repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:
   - `BSKY_HANDLE`: the handle, e.g. `jmucountdown.bsky.social`
   - `BSKY_APP_PASSWORD`: the app password from step 2
4. Put the live page link in the Bluesky bio, and say it's an unofficial fan account.

### 3. X (pay per post)
1. Create the bot account on X. Say "unofficial fan account" in the name or bio, and put the live page link in the bio.
2. In the X Developer Console, sign in as the bot account, create an app, and set its user authentication permissions to **Read and write**.
3. Generate the app's **API Key and Secret**, then its **Access Token and Secret**. Generate the access token *after* setting Read and write, or it will be read-only.
4. Buy a small amount of credits and set a spending cap. One plain post a day costs about $0.015, so $5 covers the whole countdown with room to spare.
5. Add four repository secrets: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`.
6. If X shows an **Automation** option under the bot's account information, link it to your personal account so the bot carries X's "Automated" label.

A platform without secrets is skipped, so you can launch on Bluesky first and add X later.

### 4. Test
**Actions → Daily countdown post → Run workflow**:
- `mode: preview` renders the graphic and prints both posts without posting. Download the graphic from the run's summary page.
- `mode: post` posts for real. A second run the same day won't double-post unless you tick `force`.

After that it runs every morning on its own.

## Costs

- GitHub (Actions + Pages): free for a public repo.
- Bluesky: free.
- X: about $0.015 per post with no link. A post containing a link costs $0.20, which is why X posts leave the link out and the bio carries it.

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
