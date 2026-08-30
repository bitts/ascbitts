
# Automador Amigos-Share Club (Termux / Node.js)

Sistema automatizado de busca, verificação e download de arquivos `.torrent` com suporte a agendamento, preservação do nome original dos arquivos, notificações por Telegram/E-mail e autoatualização via GitHub.

---

## 📋 Sobre o Projeto

O **Automador Amigos-Share** foi desenvolvido para rodar em segundo plano no **Termux (Android)** ou em servidores **Linux**. Ele realiza logins automáticos, pesquisa novos lançamentos de acordo com datas e horários configurados, verifica se o arquivo já foi baixado para evitar duplicidade e efetua o download direto na sua pasta de destino.

## 🚀 Principais Recursos
* **Preservação de Nome:** Baixa o arquivo `.torrent` mantendo acentuação, espaços e formato original.
* **Agendador Inteligente:** Define horários específicos, intervalos de busca e datas limite por termo.
* **Notificações:** Envia mensagens via Telegram e/ou E-mail (com layout HTML) a cada download finalizado.
* **Autoatualização (OTA):** Verifica no GitHub se há novas melhorias ou correções no script e se atualiza com a permissão do usuário.
* **Configuração Isolada:** Mantém suas credenciais e buscas em um arquivo `config.json` separado da lógica do código.

---

## 💻 Requisitos do Sistema e Compatibilidade

| Requisito | Detalhe / Recomendação |
|---|---|
| **Sistemas Operacionais** | Android (via Termux), Linux (Ubuntu, Debian, Raspberry Pi OS) ou Windows (WSL) |
| **Ambiente Node.js** | Versão 18.x ou superior |
| **Permissões Android** | Acesso ao armazenamento interno (`termux-setup-storage`) |
| **Gestão de Energia** | Permissão de execução em segundo plano sem restrições de bateria |

---

## 🛠️ Passo a Passo de Instalação no Termux (Android)

Siga os comandos abaixo em ordem. Você pode copiar todo o bloco de comandos e colar diretamente dentro do terminal do Termux.

### 1. Preparar o Termux e Permissões de Sistema

```bash
# Permite que o Termux acesse a memória interna do celular para salvar os torrents
termux-setup-storage

# Impede que o Android suspenda o Termux quando a tela desligar
termux-wake-lock

# Atualiza os pacotes internos do Termux
pkg update && pkg upgrade -y
```

### 2. Instalar o Node.js e o Git
```Bash
pkg install nodejs git -y
```

### 3. Criar a Pasta do Projeto e Baixar as Dependências
```Bash
# Cria e acessa a pasta do aplicativo
mkdir -p ~/ascbitts && cd ~/ascbitts

# Instala todas as bibliotecas necessárias para o funcionamento do script
npm install axios cheerio nodemailer axios-cookiejar-support tough-cookie
```

## ⚙️ Configuração do Sistema (`config.json`)

Para criar o arquivo de configuração sem erros de sintaxe ou aspas no celular, copie e cole o **comando abaixo diretamente no seu terminal Termux**. Ele criará o arquivo `config.json` pronto para uso:

```Bash
cat > config.json << 'EOF'
{
  "usuario": "SEU_USUARIO_AQUI",
  "senha": "SUA_SENHA_AQUI",
  "pastaDownload": "/storage/emulated/0/Download/Torrent-Flud/automacao",
  "urlLogin": "https://cliente.amigos-share.club/account-login.php",
  "urlIndex": "https://cliente.amigos-share.club/index.php",
  "urlSearchBase": "https://cliente.amigos-share.club/torrents-search.php",
  "Telegram": {
    "habilitar": false,
    "token": "SEU_BOT_TOKEN_TELEGRAM",
    "chatId": "SEU_CHAT_ID_TELEGRAM"
  },
  "Email": {
    "habilitar": false,
    "host": "smtp.gmail.com",
    "port": 465,
    "secure": true,
    "user": "seu_email@gmail.com",
    "pass": "sua_senha_de_app_aqui",
    "destinatario": "email_destino@gmail.com"
  },
  "buscas": [
    {
      "termoBusca": "one piece S23",
      "intervaloMinutos": 5,
      "horaInicioDaBusca": "12:00",
      "datasExecucao": ["30/08/2026", "06/09/2026", "13/09/2026"],
      "concluido": false,
      "ultimaBuscaMs": 0
    }
  ]
}
EOF
```

### 📝 Explicação dos Campos do `config.json`

- `usuario / senha`: Seus dados de acesso ao site.

- `pastaDownload`: Caminho absoluto onde os arquivos .torrent serão salvos.

- **Telegram**:

  - `habilitar`: Altere para true se desejar usar.

  - `token`: Token gerado pelo @BotFather.

  - `chatId`: Seu ID de usuário no Telegram.

- **Email**:

  - `habilitar`: Altere para true para receber alertas por e-mail.

  - `pass`: Senha de Aplicativo gerada na sua conta de e-mail (não use a senha normal).

- **buscas**: Lista de itens para busca agendada.

  - `termoBusca`: Texto exato a ser buscado no site.

  - `intervaloMinutos`: Tempo de espera entre cada tentativa.

  - `horaInicioDaBusca`: Horário (HH:MM) a partir do qual a busca começará a rodar.

  - `datasExecucao`: Lista de datas ["DD/MM/AAAA"] nas quais a busca está autorizada a rodar.


