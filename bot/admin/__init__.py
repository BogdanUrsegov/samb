from aiogram import Router

from bot.admin.filters import IsAdmin
from bot.admin.handlers.admin import router as admin_handlers_router
from bot.admin.handlers.admin import superadmin_router

admin_router = Router()
admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())
admin_router.include_router(admin_handlers_router)
admin_router.include_router(superadmin_router)
