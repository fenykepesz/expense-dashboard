# Ideas & Roadmap

A running list of features to add to the expense dashboard and toolchain.
Check off items as they ship; add new ideas freely.

---

## Architecture

- [x] **Migrate to a database backend** — SQLite + Flask backend, `db.py`, `app.py`, `--db` flag on converters, migration script (v1.1.0)

---

## Data Import & Merchant Management

- [x] **In-browser import UI** — upload and process bank exports directly from the dashboard (v1.2.0)
- [x] **Merchant category manager** — view, edit, and reassign merchant→category mappings; save as rules (v1.2.0)
- [x] **Manage categories** — add and delete categories (including built-ins except Uncategorized); changes persist (v1.3.0)
- [x] **Import auto-saves rules & updates existing** — category assigned during import preview is saved as a rule and applied to all existing transactions for that merchant (v1.5.0)

---

## Data & Backup

- [x] **Migrate categories to DB** — `categories` table in SQLite; migration from JSON on first run; single source of truth (v1.4.0)
- [x] **Backup facility** — "Download Backup" button exports timestamped `.zip`; auto-backup on import confirm and every 30 days; configurable backup folder; "Last backed up" indicator (v1.4.0)

---

## Transaction Management

- [x] **Exclude transactions** — soft-hide individual transactions from calculations and charts; restore any time; filter by excluded status; excluded pill shows count + total (v1.3.0)
- [x] **Permanently delete transactions** — hard-delete a transaction row from the DB via the UI, with confirm dialog (v1.6.0)
- [x] **Transaction notes** — add a free-text one-line note per transaction in the dashboard; persisted in DB (v1.5.0)
- [x] **Inline category change on dashboard** — dropdown per transaction row to change category; updates all transactions for that merchant and saves as a rule (v1.5.0)

---

## Dashboard UI

- [x] Search bar to filter transactions by merchant name (v1.2.0)
- [x] Filter transactions by year, month, category, card, status (v1.2.0 / v1.3.0)
- [x] **Category chart as bars** — replace doughnut chart with a horizontal bar chart for easier reading (v1.5.0)
- [x] Custom date range filter (from/to date picker, alongside year/month pills) (v1.6.0)
- [ ] Budget tracking — set monthly per-category budgets, show progress bars
- [ ] Year-over-year % change indicator (tried month-over-month in v1.6.0, removed — not as useful for this data; revisit as a yearly comparison instead)
- [ ] Export filtered transactions to CSV

---

## Python Toolchain

- [ ] Merchant normalization — deduplicate name variations ("SUPER-PHARM 123" → "Super Pharm")
- [ ] Multi-bank support — parsers for Hapoalim, Discount, Mizrahi exports
- [ ] Auto exchange-rate lookup (fetch live USD/EUR/GBP → ILS rates via free API)
- [ ] Combine/merge multiple export files into one import

---

## Household Finance Expansion (Net Worth / Multi-Fund)

Big-picture goal: evolve this from a credit-card tracker into a household-wide financial
dashboard covering cash flow (bank accounts) and long-term funds (pension/study/investment),
with a top-level net worth view. Decided so far:

- **Four dashboards**: Credit Card (existing, unchanged) · Bank Accounts (new) · Long-Term
  Funds (new) · Net Worth (new, top-level summary)
- **Cash flow model**: Bank Accounts dashboard is the real income-vs-expense picture; the
  monthly credit card bill appears there as a single lump expense line (mirrors how the bank
  actually debits it), not broken out by merchant — that detail stays in the Credit Card tab
