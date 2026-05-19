from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from app.config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.blueprints.main import main_bp
    app.register_blueprint(main_bp)

    from app.blueprints.listings import listings_bp
    app.register_blueprint(listings_bp)

    # Register other blueprints here when created
    # from app.blueprints.main import main_bp
    # app.register_blueprint(main_bp)

    return app