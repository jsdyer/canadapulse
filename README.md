# Canada Pulse

[Use Canada Pulse](https://coolcode.ca/canadapulse/) to explore Wikipedia reading patterns without an account.

<!-- coolcode:guide -->
“Read from Canada” counts article views originating in Canada; “Canadian topics worldwide” follows a curated list globally. Country figures are privacy-protected upper bounds, not exact reader counts. A spike is a comparison with an earlier baseline, not an explanation of why people are reading.
<!-- /coolcode:guide -->

## What works

- Date, language, topic and title filters; worldwide volume, ratio and absolute-increase sorting.
- Fourteen saved country dates and 28-day topic baselines by default; sparklines and CSV export.
- Follow articles in browser storage, including custom lookups, and check their latest available worldwide views.
- Arbitrary Wikipedia article title/language lookup directly against Wikimedia. No API key or Worker handler is required.
- Keyboard navigation, mobile layout and source links. Utility pages are filtered, with the remaining original source ranks retained.

The report date is the measured UTC date. `retrieved_at` is when the collector retrieved the data. Neither is a page-build date. Country values use Wikimedia's `views_ceil` field; a missing article is not zero. Worldwide series use the `user` agent class and measure views, not unique people. Canadian topics are editorially selected and are not a complete classification of all Canadian subjects.

## Sources and operation

Sources: [Wikimedia Analytics API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html), `top-per-country/CA/all-access/YYYY/MM/DD` and `per-article/{project}/all-access/user/{article}/daily/{start}/{end}`. Custom browser queries use the same per-article endpoint. Article pages belong to Wikipedia contributors; statistics are attributed to Wikimedia.

The **Browser tool · Check and publish** workflow checks sources daily at **16:23 UTC**, or when dispatched manually. Pushes and PRs build offline from `web/data/snapshot.json`. Refresh validates every configured series and date before replacing the snapshot. A failed source request or incomplete history fails collection and leaves the published deployment unchanged. The collector retries transient errors, limits parallel requests to three and looks back at most four additional dates when the newest country report is not ready. Older data is visibly labelled.

`web/data/status.json` is a small freshness endpoint. Register `checked_at` with a 48-hour tolerance and the daily `pages.yml` workflow in the central watchdog when hub changes are next authorized. `.github/workflows/schedule-guard.yml` guards this collector and itself; it does not prove data freshness.

## Expand or customize

Edit `config/sources.json`. Add an article such as:

```json
{"title":"Chebucto Community Net","project":"en.wikipedia","group":"Networks"}
```

The project must be a Wikipedia language project. A redirect or nonexistent title may have a different series; verify the intended article. Up to 100 topics, 2–31 country dates and 7–90 baseline days are supported. Counts and filters come from the published snapshot, not the starter list. Each snapshot carries its topic list and date coverage, so earlier snapshots from Git history remain self-contained.

Then run:

```sh
python3 scripts/refresh.py
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

Commit the configuration and generated `web/data/` together, then push to `main`. Alternatively edit the configuration and dispatch **Browser tool · Check and publish**; it refreshes, tests, commits the validated snapshot and deploys that snapshot in the same workflow. To reproduce a past reference date, use `python3 scripts/refresh.py --date YYYY-MM-DD`.

## Privacy

Local filters and CSV generation run in the browser. Followed article titles/languages are stored under `coolcode:canadapulse:followed`; **Clear followed articles** removes them. Storage failures fall back to the current visit. A custom lookup sends only its article title/language and requested dates to Wikimedia. No personal information, email or API secret is needed. Opening a source link visits Wikipedia. CoolCode's shared aggregate visit counter follows the site-wide policy and excludes toolbox inputs.

## Build and verification

Python 3.12+ and Node 24+. The static build has no package dependencies or network requests. Meaningful model/collector tests cover baseline exclusion, missing values, dates, country upper bounds, expanded configuration, hostile URLs and CSV formula text. `tests/browser_smoke.py` runs in Pages CI using Playwright and checks real bundled data, safe rendering, follows surviving refresh, filters, export and mobile layout at a subpath. The app publishes `dist/` only. Do not commit `dist/` or add a CNAME.

## Integration status

This round only edits the newly created repositories. `tool.json` is ready for the catalogue; shared homepage, sitemap and watchdog registration are intentionally left for the authorized hub integration step. Do not describe those pending shared registrations as deployed merely because this project builds.
