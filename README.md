# ZaBir FinanceFlow

A modern, local-first personal finance desktop app built with **Python, Tkinter, Pillow, SQLite3, Matplotlib and ReportLab**.
All data stays on your computer in a single SQLite file.

**Status: all six build phases are complete (v1.0.0).**

## Requirements
- Windows 10/11, **Python 3.11+** (python.org installer, keep *"tcl/tk and IDLE"* ticked)
- VS Code with the Python extension (recommended)

## Install & run (VS Code terminal, PowerShell)
```powershell
cd ZaBir_FinanceFlow
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python main.py
```
In VS Code: *Ctrl+Shift+P → Python: Select Interpreter → .venv*, then press **F5** on `main.py`.

### Optional demo data
```powershell
python seed_demo.py --reset     # WARNING: deletes existing transactions, budgets and goals first
```

### Run the tests
```powershell
python -m unittest discover -s tests -v
```
`test_core.py` covers the database, validation, CRUD, filters, budgets, savings, reports, CSV/PDF export and
backup/restore. `test_ui_smoke.py` builds every page and dialog with a fake Tk (skipped automatically when real Tk exists).

## Features
| Area | What you get |
|---|---|
| **Dashboard** | KPI cards, income vs expense, expense donut, spending trend, month summary, recent transactions, budget and goal progress, month selector - all read from SQLite |
| **Transactions** | Add / edit / view / delete; search (description + category); filters by type, category, month, date range, min/max amount; sort by date or amount; pagination (15-100 rows); filtered CSV export; duplicate-submit protection |
| **Categories** | Default + custom categories with colour and icon, spending totals, safe delete (transactions must be moved to another category) |
| **Budgets** | Overall and per-category monthly limits, live progress, over-budget and near-limit warnings, copy last month, month navigation |
| **Savings goals** | Create/edit/delete, add or withdraw money, contribution history, progress, remaining amount, monthly savings needed, completed goals |
| **Analytics** | Presets or custom month range; income vs expenses, expense distribution, savings trend, category spending, daily activity, income sources, budget utilisation, insight cards |
| **Reports** | Monthly, yearly, income, expense, category, budget and savings reports with live preview; CSV export; PDF export (premium monthly statement with charts, page numbers, header/footer); exports run in the background |
| **Settings** | Dark/light theme (saved), currency, date format, default dashboard month, display name, manual backup, **restore**, automatic backup on exit, database optimise, app info |

## Design decisions
- **Money is stored as integer minor units** (poisha/cents) - no floating point. BDT (৳) is the default with lakh/crore grouping.
  USD, EUR, GBP and INR change *display only*; no currency conversion is ever performed.
- **PDF/chart currency symbols:** if no installed font can draw the symbol (e.g. ৳ without Nirmala UI) the PDF uses the ISO
  code (`BDT 1,234.00`) instead of printing a broken glyph. Charts always use plain numbers or the code.
- **Restore safety:** the chosen file is validated (schema + integrity check), a `pre_restore_*` safety backup is written
  first, and the live database is left untouched if validation fails.
- Business logic (`core/`, `database/`, `utils/`) has no UI imports, so it is unit-tested headlessly.

## Project layout
```
ZaBir_FinanceFlow/
├── main.py  config.py  requirements.txt  seed_demo.py  README.md
├── database/   schema.py, db_manager.py      (schema, connection, backup/restore)
├── core/       finance_manager, category_manager, budget_manager,
│               savings_manager, report_manager, context   (business logic)
├── ui/         main_window, sidebar, topbar, theme, components, dialogs, charts
│   └── pages/  dashboard, transactions, categories, budgets, savings, analytics, reports, settings, base
├── utils/      helpers, validators, image_manager (Pillow), export_manager (CSV/PDF)
├── tests/      test_core.py, test_ui_smoke.py
├── assets/     icons/ images/ fonts/   (logo.png and app.ico are generated here)
├── data/       finance.db, app.log     (created automatically)
├── exports/    backups/
```

## Troubleshooting
- `No module named tkinter` -> re-run the Python installer and enable *tcl/tk*.
- Errors in the UI are logged to `data/app.log` and shown in a dialog.
- Reset everything: close the app and delete `data/finance.db`.
- Restore a mistake: *Settings -> Restore from backup* and pick a file from `backups/`.

