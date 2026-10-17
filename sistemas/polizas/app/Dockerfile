# syntax=docker/dockerfile:1
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props global.json ./
COPY src/Pacifico.Polizas.Dominio/*.csproj src/Pacifico.Polizas.Dominio/
COPY src/Pacifico.Polizas.Api/*.csproj src/Pacifico.Polizas.Api/
# El secreto "ca" es opcional: solo hace falta detrás de un proxy con certificado propio.
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    dotnet restore src/Pacifico.Polizas.Api/Pacifico.Polizas.Api.csproj
COPY src/ src/
RUN dotnet publish src/Pacifico.Polizas.Api/Pacifico.Polizas.Api.csproj -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
USER $APP_UID
ENV ASPNETCORE_HTTP_PORTS=8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "Pacifico.Polizas.Api.dll"]
