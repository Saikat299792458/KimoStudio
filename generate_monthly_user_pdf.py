#!/usr/bin/env python3
"""Generate a monthly user modification report from Activity.log.

Usage:
    python generate_monthly_user_pdf.py [log_path] [output_pdf]

If no log_path is provided, it reads from Activity.log in the current directory.
If no output_pdf is provided, it writes report.pdf in the current directory.

The script filters entries by the current month and year and computes a impact score
for each user. impact depends more strongly on the number of files modified than on
modification percentage.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from calendar import monthrange

reportlab = None
try:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph
    from reportlab.graphics.shapes import Drawing, String, Group
    from reportlab.graphics.charts.barcharts import VerticalBarChart
except ImportError:  # pragma: no cover
    reportlab = None


@dataclass
class LogEntry:
    username: str
    ip_address: str
    mac_address: str
    modified_at: datetime
    modification_percentage: float
    static_modifications: Dict[str, str]


@dataclass
class UserSummary:
    username: str
    ip_address: str
    mac_address: str
    file_count: int
    average_modification_pct: float
    impact: float


def parse_activity_log(path: str) -> List[LogEntry]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Activity log not found: {path}")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    entries: List[LogEntry] = []
    blocks = text.split("--------------------------------------------------")

    for block in blocks:
        if not block.strip():
            continue

        fields = {
            "UserName": None,
            "IP Address": None,
            "MAC Address": None,
            "Modified at": None,
            "Modification Percentage": None,
        }

        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key in fields:
                fields[key] = value

        if not all(fields.values()):
            continue

        static_modifications: Dict[str, str] = {}
        in_static_block = False
        for line in block.splitlines():
            if line.strip().startswith("Static Modifications:"):
                in_static_block = True
                continue
            if in_static_block and ":" in line:
                key, value = line.split(":", 1)
                static_modifications[key.strip()] = value.strip()

        try:
            modified_at = datetime.strptime(fields["Modified at"], "%Y-%m-%d %H:%M:%S")
            modification_percentage = float(fields["Modification Percentage"].rstrip("%"))
        except ValueError:
            continue

        entries.append(
            LogEntry(
                username=fields["UserName"],
                ip_address=fields["IP Address"],
                mac_address=fields["MAC Address"],
                modified_at=modified_at,
                modification_percentage=modification_percentage,
                static_modifications=static_modifications,
            )
        )

    return entries


def filter_entries_by_month(entries: List[LogEntry], year: int, month: int) -> List[LogEntry]:
    return [entry for entry in entries if entry.modified_at.year == year and entry.modified_at.month == month]


def summarize_static_modifications(entries: List[LogEntry]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for entry in entries:
        for key, value in entry.static_modifications.items():
            if value.strip().lower() == "yes":
                counts[key] = counts.get(key, 0) + 1
    return counts


def daily_usage(entries: List[LogEntry], year: int, month: int) -> Dict[int, int]:
    day_counts: Dict[int, int] = {}
    for entry in entries:
        if entry.modified_at.year == year and entry.modified_at.month == month:
            day_counts[entry.modified_at.day] = day_counts.get(entry.modified_at.day, 0) + 1
    return day_counts






def summarize_users(entries: List[LogEntry]) -> Tuple[List[UserSummary], int, int]:
    ip_map: Dict[str, Dict[str, Any]] = {}

    for entry in entries:
        ip = entry.ip_address
        if ip not in ip_map:
            ip_map[ip] = {
                "count": 0,
                "sum_pct": 0.0,
                "usernames": {},
                "mac_addresses": {},
            }
        ip_map[ip]["count"] += 1
        ip_map[ip]["sum_pct"] += entry.modification_percentage
        ip_map[ip]["usernames"][entry.username] = ip_map[ip]["usernames"].get(entry.username, 0) + 1
        ip_map[ip]["mac_addresses"][entry.mac_address] = ip_map[ip]["mac_addresses"].get(entry.mac_address, 0) + 1

    summaries: List[UserSummary] = []
    for ip, values in ip_map.items():
        count = int(values["count"])
        avg_pct = values["sum_pct"] / count
        # Get most common username and MAC address for this IP
        username = max(values["usernames"], key=values["usernames"].get)
        mac_address = max(values["mac_addresses"], key=values["mac_addresses"].get)
        # Calculate raw impact (not normalized to 0-100)
        impact = (count ** 1.75) * (0.75 + 0.25 * (avg_pct / 100.0))
        summaries.append(
            UserSummary(
                username=username,
                ip_address=ip,
                mac_address=mac_address,
                file_count=count,
                average_modification_pct=avg_pct,
                impact=impact,
            )
        )

    summaries.sort(key=lambda item: item.impact, reverse=True)
    total_files = len(entries)
    unique_files = sum(item.file_count for item in summaries)
    return summaries, unique_files, total_files


def build_usage_chart(daily_counts: Dict[int, int], report_month: datetime) -> Drawing:
    month_days = monthrange(report_month.year, report_month.month)[1]
    days = list(range(1, month_days + 1))
    data = [[daily_counts.get(day, 0) for day in days]]

    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 45
    chart.height = 155
    chart.width = 440
    chart.data = data
    chart.strokeColor = colors.black
    chart.valueAxis.valueMin = 0
    max_value = max(data[0]) if data and data[0] else 0
    chart.valueAxis.valueMax = max_value + max(1, int(max_value * 0.2))
    chart.valueAxis.valueStep = max(1, math.ceil(chart.valueAxis.valueMax / 8))
    chart.categoryAxis.categoryNames = [str(day) for day in days]
    chart.categoryAxis.labels.boxAnchor = 'n'
    chart.categoryAxis.strokeColor = colors.black
    chart.barWidth = min(0.3 * inch, chart.width / max(len(days) * 1.4, 1))
    if chart.bars:
        chart.bars[0].fillColor = colors.HexColor("#4B8BBE")
    drawing = Drawing()
    drawing.add(chart)
    drawing.add(String(250, 18, "Date of month", fontSize=9, textAnchor='middle'))
    # 3. Create a Group container to apply the rotation matrix
    label_group = Group()
    # Position the Group's origin where you want the label center to be
    # X = 20 (to the left of chart.x), Y = 115 (vertically centered on the chart height)
    label_group.translate(20, 115) 
    label_group.rotate(90)          # Rotates the whole container 90 degrees counterclockwise

    # 4. Create the text string relative to the Group's local coordinates
    # Because the group itself is translated, position the text at (0, 0)
    y_label = String(0, 0, "No. of mod.")
    y_label.fontSize = 9
    y_label.textAnchor = "middle"   # Centers text on the group's origin

    # 5. Add the text to the group, and the group to the main drawing
    label_group.add(y_label)
    drawing.add(label_group)
    return drawing


def build_pdf_report(
    summaries: List[UserSummary],
    report_month: datetime,
    files_this_month: int,
    total_files_modified: int,
    static_counts: Dict[str, int],
    daily_counts: Dict[int, int],
    output_path: str,
) -> None:
    if reportlab is None:
        raise ImportError(
            "The report requires reportlab. Install it with: python -m pip install reportlab"
        )

    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = {
        "heading": ParagraphStyle(
            name="Heading",
            fontSize=18,
            leading=22,
            spaceAfter=12,
            alignment=1,
        ),
        "subheading": ParagraphStyle(
            name="SubHeading",
            fontSize=12,
            leading=14,
            spaceAfter=12,
            alignment=1,
        ),
        "normal": ParagraphStyle(
            name="Normal",
            fontSize=10,
            leading=12,
            spaceAfter=10,
            alignment=0,
        ),
    }
    flowables = []
    flowables.append(Paragraph("Kimo Studio - Monthly User Modification Report", styles["heading"]))
    flowables.append(
        Paragraph(
            f"Report period: {report_month.strftime('%B %Y')}<br/>"
            f"Files modified this month: {files_this_month}<br/>"
            f"Total files modified: {total_files_modified}",
            styles["subheading"],
        )
    )
    flowables.append(Spacer(1, 0.1 * inch))

    table_data = [["Username", "IP Address", "MAC Address", "Files Modified", "Avg. Mod. %", "Impact"]]
    for summary in summaries:
        table_data.append(
            [
                summary.username,
                summary.ip_address,
                summary.mac_address,
                str(summary.file_count),
                f"{summary.average_modification_pct:.2f}",
                f"{summary.impact:.2f}",
            ]
        )
    col_width = doc.width / len(table_data[0])
    table = Table(table_data, colWidths=[col_width] * len(table_data[0]))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d3d3d3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#000000")),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (0, 1), (2, -1), "LEFT"),
                ("ALIGN", (3, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    flowables.append(table)
    flowables.append(Spacer(1, 0.2 * inch))

    if static_counts:
        static_lines = [
            f"{key}: {value}" for key, value in sorted(static_counts.items())
        ]
        static_text = "<br/>".join(static_lines)
        static_table = Table(
            [[Paragraph(f"<b>Static modification totals</b>:<br/>{static_text}", styles["normal"])]]
        )
        static_table.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        flowables.append(static_table)
        flowables.append(Spacer(1, 0.15 * inch))

    # Add impact calculation formula above the chart
    formula_text = (
        "<font face=\"Courier\">impact = (f<sup>1.75</sup>) × (0.75 + 0.25 × (p / 100))</font><br/><br/>"
        "where:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<b>f</b> = number of files modified by the user<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<b>p</b> = average modification percentage across all files"
    )
    flowables.append(Paragraph(formula_text, styles["normal"]))
    flowables.append(Spacer(1, 0.15 * inch))

    if daily_counts:
        flowables.append(Paragraph("<b>Daily modification count</b>", styles["normal"]))
        flowables.append(build_usage_chart(daily_counts, report_month))
        flowables.append(Spacer(1, 0.15 * inch))

    doc.build(flowables)


def main() -> int:
    log_path = sys.argv[1] if len(sys.argv) > 1 else  "\\\\192.168.5.6\\IPL-VLD-Calibration Management\\1. Common\\Software\\Kimo Studio\\Activity.log"
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else "monthly_user_report.pdf"

    try:
        all_entries = parse_activity_log(log_path)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    now = datetime.now()
    current_entries = filter_entries_by_month(all_entries, now.year, now.month)
    summaries, files_this_month, total_files = summarize_users(current_entries)

    if not current_entries:
        print(
            f"No entries found for {now.strftime('%B %Y')} in {log_path}."
            f" The report will still be created with zero records."
        )

    static_counts = summarize_static_modifications(current_entries)
    daily_counts = daily_usage(current_entries, now.year, now.month)

    try:
        build_pdf_report(
            summaries,
            now,
            files_this_month,
            total_files,
            static_counts,
            daily_counts,
            output_pdf,
        )
        print(f"Generated PDF report: {output_pdf}")
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Failed to generate PDF report: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
