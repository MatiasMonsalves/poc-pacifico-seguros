USE Seguros;
GO
-- Recalcula la prima de las pólizas vigentes según siniestralidad:
-- 5% de descuento sin siniestros; 15% de recargo por siniestro, máximo 3.
CREATE OR ALTER PROCEDURE dbo.usp_RecalcularPrimas
    @FechaProceso DATE
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.Polizas
    SET Prima = ROUND(PrimaBase *
                CASE WHEN Siniestros = 0 THEN 0.95
                     ELSE 1 + 0.15 * IIF(Siniestros > 3, 3, Siniestros) END, 2)
    WHERE Estado = 'VIGENTE'
      AND FechaInicio <= @FechaProceso;
END
GO
