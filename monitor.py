"""Monitor de promoções de PS5 no Chile -> alerta no Telegram.

Fontes (todas públicas, só biblioteca padrão do Python):
  1. SoloTodo   - API que agrega ~300 lojas chilenas (Falabella, Paris, Ripley, Lider,
                  Hites, PC Factory, Mercado Libre oficial, Claro, marketplaces...)
  2. Knasta     - outro comparador chileno; pega anúncios que o SoloTodo não casou
                  e traz o preço com cartão da loja
  3. Descuentos Rata - comunidade chilena de ofertas: posts de PS5 e CUPONS das lojas

Variáveis de ambiente:
  TELEGRAM_TOKEN     token do bot (@BotFather)
  TELEGRAM_CHAT_IDS  um ou mais chat_id separados por vírgula
Sem elas, roda em modo teste e só imprime as mensagens.

Uso:  python monitor.py              rodada normal
      python monitor.py --resumo     força o resumo de preços
      python monitor.py --teste      manda uma mensagem de teste no Telegram
"""
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(AQUI, "config.json")
STATE = os.path.join(AQUI, "state.json")
HORA_CHILE = timezone(timedelta(hours=-3))  # horário de verão do Chile (set-abr)
HORA_RESUMO = 10
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"

# ----------------------------------------------------------------- utilidades

