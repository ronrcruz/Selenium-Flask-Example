from flask import Flask, Response, render_template, request, jsonify, redirect, url_for, make_response
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import json
import os
import re

app = Flask(__name__)

# In-memory storage for scraped leads
scraped_leads = []

# Target websites for scraping based on country
target_websites = {
    'general': [{
        'name': 'Google Maps - Mobile Stores',
        'url': 'https://www.google.com/maps/search/mobile+stores+in+{}',
        'scraper_function': 'scrape_google_maps'
    }, {
        'name': 'Yellow Pages - Mobile Phone Stores',
        'url': 'https://www.paginasamarillas.com.{}/empresas/celulares/',
        'scraper_function': 'scrape_yellow_pages'
    }, {
        'name': 'Trade Portal - Mobile Devices',
        'url': 'https://www.go4worldbusiness.com/find/mobile-device-{}',
        'scraper_function': 'scrape_trade_portal'
    }, {
        'name': 'Trade Shows and Expos',
        'url': 'https://10times.com/{}?q=mobile',
        'scraper_function': 'scrape_trade_shows'
    }],
    'mexico': [{
        'name': 'Directorio de Empresas - Mexico',
        'url': 'https://directorio.com.mx/busqueda/celulares+mayoreo',
        'scraper_function': 'scrape_directorio_mexico'
    }],
    'colombia': [{
        'name': 'Empresite Colombia',
        'url':
        'https://empresite.eleconomistaamerica.co/Actividad/CELULARES-MAYOREO/',
        'scraper_function': 'scrape_empresite'
    }],
    'brazil': [{
        'name': 'GuiaMais Brazil',
        'url': 'https://www.guiamais.com.br/busca/celulares+atacado',
        'scraper_function': 'scrape_guiamais'
    }],
    'argentina': [{
        'name': 'Clarín Clasificados',
        'url':
        'https://www.clasificados.clarin.com/buscador/?q=celulares+mayorista',
        'scraper_function': 'scrape_clarin'
    }]
}

# Countries in Latin America for filtering
latin_american_countries = [
    'Argentina', 'Bolivia', 'Brazil', 'Chile', 'Colombia', 'Costa Rica',
    'Cuba', 'Dominican Republic', 'Ecuador', 'El Salvador', 'Guatemala',
    'Haiti', 'Honduras', 'Mexico', 'Nicaragua', 'Panama', 'Paraguay', 'Peru',
    'Puerto Rico', 'Uruguay', 'Venezuela'
]


