import os
import shutil
import time
from datetime import datetime
import tempfile
from typing import List, Optional
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine, get_db
import db_models
from auth import verify_google_token, create_access_token, get_current_user
from api_schemas import GoogleAuthRequest, AuthResponse, TopicBucketCreate, TopicBucketResponse, GenerateRequest, SourceResponse
from pipeline import MasterIngestionPipeline
from generator import QuestionGeneratorEngine
from classifier import SampleClassifier
from models import IngestionResult

Base.metadata.create_all(bind=engine)

# Existing databases were created before TopicSource gained a `purpose`
# column, and create_all() does not alter existing tables. Add it once,
# idempotently, so older deployments pick it up on restart.
try:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE topic_sources ADD COLUMN IF NOT EXISTS purpose VARCHAR(20) NOT NULL DEFAULT 'source'"))
except Exception as _e:  # noqa: BLE001 - startup must not fail on this
    print(f"[Startup] Could not ensure topic_sources.purpose column: {_e}")


def normalize_purpose(purpose):
    """Return 'source' or 'example'; anything else is a client error."""
    value = (purpose or "source").strip().lower()
    if value not in ("source", "example"):
        raise HTTPException(status_code=400, detail="purpose must be 'source' or 'example'.")
    return value


def build_example_style(example_sources):
    """Analyse a bucket's example questions and turn them into generation style.

    Returns (effective_typology, style_guidance, style_examples):
      - effective_typology: the typology the classifier detected in the
        examples, or None when there are no examples / analysis failed.
      - style_guidance: short text for the prompt's ADDITIONAL DIRECTIVES,
        built from the classifier's analysis (typology, Bloom level,
        structural features, recommended guidance). None when unusable.
      - style_examples: the example questions' text, truncated, to be shown
        to the model as a style reference only. None when there are none.

    Classifier failure must never break generation: on any error we fall
    back to the raw example text as the style reference, and if even that
    is unavailable the caller falls back to the request's own settings.
    """
    if not example_sources:
        return None, None, None
    example_text = ""
    for src in example_sources:
        try:
            src_data = IngestionResult.model_validate(src.extracted_content)
            example_text += src_data.to_llm_context() + chr(10)
        except Exception as e:
            print("[ExampleStyle] Skipping unreadable example source %s: %s" % (getattr(src, "id", "?"), e))
    example_text = example_text.strip()
    if not example_text:
        return None, None, None

    style_examples = example_text[:6000]
    style_guidance = None
    effective_typology = None
    try:
        classified = SampleClassifier().analyze_samples(example_text[:8000])
        effective_typology = classified.detected_typology or None
        features = ", ".join(classified.structural_features) or "not specified"
        style_guidance = (
            "STYLE REFERENCE - analysed from this topic's example questions "
            "(these examples are the PRIMARY basis for what to generate):" + chr(10)
            + "- Detected question typology: " + str(classified.detected_typology) + chr(10)
            + "- Bloom's level: " + str(classified.bloom_level) + chr(10)
            + "- Structural features: " + features + chr(10)
            + "- Guidance: " + str(classified.recommended_prompt_guidance)
        )
        print("[ExampleStyle] Analysed %d example file(s): typology=%s bloom=%s"
              % (len(example_sources), classified.detected_typology, classified.bloom_level))
    except Exception as e:
        print("[ExampleStyle] Classifier failed, using raw example text as style reference: %s" % e)
        style_guidance = (
            "STYLE REFERENCE - this topic's example questions are the PRIMARY "
            "basis for what to generate: imitate their format, structure, "
            "phrasing, and cognitive level as closely as possible."
        )
    return effective_typology, style_guidance, style_examples


def get_bucket_or_404(db, bucket_id, user_id):
    bucket = db.query(db_models.TopicBucket).filter(
        db_models.TopicBucket.id == bucket_id,
        db_models.TopicBucket.user_id == user_id,
    ).first()
    if not bucket:
        raise HTTPException(status_code=404, detail="Topic bucket not found.")
    return bucket


