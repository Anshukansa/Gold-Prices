import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import logging
import telegram
from datetime import datetime
import time

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# List of subscriber IDs (replace with your actual subscriber IDs)
SUBSCRIBERS = {
    7932502148  # Example user ID - replace with real ones
}

MAX_RETRIES = 30  # Number of retries before giving up

def setup_driver():
    """Sets up the Selenium WebDriver with headless Chrome."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    chrome_binary_path = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    
    options.binary_location = chrome_binary_path
    service = Service(executable_path=chromedriver_path)
    
    return webdriver.Chrome(service=service, options=options)

def format_url(model, storage):
    base_model = "-".join(model.split("-")[:2])
    return f"https://mobilemonster.com.au/sell-your-phone/apple/mobiles/{base_model}/{model}-{storage}"

def fetch_price_with_retries(driver, model, storage, url):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            logging.info(f"Attempt {retries+1} to fetch price for {model} ({storage})")
            driver.get(url)
            
            # Wait for the element to load
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//label[input[@value='yes']]/div[contains(text(), 'I will accept the reduced price of')]")
                )
            )
            
            if "Page Not Found" in driver.page_source or "404" in driver.title:
                return "N/A"
            
            time.sleep(5)  # Sleep to ensure that the price is fully loaded
            
            reduced_price_element = driver.find_element(
                By.XPATH, "//label[input[@value='yes']]/div[contains(text(), 'I will accept the reduced price of')]"
            )
            price_text = reduced_price_element.text
            
            if "AU$" in price_text:
                return price_text.split("AU$")[-1].split()[0].replace(',', '')
            else:
                return "N/A"
        
        except Exception as e:
            logging.error(f"Error fetching price for {model} ({storage}) on attempt {retries+1}: {e}")
            retries += 1
            time.sleep(5)  # Sleep before retrying

    return "N/A"  # Return N/A after all retries

def fetch_prices_for_two_models(driver, models_pair, storages):
    prices = []
    tabs = []

    for model in models_pair:
        for storage in storages:
            url = format_url(model, storage)
            logging.info(f"Opening URL: {url}")
            driver.execute_script(f"window.open('{url}', '_blank');")
            tabs.append((driver.window_handles[-1], model, storage, url))

    for tab, model, storage, url in tabs:
        driver.switch_to.window(tab)
        try:
            # Attempt to fetch price with retries
            price = fetch_price_with_retries(driver, model, storage, url)
            logging.info(f"Price for {model} ({storage}): {price}")
        except Exception as e:
            logging.error(f"Error fetching price for {model} ({storage}): {e}")
            price = "N/A"

        prices.append((model, storage, price))
        driver.close()

    driver.switch_to.window(driver.window_handles[0])
    return prices

def group_models_by_series(models_data):
    """Groups models by their series (11, 12, 13, 14)."""
    series_groups = {}
    for model in models_data:
        series = model.split()[1][0:2]  # Gets "11", "12", "13", "14" from model name
        if series not in series_groups:
            series_groups[series] = []
        series_groups[series].append(model)
    return series_groups

def format_price(price):
    """Formats the price with appropriate symbol and color emoji."""
    if price == "N/A":
        return "❌"
    try:
        price_val = float(price)
        return f"💰${price}:"  # Formatting the price
    except:
        return "❌"

def format_message_by_series(results):
    """Formats the results into a series of messages grouped by iPhone series."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    messages = []
    
    # Header message
    header_msg = (
        f"📱 *iPhone Price Update*\n"
        f"🕒 {current_time}\n"
        f"🏪 MobileMonster.com.au\n"
        f"{'='*32}\n\n"
    )
    messages.append(header_msg)

    # Group models by series
    series_groups = group_models_by_series(results["Model"])
    
    # Create a message for each series
    for series in sorted(series_groups.keys()):
        series_msg = f"*iPhone {series} Series*\n\n"
        
        for model in series_groups[series]:
            model_msg = f"📱 *{model}*\n"
            model_idx = results["Model"].index(model)
            
            for storage in ["64GB", "128GB", "256GB", "512GB", "1TB"]:
                if model_idx < len(results[storage]):
                    price = results[storage][model_idx]
                    if price and price != "N/A":
                        model_msg += f"  • {storage}: {format_price(price)}\n"
                    else:
                        model_msg += f"  • {storage}: ❌\n"
            
            series_msg += f"{model_msg}\n"
        
        messages.append(series_msg)
    
    # Add footer
    footer_msg = (
        f"{'='*32}\n"
        "💡 *Legend*:\n"
        "💰 = Available Price\n"
        "❌ = Not Available\n\n"
        "📊 _Prices updated every hour_"
    )
    messages.append(footer_msg)
    
    return messages

def send_update():
    """Main function to fetch prices and send updates."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set!")

    bot = telegram.Bot(token=token)
    
    if not SUBSCRIBERS:
        logging.info("No subscribers in the list!")
        return

    models = [
        "iphone-11", "iphone-11-pro", "iphone-11-pro-max",
        "iphone-12", "iphone-12-mini", "iphone-12-pro", "iphone-12-pro-max",
        "iphone-13", "iphone-13-mini", "iphone-13-pro", "iphone-13-pro-max",
        "iphone-14", "iphone-14-plus", "iphone-14-pro", "iphone-14-pro-max"
    ]
    storages = ["64gb", "128gb", "256gb", "512gb", "1tb"]

    results = {storage.upper(): [] for storage in storages}
    results["Model"] = []

    driver = setup_driver()
    
    try:
        for i in range(0, len(models), 2):
            models_pair = models[i:i + 2]
            logging.info(f"Processing models: {models_pair}")
            fetched_data = fetch_prices_for_two_models(driver, models_pair, storages)

            for model, storage, price in fetched_data:
                formatted_model = model.replace("-", " ").title()
                if formatted_model not in results["Model"]:
                    results["Model"].append(formatted_model)
                col_name = storage.upper()
                results[col_name].append(price)

        messages = format_message_by_series(results)

        for subscriber_id in SUBSCRIBERS:
            for message in messages:
                bot.send_message(chat_id=subscriber_id, text=message, parse_mode="Markdown")

    finally:
        driver.quit()

# Running the update function
send_update()
