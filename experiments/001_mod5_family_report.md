
# Experimento 001: Análise de Famílias Modulo 5 (Finais 0/5)

## 📌 Hipótese
O criador dos Bitcoin Puzzles utilizou uma regra modular ou determinística (passo de 5) para gerar as chaves privadas de forma que chaves da mesma família (Mod 5) herdem parâmetros estatísticos (como offset ou distância de Hamming) similares e restritos.

## 📊 Metodologia
1. Mapeamento de 82 chaves reais resolvidas (Puzzles 1 a 130).
2. Cálculo de desvio padrão do offset normalizado por família Modulo 5.
3. Teste cego Leave-One-Out.
4. Teste de hipótese nula usando Simulação de Monte Carlo com 1.000 sets sintéticos aleatórios nos mesmos intervalos de bits.

## 📈 Resultados
- **Desvio Padrão Global do Offset:** 42.23%
- **Desvio Padrão Médio das Famílias Mod 5:** 42.62%
- **Efeito de Clusterização Mod 5:** -0.38% (Aumento da variância em vez de redução).
- **P-value Monte Carlo:** **0.9950** (99.5% de chance dos dados aleatórios reproduzirem a coesão observada).

## 🏁 Conclusão
**HIPÓTESE REJEITADA.**
A análise estatística rigorosa provou que a coesão observada na "Família Mod 5" é um artefato puramente randômico e não reflete regras do gerador. Os offsets das chaves reais estão distribuídos uniformemente ao longo do range.
Esta hipótese não deve ser incorporada ao Scanner ativo do CycloneX.
