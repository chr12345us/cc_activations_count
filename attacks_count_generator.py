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
    """Create interactive HTML file with two graphs based on the Excel data."""
    
    if total_counts_df.empty:
        print("No data available for HTML graphs.")
        return
    
    # Prepare data for JavaScript
    devices = total_counts_df['Device Name'].tolist()
    months = [col for col in total_counts_df.columns if col != 'Device Name']
    
    # Prepare total counts data
    total_data = []
    for _, row in total_counts_df.iterrows():
        device_name = row['Device Name']
        values = [int(row[month]) for month in months]
        total_data.append({
            'name': device_name,
            'data': values
        })
    
    # Prepare filtered counts data
    filtered_data = []
    for _, row in filtered_counts_df.iterrows():
        device_name = row['Device Name']
        values = [int(row[month]) for month in months]
        filtered_data.append({
            'name': device_name,
            'data': values
        })
    
    # Calculate max values for Y-axis with 15% extra space
    total_max_value = max(max(device['data']) for device in total_data)
    total_chart_max = int(total_max_value * 1.15)
    
    filtered_max_value = max(max(device['data']) for device in filtered_data)
    filtered_chart_max = int(filtered_max_value * 1.15)
    

    
    # Generate colors for devices (blue to red gradient)
    def generate_device_colors(num_devices):
        """Generate colors from blue (first) to red (last) with interpolation."""
        if num_devices == 1:
            return ['#0066CC']  # Blue for single device
        elif num_devices == 2:
            return ['#0066CC', '#CC0000']  # Blue and Red
        else:
            colors = []
            for i in range(num_devices):
                # Interpolate between blue (0,102,204) and red (204,0,0)
                ratio = i / (num_devices - 1)
                r = int(0 + (204 - 0) * ratio)      # 0 to 204
                g = int(102 * (1 - ratio))           # 102 to 0
                b = int(204 * (1 - ratio))           # 204 to 0
                colors.append(f'#{r:02X}{g:02X}{b:02X}')
            return colors
    
    colors = generate_device_colors(len(devices))

    # HTML template with Chart.js
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Attacks Count Report - Interactive Graphs</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2"></script>
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
        .stack-options {{
            margin: 15px 0;
            display: flex;
            gap: 20px;
        }}
        .stack-option {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .stack-option input[type="radio"] {{
            transform: scale(1.2);
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

            <div class="stack-options">
                <strong>Chart Type:</strong>
                <div class="stack-option">
                    <input type="radio" id="unstacked" name="stackType" value="unstacked" checked>
                    <label for="unstacked">Unstacked (Side by Side)</label>
                </div>
                <div class="stack-option">
                    <input type="radio" id="stacked" name="stackType" value="stacked">
                    <label for="stacked">Stacked</label>
                </div>
            </div>
        </div>

        <div class="chart-section">
            <div class="chart-container">
                <canvas id="totalChart"></canvas>
            </div>
        </div>

        <div class="chart-section">
            <div class="excluded-info">
                <strong>Note:</strong> This chart excludes attacks of type: {', '.join(EXCLUDED_ATTACK_NAMES)}
            </div>
            <div class="chart-container">
                <canvas id="filteredChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        // Data from Python
        const devices = {json.dumps(devices)};
        const months = {json.dumps(months)};
        const totalData = {json.dumps(total_data)};
        const filteredData = {json.dumps(filtered_data)};
        const totalChartMax = {total_chart_max};
        const filteredChartMax = {filtered_chart_max};
        const colors = {json.dumps(colors)};

        // Chart styling defaults
        const chartDefaults = {{
            axis: {{
                titleColor: '#000000',        // Axis titles (Month, Number of Attacks)
                tickColor: '#666666',         // Axis tick labels (numbers and month names)
                gridColor: 'rgba(0,0,0,0.1)', // Grid lines
                lineColor: 'rgba(0,0,0,0.1)'  // Axis lines
            }},
            font: {{
                titleSize: 14,                // Axis title font size
                tickSize: 12                  // Tick label font size
            }}
        }};

        let totalChart, filteredChart;

        // Initialize charts
        function initializeCharts() {{
            const totalCtx = document.getElementById('totalChart').getContext('2d');
            const filteredCtx = document.getElementById('filteredChart').getContext('2d');

            // Create device checkboxes
            createDeviceCheckboxes();

            // Initialize charts
            totalChart = createChart(totalCtx, totalData, 'Total Attacks Count');
            filteredChart = createChart(filteredCtx, filteredData, 'Filtered Attacks Count');

            // Add event listeners
            addEventListeners();
        }}

        function createChart(ctx, data, label) {{
            // Determine which max value to use based on the label
            const chartMax = label.includes('Total') ? totalChartMax : filteredChartMax;
            
            return new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: months,
                    datasets: data.map((deviceData, index) => ({{
                        label: deviceData.name,
                        data: deviceData.data,
                        backgroundColor: colors[index] + '80', // Add transparency
                        borderColor: colors[index],
                        borderWidth: 2,
                        hidden: false
                    }}))
                }},
                plugins: [ChartDataLabels],
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{
                        mode: 'index',
                        intersect: false,
                    }},
                    plugins: {{
                        title: {{
                            display: true,
                            text: label,
                            font: {{
                                size: 18,
                                weight: 'bold'
                            }},
                            padding: 20
                        }},
                        legend: {{
                            display: true,
                            position: 'top',
                            labels: {{
                                padding: 20
                            }}
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return context.dataset.label + ': ' + context.parsed.y.toLocaleString() + ' attacks';
                                }}
                            }}
                        }},
                        datalabels: {{
                            align: 'top',
                            anchor: 'end',
                            backgroundColor: 'transparent',
                            borderColor: 'transparent',
                            color: function(context) {{
                                return context.dataset.borderColor;
                            }},
                            font: {{
                                weight: 'normal',
                                size: 12
                            }},
                            formatter: function(value, context) {{
                                // Hide labels if dataset is hidden, value is 0, or chart is stacked
                                if (context.dataset.hidden || value === 0) {{
                                    return '';
                                }}
                                
                                // Check if chart is in stacked mode
                                const chart = context.chart;
                                if (chart.options.scales.x.stacked || chart.options.scales.y.stacked) {{
                                    return '';  // Hide labels in stacked mode
                                }}
                                
                                // Use full value unless it's more than 6 digits
                                if (value >= 1000000) {{
                                    return (value / 1000000).toFixed(1) + 'M';
                                }} else {{
                                    return value.toLocaleString();
                                }}
                            }},
                            padding: 0,
                            offset: 8
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: 'Month',
                                color: chartDefaults.axis.titleColor,
                                font: {{
                                    size: chartDefaults.font.titleSize
                                }}
                            }},
                            ticks: {{
                                color: chartDefaults.axis.tickColor,
                                font: {{
                                    size: chartDefaults.font.tickSize
                                }}
                            }},
                            grid: {{
                                color: chartDefaults.axis.gridColor
                            }}
                        }},
                        y: {{
                            beginAtZero: true,
                            max: chartMax,
                            title: {{
                                display: true,
                                text: 'Number of Attacks',
                                color: chartDefaults.axis.titleColor,
                                font: {{
                                    size: chartDefaults.font.titleSize
                                }}
                            }},
                            ticks: {{
                                color: chartDefaults.axis.tickColor,
                                font: {{
                                    size: chartDefaults.font.tickSize
                                }},
                                callback: function(value, index, ticks) {{
                                    // Hide the top value (max tick)
                                    if (index === ticks.length - 1) {{
                                        return '';
                                    }}
                                    return value.toLocaleString();
                                }}
                            }},
                            grid: {{
                                color: chartDefaults.axis.gridColor
                            }}
                        }}
                    }}
                }}
            }});
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

        function addEventListeners() {{
            document.querySelectorAll('input[name="stackType"]').forEach(radio => {{
                radio.addEventListener('change', updateChartStacking);
            }});
        }}

        function toggleDevice(deviceIndex) {{
            const checkbox = document.getElementById(`device${{deviceIndex}}`);
            const isVisible = checkbox.checked;
            
            totalChart.data.datasets[deviceIndex].hidden = !isVisible;
            filteredChart.data.datasets[deviceIndex].hidden = !isVisible;
            
            totalChart.update('none');
            filteredChart.update('none');
        }}

        function selectAllDevices() {{
            devices.forEach((_, index) => {{
                const checkbox = document.getElementById(`device${{index}}`);
                checkbox.checked = true;
                totalChart.data.datasets[index].hidden = false;
                filteredChart.data.datasets[index].hidden = false;
            }});
            totalChart.update('none');
            filteredChart.update('none');
        }}

        function deselectAllDevices() {{
            devices.forEach((_, index) => {{
                const checkbox = document.getElementById(`device${{index}}`);
                checkbox.checked = false;
                totalChart.data.datasets[index].hidden = true;
                filteredChart.data.datasets[index].hidden = true;
            }});
            totalChart.update('none');
            filteredChart.update('none');
        }}

        function updateChartStacking() {{
            const stackType = document.querySelector('input[name="stackType"]:checked').value;
            const isStacked = stackType === 'stacked';
            
            totalChart.options.scales.x.stacked = isStacked;
            totalChart.options.scales.y.stacked = isStacked;
            filteredChart.options.scales.x.stacked = isStacked;
            filteredChart.options.scales.y.stacked = isStacked;
            
            totalChart.update();
            filteredChart.update();
        }}

        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', initializeCharts);
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