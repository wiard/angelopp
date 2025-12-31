from flask import Flask, request
import landmark_game
from angelopp import handle_ussd

print('[USSD] running file:', __file__, flush=True)
app = Flask(__name__)

landmark_game.ensure_schema()
@app.route("/ussd", methods=["POST"])
def ussd():
    session_id = request.form.get("sessionId", "") or ""
    phone_number = request.form.get("phoneNumber", "") or ""
    text = request.form.get("text", "") or ""

    rv = handle_ussd(session_id=session_id, phone_number=phone_number, text=text)

    # Flatten accidental nested tuples: ((body, code), code)
    if isinstance(rv, tuple) and len(rv) == 2 and isinstance(rv[0], tuple) and len(rv[0]) == 2:
        rv = rv[0]

    return rv


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)


def _stars(level:int)->str:
    return '★ ' + str(level)

# WEEKLY_LANDMARK_LEADERBOARD: injection marker not found
