"""Shared Edge driver setup and Naukri login for the bot scripts."""
import logging
import os
import time

from . import config
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

logger = logging.getLogger(__name__)

NAUKRI_EMAIL = config.get('NAUKRI_EMAIL')
NAUKRI_PASSWORD = config.get('NAUKRI_PASSWORD')
EDGE_DRIVER_PATH = config.get('EDGE_DRIVER_PATH')


def create_edge_driver(capture_network=False):
    """Create and return an Edge WebDriver instance.

    capture_network=True records network requests (driver.get_log("performance")).
    """
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    if capture_network:
        options.set_capability("ms:loggingPrefs", {"performance": "ALL"})
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    # Uncomment the line below to run in headless mode (no visible browser)
    # options.add_argument("--headless=new")

    service = None
    if EDGE_DRIVER_PATH:
        logger.info(f"Using EdgeDriver at: {EDGE_DRIVER_PATH}")
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    elif WEBDRIVER_MANAGER_AVAILABLE:
        try:
            logger.info("Using webdriver-manager to auto-download EdgeDriver...")
            service = EdgeService(EdgeChromiumDriverManager().install())
        except Exception as e:
            # Typically a corporate proxy with SSL interception or no network
            logger.warning(f"webdriver-manager failed ({e}); falling back to Selenium Manager / PATH")

    if service is None:
        logger.info("Using Selenium Manager / EdgeDriver from PATH...")
        service = EdgeService()

    driver = webdriver.Edge(service=service, options=options)
    if capture_network:
        driver.execute_cdp_cmd("Network.enable", {})
    return driver


def login_naukri(driver):
    """Log in to Naukri.com."""
    logger.info("Logging in to Naukri.com...")
    driver.get('https://login.naukri.com/')
    time.sleep(3)

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'usernameField'))
    )

    driver.find_element(By.ID, 'usernameField').send_keys(NAUKRI_EMAIL)
    passwd = driver.find_element(By.ID, 'passwordField')
    passwd.send_keys(NAUKRI_PASSWORD)
    passwd.send_keys(Keys.ENTER)

    # Wait for login to complete
    time.sleep(8)
    logger.info("Login completed.")
