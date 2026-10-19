"""Candidate entry point: imports create no database or Firebase connection."""
import os
from application import create_app

app=create_app()

if __name__=="__main__":
    app.run(host="127.0.0.1",port=int(os.getenv("PORT","5001")),debug=False)