- **Net worth model**: sum of bank account balances + long-term fund balances, trended over
  time; credit card does NOT count separately (it's already reflected via the bank debit)
- **Income**: just rows in the bank account transaction table, signed/typed as income vs
  expense — no separate income structure
- **Long-term funds** (pension, study/`קרן השתלמות`, investments): monthly **manual balance
  entry** (fund, date, balance, contribution) — no statement parser planned initially
- **Bank account import**: via `.xls` file, same pattern as the credit card converter; will
  need a real sample export to reverse-engineer the format (expect bank-specific quirks like
  the credit card one had)
- **Household / multi-user**: simple owner label per account/fund (e.g. "household member"
  dropdown) — no login/auth, stays a single local tool operated by one person
- **Frontend**: split `index.html`'s inline JS into per-dashboard files before/while adding
  the new dashboards, rather than growing one monolithic file further
- [x] **Look-Through: consolidate Concentration columns for funds sharing a track (v1.28.1)** —
  direct follow-up to v1.28.0: once the user could actually enter the same Institution Reg # across
  their 5 Altshuler Shaham study funds, the Concentration tables showed 5 nearly-identical columns
  side by side, all reading the exact same "% of fund" since a shared track means identical
  composition by construction. User asked directly whether there was value in that repetition —
  agreed there wasn't, and consolidated: `groupFundsByTrack()` (new, dashboard-lookthrough.js)
  groups active_funds sharing BOTH `institution_reg_number` and `track_number` into one combined
  display column (others render as their own single-fund column, unchanged), summing ₪ across the
  group's members and re-deriving the % from summed fund totals — provably identical to any one
  member's own % since every fund in a shared track carries the same underlying weight per
  category, confirmed both mathematically and against the live grouped render (471,974.3 +
  189,192.5 + 81,452 + 17,369.1 + 15,369.9 = 775,357.8, both still landing on 70.0% of fund). Header
  shows "(N funds)" for a real group. `active_funds` gained `institution_reg_number` (db.py) to
  make the grouping possible — wasn't previously exposed to the frontend. Scoped to the
  Concentration view's per-fund breakdown tables only (`renderCategoryTable`), not All
  Securities/Direct-vs-Funds, which weren't part of what was asked and don't have the same
  guaranteed-identical-composition property per row.
- [x] **Look-Through: multiple funds can share one investment track (v1.28.0)** — user hit
  "Another fund already uses institution X + track Y" trying to enter their real Institution Reg #
  across several Altshuler Shaham study-fund policies, all confirmed with their own insurance
  agent as pooled into the SAME investment track ("1093"), each with a distinct personal fund #
  and balance. The uniqueness guard (`_validate_unique_track_key`, added in v1.22.1) turned out to
  be preventing a legitimate real-world case, not just typos — Israeli pension/study-fund products
  regularly pool many personal accounts into one shared track. Root cause traced before fixing:
  the parser's `track_lookup` was a plain `(institution, track) -> single fund_id` dict, so if the
  guard had simply been removed without also fixing this, whichever fund happened to be LAST in
  `funds` would have silently absorbed 100% of that track's rows and every sibling fund sharing
  the track would show ₪0 look-through data with no error — the guard was accidentally doing its
  job for the wrong reason. Real fix: `track_lookup` now maps to a LIST of fund_ids, and a matching
  filing row is duplicated once per matching fund, so each fund's own weight calculation in
  `get_security_holdings` (row.fair_value_ils / that fund's own row-set total) stays fully
  independent — verified with a new test asserting a 70/30 split within a shared track applies
  correctly to each fund's own separate balance, not merged or dropped. `_validate_unique_track_key`
  removed entirely from `add_fund`/`update_fund`. Verified live via Playwright: setting the same
  Institution Reg # across all 5 of the user's real Altshuler Shaham funds (previously blocked by
  the guard) now saves cleanly with no error.
- [x] **Look-Through: only By Type starts expanded (v1.27.1)** — with the per-section collapse
  from v1.27.0 shipped, defaulted every section OTHER than By Type (Sector/Country/Currency/
  Same-Issuer) to start collapsed, so the Concentration view opens on one focused table instead
  of five stacked ones. `lookthroughSectionCollapsed` now initializes as
  `new Set(['sector', 'country', 'currency', 'crossType'])` instead of empty — the toggle
  mechanics themselves were unchanged, just the starting state.
- [x] **Look-Through: click-to-render caching, pie charts removed, per-fund tables everywhere
  (v1.27.0)** — three fixes from one round of feedback. (1) Every toggle in the Concentration
  view (top-10/show-all, sub-type +/−, and the new section collapse below) was re-fetching from
  the network and rebuilding the whole panel, which visibly flashed/reloaded on every click.
  Split `renderLookthroughView()` into a fetch-and-cache step and a cache-only
  `rerenderLookthroughView()` that every toggle now calls instead — confirmed via Playwright that
  a collapse/expand click now fires zero network requests. Only real data-changing actions
  (import confirm, delete filing) still clear `lookthroughViewCache` and re-fetch. (2) Removed
  the Type/Country/Sector/Fund pie charts added in v1.24.0 — user verdict: "no value" once the
  per-fund breakdown tables existed alongside them as redundant. Deleted `topNPlusOther`,
  `buildLookthroughPieChart`, `renderConcentrationCharts`, the chart canvases, and the Chart.js
  instance variables. (3) Applied the same per-fund breakdown table (`renderCategoryTable`,
  previously only used for By Type/By Sector) to By Country and By Currency, replacing the older
  plain `renderRollupTable`; each rollup section (Type/Sector/Country/Currency/Same-Issuer) is
  now independently collapsible to just its header via a new `lookthroughSectionCollapsed` Set
  and `toggleSection()`, mirroring the existing top-10 and sub-type-breakdown state patterns so
  it survives re-renders without a DOM round-trip. Separately clarified for the user: "cash" in
  the by-type breakdown is money sitting uninvested inside a fund (not an investment vehicle
  itself), and ETF appears under BOTH Equity and Fixed Income Exposure because different ETFs
  hold different things — a Bank Index/S&P 500 ETF is equity, a Tel Bond tracker ETF is fixed
  income; the filing's own `סיווג הקרן` field (added in v1.26.0) is what tells them apart.
- [x] **Look-Through: expandable sub-type rows for merged By Type buckets (v1.26.1)** — the
  v1.26.0 merge showed a plain text summary line ("Stock: ₪X, ETF: ₪Y...") under a merged
  bucket's name; the user wanted a real expandable tree instead — a clickable +/− next to
  Equity Exposure/Fixed Income Exposure/Derivatives & Hedging, collapsed by default, revealing
  indented sub-rows (Stock, ETF, Mutual Fund, ...) that each carry their OWN full breakdown
  (Your ILS, Total %, and every fund's own amount + % of that fund), not just a value. Needed a
  real backend shape change: `by_type`'s `type_breakdown` went from `{instrument_type: value}`
  to `{instrument_type: {value, pct_of_portfolio, by_fund, direct}}` — a full sub-bucket, same
  shape as the parent row, built by the same accumulation helper (`_accumulate`) so parent and
  child rows are computed identically, not two different code paths that could drift apart.
  Frontend: `renderCategoryCells()` factored out of the row-rendering loop so a sub-row renders
  with the exact same per-fund cell logic as its parent, just fed a different (smaller) bucket.
- [x] **Look-Through: real Equity/Fixed Income Exposure merge, not a name-based guess (v1.26.0)**
  — user asked whether ETF should count as Stock, since Stock (35%) + ETF (12%) as separate lines
  understated their real equity exposure. Almost merged blindly on `instrument_type='etf'`, but
  checked the filing first — found a real Tel Bond (bond-index) ETF sitting in the ETF sheet,
  proving ETF isn't reliably equity. The filing has its own `סיווג הקרן` (Fund Classification)
  field on the ETF and Mutual Fund sheets, with values like "מניות בחו\"ל..." (equity) or
  "אג\"ח בארץ..." (bond) — parsed into a new `asset_class` per row
  (`_asset_class_from_classification` in the parser, new `fund_holdings.asset_class` column).
  Needed two follow-up fixes once tested against real data: (1) some ETF rows prefix the label
  with an index name ("35 מניות בארץ...") which a strict prefix match missed — switched to
  substring matching; (2) mutual funds sometimes use plain English ("Equity Funds", "Bond/Fixed
  Income Funds") instead of the Hebrew taxonomy — added those too. A THIRD institution's file
  (Menora) showed some rows using a genuinely generic "Index Funds" label that says nothing
  about equity vs. bond — correctly stays unclassified rather than guessed, confirming the
  never-guess design holds even against a filing this hasn't been tested on before.
  `db.py`'s By Type rollup now merges structurally-equity (Stock) + equity-classified ETF/Mutual
  Fund into "Equity Exposure", and the bond equivalent into "Fixed Income Exposure", each with a
  `type_breakdown` composition line (reusing the same pattern as Concentration's same-issuer
  table) — a directly-held stock (no fund match, `instrument_type=None`) is always equity too,
  and had to be checked BEFORE the "no instrument_type -> Unclassified" fallback, not after, or
  it would have wrongly landed in Unclassified despite being certain equity. Real result on the
  user's data: Equity Exposure jumped to 44.8% of the portfolio (vs. 35.4% for Stock alone) once
  ETF and Mutual Fund equity exposure was correctly folded in.
- [x] **Look-Through: same per-fund breakdown for By Type (v1.25.1)** — extended the v1.25.0
  table design to Type, confirming the backend (`rollup()`-style per-bucket `by_fund`/`direct`
  tracking) generalizes cleanly: `by_type`'s bucket construction in db.py got the identical
  `by_fund`/`direct` treatment as `rollup()`, sorted by value including Unclassified in its
  natural rank. Frontend maps each row's raw instrument-type key through
  `INSTRUMENT_TYPE_LABELS` before handing it to the shared `renderCategoryTable()` — no new
  rendering code needed. Real signal surfaced immediately: on the user's data, one fund (Fenix
  12882) sits at 47% cash while another (Menora) is far more diversified — exactly the kind of
  per-fund comparison this redesign was for. Country/Currency still pending, per the user's
  explicit "let's do type first" sequencing.
- [x] **Look-Through: per-fund breakdown in the By Sector concentration table (v1.25.0)** — the
  user found the existing dual-denominator table (% of Portfolio / % of Named) confusing once
  they had real data in front of it, and asked for a redesign modeled on a reference sheet they'd
  built earlier (their own Claude Desktop report from the original brainstorm): Category | Your
  ILS | Total % | one column per fund showing THAT fund's ₪ amount and % of its OWN total (not
  the whole portfolio) in this category, e.g. "₪200 (15% of fund)". Explicitly scoped to By
  Sector first, to nail the design before repeating it for Country/Currency. `rollup()` in
  db.py now tracks a `by_fund`/`direct` breakdown per bucket (not just a portfolio-wide total),
  and `get_concentration_rollups` exposes `active_funds`/`fund_totals`/`direct_total` so the
  frontend can turn "₪X in this fund" into "₪X, Y% of that fund's own total." Rows sorted by
  value including Unclassified/Conflicting in their natural rank (matching the reference sheet)
  rather than pinned at the end. Top 10 shown by default with a "Show all N" toggle — nothing
  summed into an "Other" bucket the way the pie charts do, every category stays individually
  inspectable. Real finding surfaced by the new table: Unclassified (33%) + Conflicting (27%) =
  over 60% of the portfolio has no usable sector data — the actual reason the old table felt
  unclear, not the column design itself.
- [x] **Look-Through: column tooltips on All Securities/Overlap (v1.24.2)** — every header (the
  fixed columns, each dynamic fund column, Direct, and Overlap's Max Single Fund) now has an ℹ
  tooltip explaining what it means, same `thTooltip()` pattern already used on the Manage Funds
  table. Each fund column's tooltip names that specific fund so it's unambiguous which one a
  reader is hovering.
- [x] **Look-Through: collapse the upload/filings panels by default (v1.24.1)** — once at least
  one filing is imported, the "Import a Holdings Filing" dropzone and "Imported Filings" table
  pushed the actual views (All Securities etc.) far down the page every time the tab opened.
  Wrapped both in `<details>`, collapsed by default — same pattern as the Bank Accounts tab's
  Monthly Net Cash Flow panel (`<summary>` styled to match the existing `.chart-container h3`
  look, since a native `<summary>` isn't targeted by that selector).
- [x] **Look-Through: four Concentration pie charts (v1.24.0)** — Type, Country, Sector, and
  By Fund/Position, added above the existing rollup tables on the Concentration tab. Each
  slice's tooltip shows both the ₪ amount and % of total. Real design questions worked through
  with the user first (they explicitly asked to be asked rather than guessed at, given two real
  money bugs already found earlier this session):
  - **Type** has no rollup function before this (Concentration only ever covered
    sector/country/currency) — added one. 3 of the 20 real instrument types are net-negative
    (interest_rate_swap, future, inflation_swap — written/short derivative positions), and a
    pie slice can't represent a negative value. Decided with the user to merge all
    derivative/hedging types (option, future, fx_swap, equity_swap, interest_rate_swap,
    inflation_swap, warrant, structured_product) into one "Derivatives & Hedging" bucket —
    confirmed its net stays positive on real data (~₪38K) and also cleans up 8 near-zero types
    that would've cluttered the pie individually. `DERIVATIVE_INSTRUMENT_TYPES` in db.py.
  - **Country (42 real values) / Sector (103 real values)** both have long tails — grouped to
    top 10 + "Other" (frontend-only truncation, `topNPlusOther()`, since `get_concentration_rollups`
    already returns the full sorted list for the existing tables). "Unclassified"/"Conflicting"
    are kept as their OWN honest slices regardless of rank, never folded into "Other" — Currency's
    Conflicting bucket alone is 27% of the portfolio on real data (turned out to be almost
    entirely multi-currency bank cash accounts getting grouped under one row per bank, not an
    actual data quality problem — explained to the user with a concrete example before they
    confirmed keeping it visible).
  - **By Fund/Position** — new `by_fund` rollup: each active fund's total contribution (name +
    Track #, since names can collide) plus one "Direct" bucket for anything held outside a fund
    — a full partition of `total_portfolio`, unlike the other rollups which can have gaps.
  - Reused the app's existing pie-chart pattern exactly (`CHART_PALETTE` from shared.js,
    destroy-before-recreate, `getThemeColors()` for dark-mode-aware legend text) — this is the
    first pie chart pattern extended to include a percentage in the tooltip alongside the
    amount, which no existing chart in the app did before.
- [x] **Look-Through: clarify the fund filter's scope (v1.23.3)** — the fund/position filter
  above All Securities narrows which ROWS show (only securities that fund holds) but was easy
  to misread as narrowing the NUMBERS too — the user selected one fund and circled the fact
  that other funds' columns and My ILS/% still showed everything, expecting an isolated
  single-fund view. Confirmed with the user this filter should stay an inclusion filter (My
  ILS/%/every column always reflect everything you own, regardless of this selection) and just
  needed to say so — added a "Held in:" label, renamed the options ("Any fund/position" /
  "Direct holding" instead of the more ambiguous "All Funds/Direct"), and an ℹ tooltip spelling
  out that it only filters which rows are shown.
- [x] **Look-Through: per-fund breakdown columns restored, back-to-front (v1.23.2)** — v1.23.0
  collapsed the old per-fund columns into one compact "Funds/Positions" text column with a
  hover tooltip, to avoid the column count growing unbounded as funds are added. Live use
  showed a clear preference for the opposite: the user wanted each fund broken out as its own
  named column with the specific ILS amount, e.g. "Menora / 18013" and "Phoenix / 9579" as
  two-line headers (company name + Track #, since a fund's own display Name can be identical
  across funds — see the v1.22.1 picker fix). Restored dynamic per-fund columns (one per active
  fund, inserted between Type and Country) plus an optional Direct column that only appears
  when at least one security actually has a direct value. Column-resize bookkeeping had to
  change to support this: a fixed column count could rely on positional index matching between
  resize handles and `<col>` elements, but a variable fund count breaks that, so each resize
  handle now carries its own `data-col-index` (which `<col>` to resize) and, for the fixed
  columns only, `data-col-key` (which width to persist) — fund/Direct columns resize within the
  session but aren't saved to `localStorage`, since which funds are active changes with every
  import.
- [x] **Look-Through: classify the "Other Derivatives" sheet by its own Asset Type column
  (v1.23.1)** — v1.23.0 left ~792 real rows tagged generic `instrument_type='other'` with a
  note that they looked like FX forward contracts by content (bank SWIFT/BIC issuer codes,
  currency-pair "securities") but needed the actual source file to confirm properly rather than
  guessing from content. User sent the file; inspecting it directly found the true cause: all
  792 rows come from ONE sheet (`לא סחיר נגזרים אחרים`, "non-tradable other derivatives") that
  itself bundles four genuinely different OTC derivative types — confirmed via the sheet's own
  `סוג הנכס` (Asset Type) column, a filing-defined field with exactly 4 real values: מט"ח (FX,
  5,970 rows company-wide) → new `fx_swap`, ריבית ואג"ח (interest rate) → new
  `interest_rate_swap`, מניות לרבות מדדי מניות (equity/index) → new `equity_swap`, מדד המחירים
  לצרכן (CPI/inflation) → new `inflation_swap`. Since this is a first-class column the filing
  itself provides (not a guess from issuer-name shape), classifying by it doesn't break the
  parser's "match by header/sheet name, not row content" design — it's the SAME kind of lookup
  CANONICAL_FIELDS already does for every other field, just applied per-row instead of per-sheet
  for this one sheet specifically (`OTHER_DERIVATIVES_SHEET_NAME`,
  `ASSET_TYPE_TO_INSTRUMENT_TYPE`). Re-parsing the user's real file dropped `other` from 792 rows
  to 5 (genuinely miscellaneous items from a different, correctly-generic "Other Assets" sheet —
  repo tax positions, receivables/payables). Re-importing the same filing picks up the corrected
  labels for already-stored data (replace-on-reimport, no schema migration needed).
- [x] **Look-Through: personal-value fix, merged All Securities view, real redesign (v1.23.0)**
  — first real usage against the actual Fenix data surfaced a second, more serious value bug on
  top of the v1.22.0 one, plus a set of requested UX changes; all landed together.
  - **The real bug**: `fair_value_ils` (the value the v1.22.0 fix switched to) turned out to be
    the filing's INSTITUTIONAL total for that security across the WHOLE TRACK — every
    policyholder invested in it combined — not this user's personal share. Confirmed by
    comparing the sum of everything imported for each fund against the user's own recorded
    balance: off by 1,500x and 8,750x (a personal savings policy showing ₪657M of bank cash was
    the tell). Fixed by converting each row to a WEIGHT within its own fund
    (`row.fair_value_ils / sum of fair_value_ils across that whole fund`) and applying that
    weight to the user's own `fund_balances` entry for that fund — `has_unbalanced_fund` is back
    (a fund with holdings rows but no recorded balance can't have a weight applied at all, so it
    contributes 0 and is flagged, never guessed).
  - **A second real bug found fixing the first one**: merging fund-derived exposure with direct
    stock holdings by `security_number` alone silently collapsed different securities that
    happen to share an ISIN-like code — confirmed on real data where a written equity option's
    `security_number` matched its underlying stock's ISIN exactly, but with a different
    `issuer_number` (the option counterparty vs. the equity issuer). The two were correctly kept
    separate by the existing fund-only aggregation but collided in the merge, silently
    overwriting one with the other (~₪62,000 vanished on the real Fenix data). Fixed by giving
    every fund-derived entry its own stable identity and only using security_number to find a
    directly-held holding's best merge candidate (preferring an equity-shaped instrument type
    over a derivative sharing the same code) — nothing is ever collapsed away.
  - **All Securities is now the merged view** (`get_all_securities`, replacing the old
    fund-only `get_security_holdings` as the tab's data source): direct stock holdings and
    fund-derived exposure combine into one row and one `% of Invested` — a directly-held MSFT
    position now counts toward the same denominator as fund exposure to MSFT. Overlap and
    Concentration now run on this same merged set. The old "Direct + Indirect" tab is kept as a
    separate, differently-scoped view — "Direct vs. Funds Breakdown" — anchored on each
    individual direct holding specifically (not every security), showing its fund-side
    counterpart's value (0, not omitted, when there isn't one) and which fund(s) contribute it.
  - **Column redesign**: Security and Issuer collapsed into one "Holding" column (issuer shown
    as a muted sub-line only when it differs from the security name — decided in favor of
    keeping the more specific security name primary, since two different bonds from the same
    issuer would otherwise look identical) — the per-fund columns (which grew with every fund
    added) became one compact "Funds/Positions" column with a hover tooltip for the breakdown.
    New order: Holding, My ILS (Invested), % of Invested, Type, Funds/Positions, Country,
    Sector, Currency. The whole table is now resizable, sortable, and filterable (search text +
    Type + Fund/Direct dropdowns), same drag-handle/click-header pattern as the Manage Funds
    table — hit the same CSS gotcha as that table's sticky header: `.col-resize-handle` is
    `position:absolute; height:100%` and needs its own `<th>` as the positioning anchor; without
    a scoped `position:relative` rule it escaped to a distant ancestor and stretched to the
    entire page's height instead of just one header cell.
  - **Concentration's same-issuer cross-type rollup gained a `type_breakdown`** — e.g. "מדינת
    ישראל: ₪500K total = ₪100K bonds + ₪400K loans" instead of just a value and a list of type
    names — plus a `security_name` fallback for direct-only holdings with no issuer info, so
    they no longer collide into one shared blank-issuer bucket.
  - Fund names shown anywhere in this tab now include the Track # when set
    (`fundLabel()`) — needed the moment two of the user's own funds turned out to share an
    identical display name (see [[architecture]]'s Track # picker note), otherwise the
    Funds/Positions column would show the same name twice with no way to tell them apart.
  - Still pending: some sheet types in the Fenix (savings policy) filing aren't recognized by
    `SHEET_NAME_TO_INSTRUMENT_TYPE` yet and land under `instrument_type='other'` — sampled the
    largest ones and they're clearly FX forward contracts (issuer names are bank SWIFT/BIC codes
    like CITIUS33/CHASUS33, "security" is a currency pair). Needs the actual sheet name(s) from
    the source file to map properly rather than guessing from row content.
