import math
from plugins.base import BasePlugin

class SufixBiasPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        
        # Obter último caractere hexadecimal (nibble final)
        hex_str = f"{block_mid:x}"
        if not hex_str:
            return 50.0
            
        last_char = hex_str[-1].lower()
        
        # Mapeamento de probabilidade obtido do JSON (laplace-smoothed)
        sufix_probs = self.metadata.get("sufix_probability", {})
        
        # Obter a probabilidade do caractere ou usar um fallback padrão baixo
        prob = sufix_probs.get(last_char, 0.01)
        
        # Encontrar a probabilidade máxima para normalizar a nota (máximo = 100 pontos)
        max_prob = max(sufix_probs.values()) if sufix_probs else 0.25
        if max_prob <= 0.0:
            max_prob = 0.25
            
        # O score varia proporcionalmente à probabilidade, de 10.0 (mínimo) a 100.0 (máximo)
        score = 10.0 + 90.0 * (prob / max_prob)
        return min(100.0, max(10.0, score))
