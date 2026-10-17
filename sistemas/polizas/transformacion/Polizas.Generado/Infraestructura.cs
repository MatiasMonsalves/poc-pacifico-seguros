// Generado por tools/vb62net: infraestructura común del código traducido desde VB6
using System.Data;
using System.Net.Http.Json;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.Options;

namespace Polizas.Generado;

/// <summary>Lógica VB6 que no se pudo traducir de forma mecánica. La API responde 501.</summary>
public sealed class PendienteDeMigrarException(string detalle) : Exception(detalle);

/// <summary>Reemplaza ADODB.Connection/Recordset/Command con consultas siempre parametrizadas.</summary>
public sealed class Db(string cadenaConexion)
{
    public async Task<List<Dictionary<string, object?>>> ConsultarAsync(string sql, params (string Nombre, object? Valor)[] parametros)
    {
        await using var cn = new SqlConnection(cadenaConexion);
        await cn.OpenAsync();
        await using var cmd = Comando(cn, sql, CommandType.Text, parametros);
        await using var r = await cmd.ExecuteReaderAsync();
        var filas = new List<Dictionary<string, object?>>();
        while (await r.ReadAsync())
        {
            var fila = new Dictionary<string, object?>();
            for (var i = 0; i < r.FieldCount; i++)
                fila[r.GetName(i)] = r.IsDBNull(i) ? null : r.GetValue(i);
            filas.Add(fila);
        }
        return filas;
    }

    public async Task EjecutarProcedimientoAsync(string nombre, params (string Nombre, object? Valor)[] parametros)
    {
        await using var cn = new SqlConnection(cadenaConexion);
        await cn.OpenAsync();
        await using var cmd = Comando(cn, nombre, CommandType.StoredProcedure, parametros);
        await cmd.ExecuteNonQueryAsync();
    }

    private static SqlCommand Comando(SqlConnection cn, string texto, CommandType tipo, (string Nombre, object? Valor)[] parametros)
    {
        var cmd = new SqlCommand(texto, cn) { CommandType = tipo };
        foreach (var (nombre, valor) in parametros)
            cmd.Parameters.AddWithValue(nombre, valor ?? DBNull.Value);
        return cmd;
    }
}

public sealed class OpcionesAdf
{
    public string BaseUrl { get; set; } = "https://management.azure.com";
    public string SubscriptionId { get; set; } = "";
    public string ResourceGroup { get; set; } = "";
    public string FactoryName { get; set; } = "";
    public string ApiVersion { get; set; } = "2018-06-01";
    /// <summary>Token de Entra ID para management.azure.com; vacío contra el emulador local.</summary>
    public string? Token { get; set; }
}

/// <summary>Reemplaza "Shell dtexec paquete.dtsx": ejecuta el pipeline equivalente en Azure Data Factory.</summary>
public sealed class AdfCliente(HttpClient http, IOptions<OpcionesAdf> opciones)
{
    public async Task<string> IniciarAsync(string pipeline, Dictionary<string, string?> parametros)
    {
        var o = opciones.Value;
        var url = $"{o.BaseUrl.TrimEnd('/')}/subscriptions/{o.SubscriptionId}/resourceGroups/{o.ResourceGroup}" +
                  $"/providers/Microsoft.DataFactory/factories/{o.FactoryName}/pipelines/{pipeline}/createRun?api-version={o.ApiVersion}";
        using var solicitud = new HttpRequestMessage(HttpMethod.Post, url) { Content = JsonContent.Create(parametros) };
        if (!string.IsNullOrEmpty(o.Token))
            solicitud.Headers.Authorization = new("Bearer", o.Token);
        using var respuesta = await http.SendAsync(solicitud);
        respuesta.EnsureSuccessStatusCode();
        var cuerpo = await respuesta.Content.ReadFromJsonAsync<Dictionary<string, string>>();
        return cuerpo!["runId"];
    }
}
