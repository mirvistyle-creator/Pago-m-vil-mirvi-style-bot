from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import httpx
import re

app = FastAPI()

# Token de tu Bot de Telegram
TOKEN = "8877460148:AAFCj67-o34iLWiKvdVEltCVYjJiAP4eM7I"
TELEGRAM_API = f"https://telegram.org{TOKEN}"

# Diccionario temporal en memoria para almacenar pagos recibidos
pagos_recibidos = {}

class SMSData(BaseModel):
    mensaje: str

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "mensaje": "Validador de Pago Movil BDV en linea"}

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
        return {"status": "ignored", "reason": "SMS no corresponde a un formato valido de BDV"}

@app.post("/webhook-telegram")
async def webhook_telegram(request: Request):
    """Procesa las interacciones de Telegram usando peticiones HTTP directas"""
    data = await request.json()
    
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        texto_usuario = data["message"]["text"].strip()
        
        async with httpx.AsyncClient() as client:
            # Comando /start
            if texto_usuario == "/start":
                mensaje_bienvenida = (
                    "👋 ¡Hola! Bienvenido al sistema automatizado de verificación de pagos.\n\n"
                    "Para validar tu Pago Móvil, por favor envíame el **Número de Referencia** de tu transacción.\n\n"
                    "Escribe los números directamente en el chat para procesar la verificación."
                )
                await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_bienvenida, "parse_mode": "Markdown"})
                return {"ok": True}
            
            # Buscar número de referencia de 6 a 12 dígitos
            match_ref = re.search(r"\b(\d{6,12})\b", texto_usuario)
            if not match_ref:
                mensaje_error = "❌ No logré identificar un número de referencia válido.\nPor favor, envíame únicamente los números de la referencia de tu pago (de 6 a 12 dígitos)."
                await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_error})
                return {"ok": True}
                
            referencia = match_ref.group(1)
            
            # Verificación del pago
            if referencia in pagos_recibidos:
                pago = pagos_recibidos[referencia]
                if pago["usado"]:
                    await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": "⚠️ Esta referencia ya fue registrada y utilizada previamente para otro pago."})
                else:
                    pago["usado"] = True
                    monto_pago = pago["monto"]
                    mensaje_exito = f"✅ ¡Pago Verificado Exitosamente!\n\n🔹 **Referencia:** {referencia}\n🔹 **Monto:** Bs. {monto_pago}\n\n¡Tu orden o servicio ha sido procesado con éxito!"
                    await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_exito})
            else:
                mensaje_no_encontrado = f"🔍 Buscando la referencia **{referencia}**...\n\n❌ Aún no hemos recibido la notificación de este pago en nuestra cuenta bancaria.\n\nIntenta nuevamente en unos minutos."
                await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_no_encontrado, "parse_mode": "Markdown"})
                
    return {"ok": True}
