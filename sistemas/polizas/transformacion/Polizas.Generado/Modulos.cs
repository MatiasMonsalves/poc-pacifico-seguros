// Funciones de módulos VB6 traducidas por tools/vb62net
namespace Polizas.Generado;

public static class Modulos
{
    // VB6: Function CalcularEdad(ByVal fechaNacimiento As Date) As Integer
    public static short CalcularEdad(DateTime fechaNacimiento) => checked((short)(Vb6.DateDiff("yyyy", fechaNacimiento, Vb6.Date)));
}
