#!/usr/bin/env python3
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from tqdm import tqdm
import json
import click
from time import strptime, mktime
from playwright.sync_api import sync_playwright
import glob

# Load base URL from .env
from dotenv import load_dotenv
load_dotenv()

BASE_URL = os.getenv("JIRA_BASE_URL")
SCRIPT_DIR = Path(__file__).parent
AUTH_STATE_PATH = SCRIPT_DIR / "auth_state.json"

@click.command()
@click.argument("file_patterns", nargs=-1)
@click.option("--dry-run", is_flag=True, help="Simulate the download and display the attachment details.")
@click.option("--force", is_flag=True, help="Force download of all files, regardless of existing timestamps.")
def main(file_patterns, dry_run, force):
    """
    Extract attachments from one or more Jira XML export files and optionally download them. For each file, a new directory named after the issue key will be created at the same path level as the input FILE.

    FILE_PATTERNS are the glob patterns for the XML files.
    """
    if not BASE_URL:
        raise click.UsageError("JIRA_BASE_URL must be set in the .env file.")

    # Resolve files from glob patterns
    files = []
    for pattern in file_patterns:
        files.extend(glob.glob(pattern, recursive=True))

    if not files:
        print("❌ No files found matching the provided patterns.")
        return

    total_estimated_size = 0
    total_downloaded_files = 0
    total_skipped_files = 0
    total_downloaded_size = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        # Load auth state if available
        if AUTH_STATE_PATH.exists():
            with open(AUTH_STATE_PATH, "r") as f:
                storage_state = json.load(f)
            context.add_cookies(storage_state.get("cookies", []))

        page = context.new_page()

        for file in files:
            xml_path = Path(file)
            if not xml_path.is_file():
                print(f"❌ File not found: {file}")
                continue

            try:
                # Parse the XML file
                tree = ET.parse(xml_path)
                root = tree.getroot()

                # Extract issue key
                issue_key = root.find(".//key").text.strip()
                if not issue_key:
                    print("❌ Issue key not found in XML.")
                    continue

                print(f"🔑 Found issue key: {issue_key}")

                # Find all attachments
                attachments = root.findall(".//attachments/attachment")
                if not attachments:
                    print("ℹ️ No attachments found in the XML file.")
                    continue

                downloads = []
                logs = []

                # Queue downloads
                for attachment in attachments:
                    name = attachment.attrib.get("name")
                    attachment_id = attachment.attrib.get("id")
                    size = int(attachment.attrib.get("size", 0))
                    created = attachment.attrib.get("created")

                    total_estimated_size += size

                    if not name or not attachment_id or not created:
                        logs.append("❌ Malformed attachment element. Skipping...")
                        continue

                    # Construct download URL with URL encoding for the file name
                    encoded_name = quote(name)
                    download_url = f"{BASE_URL}/secure/attachment/{attachment_id}/{encoded_name}"

                    logs.append(f"📎 Queued attachment: {name}")
                    logs.append(f"   ↪️ URL: {download_url}")
                    logs.append(f"   ↪️ Size: {size / 1024:.2f} KB")

                    if not dry_run:
                        file_path = xml_path.parent / "attachments" / issue_key / f"ID-{attachment_id}__{name}"
                        downloads.append((download_url, file_path, name, created, size))

                # Print queued logs
                for log in logs:
                    print(log)

                # Show progress bar before starting downloads
                if not dry_run and downloads:
                    with tqdm(total=len(downloads), unit="file", desc=f"Downloading attachments for {issue_key}") as pbar:
                        # Prepare output directory
                        output_dir = xml_path.parent / "attachments" / issue_key
                        try:
                            output_dir.mkdir(parents=True, exist_ok=True)
                        except OSError as e:
                            print(f"❌ Failed to create directory {output_dir}: {e}")
                            continue

                        # Download attachments
                        for download_url, file_path, name, created, size in downloads:
                            try:
                                if file_path.exists() and not force:
                                    # Check existing file's timestamp
                                    existing_mtime = file_path.stat().st_mtime
                                    expected_mtime = mktime(strptime(created, "%a, %d %b %Y %H:%M:%S %z"))

                                    if abs(existing_mtime - expected_mtime) < 1:
                                        print(f"   ↩️ Skipped (Timestamp match): {file_path}")
                                        total_skipped_files += 1
                                        pbar.update(1)
                                        continue

                                response = page.request.get(download_url)
                                if response.status != 200:
                                    print(f"❌ Authentication or network error: Received HTTP {response.status} for {download_url}")
                                    exit(1)

                                with open(file_path, "wb") as f:
                                    f.write(response.body())

                                # Set the created timestamp on the file
                                file_mtime = mktime(strptime(created, "%a, %d %b %Y %H:%M:%S %z"))
                                os.utime(file_path, (file_mtime, file_mtime))

                                print(f"   ✅ Downloaded: {file_path}")
                                total_downloaded_files += 1
                                total_downloaded_size += size
                            except Exception as e:
                                print(f"   ❌ Failed to download {name}: {e}")
                                print("Stopping further downloads due to error.")
                                break
                            finally:
                                pbar.update(1)

            except ET.ParseError as e:
                print(f"❌ Failed to parse XML file: {e}")
            except Exception as e:
                print(f"❌ Unexpected error: {e}")

        context.close()
        browser.close()

    # Final summary
    if dry_run:
        print(f"💾 Total disk space required: {total_estimated_size / (1024 * 1024):.2f} MB")
        print(f"📎 Total number of attachments found: {len(files)}")
    else:
        print("\nSummary:")
        print(f"✅ Total files downloaded: {total_downloaded_files}")
        print(f"📦 Total downloaded size (this run): {total_downloaded_size / (1024 * 1024):.2f} MB")
        print(f"↩️ Total files skipped: {total_skipped_files}")

if __name__ == "__main__":
    main()
