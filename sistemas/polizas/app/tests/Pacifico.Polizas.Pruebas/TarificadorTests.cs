using Pacifico.Polizas.Dominio;

namespace Pacifico.Polizas.Pruebas;

public class TarificadorTests
{
    [Theory]
    [InlineData(TipoSeguro.Auto, 40, 1000, 0, 42.75)]   // 1000 × 4,5 % × 0,95
    [InlineData(TipoSeguro.Hogar, 40, 5000, 1, 20.12)]  // 5000 × 0,35 % × 1,15 = 20,125 → al par (2 es par)
    [InlineData(TipoSeguro.Vida, 65, 2000, 3, 31.32)]   // 2000 × 0,6 % × 1,8 × 1,45
    [InlineData(TipoSeguro.Auto, 22, 300, 5, 25.45)]    // tope de 3 siniestros: 300 × 4,5 % × 1,3 × 1,45 = 25,4475
    public void Calcula_la_prima(TipoSeguro tipo, int edad, decimal suma, int siniestros, decimal esperado) =>
        Assert.Equal(esperado, Tarificador.CalcularPrima(tipo, edad, suma, siniestros));

    [Fact]
    public void Aplica_la_prima_minima_despues_del_ajuste_por_siniestros() =>
        Assert.Equal(12.5m, Tarificador.CalcularPrima(TipoSeguro.Hogar, 40, 1000m, 1));

    [Fact]
    public void Redondea_al_par_como_el_legado_y_no_como_TSQL()
    {
        // 600 × 4,5 % × 1,3 × 0,95 = 33,345: el legado da 33,34; ROUND(33.345, 2) de SQL Server da 33,35 (hallazgo P1)
        Assert.Equal(33.34m, Tarificador.CalcularPrima(TipoSeguro.Auto, 22, 600m, 0));
    }

    [Theory]
    [InlineData(18, 1.3)]
    [InlineData(24, 1.3)]
    [InlineData(25, 1.0)]
    [InlineData(60, 1.0)]
    [InlineData(61, 1.45)]
    public void Factor_por_edad(int edad, decimal factor) =>
        Assert.Equal(factor, Tarificador.FactorEdad(TipoSeguro.Auto, edad));

    [Fact]
    public void Vida_mayor_de_60_tiene_factor_propio() =>
        Assert.Equal(1.8m, Tarificador.FactorEdad(TipoSeguro.Vida, 61));

    [Fact]
    public void No_acepta_tipos_numericos() =>
        Assert.Throws<ArgumentException>(() => Tarificador.ParsearTipo("1"));
}
