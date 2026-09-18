from fastapi import FastAPI, BaseModel
sat = None  # Evita choques con nombres internos de FastAPI
import requests
import re
import threading
import time

app = FastAPI()

TOKEN = "8715321676:AAFSeZupHZrp4zT_qxRJ8UzkN27k55JL6B4"
TELEGRAM_API = f"https://telegram.org{TOKEN}"

pagos_recibidos = {}

class SMSData(BaseModel):
    mensaje: str

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "modo": "buscador_automatico_polling"}

@app.post("/webhook-sms")
def recibir_sms(data: SMSData):
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

def procesar_actualizacion_telegram(update):
    """Procesa los mensajes que encuentra en la oficina de correos de Telegram"""
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        texto_usuario = update["message"]["text"].strip()
        
        if texto_usuario.startswith("/start"):
            mensaje_bienvenida = (
                "👋 ¡Hola! Bienvenido al sistema de verificación por buscador automático.\n\n"
                "Para validar tu Pago Móvil, por favor envíame el **Número de Referencia** de tu transacción."
            )
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_bienvenida})
            return

        match_ref = re.search(r"\b(\d{6,12})\b", texto_usuario)
        if not match_ref:
            mensaje_error = "❌ No logré identificar una referencia válida.\nPor favor, envíame solo los números de tu referencia (de 6 a 12 dígitos)."
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_error})
            return
            
        referencia = match_ref.group(1)
        
        if referencia in pagos_recibidos:
            pago = pagos_recibidos[referencia]
            if pago["usado"]:
                requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": "⚠️ Esta referencia ya fue registrada previamente para otro pago."})
            else:
                pago["usado"] = True
                monto_pago = pago["monto"]
                mensaje_exito = f"✅ ¡Pago Verificado Exitosamente!\n\n🔹 **Referencia:** {referencia}\n🔹 **Monto:** Bs. {monto_pago}\n\n¡Tu orden ha sido procesada!"
                requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_exito})
        else:
            mensaje_no_encontrado = f"🔍 Buscando la referencia **{referencia}**...\n\n❌ Aún no hemos recibido la notificación de este pago en nuestra cuenta bancaria.\n\nIntenta nuevamente en unos minutos."
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_no_encontrado})

def bucle_buscador_mensajes():
    """Revisa Telegram cada 2 segundos buscando mensajes nuevos de forma infinita"""
    # Primero borramos cualquier intento de webhook viejo bloqueado
    requests.get(f"{TELEGRAM_API}/deleteWebhook")
    offset = 0
    
    while True:
        try:
            # Trae los mensajes acumulados en Telegram
            response = requests.get(f"{TELEGRAM_API}/getUpdates", params={"offset": offset, "timeout": 10}, timeout=15)
            data = response.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    offset = update["update_id"] + 1
                    procesar_actualizacion_telegram(update)
        except Exception:
            pass
        time.sleep(2)

# Arrancamos el buscador en segundo plano de inmediato al cargar el archivo
hilo_buscador = threading.Thread(target=bucle_buscador_mensajes, daemon=True)
hilo_buscador.start()
