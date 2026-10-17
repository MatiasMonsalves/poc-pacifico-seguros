using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using Pacifico.Polizas.Api.DataFactory;

namespace Pacifico.Polizas.Pruebas;

public class ClienteDataFactoryTests
{
    private const string Factoria = "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DataFactory/factories/adf1";

    private sealed class Servidor(Func<HttpRequestMessage, string, (HttpStatusCode, string)> responder) : HttpMessageHandler
    {
        public List<(HttpMethod Metodo, string Url, string Cuerpo)> Solicitudes { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var cuerpo = request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct);
            Solicitudes.Add((request.Method, request.RequestUri!.PathAndQuery, cuerpo));
            var (estado, json) = responder(request, cuerpo);
            return new HttpResponseMessage(estado) { Content = new StringContent(json, Encoding.UTF8, "application/json") };
        }
    }

    private static (ClienteDataFactory, Servidor) Crear(Func<HttpRequestMessage, string, (HttpStatusCode, string)> responder)
    {
        var servidor = new Servidor(responder);
        var http = new HttpClient(servidor) { BaseAddress = new Uri("https://adf.test/") };
        var opciones = Options.Create(new OpcionesDataFactory { SubscriptionId = "sub1", ResourceGroup = "rg1", FactoryName = "adf1" });
        return (new ClienteDataFactory(http, opciones), servidor);
    }

    [Fact]
    public async Task CreateRun_usa_la_ruta_ARM_y_envia_los_parametros()
    {
        var (cliente, servidor) = Crear((_, _) => (HttpStatusCode.OK, """{"runId":"abc-123"}"""));

        var runId = await cliente.IniciarAsync("PL_CargaPolizas", new Dictionary<string, string> { ["Archivo"] = "a.csv" }, TestContext.Current.CancellationToken);

        Assert.Equal("abc-123", runId);
        var (metodo, url, cuerpo) = Assert.Single(servidor.Solicitudes);
        Assert.Equal(HttpMethod.Post, metodo);
        Assert.Equal($"{Factoria}/pipelines/PL_CargaPolizas/createRun?api-version=2018-06-01", url);
        Assert.Equal("a.csv", JsonDocument.Parse(cuerpo).RootElement.GetProperty("Archivo").GetString());
    }

    [Fact]
    public async Task Lee_el_estado_y_las_actividades()
    {
        var (cliente, servidor) = Crear((req, _) => req.Method == HttpMethod.Get
            ? (HttpStatusCode.OK, """{"runId":"r1","pipelineName":"PL_CargaPolizas","status":"Failed","message":"Operation on target X failed"}""")
            : (HttpStatusCode.OK, """{"value":[{"activityName":"Consolidar","activityType":"SqlServerStoredProcedure","status":"Failed","error":{"errorCode":"2402","message":"Sql error"}}]}"""));

        var run = await cliente.ObtenerAsync("r1", TestContext.Current.CancellationToken);
        var actividades = await cliente.ActividadesAsync("r1", TestContext.Current.CancellationToken);

        Assert.Equal("Failed", run!.Status);
        Assert.Equal("Sql error", Assert.Single(actividades).Error!.Message);
        Assert.EndsWith("/pipelineruns/r1/queryActivityruns?api-version=2018-06-01", servidor.Solicitudes[1].Url);
        Assert.Contains("lastUpdatedAfter", servidor.Solicitudes[1].Cuerpo);
    }

    [Fact]
    public async Task Run_inexistente_devuelve_null() =>
        Assert.Null(await Crear((_, _) => (HttpStatusCode.NotFound, "{}")).Item1.ObtenerAsync("x", TestContext.Current.CancellationToken));

    [Fact]
    public async Task Error_del_servicio_se_informa_con_su_detalle()
    {
        var (cliente, _) = Crear((_, _) => (HttpStatusCode.Forbidden, """{"error":{"code":"AuthorizationFailed"}}"""));
        var ex = await Assert.ThrowsAsync<ErrorDataFactory>(() => cliente.IniciarAsync("PL", new Dictionary<string, string>(), TestContext.Current.CancellationToken));
        Assert.Equal(403, ex.EstadoHttp);
        Assert.Contains("AuthorizationFailed", ex.Message);
    }
}
