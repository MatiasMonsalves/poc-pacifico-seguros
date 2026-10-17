using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace AdfEmulador;

/// <summary>Datos que ven las expresiones: pipeline(), dataset() y activity().</summary>
public sealed class ContextoExpresion
{
    public required Dictionary<string, object?> Pipeline { get; init; }
    public Dictionary<string, object?> Dataset { get; init; } = new(StringComparer.OrdinalIgnoreCase);
    public Func<string, object?> Actividad { get; init; } = _ => null;

    public ContextoExpresion ConDataset(Dictionary<string, object?> dataset) =>
        new() { Pipeline = Pipeline, Dataset = dataset, Actividad = Actividad };
}

public sealed class ErrorExpresion(string mensaje) : Exception(mensaje);

/// <summary>
/// Subconjunto del lenguaje de expresiones de ADF: literales, @{...} interpolado,
/// pipeline()/dataset()/activity(), accesos .x y ['x'] y las funciones que usan
/// los pipelines convertidos desde SSIS.
/// </summary>
public static class Expresiones
{
    /// <summary>Resuelve un valor de una definición: {"value": "...", "type": "Expression"}, un texto con @ o un literal.</summary>
    public static object? Resolver(JsonNode? nodo, ContextoExpresion ctx)
    {
        if (nodo is JsonObject obj && (string?)obj["type"] == "Expression" && obj["value"] is JsonValue valor)
            return Evaluar(valor.GetValue<string>(), ctx);
        if (nodo is JsonValue v && v.TryGetValue<string>(out var texto))
            return Evaluar(texto, ctx);
        return DesdeJson(nodo);
    }

    public static string ResolverTexto(JsonNode? nodo, ContextoExpresion ctx) => ATexto(Resolver(nodo, ctx));

    public static object? Evaluar(string texto, ContextoExpresion ctx)
    {
        if (texto.StartsWith("@@", StringComparison.Ordinal))
            return texto[1..];
        if (texto.StartsWith('@') && !texto.StartsWith("@{", StringComparison.Ordinal))
            return new Parser(texto[1..], ctx).Completa();
        if (!texto.Contains("@{", StringComparison.Ordinal))
            return texto;

        var sb = new StringBuilder();
        var i = 0;
        while (i < texto.Length)
        {
            var inicio = texto.IndexOf("@{", i, StringComparison.Ordinal);
            if (inicio < 0)
            {
                sb.Append(texto, i, texto.Length - i);
                break;
            }
            sb.Append(texto, i, inicio - i);
            var fin = Cierre(texto, inicio + 2);
            sb.Append(ATexto(new Parser(texto[(inicio + 2)..fin], ctx).Completa()));
            i = fin + 1;
        }
        return sb.ToString();
    }

    private static int Cierre(string texto, int desde)
    {
        var profundidad = 0;
        var enCadena = false;
        for (var i = desde; i < texto.Length; i++)
        {
            var c = texto[i];
            if (c == '\'') enCadena = !enCadena;
            else if (!enCadena && c == '{') profundidad++;
            else if (!enCadena && c == '}' && profundidad-- == 0) return i;
        }
        throw new ErrorExpresion($"Falta '}}' en la expresión: {texto}");
    }

    public static string ATexto(object? valor) => valor switch
    {
        null => "",
        string s => s,
        bool b => b ? "True" : "False",
        IFormattable f => f.ToString(null, CultureInfo.InvariantCulture),
        _ => JsonSerializer.Serialize(valor),
    };

    public static object? DesdeJson(JsonNode? nodo) => nodo switch
    {
        null => null,
        JsonObject o => o.ToDictionary(p => p.Key, p => DesdeJson(p.Value), StringComparer.OrdinalIgnoreCase),
        JsonArray a => a.Select(DesdeJson).ToList(),
        JsonValue v when v.TryGetValue<string>(out var s) => s,
        JsonValue v when v.TryGetValue<bool>(out var b) => b,
        JsonValue v when v.TryGetValue<long>(out var l) => l,
        JsonValue v when v.TryGetValue<double>(out var d) => d,
        _ => nodo.ToJsonString(),
    };

    private sealed class Parser(string src, ContextoExpresion ctx)
    {
        private int _pos;

        public object? Completa()
        {
            var valor = Expresion();
            Espacios();
            if (_pos != src.Length)
                throw new ErrorExpresion($"Texto inesperado en la posición {_pos}: '{src[_pos..]}'");
            return valor;
        }

        private object? Expresion()
        {
            Espacios();
            if (_pos >= src.Length) throw new ErrorExpresion("Expresión incompleta");
            var c = src[_pos];
            object? valor;
            if (c == '\'') valor = Cadena();
            else if (char.IsDigit(c) || c == '-') valor = Numero();
            else
            {
                var id = Identificador();
                Espacios();
                if (Siguiente('('))
                {
                    var args = new List<object?>();
                    Espacios();
                    if (!Siguiente(')'))
                    {
                        do args.Add(Expresion()); while (Siguiente(','));
                        Esperar(')');
                    }
                    valor = Funcion(id, args);
                }
                else valor = id switch
                {
                    "true" => true,
                    "false" => false,
                    "null" => null,
                    _ => throw new ErrorExpresion($"Identificador desconocido: {id}"),
                };
            }

