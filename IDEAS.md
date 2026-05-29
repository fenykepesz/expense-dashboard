# Ideas & Roadmap

A running list of features to add to the expense dashboard and toolchain.
Check off items as they ship; add new ideas freely.

---

## Next Up

- [ ] Drag-and-drop JSON file loading in the browser
- [ ] Search bar to filter transactions by merchant name
- [ ] Combine/merge multiple JSON files into one

---

## Architecture

- [x] **Migrate to a database backend** — SQLite + Flask backend shipped in v1.1.0; `db.py`, `app.py`, `--db` flag on converters, migration script

---

## Data Import & Merchant Management

- [ ] **In-browser import UI** — upload and process bank exports directly from the dashboard instead of running CLI scripts separately
- [ ] **Merchant category manager** — UI to view, edit, and reassign merchant→category mappings; changes persist so future imports use the updated rules

---

## Transaction Management

- [ ] **Delete transactions from the UI** — remove specific line items interactively (e.g. checkbox per row, or an inline delete button); exact UX TBD

---

## Dashboard UI

- [ ] Drag-and-drop JSON file loading in the browser (no manual file replacement)
- [ ] Custom date range filter (from/to date picker, not just year/month pills)
- [ ] Search bar to filter transactions by merchant name
- [ ] Budget tracking — set monthly per-category budgets, show progress bars
- [ ] Month-over-month % change indicators on the summary cards
- [ ] Export filtered transactions to CSV

---

## Python Toolchain

- [ ] Combine/merge multiple JSON files into one (merge outputs from multiple converters)
- [ ] Merchant normalization — deduplicate name variations ("SUPER-PHARM 123" → "Super Pharm")
- [ ] Multi-bank support — parsers for Hapoalim, Discount, Mizrahi exports
- [ ] Auto exchange-rate lookup (fetch live USD/EUR/GBP → ILS rates via free API)

---

## Nice to Have

- [ ] Dark/light theme preference persisted in localStorage
- [ ] Income tracking alongside expenses (net balance view)
- [ ] Recurring expense detection (flag subscriptions automatically)
