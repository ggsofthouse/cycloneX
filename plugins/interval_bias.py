import math
from plugins.base import BasePlugin

class IntervalBiasPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        if global_end <= global_start:
            return 50.0
            
        block_mid = (start_val + end_val) // 2
        relative_pos = (block_mid - global_start) / (global_end - global_start)
        offset_pct = relative_pos * 100.0
        
        # Identificar o ID/bits do puzzle atual baseado no range global
        # Ex: global_end de Puzzle 71 é 2^71 - 1
        bits = global_end.bit_length()
        family_id = str(bits % 5)
        
        # Carregar estatísticas de famílias do JSON
        family_stats = self.metadata.get("family_modulo_5_stats", {})
        
        if family_id in family_stats:
            target_offset = family_stats[family_id].get("avg_offset", 49.79)
            sigma = family_stats[family_id].get("std_offset", 28.24)
        else:
            target_offset = self.metadata.get("average_offset_pct", 49.79)
            sigma = self.metadata.get("std_offset_pct", 28.24)
            
        if sigma <= 0.0:
            sigma = 28.24
            
        # Corrigir offset absoluto em caso de valores muito proximos de zero
        diff_val = abs(offset_pct - target_offset)
        score = 100.0 * math.exp(-0.5 * (diff_val / sigma) ** 2)
        return score
