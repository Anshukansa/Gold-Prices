import os
import time
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import telegram

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Subscribers
SUBSCRIBERS = {7932502148, 7736209700}

# Config
MAX_RETRIES = 20
RETRY_DELAY = 5  # seconds

def setup_driver():
    """Setup optimized headless Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--window-size=800,600")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.page_load_strategy = 'eager'
    chrome_options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

    chrome_binary_path = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    chrome_options.binary_location = chrome_binary_path
    service = Service(executable_path=chromedriver_path)
    return webdriver.Chrome(service=service, options=chrome_options)

def get_abc_price(driver):
    """Get price from ABC Bullion."""
    try:
        driver.get("https://www.abcbullion.com.au/store/gabgtael375g-abc-bullion-tael-cast-bar")
        wait = WebDriverWait(driver, 8)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.scope-buy-by")))
        price_text = driver.execute_script("""
            return document.querySelector("div.scope-buy-by p.price-container span.price").innerText.trim();
        """)
        return round(float(price_text.replace(',', '').replace('$', '')), 2)
    except Exception as e:
        logger.warning(f"ABC fetch error: {e}")
        return None

def get_aarav_price(driver):
    """Get price from Aarav Bullion."""
    try:
        driver.get("https://aaravbullion.in/")
        wait = WebDriverWait(driver, 8)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.swiper-container.s1")))
        price_text = driver.execute_script("""
            const price = document.querySelector("div.swiper-slideTrending table.Trending_Table_Root table.second_table tr td:nth-child(2) span");
            return price ? price.innerText.trim() : null;
        """)
        return round(float(price_text.replace(',', '').replace('Rs.', '')), 2)
    except Exception as e:
        logger.warning(f"Aarav fetch error: {e}")
        return None

def send_message(bot, text):
    for user_id in SUBSCRIBERS:
        try:
            bot.send_message(chat_id=user_id, text=text)
            logger.info(f"Sent to {user_id}")
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")

def retry_get_prices():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")
    bot = telegram.Bot(token=token)

    abc_price, aarav_price = None, None
    attempt = 0

    while (abc_price is None or aarav_price is None) and attempt < MAX_RETRIES:
        attempt += 1
        logger.info(f"Attempt {attempt}/{MAX_RETRIES}...")

        driver = setup_driver()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    'abc': executor.submit(get_abc_price, driver),
                    'aarav': executor.submit(get_aarav_price, driver)
                }
                abc_price = futures['abc'].result()
                aarav_price = futures['aarav'].result()
        finally:
            driver.quit()

        if abc_price is None or aarav_price is None:
            logger.info(f"Retrying in {RETRY_DELAY} sec...")
            time.sleep(RETRY_DELAY)

    # Build message
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"📊 Final Update - {now}\n\n"
    abc_price1 = abc_price2 = diff = None

    if abc_price:
        abc_price1 = round((10 * abc_price) / 37.5, 2)
        abc_price2 = round(abc_price1 * 55, 2)
        message += f"ABC Bullion: ${abc_price:.2f} \n10g: ${abc_price1:.2f} / Rs.{abc_price2:.2f}\n"
    else:
        message += "ABC Bullion: ❌ Unavailable\n"

    if aarav_price:
        message += f"Aarav Bullion: Rs.{aarav_price:.2f}\n"
    else:
        message += "Aarav Bullion: ❌ Unavailable\n"

    if abc_price2 and aarav_price:
        diff = round(abc_price2 - aarav_price, 2)
        if diff == 0:
            message += "Difference: No difference.\n"
        else:
            who = "ABC" if diff > 0 else "Aarav"
            message += f"{who} is costlier by Rs.{abs(diff):.2f}\n"

    send_message(bot, message)

if __name__ == "__main__":
    logger.info("⏳ Starting optimized price updater...")
    retry_get_prices()
    logger.info("✅ Done.")
