import eval7

import eval7
import random

def estimate_equity(hero_hand, board, num_opponents, num_samples=1000):
    # hero_hand: ['Ah', 'Kd']
    # board: ['9c', 'Jd', ...]
    deck = [eval7.Card(s) for s in eval7.std_deck()]
    known = set(eval7.Card(c) for c in hero_hand + board)
    deck = [c for c in deck if c not in known]
    hero = [eval7.Card(c) for c in hero_hand]
    board_cards = [eval7.Card(c) for c in board]
    wins = 0

    for _ in range(num_samples):
        random.shuffle(deck)
        opp_hands = [deck[i*2:(i+1)*2] for i in range(num_opponents)]
        rem_board = board_cards + deck[2*num_opponents:2*num_opponents+5-len(board_cards)]
        hero_full = hero + rem_board
        opp_full = [h + rem_board for h in opp_hands]
        hero_score = eval7.evaluate(hero_full)
        opp_scores = [eval7.evaluate(o) for o in opp_full]
        if all(hero_score > s for s in opp_scores):
            wins += 1
        elif any(hero_score == s for s in opp_scores):
            wins += 0.5  # Split pot
    return wins / num_samples

def bot_best_move(hero_hand, board, pot, to_call, stack, num_opponents=1):
    equity = estimate_equity(hero_hand, board, num_opponents)
    # Pot odds: to_call / (pot + to_call)
    call_ev = equity * (pot + to_call) - to_call
    if call_ev > 0:
        return f"call (EV={call_ev:.2f}, eq={equity:.2%})"
    else:
        return f"fold (EV={call_ev:.2f}, eq={equity:.2%})"