def get_driver():
  """Initialize and return a Chrome WebDriver with enhanced anti-detection measures"""
  options = ChromeOptions()

  # Configure headless mode, but with better anti-detection
  options.add_argument("--headless=new")  # Use the newer headless mode
  options.add_argument("--disable-gpu")
  options.add_argument("--no-sandbox")
  options.add_argument("--disable-dev-shm-usage")

  # Add advanced anti-detection measures
  options.add_argument("--disable-blink-features=AutomationControlled")
  options.add_experimental_option("excludeSwitches", ["enable-automation"])
  options.add_experimental_option("useAutomationExtension", False)

  # Set a realistic user agent
  options.add_argument(
      "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  )

  # Set language to Spanish for better results in Latin America
  options.add_argument("--lang=es")

  # Set realistic window size
  options.add_argument("--window-size=1920,1080")

  # Add performance options
  options.add_argument("--disable-extensions")
  options.add_argument("--disable-notifications")
  options.add_argument("--disable-popup-blocking")

  # Create the driver
  driver = webdriver.Chrome(options=options)

  # Execute CDP commands to further avoid detection
  driver.execute_cdp_cmd(
      "Page.addScriptToEvaluateOnNewDocument", {
          "source":
          """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Overwrite the 'plugins' property to use a custom getter
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Overwrite the 'languages' property to use a custom getter
            Object.defineProperty(navigator, 'languages', {
                get: () => ['es-MX', 'es', 'en-US', 'en']
            });

            // Pass the Chrome Test
            window.chrome = {
                runtime: {}
            };
        """
      })

  return driver


def scrape_google_maps(driver, country):
  """Scrape mobile stores from Google Maps with improved reliability"""
  leads = []

  # Define search queries specific to mobile device wholesalers - PRIORITIZE SPANISH QUERIES
  search_queries = [
      # Spanish queries first (primary focus)
      f"mayoristas de celulares en {country}",  # Mobile phone wholesalers
      f"distribuidores mayoristas de celulares en {country}",  # Mobile phone wholesale distributors
      f"proveedores mayoristas de telefonos moviles en {country}",  # Mobile device wholesale suppliers
      f"empresas mayoristas de celulares en {country}",  # Cell phone wholesale companies
      f"distribuidores de smartphones al por mayor en {country}",  # Smartphone wholesale distributors
      f"importadores de celulares en {country}",  # Cell phone importers
      f"mayoristas de accesorios para celulares en {country}",  # Cell phone accessories wholesalers

      # English queries as backup
      f"mobile device wholesalers in {country}",
      f"mobile phone distributors in {country}",
      f"smartphone wholesale suppliers in {country}"
  ]

  # Function to slow down typing to seem more human
  def human_type(element, text):
    for char in text:
      element.send_keys(char)
      time.sleep(0.05)  # Small delay between keystrokes

  # Try multiple search queries to get better results
  for query_idx, query in enumerate(search_queries):
    if query_idx > 0:
      # Add a delay between queries to avoid rate limiting
      time.sleep(3)

    try:
      # Instead of directly navigating to a URL with the search term, we'll:
      # 1. Go to Google Maps homepage
      # 2. Find the search box and type our query
      # 3. Press Enter to search

      print(f"Attempting search for: {query}")

      driver.get("https://www.google.com/maps")

      # Wait for the page to load
      time.sleep(5)

      # Check for any consent dialogs or popups and handle them
      try:
        consent_buttons = driver.find_elements(
            By.XPATH,
            "//button[contains(text(), 'Aceptar todo') or contains(text(), 'Accept all') or contains(text(), 'Acepto') or contains(text(), 'I agree')]"
        )
        if consent_buttons:
          consent_buttons[0].click()
          time.sleep(2)
      except:
        pass

      # Try to find the search box by multiple methods
      search_box = None
      search_selectors = [
          "input#searchboxinput", "input[name='q']",
          "input[aria-label='Buscar en Google Maps']",
          "input[aria-label='Search Google Maps']",
          "input.tactile-searchbox-input"
      ]

      for selector in search_selectors:
        try:
          search_box = WebDriverWait(driver, 10).until(
              EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
          if search_box:
            break
        except:
          continue

      if not search_box:
        print(f"Could not find search box for query: {query}")
        continue

      # Clear the search box and type the query like a human would
      search_box.clear()
      human_type(search_box, query)

      # Press Enter to search
      search_box.send_keys(webdriver.Keys.ENTER)

      # Wait for search results to load
      time.sleep(5)

      # Now verify we have search results by looking for various elements
      result_found = False
      result_selectors = [
          "div[role='article']", ".section-result", ".place-result",
          ".maps-sprite-place-result", ".section-result-content"
      ]

      for selector in result_selectors:
        try:
          results = driver.find_elements(By.CSS_SELECTOR, selector)
          if results and len(results) > 0:
            result_found = True
            print(f"Found {len(results)} results using selector: {selector}")
            break
        except:
          continue

      if not result_found:
        print(f"No results found for query: {query}")
        # Take a screenshot for debugging
        try:
          driver.save_screenshot(f"debug_no_results_{query_idx}.png")
        except:
          pass
        continue

      # Process search results - use multiple selectors to find business listings
      found_businesses = 0
      for selector in result_selectors:
        business_elements = driver.find_elements(By.CSS_SELECTOR, selector)

        if not business_elements or len(business_elements) == 0:
          continue

        print(
            f"Processing {len(business_elements)} businesses from selector: {selector}"
        )
        found_businesses = len(business_elements)

        # Process each business (limit to first 15 for each query)
        for i, business in enumerate(business_elements[:15]):
          try:
            # Extract available info from the list view
            try:
              # Try different approaches to get the business name
              name = None
              name_selectors = [
                  "div[aria-label]", "h3", ".section-result-title",
                  ".section-result-header"
              ]

              for name_selector in name_selectors:
                try:
                  name_elem = business.find_element(By.CSS_SELECTOR,
                                                    name_selector)
                  name = name_elem.text or name_elem.get_attribute(
                      "aria-label")
                  if name:
                    break
                except:
                  continue

              if not name:
                continue  # Skip if we can't find a name

              print(f"Found business: {name}")

              # Add to leads with basic info
              lead = {
                  "name": name,
                  "country": country,
                  "source": "Google Maps",
                  "search_query": query
              }

              # Try to click on the business to get more details
              business.click()
              time.sleep(3)  # Wait for details panel to load

              # Extract additional details from the panel
              try:
                # Address
                address_selectors = [
                    "[data-item-id^='address']",
                    "button[data-tooltip^='Address']",
                    "button[data-item-id*='address']", ".section-info-text",
                    "[data-tooltip*='address']"
                ]

                for addr_selector in address_selectors:
                  try:
                    address_elem = driver.find_element(By.CSS_SELECTOR,
                                                       addr_selector)
                    address = address_elem.text or address_elem.get_attribute(
                        "aria-label")
                    if address:
                      lead["address"] = address
                      break
                  except:
                    continue

                if "address" not in lead:
                  lead["address"] = "Not found"

                # Phone number
                phone_selectors = [
                    "[data-item-id^='phone']", "button[data-tooltip^='Phone']",
                    "button[aria-label^='Phone']", "[data-tooltip*='phone']",
                    ".section-info-text"
                ]

                for phone_selector in phone_selectors:
                  try:
                    phone_elem = driver.find_element(By.CSS_SELECTOR,
                                                     phone_selector)
                    phone = phone_elem.text or phone_elem.get_attribute(
                        "aria-label")
                    if phone:
                      lead["phone"] = phone
                      break
                  except:
                    continue

                if "phone" not in lead:
                  lead["phone"] = "Not found"

                # Website
                website_selectors = [
                    "[data-item-id^='authority']",
                    "a[data-tooltip^='Website']", "a[aria-label^='Website']",
                    "[data-tooltip*='website']", "a[href^='http']"
                ]

                for website_selector in website_selectors:
                  try:
                    website_elem = driver.find_element(By.CSS_SELECTOR,
                                                       website_selector)
                    website = website_elem.get_attribute("href")
                    if website and "google.com" not in website:
                      lead["website"] = website
                      break
                  except:
                    continue

                if "website" not in lead:
                  lead["website"] = "Not found"

                # Category or business type
                category_selectors = [
                    ".section-rating-term", "[aria-label*='Type of place']",
                    ".section-rating-description",
                    ".section-editorial-description"
                ]

                for cat_selector in category_selectors:
                  try:
                    category_elem = driver.find_element(
                        By.CSS_SELECTOR, cat_selector)
                    category = category_elem.text
                    if category:
                      lead["category"] = category
                      break
                  except:
                    continue

                if "category" not in lead:
                  lead["category"] = "Not found"

                # Add the lead to our results
                leads.append(lead)
                print(f"Added lead: {lead['name']}")

                # Click back button or close to return to results
                try:
                  back_selectors = [
                      "button[aria-label='Back']",
                      "button.section-back-to-list-button",
                      "button[jsaction*='back']",
                      "button.mapsConsumerUiBackToResultsButton__button"
                  ]

                  for back_selector in back_selectors:
                    try:
                      back_button = driver.find_element(
                          By.CSS_SELECTOR, back_selector)
                      back_button.click()
                      time.sleep(2)
                      break
                    except:
                      continue
                except:
                  # If we can't go back, just reload with the search query
                  driver.get("https://www.google.com/maps/search/" +
                             query.replace(' ', '+'))
                  time.sleep(5)
              except Exception as detail_ex:
                print(f"Error getting details: {str(detail_ex)}")
                # Still add the basic info
                lead["address"] = "Not found"
                lead["phone"] = "Not found"
                lead["website"] = "Not found"
                lead["category"] = "Not found"
                leads.append(lead)

                # Try to go back to results
                try:
                  driver.get("https://www.google.com/maps/search/" +
                             query.replace(' ', '+'))
                  time.sleep(5)
                except:
                  pass
            except Exception as ex:
              print(f"Error processing business: {str(ex)}")
              continue
          except Exception as ex:
            print(f"Error clicking on business: {str(ex)}")
            continue

        # If we found and processed businesses, break the selector loop
        if found_businesses > 0:
          break

      # If we've already found at least 10 businesses across all queries, stop
      if len(leads) >= 10:
        print(f"Found enough leads ({len(leads)}), stopping search")
        break

    except Exception as e:
      print(f"Error in Google Maps search for {query}: {str(e)}")
      continue

  # Remove any duplicate entries based on name
  unique_leads = []
  seen_names = set()

  for lead in leads:
    if lead["name"] not in seen_names:
      seen_names.add(lead["name"])
      unique_leads.append(lead)

  print(f"Final lead count after removing duplicates: {len(unique_leads)}")
  return unique_leads


def scrape_trade_shows(driver, country):
  """Scrape trade shows and expos related to mobile devices"""
  leads = []

  # Map country names to URL-friendly format
  country_map = {
      'Mexico': 'mexico',
      'Colombia': 'colombia',
      'Brazil': 'brazil',
      'Argentina': 'argentina',
      'Peru': 'peru',
      'Chile': 'chile',
      'Ecuador': 'ecuador',
      'Venezuela': 'venezuela',
      'Guatemala': 'guatemala',
      'Costa Rica': 'costa-rica',
      'Panama': 'panama',
      'Dominican Republic': 'dominican-republic',
      'Bolivia': 'bolivia',
      'Paraguay': 'paraguay',
      'Uruguay': 'uruguay',
      'El Salvador': 'el-salvador',
      'Honduras': 'honduras'
  }

  # Use the country mapping if available, otherwise use lowercase with hyphens
  country_url = country_map.get(country, country.lower().replace(' ', '-'))
  url = target_websites['general'][3]['url'].format(country_url)

  try:
    driver.get(url)

    # Wait for the page to load
    try:
      WebDriverWait(driver, 10).until(
          EC.presence_of_element_located(
              (By.CSS_SELECTOR, ".event-card, .expo-card")))
    except TimeoutException:
      # Try another selector
      try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".eventlist-item")))
      except:
        return [{"error": f"Could not find trade shows for {country}"}]

    # Get all business events
    selectors = [".event-card", ".expo-card", ".eventlist-item"]
    event_elements = []

    for selector in selectors:
      elements = driver.find_elements(By.CSS_SELECTOR, selector)
      if elements:
        event_elements = elements
        break

    for event in event_elements[:10]:  # Limit to first 10
      try:
        # Try different selectors for event name
        name_selectors = [
            ".event-name", ".expo-title", "h2", ".event-title",
            ".eventlist-title"
        ]

        name = None
        for selector in name_selectors:
          try:
            name_element = event.find_element(By.CSS_SELECTOR, selector)
            name = name_element.text
            if name:
              break
          except:
            continue

        if not name:
          continue

        # Try to get date and location
        date = "Not found"
        location = "Not found"

        date_selectors = [
            ".event-date", ".expo-date", ".eventlist-date", ".event-schedule",
            ".date"
        ]

        for selector in date_selectors:
          try:
            date_element = event.find_element(By.CSS_SELECTOR, selector)
            date = date_element.text
            if date:
              break
          except:
            continue

        location_selectors = [
            ".event-location", ".expo-location", ".eventlist-location",
            ".venue", ".location"
        ]

        for selector in location_selectors:
          try:
            location_element = event.find_element(By.CSS_SELECTOR, selector)
            location = location_element.text
            if location:
              break
          except:
            continue

        # Try to get description
        description = "Not found"
        description_selectors = [
            ".event-description", ".expo-description",
            ".eventlist-description", ".description", ".event-details"
        ]

        for selector in description_selectors:
          try:
            description_element = event.find_element(By.CSS_SELECTOR, selector)
            description = description_element.text
            if description:
              break
          except:
            continue

        # Try to get website/link
        link = None
        try:
          link_element = event.find_element(By.CSS_SELECTOR, "a")
          link = link_element.get_attribute("href")
        except:
          link = "Not found"

        leads.append({
            "name": name,
            "event_date": date,
            "location": location,
            "description": description,
            "link": link,
            "country": country,
            "source": "Trade Shows and Expos"
        })
      except Exception as e:
        continue

  except Exception as e:
    return [{"error": f"Error scraping Trade Shows for {country}: {str(e)}"}]

  return leads


