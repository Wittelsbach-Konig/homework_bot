import http
import logging
import os
import time
from json.decoder import JSONDecodeError
from sys import stdout, exit

import requests
from dotenv import load_dotenv
from telegram import Bot, TelegramError
from telegram.ext import Updater

load_dotenv()


PRACTICUM_TOKEN: str = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: dict = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS: dict = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
LOG_FILE: str = os.path.join(BASE_DIR, 'homework.log')
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s %(name)s'

N_SECONDS = 5000

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(stream=stdout))


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения.

    Returns:
        bool: Доступность переменных окружения
    """
    env_vars: set = (
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
    )
    flag: bool = True
    for var in env_vars:
        if var is None:
            logger.critical(
                'Отсутствует обязательная переменная окружения: '
                f'"{var}" '
                'Программа принудительно остановлена.'
            )
            flag = False
    return flag


def send_message(bot: Bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат.

    Args:
        bot (Bot): экземпляр класса Bot
        message (str): сообщение
    """
    try:
        send_message_params: dict = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
        }
        bot.send_message(**send_message_params)
        logger.debug(
            f'Сообщение успешно отправлено: {message}'
        )
    except TelegramError as error:
        logger.error(
            f'Сообщение не отправлено: {error}'
        )
    except Exception:
        logger.error(
            f'Непредвиденная ошибка {Exception}'
        )


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к единственному эндпоинту API-сервиса.

    Args:
        timestamp (int): временная метка
    """
    try:
        get_params: dict = {
            'url': ENDPOINT,
            'headers': HEADERS,
            'params': {
                'from_date': timestamp
            },
        }
        response = requests.get(**get_params)
    except requests.exceptions.ConnectionError as e:
        raise e('Ошибка подключения.')
    except requests.exceptions.RequestException as e:
        raise e('Ошибка обработки запроса')
    except JSONDecodeError as e:
        raise e('JSON не сформирован!')
    if response.status_code != http.HTTPStatus.OK:
        raise http.exceptions.HTTPError('Страница недоступна.')
    return response.json()


def check_response(response: dict) -> dict:
    """Проверяет ответ API на соответствие документации.

    Args:
        response (dict): ответ API
    Return:
        homeworks (dict): домашняя работа
    """
    if not isinstance(response, dict):
        raise TypeError('В функцию "check_response" поступил не словарь')
    if 'homeworks' not in response:
        raise KeyError('Ключ homeworks отсутствует')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Объект homeworks не является списком')
    if response['homeworks'] == []:
        return {}
    return response.get('homeworks')[0]


def parse_status(homework: dict) -> str:
    """Извлекает из информации о конкретной домашней работе статус этой работы.

    Args:
        homework (dict): домашняя работа

    Returns:
        str: вердикт
    """
    hw_name = homework.get('homework_name')
    if hw_name is None:
        raise KeyError('Ключ status отсутствует в homework')
    hw_status = homework.get('status')
    if hw_status is None:
        raise KeyError('Ключ homework_name отсутствует в homework')
    if hw_status not in HOMEWORK_VERDICTS:
        raise KeyError(
            f'Статус {hw_status} отсутствует в перечне статусов'
        )
    verdict = HOMEWORK_VERDICTS[hw_status]
    return f'Изменился статус проверки работы "{hw_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Остутствие токенов')
        exit(1)
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - N_SECONDS
    previous_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework)
                send_message(bot, message)
                previous_error = None
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if str(previous_error) != str(error):
                send_message(bot, message)
            previous_error = error
            err_except = error
        time.sleep(RETRY_PERIOD)
        if not isinstance(err_except, TelegramError):
            timestamp = response.get('current_date', timestamp)
        err_except = None


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename=LOG_FILE,
        filemode='w',
        format=LOG_FORMAT,
    )
    main()
