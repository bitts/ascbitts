# Amigos Share Watcher

Cliente Python de terminal para a realizaçao monitorada de buscas na comunidade Amigos Share Club - Basicamente baixar torrents e enviar notificações disso.

## Requisitos

- Python 3.8 ou superior.
- `requests` e `beautifulsoup4`.
- Acesso à rede e credenciais válidas do site.
- Para Gmail: autenticação de dois fatores e uma **Senha de app** do Google, quando disponível para a conta.

## Instalação

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
cp watchlist.example.json watchlist.json
python main.py
```

Edite `config.json` ou utilize o menu do script para setar os dados. Não compartilhe `config.json`: ele contém credenciais. O programa tenta restringir suas permissões para o proprietário no sistema POSIX.

## Gmail / SMTP

Configuração recomendada:

```json
"email": {
  "enabled": true,
  "provider": "gmail",
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "username": "seuendereco@gmail.com",
  "password": "SENHA_DE_APP",
  "from": "seuendereco@gmail.com",
  "to": "destinatario@exemplo.com",
  "security": "starttls",
  "starttls": true,
  "timeout_seconds": 30
}
```

Alternativa SSL direto: `smtp_port: 465` e `security: "ssl"`.
- Porta 587: SMTP + STARTTLS.
- Porta 465: SMTP_SSL desde o início.
- Use o endereço Gmail completo no campo `username`.
- Use uma Senha de app do Google, não a senha normal da conta.
- Não publique nem envie o arquivo com a senha real.

Teste somente o e-mail, sem abrir o menu:

```bash
python main.py --test-email
```

Diagnósticos SMTP:
- `ASW-MAIL-000`: teste concluído com sucesso.
- `ASW-MAIL-001`: conexão SMTP fechada/indisponível. Confira DNS, internet, firewall, host, porta e modo SSL/STARTTLS.
- `ASW-MAIL-002`: autenticação recusada. Confira o usuário e a Senha de app.
- `ASW-MAIL-003`: falha no protocolo SMTP, remetente, destinatário ou política do provedor.
- `ASW-MAIL-005`: e-mail habilitado sem host ou destinatário.
- `ASW-MAIL-006`: tentativa de teste com e-mail desabilitado.

## Limpeza da interface

A opção **14** do menu alterna a limpeza automática da tela antes de redesenhar o menu. A preferência fica gravada em `config.json`, em `ui.clear_screen`. Em execução sem terminal interativo, a tela não é limpa.

## Execução por terminal

```bash
# Menu interativo
python main.py

# Monitoramento contínuo sem menu (processo em primeiro plano)
python main.py --daemon

# Uma rodada e encerra
python main.py --once

# Testa login e busca no site
python main.py --test

# Testa somente o e-mail
python main.py --test-email

# Sobrescreve parâmetros apenas nesta execução
python main.py --daemon --interval-seconds 600 --request-delay 5 \\
  --download-dir "$HOME/Downloads/torrents" --no-telegram

# Logs em caminho alternativo e nível detalhado
python main.py --daemon --log-file "$HOME/.local/state/amigos-watcher/watcher.log" --log-level DEBUG
```

`--daemon` não cria um processo destacado por conta própria: ele permanece em primeiro plano, comportamento recomendado para `systemd`, supervisores e serviços do sistema, que cuidam de reinício e encerramento. Para uma execução manual destacada, pode-se usar `nohup`, embora um serviço seja preferível.

## Inicialização automática com systemd (Linux)

Instale o projeto em um caminho permanente, por exemplo `/opt/amigos-share-watcher`, crie o ambiente virtual e configure `config.json`. Crie `/etc/systemd/system/amigos-share-watcher.service` (ajuste usuário e caminhos):

```ini
[Unit]
Description=Amigos Share Watcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=SEU_USUARIO
WorkingDirectory=/opt/amigos-share-watcher
ExecStart=/opt/amigos-share-watcher/.venv/bin/python /opt/amigos-share-watcher/main.py --daemon
Restart=on-failure
RestartSec=15
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Ative e confira:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now amigos-share-watcher
sudo systemctl status amigos-share-watcher
journalctl -u amigos-share-watcher -f
```

O programa também grava logs rotativos em `watcher.log` (2 MiB por arquivo, cinco cópias). Para parar:

```bash
sudo systemctl stop amigos-share-watcher
```

Não execute simultaneamente o serviço e uma segunda instância manual, para evitar consultas duplicadas.

## Opções CLI

| Opção | Finalidade |
|---|---|
| `--daemon` / `--run` | Monitoramento contínuo sem menu |
| `--once` | Uma rodada de monitoramento |
| `--test` | Teste de login e pesquisa |
| `--test-email` | Teste exclusivo do SMTP |
| `--log-file CAMINHO` | Define o arquivo de log |
| `--log-level NIVEL` | DEBUG, INFO, WARNING, ERROR ou CRITICAL |
| `--interval-seconds N` | Intervalo mínimo global (mínimo 60) |
| `--request-delay N` | Pausa entre consultas |
| `--download-dir CAMINHO` | Pasta de downloads nesta execução |
| `--no-email` | Desativa e-mail nesta execução |
| `--no-telegram` | Desativa Telegram nesta execução |
| `--clear-screen` | Força limpeza de tela nesta execução |
| `--no-clear-screen` | Desativa limpeza nesta execução |

## Códigos de auditoria

| Código | Significado |
|---|---|
| `ASW-FATAL-001` | Erro não tratado na inicialização ou execução principal |
| `ASW-SYS-000` | Processo de monitoramento iniciado |
| `ASW-SYS-001` | Sinal de encerramento recebido |
| `ASW-SYS-002` | Falha fatal no monitoramento |
| `ASW-SYS-003` | Falha ao remover arquivo PID |
| `ASW-SYS-004` | Interrupção pelo usuário |
| `ASW-WATCH-001` | Falha isolada em um item; ciclo continua |
| `ASW-WATCH-002` | Falha no ciclo geral |
| `ASW-RUN-000` | Execução pontual concluída |
| `ASW-RUN-001` | Falha em item na execução pontual |
| `ASW-SITE-000` | Login e pesquisa de teste concluídos |
| `ASW-NOTIFY-001` | Falha no teste de notificações |
| `ASW-TG-001` | Telegram habilitado sem token/chat_id |
| `ASW-TG-002` | Falha de comunicação com Telegram |
| `ASW-MAIL-000` | Teste SMTP concluído |
| `ASW-MAIL-001` | Conexão SMTP encerrada/indisponível |
| `ASW-MAIL-002` | Autenticação SMTP recusada |
| `ASW-MAIL-003` | Erro do protocolo SMTP |
| `ASW-MAIL-005` | Configuração SMTP incompleta |
| `ASW-MAIL-006` | Teste solicitado com e-mail desabilitado |

Os logs não registram intencionalmente senhas nem tokens. Ainda assim, mantenha os arquivos de log sob acesso restrito e revise qualquer log antes de compartilhá-lo.

## Limitações e observações

- O programa depende da estrutura atual do site e de suas respostas; mudanças no site podem exigir adaptação.
- O monitoramento em `--daemon` roda em primeiro plano e deve ser supervisionado pelo gerenciador de serviços.
- Teste inicialmente com uma watchlist pequena e intervalos respeitosos.
