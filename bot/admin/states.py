from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_vip_user = State()
    waiting_for_vip_plan = State()
    waiting_for_remove_vip_user = State()
    waiting_for_delete_user = State()
    waiting_for_referral_name = State()
    waiting_for_referral_code = State()
    waiting_for_referral_price = State()
    waiting_for_referral_viewer = State()