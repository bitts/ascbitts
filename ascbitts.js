/**
 * Automação de Busca e Download de Torrents da Comunidade de Compartilhamento de arquivos da Comunidade Amigos Share
 * Criador: Bitts (https://mbitts.com)[github.com/bitts]
 * Licença: AGPLv3
 * ----------------------------------------------------------------------------
 * Copyright (C) 2026-present Bitts (https://github.com | mbitts.com)
 * 
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 * 
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://gnu.org>.
 * ------------------------------------------------------------------------------
 *
 * Descrição: Script para Termux/Node.js que realiza login, busca, verifica se
 * o arquivo já existe, faz o download e notifica (Telegram/E-mail).
 * Inclui sistema de autoatualização via GitHub e arquivo externo de configuração.
 */

const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const nodemailer = require('nodemailer');
const { wrapper } = require('axios-cookiejar-support');
const { CookieJar } = require('tough-cookie');

// ==========================================
// CONTROLE DE VERSÃO E ATUALIZAÇÃO
// ==========================================
const SCRIPT_VERSION = '1.0.0';
const GITHUB_RAW_URL = 'https://raw.githubusercontent.com/bitts/ascbitts/main/ascbitts.js';

// ==========================================
// CARREGAMENTO DA CONFIGURAÇÃO (config.json)
// ==========================================
const configPath = path.join(__dirname, 'config.json');
let CONFIG;

try {
    if (!fs.existsSync(configPath)) {
        console.log('[-] O arquivo config.json não foi encontrado!');
        console.log(`[-] Crie o arquivo config.json na pasta ${__dirname} baseado no modelo.`);
        process.exit(1);
    }
    const configData = fs.readFileSync(configPath, 'utf8');
    CONFIG = JSON.parse(configData);
} catch (erro) {
    console.error(`[-] Erro ao ler o arquivo config.json: ${erro.message}`);
    console.error('[-] Verifique se o JSON está formatado corretamente.');
    process.exit(1);
}

// Configurações Globais de Sessão e E-mail
const jar = new CookieJar();
const client = wrapper(axios.create({ jar, withCredentials: true }));

const emailTransporter = nodemailer.createTransport({
    host: CONFIG.Email.host,
    port: CONFIG.Email.port,
    secure: CONFIG.Email.secure,
    auth: { user: CONFIG.Email.user, pass: CONFIG.Email.pass }
});

// ==========================================
// FUNÇÕES DE ATUALIZAÇÃO
// ==========================================

// Função auxiliar para fazer perguntas no terminal
function perguntarTerminal(pergunta) {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    return new Promise(resolve => rl.question(pergunta, resposta => {
        rl.close();
        resolve(resposta.trim().toLowerCase());
    }));
}

// Verifica no GitHub se há uma versão mais recente
async function verificarAtualizacao() {
    console.log(`[+] Verificando atualizações no GitHub... (Versão atual: ${SCRIPT_VERSION})`);
    try {
        const resposta = await axios.get(GITHUB_RAW_URL);
        const scriptRemoto = resposta.data;

        // Extrai a versão do arquivo remoto usando Expressão Regular
        const match = scriptRemoto.match(/const\s+SCRIPT_VERSION\s*=\s*['"]([^'"]+)['"]/);
        if (match && match[1]) {
            const versaoRemota = match[1];

            if (versaoRemota !== SCRIPT_VERSION) {
                console.log(`\n[!] Uma nova versão foi encontrada! (Versão remota: ${versaoRemota})`);
                const resposta = await perguntarTerminal('[?] Deseja baixar e aplicar a atualização agora? (s/n): ');

                if (resposta === 's' || resposta === 'sim') {
                    console.log('[+] Baixando nova versão...');
                    // Sobrescreve o próprio arquivo (buscador.js) com o código recebido do GitHub
                    fs.writeFileSync(__filename, scriptRemoto, 'utf8');
                    console.log('[✔] Atualização concluída com sucesso!');
                    console.log('[!] O script será encerrado. Por favor, execute-o novamente para usar a nova versão.\n');
                    process.exit(0);
                } else {
                    console.log('[-] Atualização ignorada pelo usuário. Continuando com a versão atual...\n');
                }
            } else {
                console.log('[+] O script já está na versão mais recente.\n');
            }
        }
    } catch (erro) {
        console.log(`[-] Não foi possível verificar atualizações: ${erro.message}\n`);
    }
}

