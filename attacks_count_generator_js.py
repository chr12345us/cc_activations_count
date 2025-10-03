#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate attacks count report from CSV files over the past 6 months.

This script reads CSV files from ./input folder with format database_EA_mm_yyyy.csv
for the past 6 months and creates an Excel report with two worksheets:
1. Total attack counts per device per month
2. Filtered attack counts (excluding specific attack names) per device per month

Output: attacks_count_pd_mm_yyyy.xlsx in ./output folder
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import json
import configparser

# ---------------------------------------------------------------------
# Load configuration from config.ini
def load_config():
    """Load configuration from config.ini file."""
    config = configparser.ConfigParser()
    config_file = Path("config.ini")
    
    if not config_file.exists():
        print("ERROR: config.ini file not found. Please create it with required settings.")
        sys.exit(1)
    
    config.read(config_file)
    return config

def get_device_name_mapping(config):
    """Get device name mapping from config file."""
    device_mapping = {}
    if 'DEVICE_NAMES' in config:
        for key, value in config['DEVICE_NAMES'].items():
            if key.strip() and value.strip():
                # Strip quotes and whitespace from both key and value
                clean_key = key.strip().strip('"\'')
                clean_value = value.strip().strip('"\'')
                device_mapping[clean_key] = clean_value
    return device_mapping

def update_device_names_in_config(devices_found):
    """Update config.ini with discovered devices if not already present."""
    config = configparser.ConfigParser()
    config.read("config.ini")
    
    # Ensure DEVICE_NAMES section exists
    if 'DEVICE_NAMES' not in config:
        config.add_section('DEVICE_NAMES')
    
    # Check existing mappings
    existing_devices = set(config['DEVICE_NAMES'].keys())
    new_devices = set(devices_found) - existing_devices
    
    if new_devices:
        print(f"\\nFound new devices, adding to config.ini: {', '.join(new_devices)}")
        for device in new_devices:
            # Add device with same name as default (user can edit manually)
            config.set('DEVICE_NAMES', device, device)
        
        # Write back to config file
        with open("config.ini", 'w') as f:
            config.write(f)
        
        print("NOTE: Edit config.ini [DEVICE_NAMES] section to customize device names.")

def apply_device_name_mapping(df, device_mapping):
    """Replace device IPs with friendly names if mapping exists."""
    if df.empty or 'Device Name' not in df.columns:
        return df
    
    df_copy = df.copy()
    if device_mapping:
        print(f"Applying device name mappings: {len(device_mapping)} devices")
        df_copy['Device Name'] = df_copy['Device Name'].map(device_mapping).fillna(df_copy['Device Name'])
    
    return df_copy

# Load configuration
config = load_config()
cur_month = config.get('GENERAL', 'cur_month')
EXCLUDED_ATTACK_NAMES = [name.strip() for name in config.get('FILTERS', 'excluded_attack_names').split(',') if name.strip()]
CSV_FILE_PREFIX = config.get('GENERAL', 'csv_file_prefix')
CSV_FILE_SUFFIX = config.get('GENERAL', 'csv_file_suffix')
device_mapping = get_device_name_mapping(config)
# ---------------------------------------------------------------------

def get_past_6_months():
    """Get list of (month, year) tuples for the past 6 months excluding current month."""
    # Parse cur_month to get the reference date
    month_str, year_str = cur_month.split('-')
    reference_date = datetime(int(year_str), int(month_str), 1)
    
    months = []
    
    for i in range(1, 7):  # Start from 1 to exclude current month, go back 6 months
        # Go back i months from reference date
        target_date = reference_date - relativedelta(months=i)
        months.append((target_date.month, target_date.year))
    
    # Reverse to get chronological order (oldest to newest)
    return list(reversed(months))

def format_month_year(month, year):
    """Format month and year for file naming (mm_yyyy format)."""
    return f"{month:02d}_{year}"

def get_csv_filename(month, year):
    """Generate CSV filename for given month and year."""
    return f"{CSV_FILE_PREFIX}{format_month_year(month, year)}{CSV_FILE_SUFFIX}"

