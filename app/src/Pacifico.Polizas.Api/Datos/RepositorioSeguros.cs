using System.Data;
using Microsoft.Data.SqlClient;

namespace Pacifico.Polizas.Api.Datos;

public sealed record Cliente(int IdCliente, string Rut, string Nombre, DateOnly FechaNacimiento);

public sealed record Poliza(
    string NumPoliza, string TipoSeguro, decimal SumaAsegurada, decimal PrimaBase, decimal Prima,
    int Siniestros, DateOnly FechaInicio, DateOnly FechaTermino, string Estado);

/// <summary>
/// Acceso a la BD Seguros. Reemplaza el SQL concatenado de frmPolizas.frm
/// (hallazgo P3) por consultas parametrizadas.
/// </summary>
public sealed class RepositorioSeguros(string cadenaConexion)
{
    public async Task<Cliente?> ObtenerClienteAsync(int idCliente, CancellationToken ct)
    {
        await using var cn = await AbrirAsync(ct);
        await using var cmd = new SqlCommand(
            "SELECT IdCliente, Rut, Nombre, FechaNacimiento FROM dbo.Clientes WHERE IdCliente = @IdCliente", cn);
        cmd.Parameters.Add("@IdCliente", SqlDbType.Int).Value = idCliente;
        await using var r = await cmd.ExecuteReaderAsync(ct);
        return await r.ReadAsync(ct)
            ? new Cliente(r.GetInt32(0), r.GetString(1), r.GetString(2), DateOnly.FromDateTime(r.GetDateTime(3)))
            : null;
    }

    public async Task<IReadOnlyList<Poliza>> PolizasDeClienteAsync(int idCliente, CancellationToken ct)
    {
        await using var cn = await AbrirAsync(ct);
        await using var cmd = new SqlCommand("""
            SELECT NumPoliza, TipoSeguro, SumaAsegurada, PrimaBase, Prima, Siniestros, FechaInicio, FechaTermino, Estado
            FROM dbo.Polizas WHERE IdCliente = @IdCliente ORDER BY NumPoliza
            """, cn);
        cmd.Parameters.Add("@IdCliente", SqlDbType.Int).Value = idCliente;
        await using var r = await cmd.ExecuteReaderAsync(ct);
        var polizas = new List<Poliza>();
        while (await r.ReadAsync(ct))
            polizas.Add(new Poliza(r.GetString(0), r.GetString(1), r.GetDecimal(2), r.GetDecimal(3), r.GetDecimal(4),
                r.GetInt32(5), DateOnly.FromDateTime(r.GetDateTime(6)), DateOnly.FromDateTime(r.GetDateTime(7)), r.GetString(8)));
        return polizas;
    }

    public async Task RecalcularPrimasAsync(DateOnly fechaProceso, CancellationToken ct)
    {
        await using var cn = await AbrirAsync(ct);
        await using var cmd = new SqlCommand("dbo.usp_RecalcularPrimas", cn) { CommandType = CommandType.StoredProcedure };
        cmd.Parameters.Add("@FechaProceso", SqlDbType.Date).Value = fechaProceso.ToDateTime(TimeOnly.MinValue);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    private async Task<SqlConnection> AbrirAsync(CancellationToken ct)
    {
        var cn = new SqlConnection(cadenaConexion);
        await cn.OpenAsync(ct);
        return cn;
    }
}
