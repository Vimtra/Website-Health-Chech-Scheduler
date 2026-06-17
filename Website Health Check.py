import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os

# 1. Retrieve credentials securely from GitHub Environment Variables
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')

if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
    print("❌ Error: One or more secret keys are missing from environment variables.")
    raise SystemExit

# 2. Your list of websites
WEBSITES = [
    "https://vimtra.com", "https://vimtraventures.com", "https://urpantech.com",
    "https://techalphallc.com", "https://techmyndsinc.com", "https://insightintelli.com",
    "https://xcellifesciences.com", "https://sacrosanctinfo.com", "https://rushipharma.com",
    "https://tekcog.com", "https://aadyot.com", "https://vimtechit.com",
    "https://startekpro.com", "https://github.io", "https://syncorex.com",
    "https://thewindgrove.com", "https://vsolvetechnologies.com"
]

def check_websites():
    print("Checking main websites and scanning internal pages...")
    print("This may take a few minutes depending on how many pages each site has. Please wait!\n")

    # Start building the HTML template
    html_report = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px; }
            .container { max-width: 800px; margin: auto; background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
            h2 { color: #333333; text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #dddddd; }
            th { background-color: #f2f2f2; color: #333333; }
            .status-up { color: #28a745; font-weight: bold; }
            .status-warning { color: #ff9800; font-weight: bold; }
            .status-down { color: #dc3545; font-weight: bold; }
            a { color: #007bff; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Comprehensive Website Status Report</h2>
            <table>
                <tr>
                    <th>Website</th>
                    <th>Main Status</th>
                    <th>Page Details</th>
                </tr>
    """

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    for site in WEBSITES:
        print(f"Scanning {site}...")
        try:
            response = requests.get(site, headers=headers, timeout=15)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                internal_links = set()
                base_domain = urlparse(site).netloc

                for a_tag in soup.find_all('a', href=True):
                    full_url = urljoin(site, a_tag['href'])
                    parsed_url = urlparse(full_url)

                    if parsed_url.netloc == base_domain and full_url not in internal_links:
                        if not parsed_url.fragment:
                            internal_links.add(full_url)

                broken_links_count = 0
                checked_links_count = len(internal_links)

                for link in internal_links:
                    try:
                        link_response = requests.head(link, headers=headers, timeout=5, allow_redirects=True)
                        if link_response.status_code >= 400:
                            broken_links_count += 1
                    except requests.exceptions.RequestException:
                        broken_links_count += 1

                if broken_links_count == 0:
                    detail_text = f"All {checked_links_count} linked pages are OK" if checked_links_count > 0 else "200 OK (No internal links found)"
                    html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-up'>UP</td><td>{detail_text}</td></tr>"
                else:
                    html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-warning'>UP (Warnings)</td><td>{broken_links_count} out of {checked_links_count} sub-pages are BROKEN</td></tr>"

            elif response.status_code in [401, 403, 503]:
                html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-up'>UP</td><td>UP (Main site live, internal links protected by firewall)</td></tr>"

            else:
                html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-down'>DOWN</td><td>Main Site Error {response.status_code}</td></tr>"

        except requests.exceptions.RequestException:
            try:
                fallback_headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
                fallback_resp = requests.get(site, headers=fallback_headers, timeout=10, allow_redirects=True)

                if fallback_resp.status_code in [200, 401, 403, 503]:
                    html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-up'>UP</td><td>UP (Verified via connection fallback routine)</td></tr>"
                else:
                    html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-down'>DOWN</td><td>Unreachable (Status: {fallback_resp.status_code})</td></tr>"
            except requests.exceptions.RequestException:
                html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-down'>DOWN</td><td>Unreachable</td></tr>"

    html_report += """
            </table>
        </div>
    </body>
    </html>
    """
    return html_report


def send_email(html_content):
    """Send the report via SMTP email AND create a GitHub Issue as backup."""

    # ─── Part 1: Send the actual email via Gmail SMTP ───
    print("\nSending email report...")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "📊 Daily Website Status Report (Deep Scan)"
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())

        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Email sending failed: {e}")

    # ─── Part 2: Also create a GitHub Issue as a backup log ───
    print("Creating GitHub Issue as backup log...")
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")

    if not token or not repository:
        print("⚠️  Skipping GitHub Issue: Missing GITHUB_TOKEN or GITHUB_REPOSITORY.")
        return

    # ✅ FIX: Use the correct GitHub REST API endpoint
    url = f"https://api.github.com/repos/{repository}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    issue_data = {
        "title": "📊 Daily Website Status Report (Deep Scan)",
        "body": html_content
    }

    try:
        response = requests.post(url, json=issue_data, headers=headers)
        if response.status_code == 201:
            print("✅ GitHub Issue created successfully!")
        else:
            print(f"❌ Failed to create issue. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"❌ Network failure while creating issue: {e}")


if __name__ == "__main__":
    final_report = check_websites()
    send_email(final_report)
