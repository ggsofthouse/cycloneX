import math
from plugins.base import BasePlugin

class PrefixBiasPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        hex_str = f"{block_mid:x}".lower()
        if not hex_str:
            return 50.0
            
        p_1 = self.metadata.get("prefix_1_probability", {})
        p_2 = self.metadata.get("prefix_2_probability", {})
        
        # 1-Nibble score (Peso: 0.3)
        char_1 = hex_str[0]
        prob_1 = p_1.get(char_1, 0.01)
        max_1 = max(p_1.values()) if p_1 else 0.25
        score_1 = prob_1 / max_1
        
        # 2-Nibbles score (Peso: 0.7)
        score_2 = 0.1
        if len(hex_str) >= 2:
            char_2 = hex_str[:2]
            if char_2 in p_2:
                score_2 = p_2[char_2] / max(p_2.values())
                
        score_ratio = (0.3 * score_1) + (0.7 * score_2)
        score = 10.0 + 90.0 * score_ratio
        return min(100.0, max(10.0, score))
