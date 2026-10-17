import os
import sqlite3
import hashlib
import secrets
from typing import Optional, Dict, Any, Tuple

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chronorag.db")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def hash_password(password: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    if salt_hex is None:
        salt = secrets.token_bytes(16)
        salt_hex = salt.hex()
    else:
        salt = bytes.fromhex(salt_hex)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return pwd_hash.hex(), salt_hex

def init_db():
    with get_db_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            role TEXT DEFAULT 'Student',
            phone TEXT DEFAULT '',
            organization TEXT DEFAULT '',
            avatar_blob BLOB,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            default_target_year INTEGER DEFAULT 2026,
            default_lambda REAL DEFAULT 0.35,
            api_endpoint TEXT DEFAULT 'https://api.chronorag.internal/v1/policies',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        conn.commit()

def register_user(username: str, email: str, password: str, full_name: str, role: str) -> Tuple[bool, str, Optional[int]]:
    username = username.strip()
    email = email.strip().lower()
    full_name = full_name.strip()
    if len(username) < 3:
        return False, "Username must contain at least 3 characters.", None
    if "@" not in email or "." not in email:
        return False, "Please provide a valid email address.", None
    if len(password) < 8:
        return False, "Password must contain at least 8 characters.", None
    if not full_name:
        return False, "Full name is required.", None

    pwd_hash, salt_hex = hash_password(password)
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, salt) VALUES (?, ?, ?, ?)",
                (username, email, pwd_hash, salt_hex)
            )
            user_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO profiles (user_id, full_name, role, phone, organization) VALUES (?, ?, ?, ?, ?)",
                (user_id, full_name, role, "", "")
            )
            cursor.execute(
                "INSERT INTO user_settings (user_id, default_target_year, default_lambda) VALUES (?, 2026, 0.35)",
                (user_id,)
            )
            conn.commit()
            return True, "Account registered successfully.", user_id
    except sqlite3.IntegrityError as e:
        err = str(e).lower()
        if "users.username" in err:
            return False, "That username is already taken.", None
        if "users.email" in err:
            return False, "An account with that email already exists.", None
        return False, "Account already exists with this username or email.", None
    except Exception as e:
        return False, f"Registration failed: {str(e)}", None

def authenticate_user(identifier: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    identifier = identifier.strip()
    if not identifier or not password:
        return False, "Please enter both credentials.", None
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (identifier, identifier.lower()))
        user = cursor.fetchone()
        if not user:
            return False, "Invalid username or password.", None
        expected_hash, _ = hash_password(password, user["salt"])
        if not secrets.compare_digest(expected_hash, user["password_hash"]):
            return False, "Invalid username or password.", None
        cursor.execute("SELECT * FROM profiles WHERE user_id = ?", (user["id"],))
        profile = cursor.fetchone()
        user_data = {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "created_at": user["created_at"],
            "full_name": profile["full_name"] if profile else user["username"],
            "role": profile["role"] if profile else "Student",
            "phone": profile["phone"] if profile else "",
            "organization": profile["organization"] if profile else "",
            "has_avatar": bool(profile["avatar_blob"]) if (profile and profile["avatar_blob"]) else False
        }
        return True, "Authentication successful.", user_data

def get_user_profile(user_id: int) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.created_at, 
                   p.full_name, p.role, p.phone, p.organization,
                   s.default_target_year, s.default_lambda, s.api_endpoint
            FROM users u
            LEFT JOIN profiles p ON u.id = p.user_id
            LEFT JOIN user_settings s ON u.id = s.user_id
            WHERE u.id = ?
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_user_profile(user_id: int, full_name: str, role: str, phone: str, organization: str) -> Tuple[bool, str]:
    try:
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE profiles 
                SET full_name = ?, role = ?, phone = ?, organization = ?
                WHERE user_id = ?
            """, (full_name.strip(), role.strip(), phone.strip(), organization.strip(), user_id))
            conn.commit()
            return True, "Profile changes saved successfully."
    except Exception as e:
        return False, f"Failed to update profile: {str(e)}"

def update_user_avatar(user_id: int, image_bytes: bytes) -> Tuple[bool, str]:
    try:
        with get_db_connection() as conn:
            conn.execute("UPDATE profiles SET avatar_blob = ? WHERE user_id = ?", (image_bytes, user_id))
            conn.commit()
            return True, "Profile photo updated successfully."
    except Exception as e:
        return False, f"Failed to update photo: {str(e)}"

def delete_user_avatar(user_id: int) -> Tuple[bool, str]:
    try:
        with get_db_connection() as conn:
            conn.execute("UPDATE profiles SET avatar_blob = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            return True, "Profile photo removed successfully."
    except Exception as e:
        return False, f"Failed to remove photo: {str(e)}"

def get_user_avatar(user_id: int) -> Optional[bytes]:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT avatar_blob FROM profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row and row["avatar_blob"]:
                return row["avatar_blob"]
            return None
    except Exception:
        return None

def update_user_password(user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
    if len(new_password) < 8:
        return False, "New password must contain at least 8 characters."
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "User record not found."
        cur_hash, _ = hash_password(old_password, user["salt"])
        if not secrets.compare_digest(cur_hash, user["password_hash"]):
            return False, "Current password does not match."
        new_hash, new_salt = hash_password(new_password)
        conn.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (new_hash, new_salt, user_id))
        conn.commit()
        return True, "Password changed successfully."

def update_user_settings(user_id: int, target_year: int, decay_lambda: float, api_endpoint: str) -> Tuple[bool, str]:
    try:
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE user_settings
                SET default_target_year = ?, default_lambda = ?, api_endpoint = ?
                WHERE user_id = ?
            """, (target_year, decay_lambda, api_endpoint.strip(), user_id))
            conn.commit()
            return True, "Retrieval settings saved successfully."
    except Exception as e:
        return False, f"Failed to update settings: {str(e)}"

init_db()