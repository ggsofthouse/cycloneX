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
        
        # Puzzles resolvidos têm grande tendência a terminar com '0' ou '5'
        # Vamos dar pontuação extra para os blocos cujo ponto médio de chave termine nestes nibbles.
        if last_char in ('0', '5'):
            score = 100.0
        elif last_char in ('a', 'c', 'e', 'f'):
            # Outros nibbles comuns observados no dataset
            score = 65.0
        else:
            # Nibbles raros ou de ruído
            score = 35.0
            
        return score
