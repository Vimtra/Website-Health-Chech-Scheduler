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

# Extensions and patterns to skip when scanning internal links
SKIP_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
                   '.mp4', '.mp3', '.zip', '.doc', '.docx', '.xls', '.xlsx',
                   '.ppt', '.pptx', '.css', '.js', '.ico', '.woff', '.woff2',
                   '.ttf', '.eot')

SKIP_PREFIXES = ('mailto:', 'tel:', 'javascript:', 'data:', 'sms:', 'whatsapp:')

# Domains to skip sub-page scanning (e.g. GoDaddy Website Builder blocks bots on sub-pages)
# The homepage is still checked — only internal link scanning is skipped.
SKIP_SUBPAGE_SCAN = [
    "vimtechit.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def is_server_alive(status_code):
    """Any HTTP response means the server is alive and responding.
    Even 403/503 means a firewall or WAF is active — the site is UP."""
    return status_code < 500 or status_code == 503


def is_page_ok(status_code):
    """For sub-page checks: 2xx and 3xx are fine."""
    return status_code < 400


def should_skip_url(url):
    """Skip non-HTML resources and non-http links."""
    lower = url.lower()
    if any(lower.startswith(p) for p in SKIP_PREFIXES):
        return True
    path = urlparse(lower).path
    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return True
    return False


def check_link(url):
    """Check a single internal link. Try HEAD first; if the server rejects it
    (405, 403, or other error), retry with GET before marking it broken."""
    try:
        resp = requests.head(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if is_page_ok(resp.status_code):
            return True
        # Many servers reject HEAD — fall back to GET before calling it broken
        if resp.status_code in (403, 405, 406, 501):
            resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            return is_page_ok(resp.status_code)
        return False
    except requests.exceptions.RequestException:
        return False


def check_site(site):
    """Check a single website: homepage first, then its internal links.
    Returns a tuple: (status_class, status_label, detail_text)
    """
    # ── Step A: Check the homepage ──
    try:
        response = requests.get(site, headers=HEADERS, timeout=15, allow_redirects=True)
    except requests.exceptions.RequestException:
        # First attempt failed — retry with a different User-Agent
        try:
            fallback_headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                              "Version/17.0 Safari/605.1.15",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
            response = requests.get(site, headers=fallback_headers, timeout=10, allow_redirects=True)
        except requests.exceptions.RequestException:
            return ("status-down", "DOWN", "Unreachable (no response from server)")

    # If we got ANY HTTP response, the server is alive
    if not is_server_alive(response.status_code):
        return ("status-down", "DOWN", f"Server Error {response.status_code}")

    # If the server blocked our bot request (4xx) but is clearly alive and responding.
    # A dead server can't return an HTTP status code — any response = server is running.
    if response.status_code in (401, 403, 405, 406, 415, 429, 503):
        return ("status-up", "UP", "Main site live (protected by firewall/WAF — normal)")

    # Catch any other 4xx we didn't list above — still means server is alive
    if response.status_code >= 400:
        return ("status-up", "UP", f"Main site live (server returned {response.status_code}, likely bot protection)")

    # Skip sub-page scanning for whitelisted domains (e.g. GoDaddy blocks bots)
    base_domain = urlparse(site).netloc
    if any(domain in base_domain for domain in SKIP_SUBPAGE_SCAN):
        return ("status-up", "UP", "200 OK (Sub-page scan skipped — hosting platform blocks bots)")

    soup = BeautifulSoup(response.text, 'html.parser')
    internal_links = set()
    base_domain = urlparse(site).netloc

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        if should_skip_url(href):
            continue
        full_url = urljoin(site, href)
        parsed = urlparse(full_url)
        # Only same-domain, no fragments, no query-heavy duplicates
        if parsed.netloc == base_domain and not parsed.fragment:
            # Normalize: strip trailing slash for dedup
            clean = full_url.rstrip('/')
            if clean != site.rstrip('/'):  # skip homepage itself
                internal_links.add(clean)

    if not internal_links:
        return ("status-up", "UP", "200 OK (No internal links found)")

    # ── Step C: Check each internal link ──
    broken = []
    for link in internal_links:
        if not check_link(link):
            broken.append(link)

    total = len(internal_links)

    if not broken:
        return ("status-up", "UP", f"All {total} linked pages are OK")
    else:
        broken_list = "<br>".join(f"&nbsp;&nbsp;• {b}" for b in broken[:5])
        if len(broken) > 5:
            broken_list += f"<br>&nbsp;&nbsp;... and {len(broken) - 5} more"
        return (
            "status-warning",
            "UP (Warnings)",
            f"{len(broken)} of {total} sub-pages returned errors:<br>{broken_list}"
        )


def check_websites():
    print("Checking main websites and scanning internal pages...")
    print("This may take a few minutes depending on how many pages each site has. Please wait!\n")

    html_report = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px; }
            .container { max-width: 850px; margin: auto; background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
            h2 { color: #333333; text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #dddddd; }
            th { background-color: #f2f2f2; color: #333333; }
            .status-up { color: #28a745; font-weight: bold; }
            .status-warning { color: #ff9800; font-weight: bold; }
            .status-down { color: #dc3545; font-weight: bold; }
            a { color: #007bff; text-decoration: none; }
            a:hover { text-decoration: underline; }
            .small { font-size: 12px; color: #888; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>📊 Comprehensive Website Status Report</h2>
            <table>
                <tr>
                    <th>Website</th>
                    <th>Main Status</th>
                    <th>Page Details</th>
                </tr>
    """

    for site in WEBSITES:
        print(f"Scanning {site}...")
        css_class, label, detail = check_site(site)
        html_report += (
            f"<tr>"
            f"<td><a href='{site}'>{site}</a></td>"
            f"<td class='{css_class}'>{label}</td>"
            f"<td>{detail}</td>"
            f"</tr>"
        )

    html_report += """
            </table>
            <p class="small" style="text-align:center; margin-top:16px;">
                Note: "Protected by firewall" means the site is live but blocks automated scanners — this is normal and healthy.
            </p>
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

    url = f"https://api.github.com/repos/{repository}/issues"
    api_headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    issue_data = {
        "title": "📊 Daily Website Status Report (Deep Scan)",
        "body": html_content
    }

    try:
        response = requests.post(url, json=issue_data, headers=api_headers)
        if response.status_code == 201:
            print("✅ GitHub Issue created successfully!")
        else:
            print(f"❌ Failed to create issue. Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"❌ Network failure while creating issue: {e}")


if __name__ == "__main__":
    final_report = check_websites()
    send_email(final_report)
