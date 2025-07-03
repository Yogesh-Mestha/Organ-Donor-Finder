from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import pandas as pd
from knn_model import find_matching_donors
import csv
import os



app = Flask(__name__)
app.secret_key = 'c2d5a39524191844122b15c63e04a387e692a2be0074997dd7d9c135251b9067'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost:3306/donor_dbase'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --- MODELS ---------------------------------------------------
class Patient(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    pw_hash  = db.Column(db.String(128), nullable=False)
    name     = db.Column(db.String(120), nullable=False)
    age      = db.Column(db.Integer, nullable=False)
    phone    = db.Column(db.String(20), nullable=False)

class Request(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    patient_id     = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    hospital_name  = db.Column(db.String(120), nullable=False)    # <-- was a FK
    donor_name     = db.Column(db.String(255), nullable=False)
    blood_type     = db.Column(db.String(50))
    organ_type     = db.Column(db.String(50))
    hla_typing     = db.Column(db.String(100))
    bmi            = db.Column(db.Float)
    city           = db.Column(db.String(100))
    state          = db.Column(db.String(100))
    status         = db.Column(db.String(20), default='Pending')

class Hospital(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(120), unique=True, nullable=False)
    pw_hash  = db.Column(db.String(128), nullable=False)


# Preload donor CSV for search dropdowns
donor_df        = pd.read_csv('donor_data.csv')
states          = sorted(donor_df['State'].dropna().unique())
hospital_names = sorted(donor_df['Hospital'].dropna().unique())
cities_by_state = { s: sorted(donor_df[donor_df['State']==s]['City'].dropna().unique())
                    for s in states }

# --- ROUTES ---------------------------------------------------
@app.route('/')
def home():
    return render_template('home.html')

# ---- Patient Auth & Dashboard --------------------------------
@app.route('/patient/register', methods=['GET','POST'])
def patient_register():
    if request.method=='POST':
        u = request.form
        if Patient.query.filter_by(username=u['username']).first():
            flash('Username taken','danger')
        else:
            pw_hash = bcrypt.generate_password_hash(u['password']).decode()
            p = Patient(
                username=u['username'], pw_hash=pw_hash,
                name=u['name'], age=int(u['age']), phone=u['phone']
            )
            db.session.add(p); db.session.commit()
            flash('Registered successfully','success')
            return redirect(url_for('patient_login'))
    return render_template('patient_register.html')

@app.route('/patient/login', methods=['GET','POST'])
def patient_login():
    if request.method=='POST':
        p = Patient.query.filter_by(username=request.form['username']).first()
        if p and bcrypt.check_password_hash(p.pw_hash, request.form['password']):
            session.clear()
            session['user_type']='patient'
            session['user_id']=p.id
            return redirect(url_for('patient_dashboard'))
        flash('Invalid credentials','danger')
    return render_template('patient_login.html')

@app.route('/patient/dashboard')
def patient_dashboard():
    if session.get('user_type')!='patient': return redirect(url_for('patient_login'))
    p = Patient.query.get(session['user_id'])
    return render_template('patient_dashboard.html', patient=p)

# ---- Donor Search & Request ----------------------------------
@app.route('/patient/search', methods=['GET'])
def search():
    if session.get('user_type')!='patient': return redirect(url_for('patient_login'))
    return render_template('search.html', states=states, cities_by_state=cities_by_state)

@app.route('/patient/find', methods=['POST'])
def find_donor():
    data = {
        'Blood Type': request.form['blood_type'],
        'HLA Typing': request.form['hla_typing'],
        'Organ Type': request.form['organ_type'],
        'BMI': float(request.form['bmi']),
        'Age': int(request.form['age']),
        'State': request.form['state'],
        'City': request.form['city']
    }
    matches = find_matching_donors(data, k=10)
    return render_template('results.html', matches=matches)

@app.route('/patient/request', methods=['POST'])
def patient_request():
    if session.get('user_type')!='patient':
        return redirect(url_for('patient_login'))

    di = request.form.to_dict()
    # ‘Hospital’ here comes from your KNN match’s hidden input
    hosp_name = di['Hospital']

    req = Request(
        patient_id    = session['user_id'],
        hospital_name = hosp_name,
        donor_name    = di['Name'],
        blood_type    = di['Blood_Type'],
        organ_type    = di['Organ_Type'],
        hla_typing    = di['HLA_Typing'],
        bmi           = float(di['BMI']),
        city          = di['City'],
        state         = di['State']
    )
    db.session.add(req)
    db.session.commit()

    flash(f"Request sent to {hosp_name}", 'success')
    return redirect(url_for('search'))


@app.route('/patient/track')
def track_requests():
    if session.get('user_type')!='patient':
        return redirect(url_for('patient_login'))

    # Fetch all requests for this patient—no join needed
    reqs = Request.query.filter_by(patient_id=session['user_id']) \
                        .order_by(Request.id.desc()) \
                        .all()

    return render_template('track_request.html', requests=reqs)


@app.route('/hospital/login', methods=['GET','POST'])
def hospital_login():
    if request.method=='POST':
        uname = request.form['username']
        pwd   = request.form['password']
        hospital = Hospital.query.filter_by(name=uname).first()
        if hospital and bcrypt.check_password_hash(hospital.pw_hash, pwd):
            session.clear()
            session['user_type']     = 'hospital'
            session['hospital_name'] = hospital.name
            session['hospital_id']   = hospital.id
            return redirect(url_for('hospital_dashboard'))
        flash('Invalid username or password','danger')
    return render_template('hospital_login.html')


@app.route('/hospital/dashboard')
def hospital_dashboard():
    if session.get('user_type')!='hospital':
        return redirect(url_for('hospital_login'))
    return render_template('hospital_dashboard.html',hospital_name=session['hospital_name'])

@app.route('/hospital/add_donor', methods=['GET','POST'])
def add_donor():
    # … authentication check …

    if request.method=='POST':
        new = {
          'Name':       request.form['donor_name'],
          'Age':        request.form['age'],
          'Gender':       request.form.get('gender', ''),
          'Blood Type':   request.form['blood_type'],
          'Organ Type': request.form['organ_type'],
          'HLA Typing': request.form['hla_typing'],
          'Rh Factor':    request.form.get('rh_factor', 'Positive'),
          'BMI':        request.form['bmi'],
          'Cause of death':request.form['cause_of_death'],
          'health condition':request.form['health_condition'],
          'City':       request.form['city'],
          'State':      request.form['state'],
          'Hospital':   session['hospital_name']
        }

        csv_path = os.path.join(app.root_path, 'donor_data.csv')
        df_new   = pd.DataFrame([new])

        # If file doesn't exist yet, write header; else append without header
        if not os.path.exists(csv_path):
            df_new.to_csv(csv_path, mode='w', header=True, index=False)
        else:
            df_new.to_csv(csv_path, mode='a', header=False, index=False)

        flash('Donor added successfully!', 'success')
        return redirect(url_for('hospital_dashboard'))

    return render_template('add_donor.html')

@app.route('/hospital/requests', methods=['GET','POST'])
def hospital_requests():
    if session.get('user_type') != 'hospital':
        return redirect(url_for('hospital_login'))

    hosp = session['hospital_name']

    if request.method == 'POST':
        req_id = request.form['req_id']
        action = request.form['action']    # either "accept" or "reject"
        new_status = 'Accepted' if action == 'accept' else 'Rejected'

        r = Request.query.get(int(req_id))
        if r and r.hospital_name == hosp:
            r.status = new_status
            db.session.commit()
            flash(f"Request #{req_id} marked {new_status}.", 'success')
        else:
            flash("Invalid request or permission denied.", 'danger')

        return redirect(url_for('hospital_requests'))

    # GET: show all requests for this hospital
    reqs = Request.query.filter_by(hospital_name=hosp).order_by(Request.id.desc()).all()
    return render_template('hospital_requests.html', requests=reqs)
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__=='__main__':
      # ensure models are created before serving requests
    with app.app_context():
        db.drop_all()       # ← drop every table
        db.create_all()   


        for hname in hospital_names:
            if not Hospital.query.filter_by(name=hname).first():
                # password = hospital name
                pw_hash = bcrypt.generate_password_hash(hname).decode('utf-8')
                db.session.add(Hospital(name=hname, pw_hash=pw_hash))
        db.session.commit()

    app.run(debug=True)
