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

## Comandos
```
python monitor.py --listar          # mostra tudo o que passou no filtro (auditoria)
python monitor.py --resumo          # força o resumo
python monitor.py --teste           # mensagem de teste no Telegram
python monitor.py --descobrir-chat  # descobre o chat_id depois do /start no bot
```

## Limitações (honestas)
- O SoloTodo e o Knasta releem cada loja de tempos em tempos (de minutos a algumas horas), então um "relâmpago" de 10 minutos pode escapar. Os posts do Descuentos Rata ajudam a cobrir isso.
- Amazon, Weplay, Zmart e Microplay bloqueiam robôs; essas lojas só entram quando aparecem no SoloTodo ou no Knasta.
- Cupons de app/banco que não estão publicados em lugar nenhum não têm como ser vistos.
