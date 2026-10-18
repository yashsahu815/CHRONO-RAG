import os
import sqlite3
import hashlib
import secrets
from typing import Optional, Dict, Any, Tuple, List

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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS regulatory_documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            issuing_authority TEXT NOT NULL,
            circular_no TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            publication_date TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            applicable_year INTEGER NOT NULL,
            source_url TEXT DEFAULT '',
            summary TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            verification_status TEXT DEFAULT 'Indexed — Pending Verification',
            uploaded_by TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS regulatory_chunks (
            id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            section_heading TEXT NOT NULL,
            page_number INTEGER DEFAULT 1,
            chunk_text TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES regulatory_documents(id) ON DELETE CASCADE
        );
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS regulatory_changes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            authority TEXT NOT NULL,
            start_year INTEGER NOT NULL,
            end_year INTEGER NOT NULL,
            category TEXT NOT NULL,
            earlier_doc_id TEXT,
            earlier_clause_ref TEXT,
            earlier_text TEXT,
            earlier_date TEXT,
            updated_doc_id TEXT,
            updated_clause_ref TEXT,
            updated_text TEXT,
            updated_date TEXT,
            effective_date TEXT,
            summary TEXT NOT NULL,
            change_reason TEXT,
            verification_status TEXT DEFAULT 'Verified',
            FOREIGN KEY (earlier_doc_id) REFERENCES regulatory_documents(id),
            FOREIGN KEY (updated_doc_id) REFERENCES regulatory_documents(id)
        );
        """)
        conn.commit()

    seed_verified_regulatory_records()

def seed_verified_regulatory_records():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM regulatory_documents WHERE issuing_authority = 'IRDAI'")
        if cursor.fetchone()[0] > 0:
            return

        doc_2020 = (
            "IRDAI_CIR_2020_GSV",
            "IRDAI (Non-Linked Insurance Products) Regulations - Vesting and Surrender Scale",
            "IRDAI",
            "Ref: IRDAI/NL/CIR/2019-20/124",
            "Gazette Notification",
            "2020-02-01",
            "2020-02-01",
            2020,
            "https://irdai.gov.in/notifications",
            "Mandated 3-year minimum premium payment before acquiring Guaranteed Surrender Value (GSV) with 100% first-year forfeiture.",
            "Section 7.2: A policy shall acquire a Guaranteed Surrender Value (GSV) only after payment of continuous premiums for at least 3 consecutive years for premium paying terms of 10 years or more. If a policy is discontinued or surrendered prior to the completion of 3 consecutive years, zero surrender payout is admissible, and 100% of all paid premiums shall be forfeited to the insurer.",
            "Verified",
            "system"
        )
        doc_2024 = (
            "IRDAI_MASTER_CIR_2024",
            "IRDAI Master Circular on Life Insurance Products - Abolition of Year 1 Forfeiture",
            "IRDAI",
            "IRDAI/ACTL/MST/CIR/116/06/2024",
            "Master Circular",
            "2024-06-12",
            "2024-10-01",
            2024,
            "https://irdai.gov.in/master-circulars",
            "Abolished complete premium forfeiture on Year 1 surrender and mandated Special Surrender Value (SSV) after 1 full year.",
            "Chapter III, Clause 14.1: Insurers shall not forfeit the entire premium paid under non-linked life insurance policies upon early discontinuance. A policy shall acquire a Special Surrender Value (SSV) upon payment of full premiums for at least one full policy year. Clause 14.3: The Special Surrender Value shall be calculated fairly and reasonably reflecting accumulated capital without disproportionate administrative surrender penalties.",
            "Verified",
            "system"
        )
        doc_2026 = (
            "LIC_OP_DIR_2026",
            "LIC Operational Directive on Statutory G-Sec Benchmark SSV Computations",
            "LIC of India",
            "LIC/CO/ACT/2026/DIR-04",
            "Operational Directive",
            "2026-03-15",
            "2026-04-01",
            2026,
            "https://licindia.in/guidelines",
            "Operationalized discounted cash-flow valuation linked to 10-Yr Indian G-Sec benchmark yield plus 50 bps spread for Year 1 exits.",
            "Directive Clause 4(b): Pursuant to statutory IRDAI mandates, all individual endowment and non-linked products guarantee a Special Surrender Value payable after Year 1. Payouts are computed by discounting accumulated premiums and accrued bonuses against the prevailing 10-year Indian Government Securities (G-Sec) benchmark yield plus a statutory 50 bps margin.",
            "Verified",
            "system"
        )
        cursor.executemany("""
        INSERT OR REPLACE INTO regulatory_documents 
        (id, title, issuing_authority, circular_no, doc_type, publication_date, effective_date, applicable_year, source_url, summary, raw_text, verification_status, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [doc_2020, doc_2024, doc_2026])

        chunks = [
            ("CHK_2020_1", "IRDAI_CIR_2020_GSV", 1, "Section 7.2: Vesting and Forfeiture Scale", 12, "Section 7.2: A policy shall acquire a Guaranteed Surrender Value (GSV) only after payment of continuous premiums for at least 3 consecutive years for premium paying terms of 10 years or more. If a policy is discontinued or surrendered prior to the completion of 3 consecutive years, zero surrender payout is admissible, and 100% of all paid premiums shall be forfeited to the insurer."),
            ("CHK_2024_1", "IRDAI_MASTER_CIR_2024", 1, "Chapter III Clause 14.1: Prohibition of Complete Premium Forfeiture", 28, "Chapter III, Clause 14.1: Insurers shall not forfeit the entire premium paid under non-linked life insurance policies upon early discontinuance. A policy shall acquire a Special Surrender Value (SSV) upon payment of full premiums for at least one full policy year."),
            ("CHK_2024_2", "IRDAI_MASTER_CIR_2024", 2, "Chapter III Clause 14.3: Special Surrender Value Principles", 29, "Clause 14.3: The Special Surrender Value shall be calculated fairly and reasonably reflecting accumulated capital without disproportionate administrative surrender penalties."),
            ("CHK_2026_1", "LIC_OP_DIR_2026", 1, "Directive Clause 4(b): G-Sec Linked Discounting Methodology", 4, "Directive Clause 4(b): Pursuant to statutory IRDAI mandates, all individual endowment and non-linked products guarantee a Special Surrender Value payable after Year 1. Payouts are computed by discounting accumulated premiums and accrued bonuses against the prevailing 10-year Indian Government Securities (G-Sec) benchmark yield plus a statutory 50 bps margin.")
        ]
        cursor.executemany("""
        INSERT OR REPLACE INTO regulatory_chunks 
        (id, doc_id, chunk_index, section_heading, page_number, chunk_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """, chunks)

        changes = [
            (
                "CHG_01_FORFEITURE",
                "Abolition of 100% First-Year Premium Forfeiture",
                "IRDAI / LIC",
                2020,
                2024,
                "Withdrawn or repealed provisions",
                "IRDAI_CIR_2020_GSV",
                "Section 7.2",
                "Zero surrender value payable; 100% of all paid premiums forfeited if exited within years 1 or 2.",
                "2020-02-01",
                "IRDAI_MASTER_CIR_2024",
                "Chapter III, Clause 14.1",
                "Insurers shall not forfeit the entire premium paid upon early discontinuance after 1 full year.",
                "2024-06-12",
                "2024-10-01",
                "Complete first-year forfeiture has been officially abolished by statutory authority; policyholders acquire Special Surrender Value after Year 1.",
                "Curbing early-lapse capital erosion and protecting long-term retail policyholder equity.",
                "Verified"
            ),
            (
                "CHG_02_LOCKIN",
                "Reduction of Minimum Surrender Lock-in Period",
                "IRDAI",
                2020,
                2024,
                "Amended provisions",
                "IRDAI_CIR_2020_GSV",
                "Section 7.2",
                "3 Full Consecutive Policy Years required to acquire any surrender value.",
                "2020-02-01",
                "IRDAI_MASTER_CIR_2024",
                "Chapter III, Clause 14.1",
                "Minimum continuous premium paying duration reduced to 1 Full Policy Year.",
                "2024-06-12",
                "2024-10-01",
                "Lock-in threshold for non-linked life products amended from 36 continuous months down to 12 months.",
                "Aligning product liquidity with customer-centric market conduct standards.",
                "Verified"
            ),
            (
                "CHG_03_GSEC_VALUATION",
                "Actuarial Valuation Pegged to 10-Year G-Sec Yield",
                "LIC of India",
                2024,
                2026,
                "Newly introduced provisions",
                "IRDAI_MASTER_CIR_2024",
                "Clause 14.3",
                "Qualitative requirement for fair and reasonable calculation without prescribed capital benchmark spread.",
                "2024-06-12",
                "LIC_OP_DIR_2026",
                "Directive Clause 4(b)",
                "Statutory DCF valuation discounted at 10-year Indian G-Sec benchmark yield + 50 bps spread.",
                "2026-03-15",
                "2026-04-01",
                "Quantitative discounting formula formalized using sovereign bond yields to determine exit cash values objectively.",
                "Statutory standardization of surrender value computation methodologies.",
                "Verified"
            )
        ]
        cursor.executemany("""
        INSERT OR REPLACE INTO regulatory_changes
        (id, title, authority, start_year, end_year, category, earlier_doc_id, earlier_clause_ref, earlier_text, earlier_date, updated_doc_id, updated_clause_ref, updated_text, updated_date, effective_date, summary, change_reason, verification_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, changes)

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
            return row["avatar_blob"] if (row and row["avatar_blob"]) else None
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

def get_all_regulatory_documents(verified_only: bool = False) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if verified_only:
            cursor.execute("SELECT * FROM regulatory_documents WHERE verification_status = 'Verified' ORDER BY applicable_year DESC")
        else:
            cursor.execute("SELECT * FROM regulatory_documents ORDER BY applicable_year DESC")
        return [dict(r) for r in cursor.fetchall()]

def get_regulatory_document_by_id(doc_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM regulatory_documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_chunks_for_document(doc_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM regulatory_chunks WHERE doc_id = ? ORDER BY chunk_index ASC", (doc_id,))
        return [dict(r) for r in cursor.fetchall()]

def insert_regulatory_document(doc: Dict[str, Any], chunks: List[Dict[str, Any]]) -> Tuple[bool, str]:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO regulatory_documents 
            (id, title, issuing_authority, circular_no, doc_type, publication_date, effective_date, applicable_year, source_url, summary, raw_text, verification_status, uploaded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc["id"], doc["title"], doc["issuing_authority"], doc["circular_no"],
                doc["doc_type"], doc["publication_date"], doc["effective_date"],
                doc["applicable_year"], doc.get("source_url", ""), doc["summary"],
                doc["raw_text"], doc.get("verification_status", "Indexed — Pending Verification"),
                doc.get("uploaded_by", "analyst")
            ))
            for chk in chunks:
                cursor.execute("""
                INSERT INTO regulatory_chunks 
                (id, doc_id, chunk_index, section_heading, page_number, chunk_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (chk["id"], doc["id"], chk["chunk_index"], chk["section_heading"], chk.get("page_number", 1), chk["chunk_text"]))
            conn.commit()
            return True, f"Document `{doc['id']}` successfully indexed with {len(chunks)} chunks."
    except Exception as e:
        return False, f"Failed to ingest document: {str(e)}"

def update_document_verification_status(doc_id: str, new_status: str) -> Tuple[bool, str]:
    valid_statuses = ["Verified", "Indexed — Pending Verification", "Insufficient Evidence", "Extraction Error", "Conflicting Sources"]
    if new_status not in valid_statuses:
        return False, f"Invalid verification status: {new_status}"
    try:
        with get_db_connection() as conn:
            conn.execute("UPDATE regulatory_documents SET verification_status = ? WHERE id = ?", (new_status, doc_id))
            conn.commit()
            return True, f"Verification status for `{doc_id}` updated to `{new_status}`."
    except Exception as e:
        return False, f"Database update failed: {str(e)}"

def get_regulatory_changes(start_year: int, end_year: int, category: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM regulatory_changes WHERE start_year >= ? AND end_year <= ?"
        params = [start_year, end_year]
        if category and category != "All Categories":
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY end_year DESC, start_year ASC"
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]

def get_change_by_id(change_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM regulatory_changes WHERE id = ?", (change_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

init_db()