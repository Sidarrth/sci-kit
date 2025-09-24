import os
import re
import json
from datetime import datetime, timedelta, date
import random
import requests
import pandas as pd
import numpy as np
from flask import (Flask, flash, jsonify, redirect, render_template, request, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key-for-soulhealth-hackathon'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WEATHER_API_KEY'] = os.environ.get('WEATHER_API_KEY', '29a617fe2e512a8011963bea8ff5f36f')
GEMINI_API_KEY = "AIzaSyDWNlUC9R4lArkfK79YHbUuUVkxDrn9Cmo" # IMPORTANT: PASTE YOUR GEMINI API KEY HERE

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
    fitness_goal = db.Column(db.String(50), nullable=False, default='maintain') # lose_weight, maintain, gain_weight
    location = db.Column(db.String(100), default='New York, US')
    
    health_data = db.relationship('HealthData', backref='user', lazy=True, cascade="all, delete-orphan")
    food_logs = db.relationship('FoodLog', backref='user', lazy=True, cascade="all, delete-orphan")
    weekly_schedule = db.relationship('WeeklyScheduleEvent', backref='user', lazy=True, cascade="all, delete-orphan")
    hobbies = db.relationship('Hobby', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    steps = db.Column(db.Integer, default=0)
    sleep = db.Column(db.Float, default=0.0)
    heart_rate = db.Column(db.Integer, default=0)
    calories_burned = db.Column(db.Integer, default=0)
    water_intake_ml = db.Column(db.Integer, default=0)
    mood = db.Column(db.String(20), nullable=True) # e.g., "😊 Great"
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class FoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_description = db.Column(db.String(300), nullable=False)
    calories = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class WeeklyScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.Integer, nullable=False) # Monday=0, Sunday=6
    event_name = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.String(5), nullable=False) # HH:MM
    end_time = db.Column(db.String(5), nullable=False) # HH:MM
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Hobby(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))


def calculate_tdee(user):
    # Harris-Benedict Equation for Basal Metabolic Rate (BMR)
    if user.gender.lower() == 'male':
        bmr = 88.362 + (13.397 * user.weight_kg) + (4.799 * user.height_cm) - (5.677 * user.age)
    else: # 'female'
        bmr = 447.593 + (9.247 * user.weight_kg) + (3.098 * user.height_cm) - (4.330 * user.age)
    
    # Adjust TDEE based on fitness goal
    if user.fitness_goal == 'lose_weight':
        return int(bmr * 1.2) - 500 # 500 calorie deficit
    elif user.fitness_goal == 'gain_weight':
        return int(bmr * 1.2) + 500 # 500 calorie surplus
    else: # maintain
        return int(bmr * 1.2)

def get_recommended_water_intake(user):
    # A common recommendation is 35ml per kg of body weight
    return int(user.weight_kg * 35)

def call_gemini_api(system_prompt, user_query):
    if not GEMINI_API_KEY: return "Error: Gemini API key is not configured."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"
    payload = { "contents": [{"parts": [{"text": user_query}]}], "systemInstruction": {"parts": [{"text": system_prompt}]} }
    try:
        response = requests.post(url, json=payload); response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e: return f"Error connecting to AI service: {e}"

def get_environmental_advice(location):
    api_key = app.config.get('WEATHER_API_KEY')
    if not api_key or api_key == 'YOUR_API_KEY_HERE':
        return {"title": "Environmental Advisor", "message": "Weather API key not set. Add it in your profile to see local advice."}
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
        response = requests.get(url); response.raise_for_status(); weather = response.json()
        desc = weather['weather'][0]['description']; temp = weather['main']['temp']
        if "rain" in desc:
            return {"title": "Weather Alert", "message": f"It's raining in {location}. A perfect day for an indoor workout or stretching session!"}
        return {"title": "Today's Outlook", "message": f"It's currently {temp}°C with {desc} in {location}. Looks like a great day to be active outside!"}
    except requests.exceptions.HTTPError:
         return {"title": "Environmental Advisor", "message": f"Could not find weather data for '{location}'. Please check the location name in your profile."}
    except requests.exceptions.RequestException:
        return {"title": "Environmental Advisor", "message": "Could not connect to the weather service."}

