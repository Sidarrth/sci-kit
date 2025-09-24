import os
import random
import json
from datetime import datetime, timedelta, date

import requests
import pandas as pd
import numpy as np
from flask import (Flask, flash, jsonify, redirect, render_template, request, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-super-secret-key-for-hackathon'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WEATHER_API_KEY'] = os.environ.get('WEATHER_API_KEY', '29a617fe2e512a8011963bea8ff5f36f')
GEMINI_API_KEY = "AIzaSyArvG4F-MFvcjIOYlBPUFp_NlOMv4IUDA4" # IMPORTANT: PASTE YOUR GEMINI API KEY HERE

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    height_cm = db.Column(db.Float, nullable=False)
    location = db.Column(db.String(100), default='New York, US')
    health_data = db.relationship('HealthData', backref='user', lazy=True, cascade="all, delete-orphan")
    food_logs = db.relationship('FoodLog', backref='user', lazy=True, cascade="all, delete-orphan")
    mood_logs = db.relationship('MoodLog', backref='user', lazy=True, cascade="all, delete-orphan")
    schedule_events = db.relationship('ScheduleEvent', backref='user', lazy=True, cascade="all, delete-orphan")
    hobbies = db.relationship('Hobby', backref='user', lazy=True, cascade="all, delete-orphan")
    badges = db.relationship('Badge', secondary='user_badges', backref='users')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    steps = db.Column(db.Integer, default=0)
    sleep = db.Column(db.Float, default=0.0)
    heart_rate = db.Column(db.Integer, default=0)
    calories_burned = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class FoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_description = db.Column(db.String(300), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class MoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    mood_score = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
class ScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(100), nullable=False)
    start_hour = db.Column(db.Float, nullable=False)
    end_hour = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Hobby(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    icon = db.Column(db.String(10), nullable=False)
    description = db.Column(db.String(200), nullable=False)

user_badges = db.Table('user_badges',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('badge_id', db.Integer, db.ForeignKey('badge.id'), primary_key=True)
)

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

def calculate_tdee(user):
    if user.gender.lower() == 'male': bmr = 88.362 + (13.397 * user.weight_kg) + (4.799 * user.height_cm) - (5.677 * user.age)
    else: bmr = 447.593 + (9.247 * user.weight_kg) + (3.098 * user.height_cm) - (4.330 * user.age)
    return int(bmr * 1.2)

def call_gemini_api(system_prompt, user_query):
    if not GEMINI_API_KEY: return "Error: Gemini API key is not configured."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"
    payload = { "contents": [{"parts": [{"text": user_query}]}], "systemInstruction": {"parts": [{"text": system_prompt}]} }
    try:
        response = requests.post(url, json=payload); response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e: return f"Error connecting to AI service: {e}"

def get_environmental_advice(location):
    api_key = app.config.get('WEATHER_API_KEY');
    if not api_key or api_key == 'YOUR_API_KEY_HERE': return {"title": "Environmental Advisor", "message": "Weather API key not set."}
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
        response = requests.get(url); response.raise_for_status(); weather = response.json()
        desc = weather['weather'][0]['description']; temp = weather['main']['temp']
        if "rain" in desc: return {"title": "Weather Alert", "message": f"It's raining in {location}. A perfect day for an indoor workout!"}
        return {"title": "Today's Outlook", "message": f"It's {temp}°C with {desc} in {location}. Looks like a great day for an outdoor activity!"}
    except requests.exceptions.HTTPError: return {"title": "Environmental Advisor", "message": f"Could not find weather for '{location}'."}
    except requests.exceptions.RequestException: return {"title": "Environmental Advisor", "message": "Could not connect to the weather service."}

def analyze_stress_and_burnout(health_df):
    if len(health_df) < 7: return None
    health_df['step_pct_change'] = health_df['steps'].pct_change()
    for i in range(1, len(health_df)):
        if health_df.iloc[i-1]['step_pct_change'] > 0.5 and health_df.iloc[i]['step_pct_change'] < -0.4:
            return {"title": "Pace & Consistency Alert", "message": f"A large activity spike on {health_df.iloc[i-1]['date'].strftime('%b %d')} was followed by a crash. This pattern can lead to burnout. Aiming for consistency is often more effective."}
    recent_data = health_df.tail(2)
    if len(recent_data) == 2 and all(recent_data['sleep'] > 7.0) and all(recent_data['heart_rate'] > health_df['heart_rate'].mean() + 5):
        return {"title": "Stress Alert", "message": "Your resting heart rate has been higher than usual for the past two days, even with good sleep. This can be a sign of stress. Consider a mindfulness exercise today."}
    return None

def analyze_mind_body_connection(health_df, mood_df):
    if len(health_df) < 5 or len(mood_df) < 5: return None
    merged_df = pd.merge(health_df, mood_df, on='date')
    if len(merged_df) < 5: return None
    sleep_corr = merged_df['sleep'].corr(merged_df['mood_score'])
    if abs(sleep_corr) > 0.5:
        return {"title": "Mind-Body Insight", "message": f"We've found a strong link between your sleep and mood ({int(sleep_corr*100)}% correlation). Prioritizing sleep seems to be key for your mental well-being."}
    return None

def find_optimal_slots(schedule, hobbies):
    slots = np.ones(28);
    for event in schedule:
        start_idx = int((event.start_hour - 8) * 2); end_idx = int((event.end_hour - 8) * 2)
        slots[start_idx:end_idx] = 0
    best_workout_slot = -1; best_workout_score = -1; best_hobby_slots = []
    free_indices = np.where(slots == 1)[0]
    for i in free_indices:
        hour = 8 + i * 0.5; workout_score = 1 - abs(hour - 16) / 8 
        if workout_score > best_workout_score: best_workout_score = workout_score; best_workout_slot = hour
    if hobbies and len(free_indices) > 2:
       for i in free_indices:
            hour = 8 + i * 0.5
            if hour != best_workout_slot and (hour < 12 or hour > 18):
                best_hobby_slots.append(f"{int(hour)}:{'30' if hour % 1 else '00'}")
                if len(best_hobby_slots) >= len(hobbies): break
    workout_time = f"{int(best_workout_slot)}:{'30' if best_workout_slot % 1 else '00'}" if best_workout_slot != -1 else "No clear slot"
    return {"workout": workout_time, "hobbies": best_hobby_slots}


@app.route('/'); def index(): return redirect(url_for('dashboard')) if current_user.is_authenticated else redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True); return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists.', 'error'); return redirect(url_for('register'))
        user = User(username=request.form['username'], age=int(request.form['age']), gender=request.form['gender'], weight_kg=float(request.form['weight_kg']), height_cm=float(request.form['height_cm']))
        user.set_password(request.form['password']); db.session.add(user); db.session.commit()
        flash('Registration successful! Please log in.', 'success'); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout'); @login_required; def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    health_data = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.asc()).all()
    mood_logs = MoodLog.query.filter_by(user_id=current_user.id).all()
    schedule = ScheduleEvent.query.filter_by(user_id=current_user.id).all()
    hobbies = Hobby.query.filter_by(user_id=current_user.id).all()
    insights = {}
    if health_data:
        health_df = pd.DataFrame([d.__dict__ for d in health_data]); health_df['date'] = pd.to_datetime(health_df['date'])
        mood_df = pd.DataFrame([m.__dict__ for m in mood_logs]) if mood_logs else pd.DataFrame(columns=['date', 'mood_score'])
        if not mood_df.empty: mood_df['date'] = pd.to_datetime(mood_df['date'])
        insights['stress'] = analyze_stress_and_burnout(health_df)
        insights['mind_body'] = analyze_mind_body_connection(health_df, mood_df)
    insights['slots'] = find_optimal_slots(schedule, hobbies)
    insights['environment'] = get_environmental_advice(current_user.location)
    return render_template('dashboard.html', insights=insights, today_date=date.today().isoformat())

