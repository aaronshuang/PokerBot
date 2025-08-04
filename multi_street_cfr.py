from __future__ import annotations
import random, pickle, sys
from collections import defaultdict
from dataclasses import dataclass, field
from treys import Deck, Evaluator

# ---------- CONSTANTS -------------------------------------------------------
# Added 'check' to the action set for when no bet is faced.
ACTIONS     = ['fold', 'call', 'check']
BET_BUCKETS = ['small', 'medium', 'large', 'all_in']
ACTIONS.extend(BET_BUCKETS)

# Bet sizing is now relative to the pot, which is more standard.
BUCKET_PERC = {'small': 0.5, 'medium': 1.0, 'large': 2.0, 'all_in': 1.0}

STACK_START = 20000 # Using a 200 big blind starting stack
SMALL_BLIND = 10
BIG_BLIND   = 20
ITERATIONS  = 50_000_000
SAVE_FILE   = "mccfr_3p_fixed.pkl"
DEPTH_CAP   = 120

# ---------- GLOBAL CACHES ---------------------------------------------------
ev           = Evaluator()
eval_cache   : dict[tuple[int,...], int] = {}
bucket_cache : dict[tuple[int,...], int] = {}

# Return the board cards for the current street
def get_board(street: int, full_board: list[list[int]]):
    if street == 0: return []
    if street == 1: return full_board[0]
    if street == 2: return full_board[0] + full_board[1]
    return full_board[0] + full_board[1] + full_board[2]

# fast 0-11 bucket abstraction per street (cheap HS² percentile)
def bucket(hand:list[int], board:list[int], street:int) -> int:
    key = (*sorted(hand), *sorted(board), street)
    if key in bucket_cache: return bucket_cache[key]

    # Handle pre-flop case where there's no board
    if not board:
        # Pre-flop bucketing can be based on hand strength (e.g., card ranks)
        r1, r2 = (hand[0] >> 8), (hand[1] >> 8)
        c1, c2 = (hand[0] & 0xF), (hand[1] & 0xF)
        is_pair = r1 == r2
        is_suited = c1 == c2
        score = (r1+r2) + (is_pair * 20) + (is_suited * 10) # Simple scoring
        return int(score / 4) # Abstract into buckets

    hscore = ev.evaluate(board, hand)
    scores = []
    d = Deck(); d.cards = [c for c in d.cards if c not in hand+board]
    # Sample 25 opponent hands for percentile (reduced for performance)
    for _ in range(25):
        opp = d.draw(2); scores.append(ev.evaluate(board, opp))
        d.cards.extend(opp)
    
    pct = sum(hscore < s for s in scores) / len(scores) if scores else 0
    b = int(pct * 12) # 0-11 buckets
    bucket_cache[key] = b
    return b

# ---------- NODE ------------------------------------------------------------
@dataclass(slots=True)
class Node:
    regret     : defaultdict[str, float] = field(default_factory=lambda: defaultdict(float))
    strat_sum  : defaultdict[str, float] = field(default_factory=lambda: defaultdict(float))

    def policy(self, legal_actions: list[str]) -> dict[str, float]:
        pos_regret = {a: max(0, self.regret[a]) for a in legal_actions}
        norm = sum(pos_regret.values())
        
        if norm > 0:
            return {a: pos_regret[a] / norm for a in legal_actions}
        else:
            # Default to uniform random strategy if no regrets are positive
            return {a: 1.0 / len(legal_actions) for a in legal_actions}

# ---------- UTILITY & ACTION HELPERS ----------------------------------------
def get_utils(stacks: list[int], pot: int, alive: list[bool], hands: list[list[int]], board: list[int]) -> tuple[float, ...]:
    """Calculates final utilities for all players."""
    if sum(alive) == 1:
        winner = alive.index(True)
        final_stacks = list(stacks)
        final_stacks[winner] += pot
    else:
        # Find winner(s) at showdown
        scores = {i: ev.evaluate(get_board(3, board), h) for i, h in enumerate(hands) if alive[i]}
        best_score = min(scores.values())
        winners = [p for p, s in scores.items() if s == best_score]
        
        final_stacks = list(stacks)
        split_pot = pot / len(winners)
        for w in winners:
            final_stacks[w] += split_pot

    # Utility is the change from the starting stack, normalized by stack size
    return tuple((fs - STACK_START) for fs in final_stacks)

def get_legal_actions(p: int, stacks: list[int], to_call: int, street_contrib: list[int], min_raise: int) -> list[str]:
    """Returns a list of legal actions for the current player."""
    actions = []
    stack = stacks[p]
    
    if to_call > 0:
        actions.append('fold')
        if stack > to_call:
            actions.append('call')
    else:
        actions.append('check')
    
    # Add bet/raise actions
    for b in BET_BUCKETS:
        if b == 'all_in':
            if stack > to_call:
                actions.append('all_in')
            continue
        
        # Sizing bets to the pot
        wager_size = int(BUCKET_PERC[b] * (sum(street_contrib) + to_call))
        total_bet = to_call + wager_size
        
        # Raise must be at least min_raise and player must have enough stack
        if wager_size >= min_raise and stack > total_bet:
            actions.append(b)
            
    return actions

def deal():
    d = Deck()
    hands = [d.draw(2) for _ in range(3)]
    board = [d.draw(3), d.draw(1), d.draw(1)] # [flop, turn, river]
    return hands, board, d

# ---------- MCCFR TRAVERSAL -------------------------------------------------
sys.setrecursionlimit(1 << 15)
nodes: dict[tuple, Node] = {}

