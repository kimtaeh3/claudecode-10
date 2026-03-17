from flask import Flask, redirect, url_for
from app.config import Config
from app import db


def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    app.config['DATABASE'] = Config.DATABASE

    db.init_app(app)

    from app.routes import auth, hours, forecast, admin, bulk
    app.register_blueprint(auth.bp)
    app.register_blueprint(hours.bp)
    app.register_blueprint(forecast.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(bulk.bp)

    @app.route('/')
    def index():
        return redirect(url_for('bulk.index'))

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('error.html', code=404, message='Page not found'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template('error.html', code=500, message='Server error'), 500

    return app