- [x] **Remove Official Fund #, Track # picker level (v1.22.1)** — while adding real Fenix
  savings-policy funds and putting Look-Through's Institution Reg #/Track # fields to real use,
  two follow-ups: (1) **Official Fund #** (added v1.21.0) was removed entirely — column, API
  field, table column, add-form input, all gone — since it never ended up wired to anything
  (not even Look-Through matching, which uses `institution_reg_number` + `track_number`, not
  this field) and the user flagged it as pure clutter. `funds.official_fund_number` is dropped
  via `ALTER TABLE ... DROP COLUMN` in the standard migration loop, same idempotent
  try/ALTER/except pattern used for every column addition elsewhere — no data was lost, since no
  fund had ever had a value in it. (2) **Fund Balances picker gained a 4th escalation level**:
  the real Fenix data surfaced a case the cascading Company → Fund Name → Fund # picker (v1.17.0)
  couldn't handle — two tracks under one savings policy share the exact same Fund # (it's the
  policy number, not a per-track identifier), so the picker had nowhere left to escalate. Added
  Track # as a further level: if Fund # doesn't disambiguate (all candidates share one value),
  it's skipped entirely and a Track # dropdown appears immediately after Fund Name instead;
  if Fund # *does* narrow things down but ties remain, Track # appears after that. Verified live
  against the real two-track Fenix policy (tracks 9579/12882, identical Fund # 3456318082) via
  Playwright — the dropdown appeared, listed both tracks, and resolved to the correct fund with
  its own balance history each time.
- [x] **Look-Through security-level holdings (v1.22.0)** — new top-level "🔎 Look-Through" tab:
  imports the quarterly "מצבת נכסים" (Uniform Structure asset statement) regulatory filing that
  Israeli insurance companies and pension/provident fund managers publish, and aggregates
  security-level exposure across every one of the user's funds combined (pension + study fund +
  provident fund etc. all sum seamlessly), merged with existing direct stock holdings by ISIN.
  One `.xlsx` per institution, ~30 sheets; a new `tools/holdings_filing_to_json.py` parses every
  holdings-shaped sheet by matching **header text** against a shared `CANONICAL_FIELDS` dict
  (not column position — real column counts ranged 16–53 across sheet types), so the same code
  handles cash, bonds, equities, ETFs, mutual funds, derivatives, real estate, loans, etc.
  without any institution-specific branches — validated against two real institutions' actual
  filings (Phoenix and Menora), not just synthetic fixtures. Rows are scoped at parse time to
  only the caller's own funds' `(institution_reg_number, track_number)` pairs — two new `funds`
  fields, validated unique together — so a multi-billion-shekel company-wide filing never gets
  stored beyond the tracks actually configured. Full security-level precision (every holding
  row, no minimum-weight cutoff), full institution/track scope, no fund-type restriction. Two
  new tables (`holdings_filings` one row per institution-quarter, `fund_holdings` the per-row
  snapshot); re-uploading the same quarter replaces cleanly, a new quarter preserves history for
  free. Four views: All Securities, Overlap (2+ funds), Concentration (sector/country/currency
  rollups with a dual denominator so unclassified holdings can't silently dilute or vanish from
  the total, plus same-issuer-cross-type grouping), and Direct + Indirect (merges with
  `stock_holdings` by ISIN). ETF/mutual-fund second-order look-through (decomposing what's
  *inside* a fund the user's fund holds) is explicitly out of scope for now.
  - **Real bug found and fixed during end-to-end verification against the actual Phoenix file**:
    the column labeled "% of track's assets" (`שיעור מנכסי אפיק ההשקעה`) turned out to sum to
    ~100% *within each instrument-type sheet* for a track, not across the track's total value —
    one bond sheet had a row at 525%. The original formula (`fund_balance × pct_of_track`) was
    tried first and looked reasonable until this was checked directly against real numbers,
    where it overcounted massively (every instrument category independently claiming ~100% of
    the fund). Every holdings sheet also carries an absolute `שווי הוגן (באלפי ש"ח)` (fair value,
    thousands ILS) column, already scoped to that specific track — summing it across all of one
    track's sheets produced a sane total that matched the track's real order of magnitude, and
    it doesn't depend on `fund_balances` being in sync with the filing period at all. Switched
    to that as the actual value source; `pct_of_track` is still parsed and stored but only as an
    informational per-category weight, never used for dollar math.
- [x] **Official Fund Number, Management Fees, column tooltips (v1.21.0–v1.21.1)** — three additions to
  the Manage Funds table. (1) **Official Fund #** — a new field distinct from the existing
  (personal) Fund #: the fund/track's official industry-wide identifier, shared by everyone
  invested in it rather than specific to your account. Same optional-text treatment as Fund #,
  available on both the add form and inline in the table. (2) **Management Fees** — a fund can
  charge more than one fee at once (e.g. a Deposits fee AND a separate Total/balance fee
  simultaneously — common for real Israeli pension/study/provident funds), so this is a related
  table (`fund_fees`, `UNIQUE(fund_id, fee_basis)`) rather than one column: up to one fee per
  basis (Deposits/Earnings/Total), rendered as small removable badges in a "Fees" column with
  an inline add-row (basis dropdown + % input) that only offers bases not already used.
  `add_fund_fee`/`delete_fund_fee` return the full funds list (fees embedded per fund via
  `get_funds()`) so the table re-renders the same way any other inline edit does. (3) **Column
  tooltips** — every column header in the Manage Funds table now has an ℹ tooltip icon
  explaining what it means (`FUND_COLUMN_TOOLTIPS` in dashboard-funds.js, `thTooltip()` helper),
  extending the pattern that previously only existed for the Risk column.
  - **v1.21.1 follow-up** — table usability, requested right after seeing it live with ~30 rows:
    (1) columns are now drag-to-resize (same pattern as the credit-card transaction table:
    `<colgroup>` + `.col-resize-handle`, widths persisted to `localStorage`). (2) The app's
    overall max-width grew from 1400px to 1800px so more columns fit without horizontal
    scrolling on a normal-width screen. (3) The table now sits in a height-bounded,
    internally-scrolling box with a sticky header, instead of growing to full height and
    pushing its horizontal scrollbar down past 30 rows of content — the scrollbar (and the
    column headers) stay reachable regardless of row count. Hit two real CSS gotchas getting
    there: `border-collapse:collapse` (the shared `.transactions-table` default) silently
    breaks `position:sticky` on `<th>` in most browsers, and a sticky element's own `margin-top`
    gets visually "eaten" once it sticks — both fixed scoped to just this table, not the shared
    class.
- [x] **Stock/brokerage holdings (v1.20.0–v1.20.1)** — a separate "Manage Stock Holdings" panel under
  Long-Term Funds (own tables `stock_holdings`/`stock_values`, own API, own UI — not shoehorned
  into `funds`, since the columns don't fit the generic Company/Fund Name shape). Add a holding
  once (Symbol, Brokerage Firm, Type label Stock/ESPP/RSU, Owner, Cost Basis per unit), then
  record Quantity + Price per unit at each check-in (upserts per holding+date, same pattern as
  fund balances) — Value Date auto-picks the last recorded quantity into the form as a starting
  point. Total Value and Net Value are derived, never typed: `Net Value = Total Value − 25% ×
  max(0, Total Value − Cost Basis × Quantity)` (`db.STOCK_TAX_RATE`, `_compute_stock_value`) —
  taxes only the gain above cost basis, matching how capital gains actually work for stock,
  ESPP, and RSU alike once cost basis is set correctly (purchase price for stock/ESPP,
  vesting-date fair market value for RSU — the Type label never branches the math, only the
  cost basis does). If Cost Basis is left blank, Net Value shows "⚠ Needs cost basis" instead
  of guessing — a holding with no cost basis is a genuinely unknown-gain state, not something
  worth a fake default (decided against auto-filling 25%-of-value or similar, since that number
  would look exactly as trustworthy as a real one while quietly being wrong). Counts toward Net
  Worth (via `kind: "stock"` in `get_net_worth_series`, own `NET_WORTH_TYPE_LABELS` entry,
  folded into the "Long-Term Funds" summary card) using Net Value when known, falling back to
  Total Value when cost basis is unset — a holding is never silently dropped from the total
  just because one field hasn't been filled in yet. No live price lookup — manual entry only,
  by design; see the discussion below for why.
  - **Manual entry over live price lookup, decided in discussion before building**: fetching
    the unit price automatically (some market-data API) vs. typing it in at each check-in, same
    cadence as every other fund. Live lookup would have been the app's first-ever external
    network dependency — everything else is local file upload or manual entry, by design (see
    the "Long-term funds: monthly manual balance entry — no statement parser planned initially"
    decision above) — and brings problems this app has never had to deal with: an API
    key/service to pick, rate limits, currency mismatches for non-ILS symbols, "symbol not
    found" errors, and a value that's only ever "as of whenever you last opened the tab," which
    isn't meaningfully better than a manual price for a tool updated ~monthly anyway. Symbol +
    Quantity + unit-price as three typed fields (instead of one typed lump total) still gets
    most of the benefit — the app does the multiplication/tax math instead of you, removing the
    error-prone part, without taking on an API integration for a number re-typed once a month
    regardless. Live lookup remains a possible later enhancement if manual entry proves
    annoying in practice.
  - **v1.20.1 follow-up, found while the user entered their real holdings**: two holdings can
    legitimately share a Symbol — e.g. an RSU grant and a separate ESPP purchase of the same
    company, each with a different Cost Basis. (1) The Net Worth "Include" picker's pill now
    shows the holding Type (ESPP/RSU/Stock) as part of its sub-line alongside Owner, and the
    Latest Balances table appends it in parentheses next to the name, so two same-symbol rows
    stay visually distinguishable everywhere items are identified by name alone (previously only
    the Manage Stock Holdings table itself showed Type). (2) Adding the Stocks category was the
    9th column in the Include picker's category row — CSS Grid's `auto-fill` fixes a column
    count for the WHOLE grid, so the 9th category stranded itself alone on an otherwise-empty
    second row. Switched to a fixed-width flex row (each category a hard 135px, long pill labels
    wrap instead of growing the column) with horizontal scroll as a fallback, not the primary
    mechanism — today's 9 categories fit in one row with room to spare.
- [x] **Multi-select account filter** — account filter is now toggle pills (same UX as the
  year picker) so any combination of accounts can be viewed together (v1.13.0)
- [x] **Fund type filter, Liquid flag, cascading fund picker (v1.17.0)** — (1) Manage Funds
  table gets a "Filter by type" dropdown. (2) New `is_liquid` boolean field (checkbox on
  add/edit, 💧 Liquid column) marking cash-equivalent funds (e.g. כספית ניהול נזילות) vs
  locked long-term savings — informational only, not yet wired into any calculation. (3) The
  Fund Balances "Select a fund" dropdown became a cascading Company → Fund Name → Fund #
  picker: resolves to a specific fund the moment the choice is unambiguous (e.g. a company
  with only one fund resolves instantly), and only reveals the Fund # dropdown when two funds
  genuinely share company+name (verified live against the user's own data: two Altshuler
  Shaham funds both named "אלטשולר שחם השתלמות כללי", disambiguated by fund number). A
  one-line "Selected: Company — Name — #Number" confirmation replaces showing resolved values
  as disabled dropdowns.
- [x] **Net Worth: categorized Include picker + Owner filter (v1.19.2–v1.19.5)** — (1) The
  "Include" item picker is now a table-like grid — Type as a column header, that type's funds
  listed as pills underneath — instead of one flat wall of pills; same grouping/order as the
  "By Type" chart view (v1.19.3 switched the columns from stacked rows to true side-by-side
  CSS grid columns; v1.19.4 pulled the overall "All" toggle out of the grid into its own
  full-width bar above the columns and shrank the pills so all 8 categories fit in one row;
  v1.19.5 added a per-category "All" pill to each column — toggles every item in just that
  category — and an owner sub-line under each fund/account pill's name in a muted secondary
  color). (2) New "Owner" pill picker (All + one per household member, "No Owner" bucket for
  unassigned items) that ANDs with the Include picker: selecting an owner narrows the summary
  cards, chart, and Latest Balances table down to just that owner's net worth, without having
  to hand-select every one of their funds/accounts.
- [x] **Real Estate fund type (v1.19.1)** — `real_estate` added to `FUND_TYPES` for tracking a
  home or other property alongside long-term funds (a fund with manually-entered balances, no
  mortgage/liability tracking — use net equity if there's a mortgage). `NET_WORTH_TYPE_LABELS`
  entry appended at the end, same color-stability rule as the other fund-type additions below.
- [x] **Manage Funds table redesign (v1.19.0)** — (1) Type moved to the first column. (2) Every
  field is now directly editable in place — no more click-✎-to-enter-row-edit-mode: dropdowns
  (Type, Risk level, Owner) save immediately on change, the Liquid checkbox saves immediately,
  text fields (Company, Fund Name, Fund #, Risk note) save on blur, matching the notes-input
  pattern used elsewhere. (3) All columns are sortable by clicking the header (▲/▼/↕
  indicator), blanks always sort last regardless of direction. (4) New "Latest Value" column
  showing each fund's most recent balance + as-of date, via a correlated subquery in
  `get_funds()` — refreshes automatically when a balance is added/deleted in the panel below.
- [x] **More Israeli fund types (v1.18.1–v1.18.2)** — `provident_fund` (קופת גמל),
  `investment_provident_fund` (קופת גמל להשקעה), `money_market_fund` (קרן כספית), and
  `savings_policy` (פוליסת חסכון) added to `FUND_TYPES`, each a genuinely distinct long-term
  savings vehicle rather than generic "Investment"/"Other". `NET_WORTH_TYPE_LABELS` entries are
  appended at the end, never inserted, so existing types' colors in the Net Worth "By Type"
  chart stay stable for anyone with that view already open.
- [x] **Exclude funds/accounts from Net Worth (v1.16.0)** — persistent exclude/restore toggle
  (⊘/↺) on funds (Manage Funds table, new "Net Worth" status column) and bank accounts
  (Manage Bank Accounts pills), scoped to Net Worth only — an excluded item keeps counting
  normally in its own Bank Accounts / Long-Term Funds tab, same as how excluding a transaction
  only removes it from totals, not from its own table. New `excluded_from_net_worth` column on
  `funds`/`bank_accounts`, `PATCH /api/bank-accounts/<id>`, `get_net_worth_series` filters both.
  (Replaces an earlier Chart.js legend-click-to-hide misfeature from the v1.15.0 session that
  didn't match what "hide" meant here — removed.)
- [x] **Fund detail fields + editing (v1.15.0)** — funds now have Company Name (mandatory),
  Fund Name (mandatory), and Fund Number (optional). The Manage Funds panel is a table
  (Company / Fund Name / Fund # / Type / Owner) with inline edit (✎) — the first "edit"
  capability anywhere in the app, via a new `PATCH /api/funds/<id>`. Existing funds migrate
  with company_name/fund_number defaulted to empty.
- [x] **Net worth: hide individual chart lines (v1.15.0)** — clicking a legend entry in the
  By Type / By Item views toggles that line, same as standard Chart.js behavior, but the
  hidden state now survives filter/mode changes (which recreate the chart) instead of
  resetting every time.
- [x] **Monthly Net Cash Flow chart (v1.14.0)** — collapsed-by-default `<details>` panel below
  the Monthly Cash Flow chart on the Bank Accounts tab: diverging bars around a zero baseline
  (teal surplus / orange deficit), scale symmetric around zero, follows all dashboard filters,
  renders lazily on first expand
- [x] **Layout polish (v1.13.1)** — app opens on Bank Accounts (now the first tab); "Dashboard"
  renamed "Credit Cards"; bank Transactions tile removed; Manage/Add&Import panels moved below
  the bank dashboard
- [x] **Bank cash-flow dashboard** — full credit-card-style dashboard in the Bank Accounts
  tab across all accounts: 6 summary cards (income/expenses/net/…), Monthly Cash Flow chart
  (income vs expenses), expenses by category / top descriptions / by account charts, filters
  (year pills, month, **type income/expense**, category, account, status, date range,
  search), sortable paged table with a Type column (3rd), inline per-transaction category
  edit (v1.12.0)
- [x] **Bank account `.xls` import + converter (Phase 6)** — `tools/bank_excel_to_json.py`
  parses the HTML-in-.xls account export (xlTable; debit/credit columns → signed amounts;
  `**` footnote rows take their value date; running balance → `balance_after`); in-browser
  upload in the Bank Accounts tab with preview, account-number cross-check, and
  date+reference+amount duplicate skipping (safe overlapping monthly re-imports). Net worth
  now anchors bank balances to imported `balance_after` (v1.11.0)
- [x] **Bank account transactions table + dashboard (Phase 4)** — `bank_accounts`/
  `bank_transactions` tables, owner dropdown, manual entry (income/expense with auto-sign),
  exclude/notes/delete per transaction, new "Bank Accounts" tab. File import still pending
  (Phase 6) (v1.9.0)
- [x] **Long-term funds table + dashboard (Phase 3)** — `funds`/`fund_balances` tables, owner
  dropdown, monthly manual balance entry (upserts per fund+month), balance-over-time chart
  per fund, new "Long-Term Funds" tab (v1.8.0)
- [x] **Net worth dashboard (Phase 5)** — new "Net Worth" tab: monthly trend chart
  (Total / By Type / By Item views), multi-select item filter (same pill UX as the year
  picker), summary cards, latest-balances table. Funds use last-entry-per-month carried
  forward; bank accounts use cumulative sum of non-excluded transactions until the
  importer populates `balance_after` (v1.10.0)
- [x] **Household members (Phase 1)** — managed list, CRUD API, minimal panel in Merchants
  tab (will move into its own `household.js` UI as the new dashboards take shape) (v1.7.0)
- [x] **Split frontend JS into per-feature files (Phase 2)** — `index.html`'s inline script
  is now 7 files under `js/`; verified zero behavior change (v1.7.0)

---

## Fund Classification & Risk Profile (Future Vision)

Big-picture goal: build a tool that identifies and enumerates all the funds a person or
household owns — bank accounts, long-term funds, investments — so a complete picture of net
worth emerges. From there, classify each fund by the mechanism used to hold it, along several
dimensions:

1. **Liquidity** — how quickly the money can be accessed
2. **Risk** — how exposed the fund is to loss/volatility
3. **Growth potential** (?) — expected return characteristics

Together these let the tool present the user a **risk profile**, help them see whether their
holdings are balanced across mechanisms, and eventually support **AI-based analysis** of their
overall financial position. At a later stage, this classification could become the foundation
for a **retirement calculator**.

Already in place, as a starting point:
- Net worth aggregation across bank accounts and funds exists (Net Worth tab, Total/By
  Type/By Item views)
- `is_liquid` boolean on funds (v1.17.0) is a first, informational step toward the Liquidity
  dimension — not yet used for any classification or scoring
- Fund identity (company/name/number) and type (pension/study/investment/other) are already
  captured per fund
- **Risk classification implemented (v1.18.0)** — see below

**Risk — decided to be self-declared, not inferred.** A fund's actual risk depends on the
specific exposure/breakdown of the underlying mechanism, which this tool has no live data
source for (would require pulling from Israel's capital markets registry / רשות שוק ההון,
already ruled out elsewhere in this doc as unrealistic without a live feed). Two benefits of
self-declaration: it's the only realistically buildable option, and it keeps the tool
descriptive ("recording your own judgment") rather than prescriptive ("assessing your risk
for you") — important given the README's existing "not financial advice" disclaimer.

Draft 5-level scale (labels shown in UI, not raw numbers — same pattern as fund type today).
Anchored to the track names Israeli pension/study funds already use, so self-assessment maps
onto paperwork the user already has rather than an abstract 1–5:

| # | Label | Meaning | Example anchor |
|---|---|---|---|
| 1 | Capital Guaranteed | Value doesn't really fluctuate | Checking/savings, כספית money-market fund |
| 2 | Low Risk | Mostly bonds; principal largely protected | מסלול סולידי / אג"ח |
| 3 | Moderate Risk | Mixed stock/bond blend | מסלול כללי (default track for most pension/study funds) |
| 4 | High Risk | Mostly equities | מסלול מנייתי |
| 5 | Very High Risk | Concentrated/leveraged/single-position | Individual stocks, crypto, sector-concentrated funds |

Definitions/examples live as static UI help text (educational, not advice about any specific
fund — the tool never assigns a level, the user always does).

Design details carried into implementation:
- Pair the scale with a short free-text note (same pattern as existing transaction notes) —
  e.g. "70% equity, 30% bonds per my last statement" — for detail beyond the 5-level pick
- Risk is **not** a set-once classification — a fund's underlying exposure can change (track
  switch, manager reallocation), so the field is easily re-editable at any time, framed
  as "current best guess" rather than a fixed label

- [x] **Risk classification (v1.18.0)** — self-declared 0–5 `risk_level` + free-text
  `risk_note` on **both** funds and bank accounts (scope extended to bank accounts too, for
  symmetry with `excluded_from_net_worth` — most will simply be rated Capital Guaranteed).
  0 = Not Rated (default, renders as `—`). Funds: new "Risk" column in the Manage Funds table
  with a ℹ tooltip showing the full scale definition, editable via the existing inline edit
  row (not on the add form — rating happens after the fund exists). Bank accounts: appended to
  the pill info line (`· Risk: <label>`), editable via a shared inline panel below the account
  list (pills have no row to expand into). `db.update_bank_account()` is new — bank accounts
  previously only had a single-purpose exclude-toggle setter, now generalized the same way
  `update_fund()` already works.
- [ ] Growth potential classification per fund (definition TBD — marked "?" by design, still
  an open question; may turn out to be a derived cross-tab of Liquidity × Risk rather than
  its own field — worth checking before building a third independent axis)
- [ ] Liquidity: consider evolving `is_liquid` from a boolean into a tier + optional unlock
  date (e.g. קרן השתלמות unlocks after 6 years), to support an actual liquidity-ladder view
- [ ] A combined risk-profile view — cross-tabulating Liquidity × Risk, reusing the existing
  Net Worth chart infrastructure sliced by these fields instead of fund type
- [ ] Rebalancing guidance — surfacing when holdings are concentrated in one liquidity/risk
  bucket (needs an explicit decision on how prescriptive to be, given the "not financial
  advice" disclaimer)
- [ ] AI-based analysis of the overall financial position (would be the first non-local
  feature in this app — needs an explicit, opt-in decision given everything today stays on
  the user's machine)
- [ ] Retirement calculator, built on top of this classification layer — closer than it looks,
  since net worth, monthly contributions per fund (`fund_balances.contribution`), and cash-flow
  burn rate (Bank Accounts tab) already exist; mainly missing a return-rate assumption per
  risk tier to project forward

---

## Nice to Have

- [x] Dark/light theme preference persisted in localStorage (already implemented; falls back to system preference)
- [ ] Recurring expense detection (flag subscriptions automatically)
