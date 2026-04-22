/*
    Optional stored procedures for clients that want to reserve/release inventory
    directly in SQL Server instead of going through the FastAPI transaction path.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER PROCEDURE dbo.usp_CreateOrderReservation
    @OrderID INT,
    @InventoryItemID INT,
    @Quantity INT,
    @ExpiresAt DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @Quantity <= 0
        THROW 51010, 'Reservation quantity must be greater than zero.', 1;

    BEGIN TRANSACTION;

    UPDATE dbo.InventoryItems WITH (UPDLOCK, HOLDLOCK)
    SET QuantityReserved = QuantityReserved + @Quantity,
        UpdatedAt = SYSUTCDATETIME()
    WHERE InventoryItemID = @InventoryItemID
      AND IsActive = 1
      AND QuantityOnHand - QuantityReserved >= @Quantity;

    IF @@ROWCOUNT = 0
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 51011, 'Insufficient available inventory for reservation.', 1;
    END

    INSERT INTO dbo.OrderReservations
        (OrderID, InventoryItemID, Quantity, ReservationStatus, ExpiresAt, CreatedAt, UpdatedAt)
    VALUES
        (@OrderID, @InventoryItemID, @Quantity, 'active', @ExpiresAt, SYSUTCDATETIME(), SYSUTCDATETIME());

    SELECT *
    FROM dbo.OrderReservations
    WHERE ReservationID = SCOPE_IDENTITY();

    COMMIT TRANSACTION;
END
GO

CREATE OR ALTER PROCEDURE dbo.usp_ReleaseReservation
    @ReservationID INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @InventoryItemID INT;
    DECLARE @Quantity INT;

    BEGIN TRANSACTION;

    SELECT
        @InventoryItemID = InventoryItemID,
        @Quantity = Quantity
    FROM dbo.OrderReservations WITH (UPDLOCK, HOLDLOCK)
    WHERE ReservationID = @ReservationID
      AND ReservationStatus = 'active';

    IF @InventoryItemID IS NULL
    BEGIN
        ROLLBACK TRANSACTION;
        THROW 51012, 'Active reservation was not found.', 1;
    END

    UPDATE dbo.InventoryItems WITH (UPDLOCK, HOLDLOCK)
    SET QuantityReserved =
            CASE
                WHEN QuantityReserved - @Quantity < 0 THEN 0
                ELSE QuantityReserved - @Quantity
            END,
        UpdatedAt = SYSUTCDATETIME()
    WHERE InventoryItemID = @InventoryItemID;

    UPDATE dbo.OrderReservations
    SET ReservationStatus = 'released',
        UpdatedAt = SYSUTCDATETIME()
    WHERE ReservationID = @ReservationID;

    SELECT *
    FROM dbo.OrderReservations
    WHERE ReservationID = @ReservationID;

    COMMIT TRANSACTION;
END
GO

CREATE OR ALTER PROCEDURE dbo.usp_ExpireReservations
    @AsOf DATETIME2(3) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF @AsOf IS NULL
        SET @AsOf = SYSUTCDATETIME();

    DECLARE @Expired TABLE
    (
        ReservationID INT NOT NULL,
        InventoryItemID INT NOT NULL,
        Quantity INT NOT NULL
    );

    BEGIN TRANSACTION;

    INSERT INTO @Expired (ReservationID, InventoryItemID, Quantity)
    SELECT ReservationID, InventoryItemID, Quantity
    FROM dbo.OrderReservations WITH (UPDLOCK, HOLDLOCK)
    WHERE ReservationStatus = 'active'
      AND ExpiresAt IS NOT NULL
      AND ExpiresAt <= @AsOf;

    UPDATE ii
    SET ii.QuantityReserved =
            CASE
                WHEN ii.QuantityReserved - e.Quantity < 0 THEN 0
                ELSE ii.QuantityReserved - e.Quantity
            END,
        ii.UpdatedAt = SYSUTCDATETIME()
    FROM dbo.InventoryItems ii
    INNER JOIN @Expired e ON e.InventoryItemID = ii.InventoryItemID;

    UPDATE r
    SET r.ReservationStatus = 'expired',
        r.UpdatedAt = SYSUTCDATETIME()
    FROM dbo.OrderReservations r
    INNER JOIN @Expired e ON e.ReservationID = r.ReservationID;

    SELECT *
    FROM dbo.OrderReservations
    WHERE ReservationID IN (SELECT ReservationID FROM @Expired);

    COMMIT TRANSACTION;
END
GO
