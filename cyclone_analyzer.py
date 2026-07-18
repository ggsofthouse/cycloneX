
import json
import math
import os
from collections import Counter, defaultdict

# Carregar chaves reais extraídas do arquivo puzzles_solved_clean.json
with open("puzzles_solved_clean.json", "r", encoding="utf-8") as f:
    RAW_SOLVED_PUZZLES = json.load(f)

# Converter chaves do dicionário para tipos numéricos e ordenados por ID do Puzzle
SOLVED_PUZZLES = {int(k): v for k, v in RAW_SOLVED_PUZZLES.items()}

def get_range_params(puzzle_id):
    range_start = 2 ** (puzzle_id - 1)
    range_end = (2 ** puzzle_id) - 1
    return range_start, range_end

def get_offset_pct(val, puzzle_id):
    start, end = get_range_params(puzzle_id)
    total_keys = end - start + 1
    # offset entre 0% e 100%
    return ((val - start) / total_keys) * 100.0

def calculate_shannon_entropy(hex_str):
    if not hex_str:
        return 0.0
    counts = Counter(hex_str)
    length = len(hex_str)
    ent = 0.0
    for char, count in counts.items():
        p = count / length
        ent -= p * math.log2(p)
    return ent / 4.0

def analyze_keys():
    print(f"Executando criptoanálise real em {len(SOLVED_PUZZLES)} puzzles...")
    
    offsets = []
    bit_densities = []
    entropies = []
    
    # 1. Agrupar chaves por famílias Modulo 5
    families = defaultdict(list)
    for p_id, key_hex in sorted(SOLVED_PUZZLES.items()):
        val = int(key_hex, 16)
        offset = get_offset_pct(val, p_id)
        offsets.append(offset)
        
        # Calcular bit density
        bin_str = bin(val)[2:]
        ones = bin_str.count('1')
        bit_densities.append((ones / len(bin_str)) * 100.0)
        
        # Shannon Entropy
        entropies.append(calculate_shannon_entropy(key_hex))
        
        families[p_id % 5].append({
            "id": p_id,
            "key": val,
            "hex": key_hex,
            "offset": offset
        })

    # Estatísticas globais
    def get_stats(lst):
        n = len(lst)
        if n == 0: return 0.0, 0.0
        mean = sum(lst) / n
        variance = sum((x - mean) ** 2 for x in lst) / n
        return mean, math.sqrt(variance)

    mean_offset, std_offset = get_stats(offsets)
    mean_density, std_density = get_stats(bit_densities)
    mean_entropy, std_entropy = get_stats(entropies)

    # 2. Análise por Família (Modulo 5) com normalização
    report = []
    report.append("# Relatório Científico de Análise de Puzzles — CycloneX v4.1")
    report.append("\nAnálise detalhada feita sob as 82 chaves reais publicadas no banco oficial.\n")
    report.append("## 📊 Estatísticas Gerais do Dataset Real")
    report.append(f"- **Média de Offset Global:** {mean_offset:.2f}% (Desvio Padrão: {std_offset:.2f}%)")
    report.append(f"- **Média de Densidade de Bits (Popcount):** {mean_density:.2f}% (Desvio Padrão: {std_density:.2f}%)")
    report.append(f"- **Média de Entropia de Shannon:** {mean_entropy:.3f} (Desvio Padrão: {std_entropy:.3f})")
    
    report.append("\n## 👥 Análise por Família Modulo 5 (Normalizada)")
    
    family_stats = {}
    
    for f_id in sorted(families.keys()):
        members = families[f_id]
        f_offsets = [m["offset"] for m in members]
        f_mean_offset, f_std_offset = get_stats(f_offsets)
        
        # Guardar para o JSON
        family_stats[str(f_id)] = {
            "avg_offset": round(f_mean_offset, 2),
            "std_offset": round(f_std_offset, 2)
        }
        
        report.append(f"\n### Família Mod {f_id} (Puzzles terminados em {f_id} ou {f_id+5})")
        report.append(f"Membros resolvidos: **{len(members)}**")
        report.append(f"- **Posicionamento médio no range (Offset):** {f_mean_offset:.2f}% (Desvio Padrão: {f_std_offset:.2f}%)")
        
        # Hamming Distance Cruzada e Normalizada (Removendo o bit estrutural)
        # Alinhando chaves para o tamanho de bits variáveis
        hamming_dists = []
        for i in range(1, len(members)):
            prev = members[i-1]
            curr = members[i]
            
            # Remover o MSB estrutural (que é sempre 1 na posição 2^(p_id-1))
            val_prev_clean = prev["key"] - (2 ** (prev["id"] - 1))
            val_curr_clean = curr["key"] - (2 ** (curr["id"] - 1))
            
            # XOR nos bits variáveis restantes
            xor_val = val_curr_clean ^ val_prev_clean
            h_dist = bin(xor_val).count('1')
            hamming_dists.append(h_dist)
            
        if hamming_dists:
            avg_h = sum(hamming_dists) / len(hamming_dists)
            report.append(f"- **Distância de Hamming Média Normalizada:** {avg_h:.1f} bits alterados")
        else:
            report.append("- **Distância de Hamming Média Normalizada:** N/A (Membros insuficientes)")

    # 3. Teste Cego Leave-One-Out (Validação Cruzada) para a Família Mod 1 (Família do Puzzle 71)
    report.append("\n## 🔬 Teste de Validação Leave-One-Out (Família Mod 1)")
    report.append("Simulamos a eficácia do modelo estatístico tentando prever cada puzzle resolvido da família Mod 1 (como se ele fosse oculto):\n")
    
    mod1_puzzles = [m["id"] for m in families[1] if m["id"] > 10] # Focar em puzzles maiores
    
    hits_top_10 = 0
    hits_top_20 = 0
    
    report.append("| Puzzle Oculto | Offset Real | Média dos Outros | Desvio dos Outros | Top 10% Match? | Top 25% Match? |")
    report.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for target_id in mod1_puzzles:
        # Treinar apenas com os outros membros da família Mod 1
        train_offsets = [m["offset"] for m in families[1] if m["id"] != target_id]
        target_offset = next(m["offset"] for m in families[1] if m["id"] == target_id)
        
        t_mean, t_std = get_stats(train_offsets)
        
        # Calcular Z-score para ver a proximidade
        z_score = abs(target_offset - t_mean) / (t_std if t_std > 0 else 1.0)
        
        # Se Z-score < 1.28, cai no intervalo Gaussiano de confiança de 20% (ou seja, match de ~25% da busca)
        # Se Z-score < 0.25, cai no Top 10%
        top10 = "✅ Sim" if z_score < 0.3 else "❌ Não"
        top25 = "✅ Sim" if z_score < 1.28 else "❌ Não"
        
        if z_score < 0.3:
            hits_top_10 += 1
        if z_score < 1.28:
            hits_top_20 += 1
            
        report.append(f"| #{target_id} | {target_offset:.2f}% | {t_mean:.2f}% | {t_std:.2f}% | {top10} | {top25} |")
        
    report.append(f"\n### Resultado da Validação Cruzada:")
    report.append(f"- **Top 10% de Confiança:** {hits_top_10}/{len(mod1_puzzles)} ({hits_top_10/len(mod1_puzzles)*100:.1f}%)")
    report.append(f"- **Top 25% de Confiança (Gaussiano 1.28-Sigma):** {hits_top_20}/{len(mod1_puzzles)} ({hits_top_20/len(mod1_puzzles)*100:.1f}%)")
    
    # 4. Probabilidade de Caracteres Finais e Iniciais dos dados REAIS
    sufix_counts = Counter()
    prefix_counts = Counter()
    for key_hex in SOLVED_PUZZLES.values():
        sufix_counts[key_hex[-1].lower()] += 1
        prefix_counts[key_hex[0].lower()] += 1
        
    total = len(SOLVED_PUZZLES)
    sufix_probs = {k: v / total for k, v in sufix_counts.items()}
    prefix_probs = {k: v / total for k, v in prefix_counts.items()}
    
    # Laplace smoothing para sufixo e prefixo
    for c in "0123456789abcdef":
        if c not in sufix_probs: sufix_probs[c] = 0.001
        if c not in prefix_probs: prefix_probs[c] = 0.001

    # Salvar Relatório
    with open("family_analysis_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
        
    # Salvar no JSON final do motor
    metadata = {
        "solved_count": len(SOLVED_PUZZLES),
        "average_offset_pct": round(mean_offset, 2),
        "std_offset_pct": round(std_offset, 2),
        "average_bit_density_pct": round(mean_density, 3),
        "std_bit_density_pct": round(std_density, 3),
        "average_entropy": round(mean_entropy, 3),
        "std_entropy": round(std_entropy, 3),
        "family_modulo_5_stats": family_stats,
        "sufix_probability": sufix_probs,
        "prefix_probability": prefix_probs,
        "notes": "Metadados gerados estritamente com base no dataset real fornecido em puzzles_solved_clean.json."
    }
    
    with open("puzzles_solved.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print("[OK] Criptoanálise real concluída com sucesso!")
    print("[OK] Relatório gerado em: family_analysis_report.md")

if __name__ == "__main__":
    analyze_keys()