## 📥 Baixando o Script Principal (ascbitts.js)
Execute o comando abaixo para baixar o script direto do repositório:

```Bash
curl -o ascbitts.js https://raw.githubusercontent.com/bitts/ascbitts/main/ascbitts.js
```
_(Caso utilize o seu próprio repositório, substitua o link acima pela URL Raw do seu arquivo no GitHub)._

## 🚀 Como Executar o Aplicativo
Para iniciar a automação, navegue até a pasta do projeto (se já não estiver nela) e execute:

```Bash
cd ~/ascbitts
node ascbitts.js
```

### 🔋 Dica Importante: Mantendo o Script Rodando em Segundo Plano no Android
1. Ao abrir o Termux, puxe a barra de notificações do seu celular e garanta que o **Termux Wake Lock** esteja ativado (você pode clicar em "Acquire wake lock").

2. Desative a **Otimização de Bateria** do seu Android especificamente para o aplicativo Termux (Configurações do Android -> Aplicativos -> Termux -> Bateria -> Irrestrito).

## 🔄 Como Funcionam as Atualizações Automáticas (OTA)
O script possui um mecanismo embutido de autoatualização. Toda vez que você inicia o programa com o comando `node ascbitts.js`:

1. O sistema faz uma requisição ao repositório no GitHub para verificar a versão remota do arquivo.

2. Se houver uma versão mais nova lançada no GitHub, o terminal exibirá o seguinte aviso:

```Plaintext
[!] Uma nova versão foi encontrada! (Versão remota: X.Y.Z)
[?] Deseja baixar e aplicar a atualização agora? (s/n):
```

3. Digite `s` e pressione **Enter**. O script substituirá o arquivo local pelo novo código e exibirá a mensagem de sucesso. Suas configurações pessoais mantidas no `config.json` **não serão apagadas**.


## 🛠️ Configuração nos Principais Programas de Torrent

### 1. qBittorrent (Recomendado)
O qBittorrent é um cliente de código aberto, leve e livre de anúncios.

1. Abra o qBittorrent e vá em **Ferramentas** > **Opções** (ou pressione `Alt + O`).
2. No menu lateral esquerdo, clique em **Downloads**.
3. Role até a seção **Carregar automaticamente torrents de**.
4. Marque a caixa de seleção para ativar o recurso.
5. Clique no ícone de pasta (`+`) para adicionar o diretório que você deseja monitorar.
6. *(Opcional)* Configure a coluna "Salvar em" para definir onde os downloads concluídos daquela pasta específica devem ser guardados.
7. Clique em **Aplicar** e depois em **OK**.

### 2. uTorrent / BitTorrent
*Nota: O procedimento é idêntico para ambos os programas, pois compartilham a mesma base de código.*

1. Abra o programa e acesse **Opções** > **Preferências** (ao pressionar `Ctrl + P`).
2. No menu esquerdo, clique em **Diretórios**.
3. Na parte inferior, marque a opção **Carregar arquivos .torrent automaticamente de:**.
4. Clique no botão de reticências (`...`) e selecione a pasta desejada.
5. *(Recomendado)* Marque a opção **Apagar arquivos .torrent carregados** para que a pasta vigiada não fique cheia de arquivos antigos acumulados.
6. Clique em **Aplicar** e em **OK**.

### 3. Transmission
Muito popular entre usuários de Linux e macOS devido à sua interface minimalista.

#### No Windows / Linux (Interface GTK/Qt):
1. Vá em **Editar** > **Preferências**.
2. Acesse a aba **Downloads**.
3. Marque a opção **Adicionar torrents automaticamente de:**.
4. Selecione a pasta que o programa deve monitorar.

#### No macOS:
1. Abra as **Configurações** (Preferences) do Transmission.
2. Vá até a aba **Grupos** (Groups) ou **Geral** (General).
3. Ative a opção **Watch Folder** e aponte para o diretório de sua preferência.

### 4. Deluge
Outro cliente de código aberto altamente customizável que utiliza um sistema de plugins para essa função.

1. Vá em **Editar** > **Preferências**.
2. Clique na seção **Plugins** no menu esquerdo.
3. Verifique e marque a caixa do plugin nativo chamado **AutoAdd**.
4. Após ativar, uma nova opção chamada **AutoAdd** aparecerá no menu esquerdo das Preferências.
5. Clique em **AutoAdd**, selecione **Adicionar** e configure o caminho da pasta vigiada, além do local onde os downloads concluídos devem ser salvos.
6. Clique em **Aplicar**.

---

## 💡 Dicas de Produtividade

* **Integração com o Navegador:** Configure o seu navegador de internet (Chrome, Firefox, Edge) para baixar arquivos `.torrent` diretamente dentro da sua pasta vigiada. Assim, basta um clique no site de torrent para o download começar no programa de fundo.
* **Sincronização em Nuvem:** Se você configurar a pasta vigiada dentro de um serviço de nuvem (como OneDrive, Google Drive ou Dropbox), poderá salvar um arquivo `.torrent` usando o seu celular e o seu computador em casa iniciará o download remotamente.


## 📄 Licença e Autoria
- Criador: [Bitts](https://mbitts.com)

- Licença: GNU General Public License v3.0 (GNU GPL)

**Nota sobre a Licença**: _De acordo com os termos da licença GNU GPL, você é livre para modificar e redistribuir este software, desde que mantenha os créditos do criador original no cabeçalho do código fonte._
