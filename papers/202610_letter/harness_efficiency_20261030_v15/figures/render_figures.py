#!/usr/bin/env python3
"""Compatibility entry point for the native Excel chart exporter.

This delegates to create_excel_charts.py and never redraws a Matplotlib chart.
The output directory contains results_charts.xlsx, its export manifest, and a
figures/ folder with the five color result figures. Figure 1 uses render_control_points.py.
Pass --data to build from the frozen JSON, or --workbook to export an edited
Excel workbook. Both modes require --soffice and a fresh --output-dir.
"""
from pathlib import Path
import runpy
if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'create_excel_charts.py'),run_name='__main__')
