using System.Collections.Concurrent;
using System.Data;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.Data.SqlClient;

namespace AdfEmulador;

public sealed record ErrorActividad(string ErrorCode, string Message, string FailureType = "UserError", string Target = "");

public sealed class EjecucionActividad
{
    public required string ActivityName { get; init; }
    public required string ActivityType { get; init; }
    public string ActivityRunId { get; init; } = Guid.NewGuid().ToString();
    public required string PipelineRunId { get; init; }
    public string Status { get; set; } = "InProgress";
    public DateTimeOffset? ActivityRunStart { get; set; }
    public DateTimeOffset? ActivityRunEnd { get; set; }
    public long? DurationInMs { get; set; }
    public object? Input { get; set; }
    public object? Output { get; set; }
    public ErrorActividad? Error { get; set; }
}

public sealed class EjecucionPipeline
{
    public required string RunId { get; init; }
    public required string PipelineName { get; init; }
    public required Dictionary<string, object?> Parameters { get; init; }
    public object InvokedBy { get; } = new { name = "Manual", invokedByType = "Manual" };
    public string Status { get; set; } = "Queued";
    public DateTimeOffset? RunStart { get; set; }
    public DateTimeOffset? RunEnd { get; set; }
    public long? DurationInMs { get; set; }
    public string Message { get; set; } = "";
    public DateTimeOffset LastUpdated { get; set; } = DateTimeOffset.UtcNow;
    internal ConcurrentQueue<EjecucionActividad> Actividades { get; } = new();
    internal Factoria Factoria { get; init; } = null!;
    internal Task Tarea { get; set; } = Task.CompletedTask;
}

/// <summary>Ejecuta pipelines de ADF con sus reglas de dependencias y de estado final.</summary>
public sealed class Ejecutor(ILogger<Ejecutor> log)
{
    private readonly ConcurrentDictionary<string, EjecucionPipeline> _ejecuciones = new();

    public EjecucionPipeline? Obtener(string runId) => _ejecuciones.GetValueOrDefault(runId);

    public EjecucionPipeline Iniciar(Factoria factoria, string nombrePipeline, JsonObject definicion, JsonObject? parametros)
    {
        // Parámetros: valores recibidos sobre los defaultValue del pipeline (ADF no distingue mayúsculas)
        var valores = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        foreach (var (nombre, decl) in definicion["properties"]?["parameters"]?.AsObject() ?? [])
            valores[nombre] = Expresiones.DesdeJson(decl?["defaultValue"]);
        foreach (var (nombre, valor) in parametros ?? [])
            valores[nombre] = Expresiones.DesdeJson(valor);

        var ejecucion = new EjecucionPipeline { RunId = Guid.NewGuid().ToString(), PipelineName = nombrePipeline, Parameters = valores, Factoria = factoria };
        _ejecuciones[ejecucion.RunId] = ejecucion;
        ejecucion.Tarea = Task.Run(() => Ejecutar(ejecucion, definicion));
        return ejecucion;
    }

    private async Task Ejecutar(EjecucionPipeline ejecucion, JsonObject definicion)
    {
        ejecucion.Status = "InProgress";
        ejecucion.RunStart = DateTimeOffset.UtcNow;
        log.LogInformation("Pipeline {Pipeline} run {RunId} iniciado", ejecucion.PipelineName, ejecucion.RunId);

        var actividades = definicion["properties"]!["activities"]!.AsArray().Select(a => a!.AsObject()).ToList();
        var estados = new ConcurrentDictionary<string, EjecucionActividad>(StringComparer.OrdinalIgnoreCase);
        var ctx = new ContextoExpresion
        {
            Pipeline = new(StringComparer.OrdinalIgnoreCase)
            {
                ["parameters"] = ejecucion.Parameters,
                ["RunId"] = ejecucion.RunId,
                ["Pipeline"] = ejecucion.PipelineName,
                ["DataFactory"] = ejecucion.Factoria.Nombre,
                ["TriggerTime"] = ejecucion.RunStart.Value.ToString("o"),
            },
            Actividad = nombre => estados.TryGetValue(nombre, out var a)
                ? new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
                {
                    ["output"] = a.Output,
                    ["status"] = a.Status,
                    ["error"] = a.Error is null ? null : new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase)
                    {
                        ["errorCode"] = a.Error.ErrorCode, ["message"] = a.Error.Message,
                        ["failureType"] = a.Error.FailureType, ["target"] = a.Error.Target,
                    },
                }
                : null,
        };

