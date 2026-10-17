"""Arma la entrada de `rea import-managed-reconstruction` a partir de:
  * la evidencia de `rea inspect-managed-members --format json`
  * el C# que produce `ilspycmd -t <Tipo>`

Cada método se ancla a su token, hash de firma y hash de IL normalizado, de
modo que REA verifica que el código decompilado corresponde al binario exacto.

Uso:
    python reconstruccion.py <members.json> <decompilado.cs> <Tipo.Completo> <ilspy_version> <salida.json>
"""

import json
import re
import sys


def ubicar_metodo(lineas: list[str], nombre: str) -> tuple[int, int] | None:
    patron = re.compile(rf"^\s*public\s+[\w.<>\[\]]+\s+{re.escape(nombre)}\s*\(")
    for i, linea in enumerate(lineas):
        if patron.search(linea):
            profundidad, abierto = 0, False
            for j in range(i, len(lineas)):
                profundidad += lineas[j].count("{") - lineas[j].count("}")
                abierto = abierto or "{" in lineas[j]
                if abierto and profundidad == 0:
                    return i + 1, j + 1
    return None


def main(argv: list[str]) -> int:
    members_path, cs_path, tipo, version, salida = argv[1:6]
    evidencia = json.load(open(members_path, encoding="utf-8"))
    lineas = open(cs_path, encoding="utf-8").read().splitlines()
    metodos = []
    for m in evidencia["normalized_result"]["methods"]:
        if m["declaring_type"] != tipo or m["name"].startswith("."):
            continue
        rango = ubicar_metodo(lineas, m["name"])
        if not rango:
            print(f"Sin reconstrucción para {m['name']}", file=sys.stderr)
            continue
        inicio, fin = rango
        metodos.append({
            "token": m["token"],
            "signature_sha256": m["signature"]["raw_sha256"],
            "normalized_il_sha256": m["body"]["normalized_il_sha256"],
            "reconstruction": {
                "kind": "decompiled-csharp",
                "language": "csharp",
                "text": "\n".join(lineas[inicio - 1:fin]),
                "source_path": cs_path,
                "start_line": inicio,
                "end_line": fin,
            },
        })
    entrada = {
        "static_members": evidencia,
        "decompiler": {
            "name": "ilspycmd",
            "version": version,
            "family": "ilspy",
            "executable_sha256": None,
            "options": ["-t", tipo],
        },
        "methods": metodos,
        "notes": ["Componente legado Pacifico.Tarificador analizado solo desde el binario."],
    }
    json.dump(entrada, open(salida, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"{len(metodos)} métodos: {', '.join(m['reconstruction']['text'].split('(')[0].split()[-1] for m in metodos)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
