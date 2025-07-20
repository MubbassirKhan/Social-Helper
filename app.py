from flask import Flask, render_template, jsonify, request
from werkzeug.security import generate_password_hash
from db import get_connection  # Handles DB creation and connection

app = Flask(__name__)

# ✅ Connect to DB when app starts (at launch)
initial_conn = get_connection()
if initial_conn:
    initial_conn.close()

@app.route("/")
def index():
    conn = get_connection()
    result = []

    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT datname FROM pg_database;")  # Example query
            result = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            result = [("Error:", str(e))]

    return render_template("index.html", databases=result)



@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json()
    required_fields = ['name', 'phone_number', 'email', 'city', 'password', 'address']

    # Validate input
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    hashed_password = generate_password_hash(data['password'])

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users (name, phone_number, email, city, password, address)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING uid;
        """, (
            data['name'],
            data['phone_number'],
            data['email'],
            data['city'],
            hashed_password,
            data['address']
        ))

        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "User registered successfully", "user_id": user_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500



import uuid
import time
from flask import Flask, request, jsonify, session, make_response
from werkzeug.security import check_password_hash
from db import get_connection
from datetime import timedelta


app.secret_key = 'your_super_secret_key'
app.permanent_session_lifetime = timedelta(seconds=300)

# In-memory token store: {token: expiry_timestamp}
token_store = {}

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT uid, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user[1], password):
            session.permanent = True
            session['user_id'] = user[0]

            # Generate token and set expiry for 10 seconds
            token = str(uuid.uuid4())
            token_store[token] = time.time() + 1000

            resp = make_response(jsonify({
                "message": "Login successful",
                "token": token,
                "user_id": user[0]
            }))
            resp.set_cookie("user_id", str(user[0]), max_age=30)
            return resp
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/logout", methods=["GET", "POST"])
def logout():
    user_id = session.pop('user_id', None)

    # Optional: clear token if you store it per session
    token = request.headers.get("Authorization")  # Or however you're passing the token
    if token and token in token_store:
        del token_store[token]

    resp = make_response(jsonify({
        "message": "Logged out successfully",
        "user_id": user_id
    }))
    resp.delete_cookie("user_id")

    return resp, 200

@app.context_processor
def inject_user():
    user = None
    if 'user_id' in session:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM users WHERE uid = %s", (session['user_id'],))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                user = {'name': row[0]}
        except:
            pass
    return dict(user=user)

@app.route("/verify-token", methods=["POST"])
def verify_token():
    data = request.get_json()
    token = data.get("token")

    if not token:
        return jsonify({"error": "Token required"}), 400

    expiry = token_store.get(token)
    current_time = time.time()

    if expiry and current_time < expiry:
        return jsonify({"message": "Token is valid ✅"}), 200
    else:
        return jsonify({"error": "Token is invalid or expired ❌"}), 401


@app.route("/book-doctor", methods=["POST"])
def book_doctor():
    if 'user_id' not in session:
        return jsonify({"error": "User not logged in"}), 401

    data = request.get_json()
    required_fields = ['did', 'visit_date', 'patient_age', 'gender', 'description']

    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    try:
        uid = session['user_id']
        did = data['did']

        conn = get_connection()
        cursor = conn.cursor()

        # Insert appointment into book_dr
        cursor.execute("""
            INSERT INTO book_dr (uid, did, visit_date, patient_age, gender, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING bid;
        """, (
            uid,
            did,
            data['visit_date'],
            data['patient_age'],
            data['gender'],
            data['description']
        ))

        booking_id = cursor.fetchone()[0]

        # Fetch the doctor name (assuming it's in users table by uid)
        cursor.execute("SELECT name FROM users WHERE uid = %s", (did,))
        doctor_row = cursor.fetchone()
        doctor_name = doctor_row[0] if doctor_row else "Unknown Doctor"

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Doctor appointment booked successfully",
            "booking_id": booking_id,
            "doctor_name": doctor_name
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-doctors")
def get_doctors():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT did, name FROM doctors")
    doctors = [{"uid": row[0], "name": row[1]} for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(doctors)


from flask import Flask, render_template, request, redirect, url_for, session, jsonify

# --- User Dashboard Route ---
from collections import namedtuple

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    conn = get_connection()
    cursor = conn.cursor()
    uid = session['user_id']

    # Handle profile update
    if request.method == 'POST':
        data = request.get_json()
        cursor.execute("""
            UPDATE users
            SET name=%s, phone_number=%s, email=%s, city=%s, state=%s, address=%s
            WHERE uid=%s
        """, (
            data['name'], data['phone_number'], data['email'],
            data['city'], data['state'], data['address'], uid
        ))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Profile updated successfully'}), 200

    # Fetch user details
    cursor.execute("SELECT uid, name, phone_number, email, city, state, address FROM users WHERE uid = %s", (uid,))
    row = cursor.fetchone()

    user = None
    if row:
        User = namedtuple('User', ['uid', 'name', 'phone_number', 'email', 'city', 'state', 'address'])
        user = User._make(row)

    # Fetch appointments
    cursor.execute("""
        SELECT b.bid, b.booked_at, b.visit_date, b.patient_age, b.gender, b.description, b.status,
               d.name AS doctor_name, d.specialization
        FROM book_dr b
        LEFT JOIN doctors d ON b.did = d.did
        WHERE b.uid = %s
        ORDER BY b.booked_at DESC
    """, (uid,))
    rows = cursor.fetchall()

    # Convert appointment rows to dicts
    bookings = []
    for row in rows:
        booking = {
            'bid': row[0],
            'booked_at': row[1],
            'visit_date': row[2].strftime("%Y-%m-%d"),
            'patient_age': row[3],
            'gender': row[4],
            'description': row[5],
            'status': row[6],
            'doctor_name': row[7],
            'specialization': row[8]
        }
        bookings.append(booking)

    cursor.close()
    conn.close()
    return render_template('users/dashboard.html', user=user, bookings=bookings)


@app.route("/register", methods=["GET"])
def register():
    return render_template("users/register.html")



@app.route("/about", methods=["GET"])
def about():
    return render_template("about.html")

@app.route("/login-page")
def login_page():
    return render_template("login.html")

@app.route("/splogin")
def splogin():
    return render_template("splogin.html")

@app.route("/book-doctor-form", methods=["GET"])
def book_doctor_form():
    return render_template("users/book_doctor.html")




















# DOCTOR ROUTES

import base64

from psycopg2 import IntegrityError

@app.route("/register-doctor", methods=["POST"])
def register_doctor():
    data = request.get_json()
    required_fields = ['name', 'specialization', 'email', 'phone_number', 'password', 'license']

    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    try:
        license_base64 = data['license']
        hashed_password = generate_password_hash(data['password'])

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO doctors (name, specialization, email, phone_number, password, license_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING did;
        """, (
            data['name'],
            data['specialization'],
            data['email'],
            data['phone_number'],
            hashed_password,
            license_base64
        ))

        doctor_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Doctor registered successfully", "doctor_id": doctor_id}), 201

    except IntegrityError:
        conn.rollback()
        return jsonify({"error": "Doctor already registered with this email or phone number"}), 409

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/login-doctor", methods=["POST"])
def login_doctor():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Fetch doctor details including status
        cursor.execute(
            "SELECT did, password, status FROM doctors WHERE email = %s",
            (email,)
        )
        doctor = cursor.fetchone()

        cursor.close()
        conn.close()

        if not doctor:
            return jsonify({"error": "Invalid email or password"}), 401

        doctor_id, hashed_password, status = doctor

        if status != 'active':
            return jsonify({"error": "Your account will be activated within 42 hours. Please wait."}), 403


        if check_password_hash(hashed_password, password):
            session.permanent = True
            session['doctor_id'] = doctor_id
            return jsonify({"message": "Login successful", "doctor_id": doctor_id}), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/doctor/dashboard")
