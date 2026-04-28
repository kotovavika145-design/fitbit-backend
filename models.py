# models.py
# Modèles SQLAlchemy alignés avec la base Supabase

from datetime import datetime
from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)  # mot de passe hashé
    role = db.Column(db.String(20), nullable=False)  # 'student' ou 'teacher'
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Relations
    created_sessions = db.relationship(
        "Session",
        backref="creator",
        lazy=True,
        foreign_keys="Session.created_by",
    )

    fitbit_tokens = db.relationship(
        "FitbitToken",
        backref="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    participations = db.relationship(
        "SessionParticipant",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    nasa_tlx_responses = db.relationship(
        "NasaTlxResponse",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    physiological_data = db.relationship(
        "PhysiologicalData",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    mental_load_results = db.relationship(
        "MentalLoadResult",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
        }


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    group_name = db.Column(db.String(255), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="created")
    device = db.Column(db.String(100), nullable=True)
    questionnaire_type = db.Column(db.String(100), nullable=True)

    # Relations
    participants = db.relationship(
        "SessionParticipant",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
    )

    nasa_tlx_responses = db.relationship(
        "NasaTlxResponse",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
    )

    physiological_data = db.relationship(
        "PhysiologicalData",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
    )

    mental_load_results = db.relationship(
        "MentalLoadResult",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_by": self.created_by,
            "group_name": self.group_name,
            "duration_minutes": self.duration_minutes,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "device": self.device,
            "questionnaire_type": self.questionnaire_type,
        }


class SessionParticipant(db.Model):
    __tablename__ = "session_participants"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    fitbit_connected = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "fitbit_connected": self.fitbit_connected,
        }


class FitbitToken(db.Model):
    __tablename__ = "fitbit_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False,unique=True)
    fitbit_user_id = db.Column(db.String(50), nullable=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    def is_expired(self):
        return datetime.utcnow() >= self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "fitbit_user_id": self.fitbit_user_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
        }


class NasaTlxResponse(db.Model):
    __tablename__ = "nasa_tlx_responses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)

    mental = db.Column(db.Integer, nullable=False)
    physical = db.Column(db.Integer, nullable=False)
    temporal = db.Column(db.Integer, nullable=False)
    performance = db.Column(db.Integer, nullable=False)
    effort = db.Column(db.Integer, nullable=False)
    frustration = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    response_time = db.Column(db.String(20), nullable=True)  # 'start' ou 'end'

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "mental": self.mental,
            "physical": self.physical,
            "temporal": self.temporal,
            "performance": self.performance,
            "effort": self.effort,
            "frustration": self.frustration,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "response_time": self.response_time,
        }


class PhysiologicalData(db.Model):
    __tablename__ = "physiological_data"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    heart_rate = db.Column(db.Float, nullable=True)
    hrv = db.Column(db.Float, nullable=True)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "heart_rate": self.heart_rate,
            "hrv": self.hrv,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class MentalLoadResult(db.Model):
    __tablename__ = "mental_load_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)

    nasa_score = db.Column(db.Float, nullable=True)
    avg_heart_rate = db.Column(db.Float, nullable=True)
    avg_hrv = db.Column(db.Float, nullable=True)
    global_score = db.Column(db.Float, nullable=True)
    level = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "nasa_score": self.nasa_score,
            "avg_heart_rate": self.avg_heart_rate,
            "avg_hrv": self.avg_hrv,
            "global_score": self.global_score,
            "level": self.level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
