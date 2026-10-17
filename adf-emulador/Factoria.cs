using System.Text.Json.Nodes;

namespace AdfEmulador;

/// <summary>
/// Artefactos de la factoría en el formato de la integración Git de ADF
/// (linkedService/, dataset/, pipeline/). Se leen en cada uso para que un
/// cambio en los JSON se vea sin reiniciar el emulador.
/// </summary>
public sealed class Factoria(IConfiguration config)
{
    private readonly string _carpeta = config["Adf:Carpeta"] ?? "/adf";

    public JsonObject? Pipeline(string nombre) => Leer("pipeline", nombre);

    public IEnumerable<JsonObject> Pipelines() =>
        Directory.Exists(Path.Combine(_carpeta, "pipeline"))
            ? Directory.GetFiles(Path.Combine(_carpeta, "pipeline"), "*.json").Select(f => (JsonObject)JsonNode.Parse(File.ReadAllText(f))!)
            : [];

    public JsonObject Dataset(string nombre) =>
        Leer("dataset", nombre) ?? throw new InvalidOperationException($"No existe el dataset {nombre}");

    public JsonObject LinkedService(string nombre) =>
        Leer("linkedService", nombre) ?? throw new InvalidOperationException($"No existe el linked service {nombre}");

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

    /// <summary>Raíz local que reemplaza a la cuenta de Blob Storage.</summary>
    public string RaizBlob => config["Blob:Raiz"] ?? "/blob";

    // En Azure el secreto vive en Key Vault; en el emulador viene de la configuración KeyVault:<secreto>.
    private string SecretoKeyVault(string secreto) =>
        config[$"KeyVault:{secreto}"]
        ?? throw new InvalidOperationException($"Secreto '{secreto}' no configurado (variable KeyVault__{secreto})");

    private JsonObject? Leer(string tipo, string nombre)
    {
        var ruta = Path.Combine(_carpeta, tipo, $"{nombre}.json");
        return File.Exists(ruta) ? (JsonObject)JsonNode.Parse(File.ReadAllText(ruta))! : null;
    }
}
