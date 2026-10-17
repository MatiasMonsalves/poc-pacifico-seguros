using System;
using System.Data.Common;
using System.Data.SqlClient;

namespace Pacifico.Siniestros.Reglas;

public static class CalculadoraReserva
{
	private const string CadenaPorDefecto = "Data Source=SRVSQL02;Initial Catalog=Siniestros;User ID=reglas;Password=r3gl4s";

	public static decimal Calcular(char tipo, decimal montoUF, int diasAbierto)
	{
		if (montoUF < 0m)
		{
			throw new ArgumentOutOfRangeException("montoUF");
		}
		decimal num;
		switch (char.ToUpperInvariant(tipo))
		{
		case 'V':
			num = 1.2m;
			break;
		case 'A':
		case 'H':
			num = 1.0m;
			break;
		default:
			throw new ArgumentException("Tipo de siniestro desconocido: " + tipo);
		}
		if (diasAbierto > 60)
		{
			num *= 1.1m;
		}
		return Math.Round(montoUF * num, 2);
	}

	public static decimal ReservaRegistrada(string numSiniestro)
	{
		//IL_0005: Unknown result type (might be due to invalid IL or missing references)
		//IL_000b: Expected Obj, but got Unknown
		//IL_0011: Unknown result type (might be due to invalid IL or missing references)
		//IL_0017: Expected Obj, but got Unknown
		SqlConnection val = new SqlConnection("Data Source=SRVSQL02;Initial Catalog=Siniestros;User ID=reglas;Password=r3gl4s");
		try
		{
			SqlCommand val2 = new SqlCommand("SELECT ReservaUF FROM dbo.Siniestros WHERE NumSiniestro = @n", val);
			try
			{
				val2.Parameters.AddWithValue("@n", (object)numSiniestro);
				((DbConnection)(object)val).Open();
				object obj = ((DbCommand)(object)val2).ExecuteScalar();
				return (obj == DBNull.Value || obj == null) ? 0m : ((decimal)obj);
			}
			finally
			{
				((IDisposable)val2)?.Dispose();
			}
		}
		finally
		{
			((IDisposable)val)?.Dispose();
		}
	}
}
