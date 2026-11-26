# Monitor de PS5 no Chile 🎮🇨🇱

Checa a cada ~5 minutos os preços de PS5 Slim (Digital, com disco e bundles) no Chile e avisa no Telegram.

**Fontes:** SoloTodo (≈300 lojas: Falabella, Paris, Ripley, Lider, Hites, PC Factory, Mercado Libre oficial, Claro, marketplaces…) + Knasta (preço com cartão, histórico) + Descuentos Rata (posts da comunidade e cupons).

## Alertas
| Alerta | Quando |
|---|---|
| 🚨 POSSÍVEL ERRO DE PREÇO | console abaixo de $380.000 |
| 🔥 COMPRA JÁ | Digital ≤ $549.990 · Disco ≤ $579.990 (+$60.000 se vier controle extra) |
| ✅ VALE A PENA | Digital ≤ $579.990 · Disco ≤ $619.990 (+$60.000 com controle) |
| 🔻 NOVO MENOR PREÇO | o menor preço da categoria caiu, mesmo acima da faixa |
| 📣 COMUNIDADE | alguém postou PS5 no Descuentos Rata |
| 🎟️ NOVO CUPOM | cupom novo nas lojas grandes ou de tecnologia |
| ☀️ Resumo | todo dia às 10h (Chile) |

O preço usado é o menor possível: com cartão da loja e já com o cupom do SoloTodo, quando houver. A mensagem mostra também o preço sem cartão e sem cupom.

Faixas e lojas ficam em `config.json`.

## Como confere antes de avisar
1. Cruza o mesmo anúncio no SoloTodo e no Knasta (pelo SKU). Se discordarem, vale a leitura mais nova; na dúvida, o preço mais alto.
2. Tenta ler o preço **e o estoque** na página da loja (só o produto principal). Esgotado = sem alerta.
3. "Vale a pena" só sai com preço confirmado ou lido há ≤2h. Sem confirmação, só o "compra já", e marcado ⚠️ NÃO CONFIRMADO.
4. Se uma oferta avisada esgotar ou subir, chega ❌ OFERTA ENCERRADA (uma vez só). Se voltar, avisa de novo.

## Onde roda
- **Nuvem (GitHub Actions)** a cada ~5 min. Lá o Knasta é bloqueado, então usa SoloTodo + Descuentos Rata.
- **PC (ajudante local)** `rodar_local.py`, pelo Agendador do Windows (tarefa `MonitorPS5Chile`), a cada 5 min. Com o PC ligado e todas as fontes lendo, a nuvem pula as rodadas (sinal de vida). Se a rede bloquear algo, a nuvem continua. `python rodar_local.py --testar-rede` mostra o que a rede deixa passar.

## Comandos
```
python monitor.py --listar          # mostra tudo o que passou no filtro (auditoria)
python monitor.py --resumo          # força o resumo
python monitor.py --teste           # mensagem de teste no Telegram
python monitor.py --descobrir-chat  # descobre o chat_id depois do /start no bot
python teste_monitor.py             # 26 cenários simulados, sem internet
```

## Limitações (honestas)
- O SoloTodo e o Knasta releem cada loja de tempos em tempos (de minutos a algumas horas), então um "relâmpago" de 10 minutos pode escapar. Os posts do Descuentos Rata ajudam a cobrir isso.
- Amazon, Weplay, Zmart e Microplay bloqueiam robôs; essas lojas só entram quando aparecem no SoloTodo ou no Knasta.
- Cupons de app/banco que não estão publicados em lugar nenhum não têm como ser vistos.
