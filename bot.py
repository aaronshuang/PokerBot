# bot.py
import random


def get_legal_bets(game_state, min_raise):
    pot = game_state.pot
    hero_stack = game_state.hero_stack
    current_bet = game_state.current_bet  # amount to call

    bet_sizes = [
        20,
        int(0.5 * pot),
        int(0.75 * pot),
        int(pot),
        hero_stack
    ]
    # Only include bets above min_raise and within stack
    raises = [b for b in bet_sizes if b >= min_raise and b <= hero_stack]

    # Always allow 'call' and 'fold'
    actions = ['fold']
    if current_bet <= hero_stack:
        actions.append(f'call {current_bet}')
    actions += [f'raise {b}' for b in raises if b > current_bet]
    if hero_stack > current_bet:
        actions.append('all in')
    return actions


def recommend_move(game_state, hero_hand, seat, actions_this_street):
    """
    Returns a random legal action as a placeholder.
    Replace with CFR logic later.
    """
    # For now, just randomly pick from typical actions
    legal_actions = ['fold', 'call', 'bet 40', 'raise 80']
    # If it's preflop and no bet, allow 'check'
    if game_state.street == "preflop" and not actions_this_street:
        legal_actions = ['fold', 'call', 'raise 60', 'check']
    if game_state.street in ["flop", "turn", "river"]:
        legal_actions = ['check', 'bet 40', 'bet 80', 'fold']
    return random.choice(legal_actions)
