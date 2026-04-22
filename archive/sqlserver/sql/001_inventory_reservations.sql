/*
    Firearms inventory and AR configurator support objects.

    This script is intentionally compatible with typical converted T-SQL schemas.
    If your conversion already created these tables, compare column names with
    app/table_config.py and either skip the CREATE TABLE blocks or adjust the API
    mappings to match your table names.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID('dbo.PartCategories', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PartCategories
    (
        CategoryID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PartCategories PRIMARY KEY,
        Name NVARCHAR(150) NOT NULL,
        Description NVARCHAR(MAX) NULL,
        ParentCategoryID INT NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_PartCategories_IsActive DEFAULT (1),
        CreatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_PartCategories_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_PartCategories_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_PartCategories_Parent FOREIGN KEY (ParentCategoryID) REFERENCES dbo.PartCategories(CategoryID)
    );
END
GO

IF OBJECT_ID('dbo.Suppliers', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Suppliers
    (
        SupplierID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Suppliers PRIMARY KEY,
        Name NVARCHAR(200) NOT NULL,
        ContactName NVARCHAR(200) NULL,
        Email NVARCHAR(254) NULL,
        Phone NVARCHAR(50) NULL,
        Website NVARCHAR(500) NULL,
        IsActive BIT NOT NULL CONSTRAINT DF_Suppliers_IsActive DEFAULT (1),
        CreatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_Suppliers_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_Suppliers_UpdatedAt DEFAULT SYSUTCDATETIME()
    );
END
GO

IF OBJECT_ID('dbo.InventoryItems', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.InventoryItems
    (
        InventoryItemID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_InventoryItems PRIMARY KEY,
        SKU NVARCHAR(100) NOT NULL,
        Name NVARCHAR(250) NOT NULL,
        Description NVARCHAR(MAX) NULL,
        CategoryID INT NULL,
        SupplierID INT NULL,
        Manufacturer NVARCHAR(200) NULL,
        Model NVARCHAR(200) NULL,
        Caliber NVARCHAR(75) NULL,
        Platform NVARCHAR(100) NULL,
        PartRole NVARCHAR(100) NULL,
        BuildType NVARCHAR(50) NULL,
        UnitCost DECIMAL(19,4) NULL,
        UnitPrice DECIMAL(19,4) NULL,
        QuantityOnHand INT NOT NULL CONSTRAINT DF_InventoryItems_QOH DEFAULT (0),
        QuantityReserved INT NOT NULL CONSTRAINT DF_InventoryItems_QR DEFAULT (0),
        ReorderPoint INT NOT NULL CONSTRAINT DF_InventoryItems_ReorderPoint DEFAULT (0),
        IsActive BIT NOT NULL CONSTRAINT DF_InventoryItems_IsActive DEFAULT (1),
        RequiresFFL BIT NOT NULL CONSTRAINT DF_InventoryItems_RequiresFFL DEFAULT (0),
        IsSerialized BIT NOT NULL CONSTRAINT DF_InventoryItems_IsSerialized DEFAULT (0),
        CreatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_InventoryItems_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_InventoryItems_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_InventoryItems_SKU UNIQUE (SKU),
        CONSTRAINT FK_InventoryItems_Category FOREIGN KEY (CategoryID) REFERENCES dbo.PartCategories(CategoryID),
        CONSTRAINT FK_InventoryItems_Supplier FOREIGN KEY (SupplierID) REFERENCES dbo.Suppliers(SupplierID),
        CONSTRAINT CK_InventoryItems_Quantities CHECK
        (
            QuantityOnHand >= 0
            AND QuantityReserved >= 0
            AND QuantityReserved <= QuantityOnHand
        )
    );
END
GO

IF OBJECT_ID('dbo.StockMovements', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.StockMovements
    (
        StockMovementID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_StockMovements PRIMARY KEY,
        InventoryItemID INT NOT NULL,
        MovementType NVARCHAR(50) NOT NULL,
        Quantity INT NOT NULL,
        ReferenceType NVARCHAR(50) NULL,
        ReferenceID INT NULL,
        Notes NVARCHAR(MAX) NULL,
        CreatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_StockMovements_CreatedAt DEFAULT SYSUTCDATETIME(),
        CreatedBy NVARCHAR(150) NULL,
        CONSTRAINT FK_StockMovements_InventoryItem FOREIGN KEY (InventoryItemID) REFERENCES dbo.InventoryItems(InventoryItemID),
        CONSTRAINT CK_StockMovements_Quantity CHECK (Quantity <> 0)
    );
END
GO

IF OBJECT_ID('dbo.Orders', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Orders
    (
        OrderID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Orders PRIMARY KEY,
        CustomerName NVARCHAR(200) NULL,
        CustomerEmail NVARCHAR(254) NULL,
        CustomerPhone NVARCHAR(50) NULL,
        OrderStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_Orders_OrderStatus DEFAULT ('draft'),
        BuildType NVARCHAR(50) NULL,
        Notes NVARCHAR(MAX) NULL,
        CreatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_Orders_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_Orders_UpdatedAt DEFAULT SYSUTCDATETIME()
    );
END
GO

IF OBJECT_ID('dbo.OrderReservations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.OrderReservations
    (
        ReservationID INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_OrderReservations PRIMARY KEY,
        OrderID INT NOT NULL,
        InventoryItemID INT NOT NULL,
        Quantity INT NOT NULL,
        ReservationStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_OrderReservations_Status DEFAULT ('active'),
        ExpiresAt DATETIME2(3) NULL,
        CreatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_OrderReservations_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt DATETIME2(3) NOT NULL CONSTRAINT DF_OrderReservations_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_OrderReservations_Order FOREIGN KEY (OrderID) REFERENCES dbo.Orders(OrderID),
        CONSTRAINT FK_OrderReservations_InventoryItem FOREIGN KEY (InventoryItemID) REFERENCES dbo.InventoryItems(InventoryItemID),
        CONSTRAINT CK_OrderReservations_Quantity CHECK (Quantity > 0),
        CONSTRAINT CK_OrderReservations_Status CHECK (ReservationStatus IN ('active', 'released', 'expired', 'fulfilled', 'cancelled'))
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_InventoryItems_ConfigSearch' AND object_id = OBJECT_ID('dbo.InventoryItems'))
BEGIN
    CREATE INDEX IX_InventoryItems_ConfigSearch
    ON dbo.InventoryItems (PartRole, BuildType, IsActive)
    INCLUDE (SKU, Name, Manufacturer, Model, Caliber, Platform, UnitPrice, QuantityOnHand, QuantityReserved);
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_OrderReservations_Active' AND object_id = OBJECT_ID('dbo.OrderReservations'))
BEGIN
    CREATE INDEX IX_OrderReservations_Active
    ON dbo.OrderReservations (ReservationStatus, ExpiresAt, OrderID, InventoryItemID)
    INCLUDE (Quantity);
END
GO

CREATE OR ALTER TRIGGER dbo.trg_InventoryItems_NoOversell
ON dbo.InventoryItems
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS
    (
        SELECT 1
        FROM inserted
        WHERE QuantityOnHand < 0
           OR QuantityReserved < 0
           OR QuantityReserved > QuantityOnHand
    )
    BEGIN
        THROW 51001, 'Inventory oversell protection: QuantityReserved cannot exceed QuantityOnHand and quantities cannot be negative.', 1;
    END
END
GO

CREATE OR ALTER TRIGGER dbo.trg_OrderReservations_StatusIntegrity
ON dbo.OrderReservations
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS
    (
        SELECT 1
        FROM inserted
        WHERE Quantity <= 0
           OR ReservationStatus NOT IN ('active', 'released', 'expired', 'fulfilled', 'cancelled')
    )
    BEGIN
        THROW 51002, 'Reservation integrity violation: quantity must be positive and status must be valid.', 1;
    END
END
GO
