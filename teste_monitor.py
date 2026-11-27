"""Testes do monitor SEM internet: simula várias rodadas seguidas com fontes falsas.
Rodar:  python teste_monitor.py     (sai com erro se algum cenário falhar)
"""
import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monitor as m  # noqa: E402

AGORA = datetime(2026, 11, 27, 12, 0, tzinfo=m.HORA_CHILE)
HOJE = AGORA.strftime("%d-%m-%Y")
CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"), encoding="utf-8"))
ERROS = []


def lido(horas):
    return (AGORA - timedelta(hours=horas)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def st(preco, horas, sku="111111", loja="Lider", fam="disco", ctrl=False):
    return m.oferta("solotodo", f"st{sku}", "PS5 Slim 1 TB (Blu-Ray) teste", fam, ctrl, loja, preco, preco,
                    f"https://loja/{sku}", lido_em=lido(horas), loja_key=m.chave_loja(loja), ids={sku})


def kn(preco, sku="111111", loja="lider", fam="disco", dia=HOJE):
    return m.oferta("knasta", f"{loja}#{sku}", "Consola PS5 Slim teste", fam, False, loja.capitalize(), preco,
                    preco, f"https://loja/{sku}", loja_key=m.chave_loja(loja), ids={sku}, dia=dia)


def pagina(resposta):
    m.precos_da_pagina = lambda url: resposta(url) if callable(resposta) else resposta


def rodada(state, ofertas, pag=([], False), agora=AGORA):
    pagina(pag)
    copia = [dict(o) for o in ofertas]
    alertas, melhores, _ = m.analisar(copia, [], [], CFG, state, agora)
    return alertas, melhores  # mensagem inteira (o formato novo usa várias linhas)


def checa(nome, cond, extra=""):
    print(("OK   " if cond else "ERRO ") + nome + (f"  -> {extra}" if not cond else ""))
    if not cond:
        ERROS.append(nome)


# 1) Caso real da Lider: SoloTodo velho (5h) 599.990 x Knasta de hoje 739.990 -> nada
s = {}
a, mel = rodada(s, [st(599990, 5), kn(739990)])
checa("1a Lider velha: nenhum alerta", a == [], a)
checa("1b resumo usa 739.990 (Knasta)", mel["disco"]["preco"] == 739990, mel["disco"]["preco"])

# 2) SoloTodo lido há 30 min caiu para 609.990, Knasta ainda 739.990 -> avisa (leitura nova vence)
s = {}
a, _ = rodada(s, [st(609990, 0.5), kn(739990)])
checa("2 queda nova no SoloTodo é avisada", len(a) == 1 and "VALE A PENA" in a[0], a)

# 3) Knasta de hoje caiu para 609.990, SoloTodo velho 739.990 -> avisa
s = {}
a, _ = rodada(s, [st(739990, 6), kn(609990)])
checa("3 queda vista só pelo Knasta é avisada", len(a) == 1 and "VALE A PENA" in a[0], a)

# 4) Avisa, esgota (1 encerrada só), segue esgotado (nada), repõe ao mesmo preço (avisa de novo)
s = {}
ofs = [st(609990, 0.5)]
a1, _ = rodada(s, ofs, pag=([609990], False))
a2, _ = rodada(s, ofs, pag=([609990], True), agora=AGORA + timedelta(minutes=25))
a3, _ = rodada(s, ofs, pag=([609990], True), agora=AGORA + timedelta(minutes=50))
a4, _ = rodada(s, ofs, pag=([609990], True), agora=AGORA + timedelta(minutes=75))
a5, _ = rodada(s, ofs, pag=([609990], False), agora=AGORA + timedelta(minutes=100))
checa("4a alerta inicial", len(a1) == 1 and "VALE A PENA" in a1[0], a1)
checa("4b esgotou -> 1 encerrada", len(a2) == 1 and "ENCERRADA" in a2[0] and "esgotou" in a2[0].lower(), a2)
checa("4c continua esgotado -> silêncio", a3 == [] and a4 == [], (a3, a4))
checa("4d reposição -> avisa de novo", len(a5) == 1 and "VALE A PENA" in a5[0], a5)

# 5) Pingue-pongue de hoje (página diz 599.990 mas esgotado; Knasta 739.990): 8 rodadas, no máx. 1 msg
s = {"alertados": {"solotodo:st111111": 599990}, "enviados": {"lider|disco|599990": AGORA.isoformat()}}
total = []
for i in range(8):
    a, _ = rodada(s, [st(599990, 5 + i * 0.1), kn(739990)], pag=([599990], True),
                  agora=AGORA + timedelta(minutes=5 * i))
    total += a
checa("5 sem 'encerrada' repetida (máx. 1)", len(total) <= 1, total)

# 5b) Resumo nunca mostra oferta esgotada como a melhor
s = {}
_, mel = rodada(s, [st(609990, 0.5, sku="444444"), st(689990, 0.5, sku="555555", loja="Paris")],
                pag=lambda url: ([609990], True) if "444444" in url else ([689990], False))
checa("5b resumo pula esgotado", mel["disco"]["loja"] == "Paris", mel["disco"]["loja"])

# 6) Página com produto relacionado barato (59.990) não vira 'erro de preço'
s = {}
a, _ = rodada(s, [st(609990, 0.5)], pag=([59990], False))
checa("6 preço absurdo da página é ignorado", len(a) == 1 and "ERRO DE PREÇO" not in a[0], a)

# 7) Página da loja desmente (está 699.990) -> não avisa
s = {}
a, _ = rodada(s, [st(569990, 0.5)], pag=([699990], False))
checa("7 página desmente -> sem alerta", a == [], a)

# 8) Já avisado e caiu mais -> avisa 'caiu de'
s = {}
rodada(s, [st(609990, 0.5)])
a, _ = rodada(s, [st(569990, 0.5)], agora=AGORA + timedelta(minutes=5))
checa("8 queda adicional avisa 'caiu de'", len(a) == 1 and "caiu de" in a[0], a)

# 9) Mesma oferta nas 2 fontes, mesmo preço -> 1 alerta só
s = {}
a, _ = rodada(s, [st(609990, 0.5), kn(609990)])
checa("9 duas fontes iguais -> 1 alerta", len(a) == 1, a)

# 10) Leitura velha sem confirmação: 'vale a pena' não sai; preço excelente sai marcado
s = {}
a, _ = rodada(s, [st(609990, 6, sku="222222", loja="Falabella")])
checa("10a velho + vale a pena -> nada", a == [], a)
a, _ = rodada(s, [st(569990, 6, sku="333333", loja="Falabella")])
checa("10b velho + excelente -> NÃO CONFIRMADO", len(a) == 1 and "não confirmado" in a[0].lower(), a)

# 11) Telegram: HTML recusado -> manda texto puro; Telegram fora -> erro (não grava estado)
chamadas = []


def falso_urlopen(url, dados=None, timeout=None):
    chamadas.append(dados)
    if b"parse_mode=HTML" in dados:
        raise urllib.error.HTTPError(url, 400, "bad", {}, __import__("io").BytesIO(b'{"description":"cant parse"}'))
    return None


orig = m.urllib.request.urlopen
os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_IDS"] = "x", "1"
m.time.sleep = lambda s: None
m.urllib.request.urlopen = falso_urlopen
try:
    m.enviar(["<b>teste & </b"])
    checa("11a HTML inválido -> reenvia em texto puro", len(chamadas) == 2, chamadas)
    m.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("sem rede"))
    try:
        m.enviar(["oi"])
        checa("11b Telegram fora -> levanta erro", False)
    except RuntimeError:
        checa("11b Telegram fora -> levanta erro", True)
