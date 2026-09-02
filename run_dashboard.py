"""Start the web dashboard."""
from app.dashboard.web import run_web_dashboard
run_web_dashboard(host="127.0.0.1", port=5000, debug=False)
