#!/usr/bin/env python3
import os
import csv
from pathlib import Path
from dotenv import load_dotenv
import click
from playwright.sync_api import sync_playwright

# Load environment variables from .env file
load_dotenv()

# Path to store/reuse the authenticated session state
STORAGE_STATE_PATH = os.path.join(os.path.dirname(__file__), "auth_state.json")

# Check and configure output directory from environment variable
OUTPUT_DIR_ENV = os.getenv("JIRA_DUMPER_OUTPUT_DIR")
if not OUTPUT_DIR_ENV:
    raise RuntimeError("Environment variable JIRA_DUMPER_OUTPUT_DIR is not defined.")

OUTPUT_DIR = Path(OUTPUT_DIR_ENV)
if not OUTPUT_DIR.exists():
    print(f"🔨 Creating output directory: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Default Base URL
DEFAULT_BASE_URL = os.getenv("JIRA_BASE_URL")

# Selector for XML link in the export dropdown
XML_LINK_SELECTOR = 'a[href*="jira.issueviews:issue-xml"]'

def load_csv_files(file_paths):
    """Load issue keys from the provided file paths."""
    issues = []
    for file_path in file_paths:
        with open(file_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                issues.append((row["key"], file_path))  # Include the file path for project extraction
    return issues


def save_xml_file(project, key, xml_content):
    """Save the XML content to a file."""
    project_dir = OUTPUT_DIR / project
    project_dir.mkdir(parents=True, exist_ok=True)
    file_path = project_dir / f"{key}.xml"

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(xml_content)
    print(f"📁 Saved XML for {key} to {file_path}")


def process_issues(base_url, issues, page):
    """Process issues to download and save XML."""
    for key, csv_file in issues:
        # Extract project name from the CSV file name
        project = Path(csv_file).stem.upper()

        # Navigate to the issue page
        issue_url = f"{base_url}/browse/{key}"
        print(f"🌐 Navigating to {issue_url}...")
        response = page.goto(issue_url)

        # Check if the page loaded successfully
        if response.status != 200:
            print(f"❌ Failed to load {key} (HTTP {response.status}). Skipping...")
            continue

        # Find the XML link directly
        xml_link_element = page.query_selector(XML_LINK_SELECTOR)
        if not xml_link_element:
            print(f"❌ XML export link not found for {key}. Skipping...")
            continue

        xml_url = xml_link_element.get_attribute("href")
        if not xml_url:
            print(f"❌ Failed to get XML export URL for {key}. Skipping...")
            continue

        # Download the XML
        print(f"📥 Downloading XML for {key}...")
        xml_response = page.goto(base_url + xml_url)
        if xml_response.status != 200:
            print(f"❌ Failed to download XML for {key} (HTTP {xml_response.status}). Skipping...")
            continue

        # Save the XML content
        save_xml_file(project, key, xml_response.text())


@click.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--base-url",
    default=DEFAULT_BASE_URL,
    help="The base URL of the Jira instance (set via JIRA_BASE_URL in .env file).",
)
def main(files, base_url):
    """
    Download issues from CSV files and save their XML exports.

    FILES are one or more paths to CSV files. Globs can be expanded by the shell (e.g., output/*.csv).
    """
    if not base_url:
        raise click.UsageError("The Jira base URL must be provided via --base-url or the JIRA_BASE_URL environment variable.")

    # Load issues from the provided file paths
    issues = load_csv_files(files)

    if not issues:
        print("❌ No issues found in the provided CSV files. Exiting...")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Use a single browser instance
        context = None
        try:
            # Check if auth state exists
            if os.path.exists(STORAGE_STATE_PATH):
                print(f"🔐 Using existing login state from: {STORAGE_STATE_PATH}")
                context = browser.new_context(storage_state=STORAGE_STATE_PATH)
            else:
                print("🟡 No stored login state found. Starting manual login flow...")
                context = browser.new_context()

            page = context.new_page()

            # If no auth state, allow manual login and save state
            if not os.path.exists(STORAGE_STATE_PATH):
                page.goto(f"{base_url}/login")
                print(
                    "\nPlease log in manually in the opened browser window."
                    " Once logged in, press ENTER here to continue.\n"
                )
                input("Press ENTER to continue...")  # Wait for user input
                context.storage_state(path=STORAGE_STATE_PATH)
                print(f"🟢 Saved authenticated state to: {STORAGE_STATE_PATH}")

            # Process issues
            process_issues(base_url, issues, page)

        except Exception as e:
            print(f"❌ Error during execution: {e}")
        finally:
            if context:
                context.close()
            browser.close()


if __name__ == "__main__":
    main()
