using System.Text.Json.Nodes;
using AdfEmulador;

// Emulador local de Azure Data Factory: expone el subconjunto del API REST de
// Azure Resource Manager que usa una aplicación para ejecutar y monitorear
// pipelines, con las mismas rutas que management.azure.com. Atiende varias
// factorías: una por sistema migrado.
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton<Ejecutor>();
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.DefaultIgnoreCondition =
    System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull);
var app = builder.Build();

const string factoria = "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.DataFactory/factories/{factoryName}";

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapGet(factoria + "/pipelines", (string factoryName, IConfiguration config) =>
    Abrir(config, factoryName) is { } f
        ? Results.Ok(new { value = f.Pipelines().Select(p => new { name = (string?)p["name"], properties = p["properties"] }) })
        : NoEncontrado("Factory", factoryName));

app.MapGet(factoria + "/pipelines/{pipelineName}", (string factoryName, string pipelineName, IConfiguration config) =>
    Abrir(config, factoryName) is not { } f ? NoEncontrado("Factory", factoryName)
    : f.Pipeline(pipelineName) is { } p ? Results.Ok(p) : NoEncontrado("Pipeline", pipelineName));

app.MapPost(factoria + "/pipelines/{pipelineName}/createRun", async (string factoryName, string pipelineName, HttpRequest req,
    IConfiguration config, Ejecutor ejecutor) =>
{
    if (Abrir(config, factoryName) is not { } f)
        return NoEncontrado("Factory", factoryName);
    if (f.Pipeline(pipelineName) is not { } definicion)
        return NoEncontrado("Pipeline", pipelineName);
    var parametros = req.ContentLength is > 0 || req.Headers.TransferEncoding.Count > 0
        ? (await JsonNode.ParseAsync(req.Body))?.AsObject()
        : null;
    var ejecucion = ejecutor.Iniciar(f, pipelineName, definicion, parametros);
    return Results.Ok(new { runId = ejecucion.RunId });
});

app.MapGet(factoria + "/pipelineruns/{runId}", (string runId, Ejecutor ejecutor) =>
    ejecutor.Obtener(runId) is { } e ? Results.Ok(e) : NoEncontrado("PipelineRun", runId));

app.MapPost(factoria + "/pipelineruns/{runId}/queryActivityruns", (string runId, Ejecutor ejecutor) =>
    ejecutor.Obtener(runId) is null
        ? NoEncontrado("PipelineRun", runId)
        : Results.Ok(new { value = ejecutor.Actividades(runId) }));

app.Run();

static Factoria? Abrir(IConfiguration config, string nombre)
{
    // El nombre se usa para armar una ruta: solo letras, números, '-' y '_' (como en ADF)
    if (!System.Text.RegularExpressions.Regex.IsMatch(nombre, "^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$"))
        return null;
    var f = new Factoria(config, nombre);
    return f.Existe ? f : null;
}

static IResult NoEncontrado(string tipo, string nombre) =>
    Results.NotFound(new { error = new { code = "ResourceNotFound", message = $"{tipo} '{nombre}' no existe" } });
