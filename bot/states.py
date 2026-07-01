# bot/states.py

from aiogram.fsm.state import State, StatesGroup


class AnonymousMessaging(StatesGroup):
    """
    Состояния для управления процессом анонимной переписки.

    waiting_for_message - состояние ожидания сообщения для анонимной отправки
    waiting_for_reply - состояние ожидания ответа на анонимное сообщение
    """

    waiting_for_message = State()
    waiting_for_reply = State()