def find_optimal_slots(schedule, hobbies):
    def time_to_minutes(time_str): h, m = map(int, time_str.split(':')); return h * 60 + m
    day_slots = np.ones(56) # (22 - 8) hours * 4 slots/hour (15-min intervals)
    for event in schedule:
        start_minutes = time_to_minutes(event.start_time); end_minutes = time_to_minutes(event.end_time)
        start_idx = max(0, int((start_minutes - 480) / 15)); end_idx = min(56, int((end_minutes - 480) / 15))
        day_slots[start_idx:end_idx] = 0
    free_indices = np.where(day_slots == 1)[0]
    if len(free_indices) < 3: return {"workout": "Not enough free time today", "hobbies": []}
    best_workout_slot = -1; best_workout_score = -1
    for i in free_indices:
        hour = 8 + (i * 15) / 60; workout_score = 1 - abs(hour - 16.5) / 8.5 # Peak energy at 4:30 PM
        if workout_score > best_workout_score: best_workout_score = workout_score; best_workout_slot = i
    def idx_to_time(idx): minutes = 480 + idx * 15; return f"{minutes // 60:02d}:{minutes % 60:02d}"
    workout_time = idx_to_time(best_workout_slot) if best_workout_slot != -1 else "No clear slot"
    return {"workout": workout_time, "hobbies": []} # Simplified for now

def get_free_hours_today(schedule_today):
    # Total minutes in the active day (8:00 AM to 10:00 PM)
    total_minutes = (22 - 8) * 60
    
    # Calculate busy minutes from the schedule
    busy_minutes = 0
    def time_to_minutes(time_str):
        h, m = map(int, time_str.split(':'))
        return h * 60 + m

    for event in schedule_today:
        start_time_minutes = time_to_minutes(event.start_time)
        end_time_minutes = time_to_minutes(event.end_time)
        busy_minutes += (end_time_minutes - start_time_minutes)

    # Calculate free hours
    free_hours = (total_minutes - busy_minutes) / 60
    return round(free_hours, 1)

@app.route('/')
def index():
    return render_template('index.html')

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
        if float(request.form['weight_kg']) <= 0 or float(request.form['height_cm']) <= 0 or int(request.form['age']) <=0:
            flash('Age, weight, and height must be positive numbers.', 'error'); return redirect(url_for('register'))
        user = User(username=request.form['username'], age=int(request.form['age']), gender=request.form['gender'], weight_kg=float(request.form['weight_kg']), height_cm=float(request.form['height_cm']), fitness_goal=request.form['fitness_goal'])
        user.set_password(request.form['password']); db.session.add(user); db.session.commit()
        hobbies_str = request.form.get('hobbies', '')
        if hobbies_str:
            for hobby_name in hobbies_str.split(','):
                if hobby_name.strip(): db.session.add(Hobby(name=hobby_name.strip(), user_id=user.id))
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        for i, day in enumerate(days):
            event_names = request.form.getlist(f'{day}_event_name[]'); start_times = request.form.getlist(f'{day}_start_time[]'); end_times = request.form.getlist(f'{day}_end_time[]')
            for name, start, end in zip(event_names, start_times, end_times):
                if name and start and end: db.session.add(WeeklyScheduleEvent(day_of_week=i, event_name=name, start_time=start, end_time=end, user_id=user.id))
        db.session.commit()
        flash('Registration successful! Please log in.', 'success'); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    today_weekday = datetime.today().weekday()
    schedule_today = WeeklyScheduleEvent.query.filter_by(user_id=current_user.id, day_of_week=today_weekday).all()
    hobbies = Hobby.query.filter_by(user_id=current_user.id).all()
    free_hours = get_free_hours_today(schedule_today)
    last_logged_day = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.desc()).first()
    next_log_date = (last_logged_day.date + timedelta(days=1)) if last_logged_day else date.today()
    insights = {
        'environment': get_environmental_advice(current_user.location),
        'slots': find_optimal_slots(schedule_today, hobbies)
    }
    return render_template('dashboard.html', free_hours=free_hours, next_log_date=next_log_date.isoformat(), insights=insights)

