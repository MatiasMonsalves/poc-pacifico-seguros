USE Seguros;
GO
-- Datos sintéticos (no corresponden a personas reales)
INSERT INTO dbo.Clientes (Rut, Nombre, FechaNacimiento) VALUES
 ('11111111-1', N'Ana Torres',     '1999-03-14'),
 ('22222222-2', N'Bruno Díaz',     '1980-07-02'),
 ('33333333-3', N'Carla Muñoz',    '1958-11-23'),
 ('44444444-4', N'Diego Rojas',    '1972-01-30'),
 ('55555555-5', N'Elena Fuentes',  '2003-09-09'),
 ('66666666-6', N'Felipe Soto',    '2001-12-20');

INSERT INTO dbo.Polizas (NumPoliza, IdCliente, TipoSeguro, SumaAsegurada, PrimaBase, Prima, Siniestros, FechaInicio, FechaTermino) VALUES
 ('POL-0001', 1, 'AUTO',  450.00,  20.48, 19.46, 0, '2026-01-01', '2026-12-31'),
 ('POL-0002', 2, 'HOGAR', 3200.00, 12.50, 14.38, 1, '2026-02-01', '2027-01-31'),
 ('POL-0003', 3, 'VIDA',  1500.00, 10.80, 10.26, 0, '2025-06-01', '2026-05-31');
GO
