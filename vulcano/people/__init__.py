"""
Tomoyo — People Analytics sobre o mesmo motor.

O motor genérico cobre as perguntas agregadas: turnover por área, por que o
eNPS caiu, se o absenteísmo está subindo. Este pacote guarda as três
perguntas que só existem em gente:

- **gap**     — o gap salarial de gênero é de cargo ou de composição? Separa
                o gap bruto do gap ajustado por nível e área.
- **risco**   — onde tem risco de saída nos próximos meses? Lê os sinais que
                vêm ANTES do pedido de demissão (clima, promoção, ausência),
                por grupo.
- **pessoa**  — a pergunta sobre um indivíduo, que a Tomoyo recusa. People
                Analytics fala de grupo; apontar quem vai sair é outro produto,
                com outro contrato de confiança.

Todo dado deste domínio é SIMULADO (ver scripts/build_people.py).
"""
