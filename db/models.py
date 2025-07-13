# db/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Employee(Base):
    __tablename__ = 'employees'
    employee_id = Column(Integer, primary_key=True)
    name = Column(String, index=True) # Добавляем индекс для поиска по имени
    role = Column(String)
    id_telegram = Column(BigInteger, unique=True, nullable=False) # Уже уникальный индекс

    orders = relationship("Order", back_populates="employee")

class Client(Base):
    __tablename__ = 'clients'
    client_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True) # Добавляем индекс для поиска по имени клиента

    addresses = relationship("Address", back_populates="client")
    orders = relationship("Order", back_populates="client")
    client_payments = relationship("ClientPayment", back_populates="client")

class Address(Base):
    __tablename__ = 'addresses'
    address_id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.client_id'), index=True) # Индекс для быстрого поиска адресов клиента
    address_text = Column(String, nullable=False)

    client = relationship("Client", back_populates="addresses")
    orders = relationship("Order", back_populates="address")

class Supplier(Base):
    __tablename__ = 'suppliers'
    supplier_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True) # Индекс для поиска по имени поставщика

    products = relationship("Product", back_populates="supplier")
    incoming_deliveries = relationship("IncomingDelivery", back_populates="supplier")
    supplier_invoices = relationship("SupplierInvoice", back_populates="supplier")
    supplier_payments = relationship("SupplierPayment", back_populates="supplier")

class Category(Base):
    __tablename__ = 'categories'
    category_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True) # Категории, скорее всего, уникальны

    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = 'products'
    product_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True) # Индекс для поиска по названию продукта
    category_id = Column(Integer, ForeignKey('categories.category_id'), index=True) # Индекс для фильтрации по категории
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True) # Индекс для фильтрации по поставщику
    price = Column(Float, nullable=False)
    cost_per_unit = Column(Float, nullable=False)
    description = Column(String)

    category = relationship("Category", back_populates="products")
    supplier = relationship("Supplier", back_populates="products")
    order_lines = relationship("OrderLine", back_populates="product")
    incoming_deliveries = relationship("IncomingDelivery", back_populates="product")
    inventory_movements = relationship("InventoryMovement", back_populates="product")
    stock_item = relationship("Stock", uselist=False, back_populates="product")

class Stock(Base):
    __tablename__ = 'stock'
    product_id = Column(Integer, ForeignKey('products.product_id'), primary_key=True)
    quantity = Column(Float, nullable=False, default=0.0)

    product = relationship("Product", back_populates="stock_item")

class IncomingDelivery(Base):
    __tablename__ = 'incoming_deliveries'
    delivery_id = Column(Integer, primary_key=True)
    delivery_date = Column(DateTime, nullable=False, index=True) # Индекс для отчетов по датам
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    supplier_invoice_id = Column(Integer, ForeignKey('supplier_invoices.supplier_invoice_id'), nullable=True, index=True)

    supplier = relationship("Supplier", back_populates="incoming_deliveries")
    product = relationship("Product", back_populates="incoming_deliveries")
    supplier_invoice = relationship("SupplierInvoice", back_populates="incoming_deliveries")

class InventoryMovement(Base):
    __tablename__ = 'inventory_movements'
    movement_id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    movement_type = Column(String, nullable=False, index=True) # Индекс для фильтрации по типу движения
    quantity_change = Column(Float, nullable=False)
    movement_date = Column(DateTime, nullable=False, index=True) # Индекс для отчетов по датам
    source_document_type = Column(String, nullable=False, index=True)
    source_document_id = Column(Integer, nullable=True, index=True)
    description = Column(String)
    unit_cost = Column(Float, nullable=False)

    product = relationship("Product", back_populates="inventory_movements")

    __table_args__ = (
        Index('idx_inventory_movement_product_date', 'product_id', 'movement_date'),
    )