def baixar(url, json_=True, tentativas=3, cache_bust=True):
    if cache_bust:
        url += ("&" if "?" in url else "?") + f"_={int(time.time())}"
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-CL,es;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                corpo = r.read().decode("utf-8", "replace")
            return json.loads(corpo) if json_ else corpo
        except Exception as ex:  # noqa: BLE001
            if i == tentativas - 1:
                raise RuntimeError(f"{url[:90]}: {ex}") from ex
            time.sleep(3 * (i + 1))


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def preco_int(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    dig = re.sub(r"[^\d]", "", str(v).split(",")[0].split(".")[0] if re.search(r"\.\d{2}$", str(v)) else str(v))
    return int(dig) if dig else None


def clp(v):
    return "$" + f"{v:,}".replace(",", ".")


def chave_loja(loja):
    return re.sub(r"[^a-z]", "", norm(loja))


# ------------------------------------------------- filtro: é um PS5 que serve?

RE_PS5 = re.compile(r"\b(ps ?5|playstation ?5)\b")
RE_SINAL_CONSOLA = re.compile(r"\bconsola\b|\bslim\b|edicion digital|digital edition")
RE_JOGO = re.compile(r"\b(fisico|standard edition|deluxe|day ?1|day one|edicion estandar del juego|juego ps5|videojuego ps5)\b")
RE_ACESSORIO = re.compile(
    r"\b(portal|vr ?2?|cubiertas?|carcasas?|placas?|frontales|skins?|vinilos?|stickers?|soportes?|base|bases|"
    r"cargador|estacion de carga|lente|laser|repuestos?|bolso|mochila|funda|estuche|maleta|ventilador|"
    r"refrigeracion|cooler|volante|pedales|audifonos|headset|microfono|camara|grips?|cable|hdmi|"
    r"ps ?4|ps ?2|ps ?3|reacondicionad[oa]|refurbished|usad[oa]|seminuev[oa]|open ?box|caja vacia|solo caja|"
    r"sin consola|gift ?card|tarjeta psn|psn|membresia|suscripcion|accesorios?|kit de|joystick|mando)\b"
)
RE_PARA = re.compile(r"\b(para|compatible con|compatible)\b (la |el |tu )?(consola|ps ?5|playstation)")
RE_COMECA_ACESSORIO = re.compile(r"^\W*(control|dualsense|lector|unidad|disc drive|juego|videojuego|accesorio)\b")
RE_PRO = re.compile(r"\bpro\b")
RE_CONTROLE = re.compile(r"\+ ?(1 )?(control|dualsense)|2 controles|dos controles|control adicional|dualsense adicional")


def classificar_texto(titulo, cfg):
    """Título livre (Knasta / Descuentos Rata) -> (familia, com_controle) ou None."""
    t = norm(titulo)
    if not RE_PS5.search(t) or not RE_SINAL_CONSOLA.search(t):
        return None
    if RE_COMECA_ACESSORIO.search(t) or RE_PARA.search(t) or RE_JOGO.search(re.sub(r"\+.*$", "", t)):
        return None
    # "+ 2 juegos" e "+ control" são bundle; o resto da lista de acessórios derruba
    if RE_ACESSORIO.search(re.sub(r"\+.*$", "", t)) or re.search(r"\b(usad|reacondicionad|caja vacia|sin consola)", t):
        return None
    if RE_PRO.search(t):
        return ("pro", False) if cfg.get("incluir_pro") else None
    if re.search(r"unidad (de )?disco|lector|disc drive", t):
        fam = "disco"  # digital + leitor vendido junto = PS5 com disco
    elif "digital" in t:
        fam = "digital"
    elif re.search(r"disco|blu-?ray|estandar|standard|\bdisc\b", t):
        fam = "disco"
    else:
        fam = "digital"  # desconhecido: usa o limite mais exigente
    return fam, bool(RE_CONTROLE.search(t))


def classificar_solotodo(nome, cfg):
    """Nome estruturado do catálogo SoloTodo."""
    if "PlayStation 5" not in nome:
        return None
    if re.search(r"PlayStation 5 Pro\b", nome):
        return ("pro", False) if cfg.get("incluir_pro") else None
    if "Blu-Ray" in nome:
        fam = "disco"
    elif "Digital" in nome:
        fam = "digital"
    else:
        return None
    return fam, bool(re.search(r"\+\s*Control", nome, re.I))


def limites(cfg, familia, com_controle):
    f = cfg["familias"].get(familia)
    if not f:
        return None, None
    extra = cfg.get("extra_controle", 0) if com_controle else 0
    return f["bom"] + extra, f["otimo"] + extra


def oferta(fonte, id_, produto, familia, controle, loja, preco, normal, url, **extra):
    o = dict(fonte=fonte, id=f"{fonte}:{id_}", produto=produto, familia=familia, controle=controle,
             loja=loja, preco=int(preco), normal=int(normal or preco), url=url)
    o.update(extra)
    return o


# ------------------------------------------------------------------ fontes

def desconto_cupom(cupom, preco):
    """best_coupon do SoloTodo: amount_type 1 = valor fixo; outro = percentual."""
    if not isinstance(cupom, dict) or not cupom.get("amount"):
        return 0
    valor = float(cupom["amount"])
    desc = valor if cupom.get("amount_type") == 1 else preco * valor / 100
    teto = cupom.get("max_discount_amount")
    if teto:
        desc = min(desc, float(teto))
    return int(min(desc, preco * 0.5))  # trava de segurança contra dado estranho


def fonte_solotodo(cfg):
    api = "https://publicapi.solotodo.com"
    lojas = {s["id"]: s["name"] for s in baixar(f"{api}/stores/?country=1") if s["country"] == 1}
    produtos, url = [], f"{api}/products/browse/?categories=33&search=playstation%205&page_size=100"
    while url:
        d = baixar(url, cache_bust=False) if "_=" in url else baixar(url)
        produtos += [pe["product"] for r in d["results"] for pe in r["product_entries"]]
        url = d.get("next")
    saida = []
    for p in produtos:
        tipo = classificar_solotodo(p["name"], cfg)
        if not tipo:
            continue
        for e in baixar(f"{api}/products/{p['id']}/entities/"):
            reg, loja = e.get("active_registry"), lojas.get(e["store"])
            if not reg or not reg["is_available"] or not e["is_visible"] or loja is None or e.get("currency") != 1:
                continue
            if "NewCondition" not in (e.get("condition") or "") and not cfg.get("incluir_usados"):
                continue
            preco, normal = preco_int(reg["offer_price"]), preco_int(reg["normal_price"])
            cupom, sem_cupom = e.get("best_coupon"), None
            desconto = desconto_cupom(cupom, preco)
            if desconto:
                sem_cupom, preco = preco, preco - desconto
            saida.append(oferta(
                "solotodo", e["id"], p["name"].replace("Sony PlayStation 5 ", "PS5 "), *tipo, loja,
                preco, max(normal, sem_cupom or 0), e["external_url"],
                cupom=cupom, sem_cupom=sem_cupom, vendedor=e.get("seller"),
            ))
    return saida


def _knasta_pagina(q, cat, page):
    params = {"q": q, "page": page}
    if cat:
        params["category"] = cat
    s = baixar("https://knasta.cl/results?" + urllib.parse.urlencode(params), json_=False)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s, re.S)
    if not m:
        raise RuntimeError("Knasta mudou o formato (sem __NEXT_DATA__)")
    return json.loads(m.group(1))["props"]["pageProps"]["initialData"]


