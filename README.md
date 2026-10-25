# Limpador

**Liberta espaço no disco com segurança.** Para macOS, Windows e Linux. Um só programa em Python, sem dependências.

*English summary at the bottom.*

## O que faz

Analisa o computador, mostra o que ocupa espaço e **explica cada coisa em linguagem simples**. Só apaga depois de confirmares.

| Grupo | O que significa | Exemplos |
|---|---|---|
| 🟢 **Seguras** | Voltam a ser criadas sozinhas. Não perdes nada. | Caches das apps e dos navegadores, ficheiros temporários, Lixo/Reciclagem, cache do npm/pip/Yarn, cache do Windows Update, registos do sistema |
| 🟡 **Tu decides** | Apagas agora e só recuperas/reinstalas se precisares. A escolha é tua. | Ficheiros grandes, instaladores antigos, `node_modules` de projetos parados, emuladores Android, versões do iOS do Xcode, Docker, hibernação, apps instaladas |
| 🔵 **Só para ver** | Não apaga nada. | Relatório com as pastas maiores |

Também mostra o espaço livre antes e depois, e quanto ganhaste.

## Segurança

- **Nada é apagado sem confirmação.** Mostra a lista e o espaço a libertar antes de cada passo.
- **Ficheiros pessoais** (grandes, instaladores) vão para o **Lixo/Reciclagem**, onde ainda os podes recuperar.
- **Nunca toca** em `.ssh`, `.gnupg`, chaves, e-mail, Fotos e iCloud (macOS), e recusa apagar pastas inteiras como a tua pasta pessoal, Documentos ou Library.
- **Lista própria de proteção:** cria o ficheiro `~/.limpador_protegidos.txt` e escreve lá, uma por linha, as pastas que o Limpador nunca deve tocar (por exemplo `~/.gemini`).
- **Modo simulação:** `--simular` mostra tudo o que faria, sem apagar nada. **Recomendado na primeira vez.**
- **Registo:** tudo o que é apagado fica em `~/.limpador/registo.txt`.

## Como instalar

Descarrega o instalador do teu sistema (separador *Releases* do projeto) e dá duplo clique:

| Sistema | Ficheiro | O que acontece |
|---|---|---|
| **macOS** | `Limpador.pkg` (ou `Limpador.dmg` / `Limpador-mac.zip`) | O assistente instala o **Limpador** em Aplicações. Abre-o pelo Launchpad ou pelo Finder. Precisa do Python 3 (se faltar, a app oferece-se para o instalar). |
| **Windows** | `Limpador-Setup.exe` | O assistente instala, cria atalho no menu Iniciar (e, se quiseres, no Ambiente de Trabalho) e abre o programa no fim. |
| **Linux (Ubuntu, Debian, Mint)** | `limpador_1.0_amd64.deb` | Duplo clique abre a loja de aplicações; ou `sudo apt install ./limpador_1.0_amd64.deb`. Aparece **Limpador** no menu. |

Depois de instalado, é só clicar no ícone **Limpador**: abre uma janela de terminal com o menu.

### Avisos na primeira abertura (os programas não estão assinados)
- **macOS:** se o instalador for bloqueado, clique direito > **Abrir**. Na primeira execução, aceita o pedido para controlar o Terminal. Recomendado: dá **Acesso Total ao Disco** ao Terminal (Definições do Sistema > Privacidade e Segurança) para os tamanhos virem completos.
- **Windows:** se o SmartScreen avisar, **Mais informações > Executar mesmo assim**. Para ver também as opções do sistema (cache do Windows Update, hibernação, DISM): clique direito no Limpador > **Executar como administrador**.
- **Linux:** algumas limpezas (cache de pacotes, journal) pedem a palavra-passe.

### A partir do código (qualquer sistema, Python 3.8+)
```bash
python3 limpador.py            # normal
python3 limpador.py --simular  # só mostrar, não apagar
python3 limpador.py --lang en  # inglês
```

## Compilar o executável e o ícone

```bash
pip install pyinstaller pillow numpy
python make_icons.py            # cria icons/ (png, ico, icns, svg)
bash build/build_mac.sh         # macOS  -> dist/Limpador.app, .dmg e .pkg (instalador)
bash build/build_mac_python.sh  # macOS sem PyInstaller -> .zip, .dmg e .pkg (corre num Mac ou no Linux, ver o início do script)
build\build_windows.bat         # Windows -> dist\Limpador.exe (o instalador Setup.exe usa o Inno Setup: iscc installer\windows\Limpador.iss)
bash build/build_linux.sh && bash build/build_deb.sh   # Linux -> .tar.gz e .deb (instalador)
```
Cada sistema tem de ser compilado no próprio sistema. O ficheiro `.github/workflows/build.yml` compila os três instaladores automaticamente no GitHub quando crias uma etiqueta `v1.0` e publica-os na página *Releases*, prontos para descarregar. É a forma mais simples de os obteres sem teres os três sistemas.

## Limitações

- Os tamanhos são estimativas; alguns valores sobrepõem-se, por isso o ganho real pode ser um pouco menor.
- No Windows e no Linux, a lista de apps instaladas é só para consulta: o Limpador não desinstala programas nesses sistemas.
- Alguns ficheiros em uso ou protegidos pelo sistema ficam por apagar. É normal.
- Os executáveis não estão assinados. Para distribuição ampla, considera uma assinatura (Apple Developer ID, certificado de código no Windows).

## Aviso

Usa por tua conta e risco. O Limpador foi desenhado para ser conservador, mas apagar ficheiros é irreversível, exceto o que vai para o Lixo/Reciclagem. Faz cópias do que é importante.

---

## English summary

**Limpador** frees up disk space safely on macOS, Windows and Linux. It scans your computer, explains each item in plain language, and deletes only after you confirm.

- 🟢 **Safe:** recreated automatically (caches, temp files, trash, package caches).
- 🟡 **You decide:** large files, old installers, project `node_modules`, emulators, Docker, hibernation, installed apps.
- 🔵 **View only:** a report of the biggest folders.

Personal files go to the Trash/Recycle Bin. `~/.ssh`, `~/.gnupg`, keys, mail and anything in `~/.limpador_protegidos.txt` are never touched. Use `--dry-run` first. Language follows your system; press `l` to switch. Everything deleted is logged to `~/.limpador/registo.txt`.

## Licença / License

MIT. Ver `LICENSE`.

## Limpador RAM (Linux)

Monitor de memória em tempo real, instalado junto com o Limpador (menu: **Limpador RAM**, ou `limpador-ram` no terminal).

- Mostra a RAM, a swap e a **pressão de memória**, o indicador que diz se o computador está mesmo lento por falta de RAM.
- Agrupa os processos por aplicação (por exemplo, todos os processos do Chrome numa linha) e deixa fechar o que não precisas.
- **Modo automático (opcional):** quando a memória aperta, fecha sozinho as apps marcadas na coluna *Auto*, as maiores primeiro e só se estiverem paradas há algum tempo. Nunca toca em programas do sistema, do ambiente de trabalho ou de outros utilizadores. Cada ação fica registada em `~/.limpador/ram-registo.txt`.
- **Vigiar sempre:** continua a trabalhar com a janela fechada e arranca com o computador.
- `limpador-ram --estado` mostra um resumo rápido no terminal.

Não há botão de "libertar RAM": a cache do Linux acelera o computador e esvaziá-la à força deixa-o mais lento.
