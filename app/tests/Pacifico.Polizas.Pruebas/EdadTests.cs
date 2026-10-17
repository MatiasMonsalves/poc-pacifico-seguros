using Pacifico.Polizas.Dominio;

namespace Pacifico.Polizas.Pruebas;

public class EdadTests
{
    private static readonly DateOnly Hoy = new(2026, 10, 17);

    [Fact]
    public void Exacta_cuenta_anios_cumplidos() =>
        Assert.Equal(24, Edad.Calcular(new DateOnly(2001, 12, 20), Hoy, CalculoEdad.Exacta));

    [Fact]
    public void Vb6DateDiff_suma_un_anio_antes_del_cumpleanios() =>
        Assert.Equal(25, Edad.Calcular(new DateOnly(2001, 12, 20), Hoy, CalculoEdad.Vb6DateDiff));

    [Fact]
    public void Ambas_coinciden_despues_del_cumpleanios()
    {
        var nacimiento = new DateOnly(1999, 3, 14);
        Assert.Equal(Edad.Calcular(nacimiento, Hoy, CalculoEdad.Exacta), Edad.Calcular(nacimiento, Hoy, CalculoEdad.Vb6DateDiff));
    }

    [Fact]
    public void Nacido_un_29_de_febrero_cumple_el_28_en_anios_no_bisiestos()
    {
        Assert.Equal(24, Edad.Calcular(new DateOnly(2000, 2, 29), new DateOnly(2025, 2, 27), CalculoEdad.Exacta));
        Assert.Equal(25, Edad.Calcular(new DateOnly(2000, 2, 29), new DateOnly(2025, 2, 28), CalculoEdad.Exacta));
    }
}