def traverse(p: int, street: int, stacks: list[int], street_contrib: list[int], min_raise: int,
             acted: list[bool], alive: list[bool], full_board: list[list[int]],
             street_hist: tuple[str, ...], hands: list[list[int]], depth: int) -> tuple[float, ...]:
    
    # ---- Terminal Node: Hand ends, return utilities ----
    if sum(alive) <= 1 or street == 4:
        pot = sum(c for c in street_contrib if c is not None)
        return get_utils(stacks, pot, alive, hands, full_board)

    # ---- Determine if betting round is over ----
    if all(acted) and len(set(c for i, c in enumerate(street_contrib) if alive[i])) <= 1:
        # Move to next street
        pot = sum(street_contrib)
        return traverse(p=(1 % 3), street=street + 1, stacks=stacks, street_contrib=[0, 0, 0], min_raise=BIG_BLIND,
                        acted=[False, False, False], alive=alive, full_board=full_board, street_hist=(), hands=hands, depth=depth + 1)
    
    # ---- Skip players who are folded or all-in ----
    if not alive[p] or stacks[p] == 0:
        return traverse((p + 1) % 3, street, stacks, street_contrib, min_raise, acted, alive,
                        full_board, street_hist, hands, depth + 1)

    # ---- Infoset Creation ----
    board = get_board(street, full_board)
    bkt = bucket(hands[p], board, street)
    to_call = max(street_contrib) - street_contrib[p]
    key = (street, bkt, tuple(sorted(street_hist)), to_call > 0)
    node = nodes.setdefault(key, Node())
    
    # ---- Get Policy and Sample Action ----
    legal_actions = get_legal_actions(p, stacks, to_call, street_contrib, min_raise)
    if not legal_actions: # Player is all-in but not the highest bettor
         return traverse((p + 1) % 3, street, stacks, street_contrib, min_raise, acted, alive,
                        full_board, street_hist, hands, depth + 1)

    policy = node.policy(legal_actions)
    act = random.choices(list(policy.keys()), weights=list(policy.values()), k=1)[0]
    
    # ---- Apply Action and Recurse ----
    nxt_stacks = list(stacks); nxt_street_contrib = list(street_contrib)
    nxt_min_raise = min_raise; nxt_acted = list(acted); nxt_alive = list(alive)
    nxt_acted[p] = True
    
    if act == 'fold':
        nxt_alive[p] = False
    elif act == 'check':
        pass # No change in money
    elif act == 'call':
        payment = min(to_call, nxt_stacks[p])
        nxt_stacks[p] -= payment
        nxt_street_contrib[p] += payment
    else: # Bet/Raise
        bet_amount = 0
        current_bet = max(nxt_street_contrib)
        if act == 'all_in':
            bet_amount = nxt_stacks[p]
        else: # Bet bucket
            pot_size = sum(nxt_street_contrib)
            bet_amount = to_call + int(BUCKET_PERC[act] * pot_size)
            bet_amount = max(to_call + nxt_min_raise, bet_amount) # ensure min raise
        
        bet_amount = min(bet_amount, nxt_stacks[p]) # cap at stack size
        raise_amount = bet_amount - to_call
        nxt_min_raise = raise_amount
        
        nxt_stacks[p] -= bet_amount
        nxt_street_contrib[p] += bet_amount
        
        # A bet/raise re-opens the action for other players
        for i in range(len(acted)):
            if nxt_alive[i] and i != p: nxt_acted[i] = False
            
    utils = traverse((p + 1) % 3, street, nxt_stacks, nxt_street_contrib, nxt_min_raise,
                     nxt_acted, nxt_alive, full_board, street_hist + (act,), hands, depth + 1)
    
    # ---- Regret & Strategy Sum Updates (for player p) ----
    u_p = utils[p]
    for a in legal_actions:
        # Correct OS-MCCFR regret update
        realization = u_p if a == act else 0
        expected = policy[a] * u_p
        node.regret[a] += realization - expected
        node.strat_sum[a] += policy[a]
        
    return utils

# ---------- TRAIN -----------------------------------------------------------
def train(iters:int=ITERATIONS):
    for t in range(1, iters + 1):
        hands, full_board, deck = deal()
        
        # Set up initial state with blinds
        stacks = [float(STACK_START)] * 3
        stacks[0] -= SMALL_BLIND
        stacks[1] -= BIG_BLIND
        
        street_contrib = [SMALL_BLIND, BIG_BLIND, 0.0]
        alive = [True, True, True]
        acted = [False, False, False]
        
        # Player 2 (UTG) is first to act pre-flop
        traverse(p=2, street=0, stacks=stacks, street_contrib=street_contrib, min_raise=BIG_BLIND,
                 acted=acted, alive=alive, full_board=full_board, street_hist=(), hands=hands, depth=0)
        
        if t % 10 == 0: print(f"Iteration: {t:,}/{iters:,} | Nodes: {len(nodes):,}")

    # Save the average strategy
    avg_strategy = {}
    for key, node in nodes.items():
        total_sum = sum(node.strat_sum.values())
        if total_sum > 0:
            avg_strategy[key] = {a: s / total_sum for a, s in node.strat_sum.items()}

    with open(SAVE_FILE, 'wb') as f:
        pickle.dump(avg_strategy, f)
    print("Saved average strategy to:", SAVE_FILE)

if __name__ == "__main__":
    try:
        with open(SAVE_FILE, 'rb') as f:
            nodes_data = pickle.load(f)
            # This is a simplified loading; a full implementation would restore node objects.
            print(f"Loaded {len(nodes_data)} nodes from {SAVE_FILE}. Resuming training...")
    except FileNotFoundError:
        print("No saved file found. Starting new training.")
        
    train()