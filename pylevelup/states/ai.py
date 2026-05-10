from aiogram.fsm.state import State, StatesGroup


class AIStates(StatesGroup):
    awaiting_question = State()
