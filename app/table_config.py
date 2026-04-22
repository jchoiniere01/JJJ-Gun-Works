from __future__ import annotations

from app.sql_utils import TableMapping


# -----------------------------------------------------------------------------
# Postgres schema/column names.
#
# The SQL migration scripts in ``sql/postgres/`` create these tables in the
# ``public`` schema with ``snake_case`` column names. API responses for
# list/get/create/update/delete use the same snake_case keys (psycopg's
# ``dict_row`` factory passes DB column names through).
#
# If you need to preserve the original SQL Server PascalCase API contract
# for existing frontends, add column aliases in ``crud_service.py`` rather
# than reintroducing mixed-case identifiers here.
# -----------------------------------------------------------------------------


INVENTORY_TABLES: dict[str, TableMapping] = {
    # Postgres table: public.inventory_items (was dbo.InventoryItems)
    "items": TableMapping(
        key="items",
        schema="public",
        table="inventory_items",
        primary_key="inventory_item_id",
        allowed_columns=(
            "sku",
            "name",
            "description",
            "category_id",
            "supplier_id",
            "manufacturer",
            "model",
            "caliber",
            "platform",
            "part_role",
            "build_type",
            "unit_cost",
            "unit_price",
            "quantity_on_hand",
            "quantity_reserved",
            "reorder_point",
            "is_active",
            "requires_ffl",
            "is_serialized",
            "created_at",
            "updated_at",
        ),
        searchable_columns=(
            "sku",
            "name",
            "description",
            "manufacturer",
            "model",
            "part_role",
            "build_type",
        ),
        default_order_by="name",
    ),
    # Postgres table: public.part_categories (was dbo.PartCategories)
    "categories": TableMapping(
        key="categories",
        schema="public",
        table="part_categories",
        primary_key="category_id",
        allowed_columns=(
            "name",
            "description",
            "parent_category_id",
            "is_active",
            "created_at",
            "updated_at",
        ),
        searchable_columns=("name", "description"),
        default_order_by="name",
    ),
    # Postgres table: public.suppliers (was dbo.Suppliers)
    "suppliers": TableMapping(
        key="suppliers",
        schema="public",
        table="suppliers",
        primary_key="supplier_id",
        allowed_columns=(
            "name",
            "contact_name",
            "email",
            "phone",
            "website",
            "is_active",
            "created_at",
            "updated_at",
        ),
        searchable_columns=("name", "contact_name", "email", "phone"),
        default_order_by="name",
    ),
    # Postgres table: public.stock_movements (was dbo.StockMovements)
    "stock_movements": TableMapping(
        key="stock_movements",
        schema="public",
        table="stock_movements",
        primary_key="stock_movement_id",
        allowed_columns=(
            "inventory_item_id",
            "movement_type",
            "quantity",
            "reference_type",
            "reference_id",
            "notes",
            "created_at",
            "created_by",
        ),
        searchable_columns=("movement_type", "reference_type", "notes", "created_by"),
        default_order_by="created_at",
    ),
}


RESERVATION_TABLES: dict[str, TableMapping] = {
    "orders": TableMapping(
        key="orders",
        schema="public",
        table="orders",
        primary_key="order_id",
        allowed_columns=(
            "customer_name",
            "customer_email",
            "customer_phone",
            "order_status",
            "build_type",
            "notes",
            "created_at",
            "updated_at",
        ),
        searchable_columns=(
            "customer_name",
            "customer_email",
            "customer_phone",
            "order_status",
            "build_type",
        ),
        default_order_by="created_at",
    ),
    "reservations": TableMapping(
        key="reservations",
        schema="public",
        table="order_reservations",
        primary_key="reservation_id",
        allowed_columns=(
            "order_id",
            "inventory_item_id",
            "quantity",
            "reservation_status",
            "expires_at",
            "created_at",
            "updated_at",
        ),
        searchable_columns=("reservation_status",),
        default_order_by="created_at",
    ),
}


CONFIGURATOR_TABLE = INVENTORY_TABLES["items"]
