from bot.create_bot import hashids

async def create_link(user_id, bot_username):
    ref_code = hashids.encode(user_id)
    return f"https://t.me/{bot_username}?start={ref_code}" 