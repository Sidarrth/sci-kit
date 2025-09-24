import os
import random
import threading
import time
from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
import requests
from flask import (Flask, flash, jsonify, redirect, render_template,
                   render_template_string, request, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from sklearn.linear_model import LinearRegression
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
# IMPORTANT: Change this secret key in a real application!
app.config['SECRET_KEY'] = 'your-super-secret-key-for-hackathon'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- API KEY CONFIGURATION ---
# IMPORTANT: Get a free API key from https://openweathermap.org/
app.config['WEATHER_API_KEY'] = os.environ.get('WEATHER_API_KEY', 'YOUR_API_KEY_HERE')


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(100), default='New York, US') # For weather API
    
    health_data = db.relationship('HealthData', backref='user', lazy=True, cascade="all, delete-orphan")
    mood_logs = db.relationship('MoodLog', backref='user', lazy=True, cascade="all, delete-orphan")
    schedule_events = db.relationship('ScheduleEvent', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    steps = db.Column(db.Integer)
    sleep = db.Column(db.Float)
    heart_rate = db.Column(db.Integer)
    calories_burned = db.Column(db.Integer)
    calories_intake = db.Column(db.Integer)
    water_intake = db.Column(db.Float) # in Liters
    protein_g = db.Column(db.Integer)
    carbs_g = db.Column(db.Integer)
    fats_g = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class MoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    mood_score = db.Column(db.Integer, nullable=False) # 1-5 scale
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(100), nullable=False)
    start_hour = db.Column(db.Float, nullable=False)
    end_hour = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def analyze_mind_body_connection(health_df, mood_logs):
    if mood_logs.empty or health_df.shape[0] < 5: return None
    mood_logs['date'] = mood_logs['timestamp'].dt.date
    daily_mood = mood_logs.groupby('date')['mood_score'].mean().reset_index()
    # FIX: Explicitly convert health_df date column to handle potential datetime strings
    health_df['date'] = pd.to_datetime(health_df['date']).dt.date
    merged_df = pd.merge(health_df, daily_mood, on='date', how='inner') # Use inner join
    if merged_df.shape[0] < 5: return None
    
    sleep_corr = merged_df['sleep'].corr(merged_df['mood_score'])
    steps_corr = merged_df['steps'].corr(merged_df['mood_score'])
    strongest_link, message = "None", "Keep logging your mood to find connections!"
    
    # Check for NaN correlations before comparing
    if pd.notna(sleep_corr) and pd.notna(steps_corr):
        if abs(sleep_corr) > 0.4 or abs(steps_corr) > 0.4:
            if abs(sleep_corr) > abs(steps_corr):
                strongest_link, impact = "Sleep", "positive" if sleep_corr > 0 else "negative"
                message = f"Strong {impact} link found between your sleep and mood."
            else:
                strongest_link, impact = "Activity", "positive" if steps_corr > 0 else "negative"
                message = f"Clear {impact} connection between your steps and how you feel."
    elif pd.notna(sleep_corr) and abs(sleep_corr) > 0.4:
        strongest_link, impact = "Sleep", "positive" if sleep_corr > 0 else "negative"
        message = f"Strong {impact} link found between your sleep and mood."
    elif pd.notna(steps_corr) and abs(steps_corr) > 0.4:
        strongest_link, impact = "Activity", "positive" if steps_corr > 0 else "negative"
        message = f"Clear {impact} connection between your steps and how you feel."
        
    return {"strongest_link": strongest_link, "message": message}

# Placeholder for other analysis functions
def get_environmental_advice(location): return {"advice": "Weather looks clear.", "icon": "☀️"}
def forecast_stress_and_recovery(health_df): return None
def analyze_hydration_and_macros(latest_health_data): return {"nudge": "Remember to hydrate!"}
def generate_gamified_goals(health_df): return {"steps_goal": 8000, "sleep_goal": 7.5, "message": "New goals are set!"}
def train_sleep_model(health_df): return {"optimal_sleep": 7.8}



