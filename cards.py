# cards.py

# Import the Card class from the treys library to generate integer values
from treys import Card as TreysCard

RANKS = "23456789TJQKA"
SUITS = "cdhs"

class Card:
    def __init__(self, s):
        """Initializes a Card object from a string like 'Ah' or '7c'."""
        assert len(s) == 2, "Card must be 2 chars, e.g. 'Ah'"
        self.rank = s[0].upper()
        self.suit = s[1].lower()
        assert self.rank in RANKS, f"Invalid rank: {self.rank}"
        assert self.suit in SUITS, f"Invalid suit: {self.suit}"
        
        # **THIS IS THE FIX**
        # Create the integer representation needed for sorting and evaluation.
        self.int_val = TreysCard.new(s)
    
    def __str__(self):
        return f"{self.rank}{self.suit}"
    
    def __repr__(self):
        return str(self)
    
    def __lt__(self, other):
        """Allows sorting Cards based on their integer value."""
        return self.int_val < other.int_val

    def __eq__(self, other):
        """Allows checking for equality."""
        return self.int_val == other.int_val

    def __hash__(self):
        """Allows Cards to be used as dictionary keys."""
        return hash(self.int_val)


def parse_cards(card_list):
    """Convert ['Ah', 'Kd'] to a list of Card objects."""
    return [Card(s) for s in card_list]