@app.route('/nutrition')
@login_required
def nutrition():
    tdee = calculate_tdee(current_user)
    recommended_water = get_recommended_water_intake(current_user)
    food_today = FoodLog.query.filter_by(user_id=current_user.id, date=date.today()).all()
    calories_consumed = sum(log.calories for log in food_today)
    health_today = HealthData.query.filter_by(user_id=current_user.id, date=date.today()).first()
    calories_burned = health_today.calories_burned if health_today else 0
    water_consumed = health_today.water_intake_ml if health_today else 0
    net_calories = tdee - calories_consumed + calories_burned
    
    # FIX for TypeError: Calculate percentage safely
    water_percentage = 0
    if recommended_water > 0:
        water_percentage = min((water_consumed / recommended_water) * 100, 100)

    diet_plan_prompt = f"Based on a fitness goal to '{current_user.fitness_goal.replace('_', ' ')}' and a daily calorie budget of {tdee} calories, create a simple, sample one-day meal plan (Breakfast, Lunch, Dinner, Snack). Be concise."
    diet_plan = call_gemini_api("You are a helpful nutritionist.", diet_plan_prompt)
    
    return render_template('nutrition.html', tdee=tdee, calories_consumed=calories_consumed,
                           calories_burned=calories_burned, net_calories=net_calories,
                           water_consumed=water_consumed, recommended_water=recommended_water,
                           water_percentage=water_percentage, food_logs=food_today, diet_plan=diet_plan)
@app.route('/exercise_plan')
@login_required
def exercise_plan():
    # Gather user data for the prompt
    user_data = {
        "age": current_user.age,
        "gender": current_user.gender,
        "weight_kg": current_user.weight_kg,
        "height_cm": current_user.height_cm,
        "fitness_goal": current_user.fitness_goal.replace('_', ' '),
        "schedule": [f"{e.event_name} from {e.start_time} to {e.end_time} on day {e.day_of_week}" for e in current_user.weekly_schedule],
        "hobbies": [h.name for h in current_user.hobbies]
    }
    
    # Create a detailed prompt for Gemini
    prompt = f"As a fitness coach, create a personalized weekly exercise plan for a user with the following details: {json.dumps(user_data)}. The plan should include specific exercises, sets, and reps. Also, incorporate their hobbies into the plan if possible. The plan must fit within their weekly schedule. Be motivational and concise."
    
    # Call the Gemini API
    exercise_plan_text = call_gemini_api("You are an expert fitness coach.", prompt)
    
    # Render the new template with the generated plan
    return render_template('exercise_plan.html', exercise_plan=exercise_plan_text)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # FIX: Check which form was submitted
        if 'location' in request.form:
             current_user.location = request.form['location']
             db.session.commit()
             flash('Location updated successfully!', 'success')
        elif 'day_of_week' in request.form:
            day_of_week = int(request.form['day_of_week'])
            WeeklyScheduleEvent.query.filter_by(user_id=current_user.id, day_of_week=day_of_week).delete()
            event_names = request.form.getlist('event_name[]')
            start_times = request.form.getlist('start_time[]')
            end_times = request.form.getlist('end_time[]')
            for name, start, end in zip(event_names, start_times, end_times):
                if name and start and end:
                    db.session.add(WeeklyScheduleEvent(day_of_week=day_of_week, event_name=name, start_time=start, end_time=end, user_id=current_user.id))
            db.session.commit()
            flash(f'Schedule for {date(2000, 1, 3 + day_of_week).strftime("%A")} updated!', 'success')
        return redirect(url_for('profile'))

    schedule = WeeklyScheduleEvent.query.filter_by(user_id=current_user.id).order_by(WeeklyScheduleEvent.day_of_week, WeeklyScheduleEvent.start_time).all()
    hobbies = Hobby.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', schedule=schedule, hobbies=hobbies)

