import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipar
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os

# 1. Retrieve credentials securely from Colab Secrets
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')
if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
    print("❌ Error: One or more secret keys are missing from environment variables.")
    raise SystemExit

# 2. Your list of websites
WEBSITES = [
    "https://www.vimtra.com/", "https://vimtraventures.com/", "https://www.urpantech.com/",
    "https://techalphallc.com/", "https://techmyndsinc.com/", "https://www.insightintelli.com/",
    "https://xcellifesciences.com/", "https://www.sacrosanctinfo.com/", "https://www.rushipharma.com/",
    "https://www.tekcog.com", "https://www.aadyot.com/", "https://www.vimtechit.com/",
    "https://startekpro.com/", "https://thebellabeau.github.io/bella-beau/", "https://syncorex.com/",
    "https://thewindgrove.com/", "https://vsolvetechnologies.com/"
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
            .status-warning { color: #ff9800; font-weight: bold; } /* Orange for partial outages */
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
            # Step A: Check the main homepage first
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code == 200:
                # Step B: If the homepage is up, pull all its internal links
                soup = BeautifulSoup(response.text, 'html.parser')
                internal_links = set()
                base_domain = urlparse(site).netloc

                # Find all <a href="..."> tags
                for a_tag in soup.find_all('a', href=True):
                    full_url = urljoin(site, a_tag['href'])
                    parsed_url = urlparse(full_url)

                    # Only keep links that belong to the SAME website (ignore Facebook/LinkedIn/etc.)
                    # Also ignore simple anchor links (like #contact) that just scroll down the page
                    if parsed_url.netloc == base_domain and full_url not in internal_links:
                        if not parsed_url.fragment:
                            internal_links.add(full_url)

                # Step C: Check all the found internal links
                broken_links_count = 0
                checked_links_count = len(internal_links)

                for link in internal_links:
                    try:
                        # We use .head() instead of .get() here because it's much faster
                        # just to check the status code without downloading the whole page text again
                        link_response = requests.head(link, headers=headers, timeout=5, allow_redirects=True)
                        if link_response.status_code >= 400:
                            broken_links_count += 1
                    except requests.exceptions.RequestException:
                        broken_links_count += 1

                # Step D: Format the HTML row based on what we found behind the scenes
                if broken_links_count == 0:
                    detail_text = f"All {checked_links_count} linked pages are OK" if checked_links_count > 0 else "200 OK (No internal links found)"
                    html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-up'>UP</td><td>{detail_text}</td></tr>"
                else:
                    html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-warning'>UP (Warnings)</td><td>{broken_links_count} out of {checked_links_count} sub-pages are BROKEN</td></tr>"

            else:
                # If the main site fails, don't bother checking sub-pages
                html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-down'>DOWN</td><td>Main Site Error {response.status_code}</td></tr>"

        except requests.exceptions.RequestException as e:
            html_report += f"<tr><td><a href='{site}'>{site}</a></td><td class='status-down'>DOWN</td><td>Unreachable</td></tr>"

    # Close the HTML tags
    html_report += """
            </table>
        </div>
    </body>
    </html>
    """
    return html_report

def send_email(html_content):
    print("\nDrafting HTML email...")
    msg = MIMEMultipart("alternative")
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = "📊 Daily Website Status Report (Deep Scan)"

    msg.attach(MIMEText(html_content, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, text)
        server.quit()
        print("✅ Success! The comprehensive report has been emailed to you.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

# Run the functions
if __name__ == "__main__":
    final_report = check_websites()
    send_email(final_report)
