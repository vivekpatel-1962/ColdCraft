"""Send a drafted email — after you look at exactly what goes out.

  python -m scripts.send_email 12                 # email #12: show it, then ask
  python -m scripts.send_email --run 8            # the latest draft on run #8
  python -m scripts.send_email 12 --to a@b.com    # set/override the recipient
  python -m scripts.send_email 12 --dry-run       # render + report, transmit nothing
  python -m scripts.send_email 12 --yes           # skip the prompt (you are the gate)

  --override-verdict   send even though the verifier said FAIL
  --resend             send again even though this email already went out

The default is interactive: the full envelope is printed and you must type
'send'. Anything else aborts. This script is the only way mail leaves the
program from the CLI — generation never sends.
"""
import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from app.db import database  # noqa: E402
from app.send import compose  # noqa: E402
from app.send.compose import NotSendable  # noqa: E402
from app.send.gmail import SendError  # noqa: E402

RULE = "=" * 68


def _parse(argv: list[str]) -> dict:
    o = {"email_id": None, "run": None, "to": None, "dry_run": False,
         "yes": False, "override_verdict": False, "resend": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            o["dry_run"] = True
        elif a in ("--yes", "-y"):
            o["yes"] = True
        elif a == "--override-verdict":
            o["override_verdict"] = True
        elif a == "--resend":
            o["resend"] = True
        elif a in ("--run", "--to"):
            i += 1
            if i >= len(argv):
                print(f"{a} needs a value"); sys.exit(1)
            o[a[2:]] = argv[i]
        elif a.isdigit():
            o["email_id"] = int(a)
        else:
            print(f"Unknown argument: {a}"); print(__doc__); sys.exit(1)
        i += 1
    if o["email_id"] is None and o["run"] is None:
        print(__doc__); sys.exit(1)
    return o


def _resolve_email_id(o: dict) -> int:
    if o["email_id"] is not None:
        return o["email_id"]
    row = database.get_email_for_run(int(o["run"]))
    if row is None:
        print(f"Run #{o['run']} has no draft yet."); sys.exit(2)
    return row["id"]


def _print_envelope(env) -> None:
    if env.from_address:
        sender = f"{env.from_name} <{env.from_address}>" if env.from_name else env.from_address
    else:
        sender = "— Gmail not connected —"
    print("\n" + RULE)
    print(f"FROM:    {sender}")
    print(f"TO:      {env.to or '— none —'}")
    if env.reply_to:
        print(f"REPLY-TO:{env.reply_to}")
    print(f"SUBJECT: {env.subject}")
    if env.attachment:
        print(f"ATTACH:  {env.attachment.filename} ({env.attachment.size_bytes / 1024:.0f} KB)")
    else:
        print("ATTACH:  — nothing —")
    print(RULE)
    print(env.body)
    print(RULE)
    for w in env.warnings:
        print(f"  ! {w}")
    for b in env.blockers:
        print(f"  X BLOCKED: {b}")


def main() -> None:
    o = _parse(sys.argv[1:])
    database.init_db()
    email_id = _resolve_email_id(o)

    try:
        env = compose.build_envelope(email_id, recipient_override=o["to"])
    except NotSendable as e:
        print(e); sys.exit(2)

    _print_envelope(env)

    if not o["yes"] and not o["dry_run"]:
        print("\nThis will really send the email above.")
        answer = input("Type 'send' to send it, anything else to abort: ").strip().lower()
        if answer != "send":
            print("Aborted. Nothing was sent.")
            return

    try:
        result = compose.send(
            email_id,
            confirm=True,
            recipient_override=o["to"],
            override_verdict=o["override_verdict"],
            allow_resend=o["resend"],
            dry_run=o["dry_run"],
        )
    except NotSendable as e:
        print(f"\nNot sent: {e}")
        sys.exit(2)
    except SendError as e:
        print(f"\nSend failed: {e}")
        sys.exit(3)

    if result.dry_run:
        print(f"\nDRY RUN — message rendered, nothing transmitted. "
              f"Would have gone to {result.to} from {result.from_address}.")
    else:
        print(f"\nSent to {result.to} at {result.sent_at} (gmail id {result.message_id}).")
        print(f"Recorded on email #{email_id}. Mark the outcome later with the "
              f"/api/emails/{email_id}/outcome route or the Runs tab.")


if __name__ == "__main__":
    main()
