VERSION 5.00
Begin VB.Form frmPolizas
   Caption         =   "Mantenedor de Polizas"
   Begin VB.TextBox txtCliente
   End
   Begin VB.ComboBox cboTipo
   End
   Begin VB.TextBox txtSuma
   End
   Begin VB.TextBox txtSiniestros
   End
   Begin VB.CommandButton cmdBuscar
      Caption         =   "Buscar"
   End
   Begin VB.CommandButton cmdCotizar
      Caption         =   "Cotizar"
   End
   Begin VB.CommandButton cmdRecalcular
      Caption         =   "Recalcular primas"
   End
   Begin VB.CommandButton cmdCargar
      Caption         =   "Cargar archivo de polizas"
   End
   Begin MSFlexGridLib.MSFlexGrid grdPolizas
   End
End
Attribute VB_Name = "frmPolizas"
Option Explicit

Private cn As ADODB.Connection

Private Sub Form_Load()
    Set cn = AbrirConexion()
    cboTipo.AddItem "AUTO"
    cboTipo.AddItem "HOGAR"
    cboTipo.AddItem "VIDA"
End Sub

' Lista las pólizas del cliente (el SQL se arma concatenando el texto ingresado)
Private Sub cmdBuscar_Click()
    Dim rs As New ADODB.Recordset
    rs.Open "SELECT NumPoliza, TipoSeguro, Prima, Estado FROM dbo.Polizas " & _
            "WHERE IdCliente = " & txtCliente.Text, cn
    Set grdPolizas.DataSource = rs
End Sub

' Cotiza con el componente .NET Pacifico.Tarificador expuesto por COM
Private Sub cmdCotizar_Click()
    Dim rs As New ADODB.Recordset
    Dim tarificador As Object
    Dim edad As Integer
    Dim prima As Currency

    rs.Open "SELECT FechaNacimiento FROM dbo.Clientes WHERE IdCliente = " & txtCliente.Text, cn
    edad = CalcularEdad(rs!FechaNacimiento)

    Set tarificador = CreateObject("PacificoTarificador.Tarificador")
    prima = tarificador.CalcularPrima(cboTipo.Text, edad, CCur(txtSuma.Text), CInt(txtSiniestros.Text))
    MsgBox "Prima anual: " & Format(prima, "0.00") & " UF"
End Sub

Private Sub cmdRecalcular_Click()
    Dim cmd As New ADODB.Command
    cmd.ActiveConnection = cn
    cmd.CommandType = adCmdStoredProc
    cmd.CommandText = "dbo.usp_RecalcularPrimas"
    cmd.Parameters.Append cmd.CreateParameter("@FechaProceso", adDBDate, adParamInput, , Date)
    cmd.Execute
End Sub

' Exportaba las pólizas a Excel; el botón se quitó del formulario en 2019
Private Sub ExportarExcelViejo()
    Dim rs As New ADODB.Recordset
    rs.Open "SELECT * FROM dbo.Polizas WHERE Estado = 'VIGENTE'", cn
End Sub

' Ejecuta el paquete SSIS en el servidor y espera a que termine
Private Sub cmdCargar_Click()
    Dim comando As String
    comando = """" & RUTA_DTEXEC & """ /F """ & RUTA_PAQUETE & """ /SET \Package.Variables[User::FechaProceso].Value;" & Format(Date, "yyyy-mm-dd")
    Shell comando, vbHide
    MsgBox "Carga enviada. Revise el log del servidor para ver el resultado."
End Sub