// ==========================================
// FUNÇÕES UTILITÁRIAS
// ==========================================
function obterDataAtual() {
    const d = new Date();
    const dia = String(d.getDate()).padStart(2, '0');
    const mes = String(d.getMonth() + 1).padStart(2, '0');
    const ano = d.getFullYear();
    return `${dia}/${mes}/${ano}`;
}

function obterHoraAtual() {
    const d = new Date();
    const hora = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${hora}:${min}`;
}

function limparNomeArquivo(nomeBase) {
    let nomeLimpo = nomeBase.replace(/[\\/:*?"<>|]/g, '').trim();
    if (!nomeLimpo.toLowerCase().endsWith('.torrent')) {
        nomeLimpo += '.torrent';
    }
    return nomeLimpo;
}

// ==========================================
// FUNÇÕES DE NOTIFICAÇÃO
// ==========================================
function gerarLayoutEmail(tarefa, nomeArquivo, pasta) {
    return `
    <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
        <h2 style="color: #0056b3;">✅ Download Concluído com Sucesso!</h2>
        <p>O sistema automatizado encontrou e baixou o arquivo aguardado.</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <tr style="background-color: #f8f9fa; border-bottom: 1px solid #ddd;">
                <td style="padding: 10px; font-weight: bold; width: 150px;">Termo Buscado:</td>
                <td style="padding: 10px;">${tarefa.termoBusca}</td>
            </tr>
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 10px; font-weight: bold;">Nome do Arquivo:</td>
                <td style="padding: 10px; color: #d9534f;">${nomeArquivo}</td>
            </tr>
            <tr style="background-color: #f8f9fa; border-bottom: 1px solid #ddd;">
                <td style="padding: 10px; font-weight: bold;">Salvo na Pasta:</td>
                <td style="padding: 10px;">${pasta}</td>
            </tr>
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 10px; font-weight: bold;">Data/Hora:</td>
                <td style="padding: 10px;">${obterDataAtual()} às ${obterHoraAtual()}</td>
            </tr>
        </table>
    </div>
    `;
}

async function enviarEmail(tarefa, nomeArquivo) {
    if (!CONFIG.Email.habilitar) return;
    try {
        const layoutHTML = gerarLayoutEmail(tarefa, nomeArquivo, CONFIG.pastaDownload);
        await emailTransporter.sendMail({
            from: `"Servidor Termux" <${CONFIG.Email.user}>`,
            to: CONFIG.Email.destinatario,
            subject: `[Arquivo .Torrent Baixado] ${tarefa.termoBusca}`,
            html: layoutHTML
        });
        console.log('[+] E-mail de notificação enviado com sucesso.');
    } catch (erro) {
        console.error(`[-] Falha ao enviar e-mail: ${erro.message}`);
    }
}

async function enviarTelegram(tarefa, nomeArquivo) {
    if (!CONFIG.Telegram.habilitar || !CONFIG.Telegram.token || !CONFIG.Telegram.chatId) return;
    const url = `https://api.telegram.org/bot${CONFIG.Telegram.token}/sendMessage`;
    const mensagem = `✅ <b>Download Salvo!</b>\n\n<b>Busca:</b> ${tarefa.termoBusca}\n<b>Arquivo:</b> ${nomeArquivo}`;
    try {
        await axios.post(url, { chat_id: CONFIG.Telegram.chatId, text: mensagem, parse_mode: 'HTML' });
        console.log('[+] Notificação Telegram enviada.');
    } catch (erro) {
        console.error(`[-] Falha no Telegram: ${erro.message}`);
    }
}

