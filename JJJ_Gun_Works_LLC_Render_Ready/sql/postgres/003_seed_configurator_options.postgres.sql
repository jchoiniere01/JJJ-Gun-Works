-- =============================================================================
--  JJJ Gun Works LLC — Configurator seed data (PostgreSQL port of
--  sql/003_seed_configurator_options.sql).
--
--  Notes / assumptions:
--    * The original used MERGE ... WHEN NOT MATCHED THEN INSERT, keyed by
--      SKU. We replace that with INSERT ... ON CONFLICT (sku) DO NOTHING,
--      which matches the intent (insert once, skip duplicates).
--    * The original set RequiresFFL=1 and IsSerialized=1 only when
--      PartRole = 'lower receiver'. We keep the same CASE logic below.
--    * Category lookups use a subquery per row (lateral to the VALUES
--      clause is not required — a correlated scalar subquery is fine for
--      15 rows). The three referenced PartCategories rows are inserted
--      first with their own ON CONFLICT guard on (name) — see below.
--    * part_categories.name has no UNIQUE constraint in the DDL, so this
--      script adds ON CONFLICT DO NOTHING only on inventory_items. The
--      category inserts are wrapped in IF NOT EXISTS via `WHERE NOT
--      EXISTS` to stay idempotent without changing the base schema.
--    * All SKU / name / manufacturer values are copied verbatim from
--      003_seed_configurator_options.sql (T-SQL). Spike''s Tactical is
--      preserved with its escaped apostrophe.
-- =============================================================================

SET client_min_messages = WARNING;
SET search_path = public;

-- -----------------------------------------------------------------------------
-- Categories
-- -----------------------------------------------------------------------------
INSERT INTO public.part_categories (name, description)
SELECT 'Lower Receiver', 'AR lower receivers.'
WHERE NOT EXISTS (SELECT 1 FROM public.part_categories WHERE name = 'Lower Receiver');

INSERT INTO public.part_categories (name, description)
SELECT 'Riser Mount', 'Optic riser mounts.'
WHERE NOT EXISTS (SELECT 1 FROM public.part_categories WHERE name = 'Riser Mount');

INSERT INTO public.part_categories (name, description)
SELECT 'Pistol Grip', 'AR pistol grips.'
WHERE NOT EXISTS (SELECT 1 FROM public.part_categories WHERE name = 'Pistol Grip');

-- -----------------------------------------------------------------------------
-- Inventory items
--
-- The original MERGE source had columns:
--   SKU, Name, CategoryID, Manufacturer, Model, Caliber, Platform,
--   PartRole, BuildType, UnitPrice, QuantityOnHand
--
-- We build the same row set from a VALUES list, resolve category_id via
-- a scalar subquery on the category name, and INSERT ... ON CONFLICT
-- (sku) DO NOTHING to preserve idempotency.
-- -----------------------------------------------------------------------------
INSERT INTO public.inventory_items
(
    sku, name, category_id, manufacturer, model, caliber, platform,
    part_role, build_type, unit_price, quantity_on_hand,
    quantity_reserved, is_active, requires_ffl, is_serialized
)
SELECT
    src.sku,
    src.name,
    (SELECT category_id FROM public.part_categories WHERE name = src.category_name LIMIT 1) AS category_id,
    src.manufacturer,
    src.model,
    src.caliber,
    src.platform,
    src.part_role,
    src.build_type,
    src.unit_price,
    src.quantity_on_hand,
    0                                                           AS quantity_reserved,
    TRUE                                                        AS is_active,
    CASE WHEN src.part_role = 'lower receiver' THEN TRUE ELSE FALSE END AS requires_ffl,
    CASE WHEN src.part_role = 'lower receiver' THEN TRUE ELSE FALSE END AS is_serialized
FROM
(
    VALUES
    -- Lower receivers
    ('LR-001', 'Forged AR-15 Lower Receiver',       'Lower Receiver', 'Aero Precision',     'M4E1',             'multi', 'AR-15', 'lower receiver', 'both',   129.99, 10),
    ('LR-002', 'Billet AR-15 Lower Receiver',       'Lower Receiver', 'Spike''s Tactical',  'STLS',             'multi', 'AR-15', 'lower receiver', 'both',   159.99,  8),
    ('LR-003', 'Ambi AR-15 Lower Receiver',         'Lower Receiver', 'ADM',                'UIC',              'multi', 'AR-15', 'lower receiver', 'both',   329.99,  5),
    ('LR-004', 'Lightweight AR-15 Lower Receiver',  'Lower Receiver', 'KE Arms',            'KP-15',            'multi', 'AR-15', 'lower receiver', 'rifle',  109.99,  7),
    ('LR-005', 'Pistol Marked AR Lower Receiver',   'Lower Receiver', 'Anderson',           'AM-15',            'multi', 'AR-15', 'lower receiver', 'pistol',  79.99, 12),
    -- Riser mounts
    ('RM-001', 'Absolute Co-Witness Riser Mount',   'Riser Mount',    'UTG',                'MT-RSX20S',        NULL,    'Picatinny', 'riser mount', 'both',    19.99, 15),
    ('RM-002', 'Lower 1/3 Riser Mount',             'Riser Mount',    'Primary Arms',       'GLX-RISER',        NULL,    'Picatinny', 'riser mount', 'both',    39.99, 10),
    ('RM-003', 'QD Optic Riser Mount',              'Riser Mount',    'American Defense',   'AD-170',           NULL,    'Picatinny', 'riser mount', 'both',    99.99,  6),
    ('RM-004', 'Slim Micro Dot Riser',              'Riser Mount',    'Holosun',            'HS-RISER',         NULL,    'Picatinny', 'riser mount', 'rifle',   29.99, 11),
    ('RM-005', 'Compact Pistol Optic Riser',        'Riser Mount',    'Scalarworks',        'LEAP-01',          NULL,    'Picatinny', 'riser mount', 'pistol', 149.99,  4),
    -- Pistol grips
    ('PG-001', 'MOE Pistol Grip',                   'Pistol Grip',    'Magpul',             'MOE',              NULL,    'AR-15',     'pistol grip', 'both',    19.95, 25),
    ('PG-002', 'K2 Pistol Grip',                    'Pistol Grip',    'Magpul',             'K2',               NULL,    'AR-15',     'pistol grip', 'both',    24.95, 20),
    ('PG-003', 'Rubberized AR Grip',                'Pistol Grip',    'Hogue',              'OverMolded',       NULL,    'AR-15',     'pistol grip', 'both',    29.95, 18),
    ('PG-004', 'Reduced Angle Pistol Grip',         'Pistol Grip',    'BCM',                'Gunfighter Mod 3', NULL,    'AR-15',     'pistol grip', 'rifle',   19.95, 17),
    ('PG-005', 'Compact AR Pistol Grip',            'Pistol Grip',    'B5 Systems',         'Type 23 P-Grip',   NULL,    'AR-15',     'pistol grip', 'pistol',  22.00, 13)
) AS src
(
    sku, name, category_name, manufacturer, model, caliber, platform,
    part_role, build_type, unit_price, quantity_on_hand
)
ON CONFLICT (sku) DO NOTHING;
