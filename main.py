from flask import Flask
import threading
import os

# Flask для health check
app = Flask(__name__)

@app.route('/')
def health():
    return "Shield VPN Bot is running! 🛡️", 200

@app.route('/health')
def health_check():
    return {"status": "ok"}, 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start() 

import asyncio
import logging
import os
import signal
import sys

from modules import bot_runner
from modules.config import get_config
from modules.database import DatabaseManager


def setup_logging() -> None:
    config = get_config()
    os.makedirs(config.data_dir, exist_ok=True)
    
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(
                f'{config.data_dir}/logs.log',
                encoding='utf-8'
            ),
            logging.StreamHandler(sys.stdout)
        ]
    )


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)    
    logger.setLevel(logging.INFO)
    
    config = get_config()
    db_path = os.path.join(config.data_dir, config.db_name)
    
    db_manager = DatabaseManager(db_path)
    await db_manager.initialize()
    
    logger.info("Запуск бота технической поддержки...")
    
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum: int, frame) -> None:
        logger.info(f"Получен сигнал {signum}, завершение работы...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot_runner.run_bot(db_manager, shutdown_event)
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        raise
    finally:
        await db_manager.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
