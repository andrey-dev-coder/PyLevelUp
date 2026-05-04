from aiogram.fsm.state import State, StatesGroup


class TestStates(StatesGroup):
    in_session = State()
