using System;
using System.Data.SqlClient;

namespace Pacifico.Siniestros.Reglas
{
    public static class CalculadoraReserva
    {
        private const string CadenaPorDefecto = "Data Source=SRVSQL02;Initial Catalog=Siniestros;User ID=reglas;Password=r3gl4s";

        // Reserva técnica de un siniestro (UF)
        public static decimal Calcular(char tipo, decimal montoUF, int diasAbierto)
        {
            if (montoUF < 0) throw new ArgumentOutOfRangeException("montoUF");
            decimal factor;
            switch (char.ToUpperInvariant(tipo))
            {
                case 'V': factor = 1.2m; break;
                case 'A':
                case 'H': factor = 1.0m; break;
                default: throw new ArgumentException("Tipo de siniestro desconocido: " + tipo);
            }
            if (diasAbierto > 60) factor *= 1.1m;
            return Math.Round(montoUF * factor, 2);
        }

        public static decimal ReservaRegistrada(string numSiniestro)
        {
            using (var cn = new SqlConnection(CadenaPorDefecto))
            using (var cmd = new SqlCommand("SELECT ReservaUF FROM dbo.Siniestros WHERE NumSiniestro = @n", cn))
            {
                cmd.Parameters.AddWithValue("@n", numSiniestro);
                cn.Open();
                var valor = cmd.ExecuteScalar();
                return valor == DBNull.Value || valor == null ? 0m : (decimal)valor;
            }
        }
    }
}
