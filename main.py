import asyncio
import csv
import io
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session
from youtube_search import YoutubeSearch

from database import Base, SessionLocal, engine
from models import (
    AdminContentRule,
    AdminPinnedRecommendation,
    AdminSetting,
    ApiUsageEvent,
    HistoryEntry,
    RecommendationFeedback,
    User,
    UserPreference,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("GOOGLE_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "diploma-super-secret-key-asanali")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

PRIMARY_MODEL_NAME = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3-flash-preview")
FALLBACK_MODEL_NAMES = [
    name.strip()
    for name in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite-preview").split(",")
    if name.strip()
]
DEFAULT_DAILY_LIMIT = int(os.getenv("DEFAULT_DAILY_LIMIT", "40"))


def gemini_url_for_model(model_name: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent?key={api_key}"
    )

DEFAULT_PREFERENCES = {
    "favorite_categories": [],
    "disliked_categories": [],
    "favorite_platforms": [],
    "preferred_language": "ru",
    "age_rating": "any",
    "discovery_mode": "balanced",
    "onboarding_completed": False,
}

ASSISTANT_MODE_HINTS = {
    "balanced": "Give a balanced mix of safe and fresh recommendations.",
    "fast": "Favor instant picks: recognizable titles and quick-start options.",
    "deep": "Provide thoughtful picks with one hidden gem and richer reasoning.",
    "surprise": "Prioritize unusual, bold, and less obvious options.",
}

GENERAL_QUERY_PATTERNS = [
    "что посмотреть",
    "посоветуй",
    "что-нибудь",
    "что нибудь",
    "рекомендацию",
    "recommend something",
    "something to watch",
]

FALLBACK_LIBRARY = {
    "anime": [
        {
            "title": "Врата Штейна",
            "year_genre": "2011, научная фантастика, триллер",
            "category": "Аниме",
            "description": "Если нужен умный и эмоциональный сюжет, **«Врата Штейна»** отлично сработает. История держит темп и постепенно раскрывает сильные повороты, что особенно хорошо для вдумчивого просмотра.",
        },
        {
            "title": "Клинок, рассекающий демонов",
            "year_genre": "2019, приключения, фэнтези",
            "category": "Аниме",
            "description": "Для динамичного вечера подойдет **«Клинок, рассекающий демонов»**: красивый визуал, мощные бои и понятная мотивация героев. Это хорошая точка входа даже для тех, кто редко смотрит аниме.",
        },
        {
            "title": "Охотник x Охотник",
            "year_genre": "2011, приключения, сёнэн",
            "category": "Аниме",
            "description": "**«Охотник x Охотник»** сочетает легкий старт и глубокое развитие мира. Сериал легко смотреть в компании благодаря ярким персонажам и насыщенным аркам.",
        },
    ],
    "movie": [
        {
            "title": "Бегущий по лезвию 2049",
            "year_genre": "2017, фантастика, драма",
            "category": "Фильм",
            "description": "Если хочется атмосферной научной фантастики, **«Бегущий по лезвию 2049»** дает сильный визуальный опыт и взрослую историю. Отличный вариант для спокойного, вдумчивого просмотра.",
        },
        {
            "title": "Начало",
            "year_genre": "2010, фантастика, триллер",
            "category": "Фильм",
            "description": "**«Начало»** подходит, когда нужен интеллектуальный экшен с мощной идеей. Картина держит темп и хорошо работает как для соло-просмотра, так и для обсуждения с друзьями.",
        },
        {
            "title": "Достать ножи",
            "year_genre": "2019, детектив, комедия",
            "category": "Фильм",
            "description": "Для более легкого и увлекательного вечера выбирай **«Достать ножи»**. Это стильный детектив с харизматичными персонажами и понятной динамикой сюжета.",
        },
    ],
    "series": [
        {
            "title": "Черное зеркало",
            "year_genre": "2011, антология, sci-fi",
            "category": "Сериал",
            "description": "**«Черное зеркало»** удобно смотреть по эпизодам, когда время ограничено. Каждая серия дает отдельную завершенную историю и сильный эффект обсуждения.",
        },
        {
            "title": "Аркейн",
            "year_genre": "2021, анимация, фэнтези",
            "category": "Сериал",
            "description": "Если нужен визуально сильный и эмоциональный сериал, **«Аркейн»** почти всегда попадает в цель. Подойдет для вечернего просмотра в одиночку и в компании.",
        },
        {
            "title": "Очень странные дела",
            "year_genre": "2016, приключения, мистика",
            "category": "Сериал",
            "description": "**«Очень странные дела»** хорошо подходят для дружеского просмотра благодаря атмосфере и ностальгическому вайбу. Сюжет быстро втягивает и держит интерес.",
        },
    ],
    "game": [
        {
            "title": "It Takes Two",
            "year_genre": "2021, кооператив, приключения",
            "category": "Игра",
            "description": "Для совместного вечера идеально подойдет **It Takes Two**: игра построена на взаимодействии и постоянно предлагает новые механики. Отличный вариант для пары или друзей.",
        },
        {
            "title": "Hades",
            "year_genre": "2020, roguelike, экшен",
            "category": "Игра",
            "description": "**Hades** подойдет, если хочется динамичного геймплея короткими сессиями. Игра легко запускается «на 30 минут» и при этом дает ощущение прогресса.",
        },
        {
            "title": "Stardew Valley",
            "year_genre": "2016, симулятор, инди",
            "category": "Игра",
            "description": "Если настроение на спокойный ритм, **Stardew Valley** дает расслабляющий опыт без давления. Отлично работает после напряженного дня.",
        },
    ],
    "music": [
        {
            "title": "Lo-fi Beats Mix",
            "year_genre": "lo-fi, instrumental",
            "category": "Музыка",
            "description": "Для фокуса и мягкого фона подойдет **Lo-fi Beats Mix**. Ровный ритм без резких переходов помогает удерживать концентрацию во время работы.",
        },
        {
            "title": "Synthwave Drive",
            "year_genre": "synthwave, electronic",
            "category": "Музыка",
            "description": "Если нужен энергичный, но не перегруженный звук, попробуй **Synthwave Drive**. Такой стиль хорошо подходит для вечерней работы или поездок.",
        },
        {
            "title": "Neo-Classical Focus",
            "year_genre": "neoclassical, ambient",
            "category": "Музыка",
            "description": "**Neo-Classical Focus** хорош для спокойного и продуктивного состояния. Музыка добавляет эмоциональную глубину и не отвлекает от задач.",
        },
    ],
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def asset_path(*parts: str) -> Path:
    return BASE_DIR.joinpath(*parts)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Сессия истекла, войдите снова",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if bool(user.is_blocked):
        raise HTTPException(status_code=403, detail="Аккаунт временно ограничен администратором")
    return user


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if not bool(current_user.is_admin):
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return current_user


def get_admin_setting(db: Session, key: str, default: str) -> str:
    row = db.query(AdminSetting).filter(AdminSetting.key == key).first()
    if row is None:
        row = AdminSetting(key=key, value=default)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row.value


def set_admin_setting(db: Session, key: str, value: str) -> str:
    row = db.query(AdminSetting).filter(AdminSetting.key == key).first()
    if row is None:
        row = AdminSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
    db.refresh(row)
    return row.value


def to_bool(value: str | bool | int | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on", "enabled"}


def get_default_daily_limit(db: Session) -> int:
    raw = get_admin_setting(db, "default_daily_limit", str(DEFAULT_DAILY_LIMIT))
    try:
        parsed = int(raw)
        if parsed < 1:
            return DEFAULT_DAILY_LIMIT
        return parsed
    except Exception:
        return DEFAULT_DAILY_LIMIT


def get_force_lite_mode(db: Session) -> bool:
    raw = get_admin_setting(db, "force_lite_mode", "0")
    return to_bool(raw)


def get_user_daily_limit(db: Session, user: User) -> int:
    if user.daily_limit is not None and int(user.daily_limit) > 0:
        return int(user.daily_limit)
    return get_default_daily_limit(db)


def utc_day_range() -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def count_user_today_queries(db: Session, user_id: int) -> int:
    start, end = utc_day_range()
    return (
        db.query(HistoryEntry)
        .filter(
            HistoryEntry.user_id == user_id,
            HistoryEntry.timestamp >= start,
            HistoryEntry.timestamp < end,
        )
        .count()
    )


def log_usage_event(
    db: Session,
    user_id: int | None,
    endpoint: str,
    status_code: int,
    model_name: str | None = None,
    source: str | None = None,
    query_text: str | None = None,
) -> None:
    row = ApiUsageEvent(
        user_id=user_id,
        endpoint=endpoint,
        status_code=int(status_code),
        model_name=model_name,
        source=source,
        query_text=query_text,
    )
    db.add(row)
    db.commit()


def resolve_download_file() -> Path | None:
    candidates = [
        asset_path("dist", "MediaAI", "MediaAI.exe"),
        asset_path("dist", "MediaAI.exe"),
        asset_path("downloads", "MediaAI.exe"),
        asset_path("downloads", "MediaAI.zip"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def parse_csv_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def to_csv_values(items: list[str] | None) -> str:
    if not items:
        return ""
    return ", ".join(sorted({item.strip() for item in items if item.strip()}))


def clean_list(items: list[str], limit: int = 12) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize_title(value: str) -> str:
    lowered = str(value or "").lower().strip()
    cleaned = re.sub(r"[^\wа-яё]+", " ", lowered, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def detect_bucket(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["аниме", "isekai", "исекай"]):
        return "anime"
    if any(k in q for k in ["игр", "game", "steam", "ps5", "xbox"]):
        return "game"
    if any(k in q for k in ["музык", "music", "трек", "playlist", "плейлист"]):
        return "music"
    if any(k in q for k in ["сериал", "series", "show"]):
        return "series"
    return "movie"


def get_or_create_preferences(db: Session, user_id: int) -> UserPreference:
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if prefs:
        return prefs

    prefs = UserPreference(user_id=user_id)
    db.add(prefs)
    db.commit()
    db.refresh(prefs)
    return prefs


def preferences_to_dict(prefs: UserPreference) -> dict[str, Any]:
    return {
        "favorite_categories": parse_csv_values(prefs.favorite_categories),
        "disliked_categories": parse_csv_values(prefs.disliked_categories),
        "favorite_platforms": parse_csv_values(prefs.favorite_platforms),
        "preferred_language": prefs.preferred_language or "ru",
        "age_rating": prefs.age_rating or "any",
        "discovery_mode": prefs.discovery_mode or "balanced",
        "onboarding_completed": bool(prefs.onboarding_completed),
    }


def normalize_recommendations(raw_text: str) -> list[dict[str, str]]:
    parsed: Any
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("[")
        end = raw_text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(raw_text[start : end + 1])

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or item.get("name") or "Без названия").strip()
        year_genre = str(item.get("year_genre") or item.get("yearGenre") or "").strip()
        description = str(item.get("description") or item.get("desc") or "").strip()
        category = str(item.get("category") or "").strip()
        why_this = str(item.get("why_this") or item.get("why") or "").strip()

        if not description:
            description = "Подбор выполнен по вашему запросу."
        if not why_this:
            why_this = "Подходит по вашему запросу и текущему контексту."

        normalized.append(
            {
                "title": title,
                "year_genre": year_genre,
                "description": description,
                "category": category,
                "why_this": why_this,
            }
        )

    return normalized[:12]


def collect_recent_titles(db: Session, user_id: int, limit: int = 60) -> list[str]:
    history_rows = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.user_id == user_id)
        .order_by(desc(HistoryEntry.timestamp))
        .limit(limit)
        .all()
    )

    titles: list[str] = []
    seen: set[str] = set()
    for row in history_rows:
        if not row.ai_response_json:
            continue
        try:
            payload = json.loads(row.ai_response_json)
        except Exception:
            continue
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            key = normalize_title(title)
            if not key or key in seen:
                continue
            seen.add(key)
            titles.append(title)
            if len(titles) >= limit:
                return titles
    return titles


def collect_feedback_summary(db: Session, user_id: int, limit: int = 300) -> dict[str, Any]:
    rows = (
        db.query(RecommendationFeedback)
        .filter(RecommendationFeedback.user_id == user_id)
        .order_by(desc(RecommendationFeedback.timestamp))
        .limit(limit)
        .all()
    )

    liked_titles: set[str] = set()
    disliked_titles: set[str] = set()
    watched_titles: set[str] = set()
    preferred_category_counter: Counter[str] = Counter()
    avoid_category_counter: Counter[str] = Counter()

    for row in rows:
        title_norm = normalize_title(row.title)
        category_norm = normalize_title(row.category or "")
        feedback_type = (row.feedback_type or "").lower().strip()

        if feedback_type == "like":
            if title_norm:
                liked_titles.add(title_norm)
            if category_norm:
                preferred_category_counter[category_norm] += 1
        elif feedback_type == "dislike":
            if title_norm:
                disliked_titles.add(title_norm)
            if category_norm:
                avoid_category_counter[category_norm] += 1
        elif feedback_type == "watched":
            if title_norm:
                watched_titles.add(title_norm)

    return {
        "liked_titles": liked_titles,
        "disliked_titles": disliked_titles,
        "watched_titles": watched_titles,
        "preferred_categories": [name for name, _ in preferred_category_counter.most_common(4)],
        "avoid_categories": [name for name, _ in avoid_category_counter.most_common(4)],
        "feedback_count": len(rows),
    }


def build_personalization_context(
    request: "UserRequest",
    prefs: UserPreference,
    recent_titles: list[str],
    feedback_summary: dict[str, Any],
) -> str:
    pref_data = preferences_to_dict(prefs)
    assistant_mode = (request.assistant_mode or pref_data["discovery_mode"] or "balanced").lower()
    mode_hint = ASSISTANT_MODE_HINTS.get(assistant_mode, ASSISTANT_MODE_HINTS["balanced"])

    context_parts = [
        f"User query: {request.query}",
        f"Assistant mode: {assistant_mode}. {mode_hint}",
        f"Preferred language: {pref_data['preferred_language']}",
        f"Allowed age rating: {pref_data['age_rating']}",
    ]

    if pref_data["favorite_categories"]:
        context_parts.append(f"Favorite categories: {', '.join(pref_data['favorite_categories'])}")
    if pref_data["disliked_categories"]:
        context_parts.append(f"Avoid categories: {', '.join(pref_data['disliked_categories'])}")
    if pref_data["favorite_platforms"]:
        context_parts.append(f"Preferred platforms: {', '.join(pref_data['favorite_platforms'])}")
    if request.mood:
        context_parts.append(f"Current mood: {request.mood}")
    if request.company:
        context_parts.append(f"Watching/playing company: {request.company}")
    if request.time_minutes and request.time_minutes > 0:
        context_parts.append(f"Available time: about {request.time_minutes} minutes")

    if recent_titles:
        context_parts.append(f"Avoid repeating these recent titles: {', '.join(recent_titles[:12])}")
    if feedback_summary["liked_titles"]:
        context_parts.append("User often likes titles close to past likes.")
    if feedback_summary["disliked_titles"] or feedback_summary["avoid_categories"]:
        context_parts.append("Strictly avoid disliked/watched-out content signals from feedback.")
    if feedback_summary["preferred_categories"]:
        context_parts.append(
            f"Feedback-based preferred categories: {', '.join(feedback_summary['preferred_categories'])}"
        )

    return "\n".join(context_parts)


def build_why_this(item: dict[str, Any], request: "UserRequest", prefs: UserPreference) -> str:
    existing = str(item.get("why_this") or "").strip()
    if existing:
        return existing

    pref_data = preferences_to_dict(prefs)
    reasons: list[str] = []
    if request.mood:
        reasons.append(f"совпадает с настроением «{request.mood}»")
    if request.company:
        reasons.append(f"учитывает формат просмотра «{request.company}»")
    if request.time_minutes and request.time_minutes > 0:
        reasons.append(f"подходит под доступное время около {request.time_minutes} минут")
    if item.get("category") and pref_data["favorite_categories"]:
        reasons.append("соответствует вашим любимым категориям")

    if not reasons:
        reasons.append("соответствует вашему текущему запросу")

    return "Подходит потому что " + ", ".join(reasons[:3]) + "."


def refine_or_none(query: str) -> str | None:
    normalized = query.lower().strip()
    short_query = len(normalized.split()) <= 2
    generic_match = any(pattern in normalized for pattern in GENERAL_QUERY_PATTERNS)

    if short_query or generic_match:
        return (
            "Запрос пока слишком общий. Чтобы дать точные рекомендации, уточни 2-3 параметра:\n\n"
            "- жанр или тему\n"
            "- настроение\n"
            "- формат (один/с друзьями) и время\n\n"
            "Пример: `аниме исекай на вечер, динамичное, 40 минут`"
        )
    return None


def select_recommendations(
    candidates: list[dict[str, str]],
    recent_titles: list[str],
    feedback_summary: dict[str, Any],
    limit: int = 3,
) -> list[dict[str, str]]:
    if not candidates:
        return []

    recent_norm = {normalize_title(title) for title in recent_titles if title}
    disliked_titles = set(feedback_summary.get("disliked_titles") or [])
    watched_titles = set(feedback_summary.get("watched_titles") or [])
    preferred_categories = set(feedback_summary.get("preferred_categories") or [])
    avoid_categories = set(feedback_summary.get("avoid_categories") or [])

    unique_candidates: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for idx, item in enumerate(candidates):
        title_norm = normalize_title(item.get("title", ""))
        if not title_norm or title_norm in seen_titles:
            continue
        seen_titles.add(title_norm)
        copy_item = dict(item)
        copy_item["_title_norm"] = title_norm
        copy_item["_idx"] = idx
        copy_item["_cat_norm"] = normalize_title(item.get("category", ""))
        unique_candidates.append(copy_item)

    def score(item: dict[str, str]) -> int:
        points = 0
        if item["_title_norm"] not in recent_norm:
            points += 5
        else:
            points -= 2
        if item["_title_norm"] in disliked_titles:
            points -= 100
        if item["_title_norm"] in watched_titles:
            points -= 100
        if item["_cat_norm"] in preferred_categories:
            points += 4
        if item["_cat_norm"] in avoid_categories:
            points -= 10
        return points

    ranked = sorted(unique_candidates, key=lambda x: (score(x), -x["_idx"]), reverse=True)

    selected: list[dict[str, str]] = []
    used_categories: set[str] = set()
    used_titles: set[str] = set()

    for item in ranked:
        if len(selected) >= limit:
            break
        if item["_title_norm"] in used_titles:
            continue
        if item["_title_norm"] in recent_norm:
            continue
        if item["_title_norm"] in disliked_titles or item["_title_norm"] in watched_titles:
            continue
        cat = item["_cat_norm"]
        if cat and cat in used_categories:
            continue
        selected.append(item)
        used_titles.add(item["_title_norm"])
        if cat:
            used_categories.add(cat)

    for item in ranked:
        if len(selected) >= limit:
            break
        if item["_title_norm"] in used_titles:
            continue
        if item["_title_norm"] in disliked_titles or item["_title_norm"] in watched_titles:
            continue
        selected.append(item)
        used_titles.add(item["_title_norm"])

    for item in ranked:
        if len(selected) >= limit:
            break
        if item["_title_norm"] in used_titles:
            continue
        selected.append(item)
        used_titles.add(item["_title_norm"])

    clean_output: list[dict[str, str]] = []
    for item in selected[:limit]:
        output = {k: v for k, v in item.items() if not k.startswith("_")}
        clean_output.append(output)
    return clean_output


def build_fallback_recommendations(
    request: "UserRequest",
    prefs: UserPreference,
    recent_titles: list[str],
    feedback_summary: dict[str, Any],
    limit: int = 3,
) -> list[dict[str, str]]:
    bucket = detect_bucket(request.query)
    pool = list(FALLBACK_LIBRARY.get(bucket, []))

    if bucket != "series":
        pool.extend(FALLBACK_LIBRARY["series"][:1])
    if bucket != "movie":
        pool.extend(FALLBACK_LIBRARY["movie"][:1])

    recent_norm = {normalize_title(title) for title in recent_titles}
    disliked_titles = set(feedback_summary.get("disliked_titles") or [])
    watched_titles = set(feedback_summary.get("watched_titles") or [])

    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in pool:
        title_norm = normalize_title(item.get("title", ""))
        if not title_norm or title_norm in seen:
            continue
        if title_norm in disliked_titles or title_norm in watched_titles:
            continue
        if title_norm in recent_norm and len(selected) < limit - 1:
            continue
        candidate = dict(item)
        candidate["why_this"] = build_why_this(candidate, request, prefs)
        selected.append(candidate)
        seen.add(title_norm)
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for item in pool:
            title_norm = normalize_title(item.get("title", ""))
            if not title_norm or title_norm in seen:
                continue
            candidate = dict(item)
            candidate["why_this"] = build_why_this(candidate, request, prefs)
            selected.append(candidate)
            seen.add(title_norm)
            if len(selected) >= limit:
                break

    return selected[:limit]


def history_preview(row: HistoryEntry) -> str:
    if row.ai_response_json:
        try:
            payload = json.loads(row.ai_response_json)
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                title = str(payload[0].get("title") or "").strip()
                if title:
                    return f"Последняя рекомендация: {title}"
        except Exception:
            pass
    text_value = str(row.ai_response or "").strip()
    if not text_value:
        return ""
    return text_value.replace("\n", " ")[:120]


def get_admin_rules(db: Session) -> dict[str, set[str]]:
    rows = db.query(AdminContentRule).all()
    result = {
        "black_titles": set(),
        "black_categories": set(),
        "white_titles": set(),
        "white_categories": set(),
    }
    for row in rows:
        title = normalize_title(row.title or "")
        category = normalize_title(row.category or "")
        kind = (row.rule_type or "").strip().lower()
        if kind == "blacklist":
            if title:
                result["black_titles"].add(title)
            if category:
                result["black_categories"].add(category)
        elif kind == "whitelist":
            if title:
                result["white_titles"].add(title)
            if category:
                result["white_categories"].add(category)
    return result


def apply_admin_rules(items: list[dict[str, str]], rules: dict[str, set[str]]) -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    for item in items:
        title_norm = normalize_title(item.get("title", ""))
        cat_norm = normalize_title(item.get("category", ""))
        if title_norm and title_norm in rules["black_titles"]:
            continue
        if cat_norm and cat_norm in rules["black_categories"]:
            continue
        filtered.append(item)
    return filtered


def inject_pinned_recommendations(
    db: Session,
    query_text: str,
    recommendations: list[dict[str, str]],
    limit: int = 3,
) -> list[dict[str, str]]:
    active_rows = (
        db.query(AdminPinnedRecommendation)
        .filter(AdminPinnedRecommendation.is_active.is_(True))
        .order_by(desc(AdminPinnedRecommendation.created_at))
        .all()
    )
    if not active_rows:
        return recommendations[:limit]

    query_norm = normalize_title(query_text)
    selected: list[dict[str, str]] = list(recommendations)
    seen = {normalize_title(item.get("title", "")) for item in selected}

    def matches_query(row: AdminPinnedRecommendation) -> bool:
        if not query_norm:
            return True
        title_norm = normalize_title(row.title or "")
        cat_norm = normalize_title(row.category or "")
        return (title_norm and title_norm in query_norm) or (cat_norm and cat_norm in query_norm)

    pinned_candidates = [row for row in active_rows if matches_query(row)] or active_rows
    for row in pinned_candidates:
        title_norm = normalize_title(row.title or "")
        if not title_norm or title_norm in seen:
            continue
        selected.insert(
            0,
            {
                "title": row.title,
                "year_genre": row.year_genre or "",
                "description": row.description,
                "category": row.category or "",
                "why_this": row.why_this or "Рекомендация добавлена администратором проекта.",
                "video_id": row.video_id,
            },
        )
        seen.add(title_norm)
        if len(selected) >= limit:
            break

    return selected[:limit]


def find_trailer(title: str, category: str) -> str | None:
    try:
        search_query = f"{title} trailer"
        if category and ("музыка" in category.lower() or "music" in category.lower()):
            search_query = f"{title} official video"

        results = YoutubeSearch(search_query, max_results=1).to_dict()
        return results[0]["id"] if results else None
    except Exception:
        return None


async def request_llm_candidates(
    system_instruction: str,
    force_lite_mode: bool = False,
) -> tuple[list[dict[str, str]], str]:
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is missing")

    payload = {
        "contents": [{"parts": [{"text": system_instruction}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }

    preferred_chain = [*FALLBACK_MODEL_NAMES, PRIMARY_MODEL_NAME] if force_lite_mode else [PRIMARY_MODEL_NAME, *FALLBACK_MODEL_NAMES]
    model_chain: list[str] = []
    for model_name in preferred_chain:
        if model_name not in model_chain:
            model_chain.append(model_name)

    last_error: Exception | None = None
    async with httpx.AsyncClient() as client:
        for model_index, model_name in enumerate(model_chain):
            max_attempts = 3 if model_index == 0 else 2
            url = gemini_url_for_model(model_name)
            for attempt in range(max_attempts):
                try:
                    response = await client.post(url, json=payload, timeout=45.0)
                    if response.status_code != 200:
                        raise RuntimeError(f"{model_name} status {response.status_code}: {response.text[:160]}")
                    data = response.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = normalize_recommendations(raw_text)
                    if parsed:
                        return parsed, model_name
                    raise RuntimeError(f"{model_name} returned empty recommendations")
                except Exception as exc:
                    last_error = exc
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(1.1 * (2**attempt))
                    continue

    raise RuntimeError(str(last_error) if last_error else "LLM request failed on all models")


def ensure_runtime_schema() -> None:
    with engine.begin() as conn:
        pref_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('user_preferences')")).fetchall()
        }
        if "onboarding_completed" not in pref_columns:
            conn.execute(
                text(
                    "ALTER TABLE user_preferences "
                    "ADD COLUMN onboarding_completed BOOLEAN DEFAULT 0"
                )
            )
            conn.execute(
                text(
                    "UPDATE user_preferences SET onboarding_completed = 0 "
                    "WHERE onboarding_completed IS NULL"
                )
            )

        user_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('users')")).fetchall()
        }
        if "is_blocked" not in user_columns:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
            )
            conn.execute(
                text("UPDATE users SET is_blocked = 0 WHERE is_blocked IS NULL")
            )
        if "daily_limit" not in user_columns:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN daily_limit INTEGER")
            )


Base.metadata.create_all(bind=engine)
ensure_runtime_schema()

app = FastAPI(title="AI Media Universe - Diploma Project")

frontend_dist_dir = BASE_DIR / "frontend" / "dist"
frontend_assets_dir = frontend_dist_dir / "assets"
app.mount("/assets", StaticFiles(directory=frontend_assets_dir, check_dir=False), name="frontend-assets")


def initialize_admin_defaults() -> None:
    db = SessionLocal()
    try:
        get_admin_setting(db, "force_lite_mode", "0")
        get_admin_setting(db, "default_daily_limit", str(DEFAULT_DAILY_LIMIT))
    finally:
        db.close()


initialize_admin_defaults()


class UserCreate(BaseModel):
    username: str
    password: str


class UserRequest(BaseModel):
    query: str
    session_id: str
    temporary: bool = False
    mood: str | None = None
    company: str | None = None
    time_minutes: int | None = None
    assistant_mode: str | None = "balanced"


class PreferencesUpdate(BaseModel):
    favorite_categories: list[str] = Field(default_factory=list)
    disliked_categories: list[str] = Field(default_factory=list)
    favorite_platforms: list[str] = Field(default_factory=list)
    preferred_language: str = "ru"
    age_rating: str = "any"
    discovery_mode: str = "balanced"


class FeedbackCreate(BaseModel):
    session_id: str | None = None
    query_text: str | None = None
    title: str
    category: str | None = None
    feedback_type: str


class AdminSettingsUpdate(BaseModel):
    force_lite_mode: bool | None = None
    default_daily_limit: int | None = None


class AdminUserUpdate(BaseModel):
    is_admin: bool | None = None
    is_blocked: bool | None = None
    daily_limit: int | None = None


class AdminRuleCreate(BaseModel):
    title: str | None = None
    category: str | None = None
    rule_type: str
    notes: str | None = None


class AdminPinnedCreate(BaseModel):
    title: str
    year_genre: str | None = None
    description: str
    category: str | None = None
    why_this: str | None = None
    video_id: str | None = None
    is_active: bool = True

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")

    is_admin = db.query(User).count() == 0
    hashed_pwd = get_password_hash(user.password)

    new_user = User(username=user.username, hashed_password=hashed_pwd, is_admin=is_admin)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    prefs = get_or_create_preferences(db, new_user.id)
    token = create_access_token(data={"sub": new_user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_admin": is_admin,
        "username": new_user.username,
        "onboarding_completed": bool(prefs.onboarding_completed),
    }


@app.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if bool(user.is_blocked):
        raise HTTPException(status_code=403, detail="Аккаунт временно ограничен администратором")

    prefs = get_or_create_preferences(db, user.id)
    token = create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_admin": user.is_admin,
        "username": user.username,
        "onboarding_completed": bool(prefs.onboarding_completed),
    }


@app.get("/")
async def serve_index():
    react_index = frontend_dist_dir / "index.html"
    if react_index.exists():
        return FileResponse(react_index)
    return FileResponse(asset_path("templates", "index.html"))


@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(asset_path("manifest.json"), media_type="application/manifest+json")


@app.get("/icon.png")
async def serve_icon():
    return FileResponse(asset_path("icon.png"))


@app.get("/service-worker.js")
async def serve_sw():
    return FileResponse(asset_path("service-worker.js"), media_type="application/javascript")


@app.get("/sakura.gif")
async def serve_gif():
    gif_path = asset_path("sakura.gif")
    if not gif_path.exists():
        raise HTTPException(status_code=404, detail="GIF файл не найден")
    return FileResponse(gif_path)


@app.get("/health")
async def healthcheck():
    download_file = resolve_download_file()
    return {
        "status": "ok",
        "gemini_configured": bool(api_key),
        "gemini_primary_model": PRIMARY_MODEL_NAME,
        "gemini_fallback_models": FALLBACK_MODEL_NAMES,
        "desktop_download_available": bool(download_file),
        "download_file": download_file.name if download_file else None,
    }


@app.get("/download")
async def download_app():
    download_file = resolve_download_file()
    if not download_file:
        raise HTTPException(
            status_code=404,
            detail="Файл приложения не найден. Добавь MediaAI.exe в dist/MediaAI/ или dist/",
        )

    return FileResponse(
        path=download_file,
        filename=download_file.name,
        media_type="application/octet-stream",
    )


@app.get("/api/admin/settings")
def admin_get_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    return {
        "force_lite_mode": get_force_lite_mode(db),
        "default_daily_limit": get_default_daily_limit(db),
        "primary_model": PRIMARY_MODEL_NAME,
        "fallback_models": FALLBACK_MODEL_NAMES,
    }


@app.put("/api/admin/settings")
def admin_update_settings(
    payload: AdminSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    if payload.force_lite_mode is not None:
        set_admin_setting(db, "force_lite_mode", "1" if payload.force_lite_mode else "0")
    if payload.default_daily_limit is not None:
        limit_value = max(1, int(payload.default_daily_limit))
        set_admin_setting(db, "default_daily_limit", str(limit_value))

    return {
        "force_lite_mode": get_force_lite_mode(db),
        "default_daily_limit": get_default_daily_limit(db),
    }


@app.get("/api/admin/stats")
def admin_get_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    users = db.query(User).all()
    history_rows = db.query(HistoryEntry).all()
    feedback_rows = db.query(RecommendationFeedback).all()
    usage_rows = db.query(ApiUsageEvent).all()

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_users_7d = (
        db.query(HistoryEntry.user_id)
        .filter(HistoryEntry.timestamp >= seven_days_ago)
        .distinct()
        .count()
    )

    query_counter: Counter[str] = Counter()
    for row in history_rows:
        query = str(row.user_query or "").strip()
        if query:
            query_counter[query] += 1

    model_counter: Counter[str] = Counter()
    status_counter: Counter[int] = Counter()
    for row in usage_rows:
        model_counter[str(row.model_name or "unknown")] += 1
        status_counter[int(row.status_code or 0)] += 1

    return {
        "users_total": len(users),
        "users_admins": sum(1 for u in users if u.is_admin),
        "users_blocked": sum(1 for u in users if u.is_blocked),
        "active_users_7d": active_users_7d,
        "queries_total": len(history_rows),
        "feedback_total": len(feedback_rows),
        "content_rules_total": db.query(AdminContentRule).count(),
        "pinned_total_active": db.query(AdminPinnedRecommendation).filter(AdminPinnedRecommendation.is_active.is_(True)).count(),
        "api_429_count": status_counter.get(429, 0),
        "top_queries": [{"query": q, "count": c} for q, c in query_counter.most_common(8)],
        "model_usage": [{"model": m, "count": c} for m, c in model_counter.most_common(10)],
    }


@app.get("/api/admin/users")
def admin_get_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    users = db.query(User).order_by(User.id).all()
    result = []
    for user in users:
        history_count = db.query(HistoryEntry).filter(HistoryEntry.user_id == user.id).count()
        feedback_count = db.query(RecommendationFeedback).filter(RecommendationFeedback.user_id == user.id).count()
        queries_today = count_user_today_queries(db, user.id)
        result.append(
            {
                "id": user.id,
                "username": user.username,
                "is_admin": bool(user.is_admin),
                "is_blocked": bool(user.is_blocked),
                "daily_limit": user.daily_limit,
                "effective_daily_limit": get_user_daily_limit(db, user),
                "history_count": history_count,
                "feedback_count": feedback_count,
                "queries_today": queries_today,
            }
        )
    return result


@app.put("/api/admin/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.id == current_admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="Нельзя снять admin с текущего аккаунта")

    if payload.is_admin is not None:
        user.is_admin = bool(payload.is_admin)
    if payload.is_blocked is not None:
        user.is_blocked = bool(payload.is_blocked)
    if payload.daily_limit is not None:
        user.daily_limit = max(1, int(payload.daily_limit))

    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "is_blocked": bool(user.is_blocked),
        "daily_limit": user.daily_limit,
    }


@app.delete("/api/admin/users/{user_id}/history")
def admin_reset_user_history(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    db.query(HistoryEntry).filter(HistoryEntry.user_id == user_id).delete()
    db.query(RecommendationFeedback).filter(RecommendationFeedback.user_id == user_id).delete()
    db.query(ApiUsageEvent).filter(ApiUsageEvent.user_id == user_id).delete()
    db.commit()
    return {"status": "ok"}


@app.get("/api/admin/content-rules")
def admin_get_content_rules(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    rows = db.query(AdminContentRule).order_by(desc(AdminContentRule.created_at)).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "category": row.category,
            "rule_type": row.rule_type,
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@app.post("/api/admin/content-rules")
def admin_create_content_rule(
    payload: AdminRuleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    rule_type = (payload.rule_type or "").strip().lower()
    if rule_type not in {"blacklist", "whitelist"}:
        raise HTTPException(status_code=400, detail="rule_type должен быть blacklist или whitelist")
    if not (payload.title or payload.category):
        raise HTTPException(status_code=400, detail="Нужно указать title или category")

    row = AdminContentRule(
        title=(payload.title or "").strip() or None,
        category=(payload.category or "").strip() or None,
        rule_type=rule_type,
        notes=(payload.notes or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@app.delete("/api/admin/content-rules/{rule_id}")
def admin_delete_content_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    row = db.query(AdminContentRule).filter(AdminContentRule.id == rule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@app.get("/api/admin/pinned")
def admin_get_pinned(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    rows = db.query(AdminPinnedRecommendation).order_by(desc(AdminPinnedRecommendation.created_at)).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "year_genre": row.year_genre,
            "description": row.description,
            "category": row.category,
            "why_this": row.why_this,
            "video_id": row.video_id,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@app.post("/api/admin/pinned")
def admin_create_pinned(
    payload: AdminPinnedCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    row = AdminPinnedRecommendation(
        title=(payload.title or "").strip(),
        year_genre=(payload.year_genre or "").strip() or None,
        description=(payload.description or "").strip(),
        category=(payload.category or "").strip() or None,
        why_this=(payload.why_this or "").strip() or None,
        video_id=(payload.video_id or "").strip() or None,
        is_active=bool(payload.is_active),
    )
    if not row.title or not row.description:
        raise HTTPException(status_code=400, detail="title и description обязательны")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@app.put("/api/admin/pinned/{pinned_id}")
def admin_update_pinned(
    pinned_id: int,
    payload: AdminPinnedCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    row = db.query(AdminPinnedRecommendation).filter(AdminPinnedRecommendation.id == pinned_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    row.title = (payload.title or "").strip() or row.title
    row.year_genre = (payload.year_genre or "").strip() or None
    row.description = (payload.description or "").strip() or row.description
    row.category = (payload.category or "").strip() or None
    row.why_this = (payload.why_this or "").strip() or None
    row.video_id = (payload.video_id or "").strip() or None
    row.is_active = bool(payload.is_active)
    db.commit()
    db.refresh(row)
    return {"status": "ok"}


@app.delete("/api/admin/pinned/{pinned_id}")
def admin_delete_pinned(
    pinned_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    row = db.query(AdminPinnedRecommendation).filter(AdminPinnedRecommendation.id == pinned_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@app.get("/api/admin/export")
def admin_export(
    scope: str = "users",
    export_format: str = "json",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    scope = (scope or "users").lower()
    export_format = (export_format or "json").lower()

    if scope == "users":
        rows = db.query(User).order_by(User.id).all()
        data = [
            {
                "id": row.id,
                "username": row.username,
                "is_admin": bool(row.is_admin),
                "is_blocked": bool(row.is_blocked),
                "daily_limit": row.daily_limit,
            }
            for row in rows
        ]
    elif scope == "history":
        rows = db.query(HistoryEntry).order_by(desc(HistoryEntry.timestamp)).all()
        data = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "session_id": row.session_id,
                "user_query": row.user_query,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]
    elif scope == "feedback":
        rows = db.query(RecommendationFeedback).order_by(desc(RecommendationFeedback.timestamp)).all()
        data = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "title": row.title,
                "category": row.category,
                "feedback_type": row.feedback_type,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]
    elif scope == "usage":
        rows = db.query(ApiUsageEvent).order_by(desc(ApiUsageEvent.created_at)).all()
        data = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "endpoint": row.endpoint,
                "model_name": row.model_name,
                "status_code": row.status_code,
                "source": row.source,
                "query_text": row.query_text,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    else:
        raise HTTPException(status_code=400, detail="scope должен быть users/history/feedback/usage")

    if export_format == "json":
        return Response(
            content=json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=admin_{scope}.json"},
        )
    if export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(data[0].keys()) if data else ["empty"])
        writer.writeheader()
        for row in data:
            writer.writerow(row)
        return Response(
            content=output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=admin_{scope}.csv"},
        )
    raise HTTPException(status_code=400, detail="export_format должен быть json или csv")


@app.get("/api/preferences")
def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = get_or_create_preferences(db, current_user.id)
    return preferences_to_dict(prefs)


@app.put("/api/preferences")
def update_preferences(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = get_or_create_preferences(db, current_user.id)

    prefs.favorite_categories = to_csv_values(clean_list(payload.favorite_categories, limit=12))
    prefs.disliked_categories = to_csv_values(clean_list(payload.disliked_categories, limit=12))
    prefs.favorite_platforms = to_csv_values(clean_list(payload.favorite_platforms, limit=12))
    prefs.preferred_language = (payload.preferred_language or "ru").strip()[:20] or "ru"
    prefs.age_rating = (payload.age_rating or "any").strip()[:20] or "any"
    prefs.discovery_mode = (payload.discovery_mode or "balanced").strip()[:20] or "balanced"

    db.commit()
    db.refresh(prefs)
    return preferences_to_dict(prefs)


@app.get("/api/onboarding/status")
def onboarding_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = get_or_create_preferences(db, current_user.id)
    return {"completed": bool(prefs.onboarding_completed)}


@app.put("/api/onboarding/complete")
def complete_onboarding(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = get_or_create_preferences(db, current_user.id)

    prefs.favorite_categories = to_csv_values(clean_list(payload.favorite_categories, limit=12))
    prefs.disliked_categories = to_csv_values(clean_list(payload.disliked_categories, limit=12))
    prefs.favorite_platforms = to_csv_values(clean_list(payload.favorite_platforms, limit=12))
    prefs.preferred_language = (payload.preferred_language or "ru").strip()[:20] or "ru"
    prefs.age_rating = (payload.age_rating or "any").strip()[:20] or "any"
    prefs.discovery_mode = (payload.discovery_mode or "balanced").strip()[:20] or "balanced"
    prefs.onboarding_completed = True

    db.commit()
    db.refresh(prefs)
    return {"completed": True, "preferences": preferences_to_dict(prefs)}


@app.post("/api/feedback")
def submit_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feedback_type = (payload.feedback_type or "").strip().lower()
    if feedback_type not in {"like", "dislike", "watched"}:
        raise HTTPException(status_code=400, detail="feedback_type должен быть like/dislike/watched")

    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title обязателен")

    exists = (
        db.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == current_user.id,
            RecommendationFeedback.session_id == (payload.session_id or ""),
            RecommendationFeedback.title == title,
            RecommendationFeedback.feedback_type == feedback_type,
        )
        .first()
    )
    if exists:
        return {"status": "ok", "created": False}

    row = RecommendationFeedback(
        user_id=current_user.id,
        session_id=(payload.session_id or "").strip() or None,
        query_text=(payload.query_text or "").strip() or None,
        title=title,
        category=(payload.category or "").strip() or None,
        feedback_type=feedback_type,
    )
    db.add(row)
    db.commit()
    return {"status": "ok", "created": True}


@app.get("/api/insights")
def get_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    history_rows = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.user_id == current_user.id)
        .order_by(desc(HistoryEntry.timestamp))
        .all()
    )

    category_counter: Counter[str] = Counter()
    total_recommendations = 0
    sessions = {row.session_id for row in history_rows if row.session_id}

    for row in history_rows:
        if not row.ai_response_json:
            continue
        try:
            payload = json.loads(row.ai_response_json)
        except Exception:
            continue

        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            continue

        for item in payload:
            if not isinstance(item, dict):
                continue
            total_recommendations += 1
            category = str(item.get("category") or "").strip()
            if category:
                category_counter[category] += 1

    feedback_rows = (
        db.query(RecommendationFeedback)
        .filter(RecommendationFeedback.user_id == current_user.id)
        .all()
    )
    feedback_counter = Counter((row.feedback_type or "").lower() for row in feedback_rows)

    top_categories = [name for name, _ in category_counter.most_common(3)]
    daily_limit = get_user_daily_limit(db, current_user)
    queries_today = count_user_today_queries(db, current_user.id)

    return {
        "total_queries": len(history_rows),
        "total_sessions": len(sessions),
        "total_recommendations": total_recommendations,
        "top_categories": top_categories,
        "favorite_category": top_categories[0] if top_categories else "Not enough data",
        "feedback_likes": feedback_counter.get("like", 0),
        "feedback_dislikes": feedback_counter.get("dislike", 0),
        "feedback_watched": feedback_counter.get("watched", 0),
        "daily_limit": daily_limit,
        "queries_today": queries_today,
        "remaining_today": max(0, daily_limit - queries_today),
    }


@app.post("/recommend")
async def get_recommendation(
    request: UserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query_text = (request.query or "").strip()
    if not query_text:
        return {"recommendations": "Введите запрос, чтобы я подобрал рекомендации.", "is_json": False}

    if not request.temporary:
        daily_limit = get_user_daily_limit(db, current_user)
        queries_today = count_user_today_queries(db, current_user.id)
        if queries_today >= daily_limit:
            log_usage_event(
                db=db,
                user_id=current_user.id,
                endpoint="/recommend",
                status_code=429,
                model_name=None,
                source="daily_limit",
                query_text=query_text,
            )
            return {
                "recommendations": (
                    f"Достигнут дневной лимит запросов ({daily_limit}). "
                    "Попробуй позже или обратись к администратору."
                ),
                "is_json": False,
            }

    prefs = get_or_create_preferences(db, current_user.id)
    force_lite_mode = get_force_lite_mode(db)
    recent_titles = collect_recent_titles(db, current_user.id, limit=80)
    feedback_summary = collect_feedback_summary(db, current_user.id, limit=300)
    admin_rules = get_admin_rules(db)

    personalization_context = build_personalization_context(
        request=request,
        prefs=prefs,
        recent_titles=recent_titles,
        feedback_summary=feedback_summary,
    )

    system_instruction = (
        "You are a personal entertainment assistant.\n"
        "You provide personalized recommendations for movies, series, games, music and anime.\n"
        "Use the following personalization context:\n"
        f"{personalization_context}\n\n"
        "Rules:\n"
        "1) Return exactly 6 candidate recommendations in JSON array.\n"
        "2) Each recommendation must include: title, year_genre, description, category, why_this.\n"
        "3) Description should be 2-4 sentences in Markdown with strong personalization.\n"
        "4) In every description, highlight at least 2 key terms/entities using **bold**.\n"
        "5) why_this must be 1 concise sentence: why it fits this user now.\n"
        "6) Avoid recent repeated titles and disliked signals from context.\n"
        "7) If query asks a specific category, prioritize it.\n"
        "8) Return STRICT JSON array only. No prose outside JSON.\n"
        "9) Never ask the user to уточнить/clarify before giving results; if the query is broad, make reasonable assumptions and still return candidates.\n"
        "Output format example:\n"
        "[{\"title\":\"...\",\"year_genre\":\"...\",\"description\":\"...\",\"category\":\"...\",\"why_this\":\"...\"}]"
    )

    source = "llm"
    llm_candidates: list[dict[str, str]] = []
    llm_model_used = ""
    try:
        llm_candidates, llm_model_used = await request_llm_candidates(
            system_instruction,
            force_lite_mode=force_lite_mode,
        )
        source = f"llm:{llm_model_used}"
    except Exception as exc:
        status_code = 429 if "429" in str(exc) else 500
        log_usage_event(
            db=db,
            user_id=current_user.id,
            endpoint="/recommend",
            status_code=status_code,
            model_name=llm_model_used or None,
            source="llm_error",
            query_text=query_text,
        )
        source = "fallback"

    selected = select_recommendations(llm_candidates, recent_titles, feedback_summary, limit=3)
    selected = apply_admin_rules(selected, admin_rules)
    if len(selected) < 3:
        source = "fallback"
        fallback = build_fallback_recommendations(request, prefs, recent_titles, feedback_summary, limit=3)
        fallback = apply_admin_rules(fallback, admin_rules)
        merged: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in selected + fallback:
            key = normalize_title(item.get("title", ""))
            if not key or key in seen:
                continue
            merged.append(item)
            seen.add(key)
            if len(merged) >= 3:
                break
        selected = merged

    selected = inject_pinned_recommendations(db, query_text, selected, limit=3)

    for item in selected:
        item["why_this"] = build_why_this(item, request, prefs)
        if not item.get("video_id"):
            item["video_id"] = find_trailer(item.get("title", ""), item.get("category", ""))

    if not selected:
        return {
            "recommendations": "Сейчас не получилось подобрать варианты. Попробуй переформулировать запрос чуть точнее.",
            "is_json": False,
        }

    history_text = ""
    for item in selected:
        history_text += (
            f"**{item.get('title')}**\n"
            f"{item.get('description')}\n"
            f"_Почему подходит_: {item.get('why_this')}\n\n"
        )

    if not request.temporary:
        new_entry = HistoryEntry(
            session_id=request.session_id,
            user_query=query_text,
            ai_response=history_text,
            ai_response_json=json.dumps(selected, ensure_ascii=False),
            user_id=current_user.id,
        )
        db.add(new_entry)
        db.commit()

    log_usage_event(
        db=db,
        user_id=current_user.id,
        endpoint="/recommend",
        status_code=200,
        model_name=llm_model_used or ("fallback" if source == "fallback" else None),
        source=source,
        query_text=query_text,
    )

    return {"recommendations": selected, "is_json": True, "source": source}


@app.get("/api/sessions")
def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    history = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.user_id == current_user.id)
        .order_by(desc(HistoryEntry.timestamp))
        .all()
    )

    sessions_map: dict[str, dict[str, Any]] = {}
    for item in history:
        if not item.session_id:
            continue

        if item.session_id not in sessions_map:
            sessions_map[item.session_id] = {
                "session_id": item.session_id,
                "title": item.user_query or "Новый чат",
                "message_count": 0,
                "last_timestamp": item.timestamp,
                "preview": history_preview(item),
            }

        sessions_map[item.session_id]["message_count"] += 1

    sessions = list(sessions_map.values())
    sessions.sort(key=lambda x: x["last_timestamp"] or datetime.min, reverse=True)

    for session in sessions:
        dt = session.get("last_timestamp")
        session["last_timestamp"] = dt.isoformat() if isinstance(dt, datetime) else None

    return sessions


@app.get("/api/chat/{session_id}")
def get_chat_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(HistoryEntry)
        .filter(
            HistoryEntry.session_id == session_id,
            HistoryEntry.user_id == current_user.id,
        )
        .order_by(HistoryEntry.id)
        .all()
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
