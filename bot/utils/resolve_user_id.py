import os
from bot.database.utils import get_user_id_by_custom_start_param
from aiogram.utils.deep_linking import decode_payload
from hashids import Hashids

# Инициализация Hashids (соль из .env)
HASHIDS_SALT = os.getenv("HASHIDS_SALT", "12345")
hashids = Hashids(salt=HASHIDS_SALT, min_length=6)


async def resolve_user_id(payload: str) -> int | None:
    """
    Резолвит ID получателя по цепочке фоллбэков:
    1. БД (кастомный параметр) -> 2. Hashids -> 3. decode_payload -> 4. Прямой int.
    """
    # 1. Ищем в БД
    db_id = await get_user_id_by_custom_start_param(payload)
    if db_id is not None:
        return int(db_id)

    # 2. Пытаемся расшифровать через Hashids
    decoded_hash = hashids.decode(payload)
    if decoded_hash:
        return decoded_hash[0]

    # 3. Пытаемся расшифровать через кастомный decode_payload
    try:
        decoded_payload = decode_payload(payload)
        if decoded_payload and decoded_payload.isdigit():
            return int(decoded_payload)
    except Exception:
        pass  # Игнорируем ошибки, переходим к шагу 4

    # 4. Прямое преобразование в int (для старых ссылок)
    try:
        return int(payload)
    except (ValueError, TypeError):
        return None