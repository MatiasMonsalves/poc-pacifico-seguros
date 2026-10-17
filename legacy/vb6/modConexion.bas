Attribute VB_Name = "modConexion"
Option Explicit

Public Const CONN_SEGUROS As String = "Provider=SQLOLEDB;Data Source=SRVSQL01;Initial Catalog=Seguros;User ID=app;Password=app123"
Public Const RUTA_DTEXEC As String = "C:\Program Files\Microsoft SQL Server\150\DTS\Binn\dtexec.exe"
Public Const RUTA_PAQUETE As String = "\\SRVSQL01\ETL\CargaPolizas.dtsx"

Public Function AbrirConexion() As ADODB.Connection
    Dim cn As New ADODB.Connection
    cn.Open CONN_SEGUROS
    Set AbrirConexion = cn
End Function

Public Function CalcularEdad(ByVal fechaNacimiento As Date) As Integer
    CalcularEdad = DateDiff("yyyy", fechaNacimiento, Date)
End Function