def load_csv_data(input_dir, month, year):
    """Load CSV data for specific month and year."""
    csv_file = input_dir / get_csv_filename(month, year)
    
    if not csv_file.exists():
        print(f"WARNING: CSV file not found: {csv_file.name}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(csv_file)
        print(f"Loaded: {csv_file.name} ({len(df)} rows)")
        return df
    except Exception as e:
        print(f"ERROR: Failed to read {csv_file.name}: {e}")
        return pd.DataFrame()

def count_attacks_per_device(df, month_year_label):
    """Count attacks per device for a given dataframe."""
    if df.empty:
        return pd.DataFrame()
    
    if 'Device Name' not in df.columns:
        print(f"WARNING: 'Device Name' column not found in data")
        return pd.DataFrame()
    
    # Count rows per device
    device_counts = df.groupby('Device Name').size().reset_index(name=month_year_label)
    return device_counts

def count_attacks_per_device_filtered(df, month_year_label, excluded_attacks):
    """Count attacks per device excluding specific attack names."""
    if df.empty:
        return pd.DataFrame()
    
    if 'Device Name' not in df.columns:
        print(f"WARNING: 'Device Name' column not found in data")
        return pd.DataFrame()
    
    if 'Attack Name' not in df.columns:
        print(f"WARNING: 'Attack Name' column not found in data")
        return df.groupby('Device Name').size().reset_index(name=month_year_label)
    
    # Filter out excluded attack names
    filtered_df = df[~df['Attack Name'].isin(excluded_attacks)]
    
    # Count rows per device
    device_counts = filtered_df.groupby('Device Name').size().reset_index(name=month_year_label)
    return device_counts

def merge_monthly_counts(monthly_dataframes):
    """Merge monthly count dataframes into a single dataframe."""
    if not monthly_dataframes:
        return pd.DataFrame()
    
    # Start with the first dataframe
    result_df = monthly_dataframes[0].copy()
    
    # Merge with subsequent dataframes
    for df in monthly_dataframes[1:]:
        if not df.empty:
            result_df = pd.merge(result_df, df, on='Device Name', how='outer')
    
    # Fill NaN values with 0
    result_df = result_df.fillna(0)
    
    # Sort by Device Name
    result_df = result_df.sort_values('Device Name')
    
    return result_df

def create_excel_report(output_file, total_counts_df, filtered_counts_df):
    """Create Excel file with two worksheets."""
    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        # Write total counts worksheet
        total_counts_df.to_excel(writer, sheet_name='Total Attacks Count', index=False)
        
        # Write filtered counts worksheet  
        filtered_counts_df.to_excel(writer, sheet_name='Filtered Attacks Count', index=False)
        
        # Get workbook and worksheets for formatting
        workbook = writer.book
        worksheet1 = writer.sheets['Total Attacks Count']
        worksheet2 = writer.sheets['Filtered Attacks Count']
        
        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#D7E4BC',
            'border': 1
        })
        
        # Format headers
        for worksheet in [worksheet1, worksheet2]:
            if len(total_counts_df.columns) > 0:
                for col_num, value in enumerate(total_counts_df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                    # Auto-adjust column width
                    worksheet.set_column(col_num, col_num, max(len(str(value)) + 2, 12))

def create_html_graphs(total_counts_df, filtered_counts_df, output_file_html):
    """Create interactive HTML file with two graphs using Google Charts."""
    
    if total_counts_df.empty:
        print("No data available for HTML graphs.")
        return
    
    # Prepare data for Google Charts
    devices = total_counts_df['Device Name'].tolist()
    months = [col for col in total_counts_df.columns if col != 'Device Name']
    
    # Build Google Charts data array with annotations
    # Header: ['Month', 'Device1', 'Device1 Annotation', 'Device2', 'Device2 Annotation', ...]
    total_header = ['Month']
    for device in devices:
        total_header.append(device)
        total_header.append({'type': 'string', 'role': 'annotation'})
    
    # Data rows
    total_data_rows = []
    for month in months:
        row = [month]
        for device in devices:
            value = total_counts_df.loc[total_counts_df['Device Name'] == device, month].values
            val = int(value[0]) if len(value) > 0 else 0
            row.append(val)
            row.append(str(val) if val > 0 else '')  # Annotation
        total_data_rows.append(row)
    
    # Same for filtered data
    filtered_header = ['Month']
    for device in devices:
        filtered_header.append(device)
        filtered_header.append({'type': 'string', 'role': 'annotation'})
    
    filtered_data_rows = []
    for month in months:
        row = [month]
        for device in devices:
            value = filtered_counts_df.loc[filtered_counts_df['Device Name'] == device, month].values
            val = int(value[0]) if len(value) > 0 else 0
            row.append(val)
            row.append(str(val) if val > 0 else '')  # Annotation
        filtered_data_rows.append(row)
    
    # Calculate max values for Y-axis with 25% extra space
    total_max_value = 0
    for row in total_data_rows:
        numeric_values = [val for val in row[1::2] if isinstance(val, (int, float))]  # Every other value (skip annotations)
        if numeric_values:
            total_max_value = max(total_max_value, max(numeric_values))
    
    total_chart_max = int(total_max_value * 1.25) if total_max_value > 0 else 100
    
    filtered_max_value = 0
    for row in filtered_data_rows:
        numeric_values = [val for val in row[1::2] if isinstance(val, (int, float))]  # Every other value (skip annotations)
        if numeric_values:
            filtered_max_value = max(filtered_max_value, max(numeric_values))
    
    filtered_chart_max = int(filtered_max_value * 1.25) if filtered_max_value > 0 else 100
    
    # Generate colors for devices (dark blue to light blue gradient)
    def generate_device_colors(num_devices):
        """Generate colors from dark blue (first) to light blue (last) with interpolation."""
        if num_devices == 1:
            return ['#3366CC']  # RGB(51,102,204) for single device
        elif num_devices == 2:
            return ['#3366CC', '#a8cdf0']  # RGB(51,102,204) and light blue
        else:
            colors = []
            for i in range(num_devices):
                # Interpolate between RGB(51,102,204) and RGB(168,205,240)
                ratio = i / (num_devices - 1)
                r = int(51 + (168 - 51) * ratio)    # 51 to 168
                g = int(102 + (205 - 102) * ratio)  # 102 to 205
                b = int(204 + (240 - 204) * ratio)  # 204 to 240
                colors.append(f'#{r:02X}{g:02X}{b:02X}')
            return colors
    
    colors = generate_device_colors(len(devices))

    # HTML template with Google Charts
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Attacks Count Report - Interactive Graphs</title>
    <script type="text/javascript" src="https://www.gstatic.com/charts/loader.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
        }}
        .controls {{
            margin: 20px 0;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
            border: 1px solid #dee2e6;
        }}
        .controls h3 {{
            margin: 0 0 15px 0;
            color: #495057;
        }}
        .device-checkboxes {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin: 10px 0;
        }}
        .device-checkbox {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .device-checkbox input[type="checkbox"] {{
            transform: scale(1.2);
        }}
        .device-checkbox label {{
            font-weight: 500;
            cursor: pointer;
        }}
        .chart-section {{
            margin: 30px 0;
            padding: 20px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .chart-container {{
            position: relative;
            height: 450px;
            margin: 20px 0;
        }}
        .excluded-info {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
            padding: 10px;
            margin: 10px 0;
            font-style: italic;
            color: #856404;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Attacks Count Report</h1>
            <p>Interactive Analysis of Device Attack Patterns</p>
            <p><strong>Period:</strong> {months[0]} to {months[-1]}</p>
        </div>

        <div class="controls">
            <h3>Display Options</h3>
            
            <div class="device-checkboxes">
                <strong>Devices to Show:</strong>
                <button onclick="selectAllDevices()" style="margin-left: 10px; padding: 5px 10px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer;">Select All</button>
                <button onclick="deselectAllDevices()" style="margin-left: 5px; padding: 5px 10px; background: #6c757d; color: white; border: none; border-radius: 3px; cursor: pointer;">Deselect All</button>
            </div>
            <div class="device-checkboxes" id="deviceCheckboxes">
                <!-- Device checkboxes will be populated by JavaScript -->
            </div>
        </div>

        <div class="chart-section">
            <div class="chart-container">
                <div id="totalChart"></div>
            </div>
        </div>

        <div class="chart-section">
            <div class="excluded-info">
                <strong>Note:</strong> This chart excludes attacks of type: {', '.join(EXCLUDED_ATTACK_NAMES)}
            </div>
            <div class="chart-container">
                <div id="filteredChart"></div>
            </div>
        </div>
    </div>

    <script type="text/javascript">
        // Load Google Charts
        google.charts.load('current', {{'packages':['corechart']}});
        google.charts.setOnLoadCallback(initializeCharts);

        // Data from Python
        const devices = {json.dumps(devices)};
        const months = {json.dumps(months)};
        const totalDataArray = {json.dumps([total_header] + total_data_rows)};
        const filteredDataArray = {json.dumps([filtered_header] + filtered_data_rows)};
        const totalChartMax = {total_chart_max};
        const filteredChartMax = {filtered_chart_max};
        const colors = {json.dumps(colors)};

        let totalChart, filteredChart;
        let totalDataTable, filteredDataTable;
        let originalTotalData, originalFilteredData;

        function initializeCharts() {{
            // Create DataTables from arrays
            originalTotalData = google.visualization.arrayToDataTable(totalDataArray);
            originalFilteredData = google.visualization.arrayToDataTable(filteredDataArray);
            
            // Clone for manipulation
            totalDataTable = originalTotalData.clone();
            filteredDataTable = originalFilteredData.clone();

            // Create device checkboxes
            createDeviceCheckboxes();

            // Draw initial charts
            drawCharts();
        }}

        function drawCharts() {{
            // Update data tables with device filtering
            updateDataTables();

            // Total chart options
            const totalOptions = {{
                title: 'Total Attacks Count',
                titleTextStyle: {{
                    fontSize: 18,
                    bold: true
                }},
                hAxis: {{
                    title: 'Month',
                    titleTextStyle: {{ fontSize: 14, bold: true }},
                    textStyle: {{ fontSize: 12 }},
                    slantedText: false
                }},
                vAxis: {{
                    title: 'Number of Attacks',
                    titleTextStyle: {{ fontSize: 14, bold: true }},
                    textStyle: {{ fontSize: 12 }},
                    maxValue: totalChartMax,
                    format: 'decimal'
                }},
                colors: colors,
                legend: {{ 
                    position: 'top',
                    textStyle: {{ fontSize: 12 }}
                }},
                chartArea: {{ 
                    width: '70%', 
                    height: '70%',
                    top: 80,
                    left: 80
                }},
                annotations: {{
                    textStyle: {{
                        fontSize: 12,
                        bold: true,
                        color: '#000000'
                    }},
                    alwaysOutside: true,
                    stem: {{
                        length: 5
                    }}
                }},
                height: 400,
                backgroundColor: 'transparent'
            }};

            // Filtered chart options
            const filteredOptions = {{
                title: 'Filtered Attacks Count',
                titleTextStyle: {{
                    fontSize: 18,
                    bold: true
                }},
                hAxis: {{
                    title: 'Month',
                    titleTextStyle: {{ fontSize: 14, bold: true }},
                    textStyle: {{ fontSize: 12 }},
                    slantedText: false
                }},
                vAxis: {{
                    title: 'Number of Attacks',
                    titleTextStyle: {{ fontSize: 14, bold: true }},
                    textStyle: {{ fontSize: 12 }},
                    maxValue: filteredChartMax,
                    format: 'decimal'
                }},
                colors: colors,
                legend: {{ 
                    position: 'top',
                    textStyle: {{ fontSize: 12 }}
                }},
                chartArea: {{ 
                    width: '70%', 
                    height: '70%',
                    top: 80,
                    left: 80
                }},
                annotations: {{
                    textStyle: {{
                        fontSize: 12,
                        bold: true,
                        color: '#000000'
                    }},
                    alwaysOutside: true,
                    stem: {{
                        length: 5
                    }}
                }},
                height: 400,
                backgroundColor: 'transparent'
            }};

            // Create and draw charts
            totalChart = new google.visualization.ColumnChart(document.getElementById('totalChart'));
            filteredChart = new google.visualization.ColumnChart(document.getElementById('filteredChart'));

            totalChart.draw(totalDataTable, totalOptions);
            filteredChart.draw(filteredDataTable, filteredOptions);
        }}

        function createDeviceCheckboxes() {{
            const container = document.getElementById('deviceCheckboxes');
            devices.forEach((device, index) => {{
                const div = document.createElement('div');
                div.className = 'device-checkbox';
                div.innerHTML = `
                    <input type="checkbox" id="device${{index}}" checked onchange="toggleDevice(${{index}})">
                    <label for="device${{index}}" style="color: ${{colors[index]}}">■ ${{device}}</label>
                `;
                container.appendChild(div);
            }});
        }}

        function toggleDevice(deviceIndex) {{
            updateDataTables();
            drawCharts();
        }}

        function updateDataTables() {{
            // Get which devices are selected
            const selectedDevices = [];
            devices.forEach((device, index) => {{
                const checkbox = document.getElementById(`device${{index}}`);
                if (checkbox.checked) {{
                    // Google Charts with annotations: each device has 2 columns (value + annotation)
                    selectedDevices.push(index * 2 + 1); // +1 because column 0 is months
                    selectedDevices.push(index * 2 + 2); // annotation column
                }}
            }});

            // Create new DataTables with only selected columns
            if (selectedDevices.length === 0) {{
                // If no devices selected, show empty chart with just months
                totalDataTable = new google.visualization.DataTable();
                totalDataTable.addColumn('string', 'Month');
                filteredDataTable = new google.visualization.DataTable();
                filteredDataTable.addColumn('string', 'Month');
                
                for (let i = 1; i < originalTotalData.getNumberOfRows(); i++) {{
                    totalDataTable.addRow([originalTotalData.getValue(i, 0)]);
                    filteredDataTable.addRow([originalFilteredData.getValue(i, 0)]);
                }}
            }} else {{
                // Create new tables with selected columns
                totalDataTable = new google.visualization.DataTable();
                filteredDataTable = new google.visualization.DataTable();
                
                // Add month column
                totalDataTable.addColumn('string', 'Month');
                filteredDataTable.addColumn('string', 'Month');
                
                // Add selected device columns (value + annotation pairs)
                for (let i = 0; i < selectedDevices.length; i += 2) {{
                    const valueColIndex = selectedDevices[i];
                    const annotationColIndex = selectedDevices[i + 1];
                    
                    const deviceName = originalTotalData.getColumnLabel(valueColIndex);
                    totalDataTable.addColumn('number', deviceName);
                    totalDataTable.addColumn(originalTotalData.getColumnType(annotationColIndex), 
                                           originalTotalData.getColumnLabel(annotationColIndex), 
                                           originalTotalData.getColumnId(annotationColIndex));
                    
                    filteredDataTable.addColumn('number', deviceName);
                    filteredDataTable.addColumn(originalFilteredData.getColumnType(annotationColIndex), 
                                              originalFilteredData.getColumnLabel(annotationColIndex), 
                                              originalFilteredData.getColumnId(annotationColIndex));
                }}
                
                // Add data rows
                for (let i = 1; i < originalTotalData.getNumberOfRows(); i++) {{
                    const totalRow = [originalTotalData.getValue(i, 0)];
                    const filteredRow = [originalFilteredData.getValue(i, 0)];
                    
                    for (let j = 0; j < selectedDevices.length; j++) {{
                        const colIndex = selectedDevices[j];
                        totalRow.push(originalTotalData.getValue(i, colIndex));
                        filteredRow.push(originalFilteredData.getValue(i, colIndex));
                    }}
                    
                    totalDataTable.addRow(totalRow);
                    filteredDataTable.addRow(filteredRow);
                }}
            }}
        }}

        function selectAllDevices() {{
            devices.forEach((_, index) => {{
                const checkbox = document.getElementById(`device${{index}}`);
                checkbox.checked = true;
            }});
            updateDataTables();
            drawCharts();
        }}

        function deselectAllDevices() {{
            devices.forEach((_, index) => {{
                const checkbox = document.getElementById(`device${{index}}`);
                checkbox.checked = false;
            }});
            updateDataTables();
            drawCharts();
        }}
    </script>
</body>
</html>
    """
    
    # Write HTML file
    with open(output_file_html, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML graphs saved to: {output_file_html}")

def main():
    """Main function to generate the attacks count report."""
    input_dir = Path("./input")
    output_dir = Path("./output")
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get past 6 months
    months_data = get_past_6_months()
    print(f"Processing data for months: {[format_month_year(m, y) for m, y in months_data]}")
    
    # Load data for each month
    total_monthly_dfs = []
    filtered_monthly_dfs = []
    
    for month, year in months_data:
        month_year_label = f"{month:02d}_{year}"
        print(f"\\nProcessing {month_year_label}...")
        
        # Load CSV data
        df = load_csv_data(input_dir, month, year)
        
        # Count total attacks per device
        total_counts = count_attacks_per_device(df, month_year_label)
        total_monthly_dfs.append(total_counts)
        
        # Count filtered attacks per device
        filtered_counts = count_attacks_per_device_filtered(df, month_year_label, EXCLUDED_ATTACK_NAMES)
        filtered_monthly_dfs.append(filtered_counts)
    
    # Merge monthly counts
    print(f"\\nMerging monthly data...")
    total_merged_df = merge_monthly_counts(total_monthly_dfs)
    filtered_merged_df = merge_monthly_counts(filtered_monthly_dfs)
    
    # Update config.ini with discovered devices
    if not total_merged_df.empty:
        devices_found = total_merged_df['Device Name'].tolist()
        update_device_names_in_config(devices_found)
        
        # Apply device name mapping
        total_merged_df = apply_device_name_mapping(total_merged_df, device_mapping)
        filtered_merged_df = apply_device_name_mapping(filtered_merged_df, device_mapping)
    
    # Generate output filename using the last month of data (most recent month processed)
    if months_data:
        last_month, last_year = months_data[-1]  # Get the last (most recent) month from the list
        output_filename = f"attacks_count_pd_{format_month_year(last_month, last_year)}.xlsx"
    else:
        # Fallback to cur_month if no data processed
        month_str, year_str = cur_month.split('-')
        current_month = int(month_str)
        current_year = int(year_str)
        output_filename = f"attacks_count_pd_{format_month_year(current_month, current_year)}.xlsx"
    
    output_file = output_dir / output_filename
    
    # Create Excel report
    print(f"\\nCreating Excel report: {output_filename}")
    create_excel_report(output_file, total_merged_df, filtered_merged_df)
    
    # Create HTML graphs
    html_filename = output_filename.replace('.xlsx', '.html')
    html_file = output_dir / html_filename
    print(f"\\nCreating HTML graphs: {html_filename}")
    create_html_graphs(total_merged_df, filtered_merged_df, html_file)
    
    # Print summary
    print(f"\\nReport Summary:")
    print(f"- Total devices found: {len(total_merged_df) if not total_merged_df.empty else 0}")
    print(f"- Months processed: {len([df for df in total_monthly_dfs if not df.empty])}/6")
    print(f"- Excluded attack names: {', '.join(EXCLUDED_ATTACK_NAMES)}")
    print(f"- Excel output: {output_file}")
    print(f"- HTML output: {html_file}")
    
    if total_merged_df.empty:
        print("\\nWARNING: No data was processed. Check if CSV files exist and have correct format.")
    else:
        print(f"\\nSample devices: {', '.join(total_merged_df['Device Name'].head(3).tolist())}")

if __name__ == "__main__":
    main()