# ============================================================================
# IDM Test - Modul Pelaporan
# Menghasilkan log CSV, grafik PNG, dan laporan PDF profesional
# Seluruh output dalam Bahasa Indonesia
# Dependencies: matplotlib, reportlab
# ============================================================================

import os
import csv
import statistics
from datetime import datetime, datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER

from monitor import SensorReading


def get_desktop_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


# ── Logger CSV ──────────────────────────────────────────────────────────

class CSVLogger:
    def __init__(self):
        path = os.path.join(get_desktop_path(), "idm-test-log.csv")
        self._path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow([
            "Waktu", "CPU %", "Suhu CPU", "RAM %", "Disk %", "Suhu SSD",
        ])

    def write(self, r: SensorReading):
        self._writer.writerow([
            r.timestamp,
            r.cpu_percent,
            r.cpu_temp if r.cpu_temp is not None else "N/A",
            r.ram_percent,
            r.disk_percent,
            r.ssd_temp if r.ssd_temp is not None else "N/A",
        ])
        self._file.flush()

    def close(self):
        self._file.close()


# ── Generator Grafik ────────────────────────────────────────────────────

def generate_chart(readings: list[SensorReading]) -> str:
    output_path = os.path.join(get_desktop_path(), "idm-test-cpu-temp.png")

    timestamps = []
    cpu_temps = []
    cpu_usages = []

    for r in readings:
        try:
            timestamps.append(dt.strptime(r.timestamp, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        cpu_temps.append(r.cpu_temp)
        cpu_usages.append(r.cpu_percent)

    fig, ax1 = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#1a1a2e")
    ax1.set_facecolor("#16213e")

    has_temp = any(t is not None for t in cpu_temps)

    if has_temp:
        valid_temps = [t if t is not None else 0 for t in cpu_temps]
        ax1.plot(timestamps, valid_temps, color="#e94560", linewidth=2,
                 label="Suhu CPU (°C)")
        ax1.set_ylabel("Suhu (°C)", color="#e94560", fontsize=11)
        ax1.tick_params(axis="y", labelcolor="#e94560")

        ax1.axhline(y=75, color="#f5a623", linestyle="--", alpha=0.6,
                     label="Peringatan (75°C)")
        ax1.axhline(y=85, color="#ff0000", linestyle="--", alpha=0.6,
                     label="Kritis (85°C)")

    ax2 = ax1.twinx()
    ax2.plot(timestamps, cpu_usages, color="#0f3460", linewidth=1.5,
             alpha=0.7, label="Penggunaan CPU (%)")
    ax2.set_ylabel("Penggunaan CPU (%)", color="#0f3460", fontsize=11)
    ax2.tick_params(axis="y", labelcolor="#0f3460")
    ax2.set_ylim(0, 100)

    ax1.set_xlabel("Waktu", color="#cccccc", fontsize=11)
    ax1.set_title("IDM Test — Pemantauan Suhu CPU", color="#ffffff",
                   fontsize=14, fontweight="bold", pad=15)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.autofmt_xdate(rotation=30)

    ax1.tick_params(colors="#aaaaaa")
    ax2.tick_params(colors="#aaaaaa")
    ax1.spines["bottom"].set_color("#444444")
    ax1.spines["left"].set_color("#444444")
    ax1.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_color("#444444")
    ax2.spines["right"].set_color("#444444")
    ax2.spines["top"].set_visible(False)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
               fontsize=9, facecolor="#1a1a2e", edgecolor="#444444",
               labelcolor="#cccccc")

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


# ── Evaluasi Status ─────────────────────────────────────────────────────

def evaluate_status(readings: list[SensorReading]) -> tuple[str, str, str]:
    """Mengembalikan (status, warna, deskripsi)."""
    temps = [r.cpu_temp for r in readings if r.cpu_temp is not None]

    if temps:
        max_temp = max(temps)
        if max_temp > 85:
            return ("GAGAL", "#FF0000",
                    "Suhu melebihi batas kritis! Perlu penanganan segera.")
        elif max_temp >= 75:
            return ("PERINGATAN", "#FFA500",
                    "Suhu tinggi terdeteksi. Periksa sistem pendingin.")
        else:
            return ("LULUS", "#00AA00",
                    "Semua parameter dalam batas normal. Hardware sehat.")

    usages = [r.cpu_percent for r in readings]
    if usages:
        avg_usage = statistics.mean(usages)
        if avg_usage > 95:
            return ("GAGAL", "#FF0000",
                    "Penggunaan CPU sangat tinggi. Periksa proses berjalan.")
        elif avg_usage > 85:
            return ("PERINGATAN", "#FFA500",
                    "Penggunaan CPU tinggi. Pantau lebih lanjut.")
    return ("LULUS", "#00AA00",
            "Semua parameter dalam batas normal. Hardware sehat.")


# ── Generator Laporan PDF ───────────────────────────────────────────────

def generate_pdf_report(
    readings: list[SensorReading],
    duration_minutes: int,
    chart_path: str,
    system_info: dict,
) -> str:
    output_path = os.path.join(get_desktop_path(), "idm-test-report.pdf")

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "IDMTitle", parent=styles["Title"],
        fontSize=22, textColor=HexColor("#1a1a2e"),
        spaceAfter=6, alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "IDMSub", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#666666"),
        alignment=TA_CENTER, spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "IDMHead", parent=styles["Heading2"],
        fontSize=13, textColor=HexColor("#1a1a2e"),
        spaceBefore=14, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "IDMBody", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#333333"), spaceAfter=4,
    )

    elements = []

    # ── Judul ───────────────────────────────────────────────────────
    elements.append(Paragraph("IDM TEST", title_style))
    elements.append(Paragraph(
        "LAPORAN DIAGNOSTIK HARDWARE",
        ParagraphStyle("Sub2", parent=title_style, fontSize=14,
                       textColor=HexColor("#e94560")),
    ))
    elements.append(Spacer(1, 4 * mm))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(f"Dibuat: {now}", subtitle_style))
    elements.append(Paragraph(f"Durasi Tes: {duration_minutes} menit",
                              subtitle_style))

    # Metode deteksi suhu
    cpu_m = system_info.get("temp_cpu_method", "none")
    ssd_m = system_info.get("temp_ssd_method", "none")
    method_labels = {
        "lhm": "LibreHardwareMonitor", "ohm_wmi": "OHM/LHM WMI",
        "wmi_acpi": "WMI ThermalZone", "ps_acpi": "PowerShell ACPI",
        "psutil": "psutil", "ps_reliability": "StorageReliability",
        "wmi_storage": "WMI Storage", "none": "Tidak tersedia",
    }
    elements.append(Paragraph(
        f"Deteksi Suhu CPU: {method_labels.get(cpu_m, cpu_m)} &nbsp;|&nbsp; "
        f"Deteksi Suhu SSD: {method_labels.get(ssd_m, ssd_m)}",
        subtitle_style,
    ))

    elements.append(HRFlowable(width="100%", thickness=1,
                                color=HexColor("#dddddd")))
    elements.append(Spacer(1, 4 * mm))

    # ── Informasi Sistem ────────────────────────────────────────────
    elements.append(Paragraph("Informasi Sistem", heading_style))
    sys_data = [
        ["Sistem Operasi", str(system_info.get("os", "N/A"))],
        ["Prosesor", str(system_info.get("cpu_name", "N/A"))],
        ["Core Fisik", str(system_info.get("cpu_cores_physical", "N/A"))],
        ["Core Logis", str(system_info.get("cpu_cores_logical", "N/A"))],
        ["Frekuensi CPU", f"{system_info.get('cpu_freq_mhz', 'N/A')} MHz"],
        ["Total RAM", f"{system_info.get('ram_total_gb', 'N/A')} GB"],
        ["Total Disk (C:)", f"{system_info.get('disk_total_gb', 'N/A')} GB"],
        ["Disk Kosong (C:)", f"{system_info.get('disk_free_gb', 'N/A')} GB"],
    ]
    sys_table = Table(sys_data, colWidths=[55 * mm, 105 * mm])
    sys_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), HexColor("#f0f0f5")),
        ("TEXTCOLOR", (0, 0), (-1, -1), HexColor("#333333")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
    ]))
    elements.append(sys_table)
    elements.append(Spacer(1, 4 * mm))

    # ── Statistik Tes ───────────────────────────────────────────────
    elements.append(Paragraph("Statistik Pengujian", heading_style))

    cpu_vals = [r.cpu_percent for r in readings]
    temp_vals = [r.cpu_temp for r in readings if r.cpu_temp is not None]
    ram_vals = [r.ram_percent for r in readings]
    disk_vals = [r.disk_percent for r in readings]
    ssd_vals = [r.ssd_temp for r in readings if r.ssd_temp is not None]

    def fmt(vals, unit="%"):
        if not vals:
            return "N/A", "N/A", "N/A"
        return (
            f"{min(vals):.1f}{unit}",
            f"{max(vals):.1f}{unit}",
            f"{statistics.mean(vals):.1f}{unit}",
        )

    cpu_min, cpu_max, cpu_avg = fmt(cpu_vals)
    tmp_min, tmp_max, tmp_avg = fmt(temp_vals, "°C")
    ram_min, ram_max, ram_avg = fmt(ram_vals)
    dsk_min, dsk_max, dsk_avg = fmt(disk_vals)
    ssd_min, ssd_max, ssd_avg = fmt(ssd_vals, "°C")

    stat_data = [
        ["Parameter", "Min", "Maks", "Rata-rata"],
        ["Penggunaan CPU", cpu_min, cpu_max, cpu_avg],
        ["Suhu CPU", tmp_min, tmp_max, tmp_avg],
        ["Penggunaan RAM", ram_min, ram_max, ram_avg],
        ["Penggunaan Disk", dsk_min, dsk_max, dsk_avg],
        ["Suhu SSD/NVMe", ssd_min, ssd_max, ssd_avg],
    ]
    stat_table = Table(stat_data, colWidths=[40 * mm, 35 * mm, 35 * mm,
                                              40 * mm])
    stat_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (-1, -1), HexColor("#f8f8fc")),
        ("TEXTCOLOR", (0, 1), (-1, -1), HexColor("#333333")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(stat_table)
    elements.append(Spacer(1, 6 * mm))

    # ── Grafik ──────────────────────────────────────────────────────
    if chart_path and os.path.exists(chart_path):
        elements.append(Paragraph("Grafik Suhu CPU", heading_style))
        img = RLImage(chart_path, width=160 * mm, height=80 * mm)
        elements.append(img)
        elements.append(Spacer(1, 6 * mm))

    # ── Kesimpulan ──────────────────────────────────────────────────
    status, color, description = evaluate_status(readings)
    elements.append(HRFlowable(width="100%", thickness=1,
                                color=HexColor("#dddddd")))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("Kesimpulan Akhir", heading_style))

    status_style = ParagraphStyle(
        "StatusStyle", parent=styles["Title"],
        fontSize=28, textColor=HexColor(color),
        alignment=TA_CENTER, spaceBefore=8, spaceAfter=4,
    )
    elements.append(Paragraph(status, status_style))
    elements.append(Paragraph(
        description,
        ParagraphStyle("StatusDesc", parent=body_style,
                       alignment=TA_CENTER, fontSize=10),
    ))
    elements.append(Spacer(1, 4 * mm))

    # Tabel kriteria evaluasi
    eval_data = [
        ["Status", "Kriteria"],
        ["LULUS", "Suhu CPU < 75°C"],
        ["PERINGATAN", "Suhu CPU 75°C — 85°C"],
        ["GAGAL", "Suhu CPU > 85°C"],
    ]
    eval_table = Table(eval_data, colWidths=[40 * mm, 80 * mm])
    eval_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (0, 1), HexColor("#e8f5e9")),
        ("BACKGROUND", (0, 2), (0, 2), HexColor("#fff3e0")),
        ("BACKGROUND", (0, 3), (0, 3), HexColor("#ffebee")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(eval_table)
    elements.append(Spacer(1, 8 * mm))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=HexColor("#cccccc")))
    elements.append(Paragraph(
        "IDM Test — Alat Diagnostik Hardware — "
        "Laporan dibuat secara otomatis",
        ParagraphStyle("Footer", parent=body_style, fontSize=8,
                       textColor=HexColor("#999999"),
                       alignment=TA_CENTER),
    ))

    doc.build(elements)
    return output_path
