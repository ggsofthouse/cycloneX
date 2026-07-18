# Relatório de Auditoria e Validação Estatística de Famílias — CycloneX v5.0

Este documento descreve os testes de hipótese rigorosos aplicados sobre a teoria de agrupamento em famílias (Modulação) usando os dados reais das 82 chaves públicas de Bitcoin Puzzles resolvidas.

## 🔬 1. Teste de Significância de Modulação (Mod 2 a Mod 16)
Se o criador dos puzzles usou um agrupamento em passos regulares, a modulação correta deve apresentar um desvio padrão médio de famílias substancialmente menor do que as modulações incorretas (ruído).

- **Desvio Padrão Global do Offset:** 42.23%

| Modulação (Passo) | Desvio Padrão Médio das Famílias | Efeito de Clusterização (Redução de Desvio) |
| :--- | :--- | :--- |
| Mod 2 | 42.09% | 0.14% |
| Mod 3 | 41.97% | 0.26% |
| Mod 4 | 41.44% | 0.80% |
| Mod 5 | 42.62% | -0.38% |
| Mod 6 | 41.17% | 1.06% |
| Mod 7 | 39.74% | 2.50% |
| Mod 8 | 38.78% | 3.45% |
| Mod 9 | 39.55% | 2.68% |
| Mod 10 | 38.70% | 3.53% |
| Mod 11 | 37.62% | 4.61% |
| Mod 12 | 36.52% | 5.71% |
| Mod 13 | 35.06% | 7.17% |
| Mod 14 | 35.51% | 6.73% |
| Mod 15 | 36.60% | 5.63% |
| Mod 16 | 34.79% | 7.45% |

**Análise do Teste de Modulação:**
- O melhor fator de agrupamento estatístico observado é o **Mod 16** (Redução de desvio de 7.45%).
- O agrupamento **Mod 5** (finais 0/5) obteve uma redução de desvio de **-0.38%**.

## 🧪 2. Teste Cego Leave-One-Out (Capacidade Preditiva)
Testamos a capacidade do modelo estatístico Modulo 5 de 'prever' a localização de uma chave oculta:
- **Total de testes executados:** 62
- **Acertos dentro do Top 25% do range:** 53/62 (85.5%)
- **Acertos dentro do Top 10% do range:** 17/62 (27.4%)

*Nota: Em chaves puramente aleatórias, a taxa de acerto esperada no Top 25% seria de 25.0% e no Top 10% seria de 10.0%.*

## 🎲 3. Teste de Hipótese contra Aleatoriedade (Monte Carlo)
Rodamos 1.000 simulações de conjuntos de chaves puramente aleatórios dentro dos mesmos limites de bits e calculamos a probabilidade de obter um efeito de agrupamento similar ao observado:
- **P-value (Efeito de Clusterização >= Real):** 0.9950
- **P-value (Desvio Padrão de Família <= Real):** 1.0000

**Conclusão do Teste de Hipótese:**
> ⚠️ **HIPÓTESE DE FAMÍLIA NÃO DEMONSTRADA (P-value > 0.05):**
> O padrão observado de agrupamento Modulo 5 (P-value: 0.9950) é estatisticamente comum em dados puramente aleatórios. Ele ocorre em **99.5%** dos conjuntos gerados de forma randômica. Portanto, **não podemos rejeitar a hipótese nula** de que os puzzles são independentes e aleatórios dentro de seus ranges.

## 🗝️ 4. A Hipótese Alternativa: Derivação de HD Wallet com Máscara
A outra IA propôs uma alternativa muito mais simples e robusta para explicar as chaves:
`key = start + f(seed)` ou `key = HD_Wallet_Derive(seed, i) & mask`

Se as chaves forem derivadas de uma HD Wallet determinística:
1. **Independência de Passos:** Comparar vizinhos Modulo 5 não terá nenhuma utilidade prática para prever chaves subsequentes, pois a função hash de derivação (SHA256 ou HMAC-SHA512) quebra qualquer linearidade (distância de Hamming ou XOR).
2. **Offsets Variáveis:** O offset percentual dentro de cada range dependerá exclusivamente de como a máscara foi aplicada. Se a máscara for de bits fixos (ex: pegar apenas os bits menos significativos), a chave ficará espalhada de forma uniforme no range, que é exatamente o que observamos nos dados reais.