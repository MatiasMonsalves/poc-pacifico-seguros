using System.Net.Http.Headers;
using System.Text.Json;
using Azure.Core;
using Microsoft.Extensions.Options;

namespace Pacifico.Polizas.Api.DataFactory;

public sealed class OpcionesDataFactory
{
    /// <summary>https://management.azure.com en Azure; la URL del emulador en local.</summary>
    public string BaseUrl { get; set; } = "https://management.azure.com";
    public string SubscriptionId { get; set; } = "";
    public string ResourceGroup { get; set; } = "";
    public string FactoryName { get; set; } = "";
    public string PipelineCarga { get; set; } = "PL_CargaPolizas";
    public string ApiVersion { get; set; } = "2018-06-01";
    /// <summary>Obtiene un token de Entra ID (DefaultAzureCredential / identidad administrada). Se apaga para el emulador.</summary>
    public bool UsarAzureAd { get; set; } = true;
}

public sealed record ErrorActividad(string? ErrorCode, string? Message, string? FailureType);

public sealed record EjecucionPipeline(
    string RunId, string PipelineName, string Status, DateTimeOffset? RunStart, DateTimeOffset? RunEnd,
    long? DurationInMs, string? Message);

public sealed record EjecucionActividad(
    string ActivityName, string ActivityType, string Status, DateTimeOffset? ActivityRunStart,
    DateTimeOffset? ActivityRunEnd, long? DurationInMs, ErrorActividad? Error, JsonElement? Output);

public interface IClienteDataFactory
{
    Task<string> IniciarAsync(string pipeline, IReadOnlyDictionary<string, string> parametros, CancellationToken ct);
    Task<EjecucionPipeline?> ObtenerAsync(string runId, CancellationToken ct);
    Task<IReadOnlyList<EjecucionActividad>> ActividadesAsync(string runId, CancellationToken ct);
}

/// <summary>
/// Cliente del API REST de Azure Data Factory (Microsoft.DataFactory, api-version 2018-06-01).
/// Es el reemplazo del <c>Shell dtexec</c> de la aplicación VB6: dispara el pipeline y
/// permite seguir su estado y el de cada actividad.
/// </summary>
public sealed class ClienteDataFactory(HttpClient http, IOptions<OpcionesDataFactory> opciones) : IClienteDataFactory
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private readonly OpcionesDataFactory _o = opciones.Value;

    private string Factoria =>
        $"subscriptions/{_o.SubscriptionId}/resourceGroups/{_o.ResourceGroup}/providers/Microsoft.DataFactory/factories/{_o.FactoryName}";

    public async Task<string> IniciarAsync(string pipeline, IReadOnlyDictionary<string, string> parametros, CancellationToken ct)
    {
        var url = $"{Factoria}/pipelines/{Uri.EscapeDataString(pipeline)}/createRun?api-version={_o.ApiVersion}";
        using var respuesta = await http.PostAsJsonAsync(url, parametros, Json, ct);
        await AsegurarExito(respuesta, ct);
        var cuerpo = await respuesta.Content.ReadFromJsonAsync<JsonElement>(Json, ct);
        return cuerpo.GetProperty("runId").GetString()!;
    }

    public async Task<EjecucionPipeline?> ObtenerAsync(string runId, CancellationToken ct)
    {
        using var respuesta = await http.GetAsync($"{Factoria}/pipelineruns/{Uri.EscapeDataString(runId)}?api-version={_o.ApiVersion}", ct);
        if (respuesta.StatusCode == System.Net.HttpStatusCode.NotFound) return null;
        await AsegurarExito(respuesta, ct);
        return await respuesta.Content.ReadFromJsonAsync<EjecucionPipeline>(Json, ct);
    }

    public async Task<IReadOnlyList<EjecucionActividad>> ActividadesAsync(string runId, CancellationToken ct)
    {
        // El API exige una ventana de tiempo para la consulta de actividades.
        var filtro = new { lastUpdatedAfter = DateTimeOffset.UtcNow.AddDays(-7), lastUpdatedBefore = DateTimeOffset.UtcNow.AddDays(1) };
        using var respuesta = await http.PostAsJsonAsync(
            $"{Factoria}/pipelineruns/{Uri.EscapeDataString(runId)}/queryActivityruns?api-version={_o.ApiVersion}", filtro, Json, ct);
        await AsegurarExito(respuesta, ct);
        var cuerpo = await respuesta.Content.ReadFromJsonAsync<JsonElement>(Json, ct);
        return cuerpo.GetProperty("value").Deserialize<List<EjecucionActividad>>(Json) ?? [];
    }

    private static async Task AsegurarExito(HttpResponseMessage respuesta, CancellationToken ct)
    {
        if (respuesta.IsSuccessStatusCode) return;
        var detalle = await respuesta.Content.ReadAsStringAsync(ct);
        throw new ErrorDataFactory((int)respuesta.StatusCode, detalle);
    }
}

public sealed class ErrorDataFactory(int estadoHttp, string detalle)
    : Exception($"Azure Data Factory respondió {estadoHttp}: {detalle}")
{
    public int EstadoHttp { get; } = estadoHttp;
}

/// <summary>Agrega el token de Entra ID para management.azure.com.</summary>
public sealed class AutenticacionAzureAd(TokenCredential credencial) : DelegatingHandler
{
    private static readonly TokenRequestContext Contexto = new(["https://management.azure.com/.default"]);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var token = await credencial.GetTokenAsync(Contexto, ct);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        return await base.SendAsync(request, ct);
    }
}
