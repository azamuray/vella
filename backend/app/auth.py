import os
import json
import hashlib
import hmac
from urllib.parse import parse_qsl
from typing import Optional

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


def validate_telegram_data(init_data: str) -> Optional[dict]:
    """
    Validate Telegram WebApp init data using HMAC-SHA256.
    Returns user dict if valid, None otherwise.
    """
    if not init_data:
        return None

    if not BOT_TOKEN:
        # Dev mode - parse without validation
        try:
            data = dict(parse_qsl(init_data))
            if "user" in data:
                return json.loads(data["user"])
        except Exception:
            pass
        return None

    try:
        data = dict(parse_qsl(init_data))
        received_hash = data.pop("hash", "")

        if not received_hash:
            return None

        # Create data check string (sorted alphabetically)
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items())
        )

        # Create secret key from bot token
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        # Calculate hash
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash == received_hash:
            return json.loads(data.get("user", "{}"))
    except Exception:
        pass

    return None
