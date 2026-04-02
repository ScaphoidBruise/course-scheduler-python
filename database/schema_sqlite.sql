-- SQLite dev database (enable with USE_SQLITE=1 in .env)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS courses (
    course_code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS prerequisites (
    course_code TEXT NOT NULL,
    prereq_code TEXT NOT NULL,
    PRIMARY KEY (course_code, prereq_code),
    FOREIGN KEY (course_code) REFERENCES courses (course_code) ON DELETE CASCADE,
    FOREIGN KEY (prereq_code) REFERENCES courses (course_code) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sections (
    section_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT NOT NULL,
    semester TEXT NOT NULL,
    section_code TEXT,
    instructor TEXT,
    days TEXT,
    start_time TEXT,
    end_time TEXT,
    room_number TEXT,
    delivery_mode TEXT,
    enrolled INTEGER,
    seat_limit INTEGER,
    FOREIGN KEY (course_code) REFERENCES courses (course_code) ON DELETE CASCADE
);
