import os
import threading
import webbrowser

from app import app


url = "http://127.0.0.1:5000"
threading.Timer(1.0, lambda: webbrowser.open(url)).start()
app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
