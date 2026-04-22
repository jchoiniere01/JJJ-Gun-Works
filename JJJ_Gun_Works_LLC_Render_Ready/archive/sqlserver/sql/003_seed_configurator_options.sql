/*
    Optional seed data for testing the configurator endpoint.
    It inserts five rifle/pistol-compatible options each for:
    lower receiver, riser mount, and pistol grip.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.PartCategories WHERE Name = 'Lower Receiver')
    INSERT INTO dbo.PartCategories (Name, Description) VALUES ('Lower Receiver', 'AR lower receivers.');
IF NOT EXISTS (SELECT 1 FROM dbo.PartCategories WHERE Name = 'Riser Mount')
    INSERT INTO dbo.PartCategories (Name, Description) VALUES ('Riser Mount', 'Optic riser mounts.');
IF NOT EXISTS (SELECT 1 FROM dbo.PartCategories WHERE Name = 'Pistol Grip')
    INSERT INTO dbo.PartCategories (Name, Description) VALUES ('Pistol Grip', 'AR pistol grips.');
GO

DECLARE @LowerCategoryID INT = (SELECT TOP 1 CategoryID FROM dbo.PartCategories WHERE Name = 'Lower Receiver');
DECLARE @RiserCategoryID INT = (SELECT TOP 1 CategoryID FROM dbo.PartCategories WHERE Name = 'Riser Mount');
DECLARE @GripCategoryID INT = (SELECT TOP 1 CategoryID FROM dbo.PartCategories WHERE Name = 'Pistol Grip');

MERGE dbo.InventoryItems AS target
USING
(
    VALUES
    ('LR-001', 'Forged AR-15 Lower Receiver', @LowerCategoryID, 'Aero Precision', 'M4E1', 'multi', 'AR-15', 'lower receiver', 'both', 129.99, 10),
    ('LR-002', 'Billet AR-15 Lower Receiver', @LowerCategoryID, 'Spike''s Tactical', 'STLS', 'multi', 'AR-15', 'lower receiver', 'both', 159.99, 8),
    ('LR-003', 'Ambi AR-15 Lower Receiver', @LowerCategoryID, 'ADM', 'UIC', 'multi', 'AR-15', 'lower receiver', 'both', 329.99, 5),
    ('LR-004', 'Lightweight AR-15 Lower Receiver', @LowerCategoryID, 'KE Arms', 'KP-15', 'multi', 'AR-15', 'lower receiver', 'rifle', 109.99, 7),
    ('LR-005', 'Pistol Marked AR Lower Receiver', @LowerCategoryID, 'Anderson', 'AM-15', 'multi', 'AR-15', 'lower receiver', 'pistol', 79.99, 12),
    ('RM-001', 'Absolute Co-Witness Riser Mount', @RiserCategoryID, 'UTG', 'MT-RSX20S', NULL, 'Picatinny', 'riser mount', 'both', 19.99, 15),
    ('RM-002', 'Lower 1/3 Riser Mount', @RiserCategoryID, 'Primary Arms', 'GLX-RISER', NULL, 'Picatinny', 'riser mount', 'both', 39.99, 10),
    ('RM-003', 'QD Optic Riser Mount', @RiserCategoryID, 'American Defense', 'AD-170', NULL, 'Picatinny', 'riser mount', 'both', 99.99, 6),
    ('RM-004', 'Slim Micro Dot Riser', @RiserCategoryID, 'Holosun', 'HS-RISER', NULL, 'Picatinny', 'riser mount', 'rifle', 29.99, 11),
    ('RM-005', 'Compact Pistol Optic Riser', @RiserCategoryID, 'Scalarworks', 'LEAP-01', NULL, 'Picatinny', 'riser mount', 'pistol', 149.99, 4),
    ('PG-001', 'MOE Pistol Grip', @GripCategoryID, 'Magpul', 'MOE', NULL, 'AR-15', 'pistol grip', 'both', 19.95, 25),
    ('PG-002', 'K2 Pistol Grip', @GripCategoryID, 'Magpul', 'K2', NULL, 'AR-15', 'pistol grip', 'both', 24.95, 20),
    ('PG-003', 'Rubberized AR Grip', @GripCategoryID, 'Hogue', 'OverMolded', NULL, 'AR-15', 'pistol grip', 'both', 29.95, 18),
    ('PG-004', 'Reduced Angle Pistol Grip', @GripCategoryID, 'BCM', 'Gunfighter Mod 3', NULL, 'AR-15', 'pistol grip', 'rifle', 19.95, 17),
    ('PG-005', 'Compact AR Pistol Grip', @GripCategoryID, 'B5 Systems', 'Type 23 P-Grip', NULL, 'AR-15', 'pistol grip', 'pistol', 22.00, 13)
) AS source
(
    SKU,
    Name,
    CategoryID,
    Manufacturer,
    Model,
    Caliber,
    Platform,
    PartRole,
    BuildType,
    UnitPrice,
    QuantityOnHand
)
ON target.SKU = source.SKU
WHEN NOT MATCHED THEN
    INSERT
    (
        SKU,
        Name,
        CategoryID,
        Manufacturer,
        Model,
        Caliber,
        Platform,
        PartRole,
        BuildType,
        UnitPrice,
        QuantityOnHand,
        QuantityReserved,
        IsActive,
        RequiresFFL,
        IsSerialized,
        CreatedAt,
        UpdatedAt
    )
    VALUES
    (
        source.SKU,
        source.Name,
        source.CategoryID,
        source.Manufacturer,
        source.Model,
        source.Caliber,
        source.Platform,
        source.PartRole,
        source.BuildType,
        source.UnitPrice,
        source.QuantityOnHand,
        0,
        1,
        CASE WHEN source.PartRole = 'lower receiver' THEN 1 ELSE 0 END,
        CASE WHEN source.PartRole = 'lower receiver' THEN 1 ELSE 0 END,
        SYSUTCDATETIME(),
        SYSUTCDATETIME()
    );
GO
