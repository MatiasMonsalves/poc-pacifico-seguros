using System;
using System.Data.SqlClient;
using System.Windows.Forms;
using CrystalDecisions.CrystalReports.Engine;
using Pacifico.Siniestros.Reglas;

namespace Siniestros.Reportes
{
    public class FrmReservas : Form
    {
        private const string Cadena = "Data Source=SRVSQL02;Initial Catalog=Siniestros;Integrated Security=SSPI";

        private void btnImprimir_Click(object sender, EventArgs e)
        {
            var reporte = new ReportDocument();
            reporte.Load(@"\\SRVREP\Reportes\Reservas.rpt");
            reporte.SetDatabaseLogon("rep", "rep");
            reporte.PrintToPrinter(1, false, 0, 0);
        }

        private void btnSimular_Click(object sender, EventArgs e)
        {
            var reserva = CalculadoraReserva.Calcular('V', 1500m, 30);
            MessageBox.Show("Reserva estimada: " + reserva.ToString("N2") + " UF");
        }
    }
}
