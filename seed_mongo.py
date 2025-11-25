from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URI = os.getenv("MONGO_URI")  # Prioridad si viene completa
if not MONGO_URI:
    HOST = os.getenv("MONGO_HOST", "10.73.173.21")
    PORT = int(os.getenv("MONGO_PORT", "27017"))
    USER = os.getenv("MONGO_USER", "fisica")
    PASS = os.getenv("MONGO_PASS", "F1s1c44518")
    DB   = os.getenv("MONGO_DB", "CondorDB")

    if USER and PASS:
        MONGO_URI = f"mongodb://{USER}:{PASS}@{HOST}:{PORT}/{DB}?authSource=admin"
    else:
        MONGO_URI = f"mongodb://{HOST}:{PORT}/{DB}"

client = AsyncIOMotorClient(MONGO_URI)
db = client.get_default_database()


