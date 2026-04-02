-- -----------------------------------------------------
-- Database Setup
-- -----------------------------------------------------
CREATE DATABASE IF NOT EXISTS utpb_scheduler;
USE utpb_scheduler;

-- -----------------------------------------------------
-- Reset existing tables (Must be dropped in this order 
-- to avoid foreign key conflict errors)
-- -----------------------------------------------------
DROP TABLE IF EXISTS sections;
DROP TABLE IF EXISTS prerequisites;
DROP TABLE IF EXISTS courses;

-- -----------------------------------------------------
-- 1. Core Courses Table
-- -----------------------------------------------------
CREATE TABLE courses (
    course_code VARCHAR(10) PRIMARY KEY, -- e.g., 'COSC 1336'
    title VARCHAR(255) NOT NULL,         -- e.g., 'Programming Fundamentals I'
    credits INT NOT NULL,                -- e.g., 3
    description TEXT                     -- Full catalog description
);

-- -----------------------------------------------------
-- 2. Prerequisites Junction Table
-- -----------------------------------------------------
CREATE TABLE prerequisites (
    course_code VARCHAR(10),
    prereq_code VARCHAR(10),
    PRIMARY KEY (course_code, prereq_code),
    
    -- Links to courses table; deletes automatically if course is removed
    FOREIGN KEY (course_code) REFERENCES courses(course_code) ON DELETE CASCADE,
    FOREIGN KEY (prereq_code) REFERENCES courses(course_code) ON DELETE CASCADE
);

-- -----------------------------------------------------
-- 3. Sections Table (Specific Offerings)
-- -----------------------------------------------------
CREATE TABLE sections (
    section_id INT AUTO_INCREMENT PRIMARY KEY, -- Unique ID for every single class
    course_code VARCHAR(10) NOT NULL,          -- Links back to the main courses table
    semester VARCHAR(20) NOT NULL,             -- e.g., 'Fall 2026', 'Spring 2027'
    instructor VARCHAR(100),                   -- e.g., 'Dr. Smith'
    days VARCHAR(10),                          -- e.g., 'MWF', 'TR', 'TBA'
    start_time TIME,                           -- Standard SQL time format (HH:MM:SS)
    end_time TIME,                             
    room_number VARCHAR(50),                   -- e.g., 'ST 45'
    delivery_mode VARCHAR(20),                 -- e.g., 'In-Person', 'Online', 'Hybrid'
    
    FOREIGN KEY (course_code) REFERENCES courses(course_code) ON DELETE CASCADE
);