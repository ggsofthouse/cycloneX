import math
from collections import Counter
from plugins.base import BasePlugin

class EntropyPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        hex_str = f"{block_mid:x}"
        length = len(hex_str)
        if length == 0:
            return 50.0
            
        counts = Counter(hex_str)
        shannon = 0.0
        for char, count in counts.items():
            p = count / length
            shannon -= p * math.log2(p)
            
        normalized_entropy = shannon / 4.0
        
        target_entropy = self.metadata.get("average_entropy", 0.985)
        sigma = 0.05
        
        score = 100.0 * math.exp(-0.5 * ((normalized_entropy - target_entropy) / sigma) ** 2)
        return score