finally:
    m.urllib.request.urlopen = orig
    del os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_IDS"]

# 11c) 'Novo menor preço' só para o Digital (foco); disco só avisa na faixa boa
s = {}
rodada(s, [st(700000, 0.5, sku="d1", fam="digital"), st(760000, 0.5, sku="c1")])
a, _ = rodada(s, [st(680000, 0.5, sku="d1", fam="digital"), st(740000, 0.5, sku="c1")],
              agora=AGORA + timedelta(minutes=5))
checa("11c novo menor: só Digital", len(a) == 1 and "Digital" in a[0], a)

# 12) Filtro de título
casos = {
    "Consola PS5 Slim Digital Caja Abierta": None,
    "Consola PS5 Slim Edición Digital - Exhibición": None,
    "Consola Sony PS5 PlayStation 5 - Slim (Edición Digital)": ("digital", False),
    "Consola PS5 Slim Standard 1TB + 2 Juegos PS5 Sony": ("disco", False),
    "UFC 5 Standard Edition PS5 Fisico": None,
    "Control Inalámbrico Dualsense PS5": None,
}
for t, esp in casos.items():
    checa(f"12 filtro: {t[:45]}", m.classificar_texto(t, CFG) == esp, m.classificar_texto(t, CFG))

# 13) Sinal de vida silencioso: só depois de N horas sem nenhuma mensagem
mel = {"digital": st(619990, 0.5, sku="d1", fam="digital", loja="Lider"), "disco": st(599990, 0.5)}
s = {}
txt = m.sinal_de_vida(s, mel, CFG, AGORA, "nuvem", "SoloTodo")
checa("13a primeira vez manda", txt is not None and "nada novo" in txt and "619.990" in txt, txt)
s = {"ultimo_sinal": (AGORA - timedelta(minutes=40)).isoformat(timespec="minutes")}
checa("13b 40 min depois: não manda", m.sinal_de_vida(s, mel, CFG, AGORA, "pc", "x") is None)
s = {"ultimo_sinal": (AGORA - timedelta(hours=2)).isoformat(timespec="minutes")}
checa("13c 2 h depois: manda", m.sinal_de_vida(s, mel, CFG, AGORA, "pc", "x") is not None)
checa("13d 0 desliga", m.sinal_de_vida({}, mel, {**CFG, "sinal_de_vida_horas": 0}, AGORA, "pc", "x") is None)

print(f"\n{len(ERROS)} erro(s)")
sys.exit(1 if ERROS else 0)
