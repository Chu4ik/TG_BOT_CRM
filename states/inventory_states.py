# states/inventory_states.py

from aiogram.fsm.state import State, StatesGroup

class InventoryReceiptStates(StatesGroup):
    """
    Состояния для процесса приема товара на склад.
    """
    waiting_for_supplier_selection = State()  # Ожидаем выбор поставщика
    waiting_for_invoice_date = State()       # <-- НОВОЕ СОСТОЯНИЕ: Ожидаем дату накладной
    waiting_for_invoice_number = State()     # Ожидаем номер накладной
    waiting_for_product_selection = State()  # Ожидаем выбор товара
    waiting_for_product_quantity = State()   # Ожидаем количество товара
    waiting_for_unit_cost = State()          # Ожидаем себестоимость за единицу
    confirming_line_item = State()           # Подтверждение позиции (добавить еще/завершить)
    confirming_receipt = State()             # Окончательное подтверждение всей накладной