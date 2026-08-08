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
- [x] **Multi-select account filter** — account filter is now toggle pills (same UX as the
  year picker) so any combination of accounts can be viewed together (v1.13.0)
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

## Nice to Have

- [x] Dark/light theme preference persisted in localStorage (already implemented; falls back to system preference)
- [ ] Recurring expense detection (flag subscriptions automatically)
