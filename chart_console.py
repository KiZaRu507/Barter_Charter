"""
chart_console.py

Standalone live market chart viewer for Barter Charter.

- Connects to the FastAPI server's /state/prices endpoint.
- Plots ALL commodities (dynamic) as:
    * 3 charts per row
    * Each chart fairly big & square-ish
    * Indexed prices (base = 100 at first point) so raw Rs are hidden
- Whole figure is inside a scrollable Tkinter canvas so nothing gets cut off.
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import math
import requests

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

# Set this to your server (local or ngrok)
SERVER_URL = "https://unsulfurized-repellantly-terisa.ngrok-free.dev"

REFRESH_INTERVAL = 15  # seconds
NUM_COLS = 3          # charts per row
FIG_WIDTH_INCH = 12   # overall figure width
FIG_HEIGHT_PER_ROW = 3.5  # height per row (inches)


# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------

def api_get(path: str):
    """
    Simple GET wrapper that also adds ngrok header if needed.
    """
    url = f"{SERVER_URL}{path}"
    headers = {}
    if "ngrok-free" in SERVER_URL:
        headers["ngrok-skip-browser-warning"] = "true"

    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[chart_console] GET {path} error:", e)
        return {"error": str(e)}


# -------------------------------------------------------------------
# Tkinter App
# -------------------------------------------------------------------

class MarketChartsApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Barter Charter - Market Charts")

        # Top title
        title_lbl = ttk.Label(
            root,
            text="Barter Charter – Live Market Charts",
            font=("Arial", 16, "bold")
        )
        title_lbl.pack(anchor="w", padx=10, pady=(8, 0))

        subtitle_lbl = ttk.Label(
            root,
            text="Indexed Prices (Base = 100 at first trade)",
            font=("Arial", 10)
        )
        subtitle_lbl.pack(anchor="w", padx=10, pady=(0, 8))

        # Scrollable canvas container
        container = ttk.Frame(root)
        container.pack(fill="both", expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(container, highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        hbar = ttk.Scrollbar(container, orient="horizontal", command=self.canvas.xview)

        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        hbar.pack(side="bottom", fill="x")

        # Inner frame inside canvas
        self.inner = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        # Whenever inner frame size changes, update scrollregion
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        # Matplotlib figure inside inner frame
        self.figure = Figure(figsize=(FIG_WIDTH_INCH, FIG_HEIGHT_PER_ROW), dpi=100)
        self.fig_canvas = FigureCanvasTkAgg(self.figure, master=self.inner)
        self.fig_widget = self.fig_canvas.get_tk_widget()
        self.fig_widget.pack(fill="both", expand=True)

        # Live indicator
        self.status_lbl = ttk.Label(
            root,
            text="Live",
            foreground="green",
            font=("Arial", 10, "bold")
        )
        self.status_lbl.pack(anchor="ne", padx=10, pady=(0, 5))

        # Background refresh loop
        self.running = True
        t = threading.Thread(target=self.refresh_loop, daemon=True)
        t.start()

    # -----------------------------------------------------------------
    # Background loop
    # -----------------------------------------------------------------

    def refresh_loop(self):
        """
        Background thread: periodically refresh charts.
        """
        while self.running:
            self.refresh_charts()
            time.sleep(REFRESH_INTERVAL)

    # -----------------------------------------------------------------
    # Core refresh function
    # -----------------------------------------------------------------

    def refresh_charts(self):
        data = api_get("/state/prices")
        if "error" in data:
            return

        ph = data.get("price_history", {})
        if not ph:
            return

        commodity_names = sorted(ph.keys())
        n = len(commodity_names)

        print(f"[chart_console] price_history has {n} commodities:", commodity_names)

        # Compute rows & resize figure height accordingly
        rows = max(1, math.ceil(n / NUM_COLS))
        new_height = max(FIG_HEIGHT_PER_ROW * rows, FIG_HEIGHT_PER_ROW)
        self.figure.set_size_inches(FIG_WIDTH_INCH, new_height, forward=True)

        # Clear and create new subplots grid
        self.figure.clear()
        axes = self.figure.subplots(rows, NUM_COLS, squeeze=False)
        flat_axes = [ax for row_axes in axes for ax in row_axes]

        for idx, cname in enumerate(commodity_names):
            ax = flat_axes[idx]
            series = ph.get(cname, [])
            if not series:
                ax.set_title(cname)
                ax.set_xticks([])
                ax.set_yticks([])
                continue

            xs = [p["trade_index"] for p in series]
            prices = [p["price"] for p in series]

            if not prices:
                ax.set_title(cname)
                ax.set_xticks([])
                ax.set_yticks([])
                continue

            base_price = prices[0] if prices[0] > 0 else 1.0
            ys = [(p / base_price) * 100.0 for p in prices]

            ax.plot(xs, ys)
            ax.set_title(cname, fontsize=12)
            ax.set_xlabel("Trades", fontsize=9)

            # Hide numeric y-axis labels so actual Rs are not visible
            ax.set_yticklabels([])
            ax.tick_params(axis='y', length=0)
            ax.tick_params(axis='x', labelsize=8)

        # Hide any unused axes (if grid bigger than #commodities)
        for j in range(len(commodity_names), len(flat_axes)):
            flat_axes[j].axis("off")

        self.figure.tight_layout()
        self.fig_canvas.draw()

        # Update scrollregion after figure redraw
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = MarketChartsApp(root)
    root.mainloop()