def fonte_knasta(cfg):
    vistos, saida = set(), []
    for q, cat, max_pag in [("ps5", "1204913", 4), ("playstation 5", "1204913", 6), ("consola ps5", None, 3)]:
        pag = 1
        while pag <= max_pag:
            d = _knasta_pagina(q, cat, pag)
            for p in d["products"]:
                if p["kid"] in vistos:
                    continue
                vistos.add(p["kid"])
                tipo = classificar_texto(p["title"], cfg)
                preco = preco_int(p.get("current_price"))
                if not tipo or not preco:
                    continue
                cartao = preco_int(p.get("price_card"))
                internet = preco_int(p.get("price_internet")) or preco
                saida.append(oferta(
                    "knasta", p["kid"], p["title"], *tipo, p.get("retail_label") or p["retail"],
                    min(x for x in (preco, cartao) if x), max(internet, preco), p["url"],
                    cartao=cartao, minimo_hist=preco_int(p.get("best_variation_price")),
                    minimo_hist_dia=p.get("best_variation_day"),
                ))
            if pag >= d.get("total_pages", 1):
                break
            pag += 1
            time.sleep(1)
    return saida


def fonte_rata(cfg):
    base = "https://descuentosrata.com"
    d = baixar(f"{base}/api/v1/ofertas/?limit=500&destacados=0")
    posts = []
    for o in d["results"]:
        if not o.get("activo", True):
            continue
        tipo = classificar_texto(o["nombre"], cfg)
        if not tipo:
            continue
        preco = preco_int(o.get("monto"))
        posts.append(oferta(
            "rata", o["id"], re.sub(r"^\W+", "", o["nombre"]).strip(), *tipo, o.get("tienda_nombre") or "?",
            preco or 0, preco_int(o.get("monto_anterior")) or preco or 0,
            f"{base}/oferta/{o['id']}/{o['slug']}", com_cupom=bool(o.get("cupon")),
        ))
    cupons = []
    lojas_alvo = [chave_loja(x) for x in cfg.get("lojas_cupom", [])]
    for c in baixar(f"{base}/api/v1/cupones/?limit=200")["results"]:
        loja = (c.get("tienda") or {}).get("nombre") or ""
        texto = norm(c.get("nombre", "") + " " + loja)
        relevante = any(k in chave_loja(texto) for k in lojas_alvo) or re.search(
            r"tecnolog|electro|gamer|consola|videojuego|playstation|ps5", texto)
        if relevante:
            cupons.append({
                "id": f"cupom:{c['id']}", "nome": re.sub(r"^\W+", "", c.get("nombre", "")).strip(),
                "loja": loja, "codigo": c.get("codigo") or ((c.get("tienda") or {}).get("cupon") or {}).get("codigo"),
                "fim": (c.get("vigencia_fin") or "")[:16].replace("T", " "),
                "url": f"{base}/cupones/{c['id']}/{c.get('slug', '')}",
            })
    return posts, cupons


# --------------------------------------------------------------- mensagens

def eh_marketplace(o):
    lj = norm(o["loja"])
    return "marketplace" in lj or "mercado libre" in lj or "mercadolibre" in lj or o.get("vendedor")


def linha(o, cupons_por_loja=None):
    txt = f"<b>{clp(o['preco'])}</b> · {html.escape(o['loja'])}"
    if o.get("cartao") and o["cartao"] == o["preco"] and o["normal"] > o["preco"]:
        txt += f" <i>(com cartão da loja; sem cartão {clp(o['normal'])})</i>"
    elif o["normal"] > o["preco"]:
        txt += f" <i>(antes/normal {clp(o['normal'])})</i>"
    txt += f"\n{html.escape(o['produto'])}"
    if o.get("minimo_hist"):
        txt += f"\n📉 menor preço já visto: {clp(o['minimo_hist'])} ({o.get('minimo_hist_dia') or '?'})"
    cup = o.get("cupom")
    if isinstance(cup, dict) and cup.get("code"):
        txt += f"\n🎟️ JÁ COM CUPOM <code>{html.escape(cup['code'])}</code>"
        if o.get("sem_cupom"):
            txt += f" (sem cupom {clp(o['sem_cupom'])})"
    if o.get("com_cupom"):
        txt += "\n🎟️ oferta COM CUPOM — o código está no post"
    for c in (cupons_por_loja or {}).get(chave_loja(o["loja"]), [])[:2]:
        txt += f"\n🎟️ cupom ativo na loja: {html.escape(c['nome'][:90])}" + (f" — código <code>{html.escape(c['codigo'])}</code>" if c.get("codigo") else "")
    if eh_marketplace(o):
        txt += "\n⚠️ marketplace: confira a reputação do vendedor"
    txt += f"\n<a href=\"{html.escape(o['url'])}\">👉 abrir</a> <i>({o['fonte']})</i>"
    return txt


def chave_familia(o):
    return o["familia"] + ("+controle" if o["controle"] else "")