def source_to_response(source):
    chunks = 0
    try:
        chunks = int((source.extracted_content or {}).get("total_chunks", 0))
    except Exception:  # noqa: BLE001 - malformed stored content must not break listing
        chunks = 0
    return SourceResponse(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        purpose=getattr(source, "purpose", None) or "source",
        source_url=source.source_url,
        chunks=chunks,
        created_at=source.created_at,
    )

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
    purpose: Optional[str] = Form("source"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    purpose = normalize_purpose(purpose)

    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = ingestion_pipeline.ingest_file(tmp_path, title=title or file.filename)
        source_record = db_models.TopicSource(
            bucket_id=bucket.id,
            source_type=result.source_type,
            title=result.source_title,
            purpose=purpose,
            extracted_content=result.model_dump()
        )
        db.add(source_record)
        db.commit()
        return {"status": "success", "source_id": str(source_record.id), "chunks": result.total_chunks, "purpose": purpose}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.post("/api/buckets/{bucket_id}/sources/url")
def ingest_url_to_bucket(
    bucket_id: UUID,
    url: str = Form(...),
    title: Optional[str] = Form(None),
    purpose: Optional[str] = Form("source"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    purpose = normalize_purpose(purpose)

    result = ingestion_pipeline.ingest_url(url, title=title)
    source_record = db_models.TopicSource(
        bucket_id=bucket.id,
        source_type=result.source_type,
        title=result.source_title,
        purpose=purpose,
        source_url=url,
        extracted_content=result.model_dump()
    )
    db.add(source_record)
    db.commit()
    return {"status": "success", "source_id": str(source_record.id), "chunks": result.total_chunks, "purpose": purpose}


@app.post("/api/buckets/{bucket_id}/sources/files")
def ingest_files_to_bucket(
    bucket_id: UUID,
    files: List[UploadFile] = File(...),
    purpose: Optional[str] = Form("source"),
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk upload: ingest several files in one request, all with the
    same purpose (source material or example questions). Each file is
    ingested independently, so one bad file does not lose the rest."""
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    purpose = normalize_purpose(purpose)
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    results = []
    for upload in files:
        filename = upload.filename or "unnamed file"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            shutil.copyfileobj(upload.file, tmp)
            tmp_path = tmp.name
        try:
            result = ingestion_pipeline.ingest_file(tmp_path, title=filename)
            source_record = db_models.TopicSource(
                bucket_id=bucket.id,
                source_type=result.source_type,
                title=result.source_title,
                purpose=purpose,
                extracted_content=result.model_dump()
            )
            db.add(source_record)
            db.commit()
            results.append({"filename": filename, "status": "success",
                            "source_id": str(source_record.id),
                            "chunks": result.total_chunks, "purpose": purpose})
        except Exception as exc:  # noqa: BLE001 - per-file failure must not abort the batch
            db.rollback()
            results.append({"filename": filename, "status": "error", "detail": str(exc)})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    return {"results": results}


@app.get("/api/buckets/{bucket_id}/sources", response_model=List[SourceResponse])
def list_bucket_sources(
    bucket_id: UUID,
    current_user: db_models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bucket = get_bucket_or_404(db, bucket_id, current_user.id)
    sources = sorted(bucket.sources, key=lambda src: src.created_at or datetime.min)
    return [source_to_response(src) for src in sources]

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
    # Only source material is question content. Example questions are
    # style examples; their text must not be used as grounding content.
    generate_started = time.monotonic()
    content_sources = [src for src in bucket.sources
                       if (getattr(src, "purpose", None) or "source") == "source"]
    example_sources = [src for src in bucket.sources
                       if (getattr(src, "purpose", None) or "source") == "example"]
    print("[Generate] bucket=%s sources=%d examples=%d count=%s" % (bucket_id, len(content_sources), len(example_sources), req.count))
    if not content_sources:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate questions. This bucket has no source material yet. "
                   "Example questions are style examples and are not used as question content.",
        )

    all_chunks = []
    for src in content_sources:
        src_data = IngestionResult.model_validate(src.extracted_content)
        all_chunks.extend(src_data.chunks)

    composite_source = IngestionResult(
        source_title=bucket.title,
        source_type="text",
        total_chunks=len(all_chunks),
        chunks=all_chunks
    )

    # Example questions are the PRIMARY basis for the style of what gets
    # generated: the classifier analyses them (typology, Bloom level,
    # structure) and their text is passed as a style reference. When
    # examples exist, their detected typology drives generation; the
    # typology picked in the UI is the fallback when there are none.
    detected_typology, style_guidance, style_examples = build_example_style(example_sources)
    effective_typology = detected_typology or req.target_typology
    style_instructions = style_guidance
    if req.custom_style_instructions:
        style_instructions = (style_instructions + chr(10) + req.custom_style_instructions
                              if style_instructions else req.custom_style_instructions)
    print("[Generate] effective_typology=%s style_examples=%s" % (effective_typology, "yes" if style_examples else "no"))
    style_started = time.monotonic()
    items = generator_engine.generate_questions(
        ingested_source=composite_source,
        count=req.count,
        target_typology=effective_typology,
        question_type=req.question_type,
        inject_external_stimulus=req.inject_external_stimulus,
        preferred_stimulus_modality=req.preferred_stimulus_modality,
        custom_style_instructions=style_instructions,
        style_examples=style_examples,
    )
    print("[Generate] done in %.1fs total (style analysis %.1fs, model %.1fs)" % (time.monotonic() - generate_started, style_started - generate_started, time.monotonic() - style_started))

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
