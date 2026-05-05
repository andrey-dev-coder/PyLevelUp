from aiogram.fsm.state import State, StatesGroup


class MockStates(StatesGroup):
    in_session = State()