// ==========================================
// FUNÇÕES DE NAVEGAÇÃO E DOWNLOAD
// ==========================================
async function realizarLogin() {
    try {
        console.log(`[+] Iniciando sessão com o usuário: ${CONFIG.usuario}`);
        const payload = new URLSearchParams();
        payload.append('username', CONFIG.usuario);
        payload.append('password', CONFIG.senha);

        const resposta = await client.post(CONFIG.urlLogin, payload.toString(), {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Referer': CONFIG.urlIndex }
        });

        if (resposta.data.includes('name="password"') || resposta.data.toLowerCase().includes('senha incorreta')) {
            throw new Error('Credenciais inválidas.');
        }
        console.log('[+] Login validado com sucesso!');
        return true;
    } catch (erro) {
        console.error(`[-] Falha no login: ${erro.message}`);
        return false;
    }
}

async function baixarArquivo(url, caminhoCompleto, nomeArquivoLimpo, tarefa) {
    try {
        const respostaArquivo = await client.get(url, { responseType: 'stream' });
        const escritor = fs.createWriteStream(caminhoCompleto);
        respostaArquivo.data.pipe(escritor);

        return new Promise((resolve, reject) => {
            escritor.on('finish', async () => {
                console.log(`\n[✔] SUCESSO: ${nomeArquivoLimpo}`);
                console.log(`[✔] Arquivo salvo em: ${caminhoCompleto}`);

                await enviarTelegram(tarefa, nomeArquivoLimpo);
                await enviarEmail(tarefa, nomeArquivoLimpo);

                tarefa.concluido = true;
                resolve();
            });
            escritor.on('error', (erro) => {
                console.error(`[-] Erro ao salvar arquivo: ${erro.message}`);
                reject(erro);
            });
        });
    } catch (erro) {
        console.error(`[-] Falha no download de ${url}: ${erro.message}`);
    }
}

async function processarBusca(tarefa) {
    try {
        const termoEncode = encodeURIComponent(tarefa.termoBusca).replace(/%20/g, '+');
        const searchUrl = `${CONFIG.urlSearchBase}?search=${termoEncode}&cat=0&free=2&sort=id&tipo=contenha&order=desc`;

        console.log(`[+] Buscando: "${tarefa.termoBusca}"...`);
        const resposta = await client.get(searchUrl);
        const $ = cheerio.load(resposta.data);

        let linkDownload = null;
        let nomeExtraido = '';

        $('a').each((i, el) => {
            const href = $(el).attr('href');
            if (href && (href.includes('download.php?id=') || href.endsWith('.torrent'))) {
                linkDownload = href.startsWith('http') ? href : `https://cliente.amigos-share.club/${href}`;
                nomeExtraido = $(el).text().trim() || `torrent_${Date.now()}`;
                return false;
            }
        });

        if (linkDownload) {
            const nomeFinal = limparNomeArquivo(nomeExtraido);
            const caminhoCompleto = path.join(CONFIG.pastaDownload, nomeFinal);

            if (fs.existsSync(caminhoCompleto)) {
                console.log(`[!] O arquivo "${nomeFinal}" já existe na pasta!`);
                console.log(`[!] Tarefa "${tarefa.termoBusca}" marcada como concluída.`);
                tarefa.concluido = true;
            } else {
                console.log(`[+] Encontrado! Iniciando download de: ${nomeFinal}`);
                await baixarArquivo(linkDownload, caminhoCompleto, nomeFinal, tarefa);
            }
        } else {
            console.log(`[-] Ainda não disponível. Próxima busca em ${tarefa.intervaloMinutos} minutos.`);
        }
    } catch (erro) {
        console.error(`[-] Falha no scraping para "${tarefa.termoBusca}": ${erro.message}`);
    }
}

// ==========================================
// ORQUESTRADOR CENTRAL (Agendamento)
// ==========================================
async function tickAgendador() {
    const dataHoje = obterDataAtual();
    const horaMinutoAtual = obterHoraAtual();
    const msAtual = Date.now();
    const tarefasPendentes = CONFIG.buscas.filter(t => !t.concluido);

    if (tarefasPendentes.length === 0) {
        console.log('\n[✔] Todas as tarefas configuradas foram concluídas!');
        console.log('[✔] Encerrando o script. Até logo.');
        process.exit(0);
    }

    for (let tarefa of tarefasPendentes) {
        if (!tarefa.datasExecucao.includes(dataHoje)) continue;
        if (horaMinutoAtual < tarefa.horaInicioDaBusca) continue;

        const intervaloMs = tarefa.intervaloMinutos * 60 * 1000;
        const tempoDecorridoMs = msAtual - tarefa.ultimaBuscaMs;

        if (tempoDecorridoMs >= intervaloMs) {
            tarefa.ultimaBuscaMs = msAtual;
            await processarBusca(tarefa);
        }
    }
}

