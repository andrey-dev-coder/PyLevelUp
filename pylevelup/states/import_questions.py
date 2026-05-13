from aiogram.fsm.state import State, StatesGroup


class ImportStates(StatesGroup):
    choosing_category = State()
    creating_category_key = State()
    creating_category_title = State()
    awaiting_file = State()
    confirming = State()
