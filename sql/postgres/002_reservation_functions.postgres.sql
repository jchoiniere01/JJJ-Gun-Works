-- =============================================================================
--  JJJ Gun Works LLC — Reservation functions (PostgreSQL port of
--  sql/002_reservation_procedures.sql).
--
--  The original T-SQL stored procedures are translated into plpgsql
--  FUNCTIONS (not PROCEDUREs) so they can be composed in SELECTs and so
--  they can RETURN TABLE(...) the way the T-SQL versions SELECT result
--  rows. Callers use:
--
--      SELECT * FROM public.usp_create_order_reservation(...);
--      SELECT * FROM public.usp_release_reservation(...);
--      SELECT * FROM public.usp_expire_reservations(...);
--
--  Notes / assumptions:
--    * The FastAPI backend (app/services/reservation_service.py) performs
--      the same logic inline with its own transactions. These functions
--      are preserved for parity with the T-SQL so that non-API callers
--      (psql, cron jobs, admin scripts) still get DB-enforced oversell
--      protection. The backend does NOT need to call them.
--    * T-SQL @@ROWCOUNT -> plpgsql GET DIAGNOSTICS _rowcount = ROW_COUNT
--      (or checking FOUND after single-row DML).
--    * T-SQL SCOPE_IDENTITY() -> INSERT ... RETURNING.
--    * T-SQL WITH (UPDLOCK, HOLDLOCK) on SELECT -> SELECT ... FOR UPDATE.
--    * T-SQL WITH (UPDLOCK, HOLDLOCK) on UPDATE is unnecessary in
--      PostgreSQL — UPDATE already acquires the appropriate row lock.
--    * T-SQL DECLARE @Expired TABLE(...) -> a CTE inside a single UPDATE
--      ... FROM ... statement, matching the original set-based semantics.
--    * Timestamps use now() on TIMESTAMPTZ (functionally equivalent to
--      SYSUTCDATETIME() for this app).
--    * THROW 51011 / 51012 messages -> RAISE EXCEPTION with SQLSTATE
--      'P0001'. If callers want to distinguish which rule fired, use the
--      message text or attach a MESSAGE_TEXT/DETAIL.
-- =============================================================================

SET client_min_messages = WARNING;
SET search_path = public;


