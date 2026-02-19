# ============================================================================
# IDM Test - Alat Diagnostik Hardware untuk Sistem POS
# ============================================================================
# Dependensi (install via pip):
#   pip install psutil wmi pywin32 pythonnet reportlab matplotlib
#
# Compile ke EXE:
#   pyinstaller --onefile --windowed --uac-admin --add-data "lib;lib"
#               --name=idm-test main.py
# ============================================================================

import ctypes
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os


def ensure_admin():
    """Minta hak administrator (UAC) — diperlukan untuk akses sensor suhu."""
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except Exception:
        return False

    try:
        exe = sys.executable
        if getattr(sys, "frozen", False):
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, " ".join(sys.argv[1:]), None, 1,
            )
        else:
            params = f'"{sys.argv[0]}"'
            if len(sys.argv) > 1:
                params += " " + " ".join(sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, params, None, 1,
            )
    except Exception:
        pass
    sys.exit(0)


from monitor import HardwareMonitor, SensorReading
from stress import StressEngine
from reporter import CSVLogger, generate_chart, generate_pdf_report, get_desktop_path


class IDMTestApp:
    DURATIONS = {"5 menit": 5, "10 menit": 10, "30 menit": 30}
    POLL_INTERVAL_SEC = 5

    # ── Tema ────────────────────────────────────────────────────────────
    BG = "#1a1a2e"
    BG_CARD = "#16213e"
    FG = "#e0e0e0"
    ACCENT = "#e94560"
    ACCENT2 = "#0f3460"
    GREEN = "#00c853"
    YELLOW = "#ffc107"
    RED = "#ff1744"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("IDM Test — Diagnostik Hardware")
        self.root.geometry("640x600")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        self._set_icon()

        self.monitor = HardwareMonitor()
        self.stress = StressEngine()
        self.readings: list[SensorReading] = []
        self.csv_logger: CSVLogger | None = None
        self._running = False
        self._test_thread: threading.Thread | None = None

        self._build_ui()
        self._show_sensor_status()

    def _set_icon(self):
        try:
            if getattr(sys, "frozen", False):
                base = sys._MEIPASS
            else:
                base = os.path.dirname(__file__)
            icon_path = os.path.join(base, "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

    # ── Pembuatan UI ────────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.BG_CARD)
        style.configure("TLabel", background=self.BG, foreground=self.FG,
                        font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"),
                        foreground=self.ACCENT)
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9),
                        foreground="#888888")
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"),
                        foreground=self.GREEN)
        style.configure("Metric.TLabel", font=("Consolas", 12),
                        foreground=self.FG, background=self.BG_CARD)
        style.configure("MetricTitle.TLabel", font=("Segoe UI", 8),
                        foreground="#888888", background=self.BG_CARD)

        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"),
                        padding=8)
        style.map("Accent.TButton",
                  background=[("active", self.ACCENT),
                              ("!active", self.ACCENT2)],
                  foreground=[("active", "#ffffff"),
                              ("!active", "#ffffff")])

        style.configure("Stop.TButton", font=("Segoe UI", 11, "bold"),
                        padding=8)
        style.map("Stop.TButton",
                  background=[("active", self.RED), ("!active", "#b71c1c")],
                  foreground=[("active", "#ffffff"), ("!active", "#ffffff")])

        style.configure("Green.Horizontal.TProgressbar",
                        troughcolor=self.BG_CARD,
                        background=self.ACCENT, thickness=18)

        # Header
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=20, pady=(18, 4))
        ttk.Label(header, text="IDM Test",
                  style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Alat Diagnostik Hardware POS",
                  style="Subtitle.TLabel").pack(side="left", padx=(12, 0),
                                                 pady=(8, 0))

        # Kontrol
        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", padx=20, pady=(10, 4))

        ttk.Label(ctrl, text="Durasi:").pack(side="left")
        self.duration_var = tk.StringVar(value="5 menit")
        dur_combo = ttk.Combobox(
            ctrl, textvariable=self.duration_var,
            values=list(self.DURATIONS.keys()),
            state="readonly", width=12, font=("Segoe UI", 10),
        )
        dur_combo.pack(side="left", padx=(6, 16))

        self.btn_start = ttk.Button(
            ctrl, text="Mulai Tes", style="Accent.TButton",
            command=self._on_start,
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_stop = ttk.Button(
            ctrl, text="Berhenti", style="Stop.TButton",
            command=self._on_stop, state="disabled",
        )
        self.btn_stop.pack(side="left")

        # Progress
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=20, pady=(10, 2))

        self.progress = ttk.Progressbar(
            prog_frame, orient="horizontal", mode="determinate",
            style="Green.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")

        self.lbl_status = ttk.Label(prog_frame, text="Siap",
                                    style="Status.TLabel")
        self.lbl_status.pack(pady=(4, 0))

        # Kartu metrik
        card = ttk.Frame(self.root, style="Card.TFrame", padding=14)
        card.pack(fill="both", expand=True, padx=20, pady=(10, 6))

        self.metric_labels: dict[str, tuple] = {}
        metrics = [
            ("Penggunaan CPU", "cpu_percent", "%"),
            ("Suhu CPU", "cpu_temp", "°C"),
            ("Penggunaan RAM", "ram_percent", "%"),
            ("Penggunaan Disk", "disk_percent", "%"),
            ("Suhu SSD/NVMe", "ssd_temp", "°C"),
        ]

        for i, (title, key, unit) in enumerate(metrics):
            row, col = divmod(i, 3)
            f = ttk.Frame(card, style="Card.TFrame")
            f.grid(row=row, column=col, padx=14, pady=10, sticky="nsew")
            ttk.Label(f, text=title, style="MetricTitle.TLabel").pack()
            lbl = ttk.Label(f, text="--", style="Metric.TLabel")
            lbl.pack()
            self.metric_labels[key] = (lbl, unit)

        for c in range(3):
            card.columnconfigure(c, weight=1)

        # Info deteksi sensor
        sensor_frame = ttk.Frame(self.root)
        sensor_frame.pack(fill="x", padx=20, pady=(4, 0))
        self.lbl_sensor_info = ttk.Label(sensor_frame, text="",
                                         style="Subtitle.TLabel")
        self.lbl_sensor_info.pack(anchor="w")

        # Label fase
        self.lbl_phase = ttk.Label(self.root, text="",
                                   style="Subtitle.TLabel")
        self.lbl_phase.pack(pady=(0, 2))

        # Sisa waktu
        self.lbl_time = ttk.Label(self.root, text="", style="TLabel")
        self.lbl_time.pack(pady=(0, 14))

    def _show_sensor_status(self):
        is_admin = "Ya" if ctypes.windll.shell32.IsUserAnAdmin() else "Tidak"
        cpu_m = self.monitor.cpu_method_label
        ssd_m = self.monitor.ssd_method_label
        self.lbl_sensor_info.configure(
            text=f"Admin: {is_admin}  |  Suhu CPU: {cpu_m}  |  "
                 f"Suhu SSD: {ssd_m}"
        )

    # ── Kontrol Tes ─────────────────────────────────────────────────────

    def _on_start(self):
        self.readings.clear()
        self._running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress["value"] = 0
        self._update_status("Memulai...", self.YELLOW)

        self._test_thread = threading.Thread(target=self._run_test,
                                             daemon=True)
        self._test_thread.start()

    def _on_stop(self):
        self._running = False
        self.stress.stop()
        self._update_status("Menghentikan...", self.YELLOW)

    def _run_test(self):
        duration_min = self.DURATIONS[self.duration_var.get()]
        total_seconds = duration_min * 60
        idle_seconds = 30
        load_seconds = total_seconds - idle_seconds

        try:
            self.csv_logger = CSVLogger()
        except Exception as e:
            self._schedule(lambda: messagebox.showerror(
                "Kesalahan", f"Gagal membuat file CSV:\n{e}"))
            self._finish_test()
            return

        system_info = self.monitor.get_system_info()

        # Fase 1: Idle (30 detik)
        self._schedule(lambda: self._update_phase(
            "Fase 1/2 — Pemantauan Idle"))
        self._schedule(lambda: self._update_status("Berjalan", self.GREEN))
        self.stress.start_idle()
        if not self._collect_phase(idle_seconds, total_seconds, 0):
            self._finalize(duration_min, system_info)
            return

        # Fase 2: Beban Penuh
        self._schedule(lambda: self._update_phase(
            "Fase 2/2 — Beban Penuh"))
        self.stress.start_load()
        self._collect_phase(load_seconds, total_seconds, idle_seconds)
        self.stress.stop()

        self._finalize(duration_min, system_info)

    def _collect_phase(self, phase_seconds: int, total_seconds: int,
                       elapsed_before: int) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < phase_seconds:
            if not self._running:
                return False

            reading = self.monitor.read_sensors()
            self.readings.append(reading)
            self.csv_logger.write(reading)
            self._schedule(lambda r=reading: self._update_metrics(r))

            elapsed_total = elapsed_before + (time.monotonic() - start)
            pct = min(100, (elapsed_total / total_seconds) * 100)
            remaining = max(0, total_seconds - elapsed_total)
            self._schedule(
                lambda p=pct: self.progress.configure(value=p))
            self._schedule(
                lambda s=remaining: self.lbl_time.configure(
                    text=f"Sisa waktu: {int(s // 60)}m {int(s % 60)}d"))

            time.sleep(self.POLL_INTERVAL_SEC)
        return True

    def _finalize(self, duration_min: int, system_info: dict):
        try:
            self.csv_logger.close()
        except Exception:
            pass

        self._schedule(lambda: self._update_status(
            "Membuat laporan...", self.YELLOW))
        self._schedule(lambda: self._update_phase(""))

        if self.readings:
            try:
                chart_path = generate_chart(self.readings)
            except Exception:
                chart_path = ""

            try:
                pdf_path = generate_pdf_report(
                    self.readings, duration_min, chart_path, system_info)
            except Exception as e:
                self._schedule(lambda: messagebox.showwarning(
                    "Laporan", f"Gagal membuat PDF: {e}"))
                pdf_path = ""

            msg = ["Tes selesai! File tersimpan di Desktop:"]
            msg.append("  • idm-test-log.csv")
            if chart_path:
                msg.append("  • idm-test-cpu-temp.png")
            if pdf_path:
                msg.append("  • idm-test-report.pdf")

            self._schedule(lambda: messagebox.showinfo(
                "Selesai", "\n".join(msg)))

        self._finish_test()

    def _finish_test(self):
        self._running = False
        self._schedule(lambda: self._update_status("Selesai", self.GREEN))
        self._schedule(lambda: self.btn_start.configure(state="normal"))
        self._schedule(lambda: self.btn_stop.configure(state="disabled"))
        self._schedule(lambda: self.progress.configure(value=100))
        self._schedule(lambda: self.lbl_time.configure(text=""))
        self._schedule(lambda: self._update_phase(""))

    # ── Utilitas UI ─────────────────────────────────────────────────────

    def _schedule(self, fn):
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    def _update_status(self, text: str, color: str):
        self.lbl_status.configure(text=text, foreground=color)

    def _update_phase(self, text: str):
        self.lbl_phase.configure(text=text)

    def _update_metrics(self, r: SensorReading):
        for key, (label, unit) in self.metric_labels.items():
            value = getattr(r, key, None)
            if value is not None:
                label.configure(text=f"{value}{unit}")
            else:
                label.configure(text="N/A")


def main():
    ensure_admin()
    root = tk.Tk()
    app = IDMTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
