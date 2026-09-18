from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
import httpx
import re

app = FastAPI()

TOKEN = "8877460148:AAFCj67-o34iLWiKvdVEltCVYjJiAP4eM7I"
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

# Base de datos en memoria para guardar los pagos capturados por el teléfono
pagos_recibidos = {}

class SMSData(BaseModel):
    mensaje: str

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "mensaje": "Validador en linea"}

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
        return {"status": "success", "referencia": referencia}
    except AttributeError:
        return {"status": "ignored"}

@app.post("/webhook-telegram")
async def webhook_telegram(request: Request):
    """Procesa los mensajes directos de Telegram"""
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
        
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        texto_usuario = data["message"]["text"].strip()
        
        async with httpx.AsyncClient() as client:
            # Comando /start
            if texto_usuario.startswith("/start"):
                mensaje_bienvenida = (
                    "👋 ¡Hola! Bienvenido al sistema automatizado de verificación de pagos.\n\n"
                    "Para validar tu Pago Móvil, por favor envíame el **Número de Referencia** de tu transacción."
                )
                await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_bienvenida, "parse_mode": "Markdown"})
                return {"ok": True}
            
            # Buscar número de referencia de 6 a 12 dígitos en el mensaje
            match_ref = re.search(r"\b(\d{6,12})\b", texto_usuario)
            if not match_ref:
                mensaje_error = "❌ No logré identificar una referencia válida.\nPor favor, envíame solo los números de tu referencia (de 6 a 12 dígitos)."
                await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_error})
                return {"ok": True}
                
            referencia = match_ref.group(1)
            
            # Validación interna contra el diccionario de pagos
            if referencia in pagos_recibidos:
                pago = pagos_recibidos[referencia]
                if pago["usado"]:
                    await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": "⚠️ Esta referencia ya fue registrada previamente para otro pago."})
                else:
                    pago["usado"] = True
                    monto_pago = pago["monto"]
                    mensaje_exito = f"✅ ¡Pago Verificado Exitosamente!\n\n🔹 **Referencia:** {referencia}\n🔹 **Monto:** Bs. {monto_pago}\n\n¡Tu orden ha sido procesada!"
                    await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_exito})
            else:
                mensaje_no_encontrado = f"🔍 Buscando la referencia **{referencia}**...\n\n❌ Aún no hemos recibido la notificación de este pago en nuestra cuenta bancaria.\n\nIntenta nuevamente en unos minutos."
                await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_no_encontrado, "parse_mode": "Markdown"})
                
    return {"ok": True}
