from aiogram import Router
from bot.admin.handlers import callbacks, commands, fsm, referrals, admins
from bot.admin.filters import IsAdmin

# Создаем главный роутер админки
admin_router = Router()

# Все handlers админки доступны только пользователям из таблицы admins.
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())

# Подключаем все роутеры админки
admin_router.include_router(admins.router)
admin_router.include_router(callbacks.router)
admin_router.include_router(commands.router)
admin_router.include_router(fsm.router)
admin_router.include_router(referrals.router)
