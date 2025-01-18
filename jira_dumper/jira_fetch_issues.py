#!/usr/bin/env python3
import os
import csv
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import click
from playwright.sync_api import sync_playwright

# Load environment variables from .env file
load_dotenv()

STORAGE_STATE_PATH = os.path.join(os.path.dirname(__file__), "auth_state.json")

# Check and configure output directory from environment variable
OUTPUT_DIR_ENV = os.getenv("JIRA_DUMPER_OUTPUT_DIR")
if not OUTPUT_DIR_ENV:
    raise RuntimeError("Environment variable JIRA_DUMPER_OUTPUT_DIR is not defined.")

OUTPUT_DIR = Path(OUTPUT_DIR_ENV)
if not OUTPUT_DIR.exists():
    print(f"🔨 Creating output directory: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BASE_URL = os.getenv("JIRA_BASE_URL")
RESULTS_COUNT_SELECTOR = "span.results-count-total.results-count-link"
RESULT_THRESHOLD = 500  # Maximum allowable results before splitting the date range
PAGE_SIZE = 50  # Default Jira page size

def scrape_project(project, start_date, end_date, base_url, page):
    """Scrape issues for a specific project within a date range."""
    output_file = OUTPUT_DIR / f"{project}.csv"
    issue_data = []

    def get_results_count():
        """Extract total results count from the page."""
        count_element = page.query_selector(RESULTS_COUNT_SELECTOR)
        return int(count_element.text_content()) if count_element else 0

    current_start = start_date

    while current_start < end_date:
        current_end = current_start + timedelta(days=180)  # Initial range: 6 months

        # Dynamically adjust date range until the results are within the threshold
        while True:
            jql = (
                f'project={project} AND created >= "{current_start.strftime("%Y-%m-%d")}" '
                f'AND created < "{current_end.strftime("%Y-%m-%d")}" ORDER BY created DESC'
            )
            print(f"🚀 Processing JQL: {jql}")
            page.goto(f"{base_url}/issues/?jql={jql}")

            results_count = get_results_count()
            if results_count == 0:
                print(f"❌ No results found for JQL: {jql}")
                break
            elif results_count > RESULT_THRESHOLD:
                print(f"⚠️ Results count ({results_count}) exceeds threshold. Reducing date range.")
                # Halve the range and retry
                current_end = current_start + (current_end - current_start) / 2
            else:
                print(f"✅ Results count: {results_count}. Proceeding with pagination.")
                break  # Exit the loop when results are within threshold

        # Paginate through the results within the adjusted range
        start_index = 0
        while True:
            paginated_url = f"{base_url}/issues/?jql={jql}&startIndex={start_index}"
            print(f"🌐 Fetching: {paginated_url}")
            page.goto(paginated_url)

            # Check for issue rows
            ROW_SELECTOR = "tr.issuerow"
            issue_rows = page.query_selector_all(ROW_SELECTOR)

            if not issue_rows:
                print("🏁 No more issues found or end of pagination.")
                break

            # Collect issue data
            for row in issue_rows:
                id_attr = row.get_attribute("rel")
                key = row.get_attribute("data-issuekey")
                link_element = row.query_selector("td.issuekey a.issue-link")
                summary_element = row.query_selector("td.summary a.issue-link")

                href = link_element.get_attribute("href") if link_element else None
                summary = summary_element.text_content() if summary_element else None
                if id_attr and key and href:
                    url = base_url + href if href.startswith("/") else href
                    issue_data.append((int(id_attr), key, summary.strip() if summary else "", url))

            print(f"✅ Collected {len(issue_rows)} issue rows. Total so far: {len(issue_data)}")

            # Check for next page
            start_index += PAGE_SIZE
            nav_next_selector = "a.nav-next"
            nav_next = page.query_selector(nav_next_selector)

            if not nav_next:
                print("🏁 Reached the last page for this query.")
                break

        # Move to the next date range chunk
        current_start = current_end

    # Write results to CSV
    issue_data.sort(key=lambda x: x[0])
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "key", "summary", "url"])
        writer.writerows(issue_data)
    print(f"📁 Saved {len(issue_data)} issues to {output_file}")

@click.command()
@click.option("--project", "projects", multiple=True, required=True, help="Project key to scrape (e.g., INFRA). Use multiple `--project` flags for multiple projects.")
@click.option("--start-date", default=(datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d"),
              help="Start date for the range in YYYY-MM-DD format (default: 2 years ago).")
@click.option("--end-date", default=datetime.now().strftime("%Y-%m-%d"),
              help="End date for the range in YYYY-MM-DD format (default: today).")
@click.option("--base-url", default=DEFAULT_BASE_URL, help="Base URL of the JIRA instance.")
def main(projects, start_date, end_date, base_url):
    """CLI to scrape Jira issues for specific projects and date ranges."""
    if not base_url:
        raise click.UsageError("The Jira base URL must be provided via --base-url or the JIRA_BASE_URL environment variable.")

    start_date = datetime.strptime(start_date, "%Y-%m-%d")
    end_date = datetime.strptime(end_date, "%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=STORAGE_STATE_PATH) if os.path.exists(STORAGE_STATE_PATH) else browser.new_context()
        page = context.new_page()

        if not os.path.exists(STORAGE_STATE_PATH):
            page.goto(f"{base_url}/login")
            input("Please log in and press ENTER to continue...")
            context.storage_state(path=STORAGE_STATE_PATH)

        for project in projects:
            scrape_project(project, start_date, end_date, base_url, page)

        browser.close()

if __name__ == "__main__":
    main()
