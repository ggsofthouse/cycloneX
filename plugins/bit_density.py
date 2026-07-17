import math
from plugins.base import BasePlugin

class BitDensityPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        bin_str = bin(block_mid)[2:]
        total_bits = len(bin_str)
        if total_bits == 0:
            return 50.0
            
        ones = bin_str.count('1')
        density = (ones / total_bits) * 100.0
        
        target_density = self.metadata.get("average_bit_density_pct", 49.85)
        sigma = 2.0
        
        score = 100.0 * math.exp(-0.5 * ((density - target_density) / sigma) ** 2)
        return score
