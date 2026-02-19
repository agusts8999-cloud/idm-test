# IDM Test — Hardware Diagnostic Tool for POS

Desktop application for hardware diagnostic testing on Windows POS systems (Windows 10/11).
Runs safe CPU stress tests, monitors hardware parameters, and generates professional PDF reports.

## Features

- **Two-phase testing**: 30s idle monitoring → full load stress
- **Real-time monitoring**: CPU usage, CPU temp, RAM, disk, SSD temp
- **CSV logging** every 5 seconds
- **Auto-generated PNG chart** with temperature trends
- **Professional PDF report** with system info, statistics, and pass/fail verdict
- **Safe for POS**: lightweight stress that won't damage hardware

## Requirements

- Python 3.10+
- Windows 10/11

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Compile to EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py
```

The compiled `main.exe` will be in the `dist/` folder. Rename to `idm-test.exe` for distribution.

To include a custom icon:

```bash
pyinstaller --onefile --windowed --icon=icon.ico --name=idm-test main.py
```

## Output Files (saved to Desktop)

| File                    | Description              |
|-------------------------|--------------------------|
| `idm-test-log.csv`     | Raw sensor data log      |
| `idm-test-cpu-temp.png`| CPU temperature chart    |
| `idm-test-report.pdf`  | Full diagnostic report   |

## Status Evaluation

| Status  | Condition                          |
|---------|------------------------------------|
| PASS    | CPU Temp < 75°C                    |
| WARNING | CPU Temp 75–85°C                   |
| FAIL    | CPU Temp > 85°C                    |

If temperature sensors are unavailable, CPU usage is used as fallback.

## Project Structure

```
IDM-TEST/
├── main.py           # GUI application entry point
├── monitor.py        # Hardware monitoring (psutil + WMI)
├── stress.py         # Safe CPU stress engine
├── reporter.py       # CSV, chart, and PDF generation
├── requirements.txt  # Python dependencies
└── README.md
```
