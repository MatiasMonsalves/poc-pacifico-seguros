Imports System.Runtime.InteropServices

<ComVisible(True)>
<Guid("6F3C2A51-9B7E-4D2A-8C11-5E0A7B9D4F21")>
<ProgId("PacificoTarificador.Tarificador")>
<ClassInterface(ClassInterfaceType.AutoDual)>
Public Class Tarificador

    Private Const PRIMA_MINIMA As Decimal = 12.5D
    Private Const DESCUENTO_SIN_SINIESTROS As Decimal = 0.95D
    Private Const RECARGO_POR_SINIESTRO As Decimal = 0.15D
    Private Const MAX_SINIESTROS_RECARGO As Integer = 3

    Public Function CalcularPrima(ByVal tipoSeguro As String, ByVal edad As Integer,
                                  ByVal sumaAsegurada As Decimal, ByVal siniestros As Integer) As Decimal
        If sumaAsegurada <= 0D Then
            Throw New ArgumentOutOfRangeException("sumaAsegurada", "La suma asegurada debe ser positiva")
        End If

        Dim prima As Decimal = sumaAsegurada * ObtenerTasa(tipoSeguro) * FactorEdad(tipoSeguro, edad)

        If siniestros = 0 Then
            prima = prima * DESCUENTO_SIN_SINIESTROS
        Else
            prima = prima * (1D + RECARGO_POR_SINIESTRO * Math.Min(siniestros, MAX_SINIESTROS_RECARGO))
        End If

        If prima < PRIMA_MINIMA Then
            prima = PRIMA_MINIMA
        End If

        Return Math.Round(prima, 2)
    End Function

    Public Function ObtenerTasa(ByVal tipoSeguro As String) As Decimal
        Select Case UCase(Trim(tipoSeguro))
            Case "AUTO"
                Return 0.045D
            Case "HOGAR"
                Return 0.0035D
            Case "VIDA"
                Return 0.006D
            Case Else
                Throw New ArgumentException("Tipo de seguro no soportado: " & tipoSeguro)
        End Select
    End Function

    Public Function FactorEdad(ByVal tipoSeguro As String, ByVal edad As Integer) As Decimal
        If edad < 18 Then
            Throw New ArgumentOutOfRangeException("edad", "El asegurado debe ser mayor de edad")
        End If
        If edad < 25 Then Return 1.3D
        If edad <= 60 Then Return 1D
        If UCase(Trim(tipoSeguro)) = "VIDA" Then Return 1.8D
        Return 1.45D
    End Function

End Class
