from fastapi import FastAPI
from loguru import logger
from app.database import engine, Base
from app.api import payments, subscriptions, promo

app = FastAPI(
    title="AXELUS VPN API",
    version="1.0.0"
)

app.include_router(payments.router)
app.include_router(subscriptions.router)
app.include_router(promo.router)


@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("База данных готова")
    logger.info("AXELUS VPN Backend запущен")


@app.get("/")
async def root():
    return {"service": "AXELUS VPN API", "status": "online"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}