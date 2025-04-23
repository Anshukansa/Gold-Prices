import os
import time
from datetime import datetime
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import telegram

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# List of subscriber IDs (replace with your actual subscriber IDs)
SUBSCRIBERS = {
    7932502148,
    7736209700
}

# Maximum retry attempts for each website
MAX_RETRIES = 50
RETRY_DELAY = 10  # seconds between retries

def setup_driver():
    """Sets up a lightweight Selenium WebDriver with headless Chrome."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Lightweight optimizations for Heroku
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--window-size=800,600")  # Smaller window size
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  # Disable images
    
    chrome_binary_path = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    
    chrome_options.binary_location = chrome_binary_path
    service = Service(executable_path=chromedriver_path)
    
    return webdriver.Chrome(service=service, options=chrome_options)

def get_abc_price(driver):
    """Gets price from ABC Bullion."""
    try:
        driver.get("https://www.abcbullion.com.au/store/gabgtael375g-abc-bullion-tael-cast-bar")
        wait = WebDriverWait(driver, 15)
        
        # Wait until the 'scope-buy-by' div is present
        buy_by_section = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.scope-buy-by"))
        )
        
        # Extract the price using JavaScript (faster than parsing DOM)
        script = """
        return document.querySelector("div.scope-buy-by p.price-container span.price").innerText.trim();
        """
        price_text = driver.execute_script(script)
        
        # Convert price to float with two decimals
        price = float(price_text.replace(',', '').replace('$', ''))
        price = round(price, 2)
        
        logger.info(f"Successfully got ABC Bullion price: {price:.2f}")
        return price
    except Exception as e:
        logger.error(f"Error getting ABC Bullion price: {e}")
        return None

def get_aarav_price(driver):
    """Gets price from Aarav Bullion."""
    try:
        driver.get("https://aaravbullion.in/")
        wait = WebDriverWait(driver, 15)
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
        
        # Convert price to float with two decimals
        price = float(price_text.replace(',', '').replace('Rs.', ''))
        price = round(price, 2)
        
        logger.info(f"Successfully got Aarav Bullion price: {price:.2f}")
        return price
    except Exception as e:
        logger.error(f"Error getting Aarav price: {e}")
        return None

def send_message_to_subscribers(bot, message):
    """Sends a message to all subscribers."""
    for user_id in SUBSCRIBERS:
        try:
            bot.send_message(chat_id=user_id, text=message)
            logger.info(f"Message sent to user {user_id}")
            time.sleep(1)  # Avoid hitting rate limits
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")

def retry_get_prices():
    """Main function to get prices with retries and send a single update."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")

    bot = telegram.Bot(token=token)
    
    if not SUBSCRIBERS:
        logger.info("No subscribers in the list!")
        return

    abc_price = None
    aarav_price = None
    abc_attempts = 0
    aarav_attempts = 0
    
    # Create a single WebDriver instance for all attempts (major optimization)
    driver = setup_driver()
    try:
        while (abc_price is None or aarav_price is None) and (abc_attempts < MAX_RETRIES or aarav_attempts < MAX_RETRIES):
            # Try to get ABC price if we don't have it yet
            if abc_price is None and abc_attempts < MAX_RETRIES:
                abc_price = get_abc_price(driver)
                abc_attempts += 1

            # Try to get Aarav price if we don't have it yet
            if aarav_price is None and aarav_attempts < MAX_RETRIES:
                aarav_price = get_aarav_price(driver)
                aarav_attempts += 1

            # If we don't have both prices yet, wait before retrying
            if abc_price is None or aarav_price is None:
                logger.info(f"Prices not fully retrieved. Waiting {RETRY_DELAY} seconds before retrying...")
                time.sleep(RETRY_DELAY)
    finally:
        # Always close the driver when done to free resources
        driver.quit()

    # Prepare the final message
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"📊 Final Update - {current_time}\n\n"
    
    # Initialize variables to hold calculated prices
    abc_price1 = None
    abc_price2 = None
    diff = None

    if abc_price is not None:
        # Calculate additional prices with two decimal places
        abc_price1 = round((10 * abc_price) / 37.5, 2)
        abc_price2 = round(abc_price1 * 55, 2)
        message += f"ABC Bullion: ${abc_price:.2f} \n 10 Gram: ${abc_price1:.2f} & Rs.{abc_price2:.2f}\n"
    else:
        message += "ABC Bullion: Price unavailable after maximum retries\n"
        
    if aarav_price is not None:
        message += f"Aarav Bullion: Rs.{aarav_price:.2f}\n"
    else:
        message += "Aarav Bullion: Price unavailable after maximum retries\n"
    
    # Calculate and include the difference if both prices are available
    if abc_price2 is not None and aarav_price is not None:
        diff = round(abc_price2 - aarav_price, 2)
        # Determine if ABC is more expensive or cheaper
        if diff > 0:
            comparison = "ABC Bullion is more expensive than Aarav Bullion by"
        elif diff < 0:
            comparison = "Aarav Bullion is more expensive than ABC Bullion by"
            diff = abs(diff)  # Make difference positive for display
        else:
            comparison = "ABC Bullion and Aarav Bullion have the same price."
        
        if diff != 0:
            message += f"Difference: Rs.{diff:.2f})\n"
        else:
            message += f"Difference: Rs.{diff:.2f}\n"
    
    send_message_to_subscribers(bot, message)

if __name__ == "__main__":
    logger.info("Starting price update script with retries...")
    retry_get_prices()
    logger.info("Price update script completed.")