def nome_familia(k):
    base = {"digital": "PS5 Slim Digital", "disco": "PS5 Slim com disco", "pro": "PS5 Pro"}[k.split("+")[0]]
    return base + (" + controle extra" if "+controle" in k else "")


# ----------------------------------------------------------------- análise

def analisar(ofertas, posts, cupons, cfg, state, agora):
    alertas = []
    alertados = state.setdefault("alertados", {})
    enviados = state.setdefault("enviados", {})
    menores = state.setdefault("menor_por_familia", {})
    cupons_vistos = state.setdefault("cupons_vistos", {})
    piso, erro = cfg.get("preco_minimo_valido", 150000), cfg.get("abaixo_disso_pode_ser_erro", 380000)

    cupons_por_loja = {}
    for c in cupons:
        cupons_por_loja.setdefault(chave_loja(c["loja"]), []).append(c)

    def ja_enviado(o):
        k = f"{chave_loja(o['loja'])}|{chave_familia(o)}|{o['preco']}"
        if k in enviados:
            return True
        enviados[k] = agora.isoformat(timespec="minutes")
        return False

    vistos = set()
    ofertas = [o for o in ofertas if o["preco"] >= piso]
    for o in ofertas:
        vistos.add(o["id"])
        bom, otimo = limites(cfg, o["familia"], o["controle"])
        if bom is None or o["preco"] > bom:
            alertados.pop(o["id"], None)  # voltou a subir: se cair de novo, avisa de novo
            continue
        anterior = alertados.get(o["id"])
        alertados[o["id"]] = o["preco"]
        if anterior is not None and o["preco"] >= anterior:
            continue
        if ja_enviado(o):
            continue
        if o["preco"] < erro:
            nivel = "🚨 POSSÍVEL ERRO DE PREÇO (corre, mas confira se é console novo e loja séria)"
        elif o["preco"] <= otimo:
            nivel = "🔥 COMPRA JÁ — preço excelente"
        else:
            nivel = "✅ VALE A PENA"
        if anterior:
            nivel += f" (caiu de {clp(anterior)})"
        alertas.append(f"{nivel}\n{linha(o, cupons_por_loja)}")

    for k in [k for k in alertados if k not in vistos]:
        alertados.pop(k)

    melhores = {}
    for o in sorted(ofertas, key=lambda x: x["preco"]):
        melhores.setdefault(chave_familia(o), o)
    for k, o in melhores.items():
        antes = menores.get(k)
        bom, _ = limites(cfg, o["familia"], o["controle"])
        if antes is not None and o["preco"] < antes and (bom is None or o["preco"] > bom) and not ja_enviado(o):
            alertas.append(f"🔻 NOVO MENOR PREÇO — {nome_familia(k)} (antes {clp(antes)})\n{linha(o, cupons_por_loja)}")
        if antes is None or o["preco"] < antes:
            menores[k] = o["preco"]

    for p in posts:  # posts de PS5 na comunidade: sempre avisa (são poucos e curados)
        if p["id"] in alertados:
            continue
        alertados[p["id"]] = p["preco"]
        vistos.add(p["id"])
        alertas.append(f"📣 OFERTA POSTADA NA COMUNIDADE (Descuentos Rata)\n{linha(p, cupons_por_loja)}")
    for k in [k for k in alertados if k.startswith("rata:") and k not in {p['id'] for p in posts}]:
        alertados.pop(k)

    for c in cupons:
        if c["id"] in cupons_vistos:
            continue
        cupons_vistos[c["id"]] = c["fim"]
        cod = f"\nCódigo: <code>{html.escape(c['codigo'])}</code>" if c.get("codigo") else ""
        alertas.append(f"🎟️ NOVO CUPOM — {html.escape(c['loja'] or '?')}\n{html.escape(c['nome'])}{cod}\n"
                       f"válido até {c['fim'] or '?'}\n<a href=\"{html.escape(c['url'])}\">👉 ver cupom</a>")
    ativos = {c["id"] for c in cupons}
    for k in [k for k in cupons_vistos if k not in ativos]:
        cupons_vistos.pop(k)

    limite = (agora - timedelta(hours=36)).isoformat(timespec="minutes")
    for k in [k for k, v in enviados.items() if v < limite]:
        enviados.pop(k)
    return alertas, melhores, cupons_por_loja


def resumo(melhores, cupons_por_loja, cfg, titulo, saude):
    partes = [f"<b>{titulo}</b>"]
    for k in sorted(melhores):
        o = melhores[k]
        bom, otimo = limites(cfg, o["familia"], o["controle"])
        partes.append(f"\n<u>{nome_familia(k)}</u> — vale a pena ≤ {clp(bom)} · compra já ≤ {clp(otimo)}\n{linha(o, cupons_por_loja)}")
    partes.append(f"\n<i>Fontes: {saude}. Confira o total no carrinho antes de pagar.</i>")
    return "\n".join(partes)


