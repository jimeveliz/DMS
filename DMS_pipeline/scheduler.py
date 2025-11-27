"""Programador simple que ejecuta el pipeline de ingesta de datos periodicamente."""
import logging
import time #controlar el tiempo de espera

import schedule

from launcher import main as run_launcher 
from config import config

logger = logging.getLogger(__name__)

def _run_launcher_job():
    """Envoltor o Wrapper que ejecuta el launcher y registra el resultado."""
    logger.info("Ejecutando launcher...")
    try:
        run_launcher() 
    except Exception: 
        logger.exception("Launcher finalizó con errores")
    else:
        logger.info("Launcher finalizó correctamente")


def start_scheduler(interval_minutes: int, run_on_start: bool = True):
    """Programa el trabajo del launcher para que se ejecute cada x minutos."""
    if interval_minutes <= 0:
        raise ValueError("El intervalo debe ser mayor que cero")

    if run_on_start:
        _run_launcher_job()

    """Crea un job que se ejecuta cada x minutos. Indica que ejecutar"""
    schedule.every(interval_minutes).minutes.do(_run_launcher_job) 
    logger.info(
        "Scheduler iniciado. El launcher se ejecutará cada %s minutos",
        interval_minutes,
    )
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
            """Espera un segundo entre cada verificación de trabajos pendientes"""
    except KeyboardInterrupt:
        logger.info("Scheduler detenido manualmente")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    interval = config.get("scheduler", {}).get("interval_minutes", 5)
    run_on_start = config.get("scheduler", {}).get("run_on_start", False)

    start_scheduler(interval_minutes=interval, run_on_start=run_on_start)


if __name__ == "__main__":
    main()
