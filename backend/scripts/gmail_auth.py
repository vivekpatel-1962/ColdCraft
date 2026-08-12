"""One-time Gmail authorization.

  python -m scripts.gmail_auth            # authorize (no-op if already valid)
  python -m scripts.gmail_auth --force    # re-authorize / switch to another account
  python -m scripts.gmail_auth --status   # just report, change nothing

Opens a browser. Whichever Google account you sign in with there becomes the
sending identity — it does NOT have to be the address in your resume; if they
differ, the send step sets Reply-To to the resume address and says so.

Setup, once, in the Google Cloud console for that account:
  1. Create (or pick) a project -> APIs & Services -> Library -> enable "Gmail API".
  2. OAuth consent screen -> External -> add the sending Gmail address as a Test user.
  3. Credentials -> Create credentials -> OAuth client ID -> Desktop app -> download JSON.
  4. Save it as backend/credentials.json (or set GMAIL_CREDENTIALS_PATH in .env).

The only scope requested is gmail.compose (manage drafts + send) — this program cannot read your mailbox.
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app import config  # noqa: E402
from app.send import gmail  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return

    if "--status" in args:
        st = gmail.status()
        print(f"credentials file: {config.GMAIL_CREDENTIALS_PATH} "
              f"({'found' if st.credentials_present else 'MISSING'})")
        print(f"token file:       {config.GMAIL_TOKEN_PATH}")
        print(f"authorized:       {st.authorized}")
        print(f"sending as:       {st.address or '—'}")
        print(f"detail:           {st.detail}")
        return

    try:
        st = gmail.authorize(force="--force" in args)
    except gmail.SendError as e:
        print(f"\n{e}\n")
        sys.exit(1)

    print(f"\n{st.detail}")
    print(f"Token cached at {config.GMAIL_TOKEN_PATH} (gitignored).")
    print("Nothing has been sent. Draft an email, then: python -m scripts.send_email <email_id>")


if __name__ == "__main__":
    main()
