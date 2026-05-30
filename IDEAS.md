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

---

## Data & Backup

- [ ] **Migrate categories to DB** — move custom categories and deleted built-ins from JSON files into a `categories` table in SQLite; single source of truth, simpler backup (v1.4.0)
- [ ] **Backup facility** — "Download Backup" button in UI exports a timestamped `.zip` of the DB; auto-backup before each import as safety net (v1.4.0)

---

## Transaction Management

- [x] **Exclude transactions** — soft-hide individual transactions from calculations and charts; restore any time; filter by excluded status; excluded pill shows count + total (v1.3.0)
- [ ] **Permanently delete transactions** — hard-delete a transaction row from the DB via the UI

---

## Dashboard UI

- [x] Search bar to filter transactions by merchant name (v1.2.0)
- [x] Filter transactions by year, month, category, card, status (v1.2.0 / v1.3.0)
- [ ] Custom date range filter (from/to date picker, not just year/month pills)
- [ ] Budget tracking — set monthly per-category budgets, show progress bars
- [ ] Month-over-month % change indicators on the summary cards
- [ ] Export filtered transactions to CSV

---

## Python Toolchain

- [ ] Merchant normalization — deduplicate name variations ("SUPER-PHARM 123" → "Super Pharm")
- [ ] Multi-bank support — parsers for Hapoalim, Discount, Mizrahi exports
- [ ] Auto exchange-rate lookup (fetch live USD/EUR/GBP → ILS rates via free API)
- [ ] Combine/merge multiple export files into one import

---

## Bank Integration

- [ ] **Full bank expenses integration** — TBD (details to follow)

---

## Nice to Have

- [ ] Dark/light theme preference persisted in localStorage
- [ ] Income tracking alongside expenses (net balance view)
- [ ] Recurring expense detection (flag subscriptions automatically)
