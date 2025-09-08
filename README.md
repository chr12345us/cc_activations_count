## Project
Activations Report Builder

Generate a filtered text log and a polished Excel report (with a banded “Summary” table and totals) from Vision/DFC alert logs, optionally enriched from a CSV by `attackIpsId`.

## Version
Current version: **1.0.0**

### Changelog
- v1.0.0 - Initial release


## Required files:
1. alert.log - this is the file that is in thge "logs" folder in the "Support File" from CC+
2. the "Database" file from the monthjly report, a csv file that has all the attacks with details for the month.

Place these two files in the ./input folder

## 🧭 What it does

1. **Filter** the raw log (`./input/alert.txt`) by:
   - month prefix (`YYYY-MM`, e.g., `2025-08`), and
   - an activation substring (e.g., `triggered up operation SmartTapDivert-EU1`).
2. **Save** the filtered lines to `./output/alert-filtered-YYYY-MM.txt`.
3. **Parse** each filtered line:
   - `Date` → e.g., `2025-08-02` (must be at the **start** of the line)
   - `Protected Object` → text after `protected object ` and before the next `.`
   - `attackIpsId` → text after `Attack Id `; trailing period `.` is removed.
4. **Enrich** with CSV columns by joining on `attackIpsId` (first `*.csv` in `./input`):
   - `Attack Name`, `packetCount`, `category`, `maxAttackPacketRatePps`, `maxAttackRateBps`
5. **Write Excel** (`./output/activations_report-YYYY-MM.xlsx`) with:
   - **Detail** sheet: all parsed rows + enrichment columns
   - **Summary** sheet: starts at **B2**, shows `Date` and `Number of Activations`, as a **native Excel Table** (blue banded, with a **Total** row)

The script also **prints a warning** if there are no log lines in the **previous** or **next** month (month completeness check).

---

## 📁 Project structure

```
.
├─ build_activation_report.py
├─ input/
│  ├─ alert.txt           # required
│  └─ *.csv               # optional (enrichment by attackIpsId)
└─ output/
   ├─ alert-filtered-YYYY-MM.txt
   └─ activations_report-YYYY-MM.xlsx
```

---

## ⚙️ Requirements

- Python 3.9+ recommended
- Packages:
  - `pandas`
  - `xlsxwriter` (used by pandas’ ExcelWriter)

Install:

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install pandas xlsxwriter
```

---

## 🔧 Configure

Edit the **top** of `build_activation_report.py`:

```python
# Parameters (edit these, example customized for EA)
cur_month = "2025-08"
activation_str = "triggered up operation SmartTapDivert-EU1"
```

Place your input files:

- `./input/alert.txt` (required)
- `./input/<something>.csv` (optional; first CSV found is used for enrichment)

> **CSV required columns** (case-insensitive; rename is auto-normalized if cases differ):
> - `attackIpsId` (join key)
> - `Attack Name`
> - `packetCount`
> - `category`
> - `maxAttackPacketRatePps`
> - `maxAttackRateBps`

---

## ▶️ Run

```bash
python build_activation_report.py
```

Outputs:

- `./output/alert-filtered-YYYY-MM.txt`
- `./output/activations_report-YYYY-MM.xlsx`

---

## 🧩 Log line expectations

Each line that will be considered must:

- **Start with** `YYYY-MM-DD`, e.g., `2025-08-02 ...`
- Contain your **activation string**, e.g., `triggered up operation SmartTapDivert-EU1`
- Include:
  - `protected object <NAME>.` → protected object name is captured **before** the dot
  - `Attack Id <ID>.` → the ID is captured and the trailing dot is **removed** before joining CSV

**Example:**

```
2025-08-02 03:14:07 UTC ... triggered up operation SmartTapDivert-EU1 ... protected object EA-Login-Prod. ... Attack Id 12345-XYZ.
```

Parsed:
- Date: `2025-08-02`
- Protected Object: `EA-Login-Prod`
- attackIpsId: `12345-XYZ`

---

## 📊 Excel output details

**Detail** sheet
- Columns: `Date`, `Protected Object`, `attackIpsId`, and any enrichment columns present in the CSV.

**Summary** sheet
- Starts at **B2** (Excel cell B2).
- Converted into a **native Excel Table** with style **“Table Style Medium 9”** (dark-blue header, light-blue banded rows).
- Includes a **Totals row** that sums the `Number of Activations`.

> We use Excel’s built-in table totals (no manual border hacks), which play nicely with banded rows and theme colors.

---

## 🔍 Month completeness warning

The script checks the raw log for any lines that start with:
- the **previous** month (`YYYY-MM-`) and
- the **next** month

If either is missing, it prints:

```
WARNING: No events found for previous month (YYYY-MM) and/or next month (YYYY-MM)
```

This helps catch truncated inputs.

---

## ❗ Troubleshooting

- **No CSV data appears in Excel**  
  Ensure the CSV has a column named `attackIpsId` that matches the IDs parsed from the log (remember: the script strips the trailing `.` from `Attack Id` in the log).

- **No rows in Summary**  
  Check that:
  - `cur_month` matches dates at the **start** of the log lines (`YYYY-MM-`),
  - `activation_str` matches exactly (case-sensitive substring match).

- **Multiple CSVs**  
  The script picks the **first** `*.csv` in `./input` (alphabetically). If needed, rename or adjust the script to target a specific filename/pattern.

- **Table styling**  
  We use a native Excel table for banding and totals. If you want a different blue theme, change the table `style` to another *Medium* style (e.g., `"Table Style Medium 10"`).
