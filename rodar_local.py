"""Ajudante local: roda o monitor completo no PC (Knasta + páginas das lojas funcionam
melhor com IP de casa) e avisa a nuvem com um "sinal de vida" para não duplicar alertas.

Se a rede bloquear Telegram ou GitHub, ele NÃO faz nada e a nuvem continua sozinha.
Chamado pelo Agendador de Tarefas do Windows a cada 5 min (tarefa "MonitorPS5Chile").

  python rodar_local.py                 uma rodada
  python rodar_local.py --testar-rede   mostra o que a rede atual deixa passar
"""
import json
import os
import subprocess
import sys
import traceback
import urllib.request
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
SEGREDOS = os.path.join(AQUI, "segredos_local.json")  # fora do git (.gitignore)
LOG = os.path.join(AQUI, "local.log")
SEM_JANELA = 0x08000000 if os.name == "nt" else 0


def log(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n"
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 300_000:
            with open(LOG, encoding="utf-8", errors="ignore") as f:
                resto = f.readlines()[-500:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(resto)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha)
    except OSError:
        pass
    try:
        print(linha, end="")
    except Exception:  # noqa: BLE001  (pythonw não tem console)
        pass


def git(*args, timeout=60):
    return subprocess.run(["git", *args], cwd=AQUI, capture_output=True, text=True,
                          timeout=timeout, creationflags=SEM_JANELA)


def voltar_ao_github():
    """Descarta só o estado local não enviado; o código local fica intacto."""
    git("rebase", "--abort")
    git("reset", "-q", "@{u}")
    git("checkout", "--", "state.json")


def alcanca(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400, f"HTTP {r.status}"
    except Exception as ex:  # noqa: BLE001
        return False, str(ex)[:80]


def testar_rede(token):
    alvos = [
        ("Telegram (essencial)", f"https://api.telegram.org/bot{token}/getMe"),
        ("GitHub (essencial)", "https://github.com/victormfsilva/ps5-chile-monitor"),
        ("SoloTodo", "https://publicapi.solotodo.com/stores/?country=1"),
        ("Knasta", "https://knasta.cl/results?q=ps5&category=1204913"),
        ("Descuentos Rata", "https://descuentosrata.com/api/v1/cupones/?limit=1"),
        ("Página Paris", "https://www.paris.cl/"),
        ("Página Lider", "https://www.lider.cl/"),
    ]
    for nome, url in alvos:
        ok, info = alcanca(url)
        print(f"{'OK   ' if ok else 'FALHA'} {nome:22} {info}")
    g = git("ls-remote", "--heads", "origin", timeout=30)
    print(f"{'OK   ' if g.returncode == 0 else 'FALHA'} {'git push/pull':22} {g.stderr.strip()[:80]}")
    print("\nSe Telegram e GitHub/git estiverem OK, o PC ajuda; se não, a nuvem cuida sozinha (sem problema).")


def main():
    seg = json.load(open(SEGREDOS, encoding="utf-8"))
    os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_IDS"] = seg["TELEGRAM_TOKEN"], seg["TELEGRAM_CHAT_IDS"]
    if "--testar-rede" in sys.argv:
        testar_rede(seg["TELEGRAM_TOKEN"])
        return

    ok, info = alcanca(f"https://api.telegram.org/bot{seg['TELEGRAM_TOKEN']}/getMe")
    if not ok:
        log(f"Telegram inacessível nesta rede ({info}) — a nuvem cuida.")
        return
    git("checkout", "--", "state.json")  # o estado oficial é o do GitHub
    r = git("pull", "--rebase", "--autostash", "-q")
    if r.returncode != 0:
        voltar_ao_github()
        r = git("pull", "--rebase", "--autostash", "-q")
        if r.returncode != 0:
            voltar_ao_github()
            log(f"GitHub inacessível ({r.stderr.strip()[:120]}) — a nuvem cuida.")
            return

    sys.path.insert(0, AQUI)
    import monitor  # noqa: E402
    try:
        sys.argv = [sys.argv[0]]
        monitor.main()
    except BaseException as ex:  # noqa: BLE001
        log(f"monitor falhou: {ex!r}\n{traceback.format_exc()[-600:]}")
        git("checkout", "--", "state.json")
        return

    st = json.load(open(monitor.STATE, encoding="utf-8"))
    completo = all(st.get("falhas", {}).get(f"{n}@pc", 1) == 0 for n in ("SoloTodo", "Knasta"))
    if completo:  # só "assume" se leu as 2 fontes; senão a nuvem continua rodando junto
        st["heartbeat_local"] = datetime.now(monitor.HORA_CHILE).isoformat(timespec="minutes")
    else:
        log("rede bloqueou alguma fonte — a nuvem continua rodando junto (memória compartilhada)")
    monitor.save(st)
    git("add", "state.json")
    git("-c", "user.name=monitor-ps5-pc", "-c", "user.email=victormfsilva@users.noreply.github.com",
        "commit", "-q", "-m", f"estado (PC) {datetime.now():%H:%M}")
    for _ in range(2):
        p = git("push", "-q")
        if p.returncode == 0:
            log("rodada OK (PC)")
            return
        if git("pull", "--rebase", "--autostash", "-q").returncode != 0:
            break
    voltar_ao_github()
    log(f"não consegui enviar o estado ({p.stderr.strip()[:120]}) — a nuvem segue; pode haver alerta repetido")


if __name__ == "__main__":
    main()
