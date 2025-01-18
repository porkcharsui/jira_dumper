# Jira Dumper

![image](logo.webp)

"Listen up, fool! The Jira Dumper's here to scrape issues, slice 'em, dice 'em, and pack 'em into XML for ultimate archiving power. Don't mess with your data—preserve it like a champ!"

## Install / Requirements

### Prerequisites

- Python 3.8+
- [Poetry](https://python-poetry.org/) installed globally for dependency management

### Installation Steps

1. Clone this repository:

   ```shell
   git clone git@github.com:porkcharsui/jira_dumper.git
   cd jira_dumper
   ```

2. Create a `.env` file and set the required environment variables:

   ```shell
   # Example of a .env file
   JIRA_BASE_URL=https://your.jira.instance
   JIRA_DUMPER_OUTPUT_DIR=output
   ```

3. Install dependencies using Poetry:

   ```shell
   poetry install
   ```

4. Use Poetry to run the tools within this project:

   ```shell
   poetry run jira_fetch_issues
   poetry run jira_export_xml
   poetry run jira_export_xml_attachments
   ```

## Features

### Authentication

Jira Dumper uses [Playwright](https://github.com/microsoft/playwright) with the real Chrome browser to handle authentication. If the session is not authenticated, the tools will pause and allow the user to manually log in through the browser. Once the login is complete, the user must press the ENTER key in the terminal to continue.

This process captures the authentication state in a file (`auth_state.json`), which is shared across all Jira Dumper tools. Simply delete the file to force a re-authentication on the next run, ensuring a fresh session when needed.

### Data Handling

Jira Dumper is designed to preserve all issue data as structured XML data / attachments for long-term archival and further analysis. Unlike PDF exports, which flatten information into non-structured data, XML exports ensures data remains machine-readable and accessible for integration into other workflows or tools.

Attachments are saved with this pattern:

```
{JIRA_DUMPER_OUTPUT_DIR}/PROJECT_KEY/attachments/ISSUE_KEY/ID-{attachment_id}__{filename}
```

### Explanation of Variables

- `{JIRA_DUMPER_OUTPUT_DIR}`: The base directory where all output files are stored, as specified in the `.env` file.
- `{PROJECT_KEY}`: The key of the JIRA project associated with the issues (e.g., `INFRA`, `HR`).
- `{ISSUE_KEY}`: The unique key for the specific JIRA issue (e.g., `INFRA-123`).
- `{attachment_id}`: The unique ID of the attachment in JIRA, used to ensure filenames are unique.
- `{filename}`: The original filename of the attachment. This guarantees uniqueness, prevents overwrites, and maintains clear associations with the original data.

### Efficiency

The tool skips already downloaded attachments based on timestamps, reducing redundant downloads and saving time. It also dynamically adjusts query ranges to efficiently handle large datasets.

## Steps

### Step 1: Gather Issues

This script collects Jira issues for one or more projects within a specified date range and saves the results as CSV files.

#### Usage

```shell
$ poetry run jira_fetch_issues --help
Usage: jira_fetch_issues [OPTIONS]

  CLI to scrape JIRA issues for specific projects and date ranges.

Options:
  --project TEXT     Project key to scrape (e.g., INFRA). Use multiple
                     `--project` flags for multiple projects.  [required]
  --start-date TEXT  Start date for the range in YYYY-MM-DD format (default: 2
                     years ago).
  --end-date TEXT    End date for the range in YYYY-MM-DD format (default:
                     today).
  --base-url TEXT    Base URL of the JIRA instance.
  --help             Show this message and exit.```


#### Final Command For Multiple Projects

```shell
poetry run jira_fetch_issues \
    --start-date 1984-01-01 \
    --project AP --project INFRA --project IT --project HR --project USA
```

## Step 2: Export Issues

This script takes one or more CSV files generated in Step 1, loads each issue key, and exports the issue's XML content.

### Usage

```shell
$ poetry run jira_export_xml --help 
Usage: jira_export_xml [OPTIONS] [FILES]...

  Download issues from CSV files and save their XML exports.

  FILES are one or more paths to CSV files. Globs can be expanded by the shell
  (e.g., output/*.csv).

Options:
  --base-url TEXT  The base URL of the Jira instance (set via JIRA_BASE_URL in
                   .env file).
  --help           Show this message and exit.
```

#### Export a Single CSV

```shell
poetry run jira_export_xml output/INFRA.csv
```

#### Export Using Shell Glob for All CSVs

```shell
poetry run jira_export_xml output/*.csv
```

## Step 3: Export Attachments

### Usage

```shell
$ poetry run jira_export_xml_attachments --help 
Usage: jira_export_xml_attachments [OPTIONS] [FILE_PATTERNS]...

  Extract attachments from one or more Jira XML export files and optionally
  download them. For each file, a new directory named after the issue key will
  be created at the same path level as the input FILE.

  FILE_PATTERNS are the glob patterns for the XML files.

Options:
  --dry-run  Simulate the download and display the attachment details.
  --force    Force download of all files, regardless of existing timestamps.
  --help     Show this message and exit.
```

This script processes Jira XML files to extract attachments and organize them for archival or backup purposes.

Each attachment is:

1. Stored in a directory named after its issue key.
2. Located relative to the XML file being processed.
3. Preserves timestamp metadata to ensure archival accuracy and speed up downloads for existing files, reducing redundant downloads.
4. Saved with a filename that is always unique, using the format `ID-{attachment_id}__{filename}`.

### Example XML Issue Input and File Output Structure

Here is an example of a `output/USA/USA-1984.xml` file that serves as input:

```xml
<issue>
  <key>USA-1984</key>
  <summary>Example Issue Summary</summary>
  <attachments>
    <attachment id="18113" name="the-a-team.png" size="12995" author="Mr. T" created="Wed, 31 Oct 1984 14:38:48 -0700"/>
  </attachments>
</issue>
```

Attachments are downloaded into directories named after their issue keys, relative to the XML file's location (`output/USA/USA-1984.xml`). For example:

```
output/USA/attachments/USA-1984/ID-18113__the-a-team.png
```

### Download Attachments Examples

#### Single Project Glob

```shell
poetry run jira_export_xml_attachments "output/INFRA/*.xml"
```

#### All Projects Deep Glob

```shell
poetry run jira_export_xml_attachments "output/**/*.xml"
```

NOTE: Use the `--force` flag to re-download all files regardless of existing timestamps.


## Compatibility Note

This tool has been only been thoroughly tested with Jira OnPrem version v8.3.4. If you experience any issues on different versions of Jira, please report them as an issue.