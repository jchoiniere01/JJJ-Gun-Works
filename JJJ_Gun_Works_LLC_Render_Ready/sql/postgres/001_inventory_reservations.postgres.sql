-- =============================================================================
--  JJJ Gun Works LLC — Firearms Inventory & Reservations
--  PostgreSQL port of sql/001_inventory_reservations.sql (SQL Server / T-SQL).
--
--  Assumptions made during translation:
--    * Target schema is `public` (original used `dbo`). Adjust the SET
--      search_path line if you want a dedicated schema.
--    * Identifiers converted to snake_case. If you prefer to keep the
--      original mixed-case identifiers, replace each unquoted identifier
--      below with its double-quoted T-SQL equivalent (e.g., "InventoryItems").
--    * NVARCHAR(MAX) -> TEXT; NVARCHAR(n) -> VARCHAR(n).
--    * BIT -> BOOLEAN (defaults 1/0 become TRUE/FALSE).
--    * DATETIME2(3) -> TIMESTAMPTZ with DEFAULT now(). The original stored
--      UTC via SYSUTCDATETIME(); now() returns timestamptz which is stored
--      as UTC on the server side — functionally equivalent for this app.
--    * IDENTITY columns -> INT GENERATED ALWAYS AS IDENTITY.
--    * Named DEFAULT constraints (CONSTRAINT DF_* DEFAULT (...)) collapsed
--      into inline DEFAULTs since PostgreSQL does not name default
--      constraints.
--    * T-SQL AFTER INSERT/UPDATE triggers using the `inserted` pseudo-table
--      rewritten as BEFORE INSERT/UPDATE row-level plpgsql triggers that
--      reference NEW.
--    * Script is idempotent: every CREATE TABLE uses IF NOT EXISTS and
--      indexes/triggers use CREATE INDEX IF NOT EXISTS / CREATE OR REPLACE.
-- =============================================================================

SET client_min_messages = WARNING;
SET search_path = public;

-- -----------------------------------------------------------------------------
-- part_categories   (was dbo.PartCategories)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.part_categories
(
    category_id        INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               VARCHAR(150) NOT NULL,
    description        TEXT         NULL,
    parent_category_id INT          NULL,
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT fk_part_categories_parent
        FOREIGN KEY (parent_category_id)
        REFERENCES public.part_categories (category_id)
);

