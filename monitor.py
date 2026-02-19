# ============================================================================
# IDM Test - Hardware Monitor Module
# Multi-method temperature detection for Windows 10/11
# Optimized for Intel Gen 8+ CPU temperature reading
# Dependencies: psutil, wmi, pywin32, pythonnet
# ============================================================================
#
# CPU Temperature methods (priority order):
#   1. LibreHardwareMonitor via pythonnet  ← BEST for Intel Gen 8+
#   2. OpenHardwareMonitor / LHM WMI provider
#   3. WMI root\WMI → MSAcpi_ThermalZoneTemperature
#   4. PowerShell Get-CimInstance MSAcpi_ThermalZoneTemperature
#   5. psutil sensors_temperatures (Linux fallback)
#
# SSD/NVMe Temperature methods (priority order):
#   1. LibreHardwareMonitor via pythonnet
#   2. OpenHardwareMonitor / LHM WMI provider
#   3. PowerShell Get-StorageReliabilityCounter (native Win10/11)
#   4. WMI MSFT_PhysicalDisk via Storage namespace
#
# ============================================================================

import os
import sys
import subprocess
import time
import logging
import psutil
from dataclasses import dataclass
from typing import Optional

try:
    import wmi as wmi_module
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

log = logging.getLogger("idm-monitor")

# ── LibreHardwareMonitor pythonnet initialization ───────────────────────

LHM_READY = False
_lhm_computer = None

def _get_lib_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "lib")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")


def _init_lhm_runtime():
    """Load LibreHardwareMonitorLib.dll via pythonnet (.NET Framework)."""
    global LHM_READY, _lhm_computer
    lib_dir = _get_lib_dir()
    dll_path = os.path.join(lib_dir, "LibreHardwareMonitorLib.dll")
    if not os.path.isfile(dll_path):
        log.warning("LibreHardwareMonitorLib.dll not found at %s", dll_path)
        return

    try:
        from pythonnet import load
        load("netfx")
    except Exception:
        pass

    try:
        import clr  # noqa: E402
        clr.AddReference(dll_path)
        hidsharp = os.path.join(lib_dir, "HidSharp.dll")
        if os.path.isfile(hidsharp):
            clr.AddReference(hidsharp)
        json_dll = os.path.join(lib_dir, "Newtonsoft.Json.dll")
        if os.path.isfile(json_dll):
            clr.AddReference(json_dll)

        from LibreHardwareMonitor.Hardware import Computer

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsStorageEnabled = True
        computer.Open()

        _lhm_computer = computer
        LHM_READY = True
        log.info("LibreHardwareMonitor loaded successfully")
    except Exception as exc:
        log.warning("Failed to load LibreHardwareMonitor: %s", exc)
        LHM_READY = False


try:
    _init_lhm_runtime()
except Exception:
    pass


# ── Helpers ─────────────────────────────────────────────────────────────

def _run_powershell(script: str, timeout: float = 8) -> Optional[str]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


@dataclass
class SensorReading:
    timestamp: str
    cpu_percent: float
    cpu_temp: Optional[float]
    ram_percent: float
    disk_percent: float
    ssd_temp: Optional[float]