class Order(Base):
    __tablename__ = 'orders'
    order_id = Column(Integer, primary_key=True)
    invoice_number = Column(String, unique=True, nullable=True) # Уникальный индекс для номера накладной
    order_date = Column(DateTime, nullable=False, index=True)
    delivery_date = Column(DateTime, index=True)
    employee_id = Column(Integer, ForeignKey('employees.employee_id'), index=True)
    client_id = Column(Integer, ForeignKey('clients.client_id'), index=True)
    address_id = Column(Integer, ForeignKey('addresses.address_id'), index=True)
    total_amount = Column(Float, nullable=False)
    status = Column(String, nullable=False, default='draft', index=True) # Индекс для фильтрации по статусу
    confirmation_date = Column(DateTime, index=True)
    payment_status = Column(String, nullable=False, default='unpaid', index=True) # Индекс для фильтрации по статусу оплаты
    amount_paid = Column(Float, nullable=False, default=0.0)
    due_date = Column(DateTime, index=True)
    actual_payment_date = Column(DateTime, index=True)

    employee = relationship("Employee", back_populates="orders")
    client = relationship("Client", back_populates="orders")
    address = relationship("Address", back_populates="orders")
    order_lines = relationship("OrderLine", back_populates="order")
    client_payments = relationship("ClientPayment", back_populates="order")

    __table_args__ = (
        Index('idx_order_client_status', 'client_id', 'status'),
    )

class OrderLine(Base):
    __tablename__ = 'order_lines'
    order_line_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.order_id'), index=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)

    order = relationship("Order", back_populates="order_lines")
    product = relationship("Product", back_populates="order_lines")

class ClientPayment(Base):
    __tablename__ = 'client_payments'
    payment_id = Column(Integer, primary_key=True)
    payment_date = Column(DateTime, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey('clients.client_id'), index=True)
    order_id = Column(Integer, ForeignKey('orders.order_id'), index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String, index=True)
    description = Column(String)
    payment_type = Column(String, index=True)

    client = relationship("Client", back_populates="client_payments")
    order = relationship("Order", back_populates="client_payments")

class SupplierInvoice(Base):
    __tablename__ = 'supplier_invoices'
    supplier_invoice_id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True)
    invoice_number = Column(String, unique=True) # Уникальный индекс
    invoice_date = Column(DateTime, nullable=False, index=True)
    due_date = Column(DateTime, index=True)
    total_amount = Column(Float, nullable=False)
    amount_paid = Column(Float, nullable=False, default=0.0)
    payment_status = Column(String, default='unpaid', index=True)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.now)

    supplier = relationship("Supplier", back_populates="supplier_invoices")
    incoming_deliveries = relationship("IncomingDelivery", back_populates="supplier_invoice")
    supplier_payments = relationship("SupplierPayment", back_populates="supplier_invoice")

class SupplierPayment(Base):
    __tablename__ = 'supplier_payments'
    payment_id = Column(Integer, primary_key=True)
    payment_date = Column(DateTime, nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True)
    delivery_id = Column(Integer, ForeignKey('incoming_deliveries.delivery_id'), nullable=True, index=True)
    amount = Column(Float, nullable=False)
    payment_method = Column(String, index=True)
    supplier_invoice_id = Column(Integer, ForeignKey('supplier_invoices.supplier_invoice_id'), nullable=True, index=True)
    description = Column(String)

    supplier = relationship("Supplier", back_populates="supplier_payments")
    supplier_invoice = relationship("SupplierInvoice", back_populates="supplier_payments")

class CashFlow(Base):
    __tablename__ = 'cash_flow'
    transaction_id = Column(Integer, primary_key=True)
    transaction_date = Column(DateTime, nullable=False, index=True)
    transaction_type = Column(String, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    description = Column(String)
    source_type = Column(String, index=True)
    source_id = Column(Integer, index=True)
    current_balance = Column(Float)

    # Композитные индексы, если нужны для ускорения специфических запросов
    # Например, для быстрого поиска движений по складу по типу и дате
    __table_args__ = (
        Index('idx_cash_flow_source', 'source_type', 'source_id'),
    )