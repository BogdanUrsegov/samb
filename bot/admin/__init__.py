from aiogram import Router

from bot.admin.handlers.admin import router as admin_handlers_router
from bot.admin.handlers.admin import superadmin_router
from bot.admin.handlers.referral_delete import router as referral_delete_router

admin_router = Router()
admin_router.include_router(admin_handlers_router)
admin_router.include_router(superadmin_router)
admin_router.include_router(referral_delete_router)
