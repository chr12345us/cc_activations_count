#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build an activations report from a Vision/DFC log.

Configuration:
- Parameters are read from config.ini file
- cur_month: Target month in MM-YYYY format (converted internally to YYYY-MM)
- activation_str: Text string to filter activation events
- csv_file_prefix/suffix: Pattern for CSV file matching

Steps:
1) Filter lines by month prefix (YYYY-MM) and activation text.
2) Save filtered lines to ./output/alert-filtered-YYYY-MM.txt.
3) Parse Date, Protected Object, attackIpsId (from text).
4) Enrich with CSV columns by matching attackIpsId (from ./input/*.csv).
5) Excel output: Detail, Summary, Pivot (with Total line).
6) Print a warning if no log lines exist for previous or next month.

Assumptions for CSV columns:
- attackIpsId (join key)
- Attack Name
- packetCount
- category
- maxAttackPacketRatePps
- maxAttackRateBps
"""

import re
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import configparser

# Load configuration
config = configparser.ConfigParser()
config_file = Path("config.ini")
if not config_file.exists():
    sys.exit(f"ERROR: Configuration file not found: {config_file}")
config.read(config_file)

# Get parameters from config
cur_month_config = config.get('GENERAL', 'cur_month')
activation_str = config.get('GENERAL', 'activation_str')
csv_file_prefix = config.get('GENERAL', 'csv_file_prefix', fallback='database_EA_')
csv_file_suffix = config.get('GENERAL', 'csv_file_suffix', fallback='.csv')

# Convert mm-yyyy format to yyyy-mm for internal processing
if '-' in cur_month_config:
    month_part, year_part = cur_month_config.split('-')
    cur_month = f"{year_part}-{month_part.zfill(2)}"
else:
    cur_month = cur_month_config

# Regexes for parsing the text lines
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
PO_RE = re.compile(r"protected object\s+([^\.]+)\.", re.IGNORECASE)
ATTACK_ID_RE = re.compile(r"Attack Id\s+([A-Za-z0-9._:-]+)")  # allow common id chars

CSV_REQUIRED_COLS = [
    "attackIpsId",
    "Attack Name",
    "packetCount",
    "category",
    "maxAttackPacketRatePps",
    "maxAttackRateBps",
]

def prev_next_month(ym: str):
    dt = datetime.strptime(ym + "-01", "%Y-%m-%d")
    prev = f"{dt.year-1}-12" if dt.month == 1 else f"{dt.year:04d}-{dt.month-1:02d}"
    nxt  = f"{dt.year+1}-01" if dt.month == 12 else f"{dt.year:04d}-{dt.month+1:02d}"
    return prev, nxt

def load_first_csv(input_dir: Path) -> pd.DataFrame | None:
    # Try to find CSV file matching the current month pattern
    # Convert from YYYY-MM to MM_YYYY format for file matching
    year, month = cur_month.split('-')
    month_pattern = f"{csv_file_prefix}{month}_{year}{csv_file_suffix}"
    csv_files = sorted(input_dir.glob(month_pattern))
    
    # If no month-specific file found, fall back to any CSV file
    if not csv_files:
        csv_files = sorted(input_dir.glob("*.csv"))
        
    if not csv_files:
        print("NOTE: No CSV found in ./input — proceeding without enrichment.")
        return None
    csv_path = csv_files[0]
    try:
        df = pd.read_csv(csv_path, low_memory=False)
        print(f"Using CSV: {csv_path.name}")
        # Normalize column names to exact expected ones if case differs
        colmap = {c.lower(): c for c in df.columns}
        # Try to map required columns case-insensitively
        for req in CSV_REQUIRED_COLS:
            if req not in df.columns:
                # find case-insensitive match
                lower_req = req.lower()
                if lower_req in colmap and colmap[lower_req] != req:
                    df.rename(columns={colmap[lower_req]: req}, inplace=True)
        # Check presence (non-fatal; we'll just merge what exists)
        missing = [c for c in CSV_REQUIRED_COLS if c not in df.columns]
        if missing:
            print(f"WARNING: CSV missing expected columns: {missing}. Merge will include available columns only.")
        return df
    except Exception as e:
        print(f"WARNING: Failed to read CSV ({csv_path.name}): {e}. Proceeding without enrichment.")
        return None

def main():
    input_file = Path("./input/alert.txt")
    if not input_file.exists():
        sys.exit(f"ERROR: input file not found: {input_file}")

    output_dir = Path("./output")
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_out = output_dir / f"alert-filtered-{cur_month}.txt"
    xlsx_out = output_dir / f"activations_report-{cur_month}.xlsx"

    with input_file.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Filter by month + activation
    prefix = cur_month + "-"
    month_lines = [ln for ln in lines if ln.startswith(prefix)]
    filtered_lines = [ln for ln in month_lines if activation_str in ln]

    # Save filtered text
    with txt_out.open("w", encoding="utf-8") as f:
        f.writelines(filtered_lines)

    # Parse Detail fields: Date, Protected Object, attackIpsId
    records = []
    for ln in filtered_lines:
        m_date = DATE_RE.search(ln)
        if not m_date:
            continue
        date_str = m_date.group(1)
        m_po = PO_RE.search(ln)
        protected_obj = m_po.group(1).strip() if m_po else None
        m_attack = ATTACK_ID_RE.search(ln)
        attack_id = m_attack.group(1).strip()[:-1] if m_attack else None
        records.append({
            "Date": date_str,
            "Protected Object": protected_obj,
            "attackIpsId": attack_id
        })

    detail_df = pd.DataFrame(records)

    # Load CSV and enrich by attackIpsId (left join)
    csv_df = load_first_csv(Path("./input"))
    if csv_df is not None and not detail_df.empty and "attackIpsId" in detail_df.columns:
        # Only keep columns we care about (when present)
        keep_cols = [c for c in CSV_REQUIRED_COLS if c in csv_df.columns]
        csv_trim = csv_df[keep_cols].drop_duplicates(subset=["attackIpsId"]) if "attackIpsId" in keep_cols else None
        if csv_trim is not None:
            detail_df = detail_df.merge(csv_trim, on="attackIpsId", how="left")

    # Summary: count lines per date
    if not detail_df.empty:
        summary_df = (
            detail_df.groupby("Date")
            .size()
            .reset_index(name="Number of Activations")
            .sort_values("Date")
        )
    else:
        summary_df = pd.DataFrame(columns=["Date", "Number of Activations"])

    # Month completeness check
    prev_m, next_m = prev_next_month(cur_month)
    prev_has = any(ln.startswith(prev_m + "-") for ln in lines)
    next_has = any(ln.startswith(next_m + "-") for ln in lines)
    if not prev_has or not next_has:
        missing = []
        if not prev_has: missing.append(f"previous month ({prev_m})")
        if not next_has: missing.append(f"next month ({next_m})")
        print("WARNING: No events found for " + " and ".join(missing))

    # Write Excel with 3 sheets; add Pivot "Total" row
    with pd.ExcelWriter(xlsx_out, engine="xlsxwriter") as writer:
        # Detail (unchanged)
        detail_df.to_excel(writer, sheet_name="Detail", index=False)

        # Summary at B2 (row=1, col=1 0-based)
        summary_df.to_excel(writer, sheet_name="Summary", index=False, startrow=1, startcol=1)

        wb = writer.book
        ws = writer.sheets["Summary"]

        # Table range (include header row + data rows + 1 extra row for Total)
        header_row = 1              # B2/C2
        first_col, last_col = 1, 2  # B..C
        n = len(summary_df)
        # If there are N data rows, last row for a table with a total row is header_row + N + 1
        last_row = header_row + (n if n > 0 else 0) + 1

        # Turn the Summary block into a standard Excel table with totals
        # "Table Style Medium 9" = blue header + banded light blue rows
        ws.add_table(header_row, first_col, last_row, last_col, {
            "style": "Table Style Medium 9",
            "total_row": True,
            "columns": [
                {"header": "Date", "total_string": "Total"},
                {"header": "Number of Activations", "total_function": "sum"},
            ],
        })
    
    print(f"Filtered text saved to: {txt_out}")
    print(f"Excel report saved to: {xlsx_out}")

if __name__ == "__main__":
    main()
