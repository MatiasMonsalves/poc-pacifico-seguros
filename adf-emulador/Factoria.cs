using System.Text.Json.Nodes;

namespace AdfEmulador;

/// <summary>
/// Una factoría de ADF: artefactos en el formato de la integración Git
/// (linkedService/, dataset/, pipeline/). Se leen en cada uso para que un
/// cambio en los JSON se vea sin reiniciar el emulador.
///
/// Ubicación de cada factoría (por nombre, el {factoryName} de la URL):
///   Adf:Factorias:{nombre}  carpeta explícita, o
///   {Adf:Raiz}/{nombre}/adf convención de sistemas/&lt;id&gt;/adf del repositorio.
/// Blob Storage se emula con {Adf:Raiz}/{nombre}/datos/blob (o Blob:Factorias:{nombre}).
/// </summary>
public sealed class Factoria(IConfiguration config, string nombre)
{
    public string Nombre { get; } = nombre;

    private readonly string _carpeta = config[$"Adf:Factorias:{nombre}"]
        ?? Path.Combine(config["Adf:Raiz"] ?? "/sistemas", nombre, "adf");

    public bool Existe => Directory.Exists(Path.Combine(_carpeta, "pipeline"));

    /// <summary>Raíz local que reemplaza a la cuenta de Blob Storage.</summary>
    public string RaizBlob => config[$"Blob:Factorias:{Nombre}"]
        ?? Path.Combine(config["Adf:Raiz"] ?? "/sistemas", Nombre, "datos", "blob");

    public JsonObject? Pipeline(string pipeline) => Leer("pipeline", pipeline);

    public IEnumerable<JsonObject> Pipelines() =>
        Existe
            ? Directory.GetFiles(Path.Combine(_carpeta, "pipeline"), "*.json").Select(f => (JsonObject)JsonNode.Parse(File.ReadAllText(f))!)
            : [];

    public JsonObject Dataset(string dataset) =>
        Leer("dataset", dataset) ?? throw new InvalidOperationException($"No existe el dataset {dataset}");

    public JsonObject LinkedService(string linkedService) =>
        Leer("linkedService", linkedService) ?? throw new InvalidOperationException($"No existe el linked service {linkedService}");

    /// <summary>Cadena de conexión de un linked service SQL, resolviendo referencias a Key Vault.</summary>
    public string CadenaConexion(string linkedService)
    {
        var ls = LinkedService(linkedService);
        var cadena = ls["properties"]?["typeProperties"]?["connectionString"];
        return cadena switch
        {
            JsonValue v => v.GetValue<string>(),
            JsonObject o when (string?)o["type"] == "SecureString" => (string)o["value"]!,
            JsonObject o when (string?)o["type"] == "AzureKeyVaultSecret" => SecretoKeyVault((string)o["secretName"]!),
            _ => throw new InvalidOperationException($"El linked service {linkedService} no tiene connectionString"),
        };
    }

    // En Azure el secreto vive en Key Vault; en el emulador viene de la configuración KeyVault:<secreto>.
    private string SecretoKeyVault(string secreto) =>
        config[$"KeyVault:{secreto}"]
        ?? throw new InvalidOperationException($"Secreto '{secreto}' no configurado (variable KeyVault__{secreto})");

    private JsonObject? Leer(string tipo, string artefacto)
    {
        var ruta = Path.Combine(_carpeta, tipo, $"{artefacto}.json");
        return File.Exists(ruta) ? (JsonObject)JsonNode.Parse(File.ReadAllText(ruta))! : null;
    }
}
