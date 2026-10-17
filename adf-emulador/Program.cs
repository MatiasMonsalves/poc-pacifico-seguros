using System.Text.Json.Nodes;
using AdfEmulador;

// Emulador local de Azure Data Factory: expone el subconjunto del API REST de
// Azure Resource Manager que usa una aplicación para ejecutar y monitorear
// pipelines, con las mismas rutas que management.azure.com.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton<Factoria>();
builder.Services.AddSingleton<Ejecutor>();
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.DefaultIgnoreCondition =
    System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull);
var app = builder.Build();

const string factoria = "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.DataFactory/factories/{factoryName}";

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet(factoria + "/pipelines", (Factoria f) =>
    Results.Ok(new { value = f.Pipelines().Select(p => new { name = (string?)p["name"], properties = p["properties"] }) }));

app.MapGet(factoria + "/pipelines/{pipelineName}", (string pipelineName, Factoria f) =>
    f.Pipeline(pipelineName) is { } p ? Results.Ok(p) : NoEncontrado("Pipeline", pipelineName));

app.MapPost(factoria + "/pipelines/{pipelineName}/createRun", async (string pipelineName, HttpRequest req, Factoria f, Ejecutor ejecutor) =>
{
    if (f.Pipeline(pipelineName) is not { } definicion)
        return NoEncontrado("Pipeline", pipelineName);
    var parametros = req.ContentLength is > 0 || req.Headers.TransferEncoding.Count > 0
        ? (await JsonNode.ParseAsync(req.Body))?.AsObject()
        : null;
    var ejecucion = ejecutor.Iniciar(pipelineName, definicion, parametros);
    return Results.Ok(new { runId = ejecucion.RunId });
});

app.MapGet(factoria + "/pipelineruns/{runId}", (string runId, Ejecutor ejecutor) =>
    ejecutor.Obtener(runId) is { } e ? Results.Ok(e) : NoEncontrado("PipelineRun", runId));

app.MapPost(factoria + "/pipelineruns/{runId}/queryActivityruns", (string runId, Ejecutor ejecutor) =>
    ejecutor.Obtener(runId) is null
        ? NoEncontrado("PipelineRun", runId)
        : Results.Ok(new { value = ejecutor.Actividades(runId) }));

app.Run();

static IResult NoEncontrado(string tipo, string nombre) =>
    Results.NotFound(new { error = new { code = "ResourceNotFound", message = $"{tipo} '{nombre}' no existe en la factoría" } });
