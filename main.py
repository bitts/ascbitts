#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amigos Share Watcher
Cliente de terminal para pesquisar torrents no Amigos Share Club.

O programa usa HTTP/HTML/Inertia, mantém cookies de sessão e não depende
de navegador gráfico. Respeite os termos do site e os direitos dos conteúdos.
"""
from __future__ import annotations

import argparse
import copy
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import shutil
import signal
import smtplib
import ssl
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
WATCH_FILE = APP_DIR / "watchlist.json"
LOG_FILE = APP_DIR / "watcher.log"
PID_FILE = APP_DIR / "watcher.pid"
BASE_DEFAULT = "https://amigos-share.club"
USER_AGENT = "AmigosShareWatcher/1.0 (+personal use; respectful polling)"
FILTER_KEYS = {
    "q", "exact", "category", "team", "uploader", "year_min", "year_max",
    "size_min", "size_max", "period", "swarm", "freeleech", "double_upload",
    "internal", "genre", "resolution", "container", "video_codec", "hdr",
    "audio_codec", "audio_immersive", "audio_channels", "language",
    "dub_language", "sort", "direction", "per_page"
}
BOOL_KEYS = {"exact", "freeleech", "double_upload", "internal"}
LIST_KEYS = {
    "genre", "resolution", "container", "video_codec", "hdr", "audio_codec",
    "audio_immersive", "audio_channels", "language", "dub_language"
}

DEFAULT_CONFIG = {
    "site": {"base_url": BASE_DEFAULT, "username": "", "password": "",
             "remember_me": True, "timeout_seconds": 30,
             "session_check_minutes": 15, "user_agent": USER_AGENT},
    "downloads": {"directory": str(Path.home() / "Downloads" / "torrents"),
                  "create_directory": True, "overwrite": False},
    "ui": {"clear_screen": True},
    "scheduler": {"enabled_on_start": False, "minimum_interval_seconds": 300,
                  "request_delay_seconds": 3, "jitter_seconds": 2},
    "notifications": {
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "email": {"enabled": False, "provider": "gmail", "smtp_host": "smtp.gmail.com", "smtp_port": 587,
                  "username": "", "password": "", "from": "", "to": "",
                  "security": "starttls", "starttls": True, "timeout_seconds": 30}
    }
}

def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt
    except (ValueError, TypeError):
        return None

def load_json(path: Path, default: Any) -> Any:
    """
    Carrega um arquivo JSON.

    Caso o arquivo não exista, retorna uma cópia do valor padrão.

    Em caso de erro de sintaxe, informa precisamente:
    - Arquivo que apresentou o problema;
    - Número da linha;
    - Coluna;
    - Motivo do erro.

    Isso facilita a correção manual dos arquivos de configuração.
    """
    if not path.exists():
        return copy.deepcopy(default)

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    except json.JSONDecodeError as exc:
        print("\n" + "=" * 60)
        print("ERRO NA LEITURA DO ARQUIVO JSON")
        print("=" * 60)

        print(f"Arquivo: {path}")
        print(f"Linha:   {exc.lineno}")
        print(f"Coluna:  {exc.colno}")
        print(f"Erro:    {exc.msg}")

        try:
            with path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

            if 0 < exc.lineno <= len(lines):
                print("\nTrecho problemático:")
                print(lines[exc.lineno - 1].rstrip())
                print(" " * max(0, exc.colno - 1) + "^")

        except OSError:
            pass

        print("\nVerifique a sintaxe do arquivo antes de continuar.")
        print("=" * 60)

        raise

    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"O arquivo {path} não está codificado em UTF-8."
        ) from exc

def save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

def merge_config(defaults: dict, current: dict) -> dict:
    """Mescla configurações antigas com os padrões novos sem apagar valores existentes."""
    result = copy.deepcopy(defaults)
    if not isinstance(current, dict):
        raise ValueError("A raiz de config.json precisa ser um objeto JSON.")
    for key, value in current.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value
    return result


def configure_logging(log_path: Path = LOG_FILE, level: str = "INFO") -> logging.Logger:
    """Configura log rotativo para auditoria, evitando crescimento ilimitado."""
    logger = logging.getLogger("asw")
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.propagate = False
    if not logger.handlers:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024,
                                      backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
        logger.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(console)
    return logger


def report_error(logger: logging.Logger, code: str, exc: BaseException,
                 context: str, explanation: str, causes: str = "") -> None:
    detail = (f"[{code}] {context}: {type(exc).__name__}: {exc}. "
              f"Significado: {explanation}")
    if causes:
        detail += f" Causas possíveis: {causes}"
    logger.exception(detail) if exc.__traceback__ else logger.error(detail)


def ensure_files() -> tuple[dict, list]:
    if not CONFIG_FILE.exists():
        save_json_atomic(CONFIG_FILE, DEFAULT_CONFIG)
    if not WATCH_FILE.exists():
        save_json_atomic(WATCH_FILE, [])
    loaded = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    config = merge_config(DEFAULT_CONFIG, loaded)
    # Migração: arquivos antigos tinham somente o booleano starttls.
    old_email = loaded.get("notifications", {}).get("email", {}) if isinstance(loaded, dict) else {}
    email_cfg = config.get("notifications", {}).get("email", {})
    if "security" not in old_email:
        email_cfg["security"] = (
            "starttls" if old_email.get("starttls", True)
            else ("ssl" if int(old_email.get("smtp_port", 587)) == 465 else "none")
        )
    if config != loaded:
        save_json_atomic(CONFIG_FILE, config)
    items = load_json(WATCH_FILE, [])
    if not isinstance(items, list):
        raise ValueError("watchlist.json precisa conter uma lista JSON.")
    return config, items

def deep_get(d: dict, key: str, default=None):
    return d.get(key, default) if isinstance(d, dict) else default

def page_payload(response: requests.Response) -> dict:
    """Extrai o JSON Inertia contido em data-page."""
    response.raise_for_status()
    # Respostas Inertia podem vir diretamente em JSON.
    ctype = response.headers.get("Content-Type", "")
    if "application/json" in ctype:
        try:
            obj = response.json()
            if isinstance(obj, dict) and "props" in obj:
                return obj
        except ValueError:
            pass
    soup = BeautifulSoup(response.text, "html.parser")
    node = soup.find("script", attrs={"data-page": True})
    if node and node.string:
        return json.loads(node.string)
    # Fallback: algumas versões retornam o JSON como texto dentro do script.
    if node:
        return json.loads(node.get_text())
    raise RuntimeError("A resposta não contém o payload Inertia esperado (data-page).")

class SiteClient:
    """Sessão HTTP autenticada para o Amigos Share Club."""
    def __init__(self, config: dict):
        self.cfg = config["site"]
        self.base = self.cfg.get("base_url", BASE_DEFAULT).rstrip("/")
        if urllib.parse.urlparse(self.base).scheme != "https":
            raise ValueError("Por segurança, site.base_url deve usar HTTPS.")
        self.timeout = int(self.cfg.get("timeout_seconds", 30))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.cfg.get("user_agent", USER_AGENT),
            "Accept": "text/html, application/xhtml+xml, application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.base + "/login",
            "Origin": self.base
        })
        self.logged_in = False
        self.last_check = 0.0
        self.inertia_version = None

    def _csrf_headers(self) -> dict:
        token = self.session.cookies.get("XSRF-TOKEN")
        return {"X-XSRF-TOKEN": urllib.parse.unquote(token)} if token else {}

    def login(self, force: bool = False) -> bool:
        if self.logged_in and not force:
            return True
        r = self.session.get(self.base + "/login", timeout=self.timeout)
        r.raise_for_status()
        try:
            login_page = page_payload(r)
            self.inertia_version = login_page.get("version")
        except Exception:
            # A versão pode não estar disponível em versões futuras do site.
            self.inertia_version = None
        soup = BeautifulSoup(r.text, "html.parser")
        # A aplicação fornecida não exibe token hidden; Laravel normalmente
        # entrega o token por cookie XSRF-TOKEN.
        payload = {
            "username": self.cfg.get("username", ""),
            "password": self.cfg.get("password", "")
        }
        if self.cfg.get("remember_me", True):
            payload["remember"] = "on"
        if not payload["username"] or not payload["password"]:
            raise RuntimeError("Informe site.username e site.password em config.json.")
        headers = {
            **self._csrf_headers(),
            "Referer": self.base + "/login",
            "Accept": "text/html, application/xhtml+xml"
        }
        post = self.session.post(self.base + "/login", data=payload,
                                 headers=headers, timeout=self.timeout,
                                 allow_redirects=True)
        post.raise_for_status()
        # O login correto redireciona para uma página autenticada. A validação
        # é feita tentando carregar /torrents e verificando auth.user.
        self.logged_in = False
        page = self._fetch_page("/torrents", {})
        auth = page.get("props", {}).get("auth", {})
        if not auth.get("user"):
            raise RuntimeError("O site não confirmou a autenticação. Confira usuário/senha ou eventual desafio adicional.")
        self.logged_in = True
        self.last_check = time.time()
        return True

    def _fetch_page(self, path: str, params: dict) -> dict:
        url = self.base + path
        headers = {"X-Inertia": "true"}
        if self.inertia_version:
            headers["X-Inertia-Version"] = self.inertia_version
        headers.update(self._csrf_headers())
        r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        if r.status_code in (401, 403):
            self.logged_in = False
            raise PermissionError("Sessão não autenticada ou acesso negado.")
        return page_payload(r)

    def keep_session(self, interval_minutes: int = 15) -> None:
        if not self.logged_in:
            self.login()
            return
        if time.time() - self.last_check >= interval_minutes * 60:
            page = self._fetch_page("/torrents", {})
            user = page.get("props", {}).get("auth", {}).get("user")
            if not user:
                self.logged_in = False
                self.login(force=True)
            self.last_check = time.time()

    def search(self, filters: dict) -> list[dict]:
        params = {}
        for key, value in filters.items():
            if key not in FILTER_KEYS or value is None or value == "" or value == []:
                continue
            if isinstance(value, bool):
                if value:
                    params[key] = "1"
            elif isinstance(value, list):
                # Laravel interpreta filtros múltiplos como arrays query-string.
                params[f"{key}[]"] = value
            else:
                params[key] = value
        try:
            page = self._fetch_page("/torrents", params)
        except PermissionError:
            self.login(force=True)
            page = self._fetch_page("/torrents", params)
        props = page.get("props", {})
        torrents = props.get("torrents", {})
        if isinstance(torrents, list):
            return torrents
        return torrents.get("data", []) if isinstance(torrents, dict) else []

    def download(self, torrent_id: int, destination: Path, overwrite: bool = False) -> Path:
        url = f"{self.base}/torrents/{int(torrent_id)}/download"
        headers = {**self._csrf_headers(), "Referer": self.base + "/torrents"}
        with self.session.get(url, headers=headers, stream=True,
                              allow_redirects=True, timeout=self.timeout) as r:
            if r.status_code in (401, 403):
                self.login(force=True)
                with self.session.get(url, headers=self._csrf_headers(), stream=True,
                                      allow_redirects=True, timeout=self.timeout) as retry:
                    return self._save_torrent_response(retry, destination, overwrite)
            return self._save_torrent_response(r, destination, overwrite)

    @staticmethod
    def _save_torrent_response(r, destination: Path, overwrite: bool) -> Path:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").lower()
        disposition = r.headers.get("Content-Disposition", "")
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposition, re.I)
        filename = urllib.parse.unquote(match.group(1)).strip('"') if match else ""
        if not filename:
            filename = f"torrent-{int(time.time())}.torrent"
        filename = Path(filename).name
        if not filename.lower().endswith(".torrent"):
            filename += ".torrent"
        if "text/html" in content_type:
            raise RuntimeError("O servidor retornou HTML em vez de um arquivo .torrent; verifique a sessão.")
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / filename
        if target.exists() and not overwrite:
            stem, suffix, n = target.stem, target.suffix, 2
            while (destination / f"{stem}-{n}{suffix}").exists():
                n += 1
            target = destination / f"{stem}-{n}{suffix}"
        temp = target.with_suffix(target.suffix + ".part")
        with temp.open("wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    f.write(chunk)
        if temp.stat().st_size < 20:
            temp.unlink(missing_ok=True)
            raise RuntimeError("Arquivo recebido é pequeno demais para ser um .torrent válido.")
        with temp.open("rb") as f:
            if not f.read(1) == b"d":
                temp.unlink(missing_ok=True)
                raise RuntimeError("O conteúdo baixado não parece ser um torrent (bencode inválido).")
        os.replace(temp, target)
        return target

class Notifier:
    """Envio de notificações com suporte a Gmail SSL/STARTTLS e erros diagnosticáveis."""
    def __init__(self, config: dict):
        self.cfg = config.get("notifications", {})
        self.logger = logging.getLogger("asw")

    def _send_email(self, subject: str, message: str, em: dict) -> None:
        host = str(em.get("smtp_host") or "").strip()
        port = int(em.get("smtp_port", 587))
        username = str(em.get("username") or "").strip()
        password = str(em.get("password") or "")
        sender = str(em.get("from") or username).strip()
        recipient = str(em.get("to") or "").strip()
        security = str(em.get("security") or "").strip().lower()
        if not security:
            security = "starttls" if em.get("starttls", True) else ("ssl" if port == 465 else "none")
        if security == "auto":
            security = "ssl" if port == 465 else ("starttls" if port == 587 else "none")
        if not host or not recipient:
            raise ValueError("Servidor SMTP ou destinatário não configurado.")
        if security not in ("ssl", "starttls", "none"):
            raise ValueError("security deve ser ssl, starttls ou none.")
        if security == "starttls" and port == 465:
            raise ValueError("A porta 465 normalmente exige security='ssl', não STARTTLS.")

        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, sender, recipient
        msg.set_content(message)
        context = ssl.create_default_context()
        timeout = int(em.get("timeout_seconds", 30))
        try:
            if security == "ssl":
                with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
                    server.ehlo()
                    if username:
                        server.login(username, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=timeout) as server:
                    server.ehlo()
                    if security == "starttls":
                        server.starttls(context=context)
                        server.ehlo()
                    if username:
                        server.login(username, password)
                    server.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise RuntimeError(
                "ASW-MAIL-002: Gmail recusou a autenticação. Use o endereço completo "
                "e uma Senha de app do Google; a senha normal da conta geralmente não funciona."
            ) from exc
        except (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError, OSError) as exc:
            raise RuntimeError(
                f"ASW-MAIL-001: conexão SMTP encerrada/indisponível ({host}:{port}, {security}). "
                "Verifique host, porta, SSL/STARTTLS, firewall, rede e bloqueios do provedor."
            ) from exc
        except smtplib.SMTPException as exc:
            raise RuntimeError(
                f"ASW-MAIL-003: erro no protocolo SMTP durante envio: {exc}. "
                "Verifique remetente, destinatário e política do servidor."
            ) from exc

    def send(self, subject: str, message: str) -> list[str]:
        sent = []
        tg = self.cfg.get("telegram", {})
        if tg.get("enabled"):
            if not tg.get("bot_token") or not tg.get("chat_id"):
                raise ValueError("ASW-TG-001: Telegram ativado, mas token ou chat_id vazio.")
            try:
                url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
                r = requests.post(url, data={"chat_id": tg["chat_id"],
                                             "text": f"{subject}\\n{message}"}, timeout=20)
                r.raise_for_status()
                sent.append("Telegram")
            except requests.RequestException as exc:
                raise RuntimeError(f"ASW-TG-002: falha na API do Telegram: {exc}") from exc
        em = self.cfg.get("email", {})
        if em.get("enabled"):
            if not em.get("smtp_host") or not em.get("to"):
                raise ValueError("ASW-MAIL-005: e-mail ativado, mas SMTP ou destinatário vazio.")
            self._send_email(subject, message, em)
            sent.append("E-mail")
        return sent

    def test_email(self) -> None:
        em = self.cfg.get("email", {})
        if not em.get("enabled"):
            raise ValueError("ASW-MAIL-006: habilite o e-mail antes de testar.")
        self._send_email("Teste Amigos Share Watcher",
                         "Esta é uma mensagem de teste da configuração SMTP.", em)


def validate_watch_item(item: dict) -> None:
    if not isinstance(item, dict):
        raise ValueError("Cada elemento de watchlist.json deve ser um objeto JSON.")
    if not isinstance(item.get("nome"), str) or not item["nome"].strip():
        raise ValueError("O campo 'nome' é obrigatório.")
    if not isinstance(item.get("filtros"), dict) or not item["filtros"].get("q"):
        raise ValueError(f"O item '{item['nome']}' precisa de filtros.q.")
    unknown = set(item["filtros"]) - FILTER_KEYS
    if unknown:
        raise ValueError(f"Filtros não reconhecidos: {', '.join(sorted(unknown))}")
    if not isinstance(item.get("intervalo_segundos", 900), int) or item.get("intervalo_segundos", 900) < 60:
        raise ValueError("intervalo_segundos deve ser inteiro e no mínimo 60.")
    if not parse_dt(item.get("inicio")):
        raise ValueError("O campo 'inicio' deve ser uma data ISO 8601 válida.")

class Watcher:
    def __init__(self, config: dict, items: list, stop_event: threading.Event,
                 on_event=None, dry_run=False, force_download=False):
        self.config, self.items, self.stop_event = config, items, stop_event
        self.on_event = on_event or (lambda msg: print(msg))
        self.dry_run = dry_run
        self.force_download = force_download
        self.client = SiteClient(config)
        self.notifier = Notifier(config)
        self.last_checks: dict[str, float] = {}

    def run_once(self, item: dict, ignore_schedule=False) -> list[dict]:
        validate_watch_item(item)
        if item.get("baixado") and not self.force_download:
            return []
        start = parse_dt(item["inicio"])
        if not ignore_schedule and start and datetime.now(start.tzinfo) < start:
            return []
        key = str(item.get("id") or item["nome"])
        now = time.time()
        interval = max(int(item.get("intervalo_segundos", 900)),
                       int(self.config["scheduler"].get("minimum_interval_seconds", 300)))
        if not ignore_schedule and now - self.last_checks.get(key, 0) < interval:
            return []
        self.last_checks[key] = now
        self.client.keep_session(int(self.config["site"].get("session_check_minutes", 15)))
        found = self.client.search(item["filtros"])
        # Os filtros do site são aplicados no servidor. Nome adicional permite
        # restringir resultados com uma expressão regular opcional.
        regex = item.get("nome_regex")
        if regex:
            found = [x for x in found if re.search(regex, x.get("name", ""), re.I)]
        if not found:
            self.on_event(f"Sem resultados: {item['nome']}")
            return []
        downloads = []
        for torrent in found:
            tid = torrent.get("id")
            if tid is None:
                continue
            if self.dry_run:
                self.on_event(f"[TESTE] Encontrado: {torrent.get('name')} (ID {tid})")
                downloads.append(torrent)
                continue
            dest = Path(self.config["downloads"]["directory"]).expanduser()
            file_path = self.client.download(tid, dest,
                                             bool(self.config["downloads"].get("overwrite", False)))
            item["baixado"] = now_iso()
            item["torrent_id"] = tid
            item["torrent_nome"] = torrent.get("name")
            item["arquivo"] = str(file_path)
            save_json_atomic(WATCH_FILE, self.items)
            self.on_event(f"Baixado: {torrent.get('name')} -> {file_path}")
            try:
                services = self.notifier.send("Torrent encontrado e baixado",
                    f"Item monitorado: {item['nome']}\nTorrent: {torrent.get('name')}\n"
                    f"ID: {tid}\nArquivo: {file_path}\nData: {item['baixado']}")
                if services:
                    self.on_event("Notificação enviada: " + ", ".join(services))
            except Exception as exc:
                self.on_event(f"Falha ao enviar notificação: {exc}")
            downloads.append(torrent)
            break
        return downloads

    def loop(self):
        delay = max(1, int(self.config["scheduler"].get("request_delay_seconds", 3)))
        jitter = max(0, int(self.config["scheduler"].get("jitter_seconds", 2)))
        while not self.stop_event.is_set():
            try:
                for item in self.items:
                    if self.stop_event.is_set():
                        break
                    try:
                        self.run_once(item)
                    except Exception as exc:
                        logging.getLogger("asw").exception(
                            "[ASW-WATCH-001] Falha no item '%s'; o ciclo continuará.",
                            item.get("nome", "?"))
                        self.on_event(f"Erro [ASW-WATCH-001] no item '{item.get('nome', '?')}': {exc}")
                    self.stop_event.wait(delay + (int(time.time()) % (jitter + 1) if jitter else 0))
            except Exception as exc:
                logging.getLogger("asw").exception("[ASW-WATCH-002] Falha no ciclo geral.")
                self.on_event(f"Erro [ASW-WATCH-002] no ciclo: {exc}")
            self.stop_event.wait(2)

class App:
    def __init__(self):
        self.config, self.items = ensure_files()
        self.stop_event = threading.Event()
        self.worker = None
        self.thread = None
        self.logger = configure_logging()

    def say(self, message: str):
        print(message)
        self.logger.info(message)

    def clear_screen(self):
        if self.config.get("ui", {}).get("clear_screen", True) and sys.stdout.isatty():
            os.system("cls" if os.name == "nt" else "clear")

    def toggle_clear_screen(self):
        ui = self.config.setdefault("ui", {})
        ui["clear_screen"] = not bool(ui.get("clear_screen", True))
        self.save_config()
        self.say("Limpeza automática da tela " +
                 ("ATIVADA." if ui["clear_screen"] else "DESATIVADA."))

    @staticmethod
    def pause():
        input("\nPressione ENTER para continuar...")

    @staticmethod
    def header():
        width = shutil.get_terminal_size((72, 20)).columns
        title = " AMIGOS SHARE WATCHER "
        print("\n" + "=" * min(width, 72))
        print(title.center(min(width, 72)))
        print("=" * min(width, 72))

    def save_config(self):
        save_json_atomic(CONFIG_FILE, self.config)

    def save_items(self):
        save_json_atomic(WATCH_FILE, self.items)

    def start_worker(self):
        if self.thread and self.thread.is_alive():
            self.say("Monitoramento já está ativo.")
            return
        self.stop_event.clear()
        self.worker = Watcher(self.config, self.items, self.stop_event, self.say)
        self.thread = threading.Thread(target=self.worker.loop, daemon=True)
        self.thread.start()
        self.say("Monitoramento iniciado em segundo plano. O menu continua disponível.")

    def stop_worker(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=5)
            self.say("Solicitação de parada enviada.")
        else:
            self.say("Monitoramento não está ativo.")

    def status(self):
        active = bool(self.thread and self.thread.is_alive())
        print(f"\nMonitoramento: {'ATIVO' if active else 'parado'}")
        print(f"Itens cadastrados: {len(self.items)}")
        print(f"Destino: {self.config['downloads']['directory']}")
        print(f"Configuração: {CONFIG_FILE}")
        print(f"Lista: {WATCH_FILE}")

    def list_items(self, downloaded: bool):
        chosen = [x for x in self.items if bool(x.get("baixado")) == downloaded]
        print(f"\n{'JÁ BAIXADOS' if downloaded else 'PENDENTES'} ({len(chosen)})")
        for i, item in enumerate(chosen, 1):
            print(f"\n{i}. {item.get('nome')}")
            print(f"   Busca: {item.get('filtros', {}).get('q')}")
            print(f"   Início: {item.get('inicio')}")
            print(f"   Intervalo: {item.get('intervalo_segundos')} s")
            if downloaded:
                dt = parse_dt(item.get("baixado"))
                friendly = dt.astimezone().strftime("%d/%m/%Y %H:%M:%S %Z") if dt else item.get("baixado")
                print(f"   Baixado em: {friendly}")
                print(f"   Torrent: {item.get('torrent_nome', '-')}")
                print(f"   Arquivo: {item.get('arquivo', '-')}")
        if not chosen:
            print("  (nenhum)")

    def add_item(self):
        print("\nNOVO ITEM")
        nome = input("Nome/identificação: ").strip()
        q = input("Termo de busca (q) [obrigatório]: ").strip()
        if not nome or not q:
            print("Nome e termo de busca são obrigatórios.")
            return
        inicio = input("Início ISO 8601 [agora; ex. 2026-11-09T20:00:00-03:00]: ").strip() or now_iso()
        try:
            if not parse_dt(inicio):
                raise ValueError()
        except ValueError:
            print("Data inválida.")
            return
        try:
            intervalo = int(input("Intervalo em segundos [900]: ").strip() or "900")
            if intervalo < 60:
                raise ValueError()
        except ValueError:
            print("Intervalo inválido; use pelo menos 60 segundos.")
            return
        filters = {"q": q}
        print("\nFiltros adicionais (ENTER mantém padrão):")
        for key, label in [
            ("exact", "Busca exata? (s/N)"),
            ("category", "ID da categoria/subcategoria"),
            ("team", "ID do grupo/team"),
            ("uploader", "Nick do uploader"),
            ("year_min", "Ano mínimo"), ("year_max", "Ano máximo"),
            ("size_min", "Tamanho mínimo em bytes"), ("size_max", "Tamanho máximo em bytes"),
            ("period", "Período (day/week/month/year)"),
            ("swarm", "Enxame (alive/dead)"),
            ("freeleech", "Somente freeleech? (s/N)"),
            ("double_upload", "Somente 2x upload? (s/N)"),
            ("internal", "Somente interno? (s/N)")
        ]:
            value = input(f"{label}: ").strip()
            if not value:
                continue
            if key in BOOL_KEYS:
                filters[key] = value.lower() in ("s", "sim", "y", "yes", "1")
            elif key in {"year_min", "year_max", "size_min", "size_max", "category", "team"}:
                try: filters[key] = int(value)
                except ValueError: print(f"Valor ignorado para {key}.")
            else:
                filters[key] = value
        item = {"id": f"item-{int(time.time())}", "nome": nome, "inicio": inicio,
                "intervalo_segundos": intervalo, "filtros": filters, "baixado": None}
        try:
            validate_watch_item(item)
            self.items.append(item)
            self.save_items()
            print("Item cadastrado.")
        except ValueError as exc:
            print(f"Não foi possível cadastrar: {exc}")

    def edit_site_credentials(self):
        print("\nCREDENCIAIS DO SITE (a senha não será exibida)")
        self.config["site"]["username"] = input("NickName: ").strip()
        password = getpass.getpass("Senha: ")
        if password:
            self.config["site"]["password"] = password
        self.save_config()
        print("Configuração salva com permissões restritas quando suportado.")

    def edit_download_dir(self):
        current = self.config["downloads"]["directory"]
        print(f"Destino atual: {current}")
        value = input("Novo caminho (ENTER mantém): ").strip()
        if value:
            path = Path(value).expanduser()
            if not path.exists():
                create = input(f"Pasta não existe. Criar {path}? (s/N): ").strip().lower()
                if create in ("s", "sim"):
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    return
            if not path.is_dir():
                print("O caminho não é uma pasta.")
                return
            self.config["downloads"]["directory"] = str(path.resolve())
            self.save_config()
            print("Destino atualizado.")

    def edit_notifications(self):
        print("\nNOTIFICAÇÕES")
        print("1. Telegram")
        print("2. E-mail SMTP")
        print("0. Voltar")
        op = input("> ").strip()
        if op == "1":
            n = self.config["notifications"]["telegram"]
            n["enabled"] = input("Ativar Telegram? (s/N): ").lower() in ("s", "sim")
            n["bot_token"] = input("Token do bot (ENTER mantém): ").strip() or n.get("bot_token", "")
            n["chat_id"] = input("Chat ID (ENTER mantém): ").strip() or n.get("chat_id", "")
            self.save_config()
        elif op == "2":
            n = self.config["notifications"]["email"]
            n["enabled"] = input("Ativar e-mail? (s/N): ").lower() in ("s", "sim")
            provider = input("Provedor [gmail/outro] (gmail): ").strip().lower() or "gmail"
            n["provider"] = provider
            if provider == "gmail":
                n["smtp_host"] = "smtp.gmail.com"
                if int(n.get("smtp_port", 587)) not in (465, 587):
                    n["smtp_port"] = 587
            for key, label in [("smtp_host","Servidor SMTP"),("smtp_port","Porta"),
                               ("username","Usuário SMTP (e-mail completo)"),
                               ("from","Remetente"),("to","Destinatário")]:
                default = n.get(key, "")
                val = input(f"{label} [{default}]: ").strip()
                if val:
                    n[key] = int(val) if key == "smtp_port" else val
            default_security = "ssl" if int(n.get("smtp_port", 587)) == 465 else "starttls"
            security = input(f"Segurança [ssl/starttls] ({default_security}): ").strip().lower() or default_security
            if security not in ("ssl", "starttls"):
                print("Modo inválido; mantendo STARTTLS.")
                security = "starttls"
            n["security"] = security
            n["starttls"] = security == "starttls"
            pw = getpass.getpass("Senha SMTP / Senha de app Google (ENTER mantém): ")
            if pw:
                n["password"] = pw
            self.save_config()
            print("Configuração salva. No Gmail, utilize uma Senha de app.")

    def test_notifications(self):
        try:
            email = self.config.get("notifications", {}).get("email", {})
            if email.get("enabled"):
                Notifier(self.config).test_email()
                self.say("ASW-MAIL-000: teste de e-mail enviado com sucesso.")
            else:
                sent = Notifier(self.config).send(
                    "Teste Amigos Share Watcher", "Mensagem de teste.")
                self.say("Enviado por: " + (", ".join(sent) if sent else "nenhum canal ativo/configurado"))
        except Exception as exc:
            self.logger.exception("[ASW-NOTIFY-001] Falha no teste de notificação. "
                                  "Significado: o canal configurado não concluiu o envio.")
            print(f"Falha no teste: {exc}")

    def test_search(self):
        q = input("Termo de busca para teste: ").strip()
        if not q: return
        filters = {"q": q}
        print("Filtros avançados podem ser configurados no watchlist.json.")
        download = input("Baixar o primeiro resultado se encontrado? (s/N): ").lower() in ("s","sim")
        try:
            client = SiteClient(self.config)
            client.login()
            results = client.search(filters)
            print(f"Resultados encontrados: {len(results)}")
            for i, t in enumerate(results[:10], 1):
                print(f"{i}. {t.get('name')} [ID {t.get('id')}]")
            if results and download:
                confirm = input("Confirmar download do primeiro resultado? (s/N): ").lower()
                if confirm in ("s","sim"):
                    p = client.download(results[0]["id"],
                        Path(self.config["downloads"]["directory"]).expanduser(),
                        self.config["downloads"].get("overwrite", False))
                    print(f"Arquivo salvo: {p}")
        except Exception as exc:
            print(f"Teste falhou: {exc}")

    def validate(self):
        print("\nVALIDAÇÃO")
        try:
            dest = Path(self.config["downloads"]["directory"]).expanduser()
            print(f"Destino existe: {'SIM' if dest.is_dir() else 'NÃO'} ({dest})")
            print(f"Credenciais preenchidas: {'SIM' if self.config['site'].get('username') and self.config['site'].get('password') else 'NÃO'}")
            valid = 0
            for item in self.items:
                try: validate_watch_item(item); valid += 1
                except Exception as e: print(f"Item inválido {item.get('nome')}: {e}")
            print(f"Itens válidos: {valid}/{len(self.items)}")
            if self.config["site"].get("username") and self.config["site"].get("password"):
                if input("Testar autenticação agora? (s/N): ").lower() in ("s","sim"):
                    SiteClient(self.config).login()
                    print("Autenticação concluída.")
        except Exception as exc:
            print(f"Validação falhou: {exc}")

    def backup(self):
        folder = APP_DIR / "backups"
        folder.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        paths = []
        for source in (CONFIG_FILE, WATCH_FILE):
            target = folder / f"{source.stem}-{stamp}{source.suffix}"
            shutil.copy2(source, target)
            paths.append(str(target))
        print("Backup criado:\n" + "\n".join(paths))

    def remove_item(self):
        self.list_items(False)
        try:
            idx = int(input("\nNúmero do item para remover: ")) - 1
            pending = [i for i,x in enumerate(self.items) if not x.get("baixado")]
            actual = pending[idx]
            del self.items[actual]
            self.save_items()
            print("Item removido.")
        except (ValueError, IndexError):
            print("Seleção inválida.")

    def menu(self):
        while True:
            self.header()
            self.status()
            print("""
