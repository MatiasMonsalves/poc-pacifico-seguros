# Binarios analizados con REA

| Binario | Tipo | Framework | Tipos / métodos | SQL | Conexiones |
|---|---|---|---|---|---|
| `Pacifico.Siniestros.Reglas.dll` | .NET Framework | .NETFramework,Version=v4.0 | 1 / 2 | 1 | 1 |

## Pacifico.Siniestros.Reglas.dll

- Tipo: .NET Framework
- Assembly: Pacifico.Siniestros.Reglas 1.4.0.0 · .NETFramework,Version=v4.0
- Referencias: mscorlib, System.Data
- Tipos: `Pacifico.Siniestros.Reglas.CalculadoraReserva`
- Acceso a datos: System.Data.Common.DbCommand.ExecuteScalar, System.Data.Common.DbConnection.Open, System.Data.SqlClient.SqlCommand..ctor, System.Data.SqlClient.SqlCommand.get_Parameters, System.Data.SqlClient.SqlConnection..ctor, System.Data.SqlClient.SqlParameterCollection.AddWithValue
- SQL:
  - `SELECT ReservaUF FROM dbo.Siniestros WHERE NumSiniestro = @n`
- Cadenas de conexión:
  - `Data Source=SRVSQL02;Initial Catalog=Siniestros;User ID=reglas;Password=****`
- Decompilación ILSpy 11.1.0.9782: `Pacifico.Siniestros.Reglas.dll/decompilado/`
- Reconstrucción importada en REA: `Pacifico.Siniestros.Reglas.CalculadoraReserva` (2 métodos anclados al binario)
- Siguiente paso: Leer la decompilación, migrar las reglas y validarlas con pruebas de paridad contra este binario
