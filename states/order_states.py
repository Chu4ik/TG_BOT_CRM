# states/order_states.py

from aiogram.fsm.state import State, StatesGroup

class OrderCreationStates(StatesGroup):
    """
    Состояния для процесса создания нового заказа.
    """
    waiting_for_client_selection = State()      # Ожидаем выбор клиента
    waiting_for_address_selection = State()     # Ожидаем выбор адреса
    waiting_for_new_address_input = State()     # <-- НОВОЕ СОСТОЯНИЕ: Ожидаем ввод нового адреса
    waiting_for_product_selection = State()     # Ожидаем выбор товара для добавления
    waiting_for_product_quantity = State()      # Ожидаем количество товара
    waiting_for_delivery_date = State()         # Ожидаем дату доставки
    confirming_order_item = State()             # Подтверждение позиции (добавить еще/завершить)
    confirming_final_order = State()            # Окончательное подтверждение заказа перед сохранением

class OrderEditingStates(StatesGroup): # <--- НОВЫЙ КЛАСС СОСТОЯНИЙ для редактирования
    waiting_for_my_order_selection = State()      # Ожидаем выбор заказа из списка "моих заказов"
    my_order_menu = State()                       # Главное меню редактирования конкретного заказа
    waiting_for_item_to_edit_quantity = State()   # Ожидаем выбор позиции для изменения количества
    waiting_for_new_quantity = State()            # Ожидаем новое количество
    waiting_for_item_to_delete = State()          # Ожидаем выбор позиции для удаления
    waiting_for_new_delivery_date = State()       # Ожидаем новую дату доставки
    confirming_delete_order = State()             # Подтверждение удаления заказа
    waiting_for_order_delete_confirmation = State()
    waiting_for_line_delete_confirmation = State()