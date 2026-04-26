import os
from app import create_app, socketio

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5001))
    debug = False

    socketio.run(app, host=host, port=port, debug=debug)
