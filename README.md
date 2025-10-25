# Instagram Automation Suite

A collection of Python scripts using Playwright to automate Instagram follower scraping and follow/unfollow workflows.

## ⚠️ Important Disclaimer

**Use at your own risk.** These scripts automate interactions with Instagram, which may violate Instagram's Terms of Service. Using automation tools can result in:
- Account suspension or permanent ban
- Rate limiting or IP blocking
- Loss of account access

This project is for educational purposes only. The authors are not responsible for any consequences resulting from the use of these scripts.

## 📋 Features

- **Follower Scraping**: Extract follower lists from any public Instagram profile
- **Automated Follow/Unfollow**: Follow users from a list and automatically unfollow them when they follow you back
- **Session Persistence**: Save login state to avoid repeated authentication
- **Rate Limiting**: Built-in delays and batching to mimic human behavior
- **Detailed Logging**: Track all actions with timestamped JSON logs

## 🛠️ Prerequisites

- Python 3.7+
- Playwright
- An Instagram account (obviously)

## 📦 Installation

1. Clone this repository:
```bash
git clone <your-repo-url>
cd instagram-automation
```

2. Install required packages:
```bash
pip install playwright
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

## 📂 Scripts Overview

### 1. `cookies_collector.py`
Legacy scraper for collecting Instagram followers. Uses synchronous Playwright API.

**Key Features:**
- Manual login with session state saving
- Scrollable modal extraction
- Configurable max followers limit

**Usage:**
```bash
# First run: login and save session
python cookies_collector.py  # Set DO_LOGIN=True in script

# Subsequent runs: use saved session
python cookies_collector.py  # Set DO_LOGIN=False in script
```

### 2. `instagram_scraper.py`
Improved, async follower scraper with better error handling and multiple output formats.

**Key Features:**
- Command-line argument support
- Exports to both JSON and CSV
- Multiple selector strategies for robustness
- Detailed display names and profile URLs

**Usage:**
```bash
# Scrape followers from a profile
python instagram_scraper.py --username target_username

# Custom output files and max followers
python instagram_scraper.py \
  --username target_username \
  --out-json my_followers.json \
  --out-csv my_followers.csv \
  --max 500

# Use custom session state file
python instagram_scraper.py \
  --username target_username \
  --state my_state.json
```

**Arguments:**
- `--username, -u`: Target Instagram username (required)
- `--state, -s`: Session state file path (default: `state.json`)
- `--out-json`: Output JSON file (default: `followers.json`)
- `--out-csv`: Output CSV file (default: `followers.csv`)
- `--max, -m`: Maximum followers to scrape (default: 1000)
- `--headless`: Run browser in headless mode (not recommended for login)

### 3. `main.py`
Automated follow/unfollow workflow with intelligent followback detection.

**Key Features:**
- Batch following with configurable delays
- Automatic unfollowing when users follow back
- Continuous monitoring loop
- Comprehensive action logging
- Accepts multiple input formats

**Usage:**
```bash
# Basic usage
python main.py --username your_username

# Custom settings
python main.py \
  --username your_username \
  --list followers.json \
  --interval 3600 \
  --batch 10 \
  --log my_log.jsonl

# Run with headless browser (after initial login)
python main.py --username your_username --headless
```

**Arguments:**
- `--username, -u`: Your Instagram username (required)
- `--state, -s`: Session state file (default: `state.json`)
- `--list, -l`: JSON file with usernames to follow (default: `followers.json`)
- `--interval, -i`: Seconds between followback checks (default: 3600)
- `--log`: Log file path (default: `follow_unfollow_log.jsonl`)
- `--batch`: Number of follows before pausing (default: 10)
- `--headless`: Run browser headless

**Input Format:**
The script accepts `followers.json` in two formats:

```json
// Simple array of usernames
["user1", "user2", "user3"]

// Array of objects (output from instagram_scraper.py)
[
  {"username": "user1", "profile_url": "...", "display_name": "..."},
  {"username": "user2", "profile_url": "...", "display_name": "..."}
]
```

## 🔄 Typical Workflow

1. **Scrape followers from a target profile:**
```bash
python instagram_scraper.py --username influencer_account --max 500
```

2. **Follow users and monitor for followbacks:**
```bash
python main.py --username your_username --list followers.json --interval 7200
```

3. **Check logs to see activity:**
```bash
cat follow_unfollow_log.jsonl
```

## ⚙️ Configuration

### Rate Limiting
The scripts include built-in delays to avoid detection:
- `MIN_DELAY_BETWEEN_ACTIONS`: 5 seconds
- `MAX_DELAY_BETWEEN_ACTIONS`: 12 seconds
- `BATCH_PAUSE`: 60 seconds after each batch
- Random jitter added to all delays

### Session State
Sessions are saved in `state.json` (or custom path) and include:
- Cookies
- Local storage
- Session storage

**Important:** Keep `state.json` private! It contains your login credentials.

## 📊 Log Format

Actions are logged in JSONL (newline-delimited JSON) format:

```json
{"action": "follow_attempt", "username": "user1", "performed": true, "ts": "2025-10-25T10:30:00Z"}
{"action": "check_followback", "username": "user1", "follows_me": true, "ts": "2025-10-25T11:30:00Z"}
{"action": "unfollow_on_followback", "username": "user1", "unfollowed": true, "ts": "2025-10-25T11:30:15Z"}
```

## 🚨 Safety Tips

1. **Start slow**: Test with small batches first
2. **Use realistic delays**: Instagram monitors automation patterns
3. **Don't run 24/7**: Take breaks to appear more human
4. **Monitor your account**: Watch for warnings or restrictions
5. **Use a throwaway account**: Test on an account you don't care about
6. **Respect rate limits**: Don't follow/unfollow too many users per day
7. **Keep session files secure**: Never commit `state.json` to git

## 🐛 Troubleshooting

### "Profile header did not load"
- Instagram may be blocking requests
- Try increasing timeout values
- Use a different IP/network
- Wait before retrying

### "Could not find followers link"
- Instagram's UI may have changed
- Check if the target profile is public
- Verify you're logged in correctly

### "Storage state failed to load"
- Delete `state.json` and log in again
- Ensure file permissions are correct
- Check if session has expired

### Excessive rate limiting
- Reduce `--batch` size
- Increase `--interval` time
- Add more random delays in the code

## 📝 .gitignore

Add these to your `.gitignore`:
```
state.json
*.jsonl
followers.json
followers.csv
*_followers.txt
dialog_debug.html
__pycache__/
*.pyc
```

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test thoroughly
4. Submit a pull request

## 📄 License

This project is provided as-is for educational purposes. Use responsibly.

## 🔗 Resources

- [Playwright Documentation](https://playwright.dev/python/)
- [Instagram Terms of Service](https://help.instagram.com/581066165581870)
- [Instagram Automation Best Practices](https://www.socialmediaexaminer.com/instagram-automation-dos-and-donts/)

---

**Remember:** Automation can be detected. Use these tools responsibly and at your own risk.