class HardwareMonitor:
    def __init__(self):
        self._wmi_ohm = None
        self._wmi_root = None
        self._wmi_storage = None

        self._cpu_method: Optional[str] = None
        self._ssd_method: Optional[str] = None

        self._init_wmi_providers()
        self._detect_best_methods()

    # ── WMI Initialization ──────────────────────────────────────────────

    def _init_wmi_providers(self):
        if not WMI_AVAILABLE:
            return

        for ns in ["root\\LibreHardwareMonitor", "root\\OpenHardwareMonitor"]:
            try:
                client = wmi_module.WMI(namespace=ns)
                client.Sensor()
                self._wmi_ohm = client
                log.info("WMI connected: %s", ns)
                break
            except Exception:
                continue

        try:
            self._wmi_root = wmi_module.WMI(namespace="root\\WMI")
        except Exception:
            pass

        try:
            self._wmi_storage = wmi_module.WMI(
                namespace="root\\Microsoft\\Windows\\Storage"
            )
        except Exception:
            pass

    # ── Auto-detect best working method ─────────────────────────────────

    def _detect_best_methods(self):
        cpu_methods = [
            ("lhm",       self._cpu_temp_lhm),
            ("ohm_wmi",   self._cpu_temp_ohm),
            ("wmi_acpi",  self._cpu_temp_wmi_acpi),
            ("ps_acpi",   self._cpu_temp_ps_acpi),
            ("psutil",    self._cpu_temp_psutil),
        ]
        for name, func in cpu_methods:
            val = func()
            if val is not None:
                self._cpu_method = name
                log.info("CPU temp → %s (%.1f°C)", name, val)
                break

        ssd_methods = [
            ("lhm",            self._ssd_temp_lhm),
            ("ohm_wmi",        self._ssd_temp_ohm),
            ("ps_reliability", self._ssd_temp_ps_reliability),
            ("wmi_storage",    self._ssd_temp_wmi_storage),
        ]
        for name, func in ssd_methods:
            val = func()
            if val is not None:
                self._ssd_method = name
                log.info("SSD temp → %s (%.1f°C)", name, val)
                break

    # ══════════════════════════════════════════════════════════════════════
    #  CPU Temperature Methods
    # ══════════════════════════════════════════════════════════════════════

    def _cpu_temp_lhm(self) -> Optional[float]:
        """#1 — LibreHardwareMonitor via pythonnet (Intel Gen 8+ DTS/MSR)."""
        if not LHM_READY or _lhm_computer is None:
            return None
        try:
            from LibreHardwareMonitor.Hardware import HardwareType, SensorType
            for hw in _lhm_computer.Hardware:
                ht = hw.HardwareType
                if ht != HardwareType.Cpu:
                    continue
                hw.Update()
                pkg_temp = None
                first_core = None
                for sensor in hw.Sensors:
                    if sensor.SensorType != SensorType.Temperature:
                        continue
                    if sensor.Value is None:
                        continue
                    val = float(sensor.Value)
                    if not (0 < val < 150):
                        continue
                    name = (sensor.Name or "").lower()
                    if "package" in name or "total" in name:
                        pkg_temp = val
                    elif first_core is None and "core" in name:
                        first_core = val
                if pkg_temp is not None:
                    return round(pkg_temp, 1)
                if first_core is not None:
                    return round(first_core, 1)
        except Exception as exc:
            log.debug("LHM CPU temp error: %s", exc)
        return None

    def _cpu_temp_ohm(self) -> Optional[float]:
        """#2 — OHM/LHM WMI provider."""
        if self._wmi_ohm is None:
            return None
        try:
            for sensor in self._wmi_ohm.Sensor():
                if sensor.SensorType == "Temperature":
                    name = (sensor.Name or "").lower()
                    if any(k in name for k in ["cpu package", "cpu total",
                                                "core #0", "cpu"]):
                        val = float(sensor.Value)
                        if 0 < val < 150:
                            return round(val, 1)
        except Exception:
            pass
        return None

    def _cpu_temp_wmi_acpi(self) -> Optional[float]:
        """#3 — WMI MSAcpi_ThermalZoneTemperature (needs admin)."""
        if self._wmi_root is None:
            return None
        try:
            for tz in self._wmi_root.MSAcpi_ThermalZoneTemperature():
                raw = int(tz.CurrentTemperature)
                celsius = (raw / 10.0) - 273.15
                if 0 < celsius < 150:
                    return round(celsius, 1)
        except Exception:
            pass
        return None

    def _cpu_temp_ps_acpi(self) -> Optional[float]:
        """#4 — PowerShell CIM MSAcpi_ThermalZoneTemperature."""
        script = (
            "Get-CimInstance -Namespace root/WMI "
            "-ClassName MSAcpi_ThermalZoneTemperature "
            "-ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty CurrentTemperature -First 1"
        )
        output = _run_powershell(script)
        if output:
            try:
                raw = int(output.strip())
                celsius = (raw / 10.0) - 273.15
                if 0 < celsius < 150:
                    return round(celsius, 1)
            except (ValueError, TypeError):
                pass
        return None

    def _cpu_temp_psutil(self) -> Optional[float]:
        """#5 — psutil (Linux / limited Windows)."""
        if not hasattr(psutil, "sensors_temperatures"):
            return None
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None
            for name in ["coretemp", "cpu_thermal", "k10temp", "zenpower"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass
        return None

    # ══════════════════════════════════════════════════════════════════════
    #  SSD / NVMe Temperature Methods
    # ══════════════════════════════════════════════════════════════════════

    def _ssd_temp_lhm(self) -> Optional[float]:
        """#1 — LibreHardwareMonitor via pythonnet."""
        if not LHM_READY or _lhm_computer is None:
            return None
        try:
            from LibreHardwareMonitor.Hardware import HardwareType, SensorType
            for hw in _lhm_computer.Hardware:
                ht = hw.HardwareType
                if ht != HardwareType.Storage:
                    continue
                hw.Update()
                for sensor in hw.Sensors:
                    if sensor.SensorType != SensorType.Temperature:
                        continue
                    if sensor.Value is None:
                        continue
                    val = float(sensor.Value)
                    if 0 < val < 150:
                        return round(val, 1)
        except Exception as exc:
            log.debug("LHM SSD temp error: %s", exc)
        return None

    def _ssd_temp_ohm(self) -> Optional[float]:
        """#2 — OHM/LHM WMI provider."""
        if self._wmi_ohm is None:
            return None
        try:
            for sensor in self._wmi_ohm.Sensor():
                if sensor.SensorType == "Temperature":
                    name = (sensor.Name or "").lower()
                    parent = (getattr(sensor, "Parent", "") or "").lower()
                    if any(k in name for k in ["ssd", "nvme", "disk", "drive"]):
                        val = float(sensor.Value)
                        if 0 < val < 150:
                            return round(val, 1)
                    if any(k in parent for k in ["nvme", "ssd", "storage"]):
                        val = float(sensor.Value)
                        if 0 < val < 150:
                            return round(val, 1)
        except Exception:
            pass
        return None

    def _ssd_temp_ps_reliability(self) -> Optional[float]:
        """#3 — PowerShell Get-StorageReliabilityCounter (native Win10/11)."""
        script = (
            "Get-PhysicalDisk | Get-StorageReliabilityCounter "
            "-ErrorAction SilentlyContinue | "
            "Where-Object { $_.Temperature -gt 0 } | "
            "Select-Object -ExpandProperty Temperature -First 1"
        )
        output = _run_powershell(script)
        if output:
            try:
                val = float(output.strip())
                if 0 < val < 150:
                    return round(val, 1)
            except (ValueError, TypeError):
                pass
        return None

    def _ssd_temp_wmi_storage(self) -> Optional[float]:
        """#4 — WMI MSFT_PhysicalDisk."""
        if self._wmi_storage is None:
            return None
        try:
            for disk in self._wmi_storage.MSFT_PhysicalDisk():
                raw = getattr(disk, "Temperature", None)
                if raw is not None:
                    val = float(raw)
                    if 0 < val < 150:
                        return round(val, 1)
        except Exception:
            pass
        return None

    # ══════════════════════════════════════════════════════════════════════
    #  Public API
    # ══════════════════════════════════════════════════════════════════════

    def get_cpu_temperature(self) -> Optional[float]:
        dispatch = {
            "lhm":      self._cpu_temp_lhm,
            "ohm_wmi":  self._cpu_temp_ohm,
            "wmi_acpi": self._cpu_temp_wmi_acpi,
            "ps_acpi":  self._cpu_temp_ps_acpi,
            "psutil":   self._cpu_temp_psutil,
        }
        if self._cpu_method and self._cpu_method in dispatch:
            val = dispatch[self._cpu_method]()
            if val is not None:
                return val
        for name, func in dispatch.items():
            val = func()
            if val is not None:
                self._cpu_method = name
                return val
        return None

    def get_ssd_temperature(self) -> Optional[float]:
        dispatch = {
            "lhm":            self._ssd_temp_lhm,
            "ohm_wmi":        self._ssd_temp_ohm,
            "ps_reliability": self._ssd_temp_ps_reliability,
            "wmi_storage":    self._ssd_temp_wmi_storage,
        }
        if self._ssd_method and self._ssd_method in dispatch:
            val = dispatch[self._ssd_method]()
            if val is not None:
                return val
        for name, func in dispatch.items():
            val = func()
            if val is not None:
                self._ssd_method = name
                return val
        return None

    def read_sensors(self) -> SensorReading:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cpu_percent = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        cpu_temp = self.get_cpu_temperature()
        ssd_temp = self.get_ssd_temperature()

        return SensorReading(
            timestamp=timestamp,
            cpu_percent=round(cpu_percent, 1),
            cpu_temp=round(cpu_temp, 1) if cpu_temp is not None else None,
            ram_percent=round(ram.percent, 1),
            disk_percent=round(disk.percent, 1),
            ssd_temp=round(ssd_temp, 1) if ssd_temp is not None else None,
        )

    def get_system_info(self) -> dict:
        import platform
        cpu_freq = psutil.cpu_freq()
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")

        gpu_name = "N/A"
        try:
            from benchmark import get_gpu_info
            gpu_name = get_gpu_info().get("name", "N/A")
        except Exception:
            pass

        return {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "cpu_name": platform.processor() or "N/A",
            "cpu_cores_physical": psutil.cpu_count(logical=False) or "N/A",
            "cpu_cores_logical": psutil.cpu_count(logical=True) or "N/A",
            "cpu_freq_mhz": round(cpu_freq.current, 0) if cpu_freq else "N/A",
            "ram_total_gb": round(ram.total / (1024 ** 3), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "gpu_name": gpu_name,
            "temp_cpu_method": self._cpu_method or "none",
            "temp_ssd_method": self._ssd_method or "none",
        }

    @property
    def cpu_method_label(self) -> str:
        labels = {
            "lhm": "LibreHardwareMonitor",
            "ohm_wmi": "OHM/LHM WMI",
            "wmi_acpi": "WMI ThermalZone",
            "ps_acpi": "PowerShell ACPI",
            "psutil": "psutil",
        }
        return labels.get(self._cpu_method or "", "Tidak tersedia")

    @property
    def ssd_method_label(self) -> str:
        labels = {
            "lhm": "LibreHardwareMonitor",
            "ohm_wmi": "OHM/LHM WMI",
            "ps_reliability": "StorageReliability",
            "wmi_storage": "WMI Storage",
        }
        return labels.get(self._ssd_method or "", "Tidak tersedia")
