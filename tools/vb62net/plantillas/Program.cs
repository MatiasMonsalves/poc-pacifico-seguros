// Generado por tools/vb62net
using Microsoft.AspNetCore.Diagnostics;
using __NS__;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddOpenApi();
builder.Services.AddProblemDetails();
builder.Services.AddScoped(_ => new Db(builder.Configuration.GetConnectionString("Legado")
    ?? throw new InvalidOperationException("Falta ConnectionStrings:Legado")));
builder.Services.Configure<OpcionesAdf>(builder.Configuration.GetSection("DataFactory"));
builder.Services.AddHttpClient<AdfCliente>();

var app = builder.Build();

app.UseExceptionHandler(e => e.Run(async ctx =>
{
    var error = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;
    var (estado, titulo) = error switch
    {
        PendienteDeMigrarException => (StatusCodes.Status501NotImplemented, "Pendiente de migrar"),
        FormatException or InvalidCastException or OverflowException => (StatusCodes.Status400BadRequest, "Dato inválido"),
        // 245/8114: SQL Server no pudo convertir el parámetro (por ejemplo texto donde se espera un número)
        Microsoft.Data.SqlClient.SqlException { Number: 245 or 8114 } => (StatusCodes.Status400BadRequest, "Dato inválido"),
        HttpRequestException => (StatusCodes.Status502BadGateway, "Azure Data Factory no responde"),
        _ => (StatusCodes.Status500InternalServerError, "Error interno"),
    };
    ctx.Response.StatusCode = estado;
    await Results.Problem(title: titulo, detail: estado == 500 ? null : error?.Message, statusCode: estado).ExecuteAsync(ctx);
}));

app.MapOpenApi();
app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.MapEndpointsGenerados();
app.Run();
