import psycopg2

def create_database_if_not_exists():
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="postgres",
            user="postgres",
            password="Khan@123",
            port="5433"
        )
        conn.autocommit = True
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'ServicesDB';")
        exists = cursor.fetchone()

        if not exists:
            cursor.execute('CREATE DATABASE "ServicesDB";')
            print("✅ Created ServicesDB.")
        else:
            print("ℹ️ ServicesDB already exists.")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print("❌ Error while creating database:", e)


def create_tables(connection):
    try:
        cursor = connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            phone_number VARCHAR(15) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            city VARCHAR(100),
            state VARCHAR(100) DEFAULT 'Karnataka',
            password TEXT NOT NULL,
            address TEXT
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            did SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            specialization VARCHAR(100),
            email VARCHAR(100) UNIQUE NOT NULL,
            phone_number VARCHAR(15) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            license_id TEXT,  -- Base64 encoded license ID
            status VARCHAR(20) DEFAULT 'pending'
        );


        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS book_dr (
            bid SERIAL PRIMARY KEY,
            uid INT REFERENCES users(uid) ON DELETE CASCADE,
            did INT REFERENCES doctors(did) ON DELETE SET NULL,
            booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visit_date DATE NOT NULL,
            patient_age INT,
            gender VARCHAR(10),
            description TEXT,
            status VARCHAR(50) DEFAULT 'Pending'
        );
        """)

        connection.commit()
        cursor.close()
        print("✅ All tables are ready.")

    except psycopg2.Error as e:
        print("❌ Error creating tables:", e)


def get_connection():
    create_database_if_not_exists()

    try:
        connection = psycopg2.connect(
            host="localhost",
            database="ServicesDB",
            user="postgres",
            password="Khan@123",
            port="5433"
        )
        print("✅ Connected to ServicesDB successfully!")

        # Automatically create tables after connection
        create_tables(connection)

        return connection

    except psycopg2.Error as e:
        print("❌ Error connecting to ServicesDB:", e)
        return None
