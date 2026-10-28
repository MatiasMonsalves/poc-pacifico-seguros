// Generado por tools/vb62net desde Polizas.vbp. Las líneas "VB6|" son el código original.
namespace Polizas.Generado;

public sealed record CmdBuscarClickSolicitud(string? Cliente);
public sealed record CmdCotizarClickSolicitud(string? Cliente, string? Siniestros, string? Suma, string? Tipo);

public static class EndpointsGenerados
{
    public static void MapEndpointsGenerados(this WebApplication app)
    {
        // Origen: vb6/frmPolizas.frm:32-37 · proc:polizas/frmpolizas.form_load (vb6graph)
        // VB6|     Set cn = AbrirConexion()
        // VB6|     cboTipo.AddItem "AUTO"
        // VB6|     cboTipo.AddItem "HOGAR"
        // VB6|     cboTipo.AddItem "VIDA"
        app.MapGet("/api/polizas/catalogos", () => Results.Ok(new Dictionary<string, string[]> { ["cboTipo"] = new[] { "AUTO", "HOGAR", "VIDA" } }))
            .WithDescription("Reemplaza VB6 frmPolizas.Form_Load");
        // Lista las pólizas del cliente (el SQL se arma concatenando el texto ingresado)
        // Origen: vb6/frmPolizas.frm:40-45 · proc:polizas/frmpolizas.cmdbuscar_click (vb6graph)
        // VB6|     Dim rs As New ADODB.Recordset
        // VB6|     rs.Open "SELECT NumPoliza, TipoSeguro, Prima, Estado FROM dbo.Polizas " &             "WHERE IdCliente = " & txtCliente.Text, cn
        // VB6|     Set grdPolizas.DataSource = rs
        app.MapGet("/api/polizas/buscar", async ([AsParameters] CmdBuscarClickSolicitud s, Db db) =>
        {
            var consulta1 = await db.ConsultarAsync("SELECT NumPoliza, TipoSeguro, Prima, Estado FROM dbo.Polizas WHERE IdCliente = @Cliente", ("@Cliente", (object?)s.Cliente));
            return Results.Ok(new { filas = consulta1 });
        })
            .WithDescription("Reemplaza VB6 frmPolizas.cmdBuscar_Click");
        // Cotiza con el componente .NET Pacifico.Tarificador expuesto por COM
        // Origen: vb6/frmPolizas.frm:48-60 · proc:polizas/frmpolizas.cmdcotizar_click (vb6graph)
        // VB6|     Dim rs As New ADODB.Recordset
        // VB6|     Dim tarificador As Object
        // VB6|     Dim edad As Integer
        // VB6|     Dim prima As Currency
        // VB6| 
        // VB6|     rs.Open "SELECT FechaNacimiento FROM dbo.Clientes WHERE IdCliente = " & txtCliente.Text, cn
        // VB6|     edad = CalcularEdad(rs!FechaNacimiento)
        // VB6| 
        // VB6|     Set tarificador = CreateObject("PacificoTarificador.Tarificador")
        // VB6|     prima = tarificador.CalcularPrima(cboTipo.Text, edad, CCur(txtSuma.Text), CInt(txtSiniestros.Text))
        // VB6|     MsgBox "Prima anual: " & Format(prima, "0.00") & " UF"
        app.MapPost("/api/polizas/cotizar", async (CmdCotizarClickSolicitud s, Db db) =>
        {
            var consulta1 = await db.ConsultarAsync("SELECT FechaNacimiento FROM dbo.Clientes WHERE IdCliente = @Cliente", ("@Cliente", (object?)s.Cliente));
            throw new PendienteDeMigrarException("COM PacificoTarificador.Tarificador (CalcularPrima): portar la lógica del componente (ver reingenieria/rea)");
        })
            .WithDescription("Reemplaza VB6 frmPolizas.cmdCotizar_Click");
        // Origen: vb6/frmPolizas.frm:62-69 · proc:polizas/frmpolizas.cmdrecalcular_click (vb6graph)
        // VB6|     Dim cmd As New ADODB.Command
        // VB6|     cmd.ActiveConnection = cn
        // VB6|     cmd.CommandType = adCmdStoredProc
        // VB6|     cmd.CommandText = "dbo.usp_RecalcularPrimas"
        // VB6|     cmd.Parameters.Append cmd.CreateParameter("@FechaProceso", adDBDate, adParamInput, , Date)
        // VB6|     cmd.Execute
        app.MapPost("/api/polizas/recalcular", async (Db db) =>
        {
            await db.EjecutarProcedimientoAsync("dbo.usp_RecalcularPrimas", ("@FechaProceso", (object?)Vb6.Date));
            return Results.Ok(new { ejecutado = true });
        })
            .WithDescription("Reemplaza VB6 frmPolizas.cmdRecalcular_Click");
        // Ejecuta el paquete SSIS en el servidor y espera a que termine
        // Origen: vb6/frmPolizas.frm:78-83 · proc:polizas/frmpolizas.cmdcargar_click (vb6graph)
        // VB6|     Dim comando As String
        // VB6|     comando = """" & RUTA_DTEXEC & """ /F """ & RUTA_PAQUETE & """ /SET \Package.Variables[User::FechaProceso].Value;" & Format(Date, "yyyy-mm-dd")
        // VB6|     Shell comando, vbHide
        // VB6|     MsgBox "Carga enviada. Revise el log del servidor para ver el resultado."
        app.MapPost("/api/polizas/cargar", async (AdfCliente adf) =>
        {
            var runId = await adf.IniciarAsync("PL_CargaPolizas", new Dictionary<string, string?> { ["FechaProceso"] = Vb6.Format(Vb6.Date, "yyyy-mm-dd") });
            return Results.Ok(new { runId, pipeline = "PL_CargaPolizas", estado = $"/api/cargas/{runId}" });
        })
            .WithDescription("Reemplaza VB6 frmPolizas.cmdCargar_Click");
    }
}