@app.route('/nutrition')
@login_required
def nutrition():
    tdee = calculate_tdee(current_user)
    food_today = FoodLog.query.filter_by(user_id=current_user.id, date=date.today()).all()
    calories_consumed = sum(log.calories for log in food_today)
    health_today = HealthData.query.filter_by(user_id=current_user.id, date=date.today()).first()
    calories_burned = health_today.calories_burned if health_today else 0
    net_calories = tdee - calories_consumed + calories_burned
    return render_template('nutrition.html', tdee=tdee, calories_consumed=calories_consumed, calories_burned=calories_burned, net_calories=net_calories, food_logs=food_today)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        if 'event_name' in request.form:
            db.session.add(ScheduleEvent(event_name=request.form['event_name'], start_hour=float(request.form['start_hour']), end_hour=float(request.form['end_hour']), user_id=current_user.id)); flash('Event added!', 'success')
        elif 'hobby_name' in request.form:
            db.session.add(Hobby(name=request.form['hobby_name'], user_id=current_user.id)); flash('Hobby added!', 'success')
        db.session.commit(); return redirect(url_for('profile'))
    hobbies = Hobby.query.filter_by(user_id=current_user.id).all()
    schedule = ScheduleEvent.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', hobbies=hobbies, schedule=schedule, badges=current_user.badges)

