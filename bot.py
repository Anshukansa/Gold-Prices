import os
import time
from datetime import datetime
import logging
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telegram

# Configure logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
SUBSCRIBERS = {7932502148, 7736209700}
MAX_RETRIES = 5  # Reduced from 50
RETRY_DELAY = 3  # Reduced from 10
MAX_TOTAL_RUNTIME = 180  # 3 minutes max total runtime

def setup_driver():
    """Optimized lightweight Selenium setup."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Performance optimizations
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # Disable images
    chrome_options.page_load_strategy = 'eager'  # Don't wait for all resources
    
    chrome_binary_path = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    
    chrome_options.binary_location = chrome_binary_path
    service = Service(executable_path=chromedriver_path)
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(15)  # Set timeout for page loads
    return driver

def get_abc_price_with_retries():
    """Get ABC price with retries in a separate function for threading."""
    for attempt in range(MAX_RETRIES):
        driver = setup_driver()
        try:
            driver.get("https://www.abcbullion.com.au/store/gabgtael375g-abc-bullion-tael-cast-bar")
            wait = WebDriverWait(driver, 10)
            
            buy_by_section = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.scope-buy-by"))
            )
            
            script = """
            return document.querySelector("div.scope-buy-by p.price-container span.price").innerText.trim();
            """
            price_text = driver.execute_script(script)
            
            price = float(price_text.replace(',', '').replace('$', ''))
            price = round(price, 2)
            
            logger.info(f"Got ABC Bullion price: {price:.2f}")
            return price
        except Exception as e:
            logger.error(f"ABC Bullion attempt {attempt+1} failed: {str(e)[:100]}...")
        finally:
            driver.quit()
            
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    
    logger.warning("All ABC Bullion attempts failed")
    return None

def get_aarav_price_with_retries():
    """Get Aarav price with retries in a separate function for threading."""
    for attempt in range(MAX_RETRIES):
        driver = setup_driver()
        try:
            driver.get("https://aaravbullion.in/")
            wait = WebDriverWait(driver, 10)
            
            swiper = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.swiper-container.s1"))
            )
            
            script = """
            const data = [];
            document.querySelectorAll("div.swiper-slideTrending table.Trending_Table_Root table.second_table tr").forEach(row => {
                const price = row.querySelector("td:nth-child(2) span")?.innerText.trim();
                if (price) data.push(price);
            });
            return data[0];
            """
            price_text = driver.execute_script(script)
            
            price = float(price_text.replace(',', '').replace('Rs.', ''))
            price = round(price, 2)
            
            logger.info(f"Got Aarav Bullion price: {price:.2f}")
            return price
        except Exception as e:
            logger.error(f"Aarav attempt {attempt+1} failed: {str(e)[:100]}...")
        finally:
            driver.quit()
            
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    
    logger.warning("All Aarav Bullion attempts failed")
    return None

def send_telegram_message(bot, message):
    """Send Telegram message to all subscribers."""
    for user_id in SUBSCRIBERS:
        try:
            bot.send_message(chat_id=user_id, text=message)
            logger.info(f"Message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")

def main():
    """Main function using parallel processing for faster execution."""
    start_time = time.time()
    logger.info("Starting lightweight price update script...")
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    bot = telegram.Bot(token=token)
    
    if not SUBSCRIBERS:
        logger.info("No subscribers in the list!")
        return
    
    # Run price fetching in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        abc_future = executor.submit(get_abc_price_with_retries)
        aarav_future = executor.submit(get_aarav_price_with_retries)
        
        # Wait for results with timeout
        abc_price = None
        aarav_price = None
        
        try:
            abc_price = abc_future.result(timeout=MAX_TOTAL_RUNTIME/2)
        except concurrent.futures.TimeoutError:
            logger.error("ABC price fetch timed out")
        
        try:
            aarav_price = aarav_future.result(timeout=MAX_TOTAL_RUNTIME/2)
        except concurrent.futures.TimeoutError:
            logger.error("Aarav price fetch timed out")
    
    # Prepare message
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"📊 Gold Price Update - {current_time}\n\n"
    
    abc_price1 = None
    abc_price2 = None
    
    if abc_price is not None:
        abc_price1 = round((10 * abc_price) / 37.5, 2)
        abc_price2 = round(abc_price1 * 55, 2)
        message += f"ABC: ${abc_price:.2f} | 10g: ${abc_price1:.2f} | Rs.{abc_price2:.2f}\n"
    else:
        message += "ABC Bullion: Price unavailable\n"
    
    if aarav_price is not None:
        message += f"Aarav: Rs.{aarav_price:.2f}\n"
    else:
        message += "Aarav Bullion: Price unavailable\n"
    
    if abc_price2 is not None and aarav_price is not None:
        diff = round(abc_price2 - aarav_price, 2)
        if diff != 0:
            message += f"Difference: Rs.{abs(diff):.2f} "
            message += f"({'ABC higher' if diff > 0 else 'Aarav higher'})\n"
        else:
            message += f"Prices are equal\n"
    
    send_telegram_message(bot, message)
    
    elapsed = time.time() - start_time
    logger.info(f"Script completed in {elapsed:.2f} seconds")

if __name__ == "__main__":
    main()
