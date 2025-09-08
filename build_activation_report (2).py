#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build an activations report from a Vision/DFC log.

- Filters ./input/alert.txt by month + activation text.
- Saves ./output/alert-filtered-YYYY-MM.txt.
- Parses Date, Protected Object, attackIpsId (trailing '.' removed).
- Enriches from first CSV in ./input by attackIpsId (if present).
- Writes Excel ./output/activations_report-YYYY-MM.xlsx with:
  * Detail sheet (parsed + enrichment)
  * Summary sheet at B2 as a native Excel Table with a Total row (Table Style Medium 9).
- Prints a 'month completeness' warning if previous/next month are missing in the raw log.
"""

import re
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# ---------------------------------------------------------------------
# Parameters (edit these)
cur_month = "2025-08"
activation_str = "triggered up operation SmartTapDivert-EU1"
# ---------------------------------------------------------------------

# Regexes
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
PO_RE = re.compile(r"protected object\s+([^\.]+)\.", re.IGNORECASE)
# Capture ID plus trailing dot; we slice it off per user's requirement
ATTACK_ID_RE = re.compile(r"Attack Id\s+([^\.]+\.)", re.IGNORECASE)

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
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        print("NOTE: No CSV found in ./input — proceeding without enrichment.")
        return None
    csv_path = csv_files[0]
    try:
        df = pd.read_csv(csv_path)
        print(f"Using CSV: {csv_path.name}")
        # Case-insensitive column normalization
        lower_to_actual = {c.lower(): c for c in df.columns}
        for req in CSV_REQUIRED_COLS:
            if req not in df.columns:
                lr = req.lower()
                if lr in lower_to_actual and lower_to_actual[lr] != req:
                    df.rename(columns={lower_to_actual[lr]: req}, inplace=True)
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
        attack_id = m_attack.group(1).strip()[:-1] if m_attack else None  # remove trailing '.'
        records.append({
            "Date": date_str,
            "Protected Object": protected_obj,
            "attackIpsId": attack_id
        })

    detail_df = pd.DataFrame(records)

    # Enrich from CSV
    csv_df = load_first_csv(Path("./input"))
    if csv_df is not None and not detail_df.empty and "attackIpsId" in detail_df.columns:
        keep_cols = [c for c in CSV_REQUIRED_COLS if c in csv_df.columns]
        if keep_cols and "attackIpsId" in keep_cols:
            csv_trim = csv_df[keep_cols].drop_duplicates(subset=["attackIpsId"])
            detail_df = detail_df.merge(csv_trim, on="attackIpsId", how="left")

    # Summary
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

    # Write Excel (Detail + Summary as a native table with totals)
    with pd.ExcelWriter(xlsx_out, engine="xlsxwriter") as writer:
        # Detail sheet
        detail_df.to_excel(writer, sheet_name="Detail", index=False)

        # Summary sheet starting at B2
        summary_df.to_excel(writer, sheet_name="Summary", index=False, startrow=1, startcol=1)
        wb = writer.book
        ws = writer.sheets["Summary"]

        header_row = 1           # B2/C2
        first_col, last_col = 1, 2
        n = len(summary_df)

        # Define table range including a totals row even when n=0
        if n > 0:
            last_row = header_row + n + 1  # header + n data + totals
        else:
            last_row = header_row + 1      # header + totals only

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
