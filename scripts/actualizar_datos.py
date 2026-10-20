# -*- coding: utf-8 -*-
"""
Descarga en el servidor (GitHub Actions) las fuentes que el navegador no puede consultar directamente
y las deja como JSON junto al listado publicado en GitHub Pages.

  * datos/ema.json  <- API DMC de estaciones automáticas (requiere DMC_USUARIO y DMC_TOKEN como secretos)
  * datos/mop.json  <- Emergencias en infraestructura MOP (respaldo si el navegador no puede leer el servidor MOP)
  * datos/sec.json  <- SEC "Interrupciones en línea": clientes sin suministro por comuna (todas las distribuidoras)

Solo usa la biblioteca estándar de Python. Nunca falla el flujo: si una fuente no responde,
escribe el error en su JSON y el listado lo muestra.
"""
import os, sys, json, ssl, argparse, datetime as dt
import urllib.request, urllib.parse, urllib.error

REGIONES = (4, 5, 13, 6)          # Coquimbo, Valparaíso, Metropolitana, O'Higgins
DIAS_MOP = 3
EMA_URL = "https://climatologia.meteochile.gob.cl/application/geoservicios/getEmaResumenDiarioGeo"
MOP_URL = "https://rest-sit.mop.gob.cl/arcgis/rest/services/EMERGENCIA/EMERGENCIA_MOP/MapServer/0/query"
UA = {"User-Agent": "emergencias-quebradas/1.0 (GitHub Actions)"}
SEC_URL = "https://apps.sec.cl/INTONLINEv1/ClientesAfectados/"
SEC_REGIONES = {"Coquimbo": 4, "Valparaiso": 5, "Metropolitana": 13, "O`Higgins": 6}   # nombres tal como los entrega la SEC


def ahora_utc():
    return dt.datetime.now(dt.timezone.utc)