def simulate_new_day_for_user(user):
    last_data = HealthData.query.filter_by(user_id=user.id).order_by(HealthData.date.desc()).first()
    
    if last_data:
        # FIX: Ensure we are working with a date object, not datetime
        last_date_obj = last_data.date
        if isinstance(last_date_obj, datetime):
            last_date_obj = last_date_obj.date()
        new_date = last_date_obj + timedelta(days=1)
    else:
        new_date = date.today() - timedelta(days=14)

    # Generate random data...
    steps = random.randint(3000, 12000)
    sleep = round(random.uniform(6.0, 9.0), 1)
    # ... and so on for all fields.
    new_data = HealthData(
        user_id=user.id, date=new_date, steps=steps, sleep=sleep,
        heart_rate=random.randint(55, 75), calories_burned=int(steps * 0.045),
        calories_intake=random.randint(1800, 2600), water_intake=round(random.uniform(1.5, 3.0), 1),
        protein_g=random.randint(80, 150), carbs_g=random.randint(150, 300), fats_g=random.randint(50, 90)
    )
    db.session.add(new_data)
    db.session.commit()

@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('register'))
        user = User(username=request.form['username'])
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    health_data_query = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.asc()).all()
    
    if not health_data_query:
        return render_template('dashboard.html', no_data=True, today_date=date.today().isoformat())

    health_df = pd.DataFrame([d.__dict__ for d in health_data_query])
    mood_logs_query = MoodLog.query.filter_by(user_id=current_user.id).all()
    mood_df = pd.DataFrame([m.__dict__ for m in mood_logs_query]) if mood_logs_query else pd.DataFrame()

    insights = {
        "environment": get_environmental_advice(current_user.location),
        "nutrition": analyze_hydration_and_macros(health_data_query[-1]),
        "mind_body": analyze_mind_body_connection(health_df.copy(), mood_df.copy()),
        # ... etc.
    }

    return render_template('dashboard.html', insights=insights, latest_data=health_data_query[-1], today_date=date.today().isoformat())

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # ... [Profile logic remains the same]
    return render_template('profile.html', user=current_user)

@app.route('/report')
@login_required
def report():
    # ... [Report logic remains the same]
    return render_template('report.html')

@app.route('/simulate-day')
@login_required
def simulate_day():
    simulate_new_day_for_user(current_user)
    flash('A new day has been simulated!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/add-data', methods=['POST'])
@login_required
def add_data():
    try:
        # FIX: Ensure we are parsing the date string and getting a date object
        entry_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        
        existing_data = HealthData.query.filter_by(user_id=current_user.id, date=entry_date).first()
        
        if existing_data:
            data_record = existing_data
            flash_message = f'Data for {entry_date.strftime("%B %d, %Y")} has been updated!'
        else:
            data_record = HealthData(user_id=current_user.id, date=entry_date)
            db.session.add(data_record)
            flash_message = f'Data for {entry_date.strftime("%B %d, %Y")} has been logged!'
            
        data_record.steps = request.form.get('steps', type=int)
        data_record.sleep = request.form.get('sleep', type=float)
        data_record.heart_rate = request.form.get('heart_rate', type=int)
        data_record.calories_burned = request.form.get('calories_burned', type=int)
        data_record.calories_intake = request.form.get('calories_intake', type=int)
        data_record.water_intake = request.form.get('water_intake', type=float)
        data_record.protein_g = request.form.get('protein_g', type=int)
        data_record.carbs_g = request.form.get('carbs_g', type=int)
        data_record.fats_g = request.form.get('fats_g', type=int)

        db.session.commit()
        flash(flash_message, 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred: {e}', 'error')
        
    return redirect(url_for('dashboard'))

@app.route('/log-mood', methods=['POST'])
@login_required
def log_mood(): return jsonify(success=True)

@app.route('/api/chart-data')
@login_required
def chart_data():
    history = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.asc()).limit(14).all()
    return jsonify({
        "labels": [d.date.strftime("%b %d") for d in history],
        "steps": [d.steps for d in history],
        "heart_rate": [d.heart_rate for d in history]
    })
    
#
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8081)

