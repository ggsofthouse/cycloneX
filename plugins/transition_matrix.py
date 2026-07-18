import math
from plugins.base import BasePlugin

class TransitionMatrixPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        hex_str = f"{block_mid:x}".lower()
        if not hex_str or len(hex_str) < 2:
            return 50.0
            
        matrix = self.metadata.get("transition_matrix", {})
        if not matrix:
            return 50.0
            
        # Calcular a probabilidade acumulada das transições
        score_sum = 0.0
        transitions_count = 0
        
        for i in range(len(hex_str) - 1):
            c_from = hex_str[i]
            c_to = hex_str[i+1]
            
            if c_from in matrix:
                # Obter probabilidade da transicao
                prob = matrix[c_from].get(c_to, 0.001) # fallback Laplace
                score_sum += prob
                transitions_count += 1
                
        if transitions_count == 0:
            return 50.0
            
        avg_transition_prob = score_sum / transitions_count
        
        # Normalizar o score de 10 a 100 com base em um teto observado (média esperada de transição ~0.15)
        max_avg_prob = 0.20
        score = 10.0 + 90.0 * (avg_transition_prob / max_avg_prob)
        return min(100.0, max(10.0, score))