def doctor_dashboard():
    doctor_id = session.get('doctor_id')

    if not doctor_id:
        return redirect(url_for('login'))

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Fetch doctor details
        cursor.execute("""
            SELECT name, specialization, email, phone_number 
            FROM doctors 
            WHERE did = %s
        """, (doctor_id,))
        row = cursor.fetchone()

        if not row:
            return redirect(url_for('login'))  # doctor not found, force logout

        doctor = {
            "name": row[0],
            "specialization": row[1],
            "email": row[2],
            "phone_number": row[3],
            "city": "Not provided",     # Optional: add city/state/address to DB
            "state": "Not provided",
            "address": "Not provided"
        }

        # Fetch appointments with patient info
        cursor.execute("""
            SELECT u.name AS patient_name, b.visit_date, b.description, b.status
            FROM book_dr b
            JOIN users u ON u.uid = b.uid
            WHERE b.did = %s
            ORDER BY b.visit_date ASC;
        """, (doctor_id,))

        appointments = []
        for row in cursor.fetchall():
            appointments.append({
                "patient": row[0],
                "date": row[1].strftime("%Y-%m-%d"),
                "time": "10:00 AM",  # optional: add actual time field
                "reason": row[2],
                "status": row[3]
            })

        cursor.close()
        conn.close()

        return render_template("doctor/dashboard.html", doctor=doctor, appointments=appointments)

    except Exception as e:
        print("Dashboard Error:", e)
        return "Something went wrong. Please try again later.", 500