def leer_json(url, timeout=60):
    """GET con verificación TLS. Si el servidor tiene la cadena de certificados incompleta (el ejemplo oficial
    de la DMC desactiva la verificación por eso), reintenta sin verificar y lo deja registrado."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r), None
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), ssl.SSLError):
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.load(r), "certificado TLS no verificable; se leyó sin verificar"
        raise


def post_sec(endpoint, cuerpo, timeout=40):
    """La SEC solo responde POST con JSON (sin cabeceras CORS, por eso se consulta desde el servidor)."""
    req = urllib.request.Request(SEC_URL + endpoint, data=json.dumps(cuerpo).encode(), method="POST", headers={
        **UA, "Content-Type": "application/json; charset=utf-8", "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest", "Referer": "https://apps.sec.cl/INTONLINEv1/index.aspx",
        "Origin": "https://apps.sec.cl"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def sec():
    try:
        serie = post_sec("Get", {})
        ult = serie[-1]
        filas = post_sec("GetPorFecha", {k: ult[k] for k in ("anho", "mes", "dia", "hora")})
    except Exception as e:
        return {"ok": False, "error": f"SEC sin respuesta: {type(e).__name__}", "comunas": []}
    com = [{"region": SEC_REGIONES[f["NOMBRE_REGION"]], "region_nombre": f["NOMBRE_REGION"].replace("`", "'"),
            "comuna": f["NOMBRE_COMUNA"], "clientes": int(f.get("CLIENTES_AFECTADOS") or 0)}
           for f in filas if f.get("NOMBRE_REGION") in SEC_REGIONES and (f.get("CLIENTES_AFECTADOS") or 0) > 0]
    com.sort(key=lambda c: -c["clientes"])
    return {"ok": True, "error": None,
            "hora_sec": f"{ult['anho']}-{ult['mes']:02d}-{ult['dia']:02d} {ult['hora']:02d}:00 (hora de Chile)",
            "total_nacional": ult.get("clientes_afectados"),
            "total_area": sum(c["clientes"] for c in com), "comunas": com}


def num(v):
    try:
        return None if v in ("", None) else float(v)
    except (TypeError, ValueError):
        return None


def ema(usuario, token):
    if not usuario or not token:
        return {"ok": False, "error": "Faltan los secretos DMC_USUARIO y DMC_TOKEN en el repositorio", "estaciones": []}
    url = EMA_URL + "?" + urllib.parse.urlencode({"usuario": usuario, "token": token})
    try:
        d, aviso = leer_json(url)
    except Exception as e:
        # no exponer el token en el mensaje
        return {"ok": False, "error": f"API DMC sin respuesta: {type(e).__name__}", "estaciones": []}
    if not isinstance(d, dict) or "features" not in d:
        return {"ok": False, "error": "API DMC respondió sin estaciones (¿usuario o token inválido?)", "estaciones": []}
    est = []
    for f in d["features"]:
        p = f.get("properties") or {}
        try:
            reg = int(p.get("numeroRegion"))
        except (TypeError, ValueError):
            continue
        if reg not in REGIONES:
            continue
        hoy, ayer = num(p.get("aguaCaidaHoy")), num(p.get("aguaCaidaAyer"))
        est.append({
            "nombre": p.get("nombreEstacion"), "codigo": p.get("codigoNacional"),
            "comuna": p.get("comuna"), "region": reg,
            "lat": num(p.get("latitud")), "lon": num(p.get("longitud")),
            "hoy_mm": hoy, "ayer_mm": ayer,
            # "hoy" y "ayer" son días UTC (se reinician a las 21:00 de Chile): se suman para no perder la lluvia de la tarde
            "mm_2d": round((hoy or 0) + (ayer or 0), 1),
            "temp": num(p.get("temperatura")), "creado_utc": p.get("fechaCreacion"),
        })
    est.sort(key=lambda e: -e["mm_2d"])
    out = {"ok": True, "error": None, "total_pais": len(d["features"]), "estaciones": est}
    if aviso: out["aviso"] = aviso
    return out


def mop():
    params = {"where": f"CODREG IN ({','.join(map(str, REGIONES))})", "outFields": "*", "outSR": 4326,
              "returnGeometry": "true", "orderByFields": "FECHA DESC", "f": "json"}
    try:
        d, aviso = leer_json(MOP_URL + "?" + urllib.parse.urlencode(params))
    except Exception as e:
        return {"ok": False, "error": f"Servidor MOP sin respuesta: {type(e).__name__}", "emergencias": []}
    if "error" in d:
        return {"ok": False, "error": f"Servidor MOP: {d['error'].get('message', 'error')}", "emergencias": []}
    desde = (ahora_utc() - dt.timedelta(days=DIAS_MOP)).timestamp() * 1000
    out = []
    for f in d.get("features", []):
        a = f.get("attributes") or {}
        e = str(a.get("EMERGENCIA") or "").strip()
        if not a.get("FECHA") or a["FECHA"] < desde: continue
        if str(a.get("ESTADO_EMER") or "").upper() in ("CERRADO", "CANCELADO"): continue
        if "prueba" in e.lower() or len(e) <= 5: continue
        g = f.get("geometry") or {}
        out.append({k: a.get(k) for k in ("EMERGENCIA", "INFRA_AFEC", "ROL_VIAL", "CODREG", "FECHA",
                                          "GRAVEDAD", "OPERATIVIDAD", "ESTADO_EMER", "SERV_MOP")} |
                   {"lon": g.get("x"), "lat": g.get("y")})
    r = {"ok": True, "error": None, "emergencias": out}
    if aviso: r["aviso"] = aviso
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="sitio/datos")
    a = ap.parse_args()
    os.makedirs(a.salida, exist_ok=True)
    gen = ahora_utc().isoformat(timespec="seconds")
    E = ema(os.environ.get("DMC_USUARIO", "").strip(), os.environ.get("DMC_TOKEN", "").strip())
    M = mop()
    S = sec()
    for nombre, datos in (("ema", E), ("mop", M), ("sec", S)):
        datos["generado_utc"] = gen
        with open(os.path.join(a.salida, f"{nombre}.json"), "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"EMA: ok={E['ok']} estaciones={len(E['estaciones'])} {E.get('error') or ''} {E.get('aviso') or ''}")
    print(f"MOP: ok={M['ok']} emergencias={len(M['emergencias'])} {M.get('error') or ''}")
    print(f"SEC: ok={S['ok']} comunas={len(S['comunas'])} clientes_area={S.get('total_area')} {S.get('error') or ''}")


if __name__ == "__main__":
    main()
