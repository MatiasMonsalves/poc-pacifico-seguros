namespace Pacifico.Polizas.Dominio;

public enum TipoSeguro { Auto, Hogar, Vida }

/// <summary>
/// Cálculo de prima migrado desde el componente COM legado Pacifico.Tarificador 2.3.1
/// (.NET Framework 4.8). Las reglas se recuperaron del binario con REA + ILSpy
/// (ver reingenieria/HALLAZGOS.md) y se verifican contra el binario en las pruebas de paridad.
/// </summary>
public static class Tarificador
{
    public const decimal PrimaMinima = 12.5m;
    public const decimal DescuentoSinSiniestros = 0.95m;
    public const decimal RecargoPorSiniestro = 0.15m;
    public const int MaxSiniestrosRecargo = 3;

    public static decimal CalcularPrima(TipoSeguro tipo, int edad, decimal sumaAsegurada, int siniestros)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(sumaAsegurada);
        ArgumentOutOfRangeException.ThrowIfNegative(siniestros);

        var prima = sumaAsegurada * Tasa(tipo) * FactorEdad(tipo, edad);
        prima *= siniestros == 0
            ? DescuentoSinSiniestros
            : 1m + RecargoPorSiniestro * Math.Min(siniestros, MaxSiniestrosRecargo);

        // El legado aplica la prima mínima después del ajuste por siniestralidad.
        prima = Math.Max(prima, PrimaMinima);

        // El legado usaba Math.Round(decimal, int), que redondea al par (bancario).
        // Se explicita para que no cambie por accidente: usp_RecalcularPrimas redondea distinto (hallazgo P1).
        return Math.Round(prima, 2, MidpointRounding.ToEven);
    }

    public static decimal Tasa(TipoSeguro tipo) => tipo switch
    {
        TipoSeguro.Auto => 0.045m,
        TipoSeguro.Hogar => 0.0035m,
        TipoSeguro.Vida => 0.006m,
        _ => throw new ArgumentOutOfRangeException(nameof(tipo), tipo, "Tipo de seguro no soportado"),
    };

    public static decimal FactorEdad(TipoSeguro tipo, int edad)
    {
        if (edad < 18)
            throw new ArgumentOutOfRangeException(nameof(edad), edad, "El asegurado debe ser mayor de edad");
        if (edad < 25) return 1.3m;
        if (edad <= 60) return 1m;
        return tipo == TipoSeguro.Vida ? 1.8m : 1.45m;
    }

    /// <summary>Equivale al <c>UCase(Trim(x))</c> del legado: acepta mayúsculas, minúsculas y espacios.</summary>
    public static TipoSeguro ParsearTipo(string? texto) => texto?.Trim().ToUpperInvariant() switch
    {
        "AUTO" => TipoSeguro.Auto,
        "HOGAR" => TipoSeguro.Hogar,
        "VIDA" => TipoSeguro.Vida,
        _ => throw new ArgumentException($"Tipo de seguro no soportado: {texto}", nameof(texto)),
    };
}
