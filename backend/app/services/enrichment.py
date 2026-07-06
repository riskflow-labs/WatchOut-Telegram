from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from app.models import TelegramMessage
from app.services.intelligence_settings import effective_translation_target


def translate_text(
    text: str,
    settings: dict[str, object],
    *,
    target_language: str | None = None,
) -> dict[str, str]:
    translation = settings.get("translation") or {}
    if not isinstance(translation, dict):
        return {
            "translated_content": "",
            "translation_status": "failed",
            "translation_engine": "",
            "language": "",
            "desc": "translation settings are invalid",
        }

    content = (text or "").strip()
    if not content:
        return {
            "translated_content": "",
            "translation_status": "skipped",
            "translation_engine": "",
            "language": "",
            "desc": "empty text",
        }

    detected = _detect_language(content)
    resolved_target = (target_language or "").strip().lower()
    if not resolved_target or resolved_target == "auto":
        resolved_target = effective_translation_target(settings)
    if detected != "auto" and detected.lower().startswith(resolved_target.lower()):
        return {
            "translated_content": "",
            "translation_status": "skipped",
            "translation_engine": str(translation.get("engine") or ""),
            "language": detected,
            "desc": "source language matches target language",
        }

    try:
        engine = _translation_engine(translation.get("engine"))
        if engine == "baidu":
            try:
                translated, detected_language = _translate_baidu(
                    content,
                    app_id=str(translation.get("baidu_app_id") or ""),
                    secret_key=str(translation.get("baidu_secret_key") or ""),
                    source_language=detected or "auto",
                    target_language=resolved_target,
                )
            except TranslationProviderError as exc:
                if exc.code == "58001":
                    tencent_secret_id = str(translation.get("tencent_secret_id") or "").strip()
                    tencent_secret_key = str(translation.get("tencent_secret_key") or "").strip()
                    if tencent_secret_id and tencent_secret_key:
                        translated, detected_language = _translate_tencent(
                            content,
                            secret_id=tencent_secret_id,
                            secret_key=tencent_secret_key,
                            region=str(translation.get("tencent_region") or "ap-guangzhou"),
                            source_language=detected or "auto",
                            target_language=resolved_target,
                        )
                        return {
                            "translated_content": translated,
                            "translation_status": "translated",
                            "translation_engine": "tencent",
                            "language": detected_language or detected or "",
                            "desc": "百度当前不支持该语言方向，已自动切换腾讯云翻译。",
                        }
                raise
            return {
                "translated_content": translated,
                "translation_status": "translated",
                "translation_engine": "baidu",
                "language": detected_language or detected or "",
                "desc": "",
            }
        if engine == "tencent":
            translated, detected_language = _translate_tencent(
                content,
                secret_id=str(translation.get("tencent_secret_id") or ""),
                secret_key=str(translation.get("tencent_secret_key") or ""),
                region=str(translation.get("tencent_region") or "ap-guangzhou"),
                source_language=detected or "auto",
                target_language=resolved_target,
            )
            return {
                "translated_content": translated,
                "translation_status": "translated",
                "translation_engine": "tencent",
                "language": detected_language or detected or "",
                "desc": "",
            }
        return {
            "translated_content": "",
            "translation_status": "unsupported",
            "translation_engine": str(translation.get("engine") or ""),
            "language": detected,
            "desc": f"unsupported translation engine: {translation.get('engine') or ''}",
        }
    except TranslationProviderError as exc:
        return {
            "translated_content": "",
            "translation_status": "failed",
            "translation_engine": _translation_engine(translation.get("engine")) or str(translation.get("engine") or ""),
            "language": detected,
            "desc": exc.message,
        }
    except HTTPError as exc:
        desc = "translation failed"
        if exc.code == 403:
            desc = "translation failed: 翻译服务拒绝访问，请检查接口密钥、权限或服务地址。"
        elif exc.code == 400:
            desc = "translation failed: 翻译请求参数无效，请检查源语言、目标语言和密钥配置。"
        elif exc.code == 58001:
            desc = "translation failed: 当前翻译引擎不支持该语言方向。土耳其语请优先使用腾讯云，或更换支持该语种的接口。"
        else:
            desc = f"translation failed: HTTP {exc.code}"
        return {
            "translated_content": "",
            "translation_status": "failed",
            "translation_engine": str(translation.get("engine") or ""),
            "language": detected,
            "desc": desc,
        }
    except URLError as exc:
        return {
            "translated_content": "",
            "translation_status": "failed",
            "translation_engine": str(translation.get("engine") or ""),
            "language": detected,
            "desc": f"translation failed: 无法连接翻译服务，请检查网络或服务配置。{exc.reason}",
        }
    except Exception as exc:
        return {
            "translated_content": "",
            "translation_status": "failed",
            "translation_engine": str(translation.get("engine") or ""),
            "language": detected,
            "desc": f"translation failed: {exc}",
        }


def translate_message_text(
    message: TelegramMessage,
    settings: dict[str, object],
    *,
    target_language: str | None = None,
) -> TelegramMessage:
    result = translate_text(message.content or "", settings, target_language=target_language)
    message.translated_content = result["translated_content"]
    message.translation_status = result["translation_status"]
    message.translation_engine = result["translation_engine"]
    message.language = result["language"]
    message.desc = result["desc"]
    return message


class TranslationProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _translation_engine(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "baidu": "baidu",
        "baidu_cloud": "baidu",
        "baidu_translate": "baidu",
        "baidu_translation": "baidu",
        "百度": "baidu",
        "百度云": "baidu",
        "百度云翻译": "baidu",
        "tencent": "tencent",
        "tencent_cloud": "tencent",
        "tencent_translate": "tencent",
        "tmt": "tencent",
        "腾讯": "tencent",
        "腾讯云": "tencent",
        "腾讯云机器翻译": "tencent",
    }
    return aliases.get(normalized, normalized or "baidu")


def _translate_baidu(
    text: str,
    *,
    app_id: str,
    secret_key: str,
    source_language: str,
    target_language: str,
) -> tuple[str, str]:
    if not app_id or not secret_key:
        raise RuntimeError("百度翻译 APP ID 和密钥不能为空")
    salt = str(int(time.time() * 1000))
    source = _baidu_language_code(source_language or "auto")
    target = _baidu_language_code(target_language)
    sign_text = f"{app_id}{text}{salt}{secret_key}"
    sign = hashlib.md5(sign_text.encode("utf-8")).hexdigest()
    payload = urllib.parse.urlencode(
        {
            "q": text,
            "from": source,
            "to": target,
            "appid": app_id,
            "salt": salt,
            "sign": sign,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://fanyi-api.baidu.com/api/trans/vip/translate",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("error_code"):
        code = str(data.get("error_code") or "")
        raise TranslationProviderError(code, f"百度翻译失败 {code}: {data.get('error_msg') or data}")
    results = data.get("trans_result") or []
    translated = "\n".join(str(item.get("dst") or "") for item in results).strip()
    if not translated:
        raise RuntimeError(f"百度翻译未返回译文: {data}")
    return translated, str(data.get("from") or source_language or "")


def _translate_tencent(
    text: str,
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    source_language: str,
    target_language: str,
) -> tuple[str, str]:
    if not secret_id or not secret_key:
        raise RuntimeError("腾讯云 SecretId 和 SecretKey 不能为空")
    payload = json.dumps(
        {
            "SourceText": text,
            "Source": _tencent_language_code(source_language or "auto"),
            "Target": _tencent_language_code(target_language),
            "ProjectId": 0,
        },
        ensure_ascii=False,
    )
    timestamp = int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    host = "tmt.tencentcloudapi.com"
    service = "tmt"
    algorithm = "TC3-HMAC-SHA256"
    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\nx-tc-action:texttranslate\n"
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, hashed_payload]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            str(timestamp),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    secret_date = _hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac_sha256(secret_date, service)
    secret_signing = _hmac_sha256(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    request = urllib.request.Request(
        f"https://{host}/",
        data=payload.encode("utf-8"),
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": "TextTranslate",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2018-03-21",
            "X-TC-Region": region or "ap-guangzhou",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    response_data = data.get("Response") or {}
    if response_data.get("Error"):
        error = response_data["Error"]
        raise TranslationProviderError(str(error.get("Code") or ""), f"腾讯云翻译失败 {error.get('Code')}: {error.get('Message')}")
    translated = str(response_data.get("TargetText") or "")
    if not translated:
        raise RuntimeError(f"腾讯云翻译未返回译文: {data}")
    return translated, str(response_data.get("Source") or source_language or "")


def _hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _baidu_language_code(language: str) -> str:
    lowered = (language or "").strip().lower().replace("_", "-")
    if lowered in {"zh", "zh-cn", "zh-hans", "chinese"}:
        return "zh"
    if lowered in {"zh-tw", "zh-hant", "cht"}:
        return "cht"
    if lowered in {"ja", "jp", "japanese"}:
        return "jp"
    if lowered in {"ko", "kor", "korean"}:
        return "kor"
    return lowered or "auto"


def _tencent_language_code(language: str) -> str:
    lowered = (language or "").strip().lower().replace("_", "-")
    if lowered in {"zh", "zh-cn", "zh-hans", "chinese"}:
        return "zh"
    if lowered in {"zh-tw", "zh-hant", "cht"}:
        return "zh-TW"
    if lowered in {"ja", "jp", "japanese"}:
        return "ja"
    if lowered in {"ko", "kor", "korean"}:
        return "ko"
    return lowered or "auto"


def _detect_language(text: str) -> str:
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    japanese_chars = sum(1 for char in text if "\u3040" <= char <= "\u30ff")
    korean_chars = sum(1 for char in text if "\uac00" <= char <= "\ud7af")
    cyrillic_chars = sum(1 for char in text if "\u0400" <= char <= "\u04ff")
    arabic_chars = sum(1 for char in text if "\u0600" <= char <= "\u06ff")
    turkish_chars = sum(1 for char in text.lower() if char in "çğıöşü")
    if japanese_chars >= 2:
        return "ja"
    if korean_chars >= 2:
        return "ko"
    if chinese_chars >= max(2, len(text) * 0.1):
        return "zh"
    if cyrillic_chars >= 2:
        return "ru"
    if arabic_chars >= 2:
        return "ar"
    if turkish_chars >= 1:
        return "tr"
    return "auto"
