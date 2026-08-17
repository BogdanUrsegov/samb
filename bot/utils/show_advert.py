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
                    f"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyNTA2OCIsImp0aSI6ImJkODAxYjE0LWE4ZTUtNDg1MC1hNzNjLTQyN2M5ODhjNzc1YiIsIm5hbWUiOiLQkNC90L7QvdC40LzQvdGL0LUg0YHQvtC-0LHRidC10L3QuNGPIiwiYm90aWQiOiIyMTY4OSIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL25hbWVpZGVudGlmaWVyIjoiMjUwNjgiLCJuYmYiOjE3ODY5MjYxNDYsImV4cCI6MTc4NzEzNDk0NiwiaXNzIjoiU3R1Z25vdiIsImF1ZCI6IlVzZXJzIn0.PWTyLqVE2hoioVAxCBLZM9Mu-dlALMf1sTuoRCO_n4A",
                    "Content-Type": "application/json",
                },
                json={"SendToChatId": user_id},
            ) as response:
                if not response.ok:
                    logger.error("Gramads: %s" % str(await response.json()))
    except Exception as e:
        print(f"Gramads пост не был отправлен: {e}")