@app.route('/chatbot'); @login_required; def chatbot(): return render_template('chatbot.html')
@app.route('/report'); @login_required; def report():
    health_data = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.desc()).limit(7).all()
    return render_template('report.html', health_data=health_data)

@app.route('/add-data', methods=['POST'])
@login_required
def add_data():
    try:
        form_date = date.fromisoformat(request.form['date'])
        data = HealthData.query.filter_by(user_id=current_user.id, date=form_date).first()
        if not data: data = HealthData(user_id=current_user.id, date=form_date); db.session.add(data)
        data.steps = int(request.form['steps']); data.sleep = float(request.form['sleep']); data.heart_rate = int(request.form['heart_rate']); data.calories_burned = int(request.form['calories_burned'])
        flash('Data logged successfully!', 'success'); db.session.commit()
    except Exception as e: db.session.rollback(); flash(f'Error logging data: {e}', 'error')
    return redirect(url_for('dashboard'))
    
@app.route('/log-mood', methods=['POST'])
@login_required
def log_mood():
    mood_score = request.form.get('mood_score')
    log = MoodLog.query.filter_by(user_id=current_user.id, date=date.today()).first()
    if log: log.mood_score = mood_score
    else: db.session.add(MoodLog(user_id=current_user.id, date=date.today(), mood_score=mood_score))
    db.session.commit(); flash('Mood logged!', 'success'); return redirect(url_for('dashboard'))

@app.route('/simulate-day')
@login_required
def simulate_day():
    last_data = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.desc()).first()
    new_date = (last_data.date + timedelta(days=1)) if last_data else date.today()
    if HealthData.query.filter_by(user_id=current_user.id, date=new_date).first():
        flash(f'Data for {new_date.strftime("%b %d")} already exists.', 'info'); return redirect(url_for('dashboard'))
    new_data = HealthData(user_id=current_user.id, date=new_date, steps=random.randint(4000, 12000), sleep=round(random.uniform(6.0, 9.0), 1), heart_rate=random.randint(55, 75), calories_burned=random.randint(300, 700))
    db.session.add(new_data); db.session.commit(); flash('A new day has been simulated!', 'success'); return redirect(url_for('dashboard'))

@app.route('/delete-event/<int:event_id>'); @login_required
def delete_event(event_id):
    event = db.session.get(ScheduleEvent, event_id)
    if event and event.user_id == current_user.id: db.session.delete(event); db.session.commit()
    return redirect(url_for('profile'))

@app.route('/api/log-food', methods=['POST'])
@login_required
def log_food():
    food_description = request.form['food_description']
    system_prompt = "You are a nutritional analysis expert. Based on the user's meal description, return a JSON object with your best estimate for `calories`. ONLY return the JSON object. Example: {\"calories\": 350}"
    response_str = call_gemini_api(system_prompt, food_description)
    try:
        calories = int(json.loads(response_str)['calories'])
        db.session.add(FoodLog(user_id=current_user.id, date=date.today(), meal_description=food_description, calories=calories)); db.session.commit()
        flash(f'Successfully logged "{food_description}" with an estimated {calories} calories.', 'success')
    except (json.JSONDecodeError, KeyError, TypeError): flash('The AI could not analyze that meal. Please try again.', 'error')
    return redirect(url_for('nutrition'))

@app.route('/api/chatbot', methods=['POST'])
@login_required
def api_chatbot():
    user_message = request.json.get('message')
    system_prompt = "You are a friendly wellness assistant. Provide concise, safe advice. Do not give medical diagnoses."
    response = call_gemini_api(system_prompt, user_message)
    return jsonify({"reply": response})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Badge.query.first():
            badges = [Badge(name="First Steps", icon="👟", description="Logged your first day of data."), Badge(name="Active Week", icon="🔥", description="Met a 7-day activity streak.")]
            db.session.bulk_save_objects(badges); db.session.commit()
    app.run(debug=True, port=8081)

