import math
from plugins.base import BasePlugin

class DeltaXorPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        
        # O Puzzle 71 tem um range específico de bits (2^70 a 2^71 - 1).
        # Chaves de PRNG antigos tendem a manter certas transições de XOR consistentes (ex: densidade de transições de bit próximas a 50%).
        
        # Calcular auto-XOR (XOR do bloco deslocado por 1 bit) para medir consistência da transição binária
        xor_val = block_mid ^ (block_mid >> 1)
        bin_str = bin(xor_val)[2:]
        
        # Medir Hamming Weight da transição XOR
        ones = bin_str.count('1')
        total_bits = len(bin_str)
        if total_bits == 0:
            return 50.0
            
        ratio = ones / total_bits
        
        # Esperamos que chaves não-aleatórias tenham pequenos vieses na transição.
        # Alvo ideal de transição de Hamming XOR em chaves pseudo-aleatórias: ~50% (0.5)
        # O desvio em chaves estruturadas de puzzles resolvidos é tipicamente muito estreito.
        target_ratio = 0.5015
        sigma = 0.03
        
        score = 100.0 * math.exp(-0.5 * ((ratio - target_ratio) / sigma) ** 2)
        return score
