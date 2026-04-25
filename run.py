import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5001))
    debug = False

    app.run(host=host, port=port, debug=debug)
