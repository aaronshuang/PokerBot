# interface.py

import pickle
import collections
from treys import Deck, Evaluator
from cards import parse_cards
from poker_state import GameState, Player

# =================================================================================
# == CFR BOT INTEGRATION - CODE ADDED FROM TRAINING SCRIPT
# =================================================================================

# --- Load the trained CFR strategy ---
try:
    with open("mccfr_3p_fixed.pkl", "rb") as f:
        CFR_STRATEGY = pickle.load(f)
    print("✅ CFR strategy loaded successfully.")
except FileNotFoundError:
    print("❌ ERROR: 'mccfr_3p_fixed.pkl' not found. Please run the training script first.")
    CFR_STRATEGY = {}

# --- CFR constants and helper functions ---
EVALUATOR = Evaluator()
STREET_TO_INT = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}
CFR_BET_BUCKETS = {'small': 0.5, 'medium': 1.0, 'large': 2.0} # Pot-relative sizes
BUCKET_CACHE = {}

def get_board(street: int, full_board: list[int]):
    if street == 0: return []
    if street == 1: return full_board[:3]
    if street == 2: return full_board[:4]
    return full_board

def bucket(hand: list[int], board: list[int], street: int) -> int:
    """Calculates a 0-11 hand strength bucket for the current hand and board."""
    key = (*sorted(hand), *sorted(board), street)
    if key in BUCKET_CACHE: return BUCKET_CACHE[key]
    
    if not board: # Pre-flop bucketing based on raw card ranks
        r1, r2 = (hand[0] >> 8), (hand[1] >> 8)
        c1, c2 = (hand[0] & 0xF), (hand[1] & 0xF)
        is_pair = r1 == r2
        is_suited = c1 == c2
        score = (r1 + r2) + (is_pair * 20) + (is_suited * 10)
        b = int(score / 4)
        BUCKET_CACHE[key] = b
        return b

    h_score = EVALUATOR.evaluate(board, hand)
    d = Deck()
    d.cards = [c for c in d.cards if c not in hand + board]
    scores = []
    for _ in range(25):
        opp = d.draw(2)
        scores.append(EVALUATOR.evaluate(board, opp))
        d.cards.extend(opp)

    pct = sum(h_score < s for s in scores) / len(scores) if scores else 0
    b = int(pct * 12)
    BUCKET_CACHE[key] = b
    return b

def map_action_to_cfr(action_str: str) -> str:
    """Maps a descriptive interface action to an abstract CFR action."""
    action = action_str.lower().split(" ")[0]
    if action in ["fold", "check", "call", "all_in"]:
        return action
    if action == "bet":
        if "1/2" in action_str: return "small"
        if "3/4" in action_str or "pot" in action_str: return "medium"
        return "small"
    if action == "raise":
        return "large"
    return "check"

def map_cfr_action_to_interface(cfr_action: str, gs: GameState, player: Player) -> str:
    """Maps an abstract CFR action to a concrete, executable interface action."""
    to_call = gs.current_bet - player.last_bet
    if cfr_action in ["fold", "check", "all_in"]:
        return cfr_action
    if cfr_action == "call":
        return f"call"
    
    if cfr_action in CFR_BET_BUCKETS:
        bet_perc = CFR_BET_BUCKETS[cfr_action]
        raise_amount = int(bet_perc * gs.pot)
        total_bet_size = to_call + raise_amount
        
        min_raise = gs.last_raise_amount
        if to_call > 0 and raise_amount < min_raise:
            total_bet_size = to_call + min_raise

        total_bet_size = min(total_bet_size, player.stack)

        if to_call > 0:
            return f"raise to {player.last_bet + total_bet_size}"
        else:
            return f"bet {total_bet_size}"
            
    return "check"

