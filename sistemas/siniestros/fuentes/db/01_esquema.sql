-- Sistema "siniestros" (emulado): BD de destino Siniestros y BD de origen CoreLegado
IF DB_ID('Siniestros') IS NULL CREATE DATABASE Siniestros;
GO
IF DB_ID('CoreLegado') IS NULL CREATE DATABASE CoreLegado;
GO
USE CoreLegado;
GO
-- Tabla del sistema core de donde el paquete SSIS extrae los movimientos
CREATE TABLE dbo.SINIESTRO_MOV (
    ID_MOV      INT IDENTITY PRIMARY KEY,
    NRO_SINIESTRO VARCHAR(20) NOT NULL,
    NRO_POLIZA  VARCHAR(20) NOT NULL,
    TIPO        CHAR(1)     NOT NULL,      -- A = auto, H = hogar, V = vida
    FEC_DENUNCIA DATE       NOT NULL,
    MONTO_UF    DECIMAL(18,2) NOT NULL,
    VIGENTE     BIT         NOT NULL DEFAULT 1
);
GO
USE Siniestros;
GO
IF SCHEMA_ID('stg') IS NULL EXEC('CREATE SCHEMA stg');
GO
CREATE TABLE stg.Siniestros (
    NumSiniestro  VARCHAR(20)   NOT NULL,
    NumPoliza     VARCHAR(20)   NOT NULL,
    Tipo          CHAR(1)       NOT NULL,
    FechaDenuncia DATE          NOT NULL,
    MontoUF       DECIMAL(18,2) NOT NULL
);
CREATE TABLE dbo.Siniestros (
    NumSiniestro  VARCHAR(20)   NOT NULL PRIMARY KEY,
    NumPoliza     VARCHAR(20)   NOT NULL,
    Tipo          CHAR(1)       NOT NULL,
    FechaDenuncia DATE          NOT NULL,
    MontoUF       DECIMAL(18,2) NOT NULL,
    ReservaUF     DECIMAL(18,2) NULL
);
GO
