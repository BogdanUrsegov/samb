import logging
import aiohttp

logger = logging.getLogger(__name__)


async def show_advert(user_id):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.gramads.net/ad/SendPost",
                headers={
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyNTA2OCIsImp0aSI6ImFlOWM1NjdkLTkxYmMtNGNiYi1iZjc3LTEzNTUyNDYwNzVlMiIsIm5hbWUiOiLQkNC90L7QvdC40LzQvdGL0LUg0YHQvtC-0LHRidC10L3QuNGPIiwiYm90aWQiOiIxNjcwMiIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL25hbWVpZGVudGlmaWVyIjoiMjUwNjgiLCJuYmYiOjE3NjI3ODU4NjUsImV4cCI6MTc2Mjk5NDY2NSwiaXNzIjoiU3R1Z25vdiIsImF1ZCI6IlVzZXJzIn0._LV9_rkr3aSMFfl71E2vFBw8ojFzMxO24N5ssSv-3hc",
                    "Content-Type": "application/json",
                },
                json={"SendToChatId": user_id},
            ) as response:
                print(response.content)
                if not response.ok:
                    logger.error("Gramads: %s" % str(await response.json()))
    except Exception as e:
        print(f"Gramads пост не был отправлен: {e}")
