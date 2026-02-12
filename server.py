"""
server.py

FastAPI back-end for the Barter Charter simulation.

Responsibilities:
- Hold a single global GameState.
- Hold a single ExcelLogger for barter_charter.xlsx.
- Expose HTTP endpoints for:
    * Initializing the game (commodities, teams, portfolios)
    * Starting / ending rounds
    * Recording trades (multi-commodity)
    * Exposing teams, leaderboard, commodities
    * Exposing price history for live charts
    * Exposing trades list for the Master Console log

Price behaviour:
- After EACH trade:
    * Apply the trade to holdings
    * Update ratios based on net demand
    * Update prices from ratios
    * Record a price snapshot in price_history
- At end of round:
    * Apply penalties (no-trade + min/max)
    * Log the current commodity state and portfolios to Excel
"""

from typing import List, Optional, Dict, Any
import threading

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from game_engine import (
    GameState,
    Commodity,
    Team,
    update_prices_from_ratios,
    generate_initial_portfolios_with_ranges,
    update_ratios_auto,
    apply_round_penalties,
)
from excel_logger import ExcelLogger


# ---------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------

app = FastAPI(title="Barter Charter Server")

# CORS configuration so browser JS (including ngrok) can call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # open for event usage
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],          # includes custom 'ngrok-skip-browser-warning'
)


# Global state (single game instance for the event)
game_state: Optional[GameState] = None
excel_logger: Optional[ExcelLogger] = None
# Global set to remember which rounds have already been ended
ended_rounds = set()


# Global price history for charts
# price_history[commodity_name] = list of dicts:
#   { "trade_index": int, "round": int, "price": float }
price_history: Dict[str, List[Dict[str, Any]]] = {}

# Global trade counter (for indexing price snapshots)
global_trade_counter: int = 0

# Lock to avoid race conditions when multiple terminals submit trades
state_lock = threading.Lock()


# ---------------------------------------------------------------------
# Pydantic models for requests
# ---------------------------------------------------------------------

class CommodityInput(BaseModel):
    name: str
    ratio: int  # base_ratio (units equivalent to 1 base)


class InitGameRequest(BaseModel):
    commodities: List[CommodityInput]
    base_commodity: str
    num_teams: int
    target_value_hint: float  # e.g. 2000000 (20 lakhs)


class StartRoundRequest(BaseModel):
    news: str


class TradeLeg(BaseModel):
    commodity: str
    qty: int


class TradeRequest(BaseModel):
    from_team: str
    to_team: str
    give: List[TradeLeg]      # multi-commodity allowed
    receive: List[TradeLeg]   # multi-commodity allowed


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def ensure_game_initialized():
    if game_state is None:
        raise HTTPException(
            status_code=400,
            detail="Game is not initialized. Call /admin/init_game first."
        )


def record_price_snapshot() -> None:
    """
    Take the current prices of all commodities and append to price_history.
    Uses the global_trade_counter as x-axis index.
    """
    global game_state, price_history, global_trade_counter

    if game_state is None:
        return

    round_no = game_state.current_round
    for cname, c in game_state.commodities.items():
        if cname not in price_history:
            price_history[cname] = []
        price_history[cname].append({
            "trade_index": global_trade_counter,
            "round": round_no,
            "price": c.price
        })


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/admin/init_game")
def init_game(req: InitGameRequest):
    """
    Initialize the game:
    - Define commodities and ratios
    - Set base commodity
    - Create teams
    - Generate initial portfolios (equal value, integer-only)
    - Create Excel file and log Round 0
    - Initialize price history with snapshot 0
    """
    global game_state, excel_logger, price_history, global_trade_counter

    with state_lock:
        if req.num_teams <= 0:
            raise HTTPException(status_code=400, detail="num_teams must be positive.")
        if not req.commodities:
            raise HTTPException(status_code=400, detail="commodities list cannot be empty.")

        # Create new GameState
        gs = GameState()

        # Add commodities
        for ci in req.commodities:
            if ci.ratio <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid ratio for {ci.name}. Must be positive int."
                )
            if ci.name in gs.commodities:
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate commodity name: {ci.name}"
                )
            gs.commodities[ci.name] = Commodity(
                name=ci.name,
                price=0.0,        # will be set from ratios
                base_ratio=ci.ratio
            )

        # Base commodity must exist
        if req.base_commodity not in gs.commodities:
            raise HTTPException(
                status_code=400,
                detail=f"Base commodity '{req.base_commodity}' not in commodities."
            )

        gs.base_commodity = req.base_commodity
        # Ensure base has ratio 1
        gs.commodities[req.base_commodity].base_ratio = 1

        # Convert ratios to prices
        update_prices_from_ratios(gs)

        # Create teams
        gs.teams = {}
        for i in range(req.num_teams):
            name = f"Team {i + 1}"
            gs.teams[name] = Team(name=name)

        # Round 0 (initial portfolios)
        gs.current_round = 0

        # Generate portfolios (equal value, integer-only, min/max logic)
        common_value = generate_initial_portfolios_with_ranges(
            gs,
            target_value_hint=req.target_value_hint
        )

        # Initialize Excel logger and log Round 0
        excel_logger = ExcelLogger("barter_charter.xlsx")
        excel_logger.log_commodities(gs.commodities, round_no=0)
        excel_logger.log_portfolios_round(gs)

        # Initialize global state
        game_state = gs

        # Initialize price history & trade counter
        price_history = {cname: [] for cname in gs.commodities.keys()}
        global_trade_counter = 0
        record_price_snapshot()  # snapshot 0

        return {
            "message": "Game initialized.",
            "num_teams": req.num_teams,
            "base_commodity": req.base_commodity,
            "common_portfolio_value": common_value
        }


