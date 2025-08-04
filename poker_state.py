# poker_state.py

from cards import Card

class Player:
    def __init__(self, seat, hand=None, stack=2000):
        self.seat = seat.upper()
        self.hand = hand or []
        self.stack = stack
        self.in_hand = True  # True unless folded
        # Amount committed on the current street
        self.last_bet = 0

class GameState:
    def __init__(self, hero_seat, hero_hand, blinds=(10, 20)):
        self.players = {hero_seat: Player(hero_seat, hero_hand, 2000)}
        self.hero_seat = hero_seat
        self.blinds = blinds
        self.board = []
        self.pot = 0
        # The total bet amount facing players on the current street
        self.current_bet = 0
        # The size of the last aggressive action (bet or raise)
        self.last_raise_amount = blinds[1]
        self.bet_history = []
        self.street = "preflop"

    def set_board(self, board_cards):
        self.board = board_cards

    def set_street(self, street):
        self.street = street.lower()
        # Reset betting state for the new street
        self.current_bet = 0
        self.last_raise_amount = self.blinds[1] # Min bet is one BB post-flop

    def record_action(self, actor, action):
        """Processes a player's action and updates the game state."""
        self.bet_history.append((self.street, actor, action))
        player = self.players[actor]
        tokens = action.lower().split()
        verb = tokens[0]

        if verb == 'fold':
            player.in_hand = False
        
        elif verb == 'check':
            # No change in state, but action is recorded
            pass
            
        elif verb == 'call':
            amount_to_call = self.current_bet - player.last_bet
            # Player can only call with what they have
            payment = min(amount_to_call, player.stack)
            player.stack -= payment
            self.pot += payment
            player.last_bet += payment

        elif verb == 'bet':
            # e.g., "bet 100"
            amount = int(tokens[-1])
            player.stack -= amount
            self.pot += amount
            self.current_bet = amount
            player.last_bet = amount
            self.last_raise_amount = amount

        elif verb == 'raise':
            # e.g., "raise to 150"
            total_bet_amount = int(tokens[-1])
            
            # Amount of new money this player needs to add
            new_money = total_bet_amount - player.last_bet
            
            player.stack -= new_money
            self.pot += new_money
            
            self.last_raise_amount = total_bet_amount - self.current_bet
            self.current_bet = total_bet_amount
            player.last_bet = total_bet_amount

        elif verb == 'all_in':
            all_in_amount = player.stack
            player.stack = 0
            self.pot += all_in_amount
            
            # The player's total commitment for the street
            player_total_bet = player.last_bet + all_in_amount
            
            # If this all-in is a raise, update game state accordingly
            if player_total_bet > self.current_bet:
                self.last_raise_amount = player_total_bet - self.current_bet
                self.current_bet = player_total_bet
            
            player.last_bet = player_total_bet

    def get_hero_stack(self):
        return self.players[self.hero_seat].stack

    def __str__(self):
        return f"Board: {self.board}, Pot: {self.pot}, Stacks: {[ (p.seat, p.stack) for p in self.players.values() ]}, Street: {self.street}, History: {self.bet_history}"