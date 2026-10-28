// Funciones de módulos VB6 traducidas por tools/vb62net
namespace Polizas.Generado;

public static class Modulos
{
    // VB6: Function CalcularEdad(ByVal fechaNacimiento As Date) As Integer
    // Origen: vb6/modConexion.bas:14-16 · proc:polizas/modconexion.calcularedad (vb6graph)
    public static short CalcularEdad(DateTime fechaNacimiento) => checked((short)(Vb6.DateDiff("yyyy", fechaNacimiento, Vb6.Date)));
}
