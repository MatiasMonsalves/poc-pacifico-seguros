-- Base de datos legada "Seguros" (emulación del sistema del cliente)
IF DB_ID('Seguros') IS NULL CREATE DATABASE Seguros;
GO
USE Seguros;
GO
IF SCHEMA_ID('stg') IS NULL EXEC('CREATE SCHEMA stg');
IF SCHEMA_ID('log') IS NULL EXEC('CREATE SCHEMA log');
GO
CREATE TABLE dbo.Clientes (
    IdCliente       INT IDENTITY PRIMARY KEY,
    Rut             VARCHAR(12)  NOT NULL UNIQUE,
    Nombre          NVARCHAR(100) NOT NULL,
    FechaNacimiento DATE NOT NULL
);

CREATE TABLE dbo.Polizas (
    NumPoliza     VARCHAR(20)   NOT NULL PRIMARY KEY,
    IdCliente     INT           NOT NULL REFERENCES dbo.Clientes(IdCliente),
    TipoSeguro    VARCHAR(10)   NOT NULL,
    SumaAsegurada DECIMAL(18,2) NOT NULL,
    PrimaBase     DECIMAL(18,2) NOT NULL,
    Prima         DECIMAL(18,2) NOT NULL,
    Siniestros    INT           NOT NULL DEFAULT 0,
    FechaInicio   DATE          NOT NULL,
    FechaTermino  DATE          NOT NULL,
    Estado        VARCHAR(10)   NOT NULL DEFAULT 'VIGENTE'
);

-- Staging que llena el paquete SSIS CargaPolizas desde el CSV
CREATE TABLE stg.Polizas (
    NumPoliza     VARCHAR(20)   NOT NULL,
    Rut           VARCHAR(12)   NOT NULL,
    TipoSeguro    VARCHAR(10)   NOT NULL,
    SumaAsegurada DECIMAL(18,2) NOT NULL,
    PrimaBase     DECIMAL(18,2) NOT NULL,
    Siniestros    INT           NOT NULL,
    FechaInicio   DATE          NOT NULL,
    FechaTermino  DATE          NOT NULL
);

CREATE TABLE log.ErroresETL (
    IdError INT IDENTITY PRIMARY KEY,
    Paquete VARCHAR(100)  NOT NULL,
    Fecha   DATETIME2     NOT NULL,
    Mensaje NVARCHAR(4000) NULL,
    RunId   VARCHAR(50)   NULL
);
GO
