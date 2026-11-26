# Canada Pulse

[Use Canada Pulse](https://coolcode.ca/canadapulse/) to explore Wikipedia reading patterns without an account.

<!-- coolcode:guide -->
“Read from Canada” counts article views originating in Canada; “Canadian topics worldwide” follows a curated list globally. Country figures are privacy-protected upper bounds, not exact reader counts. Browse saved report dates by month, share a date link or export its results. Historical observations and each saved day’s topic selection are retained in the repository. A retrospective import extends the configured topic series to July 2015 and available country rankings to January 2021; these are distinct measures. Missing days remain gaps. A spike compares a complete earlier baseline; it does not explain why people are reading.
<!-- /coolcode:guide -->

## What works

- Date, language, topic and title filters; worldwide volume, ratio and absolute-increase sorting.
- A growing historical archive, month/date selection, shareable date links, sparklines and CSV export. The recent collection window defaults to fourteen country dates and 28-day topic baselines; archived dates do not roll off.
- Follow articles in browser storage, including custom lookups, and check their worldwide views through the selected reporting date.
- Arbitrary Wikipedia article title/language lookup directly against Wikimedia. No API key or Worker handler is required.
- Keyboard navigation, mobile layout and source links. Known utility pages and non-language utility projects such as `thankyou.wikipedia` are filtered from the display and future collection, with the remaining original source ranks retained. Original first-observed archive files are preserved.

The report date is the measured UTC date. `retrieved_at` is when the collector retrieved the data. Neither is a page-build date. Country values use Wikimedia's `views_ceil` field; a missing article is not zero. Each stored country date retains up to the configured `country_limit` language-article results after utility pages are filtered (150 by default), with original source ranks. Worldwide series use the `user` agent class and measure views, not unique people. Canadian topics are editorially selected and are not a complete classification of all Canadian subjects.

## Sources and operation

Sources: [Wikimedia Analytics API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html), `top-per-country/CA/all-access/YYYY/MM/DD` and `per-article/{project}/all-access/user/{article}/daily/{start}/{end}`. Custom browser queries use the same per-article endpoint. Article pages belong to Wikipedia contributors; statistics are attributed to Wikimedia.

The **Browser tool · Check and publish** workflow checks sources daily at **16:23 UTC**, or when dispatched manually. Pushes and PRs build offline from checked-in `web/data/`. Refresh validates every configured series and date, stages the snapshot, monthly history, manifest and status together, and only then swaps them into place. An unavailable earlier country date (HTTP 404) is listed in `unavailable_country_dates`, not zero-filled; it does not block a valid latest report. Previously archived observations for that date remain retained even if the upstream endpoint subsequently returns 404. Other source failures, incomplete topic histories, corrupt existing archives or failed swaps preserve the previous complete dataset. The deployed site stays unchanged when collection fails. The collector retries transient server errors, makes strictly serial requests, stops on HTTP 429, and looks back at most four additional dates when the newest country report is not ready. Older data is visibly labelled.

`web/data/status.json` is a small freshness endpoint. The central watchdog monitors `checked_at` with a 48-hour tolerance and the daily `pages.yml` workflow. Historical imports do not advance this live-data check timestamp. `.github/workflows/schedule-guard.yml` guards this collector and itself; it does not prove data freshness.

## Expand or customize

Edit `config/sources.json`. Add an article such as:

```json
{"title":"Chebucto Community Net","project":"en.wikipedia","group":"Networks"}
```

The project must be a Wikipedia language project. A redirect or nonexistent title may have a different series; verify the intended article. Up to 100 topics, 2–31 country dates and 7–90 baseline days are supported. Counts and filters come from the published snapshot, not the starter list. Each archived date carries its topic list and coverage. Earlier dates retain removed topics and their original groups and values; new topics begin appearing on newly archived dates.

Country-result presentation also uses the verified project/title exclusions in [`web/utility-pages.mjs`](web/utility-pages.mjs), including the Dutch `Hoofdpagina`. Add an exact title, its Wikipedia language project and a source link there, then rebuild. Matching normalizes spaces/underscores and Unicode composition without hiding the same title in a different language project. The display, language filter and CSV share the exclusions; original archive files, view upper bounds and source rank numbers are unchanged.

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

The first archive used genuine source observations already in the original snapshot: worldwide topic data from **2026-10-14** and Canadian-reader rankings from **2026-11-11**. The historical importer retrieves older dates from the same Wikimedia APIs: worldwide article series from **2015-07-01**, and the existing country-ranking dataset from **2021-01-01**. These are retrospective API downloads, not measurements made by CoolCode in those years. The backfilled topic list is the configured selection at import time; it is not a reconstruction of a historical editorial selection. Counts follow those exact article-title/language pairs: page moves and redirects can split a subject’s history, and this importer does not invent or stitch missing aliases. **Country rankings before 2021 are not inferred or substituted from a different dataset.** Each date records its measured day and separate collection timestamp. Missing data remains absent. See [`web/data/backfill.json`](web/data/backfill.json) for exact observed ranges, request/checkpoint counts and source gaps.

Existing dates retain their **first observed counts and topic selection**. Wikimedia may revise a count later; the current rolling snapshot may then differ from the retained historical observation. A previously absent country ranking may be added from an actual later retrieval, with its own first-saved timestamp. Removing or adding a configured topic does not rewrite older days. Baseline ratios require every preceding calendar day; gaps suppress the ratio and break the chart instead of pretending missing observations are zero.

Persistence is in Git, not browser storage or a temporary Actions artifact. The whole main workflow is serialized; after waiting, it checks out current main so it includes the preceding run's archives. After tests and browser checks pass, `git add web/data` and a scoped `contents: write` commit retain the files before Pages deployment. A `GITHUB_TOKEN` data commit does not trigger another push workflow; this same run deploys it. The push is non-forced: a conflicting human push fails safely instead of overwriting changes. Dispatch main again after such a failure. A fresh checkout therefore carries every retained historical month. Private follow lists stay only in the visitor's browser and never enter this archive.

## Privacy

Local filters and CSV generation run in the browser. Followed article titles/languages are stored under `coolcode:canadapulse:followed`; **Clear followed articles** removes them. Storage failures fall back to the current visit. A custom lookup sends only its article title/language and requested dates to Wikimedia. No personal information, email or API secret is needed. Opening a source link visits Wikipedia. CoolCode's shared aggregate visit counter follows the site-wide policy and excludes toolbox inputs.

## Build and verification

Python 3.12+ and Node 24+. The static build has no package dependencies or network requests. Meaningful model/collector tests cover calendar baselines and gaps, immutable historical coverage, cold-checkout retention, idempotence, partial upstream failures, archive integrity, rollback, country upper bounds, expanded configuration, hostile URLs and CSV formula text. `tests/browser_smoke.py` runs in Pages CI using Playwright and checks real bundled data, safe rendering, follows surviving refresh, historical date links and coverage gaps, filters, export and mobile layout at a subpath. The app publishes `dist/` only. Do not commit `dist/` or add a CNAME.

## Resume or extend the historical import

Run the importer from a checkout containing the current published archive:

```sh
python3 scripts/backfill.py
```

It defaults to July 2015 for configured article histories, January 2021 for country rankings, and the latest verified snapshot report date as its end. `--end YYYY-MM-DD`, `--topic-start YYYY-MM-DD` and `--country-start YYYY-MM-DD` can bound an import. No request is made for a future or incomplete UTC day. Article requests cover the full requested range in one call per article; country rankings require one call per day. The source may return fewer observations or HTTP 404: those are explicitly recorded as gaps, never zero-filled. Other source/validation failures stop before replacing the published archive.

Every response has a URL-derived checkpoint in `.cache/backfill/`; interrupted imports resume without repeating completed requests. HTTP 404 checkpoints are deliberate observations of unavailable coverage. To retry one after the source changes, remove only that URL’s local checkpoint or select a fresh `--cache` directory. The final `collected.json` is local working data, not published. Never commit `.cache/`.

For thousands of serial requests, optional HTTP connection reuse avoids repeated TLS handshakes:

```sh
python3 -m pip install requests
python3 scripts/backfill.py --keep-alive
```

`requests` is optional for the one-off importer, not a dependency of the application, daily collector or offline build. Both transports are serial, with at least a 0.35-second gap after a completed response (at most about 171 requests/minute even with instantaneous responses). HTTP 429 stops the run without retrying ahead of the provider’s limit. Resume later from its checkpoints. `--collect-only` fetches/checkpoints without publication; a subsequent normal run uses those checkpoints and publishes atomically.

After collection, validation merges only genuinely missing dates or wholly absent topic/country coverage. Existing measured values and existing topic selections stay immutable. The live `snapshot.json` is untouched, and `status.json` keeps its original `checked_at` while updating archive coverage counts. Run the normal test/build commands, commit `web/data/` together with the importer changes and push. Push deployment is offline and therefore does not repeat the historical requests.

## Integration status

Canada Pulse is registered with the CoolCode catalogue, sitemap, shared visit counter and independent refresh watchdog. The historical importer is an explicitly invoked maintenance command, not an additional scheduled collector. Daily collection remains at 16:23 UTC and continues to retain new observations permanently. Catalogue notes describe the separate country/topic datasets and historical coverage.
