# Relatório Científico de Análise de Puzzles — CycloneX v4.1

Análise detalhada feita sob as 82 chaves reais publicadas no banco oficial.

## 📊 Estatísticas Gerais do Dataset Real
- **Média de Offset Global:** 50.15% (Desvio Padrão: 26.96%)
- **Média de Densidade de Bits (Popcount):** 51.62% (Desvio Padrão: 12.91%)
- **Média de Entropia de Shannon:** 0.660 (Desvio Padrão: 0.231)

## 👥 Análise por Família Modulo 5 (Normalizada)

### Família Mod 0 (Puzzles terminados em 0 ou 5)
Membros resolvidos: **26**
- **Posicionamento médio no range (Offset):** 50.92% (Desvio Padrão: 28.56%)
- **Distância de Hamming Média Normalizada:** 34.6 bits alterados

### Família Mod 1 (Puzzles terminados em 1 ou 6)
Membros resolvidos: **14**
- **Posicionamento médio no range (Offset):** 43.66% (Desvio Padrão: 27.12%)
- **Distância de Hamming Média Normalizada:** 16.8 bits alterados

### Família Mod 2 (Puzzles terminados em 2 ou 7)
Membros resolvidos: **14**
- **Posicionamento médio no range (Offset):** 55.45% (Desvio Padrão: 21.48%)
- **Distância de Hamming Média Normalizada:** 18.7 bits alterados

### Família Mod 3 (Puzzles terminados em 3 ou 8)
Membros resolvidos: **14**
- **Posicionamento médio no range (Offset):** 53.03% (Desvio Padrão: 22.53%)
- **Distância de Hamming Média Normalizada:** 17.8 bits alterados

### Família Mod 4 (Puzzles terminados em 4 ou 9)
Membros resolvidos: **14**
- **Posicionamento médio no range (Offset):** 47.01% (Desvio Padrão: 30.83%)
- **Distância de Hamming Média Normalizada:** 18.9 bits alterados

## 🔬 Teste de Validação Leave-One-Out (Família Mod 1)
Simulamos a eficácia do modelo estatístico tentando prever cada puzzle resolvido da família Mod 1 (como se ele fosse oculto):

| Puzzle Oculto | Offset Real | Média dos Outros | Desvio dos Outros | Top 10% Match? | Top 25% Match? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| #11 | 12.79% | 46.03% | 26.70% | ❌ Não | ✅ Sim |
| #16 | 57.20% | 42.62% | 27.87% | ❌ Não | ✅ Sim |
| #21 | 72.78% | 41.42% | 26.86% | ❌ Não | ✅ Sim |
| #26 | 62.54% | 42.21% | 27.61% | ❌ Não | ✅ Sim |
| #31 | 95.80% | 39.65% | 23.80% | ❌ Não | ❌ Não |
| #36 | 23.36% | 45.22% | 27.53% | ❌ Não | ✅ Sim |
| #41 | 32.63% | 44.51% | 27.96% | ❌ Não | ✅ Sim |
| #46 | 46.11% | 43.47% | 28.13% | ✅ Sim | ✅ Sim |
| #51 | 82.86% | 40.64% | 25.78% | ❌ Não | ❌ Não |
| #56 | 22.73% | 45.27% | 27.49% | ❌ Não | ✅ Sim |
| #61 | 23.67% | 45.20% | 27.55% | ❌ Não | ✅ Sim |
| #66 | 25.62% | 45.05% | 27.66% | ❌ Não | ✅ Sim |

### Resultado da Validação Cruzada:
- **Top 10% de Confiança:** 1/12 (8.3%)
- **Top 25% de Confiança (Gaussiano 1.28-Sigma):** 10/12 (83.3%)