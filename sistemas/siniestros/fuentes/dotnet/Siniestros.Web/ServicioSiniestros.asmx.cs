using System;
using System.Data;
using System.Data.SqlClient;
using System.Configuration;
using System.Web.Services;

namespace Siniestros.Web
{
    [WebService(Namespace = "http://pacifico.ejemplo.cl/siniestros")]
    public class ServicioSiniestros : WebService
    {
        private readonly string _cadena = ConfigurationManager.ConnectionStrings["Siniestros"].ConnectionString;

        [WebMethod]
        public DataSet SiniestrosPorPoliza(string numPoliza)
        {
            var ds = new DataSet();
            using (var cn = new SqlConnection(_cadena))
            {
                var da = new SqlDataAdapter("SELECT NumSiniestro, Tipo, FechaDenuncia, MontoUF, ReservaUF FROM dbo.Siniestros WHERE NumPoliza = '" + numPoliza + "'", cn);
                da.Fill(ds);
            }
            return ds;
        }

        [WebMethod]
        public void RecalcularReservas()
        {
            using (var cn = new SqlConnection(_cadena))
            {
                var cmd = new SqlCommand("dbo.usp_CalcularReservas", cn);
                cmd.CommandType = CommandType.StoredProcedure;
                cmd.Parameters.AddWithValue("@FechaCorte", DateTime.Today);
                cn.Open();
                cmd.ExecuteNonQuery();
            }
        }
    }
}
