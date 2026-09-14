"""
Ravena — monitoramento PLD/FT sobre o mesmo motor.

O domínio de Compliance tem duas camadas, e cada uma responde a uma pessoa:

- **A operação de monitoramento, sumarizada** (quantos alertas, quanto vira
  falso positivo, se a fila está dentro do prazo). É o que a liderança de
  Compliance acompanha, e roda no motor genérico — mesma camada semântica,
  mesmos alertas, mesma causa raiz dos outros domínios.
- **Os clientes em atenção, um a um** (quem se enquadra em qual situação da
  Carta Circular 4.001, com qual evidência e em quanto tempo vence o prazo de
  análise). É o que a analista abre de manhã. Mora neste pacote.

    regras.py      catálogo de regras: parâmetro, racional, enquadramento
    normas.py      os trechos das circulares que o painel cita
    calendario.py  dias úteis — o prazo de comunicação é em dia útil
    fila.py        prioridade explicável e a posição da fila em qualquer data
    parecer.py     o rascunho de dossiê que a Ravena escreve
    agente.py      as intenções que só fazem sentido em PLD

Todo dado deste domínio é SIMULADO (ver scripts/build_pld.py). A empresa, os
clientes e os estabelecimentos são fictícios; as regras e as referências
normativas são reais.
"""
