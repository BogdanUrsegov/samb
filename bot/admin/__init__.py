from aiogram import Router
from bot.admin.handlers import callbacks, commands, fsm

# Создаем главный роутер админки
admin_router = Router()

# Подключаем все роутеры админки
admin_router.include_router(callbacks.router)
admin_router.include_router(commands.router)
admin_router.include_router(fsm.router)