def enviar(textos):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    if not token or not chats:
        print("== MODO TESTE (sem TELEGRAM_TOKEN/TELEGRAM_CHAT_IDS) ==")
        for t in textos:
            print(re.sub(r"<[^>]+>", "", html.unescape(t)), "\n" + "-" * 40)
        return
    for chat in chats:
        for t in textos:
            dados = urllib.parse.urlencode({
                "chat_id": chat, "text": t[:4000], "parse_mode": "HTML", "disable_web_page_preview": "true",
            }).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", dados, timeout=30)
            time.sleep(0.4)


# -------------------------------------------------------------------- main

def main():
    if "--descobrir-chat" in sys.argv:  # depois de mandar /start pro bot
        token = os.environ.get("TELEGRAM_TOKEN", "").strip() or input("Token do bot: ").strip()
        d = baixar(f"https://api.telegram.org/bot{token}/getUpdates", cache_bust=False)
        chats = {(u.get("message") or u.get("my_chat_member") or {}).get("chat", {}).get("id"):
                 (u.get("message") or u.get("my_chat_member") or {}).get("chat", {}).get("first_name")
                 for u in d.get("result", [])}
        print(chats or "Nenhuma mensagem ainda: mande /start para o bot no Telegram e rode de novo.")
        return
    if "--teste" in sys.argv:
        enviar(["✅ Teste do monitor de PS5: se você está lendo isto, o Telegram está funcionando!"])
        return
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
    primeira_vez = "menor_por_familia" not in state
    agora = datetime.now(HORA_CHILE)
    falhas = state.setdefault("falhas", {})
    mensagens, ofertas, posts, cupons, ok = [], [], [], [], []

    for nome, fn in [("SoloTodo", fonte_solotodo), ("Knasta", fonte_knasta), ("Descuentos Rata", fonte_rata)]:
        try:
            r = fn(cfg)
            if nome == "Descuentos Rata":
                posts, cupons = r
            else:
                if not r:
                    raise RuntimeError("nenhum PS5 encontrado (formato mudou?)")
                ofertas += r
            ok.append(nome)
            if falhas.get(nome, 0) >= 3:
                mensagens.append(f"✅ Fonte {nome} voltou a funcionar.")
            falhas[nome] = 0
        except Exception as ex:  # noqa: BLE001
            falhas[nome] = falhas.get(nome, 0) + 1
            print(f"[ERRO] {nome}: {ex}")
            if falhas[nome] == 3:
                mensagens.append(f"⚠️ A fonte {nome} falhou 3 vezes seguidas: {html.escape(str(ex)[:200])}\n"
                                 "As outras fontes continuam monitorando.")
    if not ofertas:
        enviar(mensagens) if mensagens else None
        save(state)
        raise SystemExit("nenhuma oferta coletada")

    if "--listar" in sys.argv:  # auditoria do filtro: tudo que passou
        for o in sorted(ofertas + posts, key=lambda x: x["preco"]):
            print(f"{o['preco']:>9,} {chave_familia(o):17} {o['loja'][:18]:18} {o['fonte']:8} {o['produto'][:80]}")
        print("cupons:", [(c["loja"], c["nome"][:60], c.get("codigo")) for c in cupons])
        return

    alertas, melhores, cupons_por_loja = analisar(ofertas, posts, cupons, cfg, state, agora)
    saude = ", ".join(ok)
    hoje = agora.date().isoformat()
    if primeira_vez:
        mensagens.insert(0, resumo(melhores, cupons_por_loja, cfg, "🎮 Monitor de PS5 no Chile LIGADO! Melhores preços agora:", saude))
        state["ultimo_resumo"] = hoje
    elif "--resumo" in sys.argv or (state.get("ultimo_resumo") != hoje and agora.hour >= HORA_RESUMO):
        mensagens.insert(0, resumo(melhores, cupons_por_loja, cfg, f"☀️ Resumo {agora:%d/%m} — melhores preços de PS5", saude))
        state["ultimo_resumo"] = hoje
    mensagens += alertas

    print(f"{len(ofertas)} ofertas ({saude}), {len(posts)} posts, {len(cupons)} cupons, "
          f"{len(alertas)} alertas, {len(mensagens)} mensagens")
    if mensagens:
        enviar(mensagens)
    save(state)


def save(state):
    with open(STATE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(STATE + ".tmp", STATE)


if __name__ == "__main__":
    main()
