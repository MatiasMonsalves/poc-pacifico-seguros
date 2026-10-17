// Generado por tools/vb62net: funciones de VB6 con su semántica original
using System.Globalization;

namespace Polizas.Generado;

public static class Vb6
{
    /// <summary>
    /// VB6 convierte texto ↔ número/fecha con la configuración regional del equipo. En Chile (es-CL)
    /// la coma es el separador decimal: CCur("1,5") = 1,5 y CCur("1.5") = 15. Ajustar si los equipos usaban otra.
    /// </summary>
    public static CultureInfo Cultura { get; set; } = CultureInfo.GetCultureInfo("es-CL");

    public static DateTime Date => DateTime.Today;
    public static DateTime Now => DateTime.Now;

    /// <summary>DateDiff cuenta los límites de período cruzados, no el tiempo transcurrido: DateDiff("yyyy", 31-12-2000, 01-01-2001) = 1.</summary>
    public static long DateDiff(string intervalo, object desde, object hasta)
    {
        var a = CDate(desde);
        var b = CDate(hasta);
        return intervalo.ToLowerInvariant() switch
        {
            "yyyy" => b.Year - a.Year,
            "q" => (b.Year - a.Year) * 4 + (b.Month - 1) / 3 - (a.Month - 1) / 3,
            "m" => (b.Year - a.Year) * 12 + b.Month - a.Month,
            "d" or "y" => (long)(b.Date - a.Date).TotalDays,
            "ww" or "w" => (long)Math.Floor((b.Date - a.Date).TotalDays / 7),
            "h" => (long)(new DateTime(b.Year, b.Month, b.Day, b.Hour, 0, 0) - new DateTime(a.Year, a.Month, a.Day, a.Hour, 0, 0)).TotalHours,
            "n" => (long)(b.AddSeconds(-b.Second) - a.AddSeconds(-a.Second)).TotalMinutes,
            "s" => (long)(b - a).TotalSeconds,
            _ => throw new ArgumentException($"Intervalo de DateDiff no soportado: {intervalo}"),
        };
    }

    public static DateTime DateAdd(string intervalo, double numero, object fecha)
    {
        var f = CDate(fecha);
        return intervalo.ToLowerInvariant() switch
        {
            "yyyy" => f.AddYears((int)numero),
            "m" => f.AddMonths((int)numero),
            "d" or "y" => f.AddDays(numero),
            "h" => f.AddHours(numero),
            "n" => f.AddMinutes(numero),
            "s" => f.AddSeconds(numero),
            _ => throw new ArgumentException($"Intervalo de DateAdd no soportado: {intervalo}"),
        };
    }

    /// <summary>Format de VB6: en fechas "mm" es mes y "nn" minutos; en números el formato es compatible con .NET.</summary>
    public static string Format(object? valor, string formato = "")
    {
        if (valor is DateTime f)
        {
            var net = formato.Replace("nn", "\u0001").Replace("mm", "MM").Replace("\u0001", "mm").Replace("hh", "HH");
            return f.ToString(net.Length == 0 ? "G" : net, Cultura);
        }
        return valor is IFormattable n ? n.ToString(formato, Cultura) : Convert.ToString(valor, Cultura) ?? "";
    }

    // CInt/CLng/Round de VB6 redondean al par (bancario): CInt(2.5) = 2, CInt(3.5) = 4
    public static short CInt(object? v) => checked((short)Math.Round(Convert.ToDecimal(v, Cultura), MidpointRounding.ToEven));
    public static int CLng(object? v) => checked((int)Math.Round(Convert.ToDecimal(v, Cultura), MidpointRounding.ToEven));
    public static decimal CCur(object? v) => Math.Round(Convert.ToDecimal(v, Cultura), 4, MidpointRounding.ToEven);
    public static double CDbl(object? v) => Convert.ToDouble(v, Cultura);
    public static string CStr(object? v) => v is DateTime f ? f.ToString("G", Cultura) : Convert.ToString(v, Cultura) ?? "";
    public static DateTime CDate(object? v) => v is DateTime f ? f : DateTime.Parse(Convert.ToString(v, Cultura)!, Cultura);
    public static double Round(double v, int decimales = 0) => Math.Round(v, decimales, MidpointRounding.ToEven);
    public static decimal Round(decimal v, int decimales = 0) => Math.Round(v, decimales, MidpointRounding.ToEven);

    /// <summary>Val ignora la configuración regional: solo reconoce el punto decimal y se detiene en el primer carácter inválido.</summary>
    public static double Val(object? v)
    {
        var texto = (Convert.ToString(v, CultureInfo.InvariantCulture) ?? "").Replace(" ", "");
        var largo = 0;
        while (largo < texto.Length && (char.IsDigit(texto[largo]) || (largo == 0 && texto[largo] is '-' or '+') || texto[largo] == '.'))
            largo++;
        return double.TryParse(texto[..largo], NumberStyles.Float, CultureInfo.InvariantCulture, out var r) ? r : 0;
    }

    public static string Trim(object? v) => CStr(v).Trim(' ');
    public static string UCase(object? v) => CStr(v).ToUpper(Cultura);
    public static string LCase(object? v) => CStr(v).ToLower(Cultura);
    public static int Len(object? v) => CStr(v).Length;
    public static string Left(object? v, int n) => CStr(v)[..Math.Min(n, CStr(v).Length)];
    public static string Right(object? v, int n) { var s = CStr(v); return s[Math.Max(0, s.Length - n)..]; }
    public static string Mid(object? v, int inicio, int? largo = null)
    {
        var s = CStr(v);
        if (inicio > s.Length) return "";
        var desde = inicio - 1;
        return largo is null ? s[desde..] : s.Substring(desde, Math.Min(largo.Value, s.Length - desde));
    }
    public static bool IsNull(object? v) => v is null or DBNull;
}
