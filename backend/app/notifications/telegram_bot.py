from __future__ import annotations

import json
import http.client
import ssl
import urllib.parse
import urllib.request
from urllib.error import URLError

import socks

from app.models import NotificationChannel, TelegramMessage
from app.notifications.message_format import html_notification_text
from app.services.json_utils import loads_dict


def send_telegram_bot(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    token = str(config.get("bot_token") or "")
    chat_ids = config.get("chat_ids") or []
    proxy_url = str(config.get("proxy_url") or "").strip()
    if isinstance(chat_ids, str):
        chat_ids = [chat_ids]
    if not token or not chat_ids:
        raise RuntimeError("Telegram Bot notification requires bot_token and chat_ids")

    text = html_notification_text(message)
    for chat_id in chat_ids:
        try:
            _send_telegram_message(token, str(chat_id), text, proxy_url)
        except URLError as exc:
            if not proxy_url or not _is_proxy_ssl_eof(exc):
                raise
            _send_telegram_message(token, str(chat_id), text, "")


def _send_telegram_message(token: str, chat_id: str, text: str, proxy_url: str) -> None:
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        method="POST",
    )
    opener = _proxy_opener(proxy_url) if proxy_url else urllib.request.build_opener()
    with opener.open(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram Bot sendMessage failed: {payload}")


def _is_proxy_ssl_eof(exc: URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLError) and "UNEXPECTED_EOF_WHILE_READING" in str(reason):
        return True
    return "UNEXPECTED_EOF_WHILE_READING" in str(exc)


def _proxy_opener(proxy_url: str) -> urllib.request.OpenerDirector:
    parsed = urllib.parse.urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    proxy_types = {
        "socks5": socks.PROXY_TYPE_SOCKS5,
        "socks5h": socks.PROXY_TYPE_SOCKS5,
        "socks4": socks.PROXY_TYPE_SOCKS4,
        "http": socks.PROXY_TYPE_HTTP,
        "https": socks.PROXY_TYPE_HTTP,
    }
    if scheme not in proxy_types or not parsed.hostname or not parsed.port:
        raise RuntimeError("Telegram Bot proxy_url must be like socks5://127.0.0.1:1080")

    username = urllib.parse.unquote(parsed.username) if parsed.username else None
    password = urllib.parse.unquote(parsed.password) if parsed.password else None

    class ProxyHTTPSConnection(http.client.HTTPSConnection):
        def connect(self) -> None:
            self.sock = socks.create_connection(
                (self.host, self.port),
                timeout=self.timeout,
                proxy_type=proxy_types[scheme],
                proxy_addr=parsed.hostname,
                proxy_port=parsed.port,
                proxy_username=username,
                proxy_password=password,
                proxy_rdns=scheme in {"socks5", "socks5h"},
            )
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

    class SocksHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):  # noqa: N802
            return self.do_open(ProxyHTTPSConnection, req)

    return urllib.request.build_opener(SocksHTTPSHandler)
