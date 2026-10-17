using System;
using System.Runtime.InteropServices;
using Microsoft.VisualBasic;
using Microsoft.VisualBasic.CompilerServices;

namespace Pacifico.Tarificador;

[ComVisible(true)]
[Guid("6F3C2A51-9B7E-4D2A-8C11-5E0A7B9D4F21")]
[ProgId("PacificoTarificador.Tarificador")]
[ClassInterface(ClassInterfaceType.AutoDual)]
public class Tarificador
{
	private const decimal PRIMA_MINIMA = 12.5m;

	private const decimal DESCUENTO_SIN_SINIESTROS = 0.95m;

	private const decimal RECARGO_POR_SINIESTRO = 0.15m;

	private const int MAX_SINIESTROS_RECARGO = 3;

	public decimal CalcularPrima(string tipoSeguro, int edad, decimal sumaAsegurada, int siniestros)
	{
		if (decimal.Compare(sumaAsegurada, 0m) <= 0)
		{
			throw new ArgumentOutOfRangeException("sumaAsegurada", "La suma asegurada debe ser positiva");
		}
		decimal d = decimal.Multiply(decimal.Multiply(sumaAsegurada, ObtenerTasa(tipoSeguro)), FactorEdad(tipoSeguro, edad));
		d = ((siniestros != 0) ? decimal.Multiply(d, decimal.Add(1m, decimal.Multiply(0.15m, new decimal(Math.Min(siniestros, 3))))) : decimal.Multiply(d, 0.95m));
		if (decimal.Compare(d, 12.5m) < 0)
		{
			d = 12.5m;
		}
		return Math.Round(d, 2);
	}

	public decimal ObtenerTasa(string tipoSeguro)
	{
		return Strings.UCase(Strings.Trim(tipoSeguro)) switch
		{
			"AUTO" => 0.045m, 
			"HOGAR" => 0.0035m, 
			"VIDA" => 0.006m, 
			_ => throw new ArgumentException("Tipo de seguro no soportado: " + tipoSeguro), 
		};
	}

	public decimal FactorEdad(string tipoSeguro, int edad)
	{
		if (edad < 18)
		{
			throw new ArgumentOutOfRangeException("edad", "El asegurado debe ser mayor de edad");
		}
		decimal result;
		if (edad < 25)
		{
			result = 1.3m;
		}
		else
		{
			if (edad <= 60)
			{
				return 1m;
			}
			result = ((Operators.CompareString(Strings.UCase(Strings.Trim(tipoSeguro)), "VIDA", TextCompare: false) != 0) ? 1.45m : 1.8m);
		}
		return result;
	}
}
