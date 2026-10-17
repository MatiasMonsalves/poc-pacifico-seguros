using Azure.Identity;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.Extensions.Options;
using Pacifico.Polizas.Api.DataFactory;
using Pacifico.Polizas.Api.Datos;
using Pacifico.Polizas.Api.Endpoints;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddOpenApi();
builder.Services.AddProblemDetails();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.Configure<OpcionesDataFactory>(builder.Configuration.GetSection("DataFactory"));
builder.Services.Configure<OpcionesCotizacion>(builder.Configuration.GetSection("Cotizacion"));
builder.Services.Configure<OpcionesCargas>(builder.Configuration.GetSection("Cargas"));

builder.Services.AddSingleton(_ => new RepositorioSeguros(
    builder.Configuration.GetConnectionString("Seguros")
    ?? throw new InvalidOperationException("Falta ConnectionStrings:Seguros")));

builder.Services.AddTransient(_ => new AutenticacionAzureAd(new DefaultAzureCredential()));
var http = builder.Services.AddHttpClient<IClienteDataFactory, ClienteDataFactory>((sp, c) =>
{
    var o = sp.GetRequiredService<IOptions<OpcionesDataFactory>>().Value;
    c.BaseAddress = new Uri(o.BaseUrl.TrimEnd('/') + "/");
});
if (builder.Configuration.GetValue("DataFactory:UsarAzureAd", true))
    http.AddHttpMessageHandler<AutenticacionAzureAd>();

var app = builder.Build();

app.UseExceptionHandler(e => e.Run(async ctx =>
{
    var error = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;
    var (estado, titulo) = error switch
    {
        ArgumentException => (StatusCodes.Status400BadRequest, "Solicitud inválida"),
        ErrorDataFactory => (StatusCodes.Status502BadGateway, "Error al comunicarse con Azure Data Factory"),
        HttpRequestException => (StatusCodes.Status502BadGateway, "Azure Data Factory no responde"),
        _ => (StatusCodes.Status500InternalServerError, "Error interno"),
    };
    ctx.Response.StatusCode = estado;
    await Results.Problem(title: titulo, detail: estado == 500 ? null : error?.Message, statusCode: estado).ExecuteAsync(ctx);
}));

app.MapOpenApi();
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.MapPolizas();

app.Run();

public partial class Program;
