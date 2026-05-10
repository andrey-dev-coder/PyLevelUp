from aiogram.fsm.state import State, StatesGroup


class ReportStates(StatesGroup):
    awaiting_reason = State()