-- -----------------------------------------------------------------------------
-- suppliers   (was dbo.Suppliers)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.suppliers
(
    supplier_id  INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         VARCHAR(200) NOT NULL,
    contact_name VARCHAR(200) NULL,
    email        VARCHAR(254) NULL,
    phone        VARCHAR(50)  NULL,
    website      VARCHAR(500) NULL,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- inventory_items   (was dbo.InventoryItems)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.inventory_items
(
    inventory_item_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku               VARCHAR(100)  NOT NULL,
    name              VARCHAR(250)  NOT NULL,
    description       TEXT          NULL,
    category_id       INT           NULL,
    supplier_id       INT           NULL,
    manufacturer      VARCHAR(200)  NULL,
    model             VARCHAR(200)  NULL,
    caliber           VARCHAR(75)   NULL,
    platform          VARCHAR(100)  NULL,
    part_role         VARCHAR(100)  NULL,
    build_type        VARCHAR(50)   NULL,
    unit_cost         NUMERIC(19,4) NULL,
    unit_price        NUMERIC(19,4) NULL,
    quantity_on_hand  INT           NOT NULL DEFAULT 0,
    quantity_reserved INT           NOT NULL DEFAULT 0,
    reorder_point     INT           NOT NULL DEFAULT 0,
    is_active         BOOLEAN       NOT NULL DEFAULT TRUE,
    requires_ffl      BOOLEAN       NOT NULL DEFAULT FALSE,
    is_serialized     BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_inventory_items_sku UNIQUE (sku),
    CONSTRAINT fk_inventory_items_category
        FOREIGN KEY (category_id) REFERENCES public.part_categories (category_id),
    CONSTRAINT fk_inventory_items_supplier
        FOREIGN KEY (supplier_id) REFERENCES public.suppliers (supplier_id),
    CONSTRAINT ck_inventory_items_quantities CHECK
    (
        quantity_on_hand >= 0
        AND quantity_reserved >= 0
        AND quantity_reserved <= quantity_on_hand
    )
);

-- -----------------------------------------------------------------------------
-- stock_movements   (was dbo.StockMovements)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.stock_movements
(
    stock_movement_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inventory_item_id INT          NOT NULL,
    movement_type     VARCHAR(50)  NOT NULL,
    quantity          INT          NOT NULL,
    reference_type    VARCHAR(50)  NULL,
    reference_id      INT          NULL,
    notes             TEXT         NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_by        VARCHAR(150) NULL,
    CONSTRAINT fk_stock_movements_inventory_item
        FOREIGN KEY (inventory_item_id)
        REFERENCES public.inventory_items (inventory_item_id),
    CONSTRAINT ck_stock_movements_quantity CHECK (quantity <> 0)
);

-- -----------------------------------------------------------------------------
-- orders   (was dbo.Orders)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.orders
(
    order_id       INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name  VARCHAR(200) NULL,
    customer_email VARCHAR(254) NULL,
    customer_phone VARCHAR(50)  NULL,
    order_status   VARCHAR(50)  NOT NULL DEFAULT 'draft',
    build_type     VARCHAR(50)  NULL,
    notes          TEXT         NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- order_reservations   (was dbo.OrderReservations)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.order_reservations
(
    reservation_id     INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id           INT         NOT NULL,
    inventory_item_id  INT         NOT NULL,
    quantity           INT         NOT NULL,
    reservation_status VARCHAR(50) NOT NULL DEFAULT 'active',
    expires_at         TIMESTAMPTZ NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_order_reservations_order
        FOREIGN KEY (order_id) REFERENCES public.orders (order_id),
    CONSTRAINT fk_order_reservations_inventory_item
        FOREIGN KEY (inventory_item_id)
        REFERENCES public.inventory_items (inventory_item_id),
    CONSTRAINT ck_order_reservations_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_reservations_status
        CHECK (reservation_status IN ('active', 'released', 'expired', 'fulfilled', 'cancelled'))
);

-- -----------------------------------------------------------------------------
-- Indexes
--
-- PostgreSQL 11+ supports INCLUDE on btree indexes, so we preserve the
-- original covering-index intent from the T-SQL script.
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_inventory_items_config_search
    ON public.inventory_items (part_role, build_type, is_active)
    INCLUDE (sku, name, manufacturer, model, caliber, platform,
             unit_price, quantity_on_hand, quantity_reserved);

CREATE INDEX IF NOT EXISTS ix_order_reservations_active
    ON public.order_reservations (reservation_status, expires_at, order_id, inventory_item_id)
    INCLUDE (quantity);

-- =============================================================================
-- Triggers
--
-- Mirrors dbo.trg_InventoryItems_NoOversell and
--         dbo.trg_OrderReservations_StatusIntegrity.
-- Implemented as BEFORE INSERT OR UPDATE row-level triggers (PostgreSQL
-- has no AFTER statement-level `inserted` pseudo-table). Using BEFORE lets
-- us abort the write before it lands rather than rolling back after.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.trg_inventory_items_no_oversell()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.quantity_on_hand < 0
       OR NEW.quantity_reserved < 0
       OR NEW.quantity_reserved > NEW.quantity_on_hand THEN
        RAISE EXCEPTION
            'Inventory oversell protection: quantity_reserved cannot exceed quantity_on_hand and quantities cannot be negative.'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS inventory_items_no_oversell ON public.inventory_items;
CREATE TRIGGER inventory_items_no_oversell
    BEFORE INSERT OR UPDATE ON public.inventory_items
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_inventory_items_no_oversell();


CREATE OR REPLACE FUNCTION public.trg_order_reservations_status_integrity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.quantity <= 0
       OR NEW.reservation_status NOT IN ('active', 'released', 'expired', 'fulfilled', 'cancelled') THEN
        RAISE EXCEPTION
            'Reservation integrity violation: quantity must be positive and status must be valid.'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS order_reservations_status_integrity ON public.order_reservations;
CREATE TRIGGER order_reservations_status_integrity
    BEFORE INSERT OR UPDATE ON public.order_reservations
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_order_reservations_status_integrity();

-- =============================================================================
-- Optional: updated_at maintenance trigger
--
-- The T-SQL schema set CreatedAt/UpdatedAt via SYSUTCDATETIME() defaults and
-- the Python service code writes UpdatedAt explicitly on every UPDATE. We
-- keep that behavior and do NOT install an automatic updated_at trigger
-- here, to match the existing backend. Uncomment the block below if you
-- want PostgreSQL to maintain updated_at autonomously.
-- =============================================================================
--
-- CREATE OR REPLACE FUNCTION public.trg_touch_updated_at()
-- RETURNS trigger LANGUAGE plpgsql AS $$
-- BEGIN
--     NEW.updated_at := now();
--     RETURN NEW;
-- END;
-- $$;
--
-- DROP TRIGGER IF EXISTS touch_inventory_items_updated_at ON public.inventory_items;
-- CREATE TRIGGER touch_inventory_items_updated_at
--     BEFORE UPDATE ON public.inventory_items
--     FOR EACH ROW EXECUTE FUNCTION public.trg_touch_updated_at();
