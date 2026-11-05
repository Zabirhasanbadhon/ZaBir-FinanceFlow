# 💰 ZaBir FinanceFlow
### Smart Personal Finance Management System

<p align="center">
  **Take Control of Your Money. Track Every Expense. Build Your Financial Future.**
</p>

<p align="center">
  ![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
  ![Tkinter](https://img.shields.io/badge/GUI-Tkinter-orange)
  ![SQLite](https://img.shields.io/badge/Database-SQLite3-003B57?logo=sqlite&logoColor=white)
  ![Version](https://img.shields.io/badge/Version-1.0.0-success)
  ![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
  ![License](https://img.shields.io/badge/License-MIT-green)
</p>

---

## ✨ Overview

**ZaBir FinanceFlow** is a modern, feature-rich, and privacy-focused personal finance desktop application built with Python.

Designed to make personal money management easier, it provides a complete financial workspace where users can track income, manage expenses, create monthly budgets, monitor savings goals, analyze spending habits, and generate professional financial reports.

With a beautiful graphical interface and a local-first architecture, all financial information stays securely on your computer inside a single SQLite database.

<blockquote>
  🔒 **Your Money. Your Data. Your Privacy.**

  No cloud accounts, no external financial servers, and no mandatory internet connection.
</blockquote>

<badge>Version 1.0.0 — All Six Development Phases Completed</badge>

## 🚀 Key Features

| Module | Features |
|---|---|
| 📊 Dashboard | Financial overview, KPI cards, income vs expenses, spending charts, recent transactions |
| 💳 Transactions | Add, edit, delete, search, filter, sort, and export transactions |
| 🏷️ Categories | Custom categories, colours, icons, and spending summaries |
| 🎯 Budgets | Monthly budgets, category limits, spending alerts, and progress tracking |
| 💰 Savings Goals | Create goals, track contributions, withdrawals, and completion progress |
| 📈 Analytics | Spending trends, income analysis, category breakdowns, and financial insights |
| 📄 Reports | Monthly and yearly reports, CSV exports, and professional PDF statements |
| ⚙️ Settings | Themes, currency, date format, database backup, restore, and optimisation |

## 🎨 Modern Dashboard

Get a complete picture of your financial situation from one place.

- Total income and expenses
- Current balance overview
- Monthly financial summaries
- Income vs expense visualisation
- Expense distribution donut chart
- Spending trend analysis
- Budget utilisation
- Savings goal progress
- Recent transaction history

## 📊 Advanced Financial Analytics

Understand your financial habits with interactive visual analytics.

- Income and expense comparisons
- Expense distribution by category
- Monthly savings trends
- Daily spending activity
- Income source analysis
- Budget utilisation analysis
- Custom date-range analytics
- Automatic financial insights

## 🛡️ Privacy & Data Security

ZaBir FinanceFlow follows a local-first approach.

- All financial records are stored locally.
- SQLite3 provides reliable database management.
- Automatic backup on application exit.
- Manual database backup and restore.
- Database integrity validation before restoration.
- Automatic safety backup before restoring.
- Invalid backups never replace the active database.

**Your financial information remains under your control.**

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Core programming language |
| Tkinter | Desktop graphical interface |
| Pillow | Image processing and UI assets |
| SQLite3 | Local database management |
| Matplotlib | Charts and financial visualisation |
| ReportLab | Professional PDF report generation |
| CSV | Financial data export |
| Unittest | Automated testing |

## 📋 System Requirements

- Windows 10 / Windows 11
- Python 3.11 or later
- Visual Studio Code (recommended)
- Python extension for VS Code
- Internet connection for initial dependency installation only

**Important:** During Python installation, make sure the **Tcl/Tk and IDLE** feature is enabled.

## ⚡ Installation & Setup

### 1. Clone the Repository

```bash
git clone YOUR_REPOSITORY_URL
```

### 2. Navigate to the Project

```bash
cd ZaBir_FinanceFlow
```

### 3. Create a Virtual Environment

```bash
python -m venv .venv
```

### 4. Activate the Environment

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Launch the Application

```bash
python main.py
```

🎉 **That's it! ZaBir FinanceFlow is ready to use.**

## 🧪 Testing

Run the automated test suite:

```bash
python -m unittest discover -s tests -v
```

The tests cover:

- Database operations
- Input validation
- Transaction management
- Categories and filtering
- Budget management
- Savings goals
- Financial reports
- CSV and PDF exports
- Backup and restore
- UI page and dialog smoke tests

## 🗂️ Project Structure

```text
ZaBir_FinanceFlow/
│
├── main.py
├── config.py
├── requirements.txt
├── seed_demo.py
├── README.md
│
├── database/
│   ├── schema.py
│   └── db_manager.py
│
├── core/
│   ├── finance_manager.py
│   ├── category_manager.py
│   ├── budget_manager.py
│   ├── savings_manager.py
│   ├── report_manager.py
│   └── context.py
│
├── ui/
│   ├── main_window.py
│   ├── sidebar.py
│   ├── topbar.py
│   ├── theme.py
│   ├── components.py
│   ├── dialogs.py
│   ├── charts.py
│   └── pages/
│
├── utils/
│   ├── helpers.py
│   ├── validators.py
│   ├── image_manager.py
│   └── export_manager.py
│
├── tests/
│   ├── test_core.py
│   └── test_ui_smoke.py
│
├── assets/
│   ├── icons/
│   ├── images/
│   └── fonts/
│
├── data/
│   ├── finance.db
│   └── app.log
│
└── exports/
    └── backups/
```

## 💡 Important Design Decisions

**1. Accurate Financial Calculations**

Money is stored as integer minor units (poisha/cents), avoiding floating-point precision problems.

**2. Currency Support**

Default currency: Bangladeshi Taka (BDT ৳).

Also supports USD, EUR, GBP, and INR for display purposes. Currency conversion is not performed.

**3. Professional PDF Reports**

PDF reports include financial summaries, charts, page numbers, headers, and footers.

**4. Safe Database Restoration**

Every restore operation validates the selected database and creates a safety backup before replacing the active database.

## 🧰 Troubleshooting

| Problem | Solution |
|---|---|
| `No module named tkinter` | Reinstall Python with Tcl/Tk enabled |
| `No module named PIL` | Run `pip install Pillow` |
| `No module named matplotlib` | Run `pip install matplotlib` |
| `No module named reportlab` | Run `pip install reportlab` |
| Application error | Check `data/app.log` |
| Reset application data | Close the app and delete `data/finance.db` |
| Restore previous data | Open Settings → Restore from Backup |

## 👨‍💻 Developer

**ZaBir Hasan**

Python Developer | Desktop Application Developer | Data Analytics Enthusiast

🌐 **Website:** https://www.zabirhasan.com

## ⭐ Support the Project

If you find **ZaBir FinanceFlow** useful:

- ⭐ Give this repository a star.
- 🍴 Fork the project.
- 🐛 Report bugs and issues.
- 💡 Suggest new features.
- 📢 Share it with others.

Your support helps make the project better!

---

<p align="center">

  **ZaBir FinanceFlow**

  *Manage Smarter. Save Better. Live Financially Stronger.*

  Made with ❤️ using Python

  © 2026 ZaBir Hasan

</p>
