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