def scrape_trade_portal(driver, country):
  """Scrape international trade portal for mobile device businesses"""
  leads = []
  url = target_websites['general'][2]['url'].format(country.lower().replace(
      ' ', '-'))

  try:
    driver.get(url)

    # Wait for results to load
    try:
      WebDriverWait(driver, 10).until(
          EC.presence_of_element_located((By.CSS_SELECTOR, ".supplier-item")))
    except TimeoutException:
      return [{"error": f"Could not load trade portal results for {country}"}]

    # Get all business elements
    business_elements = driver.find_elements(By.CSS_SELECTOR, ".supplier-item")

    for business in business_elements[:15]:  # Limit to first 15
      try:
        # Get business name
        try:
          name_element = business.find_element(By.CSS_SELECTOR,
                                               ".company-name")
          name = name_element.text
        except:
          continue  # Skip if we can't find a name

        # Get business location
        try:
          location_element = business.find_element(By.CSS_SELECTOR,
                                                   ".supplier-location")
          location = location_element.text
        except:
          location = "Not found"

        # Get business description
        try:
          description_element = business.find_element(By.CSS_SELECTOR,
                                                      ".supplier-products")
          description = description_element.text
        except:
          description = "Not found"

        # Get business contact info if available
        try:
          contact_element = business.find_element(By.CSS_SELECTOR,
                                                  ".contact-info")
          contact = contact_element.text
        except:
          contact = "Not found"

        leads.append({
            "name": name,
            "location": location,
            "description": description,
            "contact": contact,
            "country": country,
            "source": "Trade Portal"
        })
      except Exception as e:
        continue

  except Exception as e:
    return [{"error": f"Error scraping Trade Portal for {country}: {str(e)}"}]

  return leads


# LinkedIn scraper function removed to avoid login requirements


def scrape_yellow_pages(driver, country):
  """Scrape Yellow Pages for mobile phone stores"""
  leads = []

  # Map country to domain suffix
  country_map = {
      'Mexico': 'mx',
      'Colombia': 'co',
      'Argentina': 'ar',
      'Peru': 'pe',
      'Chile': 'cl',
      'Ecuador': 'ec',
      'Venezuela': 've',
      'Guatemala': 'gt',
      'El Salvador': 'sv',
      'Honduras': 'hn',
      'Costa Rica': 'cr',
      'Panama': 'pa',
      'Dominican Republic': 'do',
      'Bolivia': 'bo',
      'Paraguay': 'py',
      'Uruguay': 'uy'
  }

  # Use the domain suffix if available, otherwise skip
  domain_suffix = country_map.get(country)
  if not domain_suffix:
    return [{"error": f"Yellow Pages not supported for {country}"}]

  url = target_websites['general'][1]['url'].format(domain_suffix)

  try:
    driver.get(url)

    # Wait for results to load
    try:
      WebDriverWait(driver, 10).until(
          EC.presence_of_element_located((By.CSS_SELECTOR, ".list-item")))
    except TimeoutException:
      # Try an alternative selector if the first one fails
      try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".business-card")))
      except:
        return [{
            "error":
            f"Could not identify listing elements on Yellow Pages {country}"
        }]

    # Try different selectors based on country-specific Yellow Pages format
    selectors = [
        ".list-item", ".business-card", ".listing-item", ".merchant-listing"
    ]

    business_elements = []
    for selector in selectors:
      elements = driver.find_elements(By.CSS_SELECTOR, selector)
      if elements:
        business_elements = elements
        break

    # If we found business elements, extract information
    for business in business_elements[:15]:  # Limit to first 15
      try:
        # Try different selectors for business name
        name_selectors = [
            "h2.name", ".business-name", "h3.business-name", ".listing-title",
            "h3", ".company-name"
        ]

        name = None
        for selector in name_selectors:
          try:
            name_element = business.find_element(By.CSS_SELECTOR, selector)
            name = name_element.text
            if name:
              break
          except:
            continue

        if not name:
          continue

        # Try different selectors for address
        address_selectors = [
            ".address", ".listing-address", ".merchant-address",
            ".business-address", ".direccion"
        ]

        address = "Not found"
        for selector in address_selectors:
          try:
            address_element = business.find_element(By.CSS_SELECTOR, selector)
            address = address_element.text
            if address:
              break
          except:
            continue

        # Try different selectors for phone
        phone_selectors = [
            ".phone", ".listing-phone", ".merchant-phone", ".business-phone",
            ".telefono"
        ]

        phone = "Not found"
        for selector in phone_selectors:
          try:
            phone_element = business.find_element(By.CSS_SELECTOR, selector)
            phone = phone_element.text
            if phone:
              break
          except:
            continue

        leads.append({
            "name": name,
            "address": address,
            "phone": phone,
            "country": country,
            "source": "Yellow Pages"
        })
      except Exception as e:
        continue

  except Exception as e:
    return [{"error": f"Error scraping Yellow Pages for {country}: {str(e)}"}]

  return leads


