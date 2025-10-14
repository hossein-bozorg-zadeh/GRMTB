# GitHub Release Monitor Telegram Bot

A Telegram bot designed to monitor GitHub repositories for new releases and send instant notifications to your specified Telegram chat. The bot manages its configuration (repository list and update schedules) entirely through Telegram commands.

## Key Features & Benefits

*   **Real-time Notifications:** Get immediate alerts when new releases are published on GitHub repositories.
*   **Telegram Command Based Configuration:** Manage repositories to monitor and update schedules directly within Telegram.
*   **24/7 Monitoring:** The bot runs continuously using APScheduler to ensure timely release notifications.
*   **Persistent Data Storage:** Uses Firebase Firestore to store bot configurations and prevent data loss.

## Prerequisites & Dependencies

*   **Python 3.7+:** Ensure you have Python 3.7 or a later version installed.
*   **Telegram Bot Token:** Create a Telegram bot and obtain its API token from BotFather.
*   **Firebase Project:** Set up a Firebase project and obtain the necessary credentials.
*   **Required Python Libraries:** Install the following libraries using pip:
    ```bash
    pip install python-telegram-bot firebase-admin apscheduler requests
    ```

## Installation & Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/hossein-bozorg-zadeh/GitHub-Release-Monitor-Telegram-Bot.git
    cd GitHub-Release-Monitor-Telegram-Bot
    ```

2.  **Set up Firebase:**
    *   Create a Firebase project at [https://console.firebase.google.com/](https://console.firebase.google.com/).
    *   Create a service account and download the JSON key file.
    *   Rename the downloaded JSON file to `firebase_credentials.json` and place it in the project directory.

3.  **Configure Environment Variables:**
    Set the following environment variables:

    *   `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
    *   `FIREBASE_CREDENTIALS`: Path to your Firebase credentials file (`firebase_credentials.json`). This is not strictly necessary as the `telegram_bot.py` currently expects the file to be present in the same directory.

    You can set these variables directly in your terminal or create a `.env` file. Example using the terminal:

    ```bash
    export TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
    ```

4.  **Run the Bot:**
    ```bash
    python telegram_bot.py
    ```

## Usage Examples

Once the bot is running, you can use the following Telegram commands:

*   `/start`: Starts the bot and initializes the configuration.
*   `/add_repo <owner>/<repo>`: Adds a repository to the monitoring list. Example: `/add_repo pytorch/pytorch`
*   `/remove_repo <owner>/<repo>`: Removes a repository from the monitoring list. Example: `/remove_repo pytorch/pytorch`
*   `/list_repos`: Lists all currently monitored repositories.
*   `/set_interval <minutes>`: Sets the interval (in minutes) for checking for new releases.  Example: `/set_interval 60`
*   `/help`: Displays a list of available commands.

## Configuration Options

| Option          | Description                                        | Default Value |
| --------------- | -------------------------------------------------- | ------------- |
| `TELEGRAM_BOT_TOKEN` | The API token for your Telegram bot.              | *Required*    |
| `FIREBASE_CREDENTIALS` | Path to your Firebase credentials JSON file.  | *Required*    |
| Update Interval  | The interval (in minutes) to check for new releases. | User Configured |

## Contributing Guidelines

Contributions are welcome! Please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix.
3.  Make your changes and ensure they are well-tested.
4.  Submit a pull request with a clear description of your changes.

## License Information

License not specified.

## Acknowledgments

*   [Python Telegram Bot](https://github.com/python-telegram-bot/python-telegram-bot): Core Telegram bot library.
*   [Firebase Admin SDK](https://firebase.google.com/docs/admin/setup): Firebase Admin SDK for persistent data storage.
*   [APScheduler](https://apscheduler.readthedocs.io/en/3.x/): APScheduler for background job execution.
*   [Requests](https://requests.readthedocs.io/en/latest/): Requests for HTTP calls to GitHub API.
