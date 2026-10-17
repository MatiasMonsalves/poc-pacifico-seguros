namespace Pacifico.Polizas.Dominio;

public enum CalculoEdad
{
    /// <summary>Años cumplidos.</summary>
    Exacta,

    /// <summary>
    /// Como <c>DateDiff("yyyy", nacimiento, hoy)</c> de modConexion.bas: cuenta cambios de año
    /// calendario, por lo que suma un año antes del cumpleaños (hallazgo P9).
    /// </summary>
    Vb6DateDiff,
}

public static class Edad
{
    public static int Calcular(DateOnly nacimiento, DateOnly hoy, CalculoEdad modo) => modo switch
    {
        CalculoEdad.Vb6DateDiff => hoy.Year - nacimiento.Year,
        _ => hoy.Year - nacimiento.Year - (hoy < nacimiento.AddYears(hoy.Year - nacimiento.Year) ? 1 : 0),
    };
}