@app.get("/meta/commodities")
def get_commodities():
    """
    Get current commodity definitions and prices.
    """
    ensure_game_initialized()
    gs = game_state
    return {
        "commodities": [
            {
                "name": c.name,
                "ratio_vs_base": c.base_ratio,
                "price_rs": c.price,
                # Initial allocation band (may not exist for old games)
                "alloc_min_units": getattr(c, "alloc_min_units", None),
                "alloc_max_units": getattr(c, "alloc_max_units", None),
                # Holding band used for penalties
                "min_units": getattr(c, "min_units", None),
                "max_units": getattr(c, "max_units", None),
            }
            for c in gs.commodities.values()
        ],
        "base_commodity": gs.base_commodity
    }


@app.get("/state/teams")
def get_teams_state():
    """
    Get current snapshot of all teams (holdings & values).
    """
    ensure_game_initialized()
    gs = game_state
    base = gs.base_commodity
    return {
        "teams": [
            {
                "name": t.name,
                "holdings": t.holdings,
                "value_rs": t.value_rs(gs.commodities),
                "value_base": t.value_in_base(gs.commodities, base)
            }
            for t in gs.teams.values()
        ]
    }


@app.get("/state/leaderboard")
def get_leaderboard():
    """
    Get leaderboard sorted by effective portfolio value (Rs),
    including penalties breakdown.
    """
    ensure_game_initialized()
    gs = game_state
    base = gs.base_commodity
    leaders = gs.leaderboard()

    result = []
    for t in leaders:
        raw_val = t.value_rs(gs.commodities)
        penalty = gs.penalties_rs.get(t.name, 0.0)
        effective = raw_val - penalty
        result.append({
            "name": t.name,
            "value_rs": raw_val,
            "penalty_rs": penalty,
            "effective_value_rs": effective,
            "value_base": t.value_in_base(gs.commodities, base)
        })

    return {"leaderboard": result}


@app.get("/state/trades")
def get_trades(round: Optional[int] = Query(None)):
    """
    Return list of trades, optionally filtered by round.

    Response:
    {
      "trades": [
        {
          "index": 1,
          "round_no": 1,
          "from_team": "Team 1",
          "to_team": "Team 5",
          "give": {"Gold": 10, "Oil": 5},
          "receive": {"Land": 2}
        },
        ...
      ]
    }
    """
    ensure_game_initialized()
    gs = game_state

    out = []
    for idx, tr in enumerate(gs.trades):
        if round is not None and tr.round_no != round:
            continue
        out.append({
            "index": idx + 1,
            "round_no": tr.round_no,
            "from_team": tr.from_team,
            "to_team": tr.to_team,
            "give": tr.give,
            "receive": tr.receive,
        })

    return {"trades": out}


@app.get("/state/prices")
def get_price_history():
    """
    Return price history for each commodity.

    Response structure:
    {
      "price_history": {
         "Land": [{"trade_index": 0, "round": 0, "price": 1000.0}, ...],
         "Gold": [...],
         ...
      }
    }
    """
    ensure_game_initialized()
    return {"price_history": price_history}


