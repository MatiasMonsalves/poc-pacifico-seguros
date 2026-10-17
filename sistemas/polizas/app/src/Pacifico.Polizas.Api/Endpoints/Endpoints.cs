using Microsoft.Extensions.Options;
using Pacifico.Polizas.Api.DataFactory;
using Pacifico.Polizas.Api.Datos;
using Pacifico.Polizas.Dominio;

namespace Pacifico.Polizas.Api.Endpoints;

public sealed class OpcionesCotizacion
{
    /// <summary>Vb6DateDiff mantiene el resultado del sistema legado; Exacta corrige el hallazgo P9.</summary>
    public CalculoEdad CalculoEdad { get; set; } = CalculoEdad.Vb6DateDiff;
    public string ZonaHoraria { get; set; } = "America/Santiago";
}

public sealed class OpcionesCargas
{
    public int TiempoMaximoEsperaSegundos { get; set; } = 120;
    public int IntervaloConsultaSegundos { get; set; } = 2;
}

public sealed record CotizacionSolicitud(int IdCliente, string TipoSeguro, decimal SumaAsegurada, int Siniestros);
public sealed record CotizacionRespuesta(
    int IdCliente, int Edad, string CalculoEdad, string TipoSeguro, decimal SumaAsegurada, int Siniestros, decimal Prima, string Moneda);

public sealed record RecalculoSolicitud(DateOnly? FechaProceso);
public sealed record CargaSolicitud(string Archivo, DateOnly? FechaProceso, bool Esperar = false);

public sealed record ActividadCarga(string Nombre, string Tipo, string Estado, long? DuracionMs, string? Error, object? Salida);
public sealed record EstadoCarga(
    string RunId, string Pipeline, string Estado, bool Terminada, string? Mensaje,
    DateTimeOffset? Inicio, DateTimeOffset? Fin, long? DuracionMs, IReadOnlyList<ActividadCarga> Actividades);

public static class Endpoints
{
    public static void MapPolizas(this IEndpointRouteBuilder app)
    {
        var api = app.MapGroup("/api");

        // Reemplaza cmdBuscar_Click
        api.MapGet("/clientes/{idCliente:int}/polizas", async (int idCliente, RepositorioSeguros repo, CancellationToken ct) =>
            await repo.ObtenerClienteAsync(idCliente, ct) is { } cliente
                ? Results.Ok(new { cliente, polizas = await repo.PolizasDeClienteAsync(idCliente, ct) })
                : Results.Problem($"No existe el cliente {idCliente}", statusCode: 404))
            .WithSummary("Pólizas de un cliente");

        // Reemplaza cmdCotizar_Click + el componente COM Pacifico.Tarificador
        api.MapPost("/cotizaciones", async (CotizacionSolicitud s, RepositorioSeguros repo, IOptions<OpcionesCotizacion> op,
                TimeProvider reloj, CancellationToken ct) =>
            {
                if (await repo.ObtenerClienteAsync(s.IdCliente, ct) is not { } cliente)
                    return Results.Problem($"No existe el cliente {s.IdCliente}", statusCode: 404);
                var tipo = Tarificador.ParsearTipo(s.TipoSeguro);
                var edad = Edad.Calcular(cliente.FechaNacimiento, Hoy(reloj, op.Value.ZonaHoraria), op.Value.CalculoEdad);
                var prima = Tarificador.CalcularPrima(tipo, edad, s.SumaAsegurada, s.Siniestros);
                return Results.Ok(new CotizacionRespuesta(cliente.IdCliente, edad, op.Value.CalculoEdad.ToString(),
                    tipo.ToString().ToUpperInvariant(), s.SumaAsegurada, s.Siniestros, prima, "UF"));
            })
            .WithSummary("Cotiza la prima anual");

        // Reemplaza cmdRecalcular_Click
        api.MapPost("/primas/recalcular", async (RecalculoSolicitud? s, RepositorioSeguros repo, IOptions<OpcionesCotizacion> op,
                TimeProvider reloj, CancellationToken ct) =>
            {
                var fecha = s?.FechaProceso ?? Hoy(reloj, op.Value.ZonaHoraria);
                await repo.RecalcularPrimasAsync(fecha, ct);
                return Results.Ok(new { fechaProceso = fecha, recalculado = true });
            })
            .WithSummary("Recalcula primas vigentes (usp_RecalcularPrimas)");

        // Reemplaza cmdCargar_Click (Shell dtexec): dispara el pipeline de ADF y permite seguirlo
        api.MapPost("/cargas", async (CargaSolicitud s, IClienteDataFactory adf, IOptions<OpcionesDataFactory> opAdf,
                IOptions<OpcionesCargas> opCargas, CancellationToken ct) =>
            {
                if (string.IsNullOrWhiteSpace(s.Archivo) || s.Archivo.Contains("..") || s.Archivo.IndexOfAny(['/', '\\']) >= 0)
                    return Results.Problem("Indique solo el nombre del archivo en el contenedor 'entrada'", statusCode: 400);

                var parametros = new Dictionary<string, string>
                {
                    ["Archivo"] = s.Archivo,
                    ["FechaProceso"] = s.FechaProceso?.ToString("yyyy-MM-dd") ?? "",
                };
                var runId = await adf.IniciarAsync(opAdf.Value.PipelineCarga, parametros, ct);
                if (!s.Esperar)
                    return Results.Accepted($"/api/cargas/{runId}", new { runId, estado = "Queued" });

                var limite = DateTimeOffset.UtcNow.AddSeconds(opCargas.Value.TiempoMaximoEsperaSegundos);
                EstadoCarga estado;
                do
                {
                    await Task.Delay(TimeSpan.FromSeconds(opCargas.Value.IntervaloConsultaSegundos), ct);
                    estado = (await Estado(adf, runId, ct))!;
                } while (!estado.Terminada && DateTimeOffset.UtcNow < limite);
                return Results.Ok(estado);
            })
            .WithSummary("Ejecuta la carga de pólizas en Azure Data Factory");

        api.MapGet("/cargas/{runId}", async (string runId, IClienteDataFactory adf, CancellationToken ct) =>
                await Estado(adf, runId, ct) is { } estado ? Results.Ok(estado) : Results.Problem($"No existe la ejecución {runId}", statusCode: 404))
            .WithSummary("Estado de una carga y de cada actividad del pipeline");
    }

    private static async Task<EstadoCarga?> Estado(IClienteDataFactory adf, string runId, CancellationToken ct)
    {
        if (await adf.ObtenerAsync(runId, ct) is not { } run) return null;
        var actividades = await adf.ActividadesAsync(runId, ct);
        return new EstadoCarga(run.RunId, run.PipelineName, run.Status,
            run.Status is "Succeeded" or "Failed" or "Cancelled", string.IsNullOrEmpty(run.Message) ? null : run.Message,
            run.RunStart, run.RunEnd, run.DurationInMs,
            actividades.OrderBy(a => a.ActivityRunStart ?? DateTimeOffset.MaxValue)
                .Select(a => new ActividadCarga(a.ActivityName, a.ActivityType, a.Status, a.DurationInMs, a.Error?.Message is { Length: > 0 } m ? m : null, a.Output))
                .ToList());
    }

    private static DateOnly Hoy(TimeProvider reloj, string zona) =>
        DateOnly.FromDateTime(TimeZoneInfo.ConvertTime(reloj.GetUtcNow(), TimeZoneInfo.FindSystemTimeZoneById(zona)).DateTime);
}