def scrape_directorio_mexico(driver, country="Mexico"):
  """Scrape business leads from Directorio Mexico"""
  leads = []
  url = target_websites['mexico'][0]['url']

  try:
    driver.get(url)

    # Wait for results to load
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".empresa")))

    # Get all business elements
    business_elements = driver.find_elements(By.CSS_SELECTOR, ".empresa")

    for business in business_elements[:15]:  # Limit to first 15
      try:
        name = business.find_element(By.CSS_SELECTOR, "h2 a").text

        try:
          address = business.find_element(By.CSS_SELECTOR, ".direccion").text
        except:
          address = "Not found"

        try:
          phone = business.find_element(By.CSS_SELECTOR, ".telefono").text
        except:
          phone = "Not found"

        leads.append({
            "name": name,
            "address": address,
            "phone": phone,
            "country": "Mexico",
            "source": "Directorio Mexico"
        })
      except:
        continue

  except Exception as e:
    return [{"error": str(e)}]

  return leads


def scrape_empresite(driver, country="Colombia"):
  """Scrape business leads from Empresite Colombia"""
  leads = []
  url = target_websites['colombia'][0]['url']

  try:
    driver.get(url)

    # Wait for results to load
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".m-empresas-item")))

    # Get all business elements
    business_elements = driver.find_elements(By.CSS_SELECTOR,
                                             ".m-empresas-item")

    for business in business_elements[:15]:  # Limit to first 15
      try:
        name = business.find_element(By.CSS_SELECTOR, "h2 a").text

        try:
          address = business.find_element(By.CSS_SELECTOR,
                                          ".m-empresas-info p").text
        except:
          address = "Not found"

        leads.append({
            "name": name,
            "address": address,
            "country": "Colombia",
            "source": "Empresite Colombia"
        })
      except:
        continue

  except Exception as e:
    return [{"error": str(e)}]

  return leads


def scrape_manual_url(driver, url, country):
  """Generic scraper for custom URLs"""
  leads = []

  try:
    driver.get(url)

    # Wait a bit for the page to load
    time.sleep(5)

    # Get the page source for analysis
    page_source = driver.page_source

    # Extract all phone numbers (simple regex pattern)
    phone_pattern = r'\+?[\d\s()-]{8,}'
    phones = re.findall(phone_pattern, page_source)

    # Extract email addresses
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, page_source)

    # Look for potential business names (headings)
    business_names = []
    headings = driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3")
    for heading in headings:
      business_names.append(heading.text)

    # Combine the results
    lead = {
        "url": url,
        "possible_business_names": business_names[:5],  # Limit to first 5
        "possible_phones":
        list(set(phones))[:5],  # Remove duplicates and limit
        "possible_emails":
        list(set(emails))[:5],  # Remove duplicates and limit
        "country": country,
        "source": "Manual URL"
    }

    leads.append(lead)

  except Exception as e:
    return [{"error": str(e)}]

  return leads


# Flask routes


@app.route('/')
def index():
  """Main page with lead generation form"""
  language = request.cookies.get('language', 'en')  # Default to English
  return render_template('index.html',
                         countries=latin_american_countries,
                         language=language)


@app.route('/set-language/<lang>')
def set_language(lang):
  """Set language preference in cookie and redirect back"""
  response = make_response(redirect(request.referrer or '/'))
  response.set_cookie('language', lang,
                      max_age=60 * 60 * 24 * 365)  # Cookie lasts 1 year
  return response


@app.route('/google-maps-focus')
def google_maps_focus():
  """Page specifically focused on Google Maps scraping"""
  language = request.cookies.get('language', 'en')  # Default to English
  return render_template('google_maps_focus.html',
                         countries=latin_american_countries,
                         language=language)


@app.route('/scrape', methods=['POST'])
def scrape():
  """Handle scraping request"""
  country = request.form.get('country', '')
  scrape_type = request.form.get('scrape_type', '')
  custom_url = request.form.get('custom_url', '')

  # Initialize response
  response = {"success": False, "message": "", "leads": []}

  # Get a new driver instance
  driver = get_driver()

  try:
    if scrape_type == 'custom_url' and custom_url:
      # Scrape a custom URL provided by the user
      leads = scrape_manual_url(driver, custom_url, country)
      response["leads"] = leads

    elif scrape_type == 'country_specific' and country.lower(
    ) in target_websites:
      # Use country-specific scrapers
      for website in target_websites[country.lower()]:
        scraper_function_name = website['scraper_function']
        if scraper_function_name in globals():
          country_leads = globals()[scraper_function_name](driver, country)
          response["leads"].extend(country_leads)

    elif scrape_type == 'google_maps_only':
      # Only use Google Maps scraper
      leads = scrape_google_maps(driver, country)
      response["leads"] = leads

    else:
      # Use general scrapers
      for website in target_websites['general']:
        scraper_function_name = website['scraper_function']
        if scraper_function_name in globals():
          general_leads = globals()[scraper_function_name](driver, country)
          response["leads"].extend(general_leads)

    # Update the global leads storage
    global scraped_leads
    scraped_leads.extend(response["leads"])

    response["success"] = True
    response["message"] = f"Found {len(response['leads'])} leads"

  except Exception as e:
    response["message"] = f"Error: {str(e)}"

  finally:
    # Close the driver
    driver.quit()

  return render_template('results.html', response=response)


@app.route('/view-leads')
def view_leads():
  """View all scraped leads"""
  return render_template('leads.html', leads=scraped_leads)


@app.route('/export-leads')
def export_leads():
  """Export leads as JSON"""
  return jsonify(scraped_leads)


@app.route('/clear-leads')
def clear_leads():
  """Clear all stored leads"""
  global scraped_leads
  scraped_leads = []
  return redirect(url_for('index'))


@app.route('/selenium')
def selenium_endpoint():
  """Legacy endpoint for testing Selenium functionality"""
  driver = get_driver()
  try:
    driver.get("http://www.python.org")
    assert "Python" in driver.title
    page_source = driver.page_source
  finally:
    driver.quit()

  return Response(page_source, mimetype='text/html')


# Create templates directory if it doesn't exist
if not os.path.exists('templates'):
  os.makedirs('templates')

