import requests
import json
import time
import threading
import logging
import os
from airtable import Airtable
from datetime import datetime, timezone
import sys

# Set up logging
logging.basicConfig(filename='recipe_logs.log', level=logging.INFO, format='%(asctime)s %(message)s')

class Automation:
    TRIGGERS = {
        "airtable_record_updated": {
            "description": "Triggered when a record is created or updated in Airtable",
        },
        "find_record": {
            "description": "Find a record based on specified text in a field",
        },
    }

    ACTIONS = {
        "send_webhook": {
            "description": "Sends a webhook to a specified URL",
        },
    }
    def __init__(self, trigger=None, action=None, webhook_url=None, base_key=None, table_name=None, api_key=None, field_name=None, text_to_find=None, name=None):
        self.trigger = trigger
        self.action = action
        self.webhook_url = webhook_url
        self.base_key = base_key
        self.table_name = table_name
        self.api_key = api_key
        self.field_name = field_name
        self.text_to_find = text_to_find
        self.name = name
        self.last_execution_time = None  # New attribute to store the last execution time
    

def send_webhook(url, data, recipe_name):
    response = requests.post(url, json=data)
    logging.info(f"Webhook sent to {url} with data: {data} for recipe {recipe_name}")
    return response.status_code

def fetch_records(base_key, table_name, api_key):
    airtable = Airtable(base_key, table_name, api_key=api_key)
    print("Fetching records from Airtable...")
    records = airtable.get_all()
    print(f"Fetched {len(records)} records from Airtable")
    logging.info(f"Fetched {len(records)} records from Airtable")
    return records

def save_recipe(recipe, filename):
    with open(filename, 'w') as file:
        json.dump(vars(recipe), file)
    logging.info(f"Recipe saved to {filename}")

def load_recipe(filename):
    with open(filename, 'r') as file:
        recipe_data = json.load(file)
        return Automation(**recipe_data)

def create_recipe():
    print("Creating a new recipe...")

    print("Step 1: Choose a Trigger")
    print("-----------------------")
    trigger = select_option(Automation.TRIGGERS)

    print("\nStep 2: Choose an Action")
    print("------------------------")
    action = select_option(Automation.ACTIONS)

    webhook_url = None
    if action == "send_webhook":
        webhook_url = input("\nStep 3: Enter the webhook URL: ")
    base_key = input("Step 4: Enter the Airtable base key: ")
    table_name = input("Step 5: Enter the Airtable table name: ")
    api_key = input("Step 6: Enter the Airtable API key: ")

    field_name = None
    text_to_find = None
    if trigger == "find_record":
        field_name = input("Step 7: Enter the field name to search in: ")
        text_to_find = input("Step 8: Enter the text to find in the field: ")

    name = input("Step 9: Enter a name for this recipe: ")

    return Automation(trigger, action, webhook_url, base_key, table_name, api_key, field_name, text_to_find, name)

def select_option(options):
    numbered_options = list(enumerate(options.items(), start=1))
    for number, (key, value) in numbered_options:
        print(f"{number}: {value['description']}")

    selected_option_key = None
    while selected_option_key is None:
        try:
            selection = int(input("Choose an option by entering the corresponding number: "))
            if 1 <= selection <= len(numbered_options):
                selected_option_key = numbered_options[selection - 1][1][0]
            else:
                print("Invalid choice. Please choose a valid option.")
        except ValueError:
            print("Please enter a valid number.")

    return selected_option_key