def recommend_move(gs: GameState, hero_hand: list, street_hist: list[str]) -> str:
    """
    Constructs the infoset key and queries the CFR tree for the best move.
    """
    player = gs.players[gs.hero_seat]
    
    street_int = STREET_TO_INT[gs.street]
    
    hero_hand_ints = [card.int_val for card in hero_hand]
    board_ints = [card.int_val for card in gs.board]
    hand_bkt = bucket(hero_hand_ints, board_ints, street_int)
    
    hist_tuple = tuple(sorted(street_hist))
    to_call = gs.current_bet - player.last_bet
    
    infoset_key = (street_int, hand_bkt, hist_tuple, to_call > 0)
    
    if infoset_key in CFR_STRATEGY:
        strategy = CFR_STRATEGY[infoset_key]
        best_cfr_action = max(strategy, key=strategy.get)
        print(f"🤖 BotDecides: Key={infoset_key}, Strategy={strategy}, Chose='{best_cfr_action}'")
    else:
        print(f"⚠️ BotDecides: Key={infoset_key} not found in tree. Defaulting to safe move.")
        best_cfr_action = "check" if to_call == 0 else "fold"
        
    return map_cfr_action_to_interface(best_cfr_action, gs, player)

# =================================================================================
# == GAME FLOW LOGIC
# =================================================================================

SEATS = ["SB", "BB", "BTN"]

def get_seat_order_preflop():
    return ["BTN", "SB", "BB"]

def get_seat_order_postflop():
    return ["SB", "BB", "BTN"]

def get_valid_moves(player, gs):
    """Generates a list of valid, human-readable moves."""
    moves = []
    stack = player.stack
    to_call = gs.current_bet - player.last_bet
    
    if to_call == 0:
        moves.append("check")
    else:
        moves.append("fold")
        if stack > to_call:
            moves.append(f"call")

    for label, perc in CFR_BET_BUCKETS.items():
        raise_amount = int(perc * gs.pot)
        total_bet_size = to_call + raise_amount
        
        if total_bet_size > 0 and total_bet_size < stack:
            if to_call > 0:
                if raise_amount >= gs.last_raise_amount:
                    moves.append(f"raise to {player.last_bet + total_bet_size}")
            else:
                moves.append(f"bet {total_bet_size}")

    if stack > 0:
        moves.append("all_in")
        
    return list(dict.fromkeys(moves))

def post_blinds(gs):
    sb, bb = gs.blinds
    gs.players["SB"].stack -= sb
    gs.players["SB"].last_bet = sb
    gs.players["BB"].stack -= bb
    gs.players["BB"].last_bet = bb
    gs.pot = sb + bb
    gs.current_bet = bb
    gs.last_raise_amount = bb
    print(f"Blinds posted: Pot is {gs.pot}. SB: {gs.players['SB'].stack}, BB: {gs.players['BB'].stack}")

def betting_round(gs, seat_order, hero_seat, hero_hand):
    """
    Handles a full betting round for any street using a robust queue-based approach.
    """
    if gs.street != "preflop":
        for p in gs.players.values():
            p.last_bet = 0
        gs.current_bet = 0
        gs.last_raise_amount = gs.blinds[1]

    street_hist = []
    
    actors = [s for s in seat_order if gs.players[s].in_hand and gs.players[s].stack > 0]
    
    if len(actors) <= 1:
        if len(actors) == 1 and gs.current_bet > gs.players[actors[0]].last_bet:
            pass
        else:
            return

    action_queue = collections.deque(actors)
    num_to_act = len(action_queue)
    
    while num_to_act > 0:
        seat = action_queue.popleft()
        player = gs.players[seat]

        if not player.in_hand:
            continue
        
        print("-" * 20)
        print(f"Pot: {gs.pot} | Current Bet: {gs.current_bet}")
        print(f"Turn: {seat} (Stack: {player.stack})")

        valid_moves = get_valid_moves(player, gs)
        print(f"Valid moves: {', '.join(valid_moves)}")
        
        action_str = ""
        if seat == hero_seat:
            recommended = recommend_move(gs, hero_hand, street_hist)
            user_input = input(f"Enter your move (bot suggests: {recommended}): ").strip().lower()
            action_str = user_input if user_input else recommended
        else:
            action_str = input(f"Enter {seat}'s move: ").strip().lower()

        verb = action_str.split(' ')[0]
        is_aggressive = False
        if verb in ['bet', 'raise']:
            is_aggressive = True
        elif verb == 'all_in' and (player.last_bet + player.stack) > gs.current_bet:
            is_aggressive = True

        gs.record_action(seat, action_str)
        street_hist.append(map_action_to_cfr(action_str))
        num_to_act -= 1
        
        if is_aggressive:
            remaining_actors = [s for s in seat_order if gs.players[s].in_hand and gs.players[s].stack > 0 and s != seat]
            action_queue = collections.deque(remaining_actors)
            num_to_act = len(action_queue)
            
        if sum(p.in_hand for p in gs.players.values()) <= 1:
            return

