"""
DMX Derby Controller
=====================

Tkinter GUI to control a Razor Derby over a USB-DMX adapter
(RS485, 250000 baud, 2 stop bits).

Threading model
----------------
- Connecting (serial.Serial(...)) runs in a worker thread since opening a COM port can block
- DMX send cycle runs in its own background thread while connected
- All GUI updates from background threads go through root.after(...), since Tkinter widgets must only be touched from main thread
- Write failures during the send loop (e.g. adapter unplugged) are caught and reported as a connection loss. This checks the USB link to the adapter, not the DMX cable itself -- DMX512 is unidirectional and gives no feedback from the fixture end.
"""

import threading
import time
import serial, serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox


# Theme — uncomment ONE block, comment out the others
# dark grey / purple
COLOR_BG = "#1e1e24"; COLOR_BG_LIGHT = "#2a2a33"; COLOR_FG = "#e0dff0"; COLOR = "#9b59d9"; COLOR_DARK = "#6c3fa0"; COLOR_STATUS_TEXT = "#c9a6f5"

# dark grey / blue
# COLOR_BG = "#1e1e24"; COLOR_BG_LIGHT = "#2a2a33"; COLOR_FG = "#e0dff0"; COLOR = "#4a90d9"; COLOR_DARK = "#2f5f9e"; COLOR_STATUS_TEXT = "#a6c9f5"

# black / white
# COLOR_BG = "#000000"; COLOR_BG_LIGHT = "#1a1a1a"; COLOR_FG = "#ffffff"; COLOR = "#ffffff"; COLOR_DARK = "#808080"; COLOR_STATUS_TEXT = "#d9d9d9"


# Fixed cell size so the layout never reflows when status text changes
# (avoids jank while dragging sliders).
CELL_WIDTH = 260
CELL_HEIGHT = 90
STATUS_LABEL_CHARS = 32

CHANNEL_COUNT = 9
UNIVERSE_SIZE = 513  # channel 0 unused, DMX starts at 1
SEND_INTERVAL_S = 0.03  # ca. 33 Hz


class DMXController:
    """Wraps the serial DMX512 link to a USB-DMX adapter."""

    def __init__(self, port: str):
        self.ser = serial.Serial(
            port=port,
            baudrate=250000,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO,
        )
        self.data = bytearray(UNIVERSE_SIZE)

    def set_channel(self, channel: int, value: int) -> None:
        if 1 <= channel <= 512:
            self.data[channel] = max(0, min(255, value))

    def send(self) -> None:
        """Sends one DMX frame, including break / mark-after-break."""
        self.ser.break_condition = True
        time.sleep(0.0001)
        self.ser.break_condition = False
        time.sleep(0.000012)
        self.ser.write(self.data)

    def stop(self) -> None:
        """Zeroes all channels, sends once, then closes the port."""
        for i in range(1, UNIVERSE_SIZE):
            self.data[i] = 0
        try:
            self.send()
            self.ser.close()
        except Exception:
            pass


