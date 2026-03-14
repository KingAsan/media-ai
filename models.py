from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True) 
    hashed_password = Column(String)                   
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    daily_limit = Column(Integer, nullable=True)

    
    history = relationship("HistoryEntry", back_populates="owner")
    preferences = relationship("UserPreference", back_populates="owner", uselist=False)
    feedback_entries = relationship("RecommendationFeedback", back_populates="owner")
    usage_events = relationship("ApiUsageEvent", back_populates="owner")

class HistoryEntry(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    user_query = Column(Text)
    ai_response = Column(Text)
    ai_response_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="history")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)

    favorite_categories = Column(Text, default="")
    disliked_categories = Column(Text, default="")
    favorite_platforms = Column(Text, default="")
    preferred_language = Column(String, default="ru")
    age_rating = Column(String, default="any")
    discovery_mode = Column(String, default="balanced")
    onboarding_completed = Column(Boolean, default=False)

    owner = relationship("User", back_populates="preferences")


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    session_id = Column(String, index=True, nullable=True)
    query_text = Column(Text, nullable=True)

    title = Column(String, index=True, nullable=False)
    category = Column(String, nullable=True)
    feedback_type = Column(String, index=True, nullable=False)  # like | dislike | watched

    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    owner = relationship("User", back_populates="feedback_entries")


class AdminContentRule(Base):
    __tablename__ = "admin_content_rules"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True, index=True)
    rule_type = Column(String, nullable=False, index=True)  # blacklist | whitelist
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class AdminPinnedRecommendation(Base):
    __tablename__ = "admin_pinned_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    year_genre = Column(String, nullable=True)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=True, index=True)
    why_this = Column(Text, nullable=True)
    video_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class ApiUsageEvent(Base):
    __tablename__ = "api_usage_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    endpoint = Column(String, nullable=False, index=True)
    model_name = Column(String, nullable=True, index=True)
    status_code = Column(Integer, nullable=False, index=True)
    source = Column(String, nullable=True)
    query_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    owner = relationship("User", back_populates="usage_events")


class AdminSetting(Base):
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, index=True)