# Create template files
with open('templates/index.html', 'w') as f:
  f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>{{ language == 'es' and 'Generador de Leads para Mayoristas de Dispositivos Móviles' or 'Mobile Device Wholesale Lead Generator' }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        select, input, button {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        button {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 10px;
            cursor: pointer;
            font-weight: bold;
            margin-top: 10px;
        }
        button:hover {
            background-color: #2980b9;
        }
        .actions {
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
        }
        .actions a {
            display: inline-block;
            padding: 8px 15px;
            background-color: #95a5a6;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
        }
        .description {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
            font-size: 14px;
            border-left: 4px solid #3498db;
        }
        .highlight-box {
            background-color: #e8f4fd;
            padding: 15px;
            border-radius: 4px;
            margin-top: 20px;
            border: 1px solid #3498db;
            text-align: center;
        }
        .highlight-box a {
            display: inline-block;
            background-color: #3498db;
            color: white;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 4px;
            font-weight: bold;
            margin-top: 10px;
        }
        .language-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
        }
        .language-toggle a {
            display: inline-block;
            padding: 5px 10px;
            background-color: #f0f0f0;
            color: #333;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
        }
        .language-toggle a.active {
            background-color: #3498db;
            color: white;
        }
        /* Loading overlay */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(255,255,255,0.9);
            z-index: 1000;
            text-align: center;
            padding-top: 150px;
        }
        .loader {
            border: 16px solid #f3f3f3;
            border-top: 16px solid #3498db;
            border-radius: 50%;
            width: 80px;
            height: 80px;
            animation: spin 2s linear infinite;
            margin: 0 auto 30px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading-text {
            font-size: 24px;
            color: #3498db;
            margin-bottom: 20px;
        }
        .loading-subtext {
            font-size: 16px;
            color: #7f8c8d;
            max-width: 80%;
            margin: 0 auto;
        }
    </style>
</head>
<body>
    <!-- Loading overlay -->
    <div id="loadingOverlay" class="loading-overlay">
        <div class="loader"></div>
        <div class="loading-text">{{ language == 'es' and 'Buscando Leads de Negocio...' or 'Searching for Business Leads...' }}</div>
        <div class="loading-subtext">{{ language == 'es' and 'Esto puede tardar hasta 2 minutos. Por favor, no cierres esta ventana.' or 'This may take up to 2 minutes. Please do not close this window.' }}</div>
    </div>

    <!-- Language toggle -->
    <div class="language-toggle">
        <a href="/set-language/en" class="{{ language == 'en' and 'active' or '' }}">English</a>
        <a href="/set-language/es" class="{{ language == 'es' and 'active' or '' }}">Español</a>
    </div>

    <div class="container">
        <h1>{{ language == 'es' and 'Generador de Leads para Mayoristas de Dispositivos Móviles' or 'Mobile Device Wholesale Lead Generator' }}</h1>

        <div class="description">
            {% if language == 'es' %}
            <p>Esta herramienta te ayuda a encontrar leads de negocios de dispositivos móviles en América Latina. Selecciona un país, elige un método de búsqueda y haz clic en "Generar Leads" para comenzar.</p>
            <p><strong>Nota:</strong> Esta herramienta respeta los términos de servicio de los sitios web y debe utilizarse solo para prospección comercial legítima.</p>
            {% else %}
            <p>This tool helps you find mobile device business leads in Latin America. Select a country, choose a scraping method, and click "Generate Leads" to start.</p>
            <p><strong>Note:</strong> This tool respects website terms of service and should only be used for legitimate business prospecting.</p>
            {% endif %}
        </div>

        <div class="highlight-box">
            {% if language == 'es' %}
            <h3>¿Buscas los mejores resultados?</h3>
            <p>Prueba nuestro rastreador enfocado en Google Maps para obtener leads de mayoristas de dispositivos móviles de alta calidad.</p>
            <a href="/google-maps-focus">Cambiar al Modo Enfocado de Google Maps</a>
            {% else %}
            <h3>Looking for the best results?</h3>
            <p>Try our focused Google Maps scraper for high-quality mobile device wholesale leads.</p>
            <a href="/google-maps-focus">Switch to Google Maps Focus Mode</a>
            {% endif %}
        </div>

        <form id="scrapeForm" action="/scrape" method="post">
            <div class="form-group">
                <label for="country">{{ language == 'es' and 'País Objetivo:' or 'Target Country:' }}</label>
                <select name="country" id="country" required>
                    {% for country in countries %}
                    <option value="{{ country }}">{{ country }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="form-group">
                <label for="scrape_type">{{ language == 'es' and 'Método de Búsqueda:' or 'Scraping Method:' }}</label>
                <select name="scrape_type" id="scrape_type" onchange="toggleCustomUrl()">
                    <option value="general">{{ language == 'es' and 'General (Múltiples Fuentes)' or 'General (Multiple Sources)' }}</option>
                    <option value="country_specific">{{ language == 'es' and 'Fuentes Específicas del País' or 'Country-Specific Sources' }}</option>
                    <option value="custom_url">{{ language == 'es' and 'URL Personalizada' or 'Custom URL' }}</option>
                </select>
            </div>

            <div class="form-group" id="custom_url_group" style="display: none;">
                <label for="custom_url">{{ language == 'es' and 'URL Personalizada:' or 'Custom URL:' }}</label>
                <input type="url" name="custom_url" id="custom_url" placeholder="https://example.com">
            </div>

            <button type="submit" id="submitButton">{{ language == 'es' and 'Generar Leads' or 'Generate Leads' }}</button>
        </form>

        <div class="actions">
            <a href="/view-leads">{{ language == 'es' and 'Ver Todos los Leads' or 'View All Leads' }}</a>
            <a href="/export-leads" target="_blank">{{ language == 'es' and 'Exportar Leads (JSON)' or 'Export Leads (JSON)' }}</a>
            <a href="/clear-leads" onclick="return confirm('{{ language == 'es' and '¿Estás seguro de que quieres borrar todos los leads?' or 'Are you sure you want to clear all leads?' }}')">{{ language == 'es' and 'Borrar Todos los Leads' or 'Clear All Leads' }}</a>
        </div>
    </div>

    <script>
        function toggleCustomUrl() {
            var scrapeType = document.getElementById('scrape_type').value;
            var customUrlGroup = document.getElementById('custom_url_group');

            if (scrapeType === 'custom_url') {
                customUrlGroup.style.display = 'block';
                document.getElementById('custom_url').required = true;
            } else {
                customUrlGroup.style.display = 'none';
                document.getElementById('custom_url').required = false;
            }
        }

        document.getElementById('scrapeForm').addEventListener('submit', function(e) {
            // Show loading overlay
            document.getElementById('loadingOverlay').style.display = 'block';

            // Disable the submit button to prevent multiple submissions
            document.getElementById('submitButton').disabled = true;
        });
    </script>
</body>
</html>
''')

# Create templates directory if it doesn't exist
if not os.path.exists('templates'):
  os.makedirs('templates')

# Create template files
with open('templates/google_maps_focus.html', 'w') as f:
  f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>{{ language == 'es' and 'Generador de Leads con Google Maps | Mayoristas de Dispositivos Móviles' or 'Google Maps Lead Generator | Mobile Device Wholesale' }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
        }
        .google-logo {
            text-align: center;
            margin: 20px 0;
        }
        .google-logo img {
            height: 40px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        select, input, button {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
            font-size: 16px;
        }
        button {
            background-color: #4285F4;
            color: white;
            border: none;
            padding: 12px;
            cursor: pointer;
            font-weight: bold;
            margin-top: 10px;
            font-size: 16px;
        }
        button:hover {
            background-color: #2b72e6;
        }
        .actions {
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
        }
        .actions a {
            display: inline-block;
            padding: 8px 15px;
            background-color: #95a5a6;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
        }
        .description {
            background-color: #e8f4fd;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
            font-size: 14px;
            border-left: 4px solid #4285F4;
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 20px 0;
        }
        .feature-item {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            border-left: 3px solid #4285F4;
        }
        .feature-item h3 {
            margin-top: 0;
            color: #4285F4;
        }
        .back-link {
            display: inline-block;
            margin-top: 20px;
            color: #3498db;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
        .language-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
        }
        .language-toggle a {
            display: inline-block;
            padding: 5px 10px;
            background-color: #f0f0f0;
            color: #333;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
        }
        .language-toggle a.active {
            background-color: #4285F4;
            color: white;
        }
        /* Loading overlay */
        .loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(255,255,255,0.9);
            z-index: 1000;
            text-align: center;
            padding-top: 150px;
        }
        .loader {
            border: 16px solid #f3f3f3;
            border-top: 16px solid #3498db;
            border-radius: 50%;
            width: 80px;
            height: 80px;
            animation: spin 2s linear infinite;
            margin: 0 auto 30px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading-text {
            font-size: 24px;
            color: #3498db;
            margin-bottom: 20px;
        }
        .loading-subtext {
            font-size: 16px;
            color: #7f8c8d;
            max-width: 80%;
            margin: 0 auto;
        }
    </style>
</head>
<body>
    <!-- Loading overlay -->
    <div id="loadingOverlay" class="loading-overlay">
        <div class="loader"></div>
        <div class="loading-text">{{ language == 'es' and 'Buscando Leads de Negocio...' or 'Searching for Business Leads...' }}</div>
        <div class="loading-subtext">{{ language == 'es' and 'Esto puede tardar hasta 2 minutos. Por favor, no cierres esta ventana.' or 'This may take up to 2 minutes. Please do not close this window.' }}</div>
    </div>

    <!-- Language toggle -->
    <div class="language-toggle">
        <a href="/set-language/en" class="{{ language == 'en' and 'active' or '' }}">English</a>
        <a href="/set-language/es" class="{{ language == 'es' and 'active' or '' }}">Español</a>
    </div>

    <div class="container">
        <h1>{{ language == 'es' and 'Generador de Leads con Google Maps' or 'Google Maps Lead Generator' }}</h1>
        <div class="google-logo">
            <span style="color:#4285F4;font-size:24px;font-weight:bold;">G</span>
            <span style="color:#EA4335;font-size:24px;font-weight:bold;">o</span>
            <span style="color:#FBBC05;font-size:24px;font-weight:bold;">o</span>
            <span style="color:#4285F4;font-size:24px;font-weight:bold;">g</span>
            <span style="color:#34A853;font-size:24px;font-weight:bold;">l</span>
            <span style="color:#EA4335;font-size:24px;font-weight:bold;">e</span>
            <span style="color:#777;font-size:24px;font-weight:bold;"> Maps</span>
            <span style="color:#4285F4;font-size:24px;font-weight:bold;"> {{ language == 'es' and 'Enfocado' or 'Focus' }}</span>
        </div>

        <div class="description">
            {% if language == 'es' %}
            <p>Nuestro rastreador de Google Maps está específicamente optimizado para encontrar mayoristas y distribuidores de dispositivos móviles en América Latina. Esta herramienta especializada utiliza múltiples consultas de búsqueda en español para encontrar los leads más relevantes.</p>
            {% else %}
            <p>Our Google Maps scraper is specifically optimized for finding mobile device wholesalers and distributors in Latin America. This specialized tool uses multiple search queries in Spanish to find the most relevant leads.</p>
            {% endif %}
        </div>

        <div class="feature-grid">
            <div class="feature-item">
                <h3>{% if language == 'es' %}Múltiples Consultas en Español{% else %}Multiple Spanish Queries{% endif %}</h3>
                <p>{% if language == 'es' %}Utiliza términos de búsqueda en español para encontrar más leads relevantes{% else %}Uses Spanish search terms to find more relevant leads{% endif %}</p>
            </div>
            <div class="feature-item">
                <h3>{% if language == 'es' %}Información Detallada{% else %}Detailed Information{% endif %}</h3>
                <p>{% if language == 'es' %}Extrae nombres de negocios, direcciones, números de teléfono y sitios web{% else %}Extracts business names, addresses, phone numbers, and websites{% endif %}</p>
            </div>
            <div class="feature-item">
                <h3>{% if language == 'es' %}Detección Inteligente{% else %}Smart Detection{% endif %}</h3>
                <p>{% if language == 'es' %}Medidas mejoradas anti-detección para resultados más confiables{% else %}Enhanced anti-detection measures for more reliable results{% endif %}</p>
            </div>
            <div class="feature-item">
                <h3>{% if language == 'es' %}Eliminación de Duplicados{% else %}Duplicate Removal{% endif %}</h3>
                <p>{% if language == 'es' %}Elimina automáticamente entradas de negocios duplicadas{% else %}Automatically removes duplicate business entries{% endif %}</p>
            </div>
        </div>

        <form id="scrapeForm" action="/scrape" method="post">
            <input type="hidden" name="scrape_type" value="google_maps_only">

            <div class="form-group">
                <label for="country">{% if language == 'es' %}País Objetivo:{% else %}Target Country:{% endif %}</label>
                <select name="country" id="country" required>
                    {% for country in countries %}
                    <option value="{{ country }}">{{ country }}</option>
                    {% endfor %}
                </select>
            </div>

            <button type="submit" id="submitButton">{% if language == 'es' %}Generar Leads de Google Maps{% else %}Generate Google Maps Leads{% endif %}</button>
        </form>

        <div class="actions">
            <a href="/view-leads">{% if language == 'es' %}Ver Todos los Leads{% else %}View All Leads{% endif %}</a>
            <a href="/export-leads" target="_blank">{% if language == 'es' %}Exportar Leads (JSON){% else %}Export Leads (JSON){% endif %}</a>
            <a href="/clear-leads" onclick="return confirm('{% if language == 'es' %}¿Estás seguro de que quieres borrar todos los leads?{% else %}Are you sure you want to clear all leads?{% endif %}')">{% if language == 'es' %}Borrar Todos los Leads{% else %}Clear All Leads{% endif %}</a>
        </div>

        <a href="/" class="back-link">{% if language == 'es' %}← Volver al generador principal{% else %}← Back to main lead generator{% endif %}</a>
    </div>

    <script>
        document.getElementById('scrapeForm').addEventListener('submit', function(e) {
            // Show loading overlay
            document.getElementById('loadingOverlay').style.display = 'block';

            // Disable the submit button to prevent multiple submissions
            document.getElementById('submitButton').disabled = true;
        });
    </script>
</body>
</html>
''')

with open('templates/results.html', 'w') as f:
  f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>{{ language == 'es' and 'Resultados de Búsqueda' or 'Scraping Results' }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
        }
        .result-message {
            padding: 10px;
            background-color: #e3f2fd;
            border-radius: 4px;
            margin-bottom: 20px;
            text-align: center;
        }
        .lead-card {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 15px;
            background-color: #fff;
        }
        .lead-source {
            font-size: 12px;
            color: #7f8c8d;
            margin-bottom: 5px;
        }
        .lead-name {
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 5px;
        }
        .lead-detail {
            margin-bottom: 3px;
            font-size: 14px;
        }
        .actions {
            margin-top: 20px;
            text-align: center;
        }
        .actions a {
            display: inline-block;
            padding: 8px 15px;
            background-color: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin: 0 5px;
        }
        .error {
            color: #e74c3c;
            font-style: italic;
        }
        .search-query {
            font-size: 11px;
            color: #999;
            font-style: italic;
            margin-top: 2px;
        }
        .website-link {
            background-color: #f8f9fa;
            padding: 5px 10px;
            border-radius: 4px;
            display: inline-block;
            margin-top: 5px;
        }
        .website-link a {
            color: #2980b9;
            text-decoration: none;
        }
        .badge {
            display: inline-block;
            padding: 3px 7px;
            font-size: 11px;
            background-color: #e67e22;
            color: white;
            border-radius: 10px;
            margin-left: 5px;
        }
        .language-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
        }
        .language-toggle a {
            display: inline-block;
            padding: 5px 10px;
            background-color: #f0f0f0;
            color: #333;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
        }
        .language-toggle a.active {
            background-color: #3498db;
            color: white;
        }
    </style>
