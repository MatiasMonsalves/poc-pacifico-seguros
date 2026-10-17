USE Seguros;
GO
-- Consolida staging en tablas finales y recalcula primas.
-- La validación de RUT reemplaza al Lookup "Buscar Cliente" del paquete SSIS,
-- que por defecto hace fallar la carga cuando una fila no tiene cliente.
CREATE OR ALTER PROCEDURE dbo.usp_ConsolidarPolizas
    @FechaProceso DATE
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @SinCliente INT = (
        SELECT COUNT(*)
        FROM stg.Polizas s
        LEFT JOIN dbo.Clientes c ON c.Rut = s.Rut
        WHERE c.IdCliente IS NULL);

    IF @SinCliente > 0
    BEGIN
        DECLARE @Mensaje NVARCHAR(400) =
            CONCAT(@SinCliente, ' póliza(s) en staging con RUT sin cliente en dbo.Clientes');
        THROW 50001, @Mensaje, 1;
    END

    BEGIN TRANSACTION;

    MERGE INTO dbo.Polizas AS d
    USING (SELECT s.NumPoliza, c.IdCliente, s.TipoSeguro, s.SumaAsegurada,
                  s.PrimaBase, s.Siniestros, s.FechaInicio, s.FechaTermino
           FROM stg.Polizas s
           INNER JOIN dbo.Clientes c ON c.Rut = s.Rut) AS o
    ON d.NumPoliza = o.NumPoliza
    WHEN MATCHED THEN UPDATE SET
         d.PrimaBase = o.PrimaBase, d.SumaAsegurada = o.SumaAsegurada,
         d.Siniestros = o.Siniestros, d.FechaTermino = o.FechaTermino
    WHEN NOT MATCHED THEN INSERT
         (NumPoliza, IdCliente, TipoSeguro, SumaAsegurada, PrimaBase, Prima,
          Siniestros, FechaInicio, FechaTermino)
         VALUES (o.NumPoliza, o.IdCliente, o.TipoSeguro, o.SumaAsegurada, o.PrimaBase,
                 o.PrimaBase, o.Siniestros, o.FechaInicio, o.FechaTermino);

    UPDATE dbo.Polizas SET Estado = 'VENCIDA'
    WHERE FechaTermino < @FechaProceso AND Estado = 'VIGENTE';

    COMMIT;

    EXEC dbo.usp_RecalcularPrimas @FechaProceso;
END
GO
