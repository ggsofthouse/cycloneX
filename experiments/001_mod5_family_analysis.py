
import json
import math
import random
from collections import Counter, defaultdict

# Dataset real de todas as 82 chaves do Bitcoin Puzzle para reprodução científica
SOLVED_PUZZLES = {
    1: 0x1, 2: 0x3, 3: 0x7, 4: 0x8, 5: 0x15, 6: 0x31, 7: 0x4c, 8: 0xe0, 9: 0x1d3, 10: 0x202,
    11: 0x483, 12: 0xa7b, 13: 0x1460, 14: 0x2930, 15: 0x68f3, 16: 0xc936, 17: 0x1764f, 18: 0x3080d,
    19: 0x5749f, 20: 0xd2c55, 21: 0x1ba534, 22: 0x2de40f, 23: 0x556e52, 24: 0xdc2a04, 25: 0x1fa5ee,
    26: 0x340326, 27: 0x6ac387, 28: 0xd916ce, 29: 0x17e2551, 30: 0x3d94cd64, 31: 0x7d4fe747,
    32: 0xb862a62e, 33: 0x1a96ca8d8, 34: 0x34a65911d, 35: 0x4aed21170, 36: 0x9de820a7c, 37: 0x1757756a93,
    38: 0x22382facd0, 39: 0x4b5f8303e9, 40: 0xe9ae4933d6, 41: 0x153869acc5b, 42: 0x2a221c58d8f,
    43: 0x6bd3b27c591, 44: 0xe02b35a358f, 45: 0x122fca143c05, 46: 0x2ec18388d544, 47: 0x6cd610b53cba,
    48: 0xade6d7ce3b9b, 49: 0x174176b015f4d, 50: 0x22bd43c2e9354, 51: 0x75070a1a009d4, 52: 0xefae164cb9e3c,
    53: 0x180788e47e326c, 54: 0x236fb6d5ad1f43, 55: 0x6abe1f9b67e114, 56: 0x9d18b63ac4ffdf, 57: 0x1eb25c90795d61c,
    58: 0x2c675b852189a21, 59: 0x7496cbb87cab44f, 60: 0xfc07a1825367bbe, 61: 0x13c96a3742f64906,
    62: 0x363d541eb611abee, 63: 0x7cce5efdaccf6808, 64: 0xf7051f27b09112d4, 65: 0x1a838b13505b26867,
    66: 0x2832ed74f2b5e35ee, 67: 0x730fc235c1942c1ae, 68: 0xbebb3940cd0fc1491, 69: 0x101d83275fb2bc7e0c,
    70: 0x349b84b6431a6c4ef1, 75: 0x4c5ce114686a1336e07, 80: 0xea1a5c66dcc11b5ad180,
    85: 0x11720c4f018d51b8cebba8, 90: 0x2ce00bb2136a445c71e85bf, 95: 0x527a792b183c7f64a0e8b1f4,
    100: 0xaf55fc59c335c8ec67ed24826, 105: 0x16f14fc2054cd87ee6396b33df3,
    110: 0x35c0d7234df7deb0f20cf7062444, 115: 0x60f4d11574f5deee49961d9609ac6,
    120: 0xb10f22572c497a836ea187f2e1fc23, 125: 0x1c533b6bb7f0804e09960225e44877ac,
    130: 0x33e7665705359f04f28b88cf897c603c9
}

def get_range_params(puzzle_id):
    range_start = 2 ** (puzzle_id - 1)
    range_end = (2 ** puzzle_id) - 1
    return range_start, range_end

def get_offset_pct(val, puzzle_id):
    start, end = get_range_params(puzzle_id)
    total_keys = end - start + 1
    return ((val - start) / total_keys) * 100.0

def get_stats(lst):
    n = len(lst)
    if n == 0: return 0.0, 0.0
    mean = sum(lst) / n
    variance = sum((x - mean) ** 2 for x in lst) / n
    return mean, math.sqrt(variance)

def run_experiment():
    print("[Exp 001] Iniciando auditoria experimental da hipótese Mod 5...")
    offsets = {}
    for p_id, val in SOLVED_PUZZLES.items():
        offsets[p_id] = get_offset_pct(val, p_id)
        
    global_list = list(offsets.values())
    _, global_std = get_stats(global_list)
    
    # 1. Testar modulações
    groups = defaultdict(list)
    for p_id, offset in offsets.items():
        groups[p_id % 5].append(offset)
        
    subfamily_stds = []
    for g_id, g_offsets in groups.items():
        if len(g_offsets) >= 3:
            _, g_std = get_stats(g_offsets)
            subfamily_stds.append(g_std)
            
    avg_subfamily_std = sum(subfamily_stds) / len(subfamily_stds)
    clustering_effect = global_std - avg_subfamily_std
    
    # 2. Simulação de Monte Carlo
    monte_carlo_runs = 1000
    random_clustering_larger_count = 0
    range_limits = {p_id: get_range_params(p_id) for p_id in SOLVED_PUZZLES.keys()}
    
    for run in range(monte_carlo_runs):
        synthetic_offsets = {}
        synthetic_mod5 = defaultdict(list)
        
        for p_id, (start, end) in range_limits.items():
            rand_val = random.randint(start, end)
            offset = ((rand_val - start) / (end - start + 1)) * 100.0
            synthetic_offsets[p_id] = offset
            synthetic_mod5[p_id % 5].append(offset)
            
        synthetic_global_list = list(synthetic_offsets.values())
        _, synth_global_std = get_stats(synthetic_global_list)
        
        synth_subfamily_stds = []
        for g_id, g_offsets in synthetic_mod5.items():
            if len(g_offsets) >= 3:
                _, g_std = get_stats(g_offsets)
                synth_subfamily_stds.append(g_std)
                
        synth_avg_std = sum(synth_subfamily_stds) / len(synth_subfamily_stds) if synth_subfamily_stds else synth_global_std
        synth_clustering = synth_global_std - synth_avg_std
        
        if synth_clustering >= clustering_effect:
            random_clustering_larger_count += 1
            
    p_value = random_clustering_larger_count / monte_carlo_runs
    print(f"[Exp 001] P-value calculado: {p_value:.4f}")
    print("[Exp 001] Experimento arquivado com sucesso.")

if __name__ == "__main__":
    run_experiment()