@app.route('/chatbot')
@login_required
def chatbot():
    return render_template('chatbot.html')

@app.route('/add-data', methods=['POST'])
@login_required
def add_data():
    try:
        form_date = date.fromisoformat(request.form['date'])
        if int(request.form['steps']) < 0 or float(request.form['sleep']) < 0 or int(request.form['heart_rate']) < 0 or int(request.form['calories_burned']) < 0:
             flash('All health metrics must be positive numbers.', 'error'); return redirect(url_for('dashboard'))
        data = HealthData.query.filter_by(user_id=current_user.id, date=form_date).first()
        if not data: data = HealthData(user_id=current_user.id, date=form_date); db.session.add(data)
        data.steps = int(request.form['steps']); data.sleep = float(request.form['sleep']); data.heart_rate = int(request.form['heart_rate']); data.calories_burned = int(request.form['calories_burned']); data.mood = request.form['mood']
        flash('Data logged successfully!', 'success'); db.session.commit()
    except Exception as e: db.session.rollback(); flash(f'Error logging data: {e}', 'error')
    return redirect(url_for('dashboard'))

@app.route('/log-water', methods=['POST'])
@login_required
def log_water():
    try:
        water_amount = int(request.form['water_amount'])
        if water_amount <= 0:
            flash('Please enter a positive amount of water.', 'error'); return redirect(url_for('nutrition'))
        today_data = HealthData.query.filter_by(user_id=current_user.id, date=date.today()).first()
        if not today_data:
            today_data = HealthData(user_id=current_user.id, date=date.today()); db.session.add(today_data)
        today_data.water_intake_ml += water_amount
        db.session.commit(); flash(f'Added {water_amount}ml of water to your log!', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Error logging water: {e}', 'error')
    return redirect(url_for('nutrition'))

@app.route('/delete-food/<int:log_id>')
@login_required
def delete_food(log_id):
    food_log = db.session.get(FoodLog, log_id)
    if food_log and food_log.user_id == current_user.id:
        db.session.delete(food_log); db.session.commit()
        flash('Food log entry deleted.', 'success')
    return redirect(url_for('nutrition'))

@app.route('/simulate-day')
@login_required
def simulate_day():
    last_data = HealthData.query.filter_by(user_id=current_user.id).order_by(HealthData.date.desc()).first()
    new_date = (last_data.date + timedelta(days=1)) if last_data else date.today()
    if HealthData.query.filter_by(user_id=current_user.id, date=new_date).first():
        flash(f'Data for {new_date.strftime("%b %d")} already exists.', 'info'); return redirect(url_for('dashboard'))
    new_data = HealthData(user_id=current_user.id, date=new_date, steps=random.randint(4000, 12000), sleep=round(random.uniform(6.0, 9.0), 1), heart_rate=random.randint(55, 75), calories_burned=random.randint(300, 700))
    db.session.add(new_data); db.session.commit(); flash('A new day has been simulated!', 'success'); return redirect(url_for('dashboard'))
    
@app.route('/api/log-food', methods=['POST'])
@login_required
def log_food():
    food_description = request.form['food_description']
    system_prompt = "You are a nutritional analysis expert. Your task is to estimate the calorie count of a user's meal description. Respond ONLY with a valid JSON object containing a single key: `calories`. Do not include markdown, explanations, or any text outside the JSON. For example, if the user says 'an apple', you should respond with `{\"calories\": 95}`."
    response_str = call_gemini_api(system_prompt, food_description)
    try:
        json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
        if not json_match: raise ValueError("No JSON object found in AI response.")
        calories = int(json.loads(json_match.group())['calories'])
        new_log = FoodLog(user_id=current_user.id, date=date.today(), meal_description=food_description, calories=calories)
        db.session.add(new_log); db.session.commit()
        flash(f'Successfully logged "{food_description}" with an estimated {calories} Calories.', 'success')
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        flash(f'The AI could not analyze that meal. Error: {e}', 'error')
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
    app.run(debug=True, port=8081)

