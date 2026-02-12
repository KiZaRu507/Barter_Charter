"""
master_console.py

Admin Console for Barter Charter.

Features:
- Init Game directly from console (uses default 10 commodities)
- Start Round / End Round controls
- TAB 1: Leaderboard
- TAB 2: Commodities & Bands (with Initial Min/Max and Holding Min/Max)
- TAB 3: Trade Log (per round, via /state/trades?round=X)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import requests


# -----------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------

# If master console runs on same machine as server:
# SERVER_URL = "http://127.0.0.1:8000"
# For ngrok:
SERVER_URL = "https://unsulfurized-repellantly-terisa.ngrok-free.dev"


# -----------------------------------------------------------
# Helper API functions
# -----------------------------------------------------------

def api_get(path: str):
    try:
        r = requests.get(f"{SERVER_URL}{path}")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def api_post(path: str, payload=None):
    try:
        r = requests.post(f"{SERVER_URL}{path}", json=payload)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


# -----------------------------------------------------------
# Tkinter Main App
# -----------------------------------------------------------

class MasterConsoleApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Barter Charter - Master Console")
        self.root.geometry("1500x900")

        # ===================================================
        # TOP: INIT GAME + ROUND CONTROLS
        # ===================================================
        self.top_frame = ttk.Frame(root)
        self.top_frame.pack(fill="x", padx=10, pady=5)

        # ---------------- Init Game Frame ------------------
        self.init_frame = ttk.LabelFrame(self.top_frame, text="Init Game")
        self.init_frame.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        ttk.Label(self.init_frame, text="Num Teams:").grid(row=0, column=0, padx=5, pady=3, sticky="e")
        self.num_teams_var = tk.StringVar(value="85")
        self.num_teams_entry = ttk.Entry(self.init_frame, width=8, textvariable=self.num_teams_var)
        self.num_teams_entry.grid(row=0, column=1, padx=5, pady=3, sticky="w")

        ttk.Label(self.init_frame, text="Target Value (Rs):").grid(row=0, column=2, padx=5, pady=3, sticky="e")
        self.target_value_var = tk.StringVar(value="2000000")  # 20 lakhs
        self.target_value_entry = ttk.Entry(self.init_frame, width=12, textvariable=self.target_value_var)
        self.target_value_entry.grid(row=0, column=3, padx=5, pady=3, sticky="w")

        ttk.Label(self.init_frame, text="Base Commodity:").grid(row=0, column=4, padx=5, pady=3, sticky="e")
        self.base_commodity_var = tk.StringVar(value="Silver")
        self.base_commodity_entry = ttk.Entry(self.init_frame, width=12, textvariable=self.base_commodity_var)
        self.base_commodity_entry.grid(row=0, column=5, padx=5, pady=3, sticky="w")

        ttk.Button(
            self.init_frame,
            text="Init with Default Commodities",
            command=self.init_game_default
        ).grid(row=0, column=6, padx=10, pady=3)

        # ---------------- Round Controls Frame -------------
        self.round_frame = ttk.LabelFrame(self.top_frame, text="Round Controls")
        self.round_frame.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        ttk.Label(self.round_frame, text="News/Event:").grid(row=0, column=0, padx=5, pady=3, sticky="e")
        self.news_entry = ttk.Entry(self.round_frame, width=60)
        self.news_entry.grid(row=0, column=1, padx=5, pady=3, sticky="we")

        ttk.Button(self.round_frame, text="Start Round", command=self.start_round)\
            .grid(row=0, column=2, padx=5, pady=3)
        ttk.Button(self.round_frame, text="End Round", command=self.end_round)\
            .grid(row=0, column=3, padx=5, pady=3)

        self.round_frame.columnconfigure(1, weight=1)

        # ===================================================
        # NOTEBOOK WITH TABS
        # ===================================================
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_leaderboard = ttk.Frame(self.notebook)
        self.tab_commodities = ttk.Frame(self.notebook)
        self.tab_log = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_leaderboard, text="Leaderboard")
        self.notebook.add(self.tab_commodities, text="Commodities & Bands")
        self.notebook.add(self.tab_log, text="Trade Log")

        # ===================================================
        # TAB 1: LEADERBOARD
        # ===================================================
        self._build_leaderboard_tab()

        # ===================================================
        # TAB 2: COMMODITIES & BANDS
        # ===================================================
        self._build_commodities_tab()

        # ===================================================
        # TAB 3: TRADE LOG
        # ===================================================
        self._build_log_tab()

    # -------------------------------------------------------
    # TAB BUILDERS
    # -------------------------------------------------------

    def _build_leaderboard_tab(self):
        frame = ttk.Frame(self.tab_leaderboard)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Treeview + scrollbar
        self.lb_tree = ttk.Treeview(
            frame,
            columns=("team", "value_rs", "penalty_rs", "effective_rs", "value_base"),
            show="headings",
            height=20
        )
        self.lb_tree.heading("team", text="Team")
        self.lb_tree.heading("value_rs", text="Value (Rs)")
        self.lb_tree.heading("penalty_rs", text="Penalty (Rs)")
        self.lb_tree.heading("effective_rs", text="Effective (Rs)")
        self.lb_tree.heading("value_base", text="Base Units")

        self.lb_tree.column("team", width=120, anchor="w")
        self.lb_tree.column("value_rs", width=120, anchor="e")
        self.lb_tree.column("penalty_rs", width=120, anchor="e")
        self.lb_tree.column("effective_rs", width=130, anchor="e")
        self.lb_tree.column("value_base", width=120, anchor="e")

        self.lb_tree.pack(side="left", fill="both", expand=True)

        lb_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.lb_tree.yview)
        self.lb_tree.configure(yscrollcommand=lb_scroll.set)
        lb_scroll.pack(side="right", fill="y")

        btn_frame = ttk.Frame(self.tab_leaderboard)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Refresh Leaderboard", command=self.refresh_leaderboard)\
            .pack(side="left", padx=5)

    def _build_commodities_tab(self):
        frame = ttk.Frame(self.tab_commodities)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.com_tree = ttk.Treeview(
            frame,
            columns=(
                "name",
                "ratio",
                "price",
                "alloc_min",
                "alloc_max",
                "hold_min",
                "hold_max"
            ),
            show="headings",
            height=20
        )

        self.com_tree.heading("name", text="Commodity")
        self.com_tree.heading("ratio", text="Ratio vs Base")
        self.com_tree.heading("price", text="Price (Rs)")
        self.com_tree.heading("alloc_min", text="Initial Min Units")
        self.com_tree.heading("alloc_max", text="Initial Max Units")
        self.com_tree.heading("hold_min", text="Holding Min Units")
        self.com_tree.heading("hold_max", text="Holding Max Units")

        self.com_tree.column("name", width=110, anchor="w")
        self.com_tree.column("ratio", width=110, anchor="center")
        self.com_tree.column("price", width=110, anchor="e")
        self.com_tree.column("alloc_min", width=130, anchor="e")
        self.com_tree.column("alloc_max", width=130, anchor="e")
        self.com_tree.column("hold_min", width=130, anchor="e")
        self.com_tree.column("hold_max", width=130, anchor="e")

        self.com_tree.pack(side="left", fill="both", expand=True)

        com_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.com_tree.yview)
        self.com_tree.configure(yscrollcommand=com_scroll.set)
        com_scroll.pack(side="right", fill="y")

        # Bottom: refresh button + legend
        bottom = ttk.Frame(self.tab_commodities)
        bottom.pack(fill="x", padx=5, pady=5)

        ttk.Button(bottom, text="Refresh Commodities", command=self.refresh_commodities)\
            .pack(side="left", padx=5)

        legend_text = (
            "Initial Min/Max = band used while creating starting portfolios\n"
            "Holding Min/Max  = band used to check penalties during game"
        )
        ttk.Label(bottom, text=legend_text, foreground="gray").pack(side="left", padx=10)

    def _build_log_tab(self):
        top = ttk.Frame(self.tab_log)
        top.pack(fill="x", padx=5, pady=5)

        ttk.Label(top, text="Round #:").pack(side="left", padx=5, pady=3)
        self.log_round_var = tk.StringVar(value="1")
        self.log_round_entry = ttk.Entry(top, width=6, textvariable=self.log_round_var)
        self.log_round_entry.pack(side="left", padx=5, pady=3)

        ttk.Button(top, text="Refresh Trade Log", command=self.refresh_trade_log)\
            .pack(side="left", padx=10, pady=3)

        # Text + scrollbar
        body = ttk.Frame(self.tab_log)
        body.pack(fill="both", expand=True, padx=5, pady=5)

        self.log_text = tk.Text(body, wrap="none")
        self.log_text.pack(side="left", fill="both", expand=True)

        log_scroll = ttk.Scrollbar(body, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")

    # -------------------------------------------------------
    # INIT GAME
    # -------------------------------------------------------

    def init_game_default(self):
        """
        Init game using the hard-coded 10 commodities and
        the parameters from the init frame.
        """
        try:
            num_teams = int(self.num_teams_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Num Teams must be an integer.")
            return

        try:
            target_value = float(self.target_value_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Target Value must be a number.")
            return

        base_commodity = self.base_commodity_var.get().strip()
        if not base_commodity:
            messagebox.showerror("Error", "Base Commodity cannot be empty.")
            return

        # Default commodity list
        commodities = [
            {"name": "Silver",      "ratio": 1},
            {"name": "Uranium",      "ratio": 3},
            {"name": "Silicon",       "ratio": 5},
            {"name": "O₂ Cylinder",   "ratio": 8},
            {"name": "Crude oil",   "ratio": 12},
            {"name": "Ethanol", "ratio": 18},
            {"name": "Tobacco",      "ratio": 24},
            {"name": "Cocoa",      "ratio": 30},
            {"name": "Honey",      "ratio": 38},
            {"name": "Rubber",      "ratio": 45},
        ]

        payload = {
            "commodities": commodities,
            "base_commodity": base_commodity,
            "num_teams": num_teams,
            "target_value_hint": target_value
        }

        resp = api_post("/admin/init_game", payload)
        if "error" in resp:
            messagebox.showerror("Init Game Error", resp["error"])
        else:
            messagebox.showinfo("Init Game", str(resp))

    # -------------------------------------------------------
    # ROUND CONTROLS
    # -------------------------------------------------------

    def start_round(self):
        news_text = self.news_entry.get().strip()
        if not news_text:
            messagebox.showerror("Error", "Enter a news/event headline.")
            return

        resp = api_post("/round/start", {"news": news_text})
        if "error" in resp:
            messagebox.showerror("Error", resp["error"])
        else:
            messagebox.showinfo("Start Round", str(resp))

    def end_round(self):
        resp = api_post("/round/end")
        if "error" in resp:
            messagebox.showerror("Error", resp["error"])
        else:
            messagebox.showinfo("End Round", str(resp))

    # -------------------------------------------------------
    # LEADERBOARD
    # -------------------------------------------------------

    def refresh_leaderboard(self):
        self.lb_tree.delete(*self.lb_tree.get_children())
        data = api_get("/state/leaderboard")

        if "error" in data:
            messagebox.showerror("Error", data["error"])
            return

        if "leaderboard" not in data:
            return

        for item in data["leaderboard"]:
            self.lb_tree.insert("", "end", values=(
                item["name"],
                round(item["value_rs"], 2),
                round(item.get("penalty_rs", 0.0), 2),
                round(item.get("effective_value_rs", item["value_rs"]), 2),
                round(item["value_base"], 2)
            ))

    # -------------------------------------------------------
    # COMMODITIES
    # -------------------------------------------------------

    def refresh_commodities(self):
        self.com_tree.delete(*self.com_tree.get_children())
        data = api_get("/meta/commodities")

        if "error" in data:
            messagebox.showerror("Error", data["error"])
            return

        if "commodities" not in data:
            return

        for c in data["commodities"]:
            name = c.get("name", "")
            ratio = c.get("ratio_vs_base", "")
            price = c.get("price_rs", 0.0)

            alloc_min = c.get("alloc_min_units", None)  # initial band
            alloc_max = c.get("alloc_max_units", None)
            hold_min = c.get("min_units", None)         # holding band
            hold_max = c.get("max_units", None)

            def fmt(v):
                return "" if v is None else str(v)

            self.com_tree.insert("", "end", values=(
                name,
                ratio,
                round(price, 2),
                fmt(alloc_min),
                fmt(alloc_max),
                fmt(hold_min),
                fmt(hold_max),
            ))

    # -------------------------------------------------------
    # TRADE LOG
    # -------------------------------------------------------

    def refresh_trade_log(self):
        """
        Tries to fetch trades for a given round from /state/trades?round=X.
        If server does not have this endpoint, it will show the error text.
        """
        self.log_text.delete("1.0", tk.END)
        round_str = self.log_round_var.get().strip()
        try:
            round_no = int(round_str)
        except ValueError:
            self.log_text.insert(tk.END, "Round must be an integer.\n")
            return

        data = api_get(f"/state/trades?round={round_no}")
        if "error" in data:
            self.log_text.insert(tk.END, f"Error calling /state/trades: {data['error']}\n")
            return

        trades = data.get("trades", [])
        if not trades:
            self.log_text.insert(tk.END, f"No trades found for round {round_no}.\n")
            return

        for t in trades:
            line = (
                f"Round {t.get('round')} | "
                f"{t.get('from_team')} -> {t.get('to_team')} | "
                f"Give: {t.get('give')} | "
                f"Receive: {t.get('receive')}\n"
            )
            self.log_text.insert(tk.END, line)


# -----------------------------------------------------------
# Run the Tkinter App
# -----------------------------------------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = MasterConsoleApp(root)
    root.mainloop()
