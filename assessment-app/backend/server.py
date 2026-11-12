import os
import shutil
import tempfile
from typing import List, Optional
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import Base, engine, get_db
import db_models
from auth import verify_google_token, create_access_token, get_current_user
from api_schemas import GoogleAuthRequest, AuthResponse, TopicBucketCreate, TopicBucketResponse, GenerateRequest
from pipeline import MasterIngestionPipeline
from generator import QuestionGeneratorEngine
from models import IngestionResult

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Psychometric Assessment Generation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ingestion_pipeline = MasterIngestionPipeline()
generator_engine = QuestionGeneratorEngine()

@app.post("/api/auth/google", response_model=AuthResponse)
def google_auth(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
    id_info = verify_google_token(payload.id_token)
    google_sub = id_info["sub"]
    email = id_info.get("email")
    name = id_info.get("name")
    picture = id_info.get("picture")

    user = db.query(db_models.User).filter(db_models.User.google_sub == google_sub).first()
    if not user:
        user = db_models.User(
            google_sub=google_sub,
            email=email,
            full_name=name,
            avatar_url=picture
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url
        }
    }

@app.post("/api/buckets", response_model=TopicBucketResponse)
def create_bucket(
    bucket_in: TopicBucketCreate,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db_models.TopicBucket(
        user_id=current_user.id,
        title=bucket_in.title,
        description=bucket_in.description
    )
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return bucket

@app.get("/api/buckets", response_model=List[TopicBucketResponse])
def list_buckets(
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    buckets = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.user_id == current_user.id
    ).all()
    results = []
    for b in buckets:
        results.append(TopicBucketResponse(
            id=b.id,
            title=b.title,
            description=b.description,
            created_at=b.created_at,
            sources_count=len(b.sources),
            items_count=len(b.generated_items)
        ))
    return results

@app.post("/api/buckets/{bucket_id}/sources/file")
def ingest_file_to_bucket(
    bucket_id: UUID,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = ingestion_pipeline.ingest_file(tmp_path, title=title or file.filename)
        source_record = db_models.TopicSource(
            bucket_id=bucket.id,
            source_type=result.source_type,
            title=result.source_title,
            extracted_content=result.model_dump()
        )
        db.add(source_record)
        db.commit()
        return {"status": "success", "source_id": str(source_record.id), "chunks": result.total_chunks}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.post("/api/buckets/{bucket_id}/sources/url")
def ingest_url_to_bucket(
    bucket_id: UUID,
    url: str = Form(...),
    title: Optional[str] = Form(None),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")

    result = ingestion_pipeline.ingest_url(url, title=title)
    source_record = db_models.TopicSource(
        bucket_id=bucket.id,
        source_type=result.source_type,
        title=result.source_title,
        source_url=url,
        extracted_content=result.model_dump()
    )
    db.add(source_record)
    db.commit()
    return {"status": "success", "source_id": str(source_record.id), "chunks": result.total_chunks}

@app.post("/api/buckets/{bucket_id}/generate")
def generate_bucket_test(
    bucket_id: UUID,
    req: GenerateRequest,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    if not bucket.sources:
        raise HTTPException(status_code=400, detail="Cannot generate questions. Bucket has no sources.")

    all_chunks = []
    for src in bucket.sources:
        src_data = IngestionResult.model_validate(src.extracted_content)
        all_chunks.extend(src_data.chunks)

    composite_source = IngestionResult(
        source_title=bucket.title,
        source_type="text",
        total_chunks=len(all_chunks),
        chunks=all_chunks
    )

    items = generator_engine.generate_questions(
        ingested_source=composite_source,
        count=req.count,
        target_typology=req.target_typology,
        question_type=req.question_type,
        inject_external_stimulus=req.inject_external_stimulus,
        preferred_stimulus_modality=req.preferred_stimulus_modality,
        custom_style_instructions=req.custom_style_instructions
    )

    for item in items:
        rec = db_models.GeneratedQuestionItem(
            bucket_id=bucket.id,
            catalog_typology=item.catalog_typology,
            bloom_level=item.bloom_level,
            question_type=item.question_type,
            stem=item.stem,
            stimulus=item.stimulus.model_dump() if item.stimulus else None,
            options=[opt.model_dump() for opt in item.options],
            correct_option=item.correct_option,
            pedagogical_feedback=item.pedagogical_feedback,
            distractor_rationales=item.distractor_rationales,
            citation=item.citation.model_dump()
        )
        db.add(rec)
    db.commit()
    return items

@app.get("/api/buckets/{bucket_id}/items")
def get_bucket_items(
    bucket_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == current_user.id
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    return bucket.generated_items