</head>
<body>
    <!-- Language toggle -->
    <div class="language-toggle">
        <a href="/set-language/en" class="{{ language == 'en' and 'active' or '' }}">English</a>
        <a href="/set-language/es" class="{{ language == 'es' and 'active' or '' }}">Español</a>
    </div>

    <div class="container">
        <h1>{{ language == 'es' and 'Resultados de Búsqueda' or 'Scraping Results' }}</h1>

        <div class="result-message">
            {{ response.message }}
        </div>

        {% if response.leads %}
            {% for lead in response.leads %}
                <div class="lead-card">
                    {% if lead.error %}
                        <p class="error">{{ language == 'es' and 'Error:' or 'Error:' }} {{ lead.error }}</p>
                    {% else %}
                        <div class="lead-source">
                            {{ language == 'es' and 'Fuente:' or 'Source:' }} {{ lead.source }} - {{ lead.country }}
                            {% if lead.source == "Google Maps" %}
                                <span class="badge">Maps</span>
                            {% endif %}
                        </div>

                        {% if lead.name %}
                            <div class="lead-name">{{ lead.name }}</div>
                        {% endif %}

                        {% if lead.search_query %}
                            <div class="search-query">{{ language == 'es' and 'Encontrado usando:' or 'Found using:' }} "{{ lead.search_query }}"</div>
                        {% endif %}

                        {% if lead.description %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Descripción:' or 'Description:' }}</strong> {{ lead.description }}</div>
                        {% endif %}

                        {% if lead.category %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Categoría:' or 'Category:' }}</strong> {{ lead.category }}</div>
                        {% endif %}

                        {% if lead.address %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Dirección:' or 'Address:' }}</strong> {{ lead.address }}</div>
                        {% endif %}

                        {% if lead.phone %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Teléfono:' or 'Phone:' }}</strong> {{ lead.phone }}</div>
                        {% endif %}

                        {% if lead.website and lead.website != "Not found" %}
                            <div class="lead-detail">
                                <strong>{{ language == 'es' and 'Sitio Web:' or 'Website:' }}</strong> 
                                <div class="website-link">
                                    <a href="{{ lead.website }}" target="_blank">{{ lead.website }}</a>
                                </div>
                            </div>
                        {% endif %}

                        {% if lead.link %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Enlace:' or 'Link:' }}</strong> <a href="{{ lead.link }}" target="_blank">{{ lead.link }}</a></div>
                        {% endif %}

                        {% if lead.url %}
                            <div class="lead-detail"><strong>URL:</strong> <a href="{{ lead.url }}" target="_blank">{{ lead.url }}</a></div>
                        {% endif %}

                        {% if lead.possible_business_names %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Posibles Nombres de Negocios:' or 'Possible Business Names:' }}</strong></div>
                            <ul>
                                {% for name in lead.possible_business_names %}
                                    <li>{{ name }}</li>
                                {% endfor %}
                            </ul>
                        {% endif %}

                        {% if lead.possible_phones %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Posibles Números de Teléfono:' or 'Possible Phone Numbers:' }}</strong></div>
                            <ul>
                                {% for phone in lead.possible_phones %}
                                    <li>{{ phone }}</li>
                                {% endfor %}
                            </ul>
                        {% endif %}

                        {% if lead.possible_emails %}
                            <div class="lead-detail"><strong>{{ language == 'es' and 'Posibles Correos Electrónicos:' or 'Possible Emails:' }}</strong></div>
                            <ul>
                                {% for email in lead.possible_emails %}
                                    <li>{{ email }}</li>
                                {% endfor %}
                            </ul>
                        {% endif %}
                    {% endif %}
                </div>
            {% endfor %}
        {% else %}
            <p>{{ language == 'es' and 'No se encontraron leads.' or 'No leads found.' }}</p>
        {% endif %}

        <div class="actions">
            <a href="/">{{ language == 'es' and 'Volver al Inicio' or 'Back to Home' }}</a>
            <a href="/view-leads">{{ language == 'es' and 'Ver Todos los Leads' or 'View All Leads' }}</a>
        </div>
    </div>
</body>
</html>
''')

with open('templates/leads.html', 'w') as f:
  f.write('''
<!DOCTYPE html>
<html>
<head>
    <title>{{ language == 'es' and 'Todos los Leads' or 'All Leads' }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            text-align: center;
        }
        .lead-card {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 15px;
            background-color: #fff;
        }
        .lead-source {
            font-size: 12px;
            color: #7f8c8d;
            margin-bottom: 5px;
        }
        .lead-name {
            font-weight: bold;
            font-size: 16px;
            margin-bottom: 5px;
        }
        .lead-detail {
            margin-bottom: 3px;
            font-size: 14px;
        }
        .actions {
            margin-top: 20px;
            text-align: center;
        }
        .actions a {
            display: inline-block;
            padding: 8px 15px;
            background-color: #3498db;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin: 0 5px;
        }
        .filters {
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .filter-group {
            margin-bottom: 10px;
        }
        .filter-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        .filter-group select, .filter-group input {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .error {
            color: #e74c3c;
            font-style: italic;
        }
        .no-leads {
            text-align: center;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .language-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
        }
        .language-toggle a {
            display: inline-block;
            padding: 5px 10px;
            background-color: #f0f0f0;
            color: #333;
            text-decoration: none;
            border-radius: 4px;
            font-size: 14px;
        }
        .language-toggle a.active {
            background-color: #3498db;
            color: white;
        }
        .website-link {
            background-color: #f8f9fa;
            padding: 5px 10px;
            border-radius: 4px;
            display: inline-block;
            margin-top: 5px;
        }
        .website-link a {
            color: #2980b9;
            text-decoration: none;
        }
        .badge {
            display: inline-block;
            padding: 3px 7px;
            font-size: 11px;
            background-color: #e67e22;
            color: white;
            border-radius: 10px;
            margin-left: 5px;
        }
    </style>
</head>
<body>
    <!-- Language toggle -->
    <div class="language-toggle">
        <a href="/set-language/en" class="{{ language == 'en' and 'active' or '' }}">English</a>
        <a href="/set-language/es" class="{{ language == 'es' and 'active' or '' }}">Español</a>
    </div>

    <div class="container">
        <h1>{{ language == 'es' and 'Todos los Leads Recopilados' or 'All Scraped Leads' }}</h1>

        <div class="filters">
            <div class="filter-group">
                <label for="country-filter">{{ language == 'es' and 'Filtrar por País:' or 'Filter by Country:' }}</label>
                <select id="country-filter" onchange="filterLeads()">
                    <option value="">{{ language == 'es' and 'Todos los Países' or 'All Countries' }}</option>
                    <!-- Countries will be dynamically added with JavaScript -->
                </select>
            </div>

            <div class="filter-group">
                <label for="source-filter">{{ language == 'es' and 'Filtrar por Fuente:' or 'Filter by Source:' }}</label>
                <select id="source-filter" onchange="filterLeads()">
                    <option value="">{{ language == 'es' and 'Todas las Fuentes' or 'All Sources' }}</option>
                    <!-- Sources will be dynamically added with JavaScript -->
                </select>
            </div>

            <div class="filter-group">
                <label for="search-filter">{{ language == 'es' and 'Buscar:' or 'Search:' }}</label>
                <input type="text" id="search-filter" onkeyup="filterLeads()" placeholder="{{ language == 'es' and 'Buscar por nombre, teléfono, dirección...' or 'Search by name, phone, address...' }}">
            </div>
        </div>

        <div id="leads-container">
            {% if leads %}
                {% for lead in leads %}
                    <div class="lead-card" 
                         data-country="{{ lead.country }}" 
                         data-source="{{ lead.source }}">
                        {% if lead.error %}
                            <p class="error">{{ language == 'es' and 'Error:' or 'Error:' }} {{ lead.error }}</p>
                        {% else %}
                            <div class="lead-source">
                                {{ language == 'es' and 'Fuente:' or 'Source:' }} {{ lead.source }} - {{ lead.country }}
                                {% if lead.source == "Google Maps" %}
                                    <span class="badge">Maps</span>
                                {% endif %}
                            </div>

                            {% if lead.name %}
                                <div class="lead-name">{{ lead.name }}</div>
                            {% endif %}

                            {% if lead.search_query %}
                                <div class="search-query">{{ language == 'es' and 'Encontrado usando:' or 'Found using:' }} "{{ lead.search_query }}"</div>
                            {% endif %}

                            {% if lead.description %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Descripción:' or 'Description:' }}</strong> {{ lead.description }}</div>
                            {% endif %}

                            {% if lead.category %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Categoría:' or 'Category:' }}</strong> {{ lead.category }}</div>
                            {% endif %}

                            {% if lead.address %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Dirección:' or 'Address:' }}</strong> {{ lead.address }}</div>
                            {% endif %}

                            {% if lead.phone %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Teléfono:' or 'Phone:' }}</strong> {{ lead.phone }}</div>
                            {% endif %}

                            {% if lead.website and lead.website != "Not found" %}
                                <div class="lead-detail">
                                    <strong>{{ language == 'es' and 'Sitio Web:' or 'Website:' }}</strong> 
                                    <div class="website-link">
                                        <a href="{{ lead.website }}" target="_blank">{{ lead.website }}</a>
                                    </div>
                                </div>
                            {% endif %}

                            {% if lead.link %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Enlace:' or 'Link:' }}</strong> <a href="{{ lead.link }}" target="_blank">{{ lead.link }}</a></div>
                            {% endif %}

                            {% if lead.url %}
                                <div class="lead-detail"><strong>URL:</strong> <a href="{{ lead.url }}" target="_blank">{{ lead.url }}</a></div>
                            {% endif %}

                            {% if lead.possible_business_names %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Posibles Nombres de Negocios:' or 'Possible Business Names:' }}</strong></div>
                                <ul>
                                    {% for name in lead.possible_business_names %}
                                        <li>{{ name }}</li>
                                    {% endfor %}
                                </ul>
                            {% endif %}

                            {% if lead.possible_phones %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Posibles Números de Teléfono:' or 'Possible Phone Numbers:' }}</strong></div>
                                <ul>
                                    {% for phone in lead.possible_phones %}
                                        <li>{{ phone }}</li>
                                    {% endfor %}
                                </ul>
                            {% endif %}

                            {% if lead.possible_emails %}
                                <div class="lead-detail"><strong>{{ language == 'es' and 'Posibles Correos Electrónicos:' or 'Possible Emails:' }}</strong></div>
                                <ul>
                                    {% for email in lead.possible_emails %}
                                        <li>{{ email }}</li>
                                    {% endfor %}
                                </ul>
                            {% endif %}
                        {% endif %}
                    </div>
                {% endfor %}
            {% else %}
                <div class="no-leads">
                    <p>{{ language == 'es' and 'No se han recopilado leads todavía.' or 'No leads have been scraped yet.' }}</p>
                </div>
            {% endif %}
        </div>

        <div class="actions">
            <a href="/">{{ language == 'es' and 'Volver al Inicio' or 'Back to Home' }}</a>
            <a href="/export-leads" target="_blank">{{ language == 'es' and 'Exportar Leads (JSON)' or 'Export Leads (JSON)' }}</a>
            <a href="/clear-leads" onclick="return confirm('{{ language == 'es' and '¿Estás seguro de que quieres borrar todos los leads?' or 'Are you sure you want to clear all leads?' }}')">{{ language == 'es' and 'Borrar Todos los Leads' or 'Clear All Leads' }}</a>
        </div>
    </div>

    <script>
        // Populate filters on page load
        document.addEventListener('DOMContentLoaded', function() {
            const leadCards = document.querySelectorAll('.lead-card');
            const countries = new Set();
            const sources = new Set();

            leadCards.forEach(card => {
                const country = card.getAttribute('data-country');
                const source = card.getAttribute('data-source');

                if (country) countries.add(country);
                if (source) sources.add(source);
            });

            // Add country options
            const countryFilter = document.getElementById('country-filter');
            countries.forEach(country => {
                const option = document.createElement('option');
                option.value = country;
                option.textContent = country;
                countryFilter.appendChild(option);
            });

            // Add source options
            const sourceFilter = document.getElementById('source-filter');
            sources.forEach(source => {
                const option = document.createElement('option');
                option.value = source;
                option.textContent = source;
                sourceFilter.appendChild(option);
            });
        });

        // Filter leads based on selected filters
        function filterLeads() {
            const countryFilter = document.getElementById('country-filter').value;
            const sourceFilter = document.getElementById('source-filter').value;
            const searchFilter = document.getElementById('search-filter').value.toLowerCase();

            const leadCards = document.querySelectorAll('.lead-card');

            leadCards.forEach(card => {
                const country = card.getAttribute('data-country');
                const source = card.getAttribute('data-source');
                const cardText = card.textContent.toLowerCase();

                const countryMatch = !countryFilter || country === countryFilter;
                const sourceMatch = !sourceFilter || source === sourceFilter;
                const searchMatch = !searchFilter || cardText.includes(searchFilter);

                if (countryMatch && sourceMatch && searchMatch) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        }
    </script>
</body>
</html>
''')

if __name__ == '__main__':
  app.run(host='0.0.0.0')
