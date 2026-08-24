# DMX Derby Controller

A small Tkinter GUI to control a DMX derby/laser fixture over a USB-DMX adapter — one slider per channel, live plain-text readout of what each value actually does, and a blackout button.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- One slider per DMX channel (9-channel mode), each showing a description of the current value (e.g. `114 | Derby + Laser`) instead of a raw number.
- Non-blocking connect: opening the serial port runs in a background thread, so the GUI never freezes while connecting.
- Detects connection loss (e.g. adapter unplugged) during operation and reports it instead of failing silently.
- One-click blackout

## Requirements

- Python 3.10+ as installed through [requirements.txt](requirements.txt)
- A USB-DMX adapter that shows up as a serial (COM) port

## Installation

```bash
git clone https://github.com/jesajaw/DMX-Razor-Derby-Controller
cd DMX-Razor-Derby-Controller
pip install -r requirements.txt
```

## Usage

```bash
python DMX-Controller.py
```

1. Select the COM port your USB-DMX adapter is connected to.
2. Click **Connect**.
3. Move the sliders — changes are sent continuously (~33 Hz) while connected
4. **BLACKOUT** sets all channels to 0 immediately.
5. **Disconnect** stops sending and closes the port.

## Channel Layout

| Channel | Function              |
|---------|-----------------------|
| 1       | Show Select           |
| 2       | Speed                 |
| 3       | Derby Color           |
| 4       | Derby Strobe          |
| 5       | Derby Motor           |
| 6       | Pattern               |
| 7       | Laser Mode            |
| 8       | Laser Strobe          |
| 9       | Laser Rotation        |

Value ranges and their meaning per channel are implemented in
`DMXGuiApp.describe()` and are specific to the fixture this was
originally written for — adjust them to match your device's DMX chart.

## Limitations

- DMX512 is a unidirectional protocol: the controller has no way to confirm that a fixture is actually receiving data, only that the USB-DMX adapter itself is reachable over serial.
- Tested on Windows with a generic USB-DMX (FTDI-based) adapter.

## License

MIT — see [LICENSE](LICENSE).
