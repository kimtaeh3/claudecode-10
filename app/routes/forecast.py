from flask import Blueprint, render_template, session
from app.routes.auth import login_required
from app.db import get_db

bp = Blueprint('forecast', __name__, url_prefix='/forecast')


@bp.route('/')
@login_required
def index():
    db = get_db()
    rows = db.execute(
        'SELECT f.forecast_id, f.progress, f.task_id, f.customer, f.sow, f.utilization, '
        'f.project_name, f.team, '
        '(SELECT u.full_name FROM user u WHERE u.user_id = f.pm) as pm, '
        '(SELECT u.full_name FROM user u WHERE u.user_id = f.team_lead) as team_lead, '
        'f.sub_org, f.cost, '
        '(SELECT u.full_name FROM user u WHERE u.user_id = f.resources) as resources, '
        'f.role, f.hrs_rate, f.perc, f.alloc, f.con, f.forecast, f.rem '
        'FROM forecast f '
        'WHERE f.resources = (SELECT u.user_id FROM user u WHERE u.username = ?)',
        (session['user_id'],)
    ).fetchall()
    return render_template('forecast/index.html', rows=rows)
