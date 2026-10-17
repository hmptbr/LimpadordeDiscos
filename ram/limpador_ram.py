#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIMPADOR RAM  -  monitor de memória em tempo real para Linux

Mostra a RAM, a swap e a "pressão de memória" (o indicador que diz se o
computador está mesmo a ficar lento por falta de RAM), agrupa os processos
por aplicação e deixa-te fechar o que não precisas.

Modo automático: quando a memória aperta, fecha sozinho as apps que TU
marcaste como "pode fechar", começando pelas maiores que estão paradas.
Nunca toca em processos do sistema, do ambiente de trabalho ou de outros
utilizadores.

Só usa a biblioteca padrão do Python. A janela abre no navegador.

Uso:
  limpador-ram              abre a janela
  limpador-ram --fundo      corre em segundo plano (modo automático), sem janela
  limpador-ram --estado     mostra um resumo no terminal e sai
"""
import argparse
import http.server
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque

VERSAO = "1.0"
UID = os.getuid()
EU = os.getpid()
PAGINA = os.sysconf("SC_PAGE_SIZE")
TICKS = os.sysconf("SC_CLK_TCK")

DIR_CONFIG = os.path.join(os.path.expanduser("~"), ".config", "limpador-ram")
F_CONFIG = os.path.join(DIR_CONFIG, "config.json")
DIR_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "limpador-ram")
F_INSTANCIA = os.path.join(DIR_CACHE, "instancia.json")
F_REGISTO = os.path.join(os.path.expanduser("~"), ".limpador", "ram-registo.txt")
F_AUTOSTART = os.path.join(os.path.expanduser("~"), ".config", "autostart", "limpador-ram.desktop")

# Nunca fechar: sistema, ambiente de trabalho, som, rede, terminais e shells.
PROTEGIDOS = {
    "systemd", "dbus-daemon", "dbus-broker", "dbus-launch", "gnome-shell", "gnome-session-binary",
    "gnome-session", "gnome-keyring-daemon", "gnome-terminal-server", "gnome-settings-daemon",
    "mutter", "Xorg", "Xwayland", "X", "plasmashell", "kwin_x11", "kwin_wayland", "ksmserver",
    "kded5", "kded6", "konsole", "kgx", "ptyxis", "tilix", "xterm", "alacritty", "kitty", "wezterm",
    "terminator", "xfce4-terminal", "mate-terminal", "lxterminal", "qterminal", "cinnamon",
    "cinnamon-session", "muffin", "marco", "xfwm4", "xfce4-session", "xfce4-panel", "xfdesktop",
    "xfsettingsd", "mate-session", "mate-panel", "budgie-wm", "budgie-panel", "lxqt-session",
    "openbox", "i3", "sway", "hyprland", "Hyprland", "waybar", "pipewire", "pipewire-pulse",
    "wireplumber", "pulseaudio", "NetworkManager", "nm-applet", "polkitd", "ibus-daemon",
    "ibus-x11", "fcitx5", "at-spi-bus-launcher", "at-spi2-registryd", "xdg-desktop-portal",
    "xdg-document-portal", "xdg-permission-store", "gvfsd", "bash", "zsh", "fish", "sh", "dash",
    "sshd", "ssh-agent", "gpg-agent", "login", "sudo", "su", "gdm", "sddm", "lightdm", "evolution-source-registry",
}
PREFIXOS_PROTEGIDOS = ("gsd-", "gvfs", "xdg-", "at-spi", "kwin", "xfce4-", "mate-settings",
                       "cinnamon-", "budgie-", "lxqt-", "plasma-", "pipewire", "ibus-", "gnome-shell")

# Sugestões já marcadas para o modo automático: apps de fundo que voltam a abrir
# sozinhas quando são precisas e não guardam trabalho por gravar.
SUGERIDOS = ["gnome-software", "snap-store", "update-notifier", "tracker-miner-fs-3",
             "tracker-miner-fs", "localsearch-3", "baloo_file", "baloorunner", "discover", "mintUpdate",
             "mintupdate-launcher", "packagekitd", "evolution-alarm-notify", "zeitgeist-daemon"]

INTERPRETADORES = ("python", "node", "java", "perl", "ruby", "bash", "sh", "php", "mono", "dotnet", "electron")

NOMES = {
    "chrome": "Google Chrome", "google-chrome": "Google Chrome", "chromium": "Chromium",
    "chromium-browser": "Chromium", "brave": "Brave", "firefox": "Firefox", "firefox-bin": "Firefox",
    "opera": "Opera", "vivaldi-bin": "Vivaldi", "msedge": "Microsoft Edge", "code": "VS Code",
    "codium": "VSCodium", "slack": "Slack", "discord": "Discord", "Discord": "Discord", "spotify": "Spotify",
    "telegram-desktop": "Telegram", "thunderbird": "Thunderbird", "soffice.bin": "LibreOffice",
    "nautilus": "Ficheiros (Nautilus)", "dolphin": "Ficheiros (Dolphin)", "gnome-software": "Loja de aplicações",
    "snap-store": "Loja de aplicações (Snap)", "tracker-miner-fs-3": "Indexador de ficheiros",
    "localsearch-3": "Indexador de ficheiros", "baloo_file": "Indexador de ficheiros (KDE)",
    "gnome-system-monitor": "Monitor do sistema", "evolution-alarm-notify": "Alarmes do calendário",
    "update-notifier": "Avisos de atualização", "packagekitd": "Serviço de atualizações",
    "studio": "Android Studio", "qemu-system-x86_64": "Emulador Android", "dockerd": "Docker",
    "antigravity": "Antigravity", "obsidian": "Obsidian", "whatsapp-desktop": "WhatsApp",
}


# ---------------------------------------------------------------- utilitários
def fmt(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024 or u == "TB":
            return f"{b:.0f} {u}" if u in ("B", "KB", "MB") else f"{b:.1f} {u}"
        b /= 1024


def ler(caminho, binario=False):
    try:
        with open(caminho, "rb" if binario else "r") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def registar(msg):
    try:
        os.makedirs(os.path.dirname(F_REGISTO), exist_ok=True)
        with open(F_REGISTO, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def notificar(titulo, texto):
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", "Limpador RAM", "-i", "limpador-ram", titulo, texto],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def carregar_config():
    cfg = {"auto": False, "auto_lista": list(SUGERIDOS), "limiar_pressao": 15,
           "ram_minima_pct": 10, "ocioso_min": 5, "segundo_plano": False}
    dados = ler(F_CONFIG)
    if dados:
        try:
            cfg.update(json.loads(dados))
        except ValueError:
            pass
    return cfg


def guardar_config(cfg):
    os.makedirs(DIR_CONFIG, exist_ok=True)
    tmp = F_CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, F_CONFIG)


def protegido(chave):
    return chave in PROTEGIDOS or chave.startswith(PREFIXOS_PROTEGIDOS) or chave.startswith("limpador")


# ---------------------------------------------------------------- leitura do sistema
def memoria():
    m = {}
    for linha in (ler("/proc/meminfo") or "").splitlines():
        k, _, v = linha.partition(":")
        try:
            m[k] = int(v.split()[0]) * 1024
        except (IndexError, ValueError):
            pass
    total = m.get("MemTotal", 1)
    disp = m.get("MemAvailable", m.get("MemFree", 0))
    cache = m.get("Cached", 0) + m.get("Buffers", 0) + m.get("SReclaimable", 0) - m.get("Shmem", 0)
    st, sf = m.get("SwapTotal", 0), m.get("SwapFree", 0)
    pressao = {"some10": 0.0, "some60": 0.0, "full10": 0.0, "disponivel": False}
    p = ler("/proc/pressure/memory")
    if p:
        pressao["disponivel"] = True
        for linha in p.splitlines():
            partes = linha.split()
            campos = dict(x.split("=") for x in partes[1:])
            if partes[0] == "some":
                pressao["some10"], pressao["some60"] = float(campos["avg10"]), float(campos["avg60"])
            elif partes[0] == "full":
                pressao["full10"] = float(campos["avg10"])
    swaps = (ler("/proc/swaps") or "").splitlines()[1:]
    zram = any("zram" in s for s in swaps)
    return {"total": total, "usada": total - disp, "disponivel": disp, "cache": max(cache, 0),
            "swap_total": st, "swap_usada": st - sf, "pressao": pressao, "zram": zram}


def chave_app(pid, comm):
    """Nome que agrupa os processos de uma mesma aplicação."""
    exe = None
    try:
        exe = os.path.basename(os.readlink(f"/proc/{pid}/exe")).replace(" (deleted)", "")
    except OSError:
        pass
    nome = exe or comm
    if nome.startswith(INTERPRETADORES):
        cmd = (ler(f"/proc/{pid}/cmdline", True) or b"").split(b"\0")
        for arg in cmd[1:]:
            a = arg.decode(errors="replace")
            if a and not a.startswith("-"):
                base = os.path.basename(a.rstrip("/"))
                if base and base != "-c":
                    return base.removesuffix(".py").removesuffix(".js")
                break
    return nome


class Monitor:
    def __init__(self):
        self.cfg = carregar_config()
        self.trinco = threading.RLock()
        self.historico = deque(maxlen=120)  # 2 minutos, 1 amostra por segundo
        self.mem = memoria()
        self.apps = {}
        self.cpu_ant = {}  # pid -> ticks
        self.t_ant = time.monotonic()
        self.ultima_atividade = {}  # chave -> instante
        self.acoes = deque(maxlen=30)
        self.ultimo_auto = 0.0
        self.a_fechar = {}  # chave -> instante do SIGTERM
        self.ultimo_pedido = time.monotonic()

    # --- amostragem
    def amostrar_memoria(self):
        m = memoria()
        with self.trinco:
            self.mem = m
            self.historico.append({"t": time.time(), "ram": m["usada"] / m["total"] * 100,
                                   "swap": (m["swap_usada"] / m["swap_total"] * 100) if m["swap_total"] else 0,
                                   "pressao": m["pressao"]["some10"]})

    def amostrar_processos(self):
        agora = time.monotonic()
        dt = max(agora - self.t_ant, 0.1)
        apps, cpu_novo = {}, {}
        for nome in os.listdir("/proc"):
            if not nome.isdigit():
                continue
            pid = int(nome)
            try:
                if os.stat(f"/proc/{pid}").st_uid != UID or pid == EU:
                    continue
            except OSError:
                continue
            stat = ler(f"/proc/{pid}/stat")
            if not stat:
                continue
            fecho = stat.rfind(")")
            comm = stat[stat.find("(") + 1:fecho]
            campos = stat[fecho + 2:].split()
            if campos[0] == "Z":
                continue
            ticks = int(campos[11]) + int(campos[12])
            cpu_novo[pid] = ticks
            pss = swap = 0
            roll = ler(f"/proc/{pid}/smaps_rollup")
            if roll:
                for linha in roll.splitlines():
                    if linha.startswith("Pss:"):
                        pss = int(linha.split()[1]) * 1024
                    elif linha.startswith("SwapPss:"):
                        swap = int(linha.split()[1]) * 1024
            else:
                st = (ler(f"/proc/{pid}/statm") or "0 0").split()
                pss = int(st[1]) * PAGINA
            if pss == 0 and swap == 0:
                continue  # threads do kernel, processos sem memória própria
            chave = chave_app(pid, comm)
            a = apps.setdefault(chave, {"chave": chave, "nome": NOMES.get(chave, chave), "mem": 0, "swap": 0,
                                        "pids": [], "cpu": 0.0})
            a["mem"] += pss
            a["swap"] += swap
            a["pids"].append(pid)
            a["cpu"] += max(ticks - self.cpu_ant.get(pid, ticks), 0) / TICKS / dt * 100
        with self.trinco:
            for chave, a in apps.items():
                if a["cpu"] > 1.0 or chave not in self.ultima_atividade:
                    self.ultima_atividade[chave] = agora
                a["parada_s"] = int(agora - self.ultima_atividade[chave])
                a["protegido"] = protegido(chave)
                a["auto"] = chave in self.cfg["auto_lista"]
                a["n"] = len(a["pids"])
                a["a_fechar"] = chave in self.a_fechar
            self.apps = apps
            self.cpu_ant, self.t_ant = cpu_novo, agora

    # --- ações
    def fechar(self, chave, forcar=False, motivo="manual"):
        with self.trinco:
            a = self.apps.get(chave)
        if not a:
            return False, "Essa app já não está aberta."
        if a["protegido"]:
            return False, f"{a['nome']} faz parte do sistema e não pode ser fechado."
        sinal = signal.SIGKILL if forcar else signal.SIGTERM
        n = 0
        for pid in a["pids"]:
            try:
                if os.stat(f"/proc/{pid}").st_uid == UID:
                    os.kill(pid, sinal)
                    n += 1
            except OSError:
                pass
        msg = f"{'Forçado o fecho de' if forcar else 'Fechado'} {a['nome']} ({fmt(a['mem'] + a['swap'])}, {n} processos) - {motivo}"
        registar(msg)
        with self.trinco:
            self.acoes.appendleft({"t": time.strftime("%H:%M:%S"), "msg": msg})
            if not forcar:
                self.a_fechar[chave] = time.monotonic()
        return True, msg

    def precisa_aliviar(self):
        m = self.mem
        p = m["pressao"]
        pouca_ram = m["disponivel"] / m["total"] * 100 < self.cfg["ram_minima_pct"]
        if p["disponivel"]:
            return p["some10"] >= self.cfg["limiar_pressao"] or (pouca_ram and p["some10"] >= 2)
        swap_cheia = m["swap_total"] and m["swap_usada"] / m["swap_total"] > 0.8
        return pouca_ram and bool(swap_cheia)

    def ciclo_auto(self):
        agora = time.monotonic()
        # quem recebeu SIGTERM há mais de 10 s e continua aberto: forçar (só no modo automático)
        for chave, t in list(self.a_fechar.items()):
            if agora - t > 10:
                with self.trinco:
                    ainda = chave in self.apps
                    self.a_fechar.pop(chave, None)
                if ainda and self.cfg["auto"] and chave in self.cfg["auto_lista"]:
                    self.fechar(chave, forcar=True, motivo="não respondeu ao pedido de fecho")
        if not self.cfg["auto"] or agora - self.ultimo_auto < 20 or not self.precisa_aliviar():
            return
        ocioso = self.cfg["ocioso_min"] * 60
        with self.trinco:
            candidatos = sorted((a for a in self.apps.values()
                                 if a["chave"] in self.cfg["auto_lista"] and not a["protegido"] and a["chave"] not in self.a_fechar
                                 and a["parada_s"] >= ocioso and a["mem"] + a["swap"] > 30 * 1024 * 1024),
                                key=lambda a: a["mem"] + a["swap"], reverse=True)
        if candidatos:
            a = candidatos[0]
            ok, msg = self.fechar(a["chave"], motivo="memória a ficar cheia (modo automático)")
            if ok:
                notificar("Memória libertada", f"Fechei {a['nome']} ({fmt(a['mem'] + a['swap'])}) porque a RAM estava a acabar.")
            self.ultimo_auto = agora

    def instantaneo(self):
        with self.trinco:
            apps = sorted(self.apps.values(), key=lambda a: a["mem"] + a["swap"], reverse=True)
            return {"mem": self.mem, "historico": list(self.historico), "acoes": list(self.acoes),
                    "cfg": self.cfg, "precisa_aliviar": self.precisa_aliviar(),
                    "autostart": os.path.exists(F_AUTOSTART), "versao": VERSAO,
                    "apps": [{k: v for k, v in a.items() if k != "pids"} for a in apps[:60]]}

    def laco(self):
        n = 0
        while True:
            try:
                self.amostrar_memoria()
                if n % 2 == 0:
                    self.amostrar_processos()
                    self.ciclo_auto()
            except Exception as e:  # nunca deixar o monitor morrer
                registar(f"erro: {e!r}")
            n += 1
            time.sleep(1)


# ---------------------------------------------------------------- arranque com o sistema
def definir_autostart(ligar):
    if ligar:
        os.makedirs(os.path.dirname(F_AUTOSTART), exist_ok=True)
        exe = shutil.which("limpador-ram") or f"{sys.executable} {os.path.abspath(__file__)}"
        with open(F_AUTOSTART, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Limpador RAM\n"
                    f"Exec={exe} --fundo\nIcon=limpador-ram\nX-GNOME-Autostart-enabled=true\n"
                    "NoDisplay=true\nComment=Vigia a memória em segundo plano\n")
    elif os.path.exists(F_AUTOSTART):
        os.remove(F_AUTOSTART)


# ---------------------------------------------------------------- servidor da janela
def criar_servidor(mon, token, fundo):
    class Pedido(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _resp(self, codigo, corpo, tipo="application/json"):
            dados = corpo.encode() if isinstance(corpo, str) else corpo
            self.send_response(codigo)
            self.send_header("Content-Type", tipo + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _autorizado(self):
            return secrets.compare_digest(self.headers.get("X-Token", ""), token)

        def _host_ok(self):
            # Protege contra páginas maliciosas que tentem falar com o servidor (DNS rebinding).
            return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

        def do_GET(self):
            if not self._host_ok():
                return self._resp(403, "{}")
            if self.path.split("?")[0] == "/":
                self._resp(200, HTML, "text/html")
            elif self.path == "/dados" and self._autorizado():
                mon.ultimo_pedido = time.monotonic()
                self._resp(200, json.dumps(mon.instantaneo()))
            else:
                self._resp(404, "{}")

        def do_POST(self):
            if not self._host_ok() or not self._autorizado():
                return self._resp(403, "{}")
            try:
                corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except ValueError:
                return self._resp(400, "{}")
            r = {"ok": True, "msg": ""}
            if self.path == "/fechar":
                r["ok"], r["msg"] = mon.fechar(str(corpo.get("chave")), bool(corpo.get("forcar")))
            elif self.path == "/config":
                with mon.trinco:
                    cfg = mon.cfg
                    if "auto" in corpo:
                        cfg["auto"] = bool(corpo["auto"])
                    if "marcar" in corpo:
                        ch, sim = str(corpo["marcar"]), bool(corpo.get("valor"))
                        if sim and ch not in cfg["auto_lista"] and not protegido(ch):
                            cfg["auto_lista"].append(ch)
                        elif not sim and ch in cfg["auto_lista"]:
                            cfg["auto_lista"].remove(ch)
                    for k, lo, hi in (("limiar_pressao", 1, 80), ("ocioso_min", 0, 240), ("ram_minima_pct", 2, 50)):
                        if k in corpo:
                            cfg[k] = max(lo, min(hi, int(corpo[k])))
                    if "segundo_plano" in corpo:
                        cfg["segundo_plano"] = bool(corpo["segundo_plano"])
                        definir_autostart(cfg["segundo_plano"])
                    guardar_config(cfg)
            else:
                return self._resp(404, "{}")
            self._resp(200, json.dumps(r))

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pedido)
    srv.daemon_threads = True
    return srv


def instancia_existente():
    dados = ler(F_INSTANCIA)
    if not dados:
        return None
    try:
        info = json.loads(dados)
        os.kill(info["pid"], 0)
        with socket.create_connection(("127.0.0.1", info["porta"]), timeout=1):
            return info
    except (ValueError, KeyError, OSError):
        return None


def abrir_janela(url):
    for nav in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave-browser",
                "brave", "microsoft-edge", "vivaldi"):
        if shutil.which(nav):
            subprocess.Popen([nav, f"--app={url}", "--window-size=1100,820"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return
    webbrowser.open(url)


def estado_terminal():
    mon = Monitor()
    mon.amostrar_processos()
    time.sleep(1.5)
    mon.amostrar_memoria()
    mon.amostrar_processos()
    m = mon.mem
    print(f"RAM:  {fmt(m['usada'])} de {fmt(m['total'])} usados ({fmt(m['disponivel'])} disponíveis)")
    if m["swap_total"]:
        print(f"Swap: {fmt(m['swap_usada'])} de {fmt(m['swap_total'])}{'  (zram)' if m['zram'] else ''}")
    if m["pressao"]["disponivel"]:
        print(f"Pressão de memória: {m['pressao']['some10']:.1f}% (últimos 10 s)")
    print(f"\n{'APP':32} {'MEMÓRIA':>10} {'NA SWAP':>10} {'PROC':>5}")
    for a in mon.instantaneo()["apps"][:15]:
        print(f"{a['nome'][:32]:32} {fmt(a['mem']):>10} {fmt(a['swap']):>10} {a['n']:>5}")


def main():
    ap = argparse.ArgumentParser(description="Limpador RAM - monitor de memória em tempo real")
    ap.add_argument("--fundo", action="store_true", help="correr em segundo plano, sem abrir janela")
    ap.add_argument("--estado", action="store_true", help="mostrar um resumo no terminal e sair")
    ap.add_argument("--version", action="version", version=f"Limpador RAM {VERSAO}")
    args = ap.parse_args()
    if not sys.platform.startswith("linux"):
        sys.exit("O Limpador RAM, por agora, só funciona no Linux.")
    if args.estado:
        return estado_terminal()

    info = instancia_existente()
    if info:
        if not args.fundo:
            abrir_janela(f"http://127.0.0.1:{info['porta']}/#{info['token']}")
        return

    mon = Monitor()
    token = secrets.token_urlsafe(24)
    srv = criar_servidor(mon, token, args.fundo)
    porta = srv.server_address[1]
    os.makedirs(DIR_CACHE, exist_ok=True)
    with open(F_INSTANCIA, "w") as f:
        json.dump({"pid": EU, "porta": porta, "token": token}, f)
    os.chmod(F_INSTANCIA, 0o600)
    threading.Thread(target=mon.laco, daemon=True).start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{porta}/#{token}"
    if not args.fundo:
        abrir_janela(url)
        print(f"Limpador RAM aberto em {url}")
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    try:
        while True:
            time.sleep(5)
            # Sem janela aberta há 60 s e sem modo de segundo plano: sair.
            if not args.fundo and not mon.cfg.get("segundo_plano") and time.monotonic() - mon.ultimo_pedido > 60:
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if json.loads(ler(F_INSTANCIA) or "{}").get("pid") == EU:
                os.remove(F_INSTANCIA)
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------- interface (HTML)
HTML = r"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Limpador RAM</title>
<style>
:root{--fundo:#16181d;--cartao:#1f232a;--linha:#2c313a;--texto:#e8eaed;--suave:#9aa3ae;--ram:#e5484d;--swap:#30a46c;--pressao:#f5a524;--azul:#3e8eed;--ok:#30a46c}
@media (prefers-color-scheme: light){:root{--fundo:#f4f5f7;--cartao:#fff;--linha:#e3e6ea;--texto:#1b1d21;--suave:#5f6873}}
*{box-sizing:border-box}body{margin:0;background:var(--fundo);color:var(--texto);font:14px/1.45 system-ui,"Segoe UI",Roboto,Ubuntu,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:18px;margin:0 0 12px;display:flex;align-items:center;gap:10px}h1 small{color:var(--suave);font-weight:400;font-size:13px}
.cartao{background:var(--cartao);border:1px solid var(--linha);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.estado{display:flex;gap:12px;align-items:center;font-size:15px}.estado b{font-size:16px}
.bola{width:14px;height:14px;border-radius:50%;flex:none}
.numeros{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px}
.num .r{color:var(--suave);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.num .v{font-size:20px;font-weight:600}
.num .s{color:var(--suave);font-size:12px}
.barra{height:6px;background:var(--linha);border-radius:3px;margin-top:6px;overflow:hidden}.barra i{display:block;height:100%}
canvas{width:100%;height:150px;display:block}
.legenda{display:flex;gap:16px;color:var(--suave);font-size:12px;margin-top:6px}.legenda span:before{content:"";display:inline-block;width:10px;height:3px;margin-right:6px;vertical-align:middle;background:var(--c)}
.dica{border-left:3px solid var(--pressao)}.dica code{background:var(--linha);padding:2px 5px;border-radius:4px;font-size:12px}
.dica pre{background:var(--linha);padding:10px;border-radius:8px;overflow-x:auto;font-size:12px;margin:8px 0 0}
.auto{display:flex;flex-wrap:wrap;gap:12px 24px;align-items:center}
.inter{display:flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.inter input{appearance:none;width:38px;height:22px;background:var(--linha);border-radius:11px;position:relative;cursor:pointer;margin:0;transition:.15s}
.inter input:after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;transition:.15s}
.inter input:checked{background:var(--azul)}.inter input:checked:after{left:19px}
.aj{color:var(--suave);font-size:13px}.aj input{width:52px;background:var(--fundo);color:var(--texto);border:1px solid var(--linha);border-radius:6px;padding:3px 5px}
table{width:100%;border-collapse:collapse}th{text-align:left;color:var(--suave);font-weight:500;font-size:12px;padding:6px 8px;border-bottom:1px solid var(--linha)}
td{padding:7px 8px;border-bottom:1px solid var(--linha);vertical-align:middle}tr:last-child td{border-bottom:0}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th.n{text-align:right}
.app{font-weight:500}.app small{display:block;color:var(--suave);font-weight:400;font-size:12px}
.memb{height:4px;background:var(--azul);border-radius:2px;margin-top:4px;opacity:.7}
button{background:var(--linha);color:var(--texto);border:0;border-radius:7px;padding:6px 12px;cursor:pointer;font:inherit;font-size:13px}
button:hover{filter:brightness(1.2)}button.perigo{background:#c4373c;color:#fff}button:disabled{opacity:.4;cursor:default}
.tag{font-size:11px;padding:2px 7px;border-radius:9px;background:var(--linha);color:var(--suave);white-space:nowrap}
.chk{width:16px;height:16px;cursor:pointer}
.acoes div{padding:4px 0;color:var(--suave);font-size:13px}.acoes b{color:var(--texto);font-weight:500}
#aviso{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:#333a45;color:#fff;padding:10px 16px;border-radius:9px;display:none;max-width:90%}
@media (max-width:640px){.esc{display:none}}
</style></head><body><main>
<h1>Limpador RAM <small id="ver"></small></h1>

<div class="cartao">
  <div class="estado"><div class="bola" id="bola"></div><div><b id="titulo">A analisar…</b><div id="explica" class="aj"></div></div></div>
  <div class="numeros">
    <div class="num"><div class="r">Memória RAM</div><div class="v" id="ram">–</div><div class="s" id="rams"></div><div class="barra"><i id="ramb" style="background:var(--ram)"></i></div></div>
    <div class="num"><div class="r">Swap (RAM no disco)</div><div class="v" id="swap">–</div><div class="s" id="swaps"></div><div class="barra"><i id="swapb" style="background:var(--swap)"></i></div></div>
    <div class="num"><div class="r">Pressão de memória</div><div class="v" id="pre">–</div><div class="s">tempo perdido à espera de RAM</div><div class="barra"><i id="preb" style="background:var(--pressao)"></i></div></div>
  </div>
</div>

<div class="cartao"><canvas id="graf"></canvas>
  <div class="legenda"><span style="--c:var(--ram)">RAM %</span><span style="--c:var(--swap)">Swap %</span><span style="--c:var(--pressao)">Pressão %</span><span style="margin-left:auto">últimos 2 minutos</span></div>
</div>

<div class="cartao dica" id="dica" style="display:none"></div>

<div class="cartao">
  <div class="auto">
    <label class="inter"><input type="checkbox" id="auto"><b>Fechar automaticamente quando a memória acabar</b></label>
    <label class="inter"><input type="checkbox" id="fundo"><span>Vigiar sempre (arranca com o computador)</span></label>
  </div>
  <div class="aj" style="margin-top:10px">Só fecha as apps marcadas na coluna <b>Auto</b>, as maiores primeiro, e só se estiverem paradas há pelo menos
    <input type="number" id="ocioso" min="0" max="240"> min. Entra em ação quando a pressão passa de <input type="number" id="limiar" min="1" max="80"> %.
    Programas do sistema nunca são fechados.</div>
</div>

<div class="cartao">
  <table><thead><tr><th>Aplicação</th><th class="n">Memória</th><th class="n esc">Na swap</th><th class="n esc">CPU</th><th class="esc">Parada há</th><th title="Pode ser fechada pelo modo automático">Auto</th><th></th></tr></thead>
  <tbody id="tab"></tbody></table>
</div>

<div class="cartao acoes"><b>Últimas ações</b><div id="acoes"><div>Nenhuma ainda.</div></div></div>
</main><div id="aviso"></div>
<script>
const TOKEN=location.hash.slice(1);
const $=id=>document.getElementById(id);
const fmt=b=>{const u=["B","KB","MB","GB","TB"];let i=0;while(Math.abs(b)>=1024&&i<4){b/=1024;i++}return (i<3?b.toFixed(0):b.toFixed(1))+" "+u[i]};
const tempo=s=>s<60?"agora":s<3600?Math.floor(s/60)+" min":Math.floor(s/3600)+" h "+Math.floor(s%3600/60)+" min";
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let ultimo=null,editando=false;
async function post(rota,corpo){const r=await fetch(rota,{method:"POST",headers:{"X-Token":TOKEN,"Content-Type":"application/json"},body:JSON.stringify(corpo)});return r.json()}
function aviso(t){const a=$("aviso");a.textContent=t;a.style.display="block";clearTimeout(a._t);a._t=setTimeout(()=>a.style.display="none",4000)}
function cor(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}
function grafico(h){const c=$("graf"),d=devicePixelRatio||1,W=c.clientWidth,H=c.clientHeight;c.width=W*d;c.height=H*d;const g=c.getContext("2d");g.scale(d,d);g.clearRect(0,0,W,H);
 g.strokeStyle=cor("--linha");g.lineWidth=1;for(const p of[0,50,100]){const y=4+(H-8)*(1-p/100);g.beginPath();g.moveTo(0,y);g.lineTo(W,y);g.stroke()}
 const N=120;for(const[k,v]of[["pressao","--pressao"],["swap","--swap"],["ram","--ram"]]){g.strokeStyle=cor(v);g.lineWidth=2;g.beginPath();
  h.forEach((p,i)=>{const x=W*(i+N-h.length)/(N-1),y=4+(H-8)*(1-Math.min(p[k],100)/100);i?g.lineTo(x,y):g.moveTo(x,y)});g.stroke()}}
function estado(d){const m=d.mem,p=m.pressao,disp=m.disponivel/m.total*100,sw=m.swap_total?m.swap_usada/m.swap_total*100:0;
 let c="--ok",t="Memória folgada",e="Tens RAM suficiente para o que está aberto. RAM ocupada com cache é normal e acelera o computador.";
 if(p.some10>=10||d.precisa_aliviar){c="--ram";t="Falta RAM: o computador está a ficar lento";e="O sistema está a perder tempo a mover memória para o disco. Fecha apps que não estás a usar."}
 else if(p.some10>=2||disp<15||sw>85){c="--pressao";t="Memória apertada";e=sw>85?"A swap está quase cheia: a RAM não chega para tudo o que tens aberto. Fechar uma app grande ajuda.":"Ainda está a dar, mas fechar uma app grande que não uses dá folga."}
 $("bola").style.background=cor(c);$("titulo").textContent=t;$("explica").textContent=e;
 $("ram").textContent=fmt(m.usada)+" de "+fmt(m.total);$("rams").textContent=fmt(m.disponivel)+" disponíveis · cache "+fmt(m.cache);$("ramb").style.width=(m.usada/m.total*100)+"%";
 $("swap").textContent=m.swap_total?fmt(m.swap_usada)+" de "+fmt(m.swap_total):"sem swap";$("swaps").textContent=!m.swap_total?"":m.zram?"zram ativo (comprimida na RAM)":"no disco (lenta)";$("swapb").style.width=sw+"%";
 $("pre").textContent=p.disponivel?p.some10.toFixed(1)+" %":"n/d";$("preb").style.width=Math.min(p.some10*2,100)+"%";
 const dica=$("dica");if(!m.zram&&(sw>60||m.total<12*2**30)){dica.style.display="";dica.innerHTML=`<b>Dica que faz mesmo diferença: ativar o zram.</b><div class="aj">Em vez de mandar memória para o disco (lento), o Linux comprime-a dentro da própria RAM. Em computadores com ${fmt(m.total)} nota-se bastante. Ubuntu, Debian e Mint (pede a palavra-passe, só se faz uma vez):</div><pre>sudo apt install systemd-zram-generator
printf '[zram0]\\nzram-size = ram / 2\\ncompression-algorithm = zstd\\n' | sudo tee /etc/systemd/zram-generator.conf
sudo systemctl daemon-reload && sudo systemctl start systemd-zram-setup@zram0.service</pre><div class="aj" style="margin-top:6px">O Fedora já o traz ativo. Depois disto este aviso desaparece.</div>`}else dica.style.display="none"}
function tabela(d){const max=Math.max(...d.apps.map(a=>a.mem+a.swap),1);
 $("tab").innerHTML=d.apps.filter(a=>a.mem+a.swap>5*2**20).map(a=>`<tr>
 <td class="app">${esc(a.nome)}${a.nome!==a.chave?`<small>${esc(a.chave)}</small>`:""}${a.protegido?' <span class="tag">sistema</span>':""}<div class="memb" style="width:${(a.mem+a.swap)/max*100}%"></div></td>
 <td class="n">${fmt(a.mem+a.swap)}${a.n>1?`<div class="aj" style="font-size:11px">${a.n} processos</div>`:""}</td>
 <td class="n esc">${a.swap>1<<20?fmt(a.swap):"–"}</td><td class="n esc">${a.cpu.toFixed(0)} %</td><td class="esc aj">${tempo(a.parada_s)}</td>
 <td>${a.protegido?"":`<input type="checkbox" class="chk" data-auto="${esc(a.chave)}" ${a.auto?"checked":""}>`}</td>
 <td style="text-align:right">${a.protegido?"":a.a_fechar?`<button class="perigo" data-forcar="${esc(a.chave)}">Forçar</button>`:`<button data-fechar="${esc(a.chave)}">Fechar</button>`}</td></tr>`).join("")}
function acoes(d){$("acoes").innerHTML=d.acoes.length?d.acoes.map(a=>`<div><b>${a.t}</b> ${esc(a.msg)}</div>`).join(""):"<div>Nenhuma ainda.</div>"}
async function atualizar(){try{const r=await fetch("/dados",{headers:{"X-Token":TOKEN}});if(!r.ok)throw 0;const d=await r.json();ultimo=d;
 $("ver").textContent="v"+d.versao;estado(d);grafico(d.historico);tabela(d);acoes(d);
 if(!editando){$("auto").checked=d.cfg.auto;$("fundo").checked=d.cfg.segundo_plano;$("ocioso").value=d.cfg.ocioso_min;$("limiar").value=d.cfg.limiar_pressao}}
 catch(e){$("titulo").textContent="Sem ligação ao Limpador RAM";$("explica").textContent="Fecha esta janela e volta a abrir o Limpador RAM."}}
document.addEventListener("click",async e=>{const f=e.target.dataset.fechar,F=e.target.dataset.forcar;
 if(f){const a=ultimo.apps.find(x=>x.chave===f);if(!confirm(`Fechar ${a.nome}?\n\nSe tiver trabalho por gravar, grava primeiro. Navegadores normalmente recuperam os separadores.`))return;const r=await post("/fechar",{chave:f});aviso(r.msg);atualizar()}
 if(F){const a=ultimo.apps.find(x=>x.chave===F);if(!confirm(`${a.nome} não fechou. Forçar o fecho?\n\nO que não estiver gravado perde-se.`))return;const r=await post("/fechar",{chave:F,forcar:true});aviso(r.msg);atualizar()}});
document.addEventListener("change",async e=>{const t=e.target;
 if(t.dataset.auto){await post("/config",{marcar:t.dataset.auto,valor:t.checked})}
 else if(t.id==="auto"){await post("/config",{auto:t.checked});aviso(t.checked?"Modo automático ligado.":"Modo automático desligado.")}
 else if(t.id==="fundo"){await post("/config",{segundo_plano:t.checked});aviso(t.checked?"O Limpador RAM vai vigiar a memória mesmo com esta janela fechada, e arranca com o computador.":"Deixa de correr em segundo plano.")}
 else if(t.id==="ocioso"||t.id==="limiar"){await post("/config",{ocioso_min:$("ocioso").value,limiar_pressao:$("limiar").value})}
 editando=false;atualizar()});
document.addEventListener("focusin",e=>{if(e.target.type==="number")editando=true});
atualizar();setInterval(atualizar,1000);addEventListener("resize",()=>ultimo&&grafico(ultimo.historico));
</script></body></html>"""

if __name__ == "__main__":
    main()