// ==========================================
// INTERFACE E CABEÇALHO DINÂMICO
// ==========================================
function exibirCabecalho() {
    // Detecta a largura do terminal (usa 60 como padrão se não conseguir detectar)
    const larguraTerminal = process.stdout.columns || 60;
    
    // Garante um tamanho mínimo para não quebrar o layout em telas muito pequenas
    const largura = Math.max(larguraTerminal, 45);

    const titulo = "AUTOMATIZADOR AMIGOS-SHARE (TERMUX/DEX)";
    const subTitulo = `Versão ${SCRIPT_VERSION} | Autor: github.com/bitts`;

    // Constrói as bordas dinâmicas com moldura Unicode
    const bordaSuperior = '╔' + '═'.repeat(largura - 2) + '╗';
    const bordaInferior = '╚' + '═'.repeat(largura - 2) + '╝';
    const linhaDivisoria = '╠' + '═'.repeat(largura - 2) + '╣';

    // Helper para centralizar qualquer texto dentro da largura atual da janela
    const centralizar = (texto) => {
        // Se o texto for maior que a janela, corta para não quebrar a moldura
        if (texto.length >= largura - 4) {
            texto = texto.substring(0, largura - 7) + '...';
        }
        const espacoTotal = largura - 2 - texto.length;
        const padEsquerda = Math.floor(espacoTotal / 2);
        const padDireita = espacoTotal - padEsquerda;
        return '║' + ' '.repeat(padEsquerda) + texto + ' '.repeat(padDireita) + '║';
    };

    console.clear();
    console.log(bordaSuperior);
    console.log(centralizar(titulo));
    console.log(linhaDivisoria);
    console.log(centralizar(subTitulo));
    console.log(bordaInferior);
    console.log(''); // Linha em branco após o cabeçalho
}

// ==========================================
// INICIALIZAÇÃO DO SCRIPT
// ==========================================
(async () => {
    // 1. Exibe o cabeçalho ajustado dinamicamente ao tamanho da tela
    exibirCabecalho();

    // 2. Checa por atualizações do script no GitHub
    await verificarAtualizacao();

    // 3. Garante que a pasta de download exista
    if (!fs.existsSync(CONFIG.pastaDownload)){
        fs.mkdirSync(CONFIG.pastaDownload, { recursive: true });
        console.log(`[+] Pasta de downloads criada: ${CONFIG.pastaDownload}`);
    }

    // 4. Testa credenciais de e-mail (se habilitado)
    if (CONFIG.Email && CONFIG.Email.habilitar) {
        console.log('[+] Verificando conexão com o servidor de E-mail...');
        try {
            await emailTransporter.verify();
            console.log('[+] Conexão SMTP (E-mail) validada com sucesso.');
        } catch (erro) {
            console.log(`[-] AVISO: Erro na autenticação do E-mail.`);
            console.log(`[-] Detalhe: ${erro.message}`);
            console.log(`[-] O script continuará funcionando, mas NÃO enviará e-mails.\n`);
            CONFIG.Email.habilitar = false; 
        }
    }

    // 5. Inicia processo de login no site e liga o agendador
    const logado = await realizarLogin();
    if (logado) {
        console.log(`\n[+] Agendador ativo. O sistema avaliará as tarefas a cada 1 minuto.`);
        console.log(`[+] As buscas respeitarão seus horários de início e intervalos individuais.\n`);
        
        setInterval(tickAgendador, 60000);
        tickAgendador(); 
    } else {
        console.log(`[-] Verifique seus dados de acesso no config.json e tente novamente.`);
        process.exit(1);
    }
})();
