from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    payload = await req.json()
    # Minimal validation: Telegram updates contain an 'update_id'
    update_id = payload.get("update_id")
    return {"received": bool(update_id)}
