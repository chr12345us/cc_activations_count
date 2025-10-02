# Attacks Count Generator

This script (`attacks_count_generator.py`) generates monthly attack count reports from CSV files.

## Purpose

Reads CSV files from the past 6 months and creates an Excel report showing attack counts per device per month, with both total counts and filtered counts (excluding specific attack types).

## Input

- CSV files in `./input/` folder with naming pattern: `database_EA_mm_yyyy.csv`
- Files should contain columns: `Device Name`, `Attack Name`

## Output

- Excel file in `./output/` folder named: `attacks_count_pd_mm_yyyy.xlsx`
- Contains two worksheets:
  1. **Total Attacks Count**: All attacks per device per month
  2. **Filtered Attacks Count**: Attacks excluding specified attack names

## Configuration

The script uses a `config.ini` file for all configuration settings:

```ini
[GENERAL]
cur_month = 10-2025
csv_file_prefix = database_EA_
csv_file_suffix = .csv

[FILTERS]
excluded_attack_names = Memcached-Server-Reflect

[DEVICE_NAMES]
10.74.224.50 = EU-Gateway-Primary
10.76.4.241 = EU-Gateway-Secondary
```

### Device Name Mapping
- After first run, the script automatically populates `[DEVICE_NAMES]` section with discovered devices
- Edit the config.ini to replace IP addresses with friendly names
- Second run will use the friendly names in reports and graphs

## Usage

```bash
python attacks_count_generator.py
```

## Requirements

- pandas
- python-dateutil  
- xlsxwriter
- openpyxl

Install with: `pip install pandas python-dateutil xlsxwriter openpyxl`

## Output Format

The Excel file contains:
- **Columns**: Device Name + one column per month (mm_yyyy format)
- **Rows**: One row per device found in the data
- **Values**: Count of attacks/events for that device in that month

## Example Output Structure

| Device Name   | 05_2025 | 06_2025 | 07_2025 | 08_2025 | 09_2025 |
|---------------|---------|---------|---------|---------|---------|
| 10.74.224.50  | 105748  | 110340  | 131346  | 118912  | 69347   |
| 10.76.4.241   | 1532    | 1568    | 1759    | 1613    | 884     |

## Notes

- Script processes the past 6 months from current date
- Missing CSV files for a month will show warnings but won't stop execution
- Devices with 0 attacks in a month will show 0 in the output
- Output filename uses current month/year regardless of data processed