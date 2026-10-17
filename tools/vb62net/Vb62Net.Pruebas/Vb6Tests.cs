using Polizas.Generado;

namespace Vb62Net.Pruebas;

/// <summary>El módulo Vb6 debe comportarse como el runtime de VB6, no como .NET.</summary>
public class Vb6Tests
{
    [Fact]
    public void DateDiff_cuenta_cambios_de_anio_no_anios_cumplidos()
    {
        Assert.Equal(1, Vb6.DateDiff("yyyy", new DateTime(2000, 12, 31), new DateTime(2001, 1, 1)));
        Assert.Equal(25, Vb6.DateDiff("yyyy", new DateTime(2001, 12, 20), new DateTime(2026, 10, 17)));
    }

    [Fact]
    public void DateDiff_meses_y_dias()
    {
        Assert.Equal(1, Vb6.DateDiff("m", new DateTime(2026, 1, 31), new DateTime(2026, 2, 1)));
        Assert.Equal(1, Vb6.DateDiff("d", new DateTime(2026, 1, 31, 23, 59, 0), new DateTime(2026, 2, 1, 0, 1, 0)));
    }

    [Theory]
    [InlineData("2,5", 2)]
    [InlineData("3,5", 4)]
    [InlineData("-2,5", -2)]
    public void CInt_redondea_al_par(string valor, short esperado) => Assert.Equal(esperado, Vb6.CInt(valor));

    [Fact]
    public void CInt_desborda_como_el_Integer_de_16_bits() => Assert.Throws<OverflowException>(() => Vb6.CInt("40000"));

    [Fact]
    public void CCur_usa_la_configuracion_regional_chilena()
    {
        Assert.Equal(1.5m, Vb6.CCur("1,5"));
        Assert.Equal(1500m, Vb6.CCur("1.500"));
    }

    [Fact]
    public void Val_ignora_la_configuracion_regional_y_corta_en_el_primer_caracter_invalido()
    {
        Assert.Equal(1.5, Vb6.Val("1.5abc"));
        Assert.Equal(1, Vb6.Val("1,5"));
    }

    [Fact]
    public void Format_de_fecha_usa_mm_como_mes() =>
        Assert.Equal("2026-10-17", Vb6.Format(new DateTime(2026, 10, 17, 8, 30, 0), "yyyy-mm-dd"));

    [Fact]
    public void Mid_Left_Right_con_indices_de_VB6()
    {
        Assert.Equal("cde", Vb6.Mid("abcdef", 3, 3));
        Assert.Equal("ab", Vb6.Left("abcdef", 2));
        Assert.Equal("ef", Vb6.Right("abcdef", 2));
        Assert.Equal("", Vb6.Mid("abc", 10));
    }
}

public class ModulosTraducidosTests
{
    [Fact]
    public void CalcularEdad_traducida_conserva_el_comportamiento_de_DateDiff()
    {
        // Mismo resultado que modConexion.CalcularEdad en VB6 (hallazgo P9): suma un año antes del cumpleaños
        // Nacido el 31-12 de hace 30 años: DateDiff da 30 cualquier día del año, aunque los años cumplidos sean 29
        var nacimiento = new DateTime(DateTime.Today.Year - 30, 12, 31);
        Assert.Equal(30, Modulos.CalcularEdad(nacimiento));
    }
}
