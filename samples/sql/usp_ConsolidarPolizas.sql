-- Consolida staging en tablas finales y recalcula primas
CREATE PROCEDURE dbo.usp_ConsolidarPolizas
    @FechaProceso DATE
AS
BEGIN
    SET NOCOUNT ON;

    MERGE INTO dbo.Polizas AS d
    USING (SELECT s.NumPoliza, c.IdCliente, s.Prima, s.FechaInicio
           FROM stg.Polizas s
           INNER JOIN dbo.Clientes c ON c.Rut = s.Rut) AS o
    ON d.NumPoliza = o.NumPoliza
    WHEN MATCHED THEN UPDATE SET d.Prima = o.Prima
    WHEN NOT MATCHED THEN INSERT (NumPoliza, IdCliente, Prima, FechaInicio)
         VALUES (o.NumPoliza, o.IdCliente, o.Prima, o.FechaInicio);

    UPDATE dbo.Polizas SET Estado = 'VENCIDA'
    WHERE FechaTermino < @FechaProceso;

    EXEC dbo.usp_RecalcularPrimas @FechaProceso;
END
GO
