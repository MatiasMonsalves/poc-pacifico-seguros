VERSION 5.00
Begin VB.Form frmPolizas
   Caption         =   "Mantenedor de Polizas"
End
Attribute VB_Name = "frmPolizas"
Private cn As ADODB.Connection

Private Sub Form_Load()
    Set cn = New ADODB.Connection
    cn.Open "Provider=SQLOLEDB;Data Source=SRVSQL01;Initial Catalog=Seguros;User ID=app;Password=app123"
End Sub

Private Sub cmdBuscar_Click()
    Dim rs As New ADODB.Recordset
    rs.Open "SELECT NumPoliza, Prima, Estado FROM dbo.Polizas " & _
            "WHERE IdCliente = " & txtCliente.Text, cn
End Sub

Private Sub cmdRecalcular_Click()
    Dim cmd As New ADODB.Command
    cmd.ActiveConnection = cn
    cmd.CommandType = adCmdStoredProc
    cmd.CommandText = "dbo.usp_RecalcularPrimas"
    cmd.Execute
End Sub
