import os
from datetime import date, datetime  # Added datetime import
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory,jsonify
import mysql.connector
import hashlib
import config  # Your DB config here
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads/assignments'
RESOURCE_FOLDER = 'uploads/resources'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'ppt', 'pptx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESOURCE_FOLDER'] = RESOURCE_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(RESOURCE_FOLDER):
    os.makedirs(RESOURCE_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME
    )

def hash_password_sha1(password):
    return hashlib.sha1(password.encode('utf-8')).hexdigest()

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                print("User not logged in")
                return redirect(url_for('login'))
            user_role = session.get('role')
            print(f"User role: {user_role}, Allowed roles: {roles}")
            if user_role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        username = request.form['username']
        email = request.form['email']
        birth_date = request.form['birth_date']  # YYYY-MM-DD
        sexe = request.form['sexe']
        password = request.form['password']
        role = int(request.form['role'])  # 2=Teacher, 3=Student

        hashed_pw = hash_password_sha1(password)
        registration_date = date.today()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO Users 
                (Name, Surname, Username, Email, Birth_date, Registration_date, Password, Role, Sexe)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (name, surname, username, email, birth_date, registration_date, hashed_pw, role, sexe))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.errors.IntegrityError as e:
            flash(f'Error: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        input_hash = hash_password_sha1(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ID, Password, Role FROM Users WHERE Username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            flash("User not found.", "danger")
            return redirect(url_for('login'))

        user_id, stored_hash, role = user

        if input_hash == stored_hash:
            session['user_id'] = user_id
            session['username'] = username
            session['role'] = int(role)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect password.', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/dashboard')
@role_required(1, 2, 3)
def dashboard():
    user_id = session.get('user_id')
    role = session.get('role')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Polls")
    poll_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Quizzes")
    quiz_count = cursor.fetchone()[0]

    if role == 1 or role == 2:
        cursor.execute("SELECT COUNT(*) FROM Users")
        user_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Assignment_Submissions")
        assignment_submissions = cursor.fetchone()[0]

        return render_template(
            'dashboard.html',
            poll_count=poll_count,
            quiz_count=quiz_count,
            user_count=user_count,
            assignment_submissions=assignment_submissions,
            username=session.get('username')
        )

    elif role == 3:
        cursor.execute("SELECT COUNT(*) FROM Quiz_Attempts WHERE user_id = %s", (user_id,))
        student_attempts = cursor.fetchone()[0]

         # Get assignment submissions for student
        cursor.execute("SELECT COUNT(*) FROM Assignment_Submissions WHERE student_id = %s", (user_id,))
        student_assignments = cursor.fetchone()[0]

        return render_template(
            'dashboard.html',
            poll_count=poll_count,
            quiz_count=quiz_count,
            student_attempts=student_attempts,
            student_assignments=student_assignments,
            username=session.get('username')
        )




@app.route('/admin/dashboard')
@role_required(1)
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM quizzes")
    quiz_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM forums")
    forum_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM assignments")
    assignment_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM polls")
    poll_count = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return render_template('admin_dashboard.html',
                           user_count=user_count,
                           quiz_count=quiz_count,
                           forum_count=forum_count,
                           poll_count=poll_count,
                           assignment_count=assignment_count,)