@app.post("/round/start")
def start_round(req: StartRoundRequest):
    """
    Start a new round with a news headline.
    """
    ensure_game_initialized()
    gs = game_state

    with state_lock:
        gs.start_round(req.news)
        current_round = gs.current_round

    return {
        "message": f"Round {current_round} started.",
        "round": current_round,
        "news": req.news
    }


@app.post("/trade")
def post_trade(req: TradeRequest):
    """
    Record a trade (multi-commodity):

    - Validates quantities > 0.
    - Uses GameState.record_trade to enforce:
        * Only 1 trade per pair per round.
    - After each trade:
        * Recompute ratios from net demand (update_ratios_auto)
        * Recompute prices from ratios (update_prices_from_ratios)
        * Increment global_trade_counter
        * Append price snapshot to price_history
    - Logs trade to Excel.

    Any unexpected error is caught and returned as a 400
    instead of a 500, and printed in the server console.
    """
    ensure_game_initialized()
    global game_state, excel_logger, global_trade_counter

    gs = game_state

    try:
        # ------------------ build dicts from legs ------------------ #
        give_dict: Dict[str, int] = {}
        for leg in req.give:
            if leg.qty <= 0:
                raise HTTPException(status_code=400, detail="Quantities must be positive.")
            give_dict[leg.commodity] = give_dict.get(leg.commodity, 0) + leg.qty

        receive_dict: Dict[str, int] = {}
        for leg in req.receive:
            if leg.qty <= 0:
                raise HTTPException(status_code=400, detail="Quantities must be positive.")
            receive_dict[leg.commodity] = receive_dict.get(leg.commodity, 0) + leg.qty

        # ------------------ apply trade under lock ------------------ #
        with state_lock:
            try:
                trade = gs.record_trade(
                    from_team=req.from_team,
                    to_team=req.to_team,
                    give=give_dict,
                    receive=receive_dict
                )
            except ValueError as e:
                # expected game-rule errors: show as 400 for UI
                raise HTTPException(status_code=400, detail=str(e))

            # Update ratios based on net demand in this round
            update_ratios_auto(gs)
            # Recompute rupee prices from updated ratios
            update_prices_from_ratios(gs)

            # Update price history
            global_trade_counter += 1
            record_price_snapshot()

        # Log trade to Excel if logger exists
        if excel_logger is not None:
            # ExcelLogger.log_trade expects only the Trade object
            excel_logger.log_trade(trade)

        # If we reach here, trade succeeded
        return {
            "ok": True,
            "round": trade.round_no,
            "from_team": trade.from_team,
            "to_team": trade.to_team,
            "give": trade.give,
            "receive": trade.receive
        }

    except HTTPException:
        # Re-raise explicit HTTP errors unchanged
        raise
    except Exception as e:
        # Catch-all for unexpected bugs; avoid 500s
        import traceback
        print("\n=== UNEXPECTED ERROR IN /trade ===")
        traceback.print_exc()
        print("==================================\n")
        raise HTTPException(
            status_code=400,
            detail=f"Trade processing failed: {e}"
        )


@app.post("/round/end")
def end_round():
    """
    End the current round.

    Behaviour:
    - Applies penalties ONCE per round:
        * 10% of portfolio if no trades in this round
        * 10% of portfolio if min/max quantity violated
    - Logs current commodities and portfolios (with prices) to Excel.
    - If called again for the same round number, NO new penalties
      are applied and a message is returned.
    """
    ensure_game_initialized()
    global excel_logger, ended_rounds
    gs = game_state

    with state_lock:
        if gs.current_round == 0:
            raise HTTPException(status_code=400, detail="No active round.")

        round_no = gs.current_round

        # If we already ended this round, do NOT re-apply penalties
        if round_no in ended_rounds:
            return {
                "message": f"Round {round_no} was already ended earlier. "
                           f"No additional penalties or logging applied."
            }

        # Apply no-trade & min/max penalties for this round
        apply_round_penalties(gs, round_no)

        # Log commodities and portfolios for this round
        if excel_logger is not None:
            excel_logger.log_commodities(gs.commodities, round_no=round_no)
            excel_logger.log_portfolios_round(gs)

        # Mark this round as ended so we don't hit it twice
        ended_rounds.add(round_no)

    return {"message": f"Round {round_no} ended. Ratios, penalties and portfolios logged."}