        try
        {
            var pendientes = actividades.ToList();
            while (pendientes.Count > 0)
            {
                var listas = pendientes.Where(a => Dependencias(a).All(d => estados.ContainsKey(d.Actividad))).ToList();
                if (listas.Count == 0)
                    throw new InvalidOperationException("Dependencias circulares o hacia actividades inexistentes: "
                                                        + string.Join(", ", pendientes.Select(a => (string)a["name"]!)));
                var aEjecutar = new List<JsonObject>();
                foreach (var a in listas)
                {
                    if (Dependencias(a).All(d => d.Condiciones.Any(c => Cumple(c, estados[d.Actividad].Status))))
                        aEjecutar.Add(a);
                    else
                        Registrar(ejecucion, estados, a, "Skipped");
                }
                pendientes.RemoveAll(listas.Contains);
                await Task.WhenAll(aEjecutar.Select(a => EjecutarActividad(ejecucion, estados, a, ctx)));
            }

            var evaluadas = Evaluadas(actividades, estados);
            var fallidas = evaluadas.Where(a => a.Status != "Succeeded").ToList();
            ejecucion.Status = fallidas.Count == 0 ? "Succeeded" : "Failed";
            ejecucion.Message = string.Join("; ", fallidas.Select(a => $"Operation on target {a.ActivityName} failed: {a.Error?.Message}"));
        }
        catch (Exception ex)
        {
            ejecucion.Status = "Failed";
            ejecucion.Message = ex.Message;
        }
        ejecucion.RunEnd = DateTimeOffset.UtcNow;
        ejecucion.DurationInMs = (long)(ejecucion.RunEnd - ejecucion.RunStart).Value.TotalMilliseconds;
        ejecucion.LastUpdated = ejecucion.RunEnd.Value;
        log.LogInformation("Pipeline {Pipeline} run {RunId}: {Status} {Mensaje}", ejecucion.PipelineName, ejecucion.RunId, ejecucion.Status, ejecucion.Message);
    }

    private sealed record Dependencia(string Actividad, string[] Condiciones);

    private static IEnumerable<Dependencia> Dependencias(JsonObject actividad) =>
        actividad["dependsOn"]?.AsArray().Select(d => new Dependencia(
            (string)d!["activity"]!,
            d["dependencyConditions"]!.AsArray().Select(c => (string)c!).ToArray())) ?? [];

    // Varias condiciones en una misma dependencia se combinan con O; varias dependencias, con Y.
    private static bool Cumple(string condicion, string estado) => condicion switch
    {
        "Succeeded" => estado == "Succeeded",
        "Failed" => estado == "Failed",
        "Skipped" => estado == "Skipped",
        "Completed" => estado is "Succeeded" or "Failed",
        _ => false,
    };

    /// <summary>
    /// Regla de ADF: se evalúan las actividades hoja; si una hoja quedó Skipped se evalúa su
    /// padre en su lugar. El pipeline termina bien solo si todas las evaluadas terminaron bien.
    /// </summary>
    private static List<EjecucionActividad> Evaluadas(List<JsonObject> actividades, IDictionary<string, EjecucionActividad> estados)
    {
        var conHijos = actividades.SelectMany(Dependencias).Select(d => d.Actividad).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var porNombre = actividades.ToDictionary(a => (string)a["name"]!, StringComparer.OrdinalIgnoreCase);
        var resultado = new Dictionary<string, EjecucionActividad>(StringComparer.OrdinalIgnoreCase);

        void Evaluar(string nombre)
        {
            var estado = estados[nombre];
            if (estado.Status != "Skipped") { resultado[nombre] = estado; return; }
            foreach (var d in Dependencias(porNombre[nombre])) Evaluar(d.Actividad);
        }

        foreach (var hoja in porNombre.Keys.Where(n => !conHijos.Contains(n))) Evaluar(hoja);
        return resultado.Values.ToList();
    }

    private static EjecucionActividad Registrar(EjecucionPipeline ejecucion, IDictionary<string, EjecucionActividad> estados, JsonObject a, string estado)
    {
        var registro = new EjecucionActividad
        {
            ActivityName = (string)a["name"]!, ActivityType = (string)a["type"]!,
            PipelineRunId = ejecucion.RunId, Status = estado,
        };
        estados[registro.ActivityName] = registro;
        ejecucion.Actividades.Enqueue(registro);
        ejecucion.LastUpdated = DateTimeOffset.UtcNow;
        return registro;
    }

    private async Task EjecutarActividad(EjecucionPipeline ejecucion, IDictionary<string, EjecucionActividad> estados, JsonObject a, ContextoExpresion ctx)
    {
        var registro = Registrar(ejecucion, estados, a, "InProgress");
        registro.ActivityRunStart = DateTimeOffset.UtcNow;
        var reloj = Stopwatch.StartNew();
        try
        {
            registro.Output = registro.ActivityType switch
            {
                "Script" => await Script(ejecucion.Factoria, a, ctx, registro),
                "SqlServerStoredProcedure" => await ProcedimientoAlmacenado(ejecucion.Factoria, a, ctx, registro),
                "Copy" => await Copiar(ejecucion.Factoria, a, ctx, registro),
                "ExecutePipeline" => await EjecutarPipeline(ejecucion.Factoria, a, ctx, registro),
                "Fail" => throw new FalloActividad(new ErrorActividad(
                    Expresiones.ResolverTexto(a["typeProperties"]?["errorCode"], ctx),
                    Expresiones.ResolverTexto(a["typeProperties"]?["message"], ctx), "UserError", registro.ActivityName)),
                "Wait" => await Esperar(a, ctx),
                _ => throw new FalloActividad(new ErrorActividad("NotSupported",
                    $"El emulador no soporta actividades de tipo {registro.ActivityType}")),
            };
            registro.Status = "Succeeded";
        }
        catch (FalloActividad ex)
        {
            registro.Error = ex.Error with { Target = registro.ActivityName };
            registro.Status = "Failed";
        }
        catch (SqlException ex)
        {
            registro.Error = new ErrorActividad("2402",
                $"Execution fail against sql server. Please contact SQL Server team if you need further support. Sql error number: {ex.Number}. Error Message: {ex.Message}",
                "UserError", registro.ActivityName);
            registro.Status = "Failed";
        }
        catch (Exception ex)
        {
            registro.Error = new ErrorActividad("2200", ex.Message, "UserError", registro.ActivityName);
            registro.Status = "Failed";
        }
        registro.ActivityRunEnd = DateTimeOffset.UtcNow;
        registro.DurationInMs = reloj.ElapsedMilliseconds;
        ejecucion.LastUpdated = DateTimeOffset.UtcNow;
        log.LogInformation("  {Actividad} ({Tipo}): {Estado} {Error}", registro.ActivityName, registro.ActivityType, registro.Status, registro.Error?.Message);
        if (((string?)a["description"])?.StartsWith("MARCADOR", StringComparison.Ordinal) == true)
            log.LogWarning("  {Actividad} es un marcador sin migrar: {Descripcion}", registro.ActivityName, (string?)a["description"]);
    }

    private sealed class FalloActividad(ErrorActividad error) : Exception(error.Message)
    {
        public ErrorActividad Error { get; } = error;
    }

    // -- Actividades ------------------------------------------------------

    private static async Task<object> Script(Factoria factoria, JsonObject a, ContextoExpresion ctx, EjecucionActividad registro)
    {
        await using var cn = new SqlConnection(factoria.CadenaConexion(LinkedServiceDe(a)));
        await cn.OpenAsync();
        var afectados = 0;
        var textos = new List<string>();
        foreach (var script in a["typeProperties"]!["scripts"]!.AsArray())
        {
            var texto = Expresiones.ResolverTexto(script!["text"], ctx);
            textos.Add(texto);
            await using var cmd = new SqlCommand(texto, cn);
            afectados += Math.Max(0, await cmd.ExecuteNonQueryAsync());
        }
        registro.Input = new { scripts = textos };
        return new { resultSetCount = 0, recordsAffected = afectados, resultSets = Array.Empty<object>(), outputParameters = new { }, outputLogs = "" };
    }

    private static async Task<object> ProcedimientoAlmacenado(Factoria factoria, JsonObject a, ContextoExpresion ctx, EjecucionActividad registro)
    {
        var tp = a["typeProperties"]!;
        var nombre = Expresiones.ResolverTexto(tp["storedProcedureName"], ctx);
        await using var cn = new SqlConnection(factoria.CadenaConexion(LinkedServiceDe(a)));
        await cn.OpenAsync();
        await using var cmd = new SqlCommand(nombre, cn) { CommandType = CommandType.StoredProcedure, CommandTimeout = 0 };
        var entrada = new Dictionary<string, object?>();
        foreach (var (param, def) in tp["storedProcedureParameters"]?.AsObject() ?? [])
        {
            var valor = Expresiones.Resolver(def?["value"], ctx);
            entrada[param] = valor;
            cmd.Parameters.AddWithValue("@" + param, Convertir(valor, (string?)def?["type"]));
        }
        registro.Input = new { storedProcedureName = nombre, storedProcedureParameters = entrada };
        var reloj = Stopwatch.StartNew();
        await cmd.ExecuteNonQueryAsync();
        return new { effectiveIntegrationRuntime = "AutoResolveIntegrationRuntime (emulador)", executionDuration = reloj.Elapsed.TotalSeconds };
    }

    private static object Convertir(object? valor, string? tipo)
    {
        if (valor is null) return DBNull.Value;
        var texto = Expresiones.ATexto(valor);
        return tipo switch
        {
            "DateTime" => DateTime.Parse(texto, CultureInfo.InvariantCulture),
            "Int32" => int.Parse(texto, CultureInfo.InvariantCulture),
            "Int64" => long.Parse(texto, CultureInfo.InvariantCulture),
            "Decimal" => decimal.Parse(texto, CultureInfo.InvariantCulture),
            "Boolean" => bool.Parse(texto),
            _ => texto,
        };
    }

    private async Task<object> EjecutarPipeline(Factoria factoria, JsonObject a, ContextoExpresion ctx, EjecucionActividad registro)
    {
        var tp = a["typeProperties"]!;
        var nombre = (string)tp["pipeline"]!["referenceName"]!;
        var definicion = factoria.Pipeline(nombre)
            ?? throw new FalloActividad(new ErrorActividad("2104", $"El pipeline {nombre} no existe en la factoría {factoria.Nombre}"));
        var parametros = new JsonObject();
        foreach (var (clave, valor) in tp["parameters"]?.AsObject() ?? [])
            parametros[clave] = Expresiones.ResolverTexto(valor, ctx);
        registro.Input = new { pipeline = nombre, parameters = parametros };

        var hijo = Iniciar(factoria, nombre, definicion, parametros);
        var salida = new { pipelineRunId = hijo.RunId, pipelineName = nombre };
        if ((bool?)tp["waitOnCompletion"] == false)
            return salida;
        await hijo.Tarea;
        if (hijo.Status != "Succeeded")
            throw new FalloActividad(new ErrorActividad("2105",
                $"Operation on target {nombre} failed (run {hijo.RunId}): {hijo.Message}"));
        return salida;
    }

    private static async Task<object> Copiar(Factoria factoria, JsonObject a, ContextoExpresion ctx, EjecucionActividad registro)
    {
        var tp = a["typeProperties"]!;
        var refEntrada = a["inputs"]![0]!;
        var dsEntrada = factoria.Dataset((string)refEntrada["referenceName"]!);
        var ctxEntrada = ctx.ConDataset(ParametrosDataset(dsEntrada, refEntrada, ctx));
        var tipoOrigen = (string?)tp["source"]?["type"] ?? "";

        // Origen: archivo DelimitedText en Blob Storage, o tabla/consulta de Azure SQL
        var (origen, descripcion, bytes) = tipoOrigen is "AzureSqlSource" or "SqlServerSource" or "SqlSource"
            ? await LeerSql(factoria, dsEntrada, tp["source"]!, ctxEntrada)
            : await LeerArchivo(factoria, dsEntrada, ctxEntrada);

        // Destino: tabla de Azure SQL (SQL Server en el emulador)
        var dsSalida = factoria.Dataset((string)a["outputs"]![0]!["referenceName"]!);
        var tpSalida = dsSalida["properties"]!["typeProperties"]!;
        var tabla = $"[{Expresiones.ResolverTexto(tpSalida["schema"], ctx)}].[{Expresiones.ResolverTexto(tpSalida["table"], ctx)}]";
        var lsSalida = (string)dsSalida["properties"]!["linkedServiceName"]!["referenceName"]!;
        registro.Input = new { source = new { type = tipoOrigen, origen = descripcion }, sink = new { type = "AzureSqlSink", table = tabla } };

        // Sin translator, ADF mapea las columnas por nombre
        var mapeos = tp["translator"]?["mappings"]?.AsArray()
            .Select(m => (Origen: (string)m!["source"]!["name"]!, Destino: (string)m["sink"]!["name"]!)).ToList()
            ?? origen.Columns.Cast<DataColumn>().Select(c => (Origen: c.ColumnName, Destino: c.ColumnName)).ToList();

        await using var cn = new SqlConnection(factoria.CadenaConexion(lsSalida));
        await cn.OpenAsync();
        var datos = new DataTable();
        using (var adaptador = new SqlDataAdapter($"SELECT TOP 0 * FROM {tabla}", cn))
            adaptador.FillSchema(datos, SchemaType.Source);

        for (var i = 0; i < origen.Rows.Count; i++)
        {
            var fila = datos.NewRow();
            foreach (var (columnaOrigen, columnaDestino) in mapeos)
            {
                if (!origen.Columns.Contains(columnaOrigen))
                    throw new FalloActividad(new ErrorActividad("2200",
                        $"ErrorCode=UserErrorInvalidColumnMappingColumnNotFound,'Message=La columna de origen {columnaOrigen} no existe.'"));
                var columna = datos.Columns[columnaDestino] ?? throw new FalloActividad(new ErrorActividad("2200",
                    $"ErrorCode=UserErrorInvalidColumnMappingColumnNotFound,'Message=La columna {columnaDestino} no existe en {tabla}.'"));
                fila[columna] = origen.Rows[i][columnaOrigen] switch
                {
                    string texto => ConvertirCelda(texto, columna, i + 1),
                    var valor => valor,
                };
            }
            datos.Rows.Add(fila);
        }

        using var bulk = new SqlBulkCopy(cn) { DestinationTableName = tabla };
        foreach (var (_, destino) in mapeos) bulk.ColumnMappings.Add(destino, destino);
        await bulk.WriteToServerAsync(datos);
        return new { dataRead = bytes, rowsRead = origen.Rows.Count, rowsCopied = origen.Rows.Count, sourcePeakConnections = 1, sinkPeakConnections = 1 };
    }

    private static async Task<(DataTable, string, long)> LeerArchivo(Factoria factoria, JsonObject ds, ContextoExpresion ctx)
    {
        var tp = ds["properties"]!["typeProperties"]!;
        var ubicacion = tp["location"]!;
        var contenedor = Expresiones.ResolverTexto(ubicacion["container"], ctx);
        var carpeta = Expresiones.ResolverTexto(ubicacion["folderPath"], ctx);
        var archivo = Expresiones.ResolverTexto(ubicacion["fileName"], ctx);
        var ruta = Path.Combine(factoria.RaizBlob, contenedor, carpeta, archivo);
        if (!File.Exists(ruta))
            throw new FalloActividad(new ErrorActividad("2200",
                $"ErrorCode=UserErrorSourceBlobNotExists,'Type=Microsoft.DataTransfer.Common.Shared.HybridDeliveryException,Message=The required Blob is missing. ContainerName: {contenedor}, path: {Path.Combine(carpeta, archivo)}.'"));

        var delimitador = Expresiones.ResolverTexto(tp["columnDelimiter"], ctx) is { Length: > 0 } d ? d : ",";
        var conEncabezado = (bool?)tp["firstRowAsHeader"] ?? false;
        var lineas = (await File.ReadAllLinesAsync(ruta, Encoding.UTF8)).Where(l => l.Length > 0).ToList();
        var datos = new DataTable();
        var primera = Separar(lineas.FirstOrDefault() ?? "", delimitador);
        for (var i = 0; i < primera.Length; i++)
            datos.Columns.Add(conEncabezado ? primera[i] : $"Prop_{i}", typeof(string));
        foreach (var linea in lineas.Skip(conEncabezado ? 1 : 0))
        {
            var campos = Separar(linea, delimitador);
            if (campos.Length != datos.Columns.Count)
                throw new FalloActividad(new ErrorActividad("2200",
                    $"ErrorCode=DelimitedTextColumnCountMismatch,'Message=La fila tiene {campos.Length} columnas y el encabezado {datos.Columns.Count}: {linea}'"));
            datos.Rows.Add(campos.Cast<object>().ToArray());
        }
        return (datos, $"{contenedor}/{archivo}", new FileInfo(ruta).Length);
    }

    private static async Task<(DataTable, string, long)> LeerSql(Factoria factoria, JsonObject ds, JsonNode source, ContextoExpresion ctx)
    {
        var props = ds["properties"]!;
        var consulta = Expresiones.ResolverTexto(source["sqlReaderQuery"], ctx);
        if (consulta.Length == 0)
        {
            var tp = props["typeProperties"]!;
            consulta = $"SELECT * FROM [{Expresiones.ResolverTexto(tp["schema"], ctx)}].[{Expresiones.ResolverTexto(tp["table"], ctx)}]";
        }
        await using var cn = new SqlConnection(factoria.CadenaConexion((string)props["linkedServiceName"]!["referenceName"]!));
        await cn.OpenAsync();
        var datos = new DataTable();
        using (var adaptador = new SqlDataAdapter(consulta, cn))
            adaptador.Fill(datos);
        return (datos, consulta, 0);
    }

    private static object ConvertirCelda(string valor, DataColumn columna, int fila)
    {
        if (valor.Length == 0 && columna.AllowDBNull) return DBNull.Value;
        try
        {
            return columna.DataType switch
            {
                var t when t == typeof(decimal) => decimal.Parse(valor, NumberStyles.Float, CultureInfo.InvariantCulture),
                var t when t == typeof(int) => int.Parse(valor, NumberStyles.Integer, CultureInfo.InvariantCulture),
                var t when t == typeof(long) => long.Parse(valor, NumberStyles.Integer, CultureInfo.InvariantCulture),
                var t when t == typeof(DateTime) => DateTime.Parse(valor, CultureInfo.InvariantCulture),
                var t when t == typeof(bool) => bool.Parse(valor),
                _ => valor,
            };
        }
        catch (FormatException)
        {
            throw new FalloActividad(new ErrorActividad("2200",
                $"ErrorCode=TypeConversionFailure,Exception occurred when converting value '{valor}' for column name '{columna.ColumnName}' " +
                $"from type 'String' to type '{columna.DataType.Name}'. Fila {fila} del archivo."));
        }
    }

    private static string[] Separar(string linea, string delimitador)
    {
        // CSV con comillas dobles opcionales, como DelimitedText con quoteChar "
        var campos = new List<string>();
        var actual = new StringBuilder();
        var enComillas = false;
        for (var i = 0; i < linea.Length; i++)
        {
            var c = linea[i];
            if (c == '"') { if (enComillas && i + 1 < linea.Length && linea[i + 1] == '"') { actual.Append('"'); i++; } else enComillas = !enComillas; }
            else if (!enComillas && string.CompareOrdinal(linea, i, delimitador, 0, delimitador.Length) == 0)
            {
                campos.Add(actual.ToString());
                actual.Clear();
                i += delimitador.Length - 1;
            }
            else actual.Append(c);
        }
        campos.Add(actual.ToString());
        return campos.ToArray();
    }

    private static Dictionary<string, object?> ParametrosDataset(JsonObject dataset, JsonNode referencia, ContextoExpresion ctx)
    {
        var valores = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        foreach (var (nombre, decl) in dataset["properties"]?["parameters"]?.AsObject() ?? [])
            valores[nombre] = Expresiones.DesdeJson(decl?["defaultValue"]);
        foreach (var (nombre, valor) in referencia["parameters"]?.AsObject() ?? [])
            valores[nombre] = Expresiones.Resolver(valor, ctx);
        return valores;
    }

    private static async Task<object> Esperar(JsonObject a, ContextoExpresion ctx)
    {
        var segundos = Convert.ToInt32(Expresiones.Resolver(a["typeProperties"]?["waitTimeInSeconds"], ctx), CultureInfo.InvariantCulture);
        await Task.Delay(TimeSpan.FromSeconds(segundos));
        // ssis2adf deja Wait "MARCADOR ..." donde una tarea SSIS no se pudo convertir: se avisa para que no pase inadvertido
        var descripcion = (string?)a["description"] ?? "";
        return descripcion.StartsWith("MARCADOR", StringComparison.Ordinal)
            ? new { waitTimeInSeconds = segundos, advertencia = $"Actividad pendiente de migrar: {descripcion}" }
            : (object)new { waitTimeInSeconds = segundos };
    }

    private static string LinkedServiceDe(JsonObject a) =>
        (string?)a["linkedServiceName"]?["referenceName"] ?? throw new InvalidOperationException($"La actividad {a["name"]} no tiene linkedServiceName");

    public IEnumerable<EjecucionActividad> Actividades(string runId) =>
        _ejecuciones.TryGetValue(runId, out var e) ? e.Actividades.ToArray() : [];
}
