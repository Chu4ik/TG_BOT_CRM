# db/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, BigInteger
from sqlalchemy import Computed, Numeric # Добавлено Numeric и Computed
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal # Добавляем импорт Decimal для значений по умолчанию

Base = declarative_base()

class Employee(Base):
    __tablename__ = 'employees'
    employee_id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    role = Column(String)
    id_telegram = Column(BigInteger, unique=True, nullable=False)

    orders = relationship("Order", back_populates="employee")

class Client(Base):
    __tablename__ = 'clients'
    client_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)

    addresses = relationship("Address", back_populates="client")
    orders = relationship("Order", back_populates="client")
    client_payments = relationship("ClientPayment", back_populates="client")

class Address(Base):
    __tablename__ = 'addresses'
    address_id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.client_id'), index=True)
    address_text = Column(String, nullable=False)

    client = relationship("Client", back_populates="addresses")
    orders = relationship("Order", back_populates="address")

class Supplier(Base):
    __tablename__ = 'suppliers'
    supplier_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)

    products = relationship("Product", back_populates="supplier")
    incoming_deliveries = relationship("IncomingDelivery", back_populates="supplier")
    supplier_invoices = relationship("SupplierInvoice", back_populates="supplier")
    supplier_payments = relationship("SupplierPayment", back_populates="supplier")

class Category(Base):
    __tablename__ = 'categories'
    category_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = 'products'
    product_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey('categories.category_id'), index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True)
    # ✅ ИСПРАВЛЕНИЕ: price и cost_per_unit на Numeric
    price = Column(Numeric(10, 2), nullable=False)
    cost_per_unit = Column(Numeric(10, 2), nullable=False)
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
    # ✅ ИСПРАВЛЕНИЕ: quantity на Numeric(10,2) - если в БД может быть дробным
    quantity = Column(Numeric(10, 2), nullable=False, default=Decimal('0.00')) # Default для Numeric

    product = relationship("Product", back_populates="stock_item")

class IncomingDelivery(Base):
    __tablename__ = 'incoming_deliveries'
    delivery_id = Column(Integer, primary_key=True)
    delivery_date = Column(DateTime, nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    # ✅ ИСПРАВЛЕНИЕ: quantity, unit_cost, total_cost на Numeric
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_cost = Column(Numeric(10, 2), nullable=False)
    total_cost = Column(Numeric(12, 2), nullable=False)
    supplier_invoice_id = Column(Integer, ForeignKey('supplier_invoices.supplier_invoice_id'), nullable=True, index=True)

    supplier = relationship("Supplier", back_populates="incoming_deliveries")
    product = relationship("Product", back_populates="incoming_deliveries")
    supplier_invoice = relationship("SupplierInvoice", back_populates="incoming_deliveries")

class InventoryMovement(Base):
    __tablename__ = 'inventory_movements'
    movement_id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.product_id'), index=True)
    movement_type = Column(String, nullable=False, index=True)
    # ✅ ИСПРАВЛЕНИЕ: quantity_change, unit_cost на Numeric
    quantity_change = Column(Numeric(10, 2), nullable=False)
    movement_date = Column(DateTime, nullable=False, index=True)
    source_document_type = Column(String, nullable=False, index=True)
    source_document_id = Column(Integer, nullable=True, index=True)
    description = Column(String)
    unit_cost = Column(Numeric(10, 2), nullable=False)

    product = relationship("Product", back_populates="inventory_movements")

    __table_args__ = (
        Index('idx_inventory_movement_product_date', 'product_id', 'movement_date'),
    )

class Order(Base):
    __tablename__ = 'orders'
    order_id = Column(Integer, primary_key=True)
    invoice_number = Column(String, unique=True, nullable=True) # Должен быть NULLABLE для начала
    order_date = Column(DateTime, nullable=False, index=True)
    delivery_date = Column(DateTime, index=True)
    employee_id = Column(Integer, ForeignKey('employees.employee_id'), index=True)
    client_id = Column(Integer, ForeignKey('clients.client_id'), index=True)
    address_id = Column(Integer, ForeignKey('addresses.address_id'), index=True)
    # ✅ ИСПРАВЛЕНИЕ: total_amount на Numeric
    total_amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String, nullable=False, default='draft', index=True)
    confirmation_date = Column(DateTime, index=True)
    payment_status = Column(String, nullable=False, default='unpaid', index=True)
    # ✅ ИСПРАВЛЕНИЕ: amount_paid на Numeric
    amount_paid = Column(Numeric(12, 2), nullable=False, default=Decimal('0.00')) # Default для Numeric
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
    order_line_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey('orders.order_id'), nullable=False)
    product_id = Column(Integer, ForeignKey('products.product_id'), nullable=False)
    # ✅ ИСПРАВЛЕНИЕ: quantity на Numeric(10,2) - если в БД может быть дробным, иначе Integer
    quantity = Column(Numeric(10, 2), nullable=False) # Если в БД int, то здесь Integer
    # ✅ ИСПРАВЛЕНИЕ: unit_price на Numeric(10,2)
    unit_price = Column(Numeric(10, 2), nullable=False)
    # ✅ ИСПРАВЛЕНИЕ: line_total на Numeric(12,2) и Computed
    line_total = Column(Numeric(12, 2), Computed("quantity * unit_price"))

    order = relationship("Order", back_populates="order_lines")
    product = relationship("Product")

class ClientPayment(Base):
    __tablename__ = 'client_payments'
    payment_id = Column(Integer, primary_key=True)
    payment_date = Column(DateTime, nullable=False, index=True)
    client_id = Column(Integer, ForeignKey('clients.client_id'), index=True)
    order_id = Column(Integer, ForeignKey('orders.order_id'), index=True)
    # ✅ ИСПРАВЛЕНИЕ: amount на Numeric
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String, index=True)
    description = Column(String)
    payment_type = Column(String, index=True)

    client = relationship("Client", back_populates="client_payments")
    order = relationship("Order", back_populates="client_payments")

class SupplierInvoice(Base):
    __tablename__ = 'supplier_invoices'
    supplier_invoice_id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey('suppliers.supplier_id'), index=True)
    invoice_number = Column(String, unique=True, nullable=True) # Сделал nullable=True для удобства
    invoice_date = Column(DateTime, nullable=False, index=True)
    due_date = Column(DateTime, index=True)
    # ✅ ИСПРАВЛЕНИЕ: total_amount, amount_paid на Numeric
    total_amount = Column(Numeric(12, 2), nullable=False)
    amount_paid = Column(Numeric(12, 2), nullable=False, default=Decimal('0.00'))
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
    # ✅ ИСПРАВЛЕНИЕ: amount на Numeric
    amount = Column(Numeric(12, 2), nullable=False)
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
    # ✅ ИСПРАВЛЕНИЕ: amount, current_balance на Numeric
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String)
    source_type = Column(String, index=True)
    source_id = Column(Integer, index=True)
    current_balance = Column(Numeric(12, 2))

    __table_args__ = (
        Index('idx_cash_flow_source', 'source_type', 'source_id'),
    )