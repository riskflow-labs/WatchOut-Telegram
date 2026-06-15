from __future__ import annotations

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.core.config import settings
from app.models import TelegramAccount
from app.telegram.utils import parse_proxy, session_path


class PasswordRequired(Exception):
    pass


def build_client(account: TelegramAccount) -> TelegramClient:
    return TelegramClient(
        session_path(settings.session_dir, account.session_name),
        account.api_id,
        account.api_hash,
        proxy=parse_proxy(account.proxy_url),
    )


async def send_login_code(account: TelegramAccount) -> str:
    client = build_client(account)
    await client.connect()
    try:
        sent = await client.send_code_request(account.phone)
        return sent.phone_code_hash
    finally:
        await client.disconnect()


async def verify_login_code(account: TelegramAccount, code: str, phone_code_hash: str) -> None:
    client = build_client(account)
    await client.connect()
    try:
        try:
            await client.sign_in(account.phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError as exc:
            raise PasswordRequired() from exc
    finally:
        await client.disconnect()


async def verify_password(account: TelegramAccount, password: str) -> None:
    client = build_client(account)
    await client.connect()
    try:
        await client.sign_in(password=password)
    finally:
        await client.disconnect()
