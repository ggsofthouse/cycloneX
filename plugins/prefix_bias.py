import math
from plugins.base import BasePlugin

class PrefixBiasPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        hex_str = f"{block_mid:x}"
        if not hex_str:
            return 50.0
            
        first_char = hex_str[0].lower()
        
        # Mapeamento do JSON
        prefix_probs = self.metadata.get("prefix_probability", {})
        prob = prefix_probs.get(first_char, 0.01)
        
        max_prob = max(prefix_probs.values()) if prefix_probs else 0.25
        if max_prob <= 0.0:
            max_prob = 0.25
            
        score = 10.0 + 90.0 * (prob / max_prob)
        return min(100.0, max(10.0, score))
