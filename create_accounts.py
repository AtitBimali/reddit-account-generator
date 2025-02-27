import time
import logging

from selenium.common.exceptions import NoSuchWindowException, WebDriverException

from reddit_account_generator import config as generator_config, \
    create_account, verify_email, install_driver
from reddit_account_generator.proxies import DefaultProxy, TorProxy, EmptyProxy
from reddit_account_generator.utils import *
from reddit_account_generator.exceptions import *
from config import *


num_of_accounts = int(input('How many accounts do you want to make? '))


# Set logging
logger = logging.getLogger('script')
logging.getLogger('webdriverdownloader').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('selenium').setLevel(logging.WARNING)

try:
    import coloredlogs
    coloredlogs.install(level=LOG_LEVEL, fmt='%(asctime)s %(levelname)s %(message)s')
except ImportError:
    logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s %(levelname)s %(message)s')
    logging.warning('Coloredlogs is not installed. Install it with "pip install coloredlogs" to get cool logs!')

# Set config variables
generator_config.PAGE_LOAD_TIMEOUT_S = PAGE_LOAD_TIMEOUT_S
generator_config.DRIVER_TIMEOUT_S = DRIVER_TIMEOUT_S
generator_config.MICRO_DELAY_S = MICRO_DELAY_S

if BUILTIN_DRIVER:
    # Install firefox driver binary
    logger.info('Installing firefox driver...')
    install_driver()


def save_account(email: str, username: str, password: str):
    """Save account credentials to a file."""
    logger.debug('Saving account credentials')
    with open(ACCOUNTS_FILE, 'a', encoding='utf-8') as f:
        f.write(f'{email};{username};{password}\n')


# Check for tor and proxies
logger.info('Checking if tor is running...')
is_tor_running = check_tor_running(TOR_IP, TOR_SOCKS5_PORT)
proxies = load_proxies(PROXIES_FILE)
is_proxies_loaded = len(proxies) != 0

# Define proxy manager: Tor, Proxies file or local IP
if is_tor_running:
    logger.info('Tor is running. Connecting to Tor...')
    proxy = TorProxy(TOR_IP, TOR_PORT, TOR_PASSWORD, TOR_CONTROL_PORT, TOR_DELAY)
    logger.info('Connected to Tor.')
    logger.warning('You will probably see a lot of RecaptchaException, but it\'s ok.')

else:
    logger.info('Tor is not running.')

    if is_proxies_loaded:
        proxy = DefaultProxy(proxies)
        logging.info('Loaded %s proxies.', len(proxies))

    else:
        proxy = EmptyProxy()
        logger.warning('No proxies loaded. Using local IP address.')
        logger.warning('Tor is not running. It is recommended to run Tor to avoid IP cooldowns.\n\n' +
                        'Please, run command "python run_tor.py" or add proxies to file %s\n', PROXIES_FILE)


# Create accounts
IP_COOLDOWN_S = 60 * 10  # 10 minutes
latest_account_created_timestamp = time.time() - IP_COOLDOWN_S

try:
    for i in range(num_of_accounts):
        # Check if we need to wait for IP cooldown
        delta = time.time() - latest_account_created_timestamp
        if isinstance(proxy, EmptyProxy) and delta < IP_COOLDOWN_S:
            logger.warning(f'IP cooldown. Waiting {(IP_COOLDOWN_S - delta) / 60 :.1f} minutes. Use tor/proxies to avoid this.')
            time.sleep(IP_COOLDOWN_S - delta)

        logger.info('Creating account (%s/%s)', i+1, num_of_accounts)
        proxies = proxy.get_next()

        # Create account
        retries = 0
        while retries < MAX_RETRIES:
            try:
                email, username, password = create_account(
                    email=EMAIL or None,
                    proxies=proxies,
                    hide_browser=HIDE_BROWSER
                )
                latest_account_created_timestamp = time.time()
                break

            except UsernameTakenException:
                logger.error('Username %s taken. Trying again.', username)

            except SessionExpiredException:
                logger.error('Page session expired. Trying again.')

            except NetworkException as e:
                # If we are using local IP address, we can't bypass IP cooldown
                if isinstance(proxy, EmptyProxy) and (
                        isinstance(e, IPCooldownException)):
                    logger.error(e)
                    logger.error(f'IP cooldown. Trying again in {e.cooldown}. Use tor/proxies to avoid this.')
                    time.sleep(e.cooldown.total_seconds())
                    continue

                logger.error('Network failed with %s.', e.__class__.__name__)
                proxies = proxy.get_next()
                logger.info('Using next proxy: %s', proxy)

            except NoSuchWindowException as e:
                # Handle this in top level try-except
                raise e

            except WebDriverException as e:
                logger.error(e)
                logging.error('An error occurred during account creation. Trying again %s more times...', MAX_RETRIES - retries)
                retries += 1
                username, password = None, None
        else:
            logger.error('An error occurred during account creation. Exiting...')
            exit(1)

        save_account(email, username, password)
        logger.info('Account created!')

        # Verify email
        if EMAIL:
            # You need to manually verify email if you are using your own email
            pass
        else:
            for i in range(MAX_RETRIES):
                try:
                    verify_email(email)
                    logger.info('Email verified!\n')
                    break
                except WebDriverException as e:
                    logger.error(e)
                    logger.error('An error occurred during email verification. Trying again... [%s/%s]', i+1, MAX_RETRIES)
            else:
                logger.error('Email verification failed. Skipping...')

except (KeyboardInterrupt, SystemExit, NoSuchWindowException):
    logger.info('Exiting...')
    exit(0)

logger.info('Done!')