@app.route("/doctor/home")
def doctor_home():
    doctor_id = session.get('doctor_id')

    if not doctor_id:
        return redirect(url_for('login'))

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Fetch doctor details
        cursor.execute("""
            SELECT name, specialization, email, phone_number 
            FROM doctors 
            WHERE did = %s
        """, (doctor_id,))
        row = cursor.fetchone()

        if not row:
            return redirect(url_for('login'))

        doctor = {
            "name": row[0],
            "specialization": row[1],
            "email": row[2],
            "phone_number": row[3],
            "city": "Not provided",
            "state": "Not provided",
            "address": "Not provided"
        }

        # Fetch appointments
        cursor.execute("""
            SELECT u.name AS patient_name, b.visit_date, b.description, b.status
            FROM book_dr b
            JOIN users u ON u.uid = b.uid
            WHERE b.did = %s
            ORDER BY b.visit_date ASC;
        """, (doctor_id,))

        appointments = []
        for row in cursor.fetchall():
            appointments.append({
                "patient": row[0],
                "date": row[1].strftime("%Y-%m-%d"),
                "time": "10:00 AM",
                "reason": row[2],
                "status": row[3]
            })

        cursor.close()
        conn.close()

        # Return only the component
        return render_template("doctor/home.html", doctor=doctor, appointments=appointments)

    except Exception as e:
        print("Home Load Error:", e)
        return "Error loading home.", 500


@app.route("/logout-doctor", methods=["GET", "POST"])
def logout_doctor():
    session.pop('doctor_id', None)
    return redirect(url_for('splogin'))  # Replace 'doctor_login' with your actual login route


@app.route("/doctor/appointments", methods=["GET", "POST"])
def doctor_appointments():
    doctor_id = session.get('doctor_id')
    if not doctor_id:
        return redirect(url_for('login'))

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if request.method == "POST":
            data = request.get_json()
            bid = data.get("bid")
            new_status = data.get("status")

            if not bid or new_status not in ["Approved", "Rejected", "Completed"]:
                return jsonify({"error": "Invalid input"}), 400

            cursor.execute("""
                UPDATE book_dr SET status = %s WHERE bid = %s AND did = %s
            """, (new_status, bid, doctor_id))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({"message": f"Appointment {bid} status updated to {new_status}"}), 200

        # GET: Load appointments
        cursor.execute("""
            SELECT b.bid, u.name, b.visit_date, b.description, b.status
            FROM book_dr b
            JOIN users u ON u.uid = b.uid
            WHERE b.did = %s
            ORDER BY b.visit_date ASC;
        """, (doctor_id,))
        appointments = []
        for row in cursor.fetchall():
            appointments.append({
                "bid": row[0],
                "patient": row[1],
                "date": row[2].strftime("%Y-%m-%d"),
                "reason": row[3],
                "status": row[4]
            })

        cursor.close()
        conn.close()
        return render_template("doctor/appointments.html", appointments=appointments)

    except Exception as e:
        print("Appointments Error:", e)
        return "Error loading appointments.", 500

from datetime import datetime

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow}  # <-- notice NO parentheses


from werkzeug.security import check_password_hash, generate_password_hash

