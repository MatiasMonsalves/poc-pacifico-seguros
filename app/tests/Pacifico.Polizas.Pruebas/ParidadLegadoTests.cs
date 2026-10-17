using System.Reflection;
using Pacifico.Polizas.Dominio;

namespace Pacifico.Polizas.Pruebas;

/// <summary>
/// Ejecuta el binario legado Pacifico.Tarificador.dll (.NET Framework 4.8, el mismo que
/// analizó REA) y compara sus resultados con el Tarificador migrado a .NET 10.
/// REA marca la decompilación como inferencia; estas pruebas son la validación.
/// </summary>
public class ParidadLegadoTests
{
    private static readonly Lazy<(object Instancia, MethodInfo Calcular)> Legado = new(() =>
    {
        var ruta = Path.Combine(AppContext.BaseDirectory, "legado", "Pacifico.Tarificador.dll");
        var tipo = Assembly.LoadFrom(ruta).GetType("Pacifico.Tarificador.Tarificador", throwOnError: true)!;
        return (Activator.CreateInstance(tipo)!, tipo.GetMethod("CalcularPrima")!);
    });

    private static decimal CalcularLegado(string tipo, int edad, decimal suma, int siniestros)
    {
        try
        {
            return (decimal)Legado.Value.Calcular.Invoke(Legado.Value.Instancia, [tipo, edad, suma, siniestros])!;
        }
        catch (TargetInvocationException ex) when (ex.InnerException is not null)
        {
            throw ex.InnerException;
        }
    }

    public static TheoryData<string> Tipos => new("AUTO", "HOGAR", "VIDA");

    [Theory]
    [MemberData(nameof(Tipos))]
    public void Misma_prima_que_el_binario_legado(string tipo)
    {
        var diferencias = new List<string>();
        var casos = 0;
        foreach (var edad in Enumerable.Range(18, 73))
        foreach (var suma in new[] { 1m, 150m, 300m, 450.5m, 500m, 600m, 900m, 1234.56m, 3200m, 5000m, 25000m })
        foreach (var siniestros in Enumerable.Range(0, 6))
        {
            casos++;
            var legado = CalcularLegado(tipo, edad, suma, siniestros);
            var nuevo = Tarificador.CalcularPrima(Tarificador.ParsearTipo(tipo), edad, suma, siniestros);
            if (legado != nuevo) diferencias.Add($"{tipo} edad={edad} suma={suma} siniestros={siniestros}: legado={legado} nuevo={nuevo}");
        }
        Assert.True(casos > 4000);
        Assert.Empty(diferencias);
    }

    [Theory]
    [InlineData(" auto ")]
    [InlineData("Hogar")]
    [InlineData("vida")]
    public void Acepta_el_tipo_como_el_legado(string tipo) =>
        Assert.Equal(CalcularLegado(tipo, 40, 1000m, 1), Tarificador.CalcularPrima(Tarificador.ParsearTipo(tipo), 40, 1000m, 1));

    [Theory]
    [InlineData("MOTO", 40, 1000, 0)]   // tipo desconocido
    [InlineData("AUTO", 17, 1000, 0)]   // menor de edad
    [InlineData("AUTO", 40, 0, 0)]      // suma no positiva
    public void Rechaza_los_mismos_casos_que_el_legado(string tipo, int edad, int suma, int siniestros)
    {
        Assert.ThrowsAny<ArgumentException>(() => CalcularLegado(tipo, edad, suma, siniestros));
        Assert.ThrowsAny<ArgumentException>(() => Tarificador.CalcularPrima(Tarificador.ParsearTipo(tipo), edad, suma, siniestros));
    }
}