class DMXGuiApp:
    """Tkinter UI for the DMX Derby Controller."""

    CHANNEL_NAMES = [
        "1: Show Select",
        "2: Speed",
        "3: Derby Color",
        "4: Derby Strobe",
        "5: Derby Motor",
        "6: Pattern",
        "7: Laser Mode",
        "8: Laser Strobe",
        "9: Laser Rotation",
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DMX Derby Controller")
        self.root.geometry("850x440")
        self.root.configure(bg=COLOR_BG)

        self.dmx: DMXController | None = None
        self.is_sending = False
        self.channel_labels: dict[int, ttk.Label] = {}
        self.sliders: dict[int, ttk.Scale] = {}

        self._setup_style()
        self._build_connection_bar()
        self._build_channel_grid()

# ------------------------------------------------------------
# channel value -> readable state
# ------------------------------------------------------------
    @staticmethod
    def describe(channel: int, value: int) -> str:
        if channel == 1:
            if value <= 9:    return f"{value} | Manual (Blackout/Ch.3 active)"
            if value <= 44:   return f"{value} | Derby + Laser + Strobe"
            if value <= 79:   return f"{value} | Derby + Strobe"
            if value <= 114:  return f"{value} | Derby + Laser"
            if value <= 149:  return f"{value} | Laser + Strobe"
            if value <= 184:  return f"{value} | Derby Effect"
            if value <= 219:  return f"{value} | Laser Effect"
            return f"{value} | Strobe Effect"
        if channel == 2:
            if value <= 250:  return f"{value} | Speed: {int(value / 250 * 100)}%"
            return f"{value} | Sound Control"
        if channel == 3:
            if value <= 5:    return f"{value} | Off"
            if value <= 20:   return f"{value} | Red"
            if value <= 35:   return f"{value} | Green"
            if value <= 50:   return f"{value} | Blue"
            if value <= 65:   return f"{value} | White"
            if value <= 80:   return f"{value} | Red + Green"
            if value <= 95:   return f"{value} | Red + Blue"
            if value <= 110:  return f"{value} | Red + White"
            if value <= 125:  return f"{value} | Green + Blue"
            if value <= 140:  return f"{value} | Green + White"
            if value <= 155:  return f"{value} | Blue + White"
            if value <= 170:  return f"{value} | Red + Green + Blue"
            if value <= 185:  return f"{value} | Red + Green + White"
            if value <= 200:  return f"{value} | Green + Blue + White"
            if value <= 215:  return f"{value} | RGBW (All)"
            if value <= 230:  return f"{value} | Auto Color (4)"
            return f"{value} | Auto Color (7)"
        if channel == 4:
            if value <= 5:    return f"{value} | Strobe Off"
            return f"{value} | Derby Strobe Rate: {int(value / 255 * 100)}%"
        if channel == 5:
            if value == 0:    return f"{value} | Motor Stopped"
            if value <= 127:  return f"{value} | Manual Position: {value}"
            return f"{value} | Rotation Speed: {int((value - 128) / 127 * 100)}%"
        if channel == 6:
            if value <= 9:    return f"{value} | Blackout"
            return f"{value} | Pattern {min(18, (value - 10) // 14 + 1)}"
        if channel == 7:
            if value <= 9:    return f"{value} | Laser Off"
            if value <= 49:   return f"{value} | Red"
            if value <= 89:   return f"{value} | Green"
            if value <= 129:  return f"{value} | Red + Green"
            if value <= 169:  return f"{value} | Red + Strobe Green"
            if value <= 209:  return f"{value} | Green + Strobe Red"
            return f"{value} | Red + Green (Strobe)"
        if channel == 8:
            if value <= 9:    return f"{value} | Laser Strobe Off"
            if value <= 254:  return f"{value} | Laser Strobe Rate: {int(value / 254 * 100)}%"
            return f"{value} | Sound-Controlled Strobe"
        if channel == 9:
            if value <= 4:    return f"{value} | Stopped"
            if value <= 127:  return f"{value} | Rotation CW"
            if value <= 133:  return f"{value} | Stopped"
            return f"{value} | Rotation CCW"
        return f"{value}"

# ------------------------------------------------------------
# Styling
# ------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=COLOR_BG, foreground=COLOR_FG, font=("Segoe UI", 9))
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabelframe", background=COLOR_BG, foreground=COLOR_FG, bordercolor=COLOR_DARK)
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_FG)

        style.configure("TButton", background=COLOR_BG_LIGHT, foreground=COLOR_FG, bordercolor=COLOR_DARK, focusthickness=1, padding=6)
        style.map("TButton", background=[("active", COLOR_DARK), ("pressed", COLOR)], foreground=[("active", COLOR_FG)])

        style.configure("TCombobox", fieldbackground=COLOR_BG_LIGHT, background=COLOR_BG_LIGHT, foreground=COLOR_FG, arrowcolor=COLOR)
        style.map("TCombobox", fieldbackground=[("readonly", COLOR_BG_LIGHT)])
        style.configure("Horizontal.TScale", background=COLOR_BG, troughcolor=COLOR_BG_LIGHT)

        style.configure("Blackout.TButton", background=COLOR_DARK, foreground=COLOR_FG)
        style.map("Blackout.TButton", background=[("active", COLOR)])

        style.configure("Cell.TFrame", background=COLOR_BG_LIGHT, bordercolor=COLOR_DARK)
        style.configure("Status.TLabel", background=COLOR_BG_LIGHT, foreground=COLOR_STATUS_TEXT, font=("Consolas", 9))
        style.configure("CellTitle.TLabel", background=COLOR_BG_LIGHT, foreground=COLOR_FG, font=("Segoe UI", 9, "bold"))

# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
    def _build_connection_bar(self) -> None:
        bar = ttk.LabelFrame(self.root, text="Connection", padding=10)
        bar.pack(fill="x", padx=10, pady=5)

        ttk.Label(bar, text="Port:").pack(side="left", padx=5)
        ports = [p.device for p in serial.tools.list_ports.comports()] or ["COM3", "COM4"]
        self.port_cb = ttk.Combobox(bar, values=ports, width=15, state="readonly")
        self.port_cb.pack(side="left", padx=5)
        self.port_cb.current(0)

        self.btn_connect = ttk.Button(bar, text="Connect", command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=5)

        ttk.Button(bar, text="BLACKOUT", command=self.blackout,
                   style="Blackout.TButton").pack(side="right", padx=5)

    def _build_channel_grid(self) -> None:
        grid = ttk.LabelFrame(self.root, text="DMX Channels", padding=10)
        grid.pack(fill="both", expand=True, padx=10, pady=5)

        for i in range(CHANNEL_COUNT):
            channel = i + 1
            row, col = divmod(i, 3)
            grid.columnconfigure(col, weight=1)
            self._build_cell(grid, row, col, channel, self.CHANNEL_NAMES[i])

    def _build_cell(self, parent: ttk.Frame, row: int, col: int, channel: int, name: str) -> None:
        cell = ttk.Frame(parent, padding=5, relief="groove", style="Cell.TFrame")
        cell.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        cell.pack_propagate(False)
        cell.configure(width=CELL_WIDTH, height=CELL_HEIGHT)

        ttk.Label(cell, text=name, style="CellTitle.TLabel").pack(anchor="w")

        status = ttk.Label(cell, text="---", style="Status.TLabel",
                            width=STATUS_LABEL_CHARS, anchor="w")
        status.pack(anchor="w", pady=(2, 5), fill="x")
        self.channel_labels[channel] = status

        slider = ttk.Scale(cell, from_=0, to=255, orient="horizontal",
                            command=lambda v, c=channel: self.on_slider_change(c, v))
        slider.set(0)
        slider.pack(fill="x", expand=True)
        self.sliders[channel] = slider

        self.update_display(channel, 0)

# ------------------------------------------------------------
# Sliders
# ------------------------------------------------------------
    def update_display(self, channel: int, value) -> None:
        val_int = int(float(value))
        self.channel_labels[channel].config(text=self.describe(channel, val_int))

    def on_slider_change(self, channel: int, value) -> None:
        val_int = int(float(value))
        self.update_display(channel, val_int)
        if self.dmx:
            self.dmx.set_channel(channel, val_int)

# ------------------------------------------------------------
# Connection (non-blocking)
# ------------------------------------------------------------
    def toggle_connection(self) -> None:
        if not self.is_sending:
            self.btn_connect.config(state="disabled")
            port = self.port_cb.get()
            threading.Thread(target=self._connect_worker, args=(port,), daemon=True).start()
        else:
            self.stop_dmx()
            self.btn_connect.config(text="Connect")

    def _connect_worker(self, port: str) -> None:
        try:
            dmx = DMXController(port)
            for channel, slider in self.sliders.items():
                dmx.set_channel(channel, int(slider.get()))
            self.root.after(0, self._connect_success, dmx)
        except Exception as e:
            self.root.after(0, self._connect_failed, e, port)

    def _connect_success(self, dmx: DMXController) -> None:
        self.dmx = dmx
        self.is_sending = True
        threading.Thread(target=self._send_loop, daemon=True).start()
        self.btn_connect.config(text="Disconnect", state="normal")

    def _connect_failed(self, error: Exception, port: str) -> None:
        self.btn_connect.config(state="normal")
        messagebox.showerror("Error", f"Could not open {port}:\n{error}")

    def _connection_lost(self, error: Exception) -> None:
        self.is_sending = False
        self.dmx = None
        self.btn_connect.config(text="Connect", state="normal")
        messagebox.showerror("Connection Lost", f"DMX connection interrupted:\n{error}")

    def _send_loop(self) -> None:
        """Background send cycle. Exits and reports on write failure
        (e.g. adapter unplugged) instead of failing silently."""
        while self.is_sending:
            try:
                self.dmx.send()
            except (serial.SerialException, OSError) as e:
                self.root.after(0, self._connection_lost, e)
                return
            time.sleep(SEND_INTERVAL_S)

# ------------------------------------------------------------
# Actions
# ------------------------------------------------------------
    def blackout(self) -> None:
        for channel, slider in self.sliders.items():
            slider.set(0)
            self.update_display(channel, 0)
            if self.dmx:
                self.dmx.set_channel(channel, 0)

    def stop_dmx(self) -> None:
        self.is_sending = False
        if self.dmx:
            self.dmx.stop()
            self.dmx = None

    def on_close(self) -> None:
        self.stop_dmx()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = DMXGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()