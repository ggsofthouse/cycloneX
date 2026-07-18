import math
from collections import Counter
from plugins.base import BasePlugin

class ByteFrequencyPlugin(BasePlugin):
    def calculate_score(self, start_val, end_val, global_start, global_end):
        block_mid = (start_val + end_val) // 2
        padded_hex = f"{block_mid:x}".zfill(64).lower()
        
        try:
            raw_bytes = bytes.fromhex(padded_hex)
        except Exception:
            return 50.0
            
        byte_probs = self.metadata.get("byte_probability", {})
        if not byte_probs:
            return 50.0
            
        # Contar bytes da chave candidata
        cand_counts = Counter(raw_bytes)
        
        # Calcular a distancia euclidiana entre a distribuicao candidata e o modelo historico
        distance = 0.0
        for b in range(256):
            cand_prob = cand_counts.get(b, 0) / len(raw_bytes)
            target_prob = float(byte_probs.get(str(b), 0.0))
            distance += (cand_prob - target_prob) ** 2
            
        distance = math.sqrt(distance)
        
        # Maior distancia = menos similar. Menor distancia = mais similar.
        # Normalizar score de 10 a 100 baseando-se em limites tipicos de desvio
        # Distancia euclidiana tipica fica entre 0.05 e 0.25
        max_dist = 0.25
        score = 100.0 - 90.0 * (min(max_dist, distance) / max_dist)
        return min(100.0, max(10.0, score))
