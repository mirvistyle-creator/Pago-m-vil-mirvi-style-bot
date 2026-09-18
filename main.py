from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import re

app = FastAPI()

pagos_recibidos = {}

class SMSData(BaseModel):
    mensaje: str

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "mensaje": "El validador de Pago Movil BDV funciona"}

@app.post("/webhook-sms")
async def recibir_sms(data: SMSData):
    texto = data.mensaje
    try:
        referencia = re.search(r"Ref:\s*(\d+)", texto).group(1)
        monto_str = re.search(r"Bs\.\s*([\d\.,]+)", texto).group(1)
        monto_limpio = monto_str.replace(".", "")
        
        pagos_recibidos[referencia] = {
            "monto": monto_limpio,
            "usado": False
        }
        return {"status": "success", "referencia": referencia, "monto": monto_limpio}
    except AttributeError:
        return {"status": "ignored", "reason": "El SMS no contiene un formato valido de pago BDV"}

@app.get("/verificar/{referencia}")
async def verificar_pago(referencia: str, monto_esperado: str):
    monto_esperado_limpio = monto_esperado.replace(".", "")
    
    if referencia in pagos_recibidos:
        pago = pagos_recibidos[referencia]
        if pago["usado"]:
            raise HTTPException(status_code=400, detail="Esta referencia ya fue usada previamente.")
        if pago["monto"] == monto_esperado_limpio:
            pago["usado"] = True
            return {"status": "aprobado", "mensaje": "Pago verificado exitosamente"}
        return {"status": "monto_incorrecto", "mensaje": "La referencia existe pero el monto no coincide"}
    return {"status": "no_encontrado", "mensaje": "No se encontro ningun pago con esa referencia"}