def handle_showdown(gs: GameState):
    """
    Determines the winner(s) at the end of a hand and distributes the pot.
    """
    print("\n" + "="*15 + " HAND RESULT " + "="*15)
    
    # Get players who are still in the hand
    eligible_players = [p for p in gs.players.values() if p.in_hand]
    
    # Case 1: Only one player left (everyone else folded)
    if len(eligible_players) == 1:
        winner = eligible_players[0]
        print(f"🏆 {winner.seat} wins the pot of {gs.pot} as the last remaining player.")
        winner.stack += gs.pot
        gs.pot = 0
        return

    # Case 2: Showdown between two or more players
    print(f"Showdown! Board: {' '.join(map(str, gs.board))}")
    
    scores = {}
    for player in eligible_players:
        hand_ints = [c.int_val for c in player.hand]
        board_ints = [c.int_val for c in gs.board]
        # The treys score is an integer where lower is better
        scores[player.seat] = EVALUATOR.evaluate(board_ints, hand_ints)
        print(f"{player.seat} shows {' '.join(map(str, player.hand))}")

    # Find the best score (lowest value)
    best_score = min(scores.values())
    
    # Find all players who have that score (to handle split pots)
    winners = [seat for seat, score in scores.items() if score == best_score]
    
    # Get the string description of the winning hand
    hand_class = EVALUATOR.get_rank_class(best_score)
    hand_class_str = EVALUATOR.class_to_string(hand_class)

    # Distribute the pot
    payout = gs.pot / len(winners)
    print("-" * 43)
    for seat in winners:
        gs.players[seat].stack += payout
        print(f"🏆 {seat} wins {payout:.0f} with a {hand_class_str}!")
    
    gs.pot = 0

def main():
    print("=== Poker Bot CLI Trainer ===")
    hero_seat = input("Enter your seat (SB, BB, BTN): ").strip().upper()
    hero_hand_str = input("Enter your hand (e.g., Ah Kd): ")
    hero_hand_parsed = parse_cards(hero_hand_str.split())
    
    gs = GameState(hero_seat=hero_seat, hero_hand=hero_hand_parsed, blinds=(10, 20))
    for seat in SEATS:
        if seat != hero_seat:
            gs.players[seat] = Player(seat, stack=2000)

    # --- Pre-flop ---
    post_blinds(gs)
    betting_round(gs, get_seat_order_preflop(), hero_seat, hero_hand_parsed)

    # --- Post-flop Streets ---
    for street in ["flop", "turn", "river"]:
        if sum(p.in_hand for p in gs.players.values()) <= 1: break
        gs.set_street(street)
        
        if street == "flop":
            board_str = input("Enter flop cards (e.g., 9c Jd 2s): ")
            gs.set_board(parse_cards(board_str.split()))
        else:
            card_str = input(f"Enter {street} card (e.g., 6h): ")
            gs.set_board(gs.board + parse_cards([card_str.strip()]))
            
        betting_round(gs, get_seat_order_postflop(), hero_seat, hero_hand_parsed)

    # --- Determine Winner and Distribute Pot ---
    handle_showdown(gs)

    print("\n=== Hand Over ===")
    print(f"Final Stacks: ")
    for p in gs.players.values():
        print(f"  {p.seat}: {p.stack:.0f}")

if __name__ == "__main__":
    main()