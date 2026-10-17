#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIMPADOR / CLEANER  -  liberta espaço no disco com segurança
                       free up disk space safely

macOS, Windows e Linux. Só usa a biblioteca padrão do Python.
macOS, Windows and Linux. Python standard library only.

Como funciona / How it works
  1. Analisa o computador e mostra o que ocupa espaço.
  2. Separa em: SEGURAS (voltam a ser criadas), TU DECIDES, SÓ PARA VER.
  3. Explica o que cada coisa é e só apaga depois de confirmares.

Opções / Options
  --simular, --dry-run   mostra o que faria, sem apagar nada / show only, delete nothing
  --lang pt|en           idioma / language
"""
import argparse
import glob
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings("ignore")

APP = "Limpador"
VERSAO = "1.0"
J = os.path.join
HOME = os.path.expanduser("~")

_REAL = "mac" if sys.platform == "darwin" else ("win" if sys.platform.startswith("win") else "linux")
SO = os.environ.get("LIMPADOR_SO", _REAL)  # LIMPADOR_SO existe só para testes
DRY = False
LANG = "pt"


def _(pt, en):
    return pt if LANG == "pt" else en


def detetar_idioma():
    try:
        if _REAL == "mac":
            r = subprocess.run(["defaults", "read", "-g", "AppleLocale"],
                               capture_output=True, text=True, timeout=5)
            if r.stdout.strip():
                return "pt" if r.stdout.strip().lower().startswith("pt") else "en"
        elif _REAL == "win":
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "pt" if (lid & 0xFF) == 0x16 else "en"
        for v in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
            x = os.environ.get(v, "")
            if x:
                return "pt" if x.lower().startswith("pt") else "en"
    except Exception:
        pass
    return "en"


# ----------------------------------------------------------------------------
# Terminal: cores e símbolos
# ----------------------------------------------------------------------------
def _preparar_terminal():
    ansi = True
    if _REAL == "win":
        ansi = False
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            modo = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(modo)):
                ansi = bool(k.SetConsoleMode(h, modo.value | 0x0004))
        except Exception:
            ansi = False
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return ansi


COR = sys.stdout.isatty() and _preparar_terminal()
UNI = (_REAL != "win") or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))


def _c(txt, cod):
    return "\033[%sm%s\033[0m" % (cod, txt) if COR else txt


def negrito(t): return _c(t, "1")
def verde(t): return _c(t, "32")
def amarelo(t): return _c(t, "33")
def vermelho(t): return _c(t, "31")
def azul(t): return _c(t, "36")
def cinza(t): return _c(t, "90")


def sim_ok(): return "✔" if UNI else "OK"
def sim_aviso(): return "⚠" if UNI else "!"
def sim_erro(): return "✖" if UNI else "X"
def sim_ponto(): return "•" if UNI else "-"
def sim_cadeado(): return "🔒" if UNI else "[#]"
def sim_disco(): return "💾 " if UNI else ""


# ----------------------------------------------------------------------------
# Pastas por sistema operativo
# ----------------------------------------------------------------------------
if SO == "win":
    LOCAL = os.environ.get("LOCALAPPDATA") or J(HOME, "AppData", "Local")
    ROAM = os.environ.get("APPDATA") or J(HOME, "AppData", "Roaming")
    TEMP = os.environ.get("TEMP") or J(LOCAL, "Temp")
    WINDIR = os.environ.get("SystemRoot") or r"C:\Windows"
    DRIVE = os.environ.get("SystemDrive") or "C:"
    PROGDATA = os.environ.get("ProgramData") or r"C:\ProgramData"
else:
    LOCAL = ROAM = TEMP = WINDIR = DRIVE = PROGDATA = ""


def N(p):
    return os.path.normcase(os.path.normpath(p))


def dentro(p, base):
    p, base = N(p), N(base)
    return p == base or p.startswith(base.rstrip(os.sep) + os.sep)


def pastas_utilizador():
    nomes = ("Documents", "Desktop", "Downloads", "Pictures", "Music", "Movies", "Videos")
    return [J(HOME, n) for n in nomes]


def _intocaveis():
    s = {HOME, os.path.dirname(HOME), J(HOME, ".cache"), J(HOME, ".local"),
         J(HOME, ".local", "share"), J(HOME, ".local", "share", "Trash"),
         J(HOME, ".config"), J(HOME, ".Trash")}
    s |= set(pastas_utilizador())
    if SO == "mac":
        s |= {"/", "/Users", "/System", "/Library", "/usr", "/usr/local", "/Applications",
              "/private", "/opt", "/bin", "/sbin", "/etc", "/var", "/Volumes",
              J(HOME, "Library"), J(HOME, "Library", "Application Support"),
              J(HOME, "Library", "Caches"), J(HOME, "Library", "Logs")}
    elif SO == "win":
        s |= {DRIVE + "\\", WINDIR, J(WINDIR, "System32"), DRIVE + "\\Users",
              DRIVE + "\\Program Files", DRIVE + "\\Program Files (x86)", PROGDATA,
              LOCAL, ROAM, TEMP, J(HOME, "AppData"), J(WINDIR, "Temp")}
    else:
        s |= {"/", "/home", "/usr", "/etc", "/var", "/bin", "/sbin", "/boot", "/opt",
              "/root", "/lib", "/lib64", "/var/cache", "/var/log", "/var/lib", "/tmp"}
    return {N(x) for x in s if x}


INTOCAVEIS = _intocaveis()

FICHEIRO_PROTEGIDOS = J(HOME, ".limpador_protegidos.txt")


def _protegidos():
    base = [".ssh", ".gnupg"]
    if SO == "mac":
        base += [J("Library", x) for x in ("Keychains", "Mail", "Messages", "Mobile Documents", "Photos")]
    if SO == "linux":
        base += [J(".local", "share", "keyrings"), ".mozilla", ".thunderbird"]
    lista = [J(HOME, x) for x in base]
    try:
        with open(FICHEIRO_PROTEGIDOS, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha and not linha.startswith("#"):
                    lista.append(os.path.expanduser(linha))
    except Exception:
        pass
    return lista


PROTEGIDOS = _protegidos()


def _sistema_permitido():
    if SO == "mac":
        return ["/Library/Developer/CoreSimulator/Caches", "/Applications"]
    if SO == "win":
        return [J(WINDIR, "SoftwareDistribution", "Download"), J(WINDIR, "Temp")]
    return []


SISTEMA_PERMITIDO = _sistema_permitido()


def pode_apagar(p):
    if not os.path.isabs(p):
        return False
    p = os.path.normpath(p)
    if N(p) in INTOCAVEIS:
        return False
    for pr in PROTEGIDOS:
        if dentro(p, pr) or dentro(pr, p):
            return False
    if dentro(p, HOME):
        return True
    return any(dentro(p, s) for s in SISTEMA_PERMITIDO)


# ----------------------------------------------------------------------------
# Utilitários
# ----------------------------------------------------------------------------
def existe(p):
    return os.path.lexists(p)


def _kb_py(path):
    try:
        if os.path.isfile(path) or os.path.islink(path):
            return os.lstat(path).st_size // 1024
    except OSError:
        return 0
    total = 0
    pilha = [path]
    while pilha:
        d = pilha.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            pilha.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total // 1024


def kb(path):
    """Tamanho em KB."""
    if not existe(path):
        return 0
    if _REAL != "win" and shutil.which("du"):
        try:
            r = subprocess.run(["du", "-sk", path], capture_output=True, text=True, timeout=1800)
            linhas = r.stdout.strip().splitlines()
            if linhas:
                return int(linhas[-1].split()[0])
        except Exception:
            pass
    return _kb_py(path)


def kb_multi(paths):
    return sum(kb(p) for p in paths)


def humano(k):
    if k is None:
        return _("variável", "varies")
    if k >= 1048576:
        return "%.1f GB" % (k / 1048576.0)
    if k >= 1024:
        return "%.0f MB" % (k / 1024.0)
    return "%d KB" % k


def paralelo(func, itens, workers=8):
    itens = list(itens)
    if not itens:
        return []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(func, itens))


def disco():
    t, u, l = shutil.disk_usage(HOME)
    return t, u, l


def gb(b):
    return "%.1f GB" % (b / 1073741824.0)


def run(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        class R(object):
            returncode = 1
            stdout = ""
            stderr = str(e)
        return R()


def confirmar(msg):
    try:
        r = input("%s (%s): " % (msg, _("s/n", "y/n"))).strip().lower()
    except EOFError:
        return False
    return r in ("s", "sim", "y", "yes")


def eh_admin():
    try:
        if SO == "win":
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


_sudo_ok = False


def garantir_sudo():
    global _sudo_ok
    if SO == "win":
        return eh_admin()
    if eh_admin() or _sudo_ok:
        return True
    print(cinza("    " + _("(Preciso da palavra-passe do teu utilizador. Ao escrever não aparece nada, é normal.)",
                          "(Your password is needed. Nothing shows while you type, that is normal.)")))
    r = subprocess.run(["sudo", "-v"])
    _sudo_ok = (r.returncode == 0)
    return _sudo_ok


def registo(msg):
    try:
        d = J(HOME, ".limpador")
        os.makedirs(d, exist_ok=True)
        with open(J(d, "registo.txt"), "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def correr(cmd, sudo=False, silencioso=False):
    """Corre um comando (respeita o modo simulação)."""
    if sudo and SO != "win" and not eh_admin():
        if not DRY and not garantir_sudo():
            return False
        cmd = ["sudo"] + cmd
    if DRY:
        print(cinza("    " + _("(simulação) ", "(simulation) ") + " ".join(cmd)))
        return True
    registo("CMD " + " ".join(cmd))
    try:
        if silencioso:
            return subprocess.run(cmd, capture_output=True).returncode == 0
        return subprocess.run(cmd).returncode == 0
    except Exception as e:
        print(vermelho("    %s" % e))
        return False


# ----------------------------------------------------------------------------
# Apagar
# ----------------------------------------------------------------------------
def _rmtree_forte(p):
    def erro(func, path, exc):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except Exception:
            pass
    shutil.rmtree(p, onerror=erro)


def apagar(p):
    p = os.path.normpath(p)
    if not pode_apagar(p):
        print(vermelho("    %s %s: %s" % (sim_erro(), _("Recusado por segurança", "Refused for safety"), p)))
        return False
    if not existe(p):
        return True
    if DRY:
        print(cinza("    " + _("(simulação) apagaria ", "(simulation) would delete ") + p))
        return True
    registo("DEL " + p)
    if dentro(p, HOME) or SO == "win":
        try:
            if os.path.islink(p) or os.path.isfile(p):
                try:
                    os.remove(p)
                except PermissionError:
                    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                    os.remove(p)
            else:
                _rmtree_forte(p)
        except Exception:
            pass
        if existe(p) and SO != "win":
            subprocess.run(["rm", "-rf", p], capture_output=True)
        return not existe(p)
    if not garantir_sudo():
        return False
    subprocess.run(["sudo", "rm", "-rf", p], capture_output=True)
    return not existe(p)


def apagar_varios(paths):
    ok = True
    for p in paths:
        if existe(p):
            ok = apagar(p) and ok
    return ok


def apagar_conteudo(d):
    """Apaga o que está dentro da pasta, mantendo a pasta."""
    if os.path.isfile(d):
        return apagar(d)
    if not os.path.isdir(d):
        return True
    falhas = 0
    try:
        nomes = os.listdir(d)
    except OSError:
        return False
    for nome in nomes:
        if not apagar(J(d, nome)):
            falhas += 1
    if falhas:
        print(amarelo("    %s %s" % (sim_aviso(), _("%d item(ns) estavam em uso ou protegidos e ficaram." % falhas,
                                                    "%d item(s) were in use or protected and were kept." % falhas))))
    return True


# --- Lixo / Reciclagem -------------------------------------------------------
def _lixo_linux():
    return J(HOME, ".local", "share", "Trash")


def lixo_kb():
    if SO == "mac":
        return kb(J(HOME, ".Trash"))
    if SO == "win":
        try:
            import ctypes
            from ctypes import wintypes

            class SHQUERYRBINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong),
                            ("i64NumItems", ctypes.c_longlong)]
            info = SHQUERYRBINFO()
            info.cbSize = ctypes.sizeof(info)
            ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            return int(info.i64Size // 1024)
        except Exception:
            return 0
    return kb(J(_lixo_linux(), "files"))


def esvaziar_lixo():
    if DRY:
        print(cinza("    " + _("(simulação) esvaziaria o Lixo", "(simulation) would empty the Trash")))
        return True
    registo("EMPTY TRASH")
    if SO == "mac":
        if shutil.which("osascript"):
            r = run(["osascript", "-e", 'tell application "Finder" to empty trash'], timeout=300)
            if r.returncode == 0:
                return True
        return apagar_conteudo(J(HOME, ".Trash"))
    if SO == "win":
        try:
            import ctypes
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
            return True
        except Exception:
            return False
    ok = True
    for sub in ("files", "info", "expunged"):
        ok = apagar_conteudo(J(_lixo_linux(), sub)) and ok
    return ok


def _lixo_manual_linux(p):
    try:
        if os.stat(p).st_dev != os.stat(HOME).st_dev:
            return False
        base = _lixo_linux()
        os.makedirs(J(base, "files"), exist_ok=True)
        os.makedirs(J(base, "info"), exist_ok=True)
        nome = os.path.basename(p)
        dest, i = J(base, "files", nome), 1
        while existe(dest):
            i += 1
            dest = J(base, "files", "%s.%d" % (nome, i))
        from urllib.parse import quote
        with open(J(base, "info", os.path.basename(dest) + ".trashinfo"), "w", encoding="utf-8") as f:
            f.write("[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (quote(p), time.strftime("%Y-%m-%dT%H:%M:%S")))
        shutil.move(p, dest)
        return True
    except Exception:
        return False


def mover_para_lixo(p):
    """Envia para o Lixo/Reciclagem (recuperável). True se conseguiu."""
    if not pode_apagar(p):
        print(vermelho("    %s %s: %s" % (sim_erro(), _("Recusado por segurança", "Refused for safety"), p)))
        return False
    if DRY:
        print(cinza("    " + _("(simulação) moveria para o Lixo ", "(simulation) would move to Trash ") + p))
        return True
    registo("TRASH " + p)
    try:
        if SO == "mac":
            if shutil.which("osascript"):
                seguro = p.replace("\\", "\\\\").replace('"', '\\"')
                r = run(["osascript", "-e", 'tell application "Finder" to delete POSIX file "%s"' % seguro])
                return r.returncode == 0
            return False
        if SO == "win":
            q = p.replace("'", "''")
            fn = "DeleteDirectory" if os.path.isdir(p) else "DeleteFile"
            ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
                  "[Microsoft.VisualBasic.FileIO.FileSystem]::%s('%s','OnlyErrorDialogs','SendToRecycleBin')" % (fn, q))
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
            return r.returncode == 0
        if shutil.which("gio"):
            r = run(["gio", "trash", p])
            if r.returncode == 0:
                return True
        return _lixo_manual_linux(p)
    except Exception:
        return False


def oferecer_esvaziar_lixo():
    if confirmar("\n  " + _("O espaço só é libertado quando o Lixo for esvaziado. Esvaziar o Lixo agora?",
                           "Space is only freed when the Trash is emptied. Empty the Trash now?")):
        esvaziar_lixo()
        print(verde("  %s %s" % (sim_ok(), _("Lixo esvaziado.", "Trash emptied."))))


# ----------------------------------------------------------------------------
# Seleção e submenus
# ----------------------------------------------------------------------------
def ler_selecao(txt, n, atalhos=None, permitir_todos=True):
    sel = set()
    for tok in re.split(r"[,\s]+", txt.strip().lower()):
        if not tok:
            continue
        if tok in ("t", "todos", "todas", "a", "all") and permitir_todos:
            sel |= set(range(n))
        elif atalhos and tok in atalhos:
            sel |= set(atalhos[tok])
        elif re.fullmatch(r"\d+-\d+", tok):
            a, b = [int(x) for x in tok.split("-")]
            if not (1 <= a <= b <= n):
                return None
            sel |= set(range(a - 1, b))
        elif tok.isdigit() and 1 <= int(tok) <= n:
            sel.add(int(tok) - 1)
        else:
            return None
    return sorted(sel)


def submenu(titulo, intro, itens, atalhos_desc=None, atalhos_fn=None, depois=None,
            apenas_ver=False, rodape=None):
    """itens: lista de dicts {label, tam, acao, nota}"""
    itens = list(itens)
    while itens:
        print("\n" + negrito("== " + titulo + " =="))
        for linha in intro:
            print("  " + linha)
        print()
        for i, it in enumerate(itens, 1):
            nota = ("  " + cinza(it["nota"])) if it.get("nota") else ""
            print("  %2d) %-56s %9s%s" % (i, it["label"][:56], humano(it["tam"]), nota))
        if apenas_ver:
            if rodape:
                rodape()
            else:
                input(_("\n  Prima Enter para voltar...", "\n  Press Enter to go back..."))
            return
        dica = _("  Escreve os números (ex: 1 3 4 ou 2-5), 't' = todos",
                 "  Type the numbers (e.g. 1 3 4 or 2-5), 'a' = all")
        if atalhos_desc:
            dica += ", " + atalhos_desc
        dica += _(". Enter = voltar.", ". Enter = go back.")
        print("\n" + dica)
        try:
            r = input("  > ").strip().lower()
        except EOFError:
            return
        if not r:
            return
        atalhos = {}
        if atalhos_fn:
            for k, f in atalhos_fn.items():
                atalhos[k] = {i for i, it in enumerate(itens) if f(it)}
        sel = ler_selecao(r, len(itens), atalhos)
        if sel is None:
            print(amarelo("  " + _("Não percebi. Usa números separados por espaço (ex: 1 3).",
                                  "I did not understand. Use numbers separated by spaces (e.g. 1 3).")))
            continue
        if not sel:
            print(amarelo("  " + _("Nada selecionado.", "Nothing selected.")))
            continue
        escolhidos = [itens[i] for i in sel]
        total = sum((x["tam"] or 0) for x in escolhidos)
        print("\n  " + _("Vais apagar:", "You are about to delete:"))
        for x in escolhidos:
            print("   %s %s (%s)" % (sim_ponto(), x["label"], humano(x["tam"])))
        if not confirmar("  " + _("Confirmas? Liberta cerca de %s" % humano(total),
                                  "Confirm? Frees about %s" % humano(total))):
            print("  " + _("Cancelado, nada foi apagado.", "Cancelled, nothing was deleted."))
            continue
        for x in escolhidos:
            print("  > %s ..." % x["label"])
            ok = x["acao"]()
            print(verde("    %s %s" % (sim_ok(), _("Feito", "Done"))) if ok
                  else amarelo("    %s %s" % (sim_aviso(), _("Não consegui apagar tudo", "Could not delete everything"))))
        itens = [x for x in itens if x not in escolhidos]
        if depois:
            depois()


def mk(titulo, desc, risco, tam, acao=None, sub=None, info=None, admin=False):
    if tam is not None and tam < 1024:
        return None  # esconde o que já está (quase) vazio
    return {"titulo": titulo, "desc": desc, "risco": risco, "tam": tam,
            "acao": acao, "sub": sub, "info": info, "admin": admin}


def item_pastas(titulo, desc, risco, paths, conteudo=True, admin=False):
    vistos, lista = set(), []
    for p in paths:
        if existe(p) and N(p) not in vistos:
            vistos.add(N(p))
            lista.append(p)
    if not lista:
        return None
    tam = kb_multi(lista)

    def acao():
        ok = True
        for p in lista:
            ok = (apagar_conteudo(p) if conteudo else apagar(p)) and ok
        return ok
    return mk(titulo, desc, risco, tam, acao=acao, admin=admin)


# ----------------------------------------------------------------------------
# SEGURAS - todos os sistemas
# ----------------------------------------------------------------------------
def item_temporarios():
    if SO == "mac":
        return item_pastas(_("Caches das apps", "App caches"),
                           _("Ficheiros temporários que as apps guardam para abrir mais depressa. Voltam a ser criados sozinhos.",
                             "Temporary files apps keep to open faster. They are recreated automatically."),
                           "seguro", [J(HOME, "Library", "Caches")])
    if SO == "win":
        return item_pastas(_("Ficheiros temporários", "Temporary files"),
                           _("Temporários do Windows e das apps, relatórios de erros. Os que estiverem em uso ficam.",
                             "Temporary files from Windows and apps, error reports. Files in use are kept."),
                           "seguro", [TEMP, J(LOCAL, "Temp"), J(LOCAL, "CrashDumps"),
                                      J(LOCAL, "Microsoft", "Windows", "WER")])
    return item_pastas(_("Cache das apps (~/.cache)", "App cache (~/.cache)"),
                       _("Ficheiros temporários das apps. Voltam a ser criados sozinhos.",
                         "Temporary files kept by apps. They are recreated automatically."),
                       "seguro", [J(HOME, ".cache")])


def item_logs():
    if SO != "mac":
        return None
    return item_pastas(_("Registos (logs)", "Logs"),
                       _("Histórico técnico das apps. Podes apagar sem perder nada.",
                         "Technical history written by apps. Safe to delete."),
                       "seguro", [J(HOME, "Library", "Logs")])


def item_miniaturas():
    if SO != "win":
        return None
    fs = glob.glob(J(LOCAL, "Microsoft", "Windows", "Explorer", "thumbcache_*.db")) + \
        glob.glob(J(LOCAL, "Microsoft", "Windows", "Explorer", "iconcache_*.db"))
    return item_pastas(_("Miniaturas e ícones em cache", "Thumbnail and icon cache"),
                       _("O Windows volta a criar as miniaturas quando abrires as pastas.",
                         "Windows recreates thumbnails when you open folders."),
                       "seguro", fs)


def item_lixo():
    t = lixo_kb()
    nome = _("Reciclagem", "Recycle Bin") if SO == "win" else _("Lixo", "Trash")
    return mk(nome, _("Ficheiros que já eliminaste mas que ainda ocupam espaço.",
                      "Files you already deleted that still take up space."),
              "seguro", t, acao=esvaziar_lixo)


def _browsers():
    """[(nome, [pastas de cache existentes])]"""
    extras = ("Cache", "Code Cache", "GPUCache", J("Service Worker", "CacheStorage"))
    if SO == "mac":
        sup = J(HOME, "Library", "Application Support")
        cch = J(HOME, "Library", "Caches")
        chrom = {"Google Chrome": [J(sup, "Google", "Chrome"), J(cch, "Google", "Chrome")],
                 "Microsoft Edge": [J(sup, "Microsoft Edge"), J(cch, "Microsoft Edge")],
                 "Brave": [J(sup, "BraveSoftware", "Brave-Browser"), J(cch, "BraveSoftware")],
                 "Vivaldi": [J(sup, "Vivaldi"), J(cch, "Vivaldi")],
                 "Chromium": [J(sup, "Chromium"), J(cch, "Chromium")]}
        ff = [J(cch, "Firefox", "Profiles")]
        extra_diretas = {"Safari": [J(cch, "com.apple.Safari")]}
    elif SO == "win":
        chrom = {"Google Chrome": [J(LOCAL, "Google", "Chrome", "User Data")],
                 "Microsoft Edge": [J(LOCAL, "Microsoft", "Edge", "User Data")],
                 "Brave": [J(LOCAL, "BraveSoftware", "Brave-Browser", "User Data")],
                 "Vivaldi": [J(LOCAL, "Vivaldi", "User Data")],
                 "Chromium": [J(LOCAL, "Chromium", "User Data")]}
        ff = [J(LOCAL, "Mozilla", "Firefox", "Profiles")]
        extra_diretas = {}
    else:
        cfg, cch = J(HOME, ".config"), J(HOME, ".cache")
        chrom = {"Google Chrome": [J(cfg, "google-chrome"), J(cch, "google-chrome")],
                 "Microsoft Edge": [J(cfg, "microsoft-edge"), J(cch, "microsoft-edge")],
                 "Brave": [J(cfg, "BraveSoftware", "Brave-Browser"), J(cch, "BraveSoftware")],
                 "Vivaldi": [J(cfg, "vivaldi"), J(cch, "vivaldi")],
                 "Chromium": [J(cfg, "chromium"), J(cch, "chromium")]}
        ff = [J(cch, "mozilla", "firefox")]
        extra_diretas = {}
    res = []
    for nome, bases in chrom.items():
        paths = []
        for b in bases:
            if not os.path.isdir(b):
                continue
            if os.path.basename(b) in ("Chrome", "google-chrome") and "Caches" in b or "/.cache/" in b.replace("\\", "/"):
                paths.append(b)
                continue
            try:
                for d in os.listdir(b):
                    if d == "Default" or d.startswith("Profile ") or d == "Guest Profile":
                        for e in extras:
                            paths.append(J(b, d, e))
            except OSError:
                pass
            if "Caches" in b:
                paths.append(b)
        paths = [p for p in paths if existe(p)]
        if paths:
            res.append((nome, paths))
    paths = []
    for base in ff:
        if os.path.isdir(base):
            paths += glob.glob(J(base, "*", "cache2"))
            if SO == "linux":
                paths += glob.glob(J(base, "*", "cache2"))
    paths = [p for p in dict.fromkeys(paths) if existe(p)]
    if paths:
        res.append(("Firefox", paths))
    for nome, ps in extra_diretas.items():
        ps = [p for p in ps if existe(p)]
        if ps:
            res.append((nome, ps))
    return res


def item_navegadores():
    bs = _browsers()
    if not bs:
        return None
    todos = []
    for _n, ps in bs:
        todos += ps
    todos = list(dict.fromkeys(todos))
    tam = kb_multi(todos)
    nomes = ", ".join(n for n, _ps in bs)

    def acao():
        ok = True
        for p in todos:
            ok = apagar_conteudo(p) and ok
        return ok
    return mk(_("Cache dos navegadores (%s)" % nomes, "Browser cache (%s)" % nomes),
              _("Páginas e imagens guardadas para carregar mais depressa. Não apaga palavras-passe, histórico nem sessões. Fecha os navegadores antes.",
                "Pages and images stored to load faster. Does not delete passwords, history or logins. Close your browsers first."),
              "seguro", tam, acao=acao)


# --- caches de programação (só aparecem se existirem) -------------------------
def item_npm():
    p = J(LOCAL, "npm-cache") if SO == "win" else J(HOME, ".npm", "_cacache")
    return item_pastas(_("Cache do npm", "npm cache"),
                       _("Pacotes JavaScript descarregados. Descarregam-se outra vez quando precisares.",
                         "Downloaded JavaScript packages. Downloaded again when needed."),
                       "seguro", [p], conteudo=False)


def item_yarn():
    p = {"mac": J(HOME, "Library", "Caches", "Yarn"), "win": J(LOCAL, "Yarn", "Cache"),
         "linux": J(HOME, ".cache", "yarn")}[SO]
    return item_pastas(_("Cache do Yarn", "Yarn cache"),
                       _("Pacotes descarregados pelo Yarn. Voltam a ser descarregados quando precisares.",
                         "Packages downloaded by Yarn. Downloaded again when needed."),
                       "seguro", [p], conteudo=False)


def item_pip():
    p = {"mac": J(HOME, "Library", "Caches", "pip"), "win": J(LOCAL, "pip", "Cache"),
         "linux": J(HOME, ".cache", "pip")}[SO]
    return item_pastas(_("Cache do pip (Python)", "pip cache (Python)"),
                       _("Pacotes Python descarregados. Voltam a ser descarregados quando precisares.",
                         "Downloaded Python packages. Downloaded again when needed."),
                       "seguro", [p], conteudo=False)


def item_pnpm():
    if not shutil.which("pnpm"):
        return None
    r = run(["pnpm", "store", "path"], timeout=30)
    caminho = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    t = kb(caminho) if caminho and os.path.isdir(caminho) else 0
    return mk(_("Cache do pnpm (limpeza inteligente)", "pnpm store (smart cleanup)"),
              _("Remove só pacotes que nenhum projeto usa. O ganho real é menor do que o tamanho mostrado.",
                "Removes only packages no project uses. Real gain is smaller than the size shown."),
              "seguro", t, acao=lambda: correr(["pnpm", "store", "prune"]))


def item_brew():
    if SO == "win" or not shutil.which("brew"):
        return None

    def acao():
        a = correr(["brew", "cleanup", "--prune=all"])
        correr(["brew", "autoremove"])
        return a
    return mk(_("Homebrew: versões antigas e downloads", "Homebrew: old versions and downloads"),
              _("Limpa versões antigas de programas instalados com o brew.",
                "Cleans old versions of programs installed with brew."),
              "seguro", None, acao=acao)


# --- Linux -------------------------------------------------------------------
def _gestor_pacotes():
    for g in ("apt-get", "dnf", "pacman"):
        if shutil.which(g):
            return g
    return None


def item_cache_pacotes():
    if SO != "linux":
        return None
    g = _gestor_pacotes()
    if g == "apt-get":
        t, cmd = kb("/var/cache/apt/archives"), ["apt-get", "clean"]
    elif g == "dnf":
        t, cmd = kb("/var/cache/dnf"), ["dnf", "clean", "all"]
    elif g == "pacman":
        t, cmd = kb("/var/cache/pacman/pkg"), ["pacman", "-Sc", "--noconfirm"]
    else:
        return None
    return mk(_("Cache do gestor de pacotes", "Package manager cache"),
              _("Instaladores já descarregados pelo sistema. Pede a palavra-passe.",
                "Installers the system already downloaded. Asks for your password."),
              "seguro", t, acao=lambda: correr(cmd, sudo=True))


def item_journal():
    if SO != "linux" or not shutil.which("journalctl"):
        return None
    r = run(["journalctl", "--disk-usage"], timeout=20)
    m = re.search(r"([\d.]+)\s*([KMGT])", r.stdout)
    if not m:
        return None
    t = int(float(m.group(1)) * {"K": 1, "M": 1024, "G": 1048576, "T": 1073741824}[m.group(2)])
    if t < 300 * 1024:
        return None
    return mk(_("Registos do sistema (journal)", "System logs (journal)"),
              _("Mantém só os 200 MB mais recentes. Pede a palavra-passe.",
                "Keeps only the most recent 200 MB. Asks for your password."),
              "seguro", t, acao=lambda: correr(["journalctl", "--vacuum-size=200M"], sudo=True))


def item_flatpak():
    if SO != "linux" or not shutil.which("flatpak"):
        return None
    r = run(["flatpak", "uninstall", "--unused", "--assumeno"], timeout=30)
    if "Nothing unused" in r.stdout or not r.stdout.strip():
        return None
    return mk(_("Flatpak: componentes sem uso", "Flatpak: unused components"),
              _("Runtimes que nenhuma app usa. Voltam a ser instalados se precisares.",
                "Runtimes no app uses. Reinstalled if needed."),
              "seguro", None, acao=lambda: correr(["flatpak", "uninstall", "--unused", "-y"]))


def item_snaps():
    if SO != "linux" or not shutil.which("snap"):
        return None
    r = run(["snap", "list", "--all"], timeout=30)
    velhos = []
    for l in r.stdout.splitlines()[1:]:
        c = l.split()
        if len(c) >= 6 and "disabled" in c[-1]:
            velhos.append((c[0], c[2]))
    if not velhos:
        return None
    t = sum(kb("/var/lib/snapd/snaps/%s_%s.snap" % v) for v in velhos)

    def acao():
        ok = True
        for nome, rev in velhos:
            ok = correr(["snap", "remove", nome, "--revision=%s" % rev], sudo=True) and ok
        return ok
    return mk(_("Snap: versões antigas (%d)" % len(velhos), "Snap: old versions (%d)" % len(velhos)),
              _("Versões antigas de apps Snap que o sistema guarda. Não afeta a versão em uso.",
                "Old versions of Snap apps the system keeps. Does not affect the version in use."),
              "seguro", t, acao=acao)


# --- Windows (precisam de administrador) --------------------------------------
def item_wu():
    if SO != "win":
        return None
    p = J(WINDIR, "SoftwareDistribution", "Download")

    def acao():
        correr(["net", "stop", "wuauserv"], silencioso=True)
        correr(["net", "stop", "bits"], silencioso=True)
        ok = apagar_conteudo(p)
        correr(["net", "start", "wuauserv"], silencioso=True)
        correr(["net", "start", "bits"], silencioso=True)
        return ok
    return mk(_("Cache do Windows Update", "Windows Update cache"),
              _("Ficheiros de atualizações já instaladas. O Windows descarrega outra vez o que precisar.",
                "Files of already-installed updates. Windows downloads again what it needs."),
              "seguro", kb(p) if os.path.isdir(p) else 0, acao=acao, admin=True)


def item_wintemp():
    if SO != "win":
        return None
    return item_pastas(_("Temporários do sistema (Windows\\Temp)", "System temp files (Windows\\Temp)"),
                       _("Temporários do próprio Windows. Os que estiverem em uso ficam.",
                         "Windows' own temporary files. Files in use are kept."),
                       "seguro", [J(WINDIR, "Temp")], admin=True)


def item_dism():
    if SO != "win":
        return None
    return mk(_("Limpeza de componentes do Windows (DISM)", "Windows component cleanup (DISM)"),
              _("Remove versões antigas de componentes do sistema. Demora alguns minutos. É a limpeza oficial da Microsoft.",
                "Removes old versions of system components. Takes a few minutes. This is Microsoft's official cleanup."),
              "seguro", None,
              acao=lambda: correr(["Dism.exe", "/online", "/Cleanup-Image", "/StartComponentCleanup"]), admin=True)


# ----------------------------------------------------------------------------
# SEGURAS - macOS (Xcode)
# ----------------------------------------------------------------------------
def item_derived():
    if SO != "mac":
        return None
    return item_pastas(_("Xcode: ficheiros de compilação", "Xcode: build files"),
                       _("Voltam a ser criados quando compilares uma app.", "Recreated when you build an app."),
                       "seguro", [J(HOME, "Library", "Developer", "Xcode", "DerivedData")])


def item_devsupport():
    if SO != "mac":
        return None
    b = J(HOME, "Library", "Developer", "Xcode")
    return item_pastas(_("Xcode: suporte de iPhones/iPads ligados", "Xcode: connected iPhone/iPad support"),
                       _("Símbolos de depuração. Voltam a ser descarregados ao ligares o dispositivo.",
                         "Debug symbols. Downloaded again when you connect the device."),
                       "seguro", [J(b, "iOS DeviceSupport"), J(b, "watchOS DeviceSupport"), J(b, "tvOS DeviceSupport")],
                       conteudo=False)


def item_simcaches():
    if SO != "mac":
        return None
    return item_pastas(_("Xcode: caches do simulador", "Xcode: simulator caches"),
                       _("Recriam-se quando abrires o simulador. Pede a palavra-passe.",
                         "Recreated when you open the simulator. Asks for your password."),
                       "seguro", ["/Library/Developer/CoreSimulator/Caches"])


# ----------------------------------------------------------------------------
# TU DECIDES
# ----------------------------------------------------------------------------
def item_snapshots():
    if SO != "mac" or not shutil.which("tmutil"):
        return None
    r = run(["tmutil", "listlocalsnapshots", "/"], timeout=30)
    datas = [m.group(1) for m in (re.search(r"TimeMachine\.([\d-]+)\.local", l) for l in r.stdout.splitlines()) if m]
    if not datas:
        return None

    def acao():
        ok = True
        for d in datas:
            ok = correr(["tmutil", "deletelocalsnapshots", d], sudo=True, silencioso=True) and ok
        return ok
    return mk(_("Cópias locais do Time Machine (%d)" % len(datas), "Local Time Machine snapshots (%d)" % len(datas)),
              _("Pontos de restauro guardados no próprio disco. Ficas sem esses pontos locais.",
                "Restore points kept on the disk itself. You lose those local restore points."),
              "decide", None, acao=acao)


def _runtimes_ios():
    if SO != "mac" or not shutil.which("xcrun"):
        return [], 0
    r = run(["xcrun", "simctl", "runtime", "list"], timeout=60)
    rts = []
    for l in r.stdout.splitlines():
        m = re.match(r"^\s*(.+?) \((\w+)\) - ([0-9A-Fa-f-]{36}) \((\w+)\)", l)
        if m and m.group(4).lower() != "deleting":
            rts.append({"nome": m.group(1), "build": m.group(2), "id": m.group(3), "estado": m.group(4)})
    total = 0
    m = re.search(r"Total Disk Images: \d+ \(([\d.]+)([KMGT])\)", r.stdout)
    if m:
        total = int(float(m.group(1)) * {"K": 1, "M": 1024, "G": 1048576, "T": 1073741824}[m.group(2)])
    return rts, total


def item_runtimes():
    rts, total = _runtimes_ios()
    if not rts:
        return None

    def sub():
        por = int(total / len(rts)) if total else None
        itens = []
        for rt in rts:
            itens.append({"label": "%s (%s)" % (rt["nome"], rt["build"]), "tam": por, "nota": rt["estado"],
                          "acao": (lambda rt=rt: correr(["xcrun", "simctl", "runtime", "delete", rt["id"]]))})
        submenu(_("Xcode: versões do iOS para o simulador", "Xcode: iOS versions for the simulator"),
                [_("Cada versão ocupa vários GB (valor estimado).", "Each version takes several GB (estimate)."),
                 _("Voltas a descarregá-la no Xcode > Settings > Components.",
                   "You can download it again in Xcode > Settings > Components."),
                 cinza(_("Dica: mantém só a mais recente.", "Tip: keep only the latest one."))], itens)
    return mk(_("Xcode: versões do iOS (%d)" % len(rts), "Xcode: iOS versions (%d)" % len(rts)),
              _("Cada versão do iOS usada no simulador ocupa vários GB. Reinstalas só quando precisares.",
                "Each iOS version used by the simulator takes several GB. Reinstall only if needed."),
              "decide", total or None, sub=sub)


def item_simdevices():
    d = J(HOME, "Library", "Developer", "CoreSimulator", "Devices")
    if SO != "mac" or not shutil.which("xcrun") or not os.path.isdir(d):
        return None

    def acao():
        correr(["xcrun", "simctl", "shutdown", "all"], silencioso=True)
        return correr(["xcrun", "simctl", "delete", "all"])
    return mk(_("Xcode: iPhones virtuais do simulador", "Xcode: simulator virtual devices"),
              _("Apaga os dispositivos simulados e as apps de teste dentro deles. Crias outros quando precisares.",
                "Deletes simulated devices and the test apps inside them. You can create new ones."),
              "decide", kb(d), acao=acao)


def item_archives():
    if SO != "mac":
        return None
    return item_pastas(_("Xcode: arquivos de apps compiladas", "Xcode: app archives"),
                       _("Versões antigas de apps que publicaste. Só apaga se não precisas delas.",
                         "Old builds of apps you published. Delete only if you do not need them."),
                       "decide", [J(HOME, "Library", "Developer", "Xcode", "Archives")])


def item_ios_backups():
    if SO != "mac":
        return None
    base = J(HOME, "Library", "Application Support", "MobileSync", "Backup")
    if not os.path.isdir(base):
        return None
    try:
        dirs = [J(base, d) for d in os.listdir(base) if os.path.isdir(J(base, d))]
    except OSError:
        return None
    if not dirs:
        return None
    tams = paralelo(kb, dirs)

    def sub():
        itens = []
        for p, t in zip(dirs, tams):
            nome, data = os.path.basename(p), ""
            try:
                with open(J(p, "Info.plist"), "rb") as f:
                    info = plistlib.load(f)
                nome = info.get("Device Name") or nome
                d = info.get("Last Backup Date")
                data = d.strftime("%d/%m/%Y") if d else ""
            except Exception:
                pass
            itens.append({"label": nome, "tam": t, "nota": data, "acao": (lambda p=p: apagar(p))})
        submenu(_("Cópias de segurança de iPhone/iPad", "iPhone/iPad backups"),
                [amarelo(_("Atenção: se for a única cópia do teu telemóvel, não apagues.",
                           "Warning: if this is the only backup of your phone, do not delete it."))], itens)
    return mk(_("Cópias de segurança de iPhone/iPad (%d)" % len(dirs), "iPhone/iPad backups (%d)" % len(dirs)),
              _("Cópias do telemóvel feitas no Mac. Pesadas, mas podem ser a tua única cópia.",
                "Phone backups made on this Mac. Heavy, but may be your only copy."),
              "decide", sum(tams), sub=sub)


def item_dev_caches():
    paths = [J(HOME, ".gradle", "caches"), J(HOME, ".m2", "repository"), J(HOME, ".cargo", "registry")]
    return item_pastas(_("Caches de programação (Gradle, Maven, Cargo)", "Developer caches (Gradle, Maven, Cargo)"),
                       _("Bibliotecas descarregadas. Voltam a ser descarregadas na próxima compilação (mais lenta).",
                         "Downloaded libraries. Downloaded again on the next build (slower)."),
                       "decide", paths, conteudo=False)


def item_android():
    sdk = {"mac": J(HOME, "Library", "Android", "sdk"), "win": J(LOCAL, "Android", "Sdk"),
           "linux": J(HOME, "Android", "Sdk")}[SO]
    cand = [(_("Imagens de emulador Android", "Android emulator images"), J(sdk, "system-images")),
            (_("Emulador Android", "Android emulator"), J(sdk, "emulator")),
            ("Android NDK", J(sdk, "ndk")),
            (_("Código-fonte do Android (sources)", "Android sources"), J(sdk, "sources")),
            ("CMake", J(sdk, "cmake")),
            (_("Dispositivos virtuais (AVDs)", "Virtual devices (AVDs)"), J(HOME, ".android", "avd"))]
    cand = [(n, p) for n, p in cand if os.path.isdir(p)]
    if not cand:
        return None
    tams = paralelo(lambda c: kb(c[1]), cand)
    if sum(tams) < 1024:
        return None

    def sub():
        itens = [{"label": n, "tam": t, "acao": (lambda p=p: apagar(p)),
                  "nota": _("reinstalas pelo Android Studio", "reinstall via Android Studio")}
                 for (n, p), t in zip(cand, tams) if t]
        submenu("Android", [_("Tudo isto se descarrega outra vez pelo Android Studio.",
                              "All of this can be downloaded again with Android Studio.")], itens)
    return mk(_("Android (emuladores e ferramentas)", "Android (emulators and tools)"),
              _("Ferramentas de desenvolvimento Android. Reinstalas só quando voltares a precisar.",
                "Android development tools. Reinstall only if you need them again."),
              "decide", sum(tams), sub=sub)


def item_docker():
    if not shutil.which("docker"):
        return None
    if run(["docker", "info"], timeout=15).returncode != 0:
        return None
    return mk(_("Docker: imagens e contentores sem uso", "Docker: unused images and containers"),
              _("Remove contentores parados, redes e imagens sem uso. Não apaga volumes (dados).",
                "Removes stopped containers, networks and dangling images. Does not delete volumes (data)."),
              "decide", None, acao=lambda: correr(["docker", "system", "prune", "-f"]))


def curto(p):
    return "~" + p[len(HOME):] if dentro(p, HOME) else p


def _achar_node_modules():
    nomes = ("Projects", "Projetos", "Documents", "Desktop", "Developer", "Dev", "Code", "code",
             "repos", "src", "work", "GitHub", "github", "Sites", "Source")
    achados = []
    for base in [J(HOME, n) for n in nomes if os.path.isdir(J(HOME, n))]:
        prof = base.count(os.sep)
        for atual, dirs, _f in os.walk(base, followlinks=False):
            if "node_modules" in dirs:
                achados.append(J(atual, "node_modules"))
                dirs.remove("node_modules")
            if atual.count(os.sep) - prof >= 6:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("Library", "AppData")]
    return sorted(set(achados))


def _atividade(proj):
    cands = [J(proj, x) for x in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
                                  ".git/index", ".git/HEAD")]
    ts = [os.path.getmtime(c) for c in cands if os.path.exists(c)]
    try:
        return max(ts) if ts else os.path.getmtime(proj)
    except Exception:
        return time.time()


def item_node_modules():
    achados = _achar_node_modules()
    if not achados:
        return None
    tams = paralelo(kb, achados)
    dados = []
    for p, t in zip(achados, tams):
        if t < 20 * 1024:
            continue
        dias = int((time.time() - _atividade(os.path.dirname(p))) / 86400)
        dados.append((p, t, dias))
    dados.sort(key=lambda x: -x[1])
    total = sum(d[1] for d in dados)
    if total < 1024:
        return None

    def sub():
        itens = [{"label": curto(os.path.dirname(p)), "tam": t, "acao": (lambda p=p: apagar(p)),
                  "nota": _("mexido há %d dias" % dias, "touched %d days ago" % dias), "parado": dias >= 60}
                 for p, t, dias in dados]
        submenu(_("Pastas node_modules dos projetos", "Project node_modules folders"),
                [_("Cada projeto JavaScript tem uma pasta node_modules com as bibliotecas que usa.",
                   "Each JavaScript project has a node_modules folder with its libraries."),
                 _("Apagar é seguro: voltas a criá-la com 'npm install'.", "Deleting is safe: recreate it with 'npm install'."),
                 cinza(_("Dica: 'p' escolhe os projetos parados há 60 dias ou mais.",
                         "Tip: 'p' picks projects untouched for 60+ days."))],
                itens, atalhos_desc=_("'p' = só projetos parados (60+ dias)", "'p' = only idle projects (60+ days)"),
                atalhos_fn={"p": lambda it: it.get("parado")})
    return mk(_("node_modules dos projetos (%d)" % len(dados), "Project node_modules (%d)" % len(dados)),
              _("Bibliotecas de cada projeto JavaScript. Recriam-se com 'npm install'.",
                "Libraries of each JavaScript project. Recreated with 'npm install'."),
              "decide", total, sub=sub)


def _achar_grandes(limite_mb=300):
    achados = []
    for base in pastas_utilizador():
        if not os.path.isdir(base):
            continue
        for atual, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "Library")
                       and not d.endswith((".app", ".photoslibrary", ".imovielibrary", ".fcpbundle", ".tvlibrary"))]
            for f in files:
                p = J(atual, f)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if st.st_size >= limite_mb * 1048576 and not os.path.islink(p):
                    achados.append((p, st.st_size // 1024, st.st_mtime))
    achados.sort(key=lambda x: -x[1])
    return achados[:30]


def _acao_para_lixo(p):
    def acao():
        if mover_para_lixo(p):
            return True
        print(amarelo("    " + _("Não consegui mover para o Lixo.", "Could not move to the Trash.")))
        if confirmar("    " + _("Apagar em definitivo?", "Delete permanently?")):
            return apagar(p)
        return False
    return acao


def item_grandes():
    achados = _achar_grandes()
    if not achados:
        return None

    def sub():
        itens = [{"label": curto(p), "tam": t, "acao": _acao_para_lixo(p),
                  "nota": time.strftime("%d/%m/%Y", time.localtime(mt))} for p, t, mt in achados]
        submenu(_("Ficheiros grandes (mais de 300 MB)", "Large files (over 300 MB)"),
                [_("Os teus ficheiros pessoais maiores. Só tu sabes o que ainda precisas.",
                   "Your biggest personal files. Only you know what you still need."),
                 _("Vão para o Lixo (dá para recuperar até esvaziares).", "They go to the Trash (recoverable until you empty it)."),
                 cinza(_("A data é a da última alteração.", "The date is the last modified date."))],
                itens, depois=oferecer_esvaziar_lixo)
    return mk(_("Ficheiros grandes (%d encontrados)" % len(achados), "Large files (%d found)" % len(achados)),
              _("Vídeos, instaladores e ficheiros pesados nas tuas pastas pessoais.",
                "Videos, installers and heavy files in your personal folders."),
              "decide", sum(a[1] for a in achados), sub=sub)


def item_instaladores():
    base = J(HOME, "Downloads")
    if not os.path.isdir(base):
        return None
    exts = (".dmg", ".pkg", ".exe", ".msi", ".msix", ".deb", ".rpm", ".iso", ".appimage")
    achados = []
    prof = base.count(os.sep)
    for atual, dirs, files in os.walk(base, followlinks=False):
        if atual.count(os.sep) - prof >= 2:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(exts):
                p = J(atual, f)
                try:
                    st = os.lstat(p)
                except OSError:
                    continue
                if st.st_size >= 5 * 1048576:
                    achados.append((p, st.st_size // 1024, st.st_mtime))
    achados.sort(key=lambda x: -x[1])
    achados = achados[:40]
    total = sum(a[1] for a in achados)
    if total < 1024:
        return None

    def sub():
        itens = [{"label": curto(p), "tam": t, "acao": _acao_para_lixo(p),
                  "nota": time.strftime("%d/%m/%Y", time.localtime(mt))} for p, t, mt in achados]
        submenu(_("Instaladores nas Transferências", "Installers in Downloads"),
                [_("Programas de instalação que normalmente já não precisas depois de instalar.",
                   "Setup files you usually no longer need once installed."),
                 _("Vão para o Lixo (dá para recuperar até esvaziares).", "They go to the Trash (recoverable until you empty it).")],
                itens, depois=oferecer_esvaziar_lixo)
    return mk(_("Instaladores antigos (%d)" % len(achados), "Old installers (%d)" % len(achados)),
              _("Ficheiros .dmg, .pkg, .exe, .msi, .deb... que ficaram nas Transferências.",
                "Setup files (.dmg, .pkg, .exe, .msi, .deb...) left in Downloads."),
              "decide", total, sub=sub)


# --- Apps instaladas ---------------------------------------------------------
def _listar_apps_mac():
    apps = []
    for base in ("/Applications", J(HOME, "Applications")):
        if not os.path.isdir(base):
            continue
        try:
            nomes = sorted(os.listdir(base))
        except OSError:
            continue
        for nome in nomes:
            p = J(base, nome)
            if nome.endswith(".app"):
                apps.append(p)
            elif os.path.isdir(p) and not nome.startswith("."):
                try:
                    apps += [J(p, n2) for n2 in os.listdir(p) if n2.endswith(".app")]
                except OSError:
                    pass
    return apps


def _medir_app_mac(app):
    nome = os.path.basename(app)[:-4]
    bid = None
    try:
        with open(J(app, "Contents", "Info.plist"), "rb") as f:
            bid = plistlib.load(f).get("CFBundleIdentifier")
    except Exception:
        pass
    lib = J(HOME, "Library")
    caches = [J(lib, "Caches", nome)]
    dados = [J(lib, "Application Support", nome)]
    if bid:
        caches += [J(lib, "Caches", bid), J(lib, "Containers", bid, "Data", "Library", "Caches")]
        dados += [J(lib, "Application Support", bid),
                  J(lib, "Containers", bid, "Data", "Library", "Application Support")]
    caches = [c for c in dict.fromkeys(caches) if os.path.exists(c)]
    dados = [d for d in dict.fromkeys(dados) if os.path.exists(d)]
    return {"nome": nome, "app": app, "kb_app": kb(app), "caches": caches, "dados": dados,
            "kb_cache": kb_multi(caches), "kb_dados": kb_multi(dados)}


def _apps_windows():
    import winreg
    chaves = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
              (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")]
    res = {}
    for hive, sub in chaves:
        try:
            k = winreg.OpenKey(hive, sub)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                nome = winreg.QueryValueEx(sk, "DisplayName")[0]
                try:
                    tam = int(winreg.QueryValueEx(sk, "EstimatedSize")[0])
                except OSError:
                    tam = 0
                res[nome] = max(tam, res.get(nome, 0))
            except OSError:
                pass
    return sorted(res.items(), key=lambda x: -x[1])


def _apps_linux():
    res = []
    if shutil.which("dpkg-query"):
        r = run(["dpkg-query", "-W", "-f", "${Installed-Size}\t${Package}\n"], timeout=60)
        for l in r.stdout.splitlines():
            try:
                t, n = l.split("\t")
                res.append((n, int(t)))
            except ValueError:
                pass
    elif shutil.which("rpm"):
        r = run(["rpm", "-qa", "--queryformat", "%{SIZE}\t%{NAME}\n"], timeout=60)
        for l in r.stdout.splitlines():
            try:
                t, n = l.split("\t")
                res.append((n, int(t) // 1024))
            except ValueError:
                pass
    return sorted(res, key=lambda x: -x[1])


def item_apps():
    if SO == "mac":
        apps = _listar_apps_mac()
        if not apps:
            return None
        infos = paralelo(_medir_app_mac, apps)
        for i in infos:
            i["total"] = i["kb_app"] + i["kb_cache"] + i["kb_dados"]
        infos = sorted([i for i in infos if i["total"] >= 50 * 1024], key=lambda i: -i["total"])[:40]
        if not infos:
            return None

        def sub():
            itens = []
            for i in infos:
                def acao(i=i):
                    ok = mover_para_lixo(i["app"])
                    if not ok:
                        print(amarelo("    " + _("Não consegui usar o Lixo; a apagar a app diretamente.",
                                                  "Could not use the Trash; deleting the app directly.")))
                        ok = apagar(i["app"])
                    for p in i["caches"] + i["dados"]:
                        apagar(p)
                    return ok
                nota = "app %s + cache %s + %s %s" % (humano(i["kb_app"]), humano(i["kb_cache"]),
                                                       _("dados", "data"), humano(i["kb_dados"]))
                itens.append({"label": i["nome"], "tam": i["total"], "acao": acao, "nota": nota})
            submenu(_("Apps instaladas (as 40 maiores)", "Installed apps (the 40 largest)"),
                    [_("Escolher uma app = desinstalar a app e apagar a cache e os dados dela.",
                       "Picking an app = uninstall it and delete its cache and data.")],
                    itens, depois=oferecer_esvaziar_lixo)
        return mk(_("Apps instaladas: ver e desinstalar", "Installed apps: view and uninstall"),
                  _("Lista as apps por tamanho (app + cache + dados) e deixa-te desinstalar as que já não usas.",
                    "Lists apps by size (app + cache + data) and lets you uninstall the ones you no longer use."),
                  "decide", sum(i["total"] for i in infos), sub=sub)
    # Windows / Linux: só listar
    try:
        lista = _apps_windows() if SO == "win" else _apps_linux()
    except Exception:
        lista = []
    lista = [(n, t) for n, t in lista if t >= 50 * 1024][:40]
    if not lista:
        return None

    def sub():
        itens = [{"label": n, "tam": t, "acao": None, "nota": ""} for n, t in lista]

        def rodape():
            if SO == "win":
                if confirmar("\n  " + _("Abrir 'Aplicações instaladas' do Windows para desinstalar?",
                                       "Open Windows 'Installed apps' to uninstall?")):
                    try:
                        os.startfile("ms-settings:appsfeatures")
                    except Exception:
                        pass
            else:
                print("\n  " + cinza(_("Para desinstalar: sudo apt remove <nome>  (ou a loja de aplicações).",
                                      "To uninstall: sudo apt remove <name>  (or your software center).")))
                input(_("  Prima Enter para voltar...", "  Press Enter to go back..."))
        submenu(_("Apps instaladas (as 40 maiores)", "Installed apps (the 40 largest)"),
                [_("Só para ver: o Limpador não desinstala programas neste sistema.",
                   "View only: Limpador does not uninstall programs on this system.")],
                itens, apenas_ver=True, rodape=rodape)
    return mk(_("Apps instaladas: ver as maiores", "Installed apps: see the largest"),
              _("Lista os programas por tamanho para decidires o que desinstalar nas definições do sistema.",
                "Lists programs by size so you can decide what to uninstall in system settings."),
              "decide", None, sub=sub)


# --- Windows: armazenamento e hibernação -------------------------------------
def item_storagesense():
    if SO != "win" or not os.path.isdir(DRIVE + "\\Windows.old"):
        return None

    def acao():
        try:
            os.startfile("ms-settings:storagesense")
            return True
        except Exception:
            return False
    return mk(_("Windows.old (versão anterior do Windows)", "Windows.old (previous Windows version)"),
              _("Abre o Armazenamento do Windows, onde ele próprio remove 'Instalações anteriores do Windows'.",
                "Opens Windows Storage settings where Windows itself removes 'Previous Windows installations'."),
              "decide", None, acao=acao)


def item_hibernacao():
    if SO != "win":
        return None
    p = DRIVE + "\\hiberfil.sys"
    try:
        t = os.stat(p).st_size // 1024
    except OSError:
        t = None
    return mk(_("Hibernação (hiberfil.sys)", "Hibernation (hiberfil.sys)"),
              _("Desliga a hibernação e liberta um ficheiro do tamanho da memória RAM. Perdes a hibernação e o arranque rápido.",
                "Turns hibernation off and frees a file the size of your RAM. You lose hibernation and fast startup."),
              "decide", t, acao=lambda: correr(["powercfg", "/hibernate", "off"]), admin=True)


# ----------------------------------------------------------------------------
# SÓ PARA VER
# ----------------------------------------------------------------------------
def relatorio():
    print("\n" + negrito("== " + _("Onde está o espaço?", "Where is the space?") + " =="))
    print(cinza("  " + _("(a medir, pode demorar 1 a 2 minutos...)", "(measuring, may take 1 to 2 minutes...)")))
    if SO == "mac":
        zonas = [(HOME, _("A tua pasta", "Your folder")), (J(HOME, "Library"), "Library"),
                 (J(HOME, "Library", "Application Support"), "Application Support"),
                 ("/Library", "/Library"), ("/usr/local", "/usr/local"), ("/opt", "/opt"),
                 ("/Applications", "/Applications")]
    elif SO == "win":
        zonas = [(HOME, _("A tua pasta", "Your folder")), (LOCAL, "AppData\\Local"), (ROAM, "AppData\\Roaming"),
                 (PROGDATA, "ProgramData"), (DRIVE + "\\Program Files", "Program Files"),
                 (DRIVE + "\\Program Files (x86)", "Program Files (x86)")]
    else:
        zonas = [(HOME, _("A tua pasta", "Your folder")), (J(HOME, ".cache"), "~/.cache"),
                 (J(HOME, ".local", "share"), "~/.local/share"), (J(HOME, ".config"), "~/.config"),
                 ("/var", "/var"), ("/opt", "/opt"), ("/usr", "/usr")]
    for base, nome in zonas:
        if not os.path.isdir(base):
            continue
        try:
            filhos = [J(base, x) for x in os.listdir(base)]
        except OSError:
            continue
        tams = paralelo(kb, filhos)
        top = sorted(zip(filhos, tams), key=lambda x: -x[1])[:8]
        print("\n  " + negrito(nome))
        for p, t in top:
            if t < 10 * 1024:
                continue
            marca = sim_cadeado() if any(dentro(p, x) or dentro(x, p) for x in PROTEGIDOS) else "  "
            print("   %s %-48s %9s" % (marca, os.path.basename(p)[:48], humano(t)))
    print("\n  " + cinza("%s = %s" % (sim_cadeado(), _("protegido: este programa nunca mexe nisto.",
                                                   "protected: this program never touches it."))))
    input("\n  " + _("Prima Enter para voltar ao menu...", "Press Enter to go back to the menu..."))


def item_relatorio():
    return {"titulo": _("Relatório: onde está o espaço?", "Report: where is the space?"),
            "desc": _("Mostra as pastas maiores. Só para ver, não apaga nada.",
                      "Shows the biggest folders. View only, deletes nothing."),
            "risco": "info", "tam": None, "acao": None, "sub": None, "info": relatorio, "admin": False}


# ----------------------------------------------------------------------------
# Menu principal
# ----------------------------------------------------------------------------
def construtores():
    return [item_temporarios, item_logs, item_miniaturas, item_lixo, item_navegadores,
            item_npm, item_yarn, item_pip, item_pnpm, item_brew,
            item_cache_pacotes, item_journal, item_flatpak, item_snaps,
            item_wu, item_wintemp, item_dism,
            item_derived, item_devsupport, item_simcaches,
            item_snapshots, item_runtimes, item_simdevices, item_archives, item_ios_backups,
            item_dev_caches, item_android, item_docker, item_node_modules,
            item_grandes, item_instaladores, item_apps, item_storagesense, item_hibernacao]


_ocultos_admin = 0


def analisar():
    global _ocultos_admin
    fs = construtores()
    print("\n  " + negrito(_("A analisar o teu computador...", "Scanning your computer...")) +
          cinza(_(" (pode demorar 1 a 3 minutos, não feches a janela)", " (may take 1 to 3 minutes, do not close the window)")))
    resultados = [None] * len(fs)
    feitos = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(f): i for i, f in enumerate(fs)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                resultados[i] = fut.result()
            except Exception:
                resultados[i] = None
            feitos += 1
            sys.stdout.write("\r  %s %d/%d   " % (_("Progresso:", "Progress:"), feitos, len(fs)))
            sys.stdout.flush()
    sys.stdout.write("\r" + " " * 40 + "\r")
    itens = [r for r in resultados if r]
    _ocultos_admin = 0
    if SO == "win" and not eh_admin():
        _ocultos_admin = len([i for i in itens if i.get("admin")])
        itens = [i for i in itens if not i.get("admin")]
    itens.append(item_relatorio())
    return itens


def grupos():
    return [("seguro", "🟢 " if UNI else "[+] ", _("SEGURAS", "SAFE"),
             _("voltam a ser criadas sozinhas, não perdes nada", "recreated automatically, you lose nothing")),
            ("decide", "🟡 " if UNI else "[?] ", _("TU DECIDES", "YOU DECIDE"),
             _("apagas agora e só reinstalas/recuperas se precisares", "delete now, restore or reinstall only if needed")),
            ("info", "🔵 " if UNI else "[i] ", _("SÓ PARA VER", "VIEW ONLY"),
             _("não apaga nada", "deletes nothing"))]


def cabecalho():
    linha = "=" * 46
    print("\n" + negrito(linha))
    print(negrito("   %s v%s" % (APP.upper(), VERSAO)))
    print(negrito(linha))
    print(cinza("  " + _("Nada é apagado sem eu te pedir confirmação.", "Nothing is deleted without asking you first.")))
    if DRY:
        print(amarelo("  " + _("MODO SIMULAÇÃO: nada será apagado.", "SIMULATION MODE: nothing will be deleted.")))


def mostrar_disco():
    t, u, l = disco()
    pct = int(round(u * 100.0 / t)) if t else 0
    cor = verde if pct < 75 else (amarelo if pct < 90 else vermelho)
    print("\n  %s%s: %s %s %s  (%s %s)" % (sim_disco(), _("Disco", "Disk"), negrito(gb(l)), _("livres de", "free of"),
                                          gb(t), cor("%d%%" % pct), _("usado", "used")))


def mostrar_menu(itens):
    mostrar_disco()
    lista = []
    for risco, icone, titulo, sub in grupos():
        grupo = [i for i in itens if i["risco"] == risco]
        if not grupo:
            continue
        print("\n  " + negrito(icone + titulo) + cinza(" - " + sub))
        for it in grupo:
            lista.append(it)
            tam = ("%9s" % humano(it["tam"])) if it["risco"] != "info" else "         "
            print("   %2d) %-46s %s" % (len(lista), it["titulo"][:46], tam))
            print("       " + cinza(it["desc"]))
    print("\n  %s %s" % (sim_cadeado(), cinza(_("Nunca toco em: ficheiros pessoais (a não ser que escolhas), chaves, e-mail e tudo o que puseres em %s." % FICHEIRO_PROTEGIDOS,
                                              "I never touch: personal files (unless you pick them), keys, email and anything you list in %s." % FICHEIRO_PROTEGIDOS))))
    if _ocultos_admin:
        print("  " + amarelo(_("%d opções precisam de administrador (cache do Windows Update, hibernação...). Abre o Limpador com clique direito > Executar como administrador." % _ocultos_admin,
                              "%d options need administrator rights (Windows Update cache, hibernation...). Open Limpador via right-click > Run as administrator." % _ocultos_admin)))
    seguras = [it for it in lista if it["risco"] == "seguro" and it.get("acao")]
    total_seguro = sum((it["tam"] or 0) for it in seguras)
    print("\n  " + negrito(_("O que queres fazer?", "What would you like to do?")))
    print("   %s %s (%s " % (sim_ponto(), _("Escreve os números que queres limpar", "Type the numbers you want to clean"), _("ex:", "e.g.")) + azul("1 3 5") + ")")
    print("   %s %s = %s (%s %s)" % (sim_ponto(), azul("s"), _("limpar todas as SEGURAS de uma vez", "clean ALL the SAFE items at once"),
                                    _("cerca de", "about"), humano(total_seguro)))
    print("   %s %s = %s    %s %s = %s" % (sim_ponto(), azul("l"), _("mudar idioma (English)", "switch language (Português)"),
                                         sim_ponto(), azul("q"), _("sair", "quit")))
    print(cinza("   " + _("(alguns valores sobrepõem-se, por isso o ganho real pode ser um pouco menor)",
                          "(some values overlap, so the real gain may be a little smaller)")))
    return lista, seguras


def executar_selecao(lista, sel):
    simples = [lista[i] for i in sel if lista[i].get("acao")]
    outros = [lista[i] for i in sel if not lista[i].get("acao")]
    if simples:
        total = sum((x["tam"] or 0) for x in simples)
        print("\n  " + _("Vais limpar:", "You are about to clean:"))
        for x in simples:
            print("   %s %s (%s)" % (sim_ponto(), x["titulo"], humano(x["tam"])))
        if confirmar("\n  " + _("Confirmas? Liberta até cerca de %s" % humano(total), "Confirm? Frees up to about %s" % humano(total))):
            _t, _u, antes = disco()
            for x in simples:
                print("\n  > %s ..." % x["titulo"])
                try:
                    ok = x["acao"]()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(vermelho("    %s %s: %s" % (sim_erro(), _("Erro", "Error"), e)))
                    ok = False
                print(verde("    %s %s" % (sim_ok(), _("Concluído", "Done"))) if ok
                      else amarelo("    %s %s" % (sim_aviso(), _("Concluído com avisos", "Done with warnings"))))
            _t, _u, depois = disco()
            print("\n  %s%s %s  (%s %s)" % (sim_disco(), _("Espaço livre agora:", "Free space now:"), negrito(gb(depois)),
                                         _("ganho:", "gained:"), gb(max(depois - antes, 0))))
            print(cinza("     " + _("O sistema pode demorar um minuto a atualizar este número.",
                                    "The system may take a minute to update this number.")))
        else:
            print("  " + _("Cancelado, nada foi apagado.", "Cancelled, nothing was deleted."))
    for x in outros:
        if x.get("sub"):
            x["sub"]()
        elif x.get("info"):
            x["info"]()


def main():
    global DRY, LANG
    ap = argparse.ArgumentParser(description="Limpador / Cleaner")
    ap.add_argument("--simular", "--dry-run", action="store_true", dest="dry")
    ap.add_argument("--lang", choices=("pt", "en"))
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args()
    if args.version:
        print("%s %s" % (APP, VERSAO))
        return
    DRY = args.dry
    LANG = args.lang or detetar_idioma()
    cabecalho()
    while True:
        itens = analisar()
        lista, seguras = mostrar_menu(itens)
        atalhos = {"s": {i for i, it in enumerate(lista) if it in seguras}}
        mudou_idioma = False
        while True:
            try:
                r = input("\n  > ").strip().lower()
            except EOFError:
                r = "q"
            if r in ("q", "sair", "quit", "exit", "0"):
                print("\n  " + _("Até à próxima! Corre o Limpador de 2 em 2 ou 3 em 3 meses.\n",
                                "See you next time! Run Limpador every 2 or 3 months.\n"))
                return
            if r in ("l", "lang"):
                LANG = "en" if LANG == "pt" else "pt"
                mudou_idioma = True
                break
            sel = ler_selecao(r, len(lista), atalhos, permitir_todos=False)
            if not sel:
                print(amarelo("  " + _("Não percebi. Escreve números (ex: 1 3), 's' ou 'q'.",
                                      "I did not understand. Type numbers (e.g. 1 3), 's' or 'q'.")))
                continue
            break
        if mudou_idioma:
            continue
        executar_selecao(lista, sel)
        print("\n  " + cinza(_("A voltar ao menu com os valores atualizados...", "Back to the menu with updated values...")))
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  " + _("Cancelado. Nada mais foi apagado.", "Cancelled. Nothing else was deleted.") + "\n")
    if (_REAL == "win" or getattr(sys, "frozen", False)) and sys.stdin and sys.stdin.isatty():
        try:
            input("  " + _("Prima Enter para fechar esta janela...", "Press Enter to close this window..."))
        except EOFError:
            pass
