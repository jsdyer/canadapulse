# Canada Pulse

[Use Canada Pulse](https://coolcode.ca/canadapulse/) to explore Wikipedia reading patterns without an account.

<!-- coolcode:guide -->
“Read from Canada” counts article views originating in Canada; “Canadian topics worldwide” follows a curated list globally. Country figures are privacy-protected upper bounds, not exact reader counts. Browse saved report dates by month, share a date link or export its results. Historical observations and the topic selection for each day are retained in the repository. Missing days remain gaps. A spike compares a complete earlier baseline; it does not explain why people are reading.
<!-- /coolcode:guide -->

## What works

- Date, language, topic and title filters; worldwide volume, ratio and absolute-increase sorting.
- A growing historical archive, month/date selection, shareable date links, sparklines and CSV export. The recent collection window defaults to fourteen country dates and 28-day topic baselines; archived dates do not roll off.
- Follow articles in browser storage, including custom lookups, and check their worldwide views through the selected reporting date.
- Arbitrary Wikipedia article title/language lookup directly against Wikimedia. No API key or Worker handler is required.
- Keyboard navigation, mobile layout and source links. Utility pages are filtered, with the remaining original source ranks retained.

The report date is the measured UTC date. `retrieved_at` is when the collector retrieved the data. Neither is a page-build date. Country values use Wikimedia's `views_ceil` field; a missing article is not zero. Worldwide series use the `user` agent class and measure views, not unique people. Canadian topics are editorially selected and are not a complete classification of all Canadian subjects.

## Sources and operation

Sources: [Wikimedia Analytics API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html), `top-per-country/CA/all-access/YYYY/MM/DD` and `per-article/{project}/all-access/user/{article}/daily/{start}/{end}`. Custom browser queries use the same per-article endpoint. Article pages belong to Wikipedia contributors; statistics are attributed to Wikimedia.

The **Browser tool · Check and publish** workflow checks sources daily at **16:23 UTC**, or when dispatched manually. Pushes and PRs build offline from checked-in `web/data/`. Refresh validates every configured series and date, stages the snapshot, monthly history, manifest and status together, and only then swaps them into place. A failed source request, incomplete history, corrupt existing archive or failed swap preserves the previous complete dataset. The deployed site stays unchanged when collection fails. The collector retries transient errors, limits parallel requests to three and looks back at most four additional dates when the newest country report is not ready. Older data is visibly labelled.

`web/data/status.json` is a small freshness endpoint. Register `checked_at` with a 48-hour tolerance and the daily `pages.yml` workflow in the central watchdog when hub changes are next authorized. `.github/workflows/schedule-guard.yml` guards this collector and itself; it does not prove data freshness.

## Expand or customize

Edit `config/sources.json`. Add an article such as:

```json
{"title":"Chebucto Community Net","project":"en.wikipedia","group":"Networks"}
```

The project must be a Wikipedia language project. A redirect or nonexistent title may have a different series; verify the intended article. Up to 100 topics, 2–31 country dates and 7–90 baseline days are supported. Counts and filters come from the published snapshot, not the starter list. Each archived date carries its topic list and coverage. Earlier dates retain removed topics and their original groups and values; new topics begin appearing on newly archived dates.

Then run:

```sh
python3 scripts/refresh.py
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

Commit the configuration and generated `web/data/` together, then push to `main`. Alternatively edit the configuration and dispatch **Browser tool · Check and publish**; choose the `main` branch: it refreshes, tests, commits the validated snapshot **and all archive changes**, then deploys the same built data. Non-main manual runs cannot collect or push to main. To request real past source data, use `python3 scripts/refresh.py --date YYYY-MM-DD`; this can add missing historical days or absent country rankings without moving a newer live report backward. It never replaces observations already archived for an existing date. To seed history from a verified local snapshot without querying sources or advancing its check date, use `python3 scripts/refresh.py --archive-existing`. Never hand-fill missing dates with invented values.

## Durable historical data

`web/data/history/YYYY-MM.json` stores one compact observation per configured article/date plus each collected Canadian-reader ranking. `manifest.json` lists actual dates, separate topic/country coverage, byte sizes and SHA-256 checksums. The browser loads only the selected date's month, the months needed for its baseline, and the previous country ranking's month when necessary. It keeps at most eight months in memory. Older months remain available; there is no rolling deletion. This avoids repeating the full rolling topic series in every archived snapshot. Growth follows the configured topics and country ranking limit; the initial 42-day archive is about 285 KB, before compression.

The archive starts with genuine observations already in the checked-in snapshot: worldwide topic data from **2026-10-14** and Canadian-reader rankings from **2026-11-11**. It cannot reconstruct rankings or topic selections that were never collected. Historical topic-only dates explicitly say that a Canadian-country ranking is unavailable. Each day records when its source values were first retrieved; that timestamp is distinct from the measured UTC report date and the site build date.

Existing dates retain their **first observed counts and topic selection**. Wikimedia may revise a count later; the current rolling snapshot may then differ from the retained historical observation. A previously absent country ranking may be added from an actual later retrieval, with its own first-saved timestamp. Removing or adding a configured topic does not rewrite older days. Baseline ratios require every preceding calendar day; gaps suppress the ratio and break the chart instead of pretending missing observations are zero.

Persistence is in Git, not browser storage or a temporary Actions artifact. The whole main workflow is serialized; after waiting, it checks out current main so it includes the preceding run's archives. After tests and browser checks pass, `git add web/data` and a scoped `contents: write` commit retain the files before Pages deployment. A `GITHUB_TOKEN` data commit does not trigger another push workflow; this same run deploys it. The push is non-forced: a conflicting human push fails safely instead of overwriting changes. Dispatch main again after such a failure. A fresh checkout therefore carries every retained historical month. Private follow lists stay only in the visitor's browser and never enter this archive.

## Privacy

Local filters and CSV generation run in the browser. Followed article titles/languages are stored under `coolcode:canadapulse:followed`; **Clear followed articles** removes them. Storage failures fall back to the current visit. A custom lookup sends only its article title/language and requested dates to Wikimedia. No personal information, email or API secret is needed. Opening a source link visits Wikipedia. CoolCode's shared aggregate visit counter follows the site-wide policy and excludes toolbox inputs.

## Build and verification

Python 3.12+ and Node 24+. The static build has no package dependencies or network requests. Meaningful model/collector tests cover calendar baselines and gaps, immutable historical coverage, cold-checkout retention, idempotence, partial upstream failures, archive integrity, rollback, country upper bounds, expanded configuration, hostile URLs and CSV formula text. `tests/browser_smoke.py` runs in Pages CI using Playwright and checks real bundled data, safe rendering, follows surviving refresh, historical date links and coverage gaps, filters, export and mobile layout at a subpath. The app publishes `dist/` only. Do not commit `dist/` or add a CNAME.

## Integration status

This round only edits the newly created repositories. `tool.json` is ready for the catalogue; shared homepage, sitemap and watchdog registration are intentionally left for the authorized hub integration step. Do not describe those pending shared registrations as deployed merely because this project builds.
