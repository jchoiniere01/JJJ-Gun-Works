from __future__ import annotations

from app.sql_utils import TableMapping


INVENTORY_TABLES: dict[str, TableMapping] = {
    # Expected converted T-SQL table: dbo.InventoryItems
    "items": TableMapping(
        key="items",
        schema="dbo",
        table="InventoryItems",
        primary_key="InventoryItemID",
        allowed_columns=(
            "SKU",
            "Name",
            "Description",
            "CategoryID",
            "SupplierID",
            "Manufacturer",
            "Model",
            "Caliber",
            "Platform",
            "PartRole",
            "BuildType",
            "UnitCost",
            "UnitPrice",
            "QuantityOnHand",
            "QuantityReserved",
            "ReorderPoint",
            "IsActive",
            "RequiresFFL",
            "IsSerialized",
            "CreatedAt",
            "UpdatedAt",
        ),
        searchable_columns=("SKU", "Name", "Description", "Manufacturer", "Model", "PartRole", "BuildType"),
        default_order_by="Name",
    ),
    # Expected converted T-SQL table: dbo.PartCategories
    "categories": TableMapping(
        key="categories",
        schema="dbo",
        table="PartCategories",
        primary_key="CategoryID",
        allowed_columns=("Name", "Description", "ParentCategoryID", "IsActive", "CreatedAt", "UpdatedAt"),
        searchable_columns=("Name", "Description"),
        default_order_by="Name",
    ),
    # Expected converted T-SQL table: dbo.Suppliers
    "suppliers": TableMapping(
        key="suppliers",
        schema="dbo",
        table="Suppliers",
        primary_key="SupplierID",
        allowed_columns=("Name", "ContactName", "Email", "Phone", "Website", "IsActive", "CreatedAt", "UpdatedAt"),
        searchable_columns=("Name", "ContactName", "Email", "Phone"),
        default_order_by="Name",
    ),
    # Expected converted T-SQL table: dbo.StockMovements
    "stock_movements": TableMapping(
        key="stock_movements",
        schema="dbo",
        table="StockMovements",
        primary_key="StockMovementID",
        allowed_columns=(
            "InventoryItemID",
            "MovementType",
            "Quantity",
            "ReferenceType",
            "ReferenceID",
            "Notes",
            "CreatedAt",
            "CreatedBy",
        ),
        searchable_columns=("MovementType", "ReferenceType", "Notes", "CreatedBy"),
        default_order_by="CreatedAt",
    ),
}


RESERVATION_TABLES: dict[str, TableMapping] = {
    "orders": TableMapping(
        key="orders",
        schema="dbo",
        table="Orders",
        primary_key="OrderID",
        allowed_columns=(
            "CustomerName",
            "CustomerEmail",
            "CustomerPhone",
            "OrderStatus",
            "BuildType",
            "Notes",
            "CreatedAt",
            "UpdatedAt",
        ),
        searchable_columns=("CustomerName", "CustomerEmail", "CustomerPhone", "OrderStatus", "BuildType"),
        default_order_by="CreatedAt",
    ),
    "reservations": TableMapping(
        key="reservations",
        schema="dbo",
        table="OrderReservations",
        primary_key="ReservationID",
        allowed_columns=(
            "OrderID",
            "InventoryItemID",
            "Quantity",
            "ReservationStatus",
            "ExpiresAt",
            "CreatedAt",
            "UpdatedAt",
        ),
        searchable_columns=("ReservationStatus",),
        default_order_by="CreatedAt",
    ),
}


CONFIGURATOR_TABLE = INVENTORY_TABLES["items"]
