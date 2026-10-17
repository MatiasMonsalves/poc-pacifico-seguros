USE Siniestros;
GO
-- Consolida el staging y calcula la reserva técnica: 120 % del monto en vida,
-- 100 % en auto y hogar, más 10 % si el siniestro lleva más de 90 días abierto.
CREATE OR ALTER PROCEDURE dbo.usp_CalcularReservas
    @FechaCorte DATE
AS
BEGIN
    SET NOCOUNT ON;
    MERGE dbo.Siniestros AS d
    USING stg.Siniestros AS o ON d.NumSiniestro = o.NumSiniestro
    WHEN MATCHED THEN UPDATE SET d.MontoUF = o.MontoUF
    WHEN NOT MATCHED THEN INSERT (NumSiniestro, NumPoliza, Tipo, FechaDenuncia, MontoUF)
         VALUES (o.NumSiniestro, o.NumPoliza, o.Tipo, o.FechaDenuncia, o.MontoUF);

    UPDATE dbo.Siniestros
    SET ReservaUF = ROUND(MontoUF * IIF(Tipo = 'V', 1.2, 1.0)
                    * IIF(DATEDIFF(DAY, FechaDenuncia, @FechaCorte) > 90, 1.1, 1.0), 2);
END
GO
