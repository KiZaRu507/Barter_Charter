"""
game_engine.py

Pure game logic for the Barter Charter simulation.
No UI, no network, no Excel here.

Key concepts:
- Commodity (with base_ratio and derived price)
- Team (holdings of commodities)
- Trade (movement of holdings between teams)
- GameState (all commodities, teams, rounds, trades)

All monetary logic is expressed in terms of a base commodity.
"""

from dataclasses import dataclass, field
from typing import Dict, List

# Hypothetical rupee price of 1 unit of the BASE commodity.
# This is a global assumption – change if you want bigger/smaller nominal values.
BASE_PRICE_RS = 1000.0


# ---------------------------------------------------------------------
# DATA CLASSES
# ---------------------------------------------------------------------

@dataclass
class Commodity:
    """
    Represents one commodity.

    base_ratio:
        "How many units of THIS commodity are equivalent to 1 unit of BASE."
        Example: base = Land
            Land.base_ratio = 1
            Gold.base_ratio = 4  ->  1 Land = 4 Gold units

    price:
        Derived from the base_ratio and BASE_PRICE_RS.
        The engine sets price via update_prices_from_ratios().
    """
    name: str
    price: float        # Rs per unit (derived from ratio + BASE_PRICE_RS)
    base_ratio: int
    min_units: int = 0  # per-team minimum (for initial allocation)
    max_units: int = 0  # per-team maximum (for initial allocation)


@dataclass
class Team:
    """
    Represents a team and its holdings of each commodity.
    """
    name: str
    holdings: Dict[str, int] = field(default_factory=dict)

    def value_rs(self, commodities: Dict[str, Commodity]) -> float:
        """
        Total portfolio value in rupees.
        """
        total = 0.0
        for cname, c in commodities.items():
            qty = self.holdings.get(cname, 0)
            total += qty * c.price
        return total

    def value_in_base(self, commodities: Dict[str, Commodity], base_commodity: str) -> float:
        """
        Convert total holdings into equivalent UNITS OF BASE commodity.

        If base_ratio = r (units of this per 1 base), then:
        - 1 unit of base = 1 base unit
        - 1 unit of commodity i = 1/r base units
        """
        total = 0.0
        for cname, c in commodities.items():
            qty = self.holdings.get(cname, 0)
            if qty == 0:
                continue
            if cname == base_commodity:
                total += qty
            else:
                if c.base_ratio > 0:
                    total += qty / float(c.base_ratio)
        return total


@dataclass
class Trade:
    """
    One trade between two teams in a specific round.
    """
    round_no: int
    from_team: str
    to_team: str
    give: Dict[str, int]     # what from_team gives
    receive: Dict[str, int]  # what from_team gets


@dataclass
class RoundInfo:
    """
    Basic data for a round (mostly for logging / UI).
    """
    round_no: int
    news: str


@dataclass
class GameState:
    """
    All game state lives here:
    - Definitions of commodities
    - Teams and their holdings
    - Base commodity name
    - Trades and rounds
    - Current round number
    - Penalties (rupee value) applied to teams
    """
    commodities: Dict[str, Commodity] = field(default_factory=dict)
    teams: Dict[str, Team] = field(default_factory=dict)
    base_commodity: str = ""
    trades: List[Trade] = field(default_factory=list)
    rounds: List[RoundInfo] = field(default_factory=list)
    current_round: int = 0
    penalties_rs: Dict[str, float] = field(default_factory=dict)


    def start_round(self, news: str):
        """
        Begin a new round with a news headline.
        """
        self.current_round += 1
        self.rounds.append(RoundInfo(round_no=self.current_round, news=news))
        self.round_open_ratios = {
            cname: int(c.base_ratio) for cname, c in self.commodities.items()
        }

    def record_trade(self, from_team: str, to_team: str,
                     give: Dict[str, int], receive: Dict[str, int]) -> Trade:
        """
        Apply a trade to the teams and record it.

        Rule: Only 1 trade is allowed between a pair of teams per round
        (pair is unordered: (A,B) == (B,A)).
        """
        if self.current_round == 0:
            raise ValueError("No active round. Start a round first.")

        # Enforce "only 1 trade per pair per round"
        for tr in self.trades:
            if tr.round_no != self.current_round:
                continue
            pair_existing = {tr.from_team, tr.to_team}
            pair_new = {from_team, to_team}
            if pair_existing == pair_new:
                raise ValueError(
                    f"Only one trade allowed between {from_team} and {to_team} in round {self.current_round}."
                )

        trade = Trade(
            round_no=self.current_round,
            from_team=from_team,
            to_team=to_team,
            give=give,
            receive=receive
        )
        apply_trade(trade, self.teams)
        self.trades.append(trade)
        return trade

    def leaderboard(self):
        """
        Teams sorted by effective portfolio value (Rs), descending.
        Effective value = holdings value - accumulated penalties.
        """
        def effective_value(team: Team) -> float:
            raw = team.value_rs(self.commodities)
            penalty = self.penalties_rs.get(team.name, 0.0)
            return raw - penalty

        return sorted(
            self.teams.values(),
            key=effective_value,
            reverse=True
        )


