using System.Text.Json.Nodes;
using AdfEmulador;

namespace AdfEmulador.Pruebas;

public class ExpresionesTests
{
    private static ContextoExpresion Ctx(string fecha = "") => new()
    {
        Pipeline = new(StringComparer.OrdinalIgnoreCase)
        {
            ["parameters"] = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase) { ["Archivo"] = "a.csv", ["FechaProceso"] = fecha },
            ["RunId"] = "run-1",
        },
        Dataset = new(StringComparer.OrdinalIgnoreCase) { ["fileName"] = "b.csv" },
        Actividad = n => n == "Consolidar"
            ? new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
              { ["error"] = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase) { ["message"] = "boom" } }
            : null,
    };

    [Theory]
    [InlineData("texto plano", "texto plano")]
    [InlineData("@@literal", "@literal")]
    [InlineData("@pipeline().parameters.Archivo", "a.csv")]
    [InlineData("@dataset().fileName", "b.csv")]
    [InlineData("archivo @{pipeline().parameters.Archivo} run @{pipeline().RunId}", "archivo a.csv run run-1")]
    [InlineData("@concat('Consolidar falló: ', activity('Consolidar').error.message)", "Consolidar falló: boom")]
    [InlineData("@toUpper('it''s')", "IT'S")]
    [InlineData("@formatDateTime('2026-10-17T03:00:00Z', 'yyyy-MM-dd')", "2026-10-17")]
    public void Evalua(string expresion, string esperado) =>
        Assert.Equal(esperado, Expresiones.ATexto(Expresiones.Evaluar(expresion, Ctx())));

    [Fact]
    public void Usa_el_parametro_si_viene_informado()
    {
        const string e = "@if(empty(pipeline().parameters.FechaProceso), 'hoy', pipeline().parameters.FechaProceso)";
        Assert.Equal("2026-01-31", Expresiones.Evaluar(e, Ctx("2026-01-31")));
        Assert.Equal("hoy", Expresiones.Evaluar(e, Ctx()));
    }

    [Fact]
    public void Convierte_de_UTC_a_hora_de_Chile()
    {
        // 02:00 UTC del 18-10 sigue siendo 17-10 en Santiago: GETDATE() en el servidor on-premise daba el 17
        Assert.Equal("2026-10-17", Expresiones.Evaluar("@convertFromUtc('2026-10-18T02:00:00Z', 'Pacific SA Standard Time', 'yyyy-MM-dd')", Ctx()));
    }

    [Fact]
    public void Resuelve_objetos_Expression_de_las_definiciones() =>
        Assert.Equal("a.csv", Expresiones.Resolver(JsonNode.Parse("""{"value":"@pipeline().parameters.Archivo","type":"Expression"}"""), Ctx()));

    [Fact]
    public void Funcion_desconocida_da_error_claro() =>
        Assert.Contains("noExiste", Assert.Throws<ErrorExpresion>(() => Expresiones.Evaluar("@noExiste()", Ctx())).Message);
}
