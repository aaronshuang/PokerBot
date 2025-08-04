import pickle
from treys import Card
from multi_street_cfr import encode, bucket, BET_BUCKETS

NODES = pickle.load(open("multi_street_cfr.pkl","rb"))

def map_action(act_str, stack):
    t = act_str.split()
    if t[0] in ('fold','call'):
        return t[0]
    if t[0] in ('bet','raise'):
        return bucket(int(t[1])/stack*100)
    if act_str=='all in':
        return 'all_in'
    # assume already mapped
    return act_str         

def gto(hand_cards, board_cards, street_idx,
        history_labels, stacks, player_idx=0):
    key = encode(hand_cards, board_cards, street_idx,
                 history_labels, stacks)
    node = NODES.get(key)
    if not node:
        return "call"
    strat = node.avg_strategy()
    return max(strat, key=strat.get)
