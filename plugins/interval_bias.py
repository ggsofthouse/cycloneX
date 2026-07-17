import math
from plugins.base import BasePlugin

class IntervalBiasPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        if global_end <= global_start:
            return 50.0
            
        block_mid = (start_val + end_val) // 2
        relative_pos = (block_mid - global_start) / (global_end - global_start)
        offset_pct = relative_pos * 100.0
        
        target_offset = self.metadata.get("average_offset_pct", 32.4)
        sigma = 25.0
        
        score = 100.0 * math.exp(-0.5 * ((offset_pct - target_offset) / sigma) ** 2)
        return score
