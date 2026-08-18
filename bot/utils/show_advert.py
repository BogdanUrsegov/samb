import logging
import aiohttp
from bot.config import settings

logger = logging.getLogger(__name__)

GRAMADS_API_KEY = settings.gramads_api_key


async def show_advert(user_id):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.gramads.net/ad/SendPost",
                headers={
                    "Authorization": f"Bearer {GRAMADS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"SendToChatId": user_id},
            ) as response:
                if not response.ok:
                    logger.error("Gramads: %s" % str(await response.json()))
    except Exception as e:
        print(f"Gramads пост не был отправлен: {e}")