            while (true)
            {
                Espacios();
                if (Siguiente('.')) valor = Propiedad(valor, Identificador());
                else if (Siguiente('['))
                {
                    var clave = Expresion();
                    Esperar(']');
                    valor = Propiedad(valor, clave);
                }
                else return valor;
            }
        }

        private static object? Propiedad(object? valor, object? clave) => valor switch
        {
            null => null,
            IDictionary<string, object?> d => d.TryGetValue(ATexto(clave), out var v) ? v : null,
            IList<object?> l when clave is long i => l[(int)i],
            _ => throw new ErrorExpresion($"No se puede leer '{ATexto(clave)}' de un valor {valor.GetType().Name}"),
        };

        private object? Funcion(string nombre, List<object?> a)
        {
            switch (nombre)
            {
                case "pipeline": return ctx.Pipeline;
                case "dataset": return ctx.Dataset;
                case "activity": return ctx.Actividad(ATexto(a[0]));
                case "concat": return string.Concat(a.Select(ATexto));
                case "if": return EsVerdadero(a[0]) ? a[1] : a[2];
                case "empty": return a[0] switch { null => true, string s => s.Length == 0, System.Collections.ICollection c => c.Count == 0, _ => false };
                case "equals": return string.Equals(ATexto(a[0]), ATexto(a[1]), StringComparison.Ordinal);
                case "not": return !EsVerdadero(a[0]);
                case "and": return a.All(EsVerdadero);
                case "or": return a.Any(EsVerdadero);
                case "coalesce": return a.FirstOrDefault(x => x is not null);
                case "string": return ATexto(a[0]);
                case "int": return long.Parse(ATexto(a[0]), CultureInfo.InvariantCulture);
                case "toUpper": return ATexto(a[0]).ToUpperInvariant();
                case "toLower": return ATexto(a[0]).ToLowerInvariant();
                case "utcNow": return Formatear(DateTimeOffset.UtcNow, a.ElementAtOrDefault(0));
                case "formatDateTime": return Formatear(Fecha(a[0]), a.ElementAtOrDefault(1));
                case "addDays": return Formatear(Fecha(a[0]).AddDays(Convert.ToDouble(a[1], CultureInfo.InvariantCulture)), a.ElementAtOrDefault(2));
                case "convertFromUtc":
                    var zona = ZonaHoraria(ATexto(a[1]));
                    var local = TimeZoneInfo.ConvertTime(Fecha(a[0]), zona);
                    return Formatear(local, a.ElementAtOrDefault(2));
                default: throw new ErrorExpresion($"Función no soportada por el emulador: {nombre}()");
            }
        }

        private static bool EsVerdadero(object? v) => v switch
        {
            bool b => b,
            string s => bool.TryParse(s, out var b) && b,
            _ => false,
        };

        private static DateTimeOffset Fecha(object? v) =>
            DateTimeOffset.Parse(ATexto(v), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal);

        private static string Formatear(DateTimeOffset fecha, object? formato) =>
            formato is null
                ? fecha.ToString(fecha.Offset == TimeSpan.Zero ? "yyyy-MM-ddTHH:mm:ss.fffffffZ" : "o", CultureInfo.InvariantCulture)
                : fecha.ToString(ATexto(formato), CultureInfo.InvariantCulture);

        private static TimeZoneInfo ZonaHoraria(string id)
        {
            // ADF usa IDs de Windows; en Linux .NET los traduce con ICU, y si no puede se usa el IANA conocido.
            try { return TimeZoneInfo.FindSystemTimeZoneById(id); }
            catch (TimeZoneNotFoundException) when (id == "Pacific SA Standard Time")
            {
                return TimeZoneInfo.FindSystemTimeZoneById("America/Santiago");
            }
        }

        private string Cadena()
        {
            var sb = new StringBuilder();
            _pos++;
            while (_pos < src.Length)
            {
                if (src[_pos] == '\'')
                {
                    if (_pos + 1 < src.Length && src[_pos + 1] == '\'') { sb.Append('\''); _pos += 2; continue; }
                    _pos++;
                    return sb.ToString();
                }
                sb.Append(src[_pos++]);
            }
            throw new ErrorExpresion("Cadena sin cerrar");
        }

        private object Numero()
        {
            var inicio = _pos++;
            while (_pos < src.Length && (char.IsDigit(src[_pos]) || src[_pos] == '.')) _pos++;
            var texto = src[inicio.._pos];
            return texto.Contains('.')
                ? double.Parse(texto, CultureInfo.InvariantCulture)
                : long.Parse(texto, CultureInfo.InvariantCulture);
        }

        private string Identificador()
        {
            Espacios();
            var inicio = _pos;
            while (_pos < src.Length && (char.IsLetterOrDigit(src[_pos]) || src[_pos] == '_')) _pos++;
            if (inicio == _pos) throw new ErrorExpresion($"Se esperaba un identificador en la posición {_pos}");
            return src[inicio.._pos];
        }

        private void Espacios()
        {
            while (_pos < src.Length && char.IsWhiteSpace(src[_pos])) _pos++;
        }

        private bool Siguiente(char c)
        {
            Espacios();
            if (_pos < src.Length && src[_pos] == c) { _pos++; return true; }
            return false;
        }

        private void Esperar(char c)
        {
            if (!Siguiente(c)) throw new ErrorExpresion($"Se esperaba '{c}' en la posición {_pos}");
        }
    }
}
