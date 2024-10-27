from flask import Flask, render_template
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
import os

app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static',
)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

socketio = SocketIO(app)
migrate = Migrate()
login_manager = LoginManager(app)

with app.app_context():
    from .routes import main, setupSockets
    app.register_blueprint(main)
    setupSockets(socketio)

    from .models import db, User
    db.init_app(app)
    db.create_all()
    migrate.init_app(app, db)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    login_manager.login_view = 'socket.login'
    login_manager.login_message_category = 'info'
    login_manager.login_message = 'Please log in to access this page.'




