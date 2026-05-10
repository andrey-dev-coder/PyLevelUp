from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    awaiting_query = State()