# ---------------------------------------------------------------------
# PRICE & RATIO HANDLING
# ---------------------------------------------------------------------

def update_prices_from_ratios(game_state: GameState):
    """
    Convert ratios into rupee prices.

    Semantics:
    - base_ratio for commodity i = units of i equivalent to 1 unit of base.
    - price_base = BASE_PRICE_RS (constant).
    - price_i = price_base / base_ratio_i
      (because 1 base (value Rs) = base_ratio_i * i  => price_i = price_base / base_ratio_i)
    """
    if not game_state.base_commodity:
        return
    for cname, c in game_state.commodities.items():
        if cname == game_state.base_commodity:
            c.base_ratio = 1  # enforce
            c.price = BASE_PRICE_RS
        else:
            if c.base_ratio <= 0:
                # avoid division by zero; fallback
                c.base_ratio = 1
            c.price = BASE_PRICE_RS / float(c.base_ratio)


# ---------------------------------------------------------------------
# INITIAL PORTFOLIO GENERATION
# ---------------------------------------------------------------------

def generate_initial_portfolios_with_ranges(
    game_state: GameState,
    target_value_hint: float = 2_000_000.0
) -> float:
    """
    SAFEST & FINAL VERSION:

    - Deterministic (same input → same portfolio every run)
    - Tight allocation bands (initial seeding)
    - Slightly wider holding bands (for trading)
    - Ensures enough liquidity but prevents hoarding
    - Zero risk of slack_total / K_extra errors
    """
    import random

    if not game_state.commodities:
        raise ValueError("No commodities defined.")
    if not game_state.base_commodity:
        raise ValueError("Base commodity not set.")
    if not game_state.teams:
        raise ValueError("No teams defined.")

    commodities = game_state.commodities
    N = len(commodities)

    # -----------------------------------------
    # 0. Deterministic seed
    # -----------------------------------------
    seed_key = f"{len(game_state.teams)}-{len(commodities)}-{int(target_value_hint)}"
    random.seed(seed_key)

    # -----------------------------------------
    # 1. Base units calculation
    # -----------------------------------------
    S = int(round(target_value_hint / BASE_PRICE_RS))
    if S < N * 3:
        S = N * 3

    base_target_each = S / float(N)

    # Allocation bands (tight → fair starting point)
    alloc_min_factor = 0.85
    alloc_max_factor = 1.15

    # Holding bands (slightly wider → allows trading)
    hold_min_factor = 0.70
    hold_max_factor = 1.30

    base_min_total_alloc = 0
    base_max_total_alloc = 0

    # -----------------------------------------
    # 2. Compute allocation & holding bands
    # -----------------------------------------
    for cname, c in commodities.items():
        r = max(1, c.base_ratio)
        units_target = base_target_each * r

        # Allocation band
        alloc_min_mult = max(1, int(units_target * alloc_min_factor // r))
        alloc_max_mult = max(alloc_min_mult + 1, int(units_target * alloc_max_factor // r))

        c.alloc_min_units = alloc_min_mult * r
        c.alloc_max_units = alloc_max_mult * r

        base_min_total_alloc += c.alloc_min_units // r
        base_max_total_alloc += c.alloc_max_units // r

        # Holding band
        hold_min_mult = max(1, int(units_target * hold_min_factor // r))
        hold_max_mult = max(hold_min_mult + 1, int(units_target * hold_max_factor // r))

        c.min_units = hold_min_mult * r
        c.max_units = hold_max_mult * r

    # -----------------------------------------
    # 3. Selecting K_total (same for all teams)
    # -----------------------------------------
    lower = base_min_total_alloc
    upper = base_max_total_alloc

    if S < lower:
        K_total = lower
    elif S > upper:
        K_total = upper
    else:
        K_total = S

    slack_total = upper - lower
    K_extra = K_total - lower

    if K_extra < 0:
        K_extra = 0
    if K_extra > slack_total:
        K_extra = slack_total

    # -----------------------------------------
    # 4. Build base-unit slots for allocating extras
    # -----------------------------------------
    base_unit_slots = []
    for cname, c in commodities.items():
        r = c.base_ratio
        capacity = (c.alloc_max_units - c.alloc_min_units) // r
        if capacity > 0:
            base_unit_slots.extend([cname] * capacity)

    # Emergency safety
    if len(base_unit_slots) == 0:
        K_extra = 0

    # -----------------------------------------
    # 5. Allocate per team
    # -----------------------------------------
    for team in game_state.teams.values():
        team.holdings = {
            cname: c.alloc_min_units for cname, c in commodities.items()
        }

        if K_extra > 0 and len(base_unit_slots) >= K_extra:
            picks = random.sample(base_unit_slots, K_extra)
            for cname in picks:
                team.holdings[cname] += commodities[cname].base_ratio

        # Enforce holding band
        for cname, c in commodities.items():
            q = team.holdings[cname]
            if q < c.min_units:
                team.holdings[cname] = c.min_units
            if q > c.max_units:
                team.holdings[cname] = c.max_units

    # -----------------------------------------
    # Return portfolio rupee value
    # -----------------------------------------
    return K_total * BASE_PRICE_RS



# ---------------------------------------------------------------------
# TRADES & DEMAND / RATIO UPDATE
# ---------------------------------------------------------------------

def apply_trade(trade: Trade, teams: Dict[str, Team]):
    """
    Apply a trade to teams' holdings.

    from_team:
        - loses 'give' holdings
        - gains 'receive' holdings

    to_team:
        - gains 'give'
        - loses 'receive'
    """
    t_from = teams[trade.from_team]
    t_to = teams[trade.to_team]

    # Subtract what from_team gives; add to to_team
    for cname, qty in trade.give.items():
        if qty < 0:
            raise ValueError("Quantity cannot be negative.")
        if t_from.holdings.get(cname, 0) < qty:
            raise ValueError(f"{t_from.name} does not have enough {cname}")
        t_from.holdings[cname] = t_from.holdings.get(cname, 0) - qty
        t_to.holdings[cname] = t_to.holdings.get(cname, 0) + qty

    # Subtract what to_team gives (receive for from_team)
    for cname, qty in trade.receive.items():
        if qty < 0:
            raise ValueError("Quantity cannot be negative.")
        if t_to.holdings.get(cname, 0) < qty:
            raise ValueError(f"{t_to.name} does not have enough {cname}")
        t_to.holdings[cname] = t_to.holdings.get(cname, 0) - qty
        t_from.holdings[cname] = t_from.holdings.get(cname, 0) + qty


def compute_net_demand(game_state: GameState, round_no: int) -> Dict[str, float]:
    """
    Net demand per commodity in a given round.

    Positive => net buying (more received than given)
    Negative => net selling (more given than received)
    """
    net = {cname: 0.0 for cname in game_state.commodities.keys()}
    for tr in game_state.trades:
        if tr.round_no != round_no:
            continue
        for cname, qty in tr.give.items():
            net[cname] = net.get(cname, 0.0) - qty
        for cname, qty in tr.receive.items():
            net[cname] = net.get(cname, 0.0) + qty
    return net


def update_ratios_auto(
    game_state: GameState,
    sensitivity: float = 0.5,
    circuit_pct: float = 0.20,   # 20% circuit by default
):
    """
    Automatic ratio update based on net demand.
    Adds per-round circuit breaker: ratio cannot move beyond ±circuit_pct
    from the round open ratio.

    Interpretation:
    - base_ratio = units of this commodity equivalent to 1 base.
    - Higher demand => ratio decreases (more valuable).
    - Higher supply => ratio increases (cheaper).
    """
    if game_state.current_round == 0:
        return

    net = compute_net_demand(game_state, game_state.current_round)
    total_abs = sum(abs(v) for v in net.values()) or 1.0

    # Must exist (we'll add it in start_round)
    round_open = getattr(game_state, "round_open_ratios", None) or {}

    for cname, c in game_state.commodities.items():
        if cname == game_state.base_commodity:
            c.base_ratio = 1
            continue

        old_ratio = max(1, int(c.base_ratio))
        delta = net.get(cname, 0.0) / total_abs
        factor = 1.0 - sensitivity * delta
        if factor <= 0:
            factor = 0.1

        proposed = int(round(old_ratio * factor))
        if proposed < 1:
            proposed = 1

        # -------- Circuit breaker clamp (per round) --------
        open_ratio = int(round_open.get(cname, old_ratio))
        if open_ratio < 1:
            open_ratio = 1

        # Ratio lower bound means "more valuable" (ratio smaller)
        # Ratio upper bound means "cheaper" (ratio bigger)
        lower = max(1, int(round(open_ratio * (1.0 - circuit_pct))))
        upper = max(lower + 1, int(round(open_ratio * (1.0 + circuit_pct))))

        clamped = min(max(proposed, lower), upper)

        c.base_ratio = clamped

    # Ensure base stays 1
    if game_state.base_commodity in game_state.commodities:
        game_state.commodities[game_state.base_commodity].base_ratio = 1


# ---------------------------------------------------------------------
# PENALTIES: NO-TRADE & MIN/MAX VIOLATIONS
# ---------------------------------------------------------------------

def teams_with_trades_in_round(game_state: GameState, round_no: int) -> set[str]:
    """
    Return set of team names that participated in at least one trade
    in the given round (as buyer or seller).
    """
    active = set()
    for tr in game_state.trades:
        if tr.round_no != round_no:
            continue
        active.add(tr.from_team)
        active.add(tr.to_team)
    return active


def check_min_max_violation(game_state: GameState, team: Team) -> bool:
    """
    Return True if team violates any min/max commodity constraint.
    """
    for cname, c in game_state.commodities.items():
        qty = team.holdings.get(cname, 0)
        if c.min_units and qty < c.min_units:
            return True
        if c.max_units and qty > c.max_units:
            return True
    return False


def apply_round_penalties(
    game_state: GameState,
    round_no: int,
    no_trade_penalty_rate: float = 0.10,
    range_penalty_rate: float = 0.10
):
    """
    Apply penalties at end of a round:

    - 10% of total portfolio value if team did NOT trade in the round.
    - 10% of total portfolio value if team violates any min/max quantity.
    """
    active = teams_with_trades_in_round(game_state, round_no)

    for tname, team in game_state.teams.items():
        value = team.value_rs(game_state.commodities)
        # 1) No-trade penalty
        if tname not in active:
            p = value * no_trade_penalty_rate
            game_state.penalties_rs[tname] = game_state.penalties_rs.get(tname, 0.0) + p

        # 2) Min/max violation penalty
        if check_min_max_violation(game_state, team):
            p2 = value * range_penalty_rate
            game_state.penalties_rs[tname] = game_state.penalties_rs.get(tname, 0.0) + p2