1. Iniciar monitoramento em segundo plano
2. Parar monitoramento
3. Listar itens pendentes
4. Listar itens baixados
5. Cadastrar novo item
6. Remover item pendente
7. Testar pesquisa / download
8. Configurar usuário e senha do site
9. Configurar pasta de destino
10. Configurar notificações (Telegram/e-mail)
11. Testar envio de notificações
12. Validar configurações e autenticação
13. Fazer backup dos arquivos JSON
14. Ativar/desativar limpeza da interface
0. Sair
""")
            op = input("Selecione: ").strip()
            if op == "1": self.start_worker()
            elif op == "2": self.stop_worker()
            elif op == "3": self.list_items(False); self.pause()
            elif op == "4": self.list_items(True); self.pause()
            elif op == "5": self.add_item(); self.pause()
            elif op == "6": self.remove_item(); self.pause()
            elif op == "7": self.test_search(); self.pause()
            elif op == "8": self.edit_site_credentials(); self.pause()
            elif op == "9": self.edit_download_dir(); self.pause()
            elif op == "10": self.edit_notifications(); self.pause()
            elif op == "11": self.test_notifications(); self.pause()
            elif op == "12": self.validate(); self.pause()
            elif op == "13": self.backup(); self.pause()
            elif op == "14": self.toggle_clear_screen(); self.pause()
            elif op == "0":
                self.stop_worker()
                break
            else:
                print("Opção inválida."); time.sleep(1)

def daemon_mode(config=None, items=None, log_path=LOG_FILE, log_level="INFO"):
    """Executa em primeiro plano sem menu; adequado a systemd, Termux ou nohup."""
    logger = configure_logging(log_path, log_level)
    if config is None or items is None:
        config, items = ensure_files()
    stop = threading.Event()

    def stop_signal(signum, _frame):
        logger.info("[ASW-SYS-001] Sinal %s recebido; encerrando.", signum)
        stop.set()

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    watcher = Watcher(config, items, stop, logger.info)
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        logger.info("[ASW-SYS-000] Monitoramento iniciado. PID=%s", os.getpid())
        watcher.loop()
    except Exception as exc:
        report_error(logger, "ASW-SYS-002", exc, "Falha fatal no monitoramento",
                     "O processo principal não conseguiu continuar.",
                     "configuração, I/O, rede, dependências ou falha inesperada")
        raise
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            logger.exception("[ASW-SYS-003] Não foi possível remover o PID.")


def run_once(config, items, logger):
    watcher = Watcher(config, items, threading.Event(), logger.info)
    errors = 0
    for item in items:
        try:
            watcher.run_once(item, ignore_schedule=True)
        except Exception as exc:
            errors += 1
            report_error(logger, "ASW-RUN-001", exc,
                         f"Falha no item {item.get('nome', '?')}",
                         "A busca/download desse item não foi concluída.",
                         "dados inválidos, autenticação, rede ou permissão de escrita")
    logger.info("[ASW-RUN-000] Execução concluída. Itens=%s Erros=%s", len(items), errors)
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(
        description="Amigos Share Watcher - monitor de buscas do Amigos Share Club")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--daemon", "--run", action="store_true",
                      help="executa continuamente sem menu (serviço do sistema)")
    mode.add_argument("--once", action="store_true",
                      help="executa uma rodada de todos os itens e encerra")
    mode.add_argument("--test", action="store_true",
                      help="testa autenticação e pesquisa no site")
    mode.add_argument("--test-email", action="store_true",
                      help="testa exclusivamente o envio SMTP")
    parser.add_argument("--log-file", default=str(LOG_FILE), help="arquivo de log")
    parser.add_argument("--log-level", default="INFO",
                        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))
    parser.add_argument("--interval-seconds", type=int,
                        help="sobrescreve o intervalo mínimo global de consultas")
    parser.add_argument("--request-delay", type=int,
                        help="sobrescreve a pausa entre consultas no ciclo")
    parser.add_argument("--download-dir", help="sobrescreve a pasta de downloads nesta execução")
    parser.add_argument("--no-email", action="store_true", help="desativa notificações por e-mail nesta execução")
    parser.add_argument("--no-telegram", action="store_true", help="desativa Telegram nesta execução")
    parser.add_argument("--clear-screen", dest="clear_screen", action="store_true")
    parser.add_argument("--no-clear-screen", dest="clear_screen", action="store_false")
    parser.set_defaults(clear_screen=None)
    args = parser.parse_args()

    logger = configure_logging(Path(args.log_file).expanduser(), args.log_level)
    try:
        config, items = ensure_files()
        if args.clear_screen is not None:
            config.setdefault("ui", {})["clear_screen"] = args.clear_screen
        if args.interval_seconds is not None:
            if args.interval_seconds < 60:
                raise ValueError("--interval-seconds deve ser pelo menos 60.")
            config.setdefault("scheduler", {})["minimum_interval_seconds"] = args.interval_seconds
        if args.request_delay is not None:
            if args.request_delay < 0:
                raise ValueError("--request-delay não pode ser negativo.")
            config.setdefault("scheduler", {})["request_delay_seconds"] = args.request_delay
        if args.download_dir:
            config.setdefault("downloads", {})["directory"] = str(Path(args.download_dir).expanduser())
        if args.no_email:
            config.setdefault("notifications", {}).setdefault("email", {})["enabled"] = False
        if args.no_telegram:
            config.setdefault("notifications", {}).setdefault("telegram", {})["enabled"] = False
        if args.daemon:
            daemon_mode(config, items, Path(args.log_file).expanduser(), args.log_level)
            return 0
        if args.once:
            return run_once(config, items, logger)
        if args.test_email:
            Notifier(config).test_email()
            logger.info("[ASW-MAIL-000] Teste SMTP concluído com sucesso.")
            return 0
        if args.test:
            client = SiteClient(config)
            client.login()
            logger.info("[ASW-SITE-000] Login OK. Resultados em /torrents: %s",
                        len(client.search({"q": "teste"})))
            return 0
        App().menu()
        return 0
    except KeyboardInterrupt:
        logger.warning("[ASW-SYS-004] Execução interrompida pelo usuário.")
        return 130
    except Exception as exc:
        report_error(logger, "ASW-FATAL-001", exc,
                     "Falha não tratada na inicialização/execução",
                     "O programa encerrou sem concluir a operação.",
                     "JSON, permissões, dependências, conectividade ou erro inesperado")
        print(f"Erro [ASW-FATAL-001]: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