@app.route('/admin/manage/teachers')
@role_required(1)
def admin_manage_teachers():
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        cursor.execute("""
            SELECT ID, Name, Username, Email, Registration_date
            FROM Users
            WHERE Role = 2 AND (Name LIKE %s OR Username LIKE %s)
        """, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT ID, Name, Username, Email, Registration_date FROM Users WHERE Role = 2")

    teachers = cursor.fetchall()
    conn.close()
    return render_template('admin_manage_teachers.html', teachers=teachers)


@app.route('/admin/manage/students')
@role_required(1)
def admin_manage_students():
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:
        cursor.execute("""
            SELECT ID, Name, Username, Email, Registration_date
            FROM Users
            WHERE Role = 3 AND (Name LIKE %s OR Username LIKE %s)
        """, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("""
            SELECT ID, Name, Username, Email, Registration_date
            FROM Users
            WHERE Role = 3
        """)

    students = cursor.fetchall()
    conn.close()
    return render_template('admin_manage_students.html', students=students)


@app.route('/admin/delete/<int:user_id>', methods=['POST'])
@role_required(1)
def delete_user(user_id):
    print(f"Received request to delete user ID: {user_id}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check user exists and is a student
        cursor.execute("SELECT Role FROM Users WHERE ID = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            print("User not found.")
            return jsonify({'status': 'error', 'message': 'User not found.'}), 404
        role = row[0]
        if role != 3:
            print(f"User role is {role}, not student. Cannot delete.")
            return jsonify({'status': 'error', 'message': 'User is not a student.'}), 403
        
        cursor.execute("DELETE FROM Users WHERE ID = %s", (user_id,))
        conn.commit()
        deleted_rows = cursor.rowcount
        cursor.close()
        conn.close()
        print(f"Deleted rows count: {deleted_rows}")

        if deleted_rows == 0:
            return jsonify({'status': 'error', 'message': 'Delete failed.'}), 500

        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print('Exception:', e)
        return jsonify({'status': 'error', 'message': str(e)}), 500






@app.route('/teacher_forum')
@role_required(2)  # only Teacher
def teacher_forum():
    # teacher forum code
    return render_template('teacher_forum.html')

@app.route('/forums')
@role_required(1, 2, 3)
def forums():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
        f.Subject AS subject,
        f.Title AS title,
        f.Content AS content,
        f.Timestamp AS timestamp,
        u.Username AS username
    FROM Forums f
    JOIN Users u ON f.UserID = u.ID
    ORDER BY f.Timestamp DESC
""")

    posts = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('forums.html', posts=posts)

@app.route('/forums/new', methods=['GET', 'POST'])
@role_required(1,2)
def new_forum_post():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        subject = request.form['subject']
        title = request.form['title']
        content = request.form['content']
        user_id = session['user_id']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Forums (Subject, Title, Content, UserID) VALUES (%s, %s, %s, %s)",
                       (subject, title, content, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Post created successfully!', 'success')
        return redirect(url_for('forums'))

    return render_template('new_forum_post.html')

@app.route('/assignments/create', methods=['GET', 'POST'])
@role_required(1,2)  # Teacher only
def create_assignment():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date']
        course_id = None  # placeholder

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO assignments (title, description, due_date, course_id)
            VALUES (%s, %s, %s, %s)
        ''', (title, description, due_date, course_id))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Assignment created successfully!', 'success')
        return redirect(url_for('teacher_assignments'))

    return render_template('create_assignment.html')

@app.route('/assignments/teacher')
@role_required(1,2)
def teacher_assignments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM assignments ORDER BY due_date DESC')
    assignments = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('teacher_assignments.html', assignments=assignments)

@app.route('/assignments')
@role_required(3)
def assignments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM assignments ORDER BY due_date DESC')
    assignments = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('assignments.html', assignments=assignments)

@app.route('/assignments/<int:assignment_id>/submit', methods=['GET', 'POST'])
@role_required(3)
def submit_assignment(assignment_id):
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            user_id = session['user_id']
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{user_id}_{assignment_id}_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT id FROM assignment_submissions
                WHERE assignment_id=%s AND student_id=%s
            ''', (assignment_id, user_id))
            existing = cursor.fetchone()

            now = datetime.now()

            if existing:
                cursor.execute('''
                    UPDATE assignment_submissions
                    SET file=%s, submitted_at=%s
                    WHERE id=%s
                ''', (filename, now, existing[0]))
            else:
                cursor.execute('''
                    INSERT INTO assignment_submissions (assignment_id, student_id, file, submitted_at)
                    VALUES (%s, %s, %s, %s)
                ''', (assignment_id, user_id, filename, now))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Assignment submitted successfully!', 'success')
            return redirect(url_for('assignments'))

        else:
            flash('File type not allowed', 'danger')
            return redirect(request.url)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM assignments WHERE id=%s', (assignment_id,))
    assignment = cursor.fetchone()
    cursor.close()
    conn.close()

    if not assignment:
        flash('Assignment not found', 'danger')
        return redirect(url_for('assignments'))

    return render_template('submit_assignment.html', assignment=assignment)

@app.route('/assignments/<int:assignment_id>/submissions')
@role_required(1,2)
def view_submissions(assignment_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT s.id, s.file, s.submitted_at, u.Username, u.Name, u.Surname
        FROM assignment_submissions s
        JOIN Users u ON s.student_id = u.ID
        WHERE s.assignment_id = %s
        ORDER BY s.submitted_at DESC
    ''', (assignment_id,))
    submissions = cursor.fetchall()

    cursor.execute('SELECT * FROM assignments WHERE id=%s', (assignment_id,))
    assignment = cursor.fetchone()

    cursor.close()
    conn.close()

    if not assignment:
        flash('Assignment not found', 'danger')
        return redirect(url_for('teacher_assignments'))

    return render_template('view_submissions.html', submissions=submissions, assignment=assignment)

@app.route('/uploads/assignments/<filename>')
def uploaded_file(filename):
    # Added send_from_directory import to serve files
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/resources', methods=['GET', 'POST'])
@role_required(1, 2, 3)
def resources():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST' and session['role'] == 2:
        description = request.form['description']
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['RESOURCE_FOLDER'], filename)
            file.save(filepath)

            cursor.execute('''
                INSERT INTO resources (filename, uploaded_by, description)
                VALUES (%s, %s, %s)
            ''', (filename, session['user_id'], description))
            conn.commit()
            flash("Resource uploaded successfully!", "success")
        else:
            flash("Invalid file type", "danger")

    cursor.execute('''
        SELECT r.*, u.Username 
        FROM resources r 
        JOIN Users u ON r.uploaded_by = u.ID
        ORDER BY upload_time DESC
    ''')
    resources = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('resources.html', resources=resources, role=session['role'])

@app.route('/uploads/resources/<filename>')
def download_resource(filename):
    return send_from_directory(app.config['RESOURCE_FOLDER'], filename, as_attachment=True)

@app.route('/delete-resource', methods=['POST'])
def delete_resource():
    if 'role' not in session or session['role'] != 2:  # Only teachers allowed
        flash("Unauthorized action.", "error")
        return redirect(url_for('resources'))

    resource_id = request.form.get('resource_id')
    if not resource_id:
        flash("Invalid resource ID.", "error")
        return redirect(url_for('resources'))

    # Example DB deletion logic (adapt to your DB setup)
    conn = get_db_connection()
    cur = conn.cursor()

    # Optionally: check ownership or permissions here
    cur.execute("DELETE FROM resources WHERE id = %s AND uploaded_by = %s", (resource_id,))
    conn.commit()
    cur.close()
    conn.close()

    flash("Resource deleted successfully.", "success")
    return redirect(url_for('resources'))

@app.route('/polls')
def polls():
    user_id = session.get('user_id')
    user_role = session.get('role')  # Assuming you store role in session on login
    
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.question, po.id AS option_id, po.option_text 
        FROM polls p 
        JOIN poll_options po ON p.id = po.poll_id
        ORDER BY p.created_at DESC
    """)
    rows = cur.fetchall()

    polls = {}
    for row in rows:
        poll_id, question, option_id, option_text = row
        if poll_id not in polls:
            polls[poll_id] = {
                "question": question,
                "options": []
            }
        polls[poll_id]["options"].append({
            "id": option_id,
            "text": option_text
        })

    cur.close()
    conn.close()

    return render_template('polls.html', polls=polls, user_id=user_id, user_role=user_role)


@app.route('/polls/create', methods=['GET', 'POST'])
def create_poll():
    if 'user_id' not in session:
        flash("Please login to create a poll.", "error")
        return redirect(url_for('login')) 

    user_role = session.get('role')
    if user_role not in [1,2]:
        flash("You do not have permission to create polls.", "error")
        return redirect(url_for('polls'))

    if request.method == 'POST':
        question = request.form.get('question')
        options = request.form.getlist('options')  # multiple options with same name

        if not question or not options or any(opt.strip() == "" for opt in options):
            flash("Please enter a question and all options.", "error")
            return redirect(url_for('create_poll'))

        conn = get_db_connection()
        cur = conn.cursor()
# Insert the poll
        cur.execute("""INSERT INTO polls (question, created_by) VALUES (%s, %s)""", (question, session['user_id']))
        poll_id = cur.lastrowid

        # Insert options
        for option_text in options:
            cur.execute("""
                INSERT INTO poll_options (poll_id, option_text) VALUES (%s, %s)
            """, (poll_id, option_text.strip()))

        conn.commit()
        cur.close()
        conn.close()

        flash("Poll created successfully!", "success")
        return redirect(url_for('polls'))

    # GET request: render form
    return render_template('create_poll.html')

@app.route('/polls/vote', methods=['POST'])
def poll_vote():
    if 'user_id' not in session:
        flash("You must be logged in to vote.", "error")
        return redirect(url_for('polls'))

    user_id = session['user_id']
    user_role = session.get('role')

    if user_role != 3:  # 3 means student
        flash("Only students can vote in polls.", "error")
        return redirect(url_for('polls'))

    poll_id = request.form.get('poll_id')
    option_id = request.form.get('option_id')

    if not poll_id or not option_id:
        flash("Invalid vote submission.", "error")
        return redirect(url_for('polls'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Check if user already voted on this poll
    cur.execute("""
      SELECT id FROM poll_votes WHERE poll_id=%s AND user_id=%s
    """, (poll_id, user_id))
    if cur.fetchone():
        flash("You have already voted on this poll.", "warning")
        cur.close()
        conn.close()
        return redirect(url_for('polls'))

    # Insert vote
    cur.execute("""
      INSERT INTO poll_votes (poll_id, option_id, user_id) VALUES (%s, %s, %s)
    """, (poll_id, option_id, user_id))

    conn.commit()
    cur.close()
    conn.close()

    flash("Thank you for voting!", "success")
    return redirect(url_for('poll_results', poll_id=poll_id))


@app.route('/polls/results/<int:poll_id>')
def poll_results(poll_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Get poll question
    cur.execute("SELECT question FROM polls WHERE id=%s", (poll_id,))
    poll = cur.fetchone()
    if not poll:
        flash("Poll not found.", "error")
        cur.close()
        conn.close()
        return redirect(url_for('polls'))

    # Get poll options and vote counts
    cur.execute("""
        SELECT po.id, po.option_text, COUNT(pv.id) as votes
        FROM poll_options po
        LEFT JOIN poll_votes pv ON po.id = pv.option_id
        WHERE po.poll_id = %s
        GROUP BY po.id
        ORDER BY po.id
    """, (poll_id,))
    options = cur.fetchall()

    cur.close()
    conn.close()

    total_votes = sum(vote_count for _, _, vote_count in options) or 1  # avoid division by zero

    return render_template('poll_results.html', poll=poll[0], options=options, total_votes=total_votes)



@app.route('/add_student', methods=['GET', 'POST'])
@role_required(1) 
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        sexe = request.form['sexe']
        birth_date = request.form['birth_date']
        registration_date = datetime.now() 

        hashed_pw = hashlib.sha1(password.encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO Users 
                (Name, Surname, Username, Email, Password, Sexe, Birth_date, Registration_date, Role)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (name, surname, username, email, hashed_pw, sexe, birth_date, registration_date, 3))
            conn.commit()
            flash("✅ Student added successfully!", "success")
        except mysql.connector.IntegrityError:
            flash("❌ Username already exists. Please choose another.", "error")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('add_student'))

    return render_template('add_student.html')



@app.route('/quizzes')
def quizzes():
    user_role = session.get('role')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, description FROM quizzes ORDER BY id DESC")
    quizzes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('quizzes.html', quizzes=quizzes, user_role=user_role)


@app.route('/quizzes/<int:quiz_id>/add_question', methods=['GET', 'POST'])
def add_question(quiz_id):
    user_role = session.get('role')
    if user_role not in [1, 2]:
        flash("You don't have permission to add questions.", "error")
        return redirect(url_for('quizzes'))
    if request.method == 'POST':
        question_text = request.form['question_text']
        options = request.form.getlist('options[]')
        correct_option = int(request.form['correct_option'])

        conn = get_db_connection()
        cur = conn.cursor()

        # Insert question
        cur.execute("INSERT INTO quiz_questions (quiz_id, question_text) VALUES (%s, %s)", (quiz_id, question_text))
        question_id = cur.lastrowid

        # Insert options
        for i, option_text in enumerate(options):
            is_correct = (i == correct_option)
            cur.execute("INSERT INTO quiz_options (question_id, option_text, is_correct) VALUES (%s, %s, %s)",
                        (question_id, option_text, is_correct))
        conn.commit()
        cur.close()
        conn.close()
        flash("Question added successfully.", "success")
        return redirect(url_for('add_question', quiz_id=quiz_id))
    return render_template('add_question.html', quiz_id=quiz_id)


@app.route('/quizzes/<int:quiz_id>/take', methods=['GET'])
def take_quiz(quiz_id):
    user_role = session.get('role')
    if user_role != 3:
        flash("Only students can take quizzes.", "error")
        return redirect(url_for('quizzes'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Get quiz
    cur.execute("SELECT id, title, description FROM quizzes WHERE id=%s", (quiz_id,))
    quiz = cur.fetchone()
    if not quiz:
        flash("Quiz not found.", "error")
        cur.close()
        conn.close()
        return redirect(url_for('quizzes'))

    # Get questions and options
    cur.execute("SELECT id, question_text FROM quiz_questions WHERE quiz_id=%s", (quiz_id,))
    questions_data = cur.fetchall()

    questions = []
    for q in questions_data:
        q_id, q_text = q
        cur.execute("SELECT id, option_text FROM quiz_options WHERE question_id=%s", (q_id,))
        options = cur.fetchall()
        questions.append({
            'id': q_id,
            'text': q_text,
            'options': [{'id': o[0], 'text': o[1]} for o in options]
        })

    cur.close()
    conn.close()

    return render_template('take_quiz.html', quiz={'id': quiz[0], 'title': quiz[1], 'description': quiz[2]}, questions=questions)

@app.context_processor
def inject_user():
    return {
        'username': session.get('username'),
        'user_id': session.get('user_id'),
        'role': session.get('role')
    }

@app.route('/quizzes/<int:quiz_id>/submit', methods=['POST'])
def submit_quiz(quiz_id):
    user_role = session.get('role')
    user_id = session.get('user_id')
    if user_role != 3:
        flash("Only students can submit quizzes.", "error")
        return redirect(url_for('quizzes'))

    raw_answers = request.form.to_dict(flat=False)
    answers_dict = {}

    for key, value in raw_answers.items():
        try:
            q_id = int(key)  # assuming form input names are question IDs
            if isinstance(value, list):
                answers_dict[q_id] = int(value[0])
            else:
                answers_dict[q_id] = int(value)
        except:
            continue

    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch correct answers
    cur.execute("""
        SELECT qq.id, qo.id, qo.is_correct
        FROM quiz_questions qq
        JOIN quiz_options qo ON qq.id = qo.question_id
        WHERE qq.quiz_id=%s
    """, (quiz_id,))
    rows = cur.fetchall()

    correct_answers = {}
    for q_id, option_id, is_correct in rows:
        if is_correct:
            correct_answers[q_id] = option_id

    score = 0
    total_questions = len(correct_answers)

    for q_id, selected_option_id in answers_dict.items():
        if correct_answers.get(q_id) == selected_option_id:
            score += 1

    # Save attempt
    # After score calculation...

# Insert attempt
    cur.execute("""INSERT INTO quiz_attempts (quiz_id, user_id, score, taken_at) VALUES (%s, %s, %s, NOW())""", (quiz_id, user_id, score))
    conn.commit()  # commit so lastrowid works

    attempt_id = cur.lastrowid

# Insert answers for the attempt
    for q_id, selected_option_id in answers_dict.items():
        cur.execute("""INSERT INTO quiz_answers (attempt_id, question_id, selected_option_id) VALUES (%s, %s, %s) """, (attempt_id, q_id, selected_option_id))
    conn.commit()

    cur.close()
    conn.close()

    flash(f"You scored {score} out of {total_questions}.", "success")

    return redirect(url_for('quiz_results', attempt_id=attempt_id))




@app.route('/quiz/results/<int:attempt_id>')
def quiz_results(attempt_id):
    user_id = session.get('user_id')
    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch the attempt
    cur.execute("SELECT quiz_id, user_id, score FROM quiz_attempts WHERE id=%s", (attempt_id,))
    attempt = cur.fetchone()

    if not attempt:
        flash("Attempt not found.", "error")
        return redirect(url_for('quizzes'))

    quiz_id, attempt_user_id, score = attempt

    # Allow student to view only their own result
    if session.get('role') == 3 and attempt_user_id != user_id:
        flash("Unauthorized access to results.", "error")
        return redirect(url_for('quizzes'))

    # Get all questions and options
    cur.execute("""
        SELECT q.id, q.question_text, o.id, o.option_text, o.is_correct
        FROM quiz_questions q
        JOIN quiz_options o ON q.id = o.question_id
        WHERE q.quiz_id = %s
        ORDER BY q.id, o.id
    """, (quiz_id,))
    rows = cur.fetchall()

    questions_dict = {}
    for q_id, q_text, o_id, o_text, is_correct in rows:
        if q_id not in questions_dict:
            questions_dict[q_id] = {
                'id': q_id,
                'text': q_text,
                'options': []
            }
        questions_dict[q_id]['options'].append({
            'id': o_id,
            'text': o_text,
            'is_correct': is_correct
        })

    # Fetch user's selected answers
    cur.execute("""
        SELECT question_id, selected_option_id
        FROM quiz_answers
        WHERE attempt_id = %s
    """, (attempt_id,))
    answer_rows = cur.fetchall()
    user_answers = {q_id: selected_id for q_id, selected_id in answer_rows}

    cur.close()
    conn.close()

    total_questions = len(questions_dict)

    return render_template(
        'quiz_results.html',
        score=score,
        total_questions=total_questions,
        questions=questions_dict.values(),  # convert dict to list
        user_answers=user_answers
    )


@app.route('/quizzes/<int:quiz_id>/results')
def view_quiz_results(quiz_id):
    if session.get('role') != 2:
        flash("Only teachers can view results.", "error")
        return redirect(url_for('quizzes'))

    conn = get_db_connection()
    cur = conn.cursor()

    # Fetch quiz title
    cur.execute("SELECT title FROM quizzes WHERE id=%s", (quiz_id,))
    quiz = cur.fetchone()
    if not quiz:
        flash("Quiz not found.", "error")
        return redirect(url_for('quizzes'))

    # Fetch student scores and attempt ids
    cur.execute("""
        SELECT u.username, qa.score, qa.id
        FROM quiz_attempts qa
        JOIN users u ON qa.user_id = u.id
        WHERE qa.quiz_id = %s
    """, (quiz_id,))
    results = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('view_quiz_results.html', quiz_title=quiz[0], results=results)

@app.route('/quiz/view/<int:quiz_id>')
@role_required(1, 2)
def view_quiz(quiz_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get quiz info
    cursor.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
    quiz = cursor.fetchone()

    # Get questions
    cursor.execute("SELECT * FROM quiz_questions WHERE quiz_id = %s", (quiz_id,))
    questions_raw = cursor.fetchall()

    # Get all options in one go
    question_ids = [q['id'] for q in questions_raw]
    if question_ids:
        format_strings = ','.join(['%s'] * len(question_ids))
        cursor.execute(f"SELECT * FROM quiz_options WHERE question_id IN ({format_strings})", tuple(question_ids))
        all_options = cursor.fetchall()
    else:
        all_options = []

    # Organize options by question_id
    options_by_qid = {}
    for opt in all_options:
        options_by_qid.setdefault(opt['question_id'], []).append(opt)

    # Attach options to questions
    for q in questions_raw:
        q['options'] = options_by_qid.get(q['id'], [])

    cursor.close()
    conn.close()

    return render_template("view_quiz.html", quiz=quiz, questions=questions_raw)



@app.route('/quizzes/create', methods=['GET', 'POST'])
def create_quiz():
    user_role = session.get('role')
    if user_role not in [1, 2]:  # Only admin(1) and teachers(2)
        flash("You don't have permission to create quizzes.", "error")
        return redirect(url_for('quizzes'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO quizzes (title, description) VALUES (%s, %s)", (title, description))
        conn.commit()
        cur.close()
        conn.close()
        flash("Quiz created successfully.", "success")
        return redirect(url_for('quizzes'))
    return render_template('create_quiz.html')



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