@app.route("/doctor/profile", methods=["GET", "POST"])
def doctor_profile():
    doctor_id = session.get("doctor_id")
    if not doctor_id:
        return redirect(url_for("login_doctor"))

    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        data = request.form
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone_number")
        specialization = data.get("specialization")
        old_password = data.get("old_password")
        new_password = data.get("new_password")

        try:
            if old_password and new_password:
                cursor.execute("SELECT password FROM doctors WHERE did = %s", (doctor_id,))
                stored_password = cursor.fetchone()[0]

                if not check_password_hash(stored_password, old_password):
                    return "Old password is incorrect", 400

                hashed = generate_password_hash(new_password)
                cursor.execute("UPDATE doctors SET password = %s WHERE did = %s", (hashed, doctor_id))

            # Update other profile details
            cursor.execute("""
                UPDATE doctors SET name=%s, email=%s, phone_number=%s, specialization=%s
                WHERE did=%s
            """, (name, email, phone, specialization, doctor_id))

            conn.commit()
        except Exception as e:
            print("Update Error:", e)
            return "Update failed", 500

    # Fetch doctor data
    cursor.execute("SELECT name, email, phone_number, specialization FROM doctors WHERE did = %s", (doctor_id,))
    doctor = cursor.fetchone()

    # Fetch appointment history
    cursor.execute("""
        SELECT u.name, b.visit_date, b.description, b.status
        FROM book_dr b
        JOIN users u ON u.uid = b.uid
        WHERE b.did = %s
        ORDER BY b.visit_date DESC;
    """, (doctor_id,))
    history = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("doctor/profile.html", doctor=doctor, history=history)














############## Admin Routes ##############

from flask import request, session, redirect, url_for, render_template, jsonify

@app.route('/admin/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'admin' and password == 'admin':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin/admin_login.html', error='Invalid credentials')
    
    # If GET request, show login form
    return render_template('admin/admin_login.html')


@app.route('/admin/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route("/admin/admin_dashboard")
def admin_dashboard():
    if 'admin_logged_in' not in session:
        return redirect("/admin/admin_login")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM doctors")
    total_doctors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM book_dr")
    total_appointments = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return render_template("admin/admin_dashboard.html",
                            total_doctors=total_doctors,
                            total_users=total_users,
                            total_appointments=total_appointments,
                            last_login="Today",
                            last_backup="July 19, 2025",
                            pending_verifications=3,
                            new_feedback_count=5)
    
from psycopg2.extras import RealDictCursor

@app.route("/admin/manage-doctors")
def admin_manage_doctors():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT did, name, email, specialization, phone_number, status, license_id FROM doctors")
    doctors = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin/manage_doctors.html", doctors=doctors)

@app.route("/admin/update_doctor_status", methods=["POST"])
def update_doctor_status():
    data = request.get_json()
    did = data.get("doctor_id")
    new_status = data.get("status")

    if not did or not new_status:
        return jsonify({"error": "Missing data"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE doctors SET status = %s WHERE did = %s", (new_status, did))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Doctor status updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
import psycopg2.extras
from flask import request, jsonify, render_template
import psycopg2.extras

# Render Admin Management Page
@app.route("/admin/manage-users")
def admin_manage_users():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Fetch users
    cursor.execute("""
        SELECT uid, name, phone_number, email, city, state, address 
        FROM users
    """)
    users = cursor.fetchall()

    # Fetch appointments
    cursor.execute("""
        SELECT b.bid, b.uid, b.visit_date, b.status, b.gender, b.patient_age, b.description,
               d.name AS doctor_name, u.name AS user_name
        FROM book_dr b
        JOIN users u ON u.uid = b.uid
        LEFT JOIN doctors d ON d.did = b.did
        ORDER BY b.booked_at DESC
    """)
    appointments = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/manage_users.html", users=users, appointments=appointments)

# === USER ROUTES ===

@app.route("/admin/delete-user/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE uid = %s", (uid,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "User deleted"}), 200

@app.route("/admin/update-user/<int:uid>", methods=["PUT"])
def update_user(uid):
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET name = %s,
            email = %s,
            phone_number = %s,
            city = %s,
            state = %s,
            address = %s
        WHERE uid = %s
    """, (
        data.get("name"), data.get("email"), data.get("phone_number"),
        data.get("city"), data.get("state"), data.get("address"),
        uid
    ))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "User updated"}), 200

# === APPOINTMENT ROUTES ===

@app.route("/admin/delete-appointment/<int:bid>", methods=["DELETE"])
def delete_appointment(bid):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM book_dr WHERE bid = %s", (bid,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Appointment deleted"}), 200

@app.route("/admin/update-appointment/<int:bid>", methods=["PUT"])
def update_appointment(bid):
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE book_dr
        SET visit_date = %s,
            gender = %s,
            patient_age = %s,
            description = %s,
            status = %s
        WHERE bid = %s
    """, (
        data.get("visit_date"), data.get("gender"),
        data.get("patient_age"), data.get("description"),
        data.get("status"), bid
    ))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Appointment updated"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