-- -----------------------------------------------------------------------------
-- usp_create_order_reservation
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.usp_create_order_reservation
(
    p_order_id          INT,
    p_inventory_item_id INT,
    p_quantity          INT,
    p_expires_at        TIMESTAMPTZ DEFAULT NULL
)
RETURNS TABLE
(
    reservation_id     INT,
    order_id           INT,
    inventory_item_id  INT,
    quantity           INT,
    reservation_status VARCHAR(50),
    expires_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_rowcount INT;
BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Reservation quantity must be greater than zero.'
            USING ERRCODE = 'P0001';
    END IF;

    -- Guarded update. PostgreSQL locks the matched row for the duration
    -- of the UPDATE; the WHERE clause is the oversell guard.
    UPDATE public.inventory_items
       SET quantity_reserved = quantity_reserved + p_quantity,
           updated_at        = now()
     WHERE inventory_item_id = p_inventory_item_id
       AND is_active = TRUE
       AND quantity_on_hand - quantity_reserved >= p_quantity;

    GET DIAGNOSTICS v_rowcount = ROW_COUNT;
    IF v_rowcount = 0 THEN
        RAISE EXCEPTION 'Insufficient available inventory for reservation.'
            USING ERRCODE = 'P0001';
    END IF;

    RETURN QUERY
    INSERT INTO public.order_reservations
        (order_id, inventory_item_id, quantity, reservation_status, expires_at)
    VALUES
        (p_order_id, p_inventory_item_id, p_quantity, 'active', p_expires_at)
    RETURNING reservation_id,
              order_id,
              inventory_item_id,
              quantity,
              reservation_status,
              expires_at,
              created_at,
              updated_at;
END;
$$;


-- -----------------------------------------------------------------------------
-- usp_release_reservation
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.usp_release_reservation
(
    p_reservation_id INT
)
RETURNS TABLE
(
    reservation_id     INT,
    order_id           INT,
    inventory_item_id  INT,
    quantity           INT,
    reservation_status VARCHAR(50),
    expires_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_inventory_item_id INT;
    v_quantity          INT;
BEGIN
    -- Lock the active reservation row (equivalent to WITH (UPDLOCK, HOLDLOCK)).
    SELECT r.inventory_item_id, r.quantity
      INTO v_inventory_item_id, v_quantity
      FROM public.order_reservations r
     WHERE r.reservation_id = p_reservation_id
       AND r.reservation_status = 'active'
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Active reservation was not found.'
            USING ERRCODE = 'P0001';
    END IF;

    UPDATE public.inventory_items
       SET quantity_reserved = GREATEST(quantity_reserved - v_quantity, 0),
           updated_at        = now()
     WHERE inventory_item_id = v_inventory_item_id;

    RETURN QUERY
    UPDATE public.order_reservations
       SET reservation_status = 'released',
           updated_at         = now()
     WHERE reservation_id = p_reservation_id
    RETURNING reservation_id,
              order_id,
              inventory_item_id,
              quantity,
              reservation_status,
              expires_at,
              created_at,
              updated_at;
END;
$$;


-- -----------------------------------------------------------------------------
-- usp_expire_reservations
--
-- Set-based: a CTE selects all active reservations whose expires_at has
-- passed (FOR UPDATE, so concurrent callers can't double-expire), then a
-- single UPDATE against inventory_items subtracts each expired quantity
-- and a final UPDATE flips reservation_status. RETURN QUERY returns the
-- expired reservation rows for caller visibility.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.usp_expire_reservations
(
    p_as_of TIMESTAMPTZ DEFAULT NULL
)
RETURNS TABLE
(
    reservation_id     INT,
    order_id           INT,
    inventory_item_id  INT,
    quantity           INT,
    reservation_status VARCHAR(50),
    expires_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_as_of TIMESTAMPTZ := COALESCE(p_as_of, now());
BEGIN
    -- Gather candidates into a TEMP table first so we can run both
    -- side-effect UPDATEs against a stable snapshot, then return the
    -- expired reservation rows.
    CREATE TEMP TABLE tmp_expired
    (
        reservation_id    INT PRIMARY KEY,
        inventory_item_id INT NOT NULL,
        quantity          INT NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO tmp_expired (reservation_id, inventory_item_id, quantity)
    SELECT r.reservation_id, r.inventory_item_id, r.quantity
      FROM public.order_reservations r
     WHERE r.reservation_status = 'active'
       AND r.expires_at IS NOT NULL
       AND r.expires_at <= v_as_of
       FOR UPDATE;

    -- Roll back the reserved quantity on each affected inventory item.
    -- A reservation can (in theory) repeat the same inventory_item_id
    -- only across different reservations, so we aggregate.
    UPDATE public.inventory_items ii
       SET quantity_reserved = GREATEST(ii.quantity_reserved - agg.total_qty, 0),
           updated_at        = now()
      FROM (
            SELECT inventory_item_id, SUM(quantity) AS total_qty
              FROM tmp_expired
             GROUP BY inventory_item_id
           ) agg
     WHERE ii.inventory_item_id = agg.inventory_item_id;

    UPDATE public.order_reservations r
       SET reservation_status = 'expired',
           updated_at         = now()
     WHERE r.reservation_id IN (SELECT reservation_id FROM tmp_expired);

    RETURN QUERY
    SELECT r.reservation_id,
           r.order_id,
           r.inventory_item_id,
           r.quantity,
           r.reservation_status,
           r.expires_at,
           r.created_at,
           r.updated_at
      FROM public.order_reservations r
      JOIN tmp_expired e ON e.reservation_id = r.reservation_id;
END;
$$;