def execute_recipe(recipe):
    recipe.is_running = True
    logging.info(f"Monitoring Airtable for changes for recipe {recipe.name} ...")
    airtable = Airtable(recipe.base_key, recipe.table_name, api_key=recipe.api_key)

    start_time = datetime.utcnow().replace(tzinfo=None)  # Save the current time when the recipe starts
    last_checked_time = recipe.last_execution_time or start_time  # Use last_execution_time or start_time as initial value
    processed_records = set()

    while True:
        print("Fetching records from Airtable...")
        records = airtable.get_all()
        print(f"Fetched {len(records)} records from Airtable")

        for record in records:
            record_id = record['id']
            print("Processing record:", record_id)
            record_time_str = record['fields'].get('Last Modified')

            if record_id in processed_records:
                print("Record already processed. Skipping...")
                continue  # Skip this record if it has already been processed

            if record_time_str:
                record_time = datetime.fromisoformat(record_time_str).replace(tzinfo=None)  # make offset-naive
                print("Record Time:", record_time)

                if recipe.trigger == "airtable_record_updated" and record_time > last_checked_time:
                    logging.info(f"{recipe.name}: Detected updated record {record_id}")
                    send_webhook(recipe.webhook_url, {"record": record}, recipe.name)

                elif recipe.trigger == "find_record" and recipe.field_name in record['fields']:
                    field_value = record['fields'][recipe.field_name]
                    if isinstance(field_value, str) and recipe.text_to_find in field_value:
                        logging.info(f"{recipe.name}: Detected record {record_id} with text '{recipe.text_to_find}' in field '{recipe.field_name}'")
                        send_webhook(recipe.webhook_url, {"record": record}, recipe.name)

            processed_records.add(record_id)

        recipe.last_execution_time = last_checked_time  # Update the last execution time in the recipe
        if not recipe.is_running:  # Check if the recipe is stopped
            break  # If it's stopped, break out of the while loop
        time.sleep(10)  # Wait for 10 seconds before checking again

    recipe.is_running = False  # Ensure the recipe is marked as stopped after the loop ends

class RecipeManager:
    def __init__(self):
        self.recipes = []
        self.threads = []
        self.load_all_recipes()

    def add_recipe(self, recipe):
        recipe.is_running = False  # Set is_running to False by default
        recipe.is_thread_running = False  # Set is_thread_running to False by default
        self.recipes.append(recipe)
        thread = threading.Thread(target=execute_recipe, args=(recipe,))
        self.threads.append(thread)

    def start_all(self):
        if all(recipe.is_running for recipe in self.recipes):
            logging.info("All recipes are already running")
        else:
            for thread, recipe in zip(self.threads, self.recipes):
                if recipe.is_running:
                    logging.info(f"{recipe.name}: Recipe {recipe.webhook_url} is already running")
                else:
                    thread.start()
                    recipe.is_running = True
                    recipe.is_thread_running = True  # Mark the thread as running
                    logging.info(f"{recipe.name}: Recipe {recipe.webhook_url} started")


    def log_status(self):
        for recipe in self.recipes:
            status = "running" if recipe.is_thread_running else "stopped"  # Use is_thread_running instead of is_running
            print(f"Recipe {recipe.name}: {recipe.webhook_url} is {status}")
            logging.info(f"Recipe {recipe.name}: {recipe.webhook_url} is {status}")




    def load_all_recipes(self):
        for filename in os.listdir():
            if filename.endswith('.json'):
                recipe = load_recipe(filename)
                self.add_recipe(recipe)
        logging.info(f"Loaded {len(self.recipes)} recipes")

    def print_logs(self):
        with open('recipe_logs.log', 'r') as file:
            logs = file.read()
            print(logs)

def main_menu():
    print("Available commands:")
    print("  create - Create a new recipe")
    print("  start  - Start all recipes")
    print("  status - View status of all recipes")
    print("  logs   - View the logs")
    print("  exit   - Exit the application")

def main():
    manager = RecipeManager()
    main_menu()
    while True:
        action = input("Enter a command: ")
        if action == 'create':
            user_recipe = create_recipe()
            filename = user_recipe.name + ".json"
            save_recipe(user_recipe, filename)
            logging.info(f"Recipe saved as {filename}")
            manager.add_recipe(user_recipe)
            print(f"Recipe '{user_recipe.name}' created.")
        elif action == 'start':
            manager.start_all()
            logging.info("All recipes started")
        elif action == 'status':
            manager.log_status()
        elif action == 'logs':
            manager.print_logs()
        elif action == 'exit':
            sys.exit(0)
        else:
            print("Unknown command. Please try again.")
            main_menu()

if __name__ == "__main__":
    main()
